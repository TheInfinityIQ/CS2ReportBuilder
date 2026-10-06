"""Resource-aware admission for independent demo subprocesses, with durable results."""

from __future__ import annotations
import json
import os
import signal
import threading
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from .job_lock import exclusive
from .packet_jobs import process_options


@dataclass(frozen=True)
class Resources:
    cpu: float
    total: int
    available: int


def can_start(resources, estimate, cpu_target=80, memory_target=90):
    reserve = resources.total * (1 - memory_target / 100)
    return resources.cpu < cpu_target - 5 and resources.available - estimate >= reserve


def estimate_memory(demo_bytes, observed_peak, phase):
    # Bounded measurement: viewer-only used ~0.75 GB for a 314 MB demo;
    # core+viewer used ~1.9 GB. Keep headroom and learn larger observed peaks.
    multiplier = 4 if phase == "viewer" else 8
    return max(2 * 1024**3, int(observed_peak * 1.3), demo_bytes * multiplier)


def job_size(item):
    try:
        return Path(item[1]["demo"]).stat().st_size
    except OSError:
        return float("inf")


def _run_queue(
    repo,
    jobs,
    work_root,
    *,
    phase="viewer",
    cpu_target=80,
    memory_target=90,
    max_workers=None,
    cancel_path=None,
    log=print,
    sampler=None,
    spawn=None,
    sleep=time.sleep,
    stop_requested=lambda: False,
):
    """Cancel admissions, not active parsers. One coordinator owns summaries and logs."""
    if not 10 <= cpu_target <= 95 or not 20 <= memory_target <= 95:
        raise ValueError("CPU target must be 10–95%; memory target 20–95%")
    max_workers = min(8, os.cpu_count() or 1) if max_workers is None else max_workers
    if max_workers < 1 or phase not in {"viewer", "prepare"}:
        raise ValueError("Invalid worker count or phase")
    seen = set()
    for job in jobs:
        target = os.path.normcase(str(Path(job["analysis"]).resolve()))
        if target in seen:
            raise ValueError(f"Two jobs target the same analysis: {target}")
        seen.add(target)
    if sampler is None:
        import psutil

        psutil.cpu_percent(None)  # prime the first nonblocking reading

        def sampler():
            memory = psutil.virtual_memory()
            return Resources(psutil.cpu_percent(None), memory.total, memory.available)

    if spawn is None:
        spawn = subprocess.Popen
    work_root = Path(work_root).resolve()
    work_root.mkdir(parents=True, exist_ok=True)
    result = {"phase": phase, "cpu_target": cpu_target, "memory_target": memory_target, "results": []}
    with exclusive(work_root / "coordinator.lock"):
        run = work_root / (datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid4().hex[:8])
        run.mkdir()
        result["run_folder"] = str(run)
        pending, active, peak, cool = sorted(enumerate(jobs), key=job_size), [], 0, 0
        (run / "jobs.json").write_text(json.dumps(jobs, indent=2), encoding="utf-8")
        last_wait_log = -30

        def persist():
            target = run / "summary.json"
            temporary = target.with_suffix(".tmp")
            temporary.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
            temporary.replace(target)

        persist()
        while pending or active:
            for item in list(active):
                process, index, job, stream, output, maximum, reserved = item
                try:
                    import psutil

                    p = psutil.Process(process.pid)
                    rss = p.memory_info().rss + sum(c.memory_info().rss for c in p.children(recursive=True))
                    item[5] = max(maximum, rss)
                except (ImportError, OSError, AttributeError):
                    pass
                except psutil.Error:
                    pass
                code = process.poll()
                if code is None:
                    continue
                stream.close()
                active.remove(item)
                peak = max(peak, item[5])
                try:
                    record = json.loads(output.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    record = {"status": "failed", "detail": f"Worker exited {code}; see its log"}
                if code:
                    record["status"] = "failed"
                record.update(job=job, index=index, peak_bytes=item[5], log=str(stream.name))
                result["results"].append(record)
                persist()
                log(
                    f"[{len(result['results'])}/{len(jobs)}] {Path(job['demo']).name}: {record['status']} · log: {stream.name}"
                )
            cancelled = stop_requested() or (cancel_path is not None and Path(cancel_path).exists())
            if cancelled and pending:
                for index, job in pending:
                    result["results"].append({"index": index, "job": job, "status": "cancelled"})
                pending.clear()
                persist()
                log("Cancellation requested; letting active jobs finish.")
            if pending:
                r = sampler()
                job = pending[0][1]
                try:
                    estimate = estimate_memory(Path(job["demo"]).stat().st_size, peak, phase)
                except OSError as exc:
                    index, job = pending.pop(0)
                    result["results"].append(
                        {"index": index, "job": job, "status": "failed", "detail": str(exc)}
                    )
                    persist()
                    log(f"Missing/unreadable demo: {job['demo']}")
                    continue
                outstanding = sum(max(0, item[6] - item[5]) for item in active)
                headroom = can_start(r, estimate + outstanding, cpu_target, memory_target)
                cool = cool + 1 if headroom else 0
                if headroom and len(active) < max_workers and (not active or cool >= 3):
                    index, job = pending.pop(0)
                    cool = 0
                    spec, output = run / f"{index:04d}.job.json", run / f"{index:04d}.result.json"
                    spec.write_text(json.dumps(job), encoding="utf-8")
                    stream = (run / f"{index:04d}.log").open("w", encoding="utf-8")
                    memory_budget = (
                        r.available + sum(item[5] for item in active) - r.total * (1 - memory_target / 100)
                    )
                    cohort = min(max_workers, max(1, int(memory_budget / estimate)))
                    env = {
                        **os.environ,
                        "PYTHONUTF8": "1",
                        "OMP_NUM_THREADS": "1",
                        "OPENBLAS_NUM_THREADS": "1",
                        "MKL_NUM_THREADS": "1",
                        "RAYON_NUM_THREADS": str(
                            max(1, int((os.cpu_count() or 1) * cpu_target / 100 / cohort))
                        ),
                    }
                    try:
                        process = spawn(
                            [
                                sys.executable,
                                "-u",
                                str(Path(repo) / "scripts/fix_viewer_data.py"),
                                "--worker",
                                str(spec),
                                "--result",
                                str(output),
                                "--phase",
                                phase,
                            ],
                            stdout=stream,
                            stderr=subprocess.STDOUT,
                            env=env,
                            **process_options(),
                        )
                    except OSError as exc:
                        stream.close()
                        result["results"].append(
                            {
                                "index": index,
                                "job": job,
                                "status": "failed",
                                "detail": str(exc),
                                "log": str(stream.name),
                            }
                        )
                        persist()
                        log(f"Could not start {job['demo']}: {exc}")
                        continue
                    active.append([process, index, job, stream, output, 0, estimate])
                    log(
                        f"Starting {Path(job['demo']).name} · {len(active)} active · CPU {r.cpu:.0f}% · RAM {(1 - r.available / r.total) * 100:.0f}%"
                    )
                elif not active and time.monotonic() - last_wait_log >= 30:
                    last_wait_log = time.monotonic()
                    log(
                        f"Waiting for resources · CPU {r.cpu:.0f}% · available RAM {r.available / 1024**3:.1f} GB · next-job reserve {estimate / 1024**3:.1f} GB"
                    )
            if pending or active:
                sleep(1)
        persist()
    return result


def run_queue(repo, jobs, work_root, **options):
    """Ctrl+C stops admissions and waits for already running parsers."""
    requested = threading.Event()
    previous = {}
    if threading.current_thread() is threading.main_thread():
        for sig in (signal.SIGINT, getattr(signal, "SIGBREAK", signal.SIGINT)):
            if sig not in previous:
                previous[sig] = signal.signal(sig, lambda *args: requested.set())
    try:
        return _run_queue(repo, jobs, work_root, stop_requested=requested.is_set, **options)
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
