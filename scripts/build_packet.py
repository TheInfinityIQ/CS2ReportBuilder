"""Build one hand-off packet: everything a fresh AI coach needs to write a Player Study for one player.

    python scripts/build_packet.py --id P_pug_iTrilogyy --player iTrilogyy --steamid 76561198181834733 \
        --batch-dir <folder that holds ONLY this packet's analysed demo folders> --out <packets>/P_pug_iTrilogyy \
        --example examples/mimy/coach_plan_v3.json [--expect 30] [--no-batch-copy] [--kind pug|pro]

What it does (nothing here writes coaching; it only prepares evidence and instructions):
  1. checks the integrity gate on every demo, and that the player is in every demo
  2. computes digest.json and findings_all.json (the software's numbers), then findings_shortlist.json / findings_index.txt
  3. renders PROMPT.md from coach/handoff/PROMPT.md and copies RULES.md and MODULES.md
  4. copies the report software (src/, assets/maps, pyproject.toml), tools/moment_facts.py and an example plan for ANOTHER player
  5. copies the analysed demos to data/batch (unless --no-batch-copy) and writes MANIFEST.json
  6. smoke test: builds a tiny report with the packet's own copy of the software, so a packet that cannot render is never handed out

The number of Teaching Moments is not set anywhere in the packet: the evidence decides (owner ruling 2026-09-29).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from cs2di.analyst import analyse_batch, jsonable  # noqa: E402
from cs2di.digest import build_digest  # noqa: E402
from cs2di.evidence import scan_batch  # noqa: E402

STATUS_ORDER = {"credible": 0, "leaning": 1, "unclear": 2, "no_difference": 3}
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", "_repair_backup")


def fmt(v, nd=3):
    return "None" if v is None else f"{v:.{nd}f}"


def index_line(f: dict) -> str:
    q = f.get("q")
    return (f"{f['status']:<13} | {f['id']} | k/n={f.get('k')}/{f.get('n')} | you {fmt(f.get('rate'))} vs "
            f"{fmt(f.get('baseline_rate'))} | q={'None' if q is None else round(q, 4)} | "
            f"interleaved-splits-agree={f.get('halves_agree')} | examples={len(f.get('examples') or [])}")


def usable(analysis: dict) -> list[dict]:
    fs = [f for f in analysis["findings"] if f["status"] in STATUS_ORDER]
    return sorted(fs, key=lambda f: (STATUS_ORDER[f["status"]], f["q"] if f.get("q") is not None else 9, f["id"]))


def render_prompt(player: str, steamid: str, n: int) -> str:
    t = (REPO / "coach/handoff/PROMPT.md").read_text(encoding="utf-8")
    return t.replace("{{PLAYER}}", player).replace("{{STEAMID}}", steamid).replace("{{N}}", str(n))


README = """# Coach packet: {player}

This folder is a complete, self-contained task. Open `PROMPT.md` and follow it.

- `PROMPT.md`  the task and the steps
- `RULES.md`, `MODULES.md`  the rules and the plan format
- `data/`  the evidence the software computed, and the matches behind it
- `src/`, `tools/`, `assets/`  the report software and helper (Python 3.11+, pandas, pyarrow, scipy)

Packet id: {pid}. {n} matches. Prepared {today}.
"""


def smoke_test(out: Path, batch: Path, steamid: str, analysis: dict) -> str:
    """Build a tiny report with the packet's own software. Returns the tool's last output line."""
    cands = [f for f in usable(analysis) if f.get("examples")] or usable(analysis)
    f = cands[0]
    mod = {"type": "FindingCard", "finding": f["id"], "caption": "Smoke test."}
    blocks = [{"layout": "module_only", "module": mod}]
    if f.get("examples"):
        blocks.append({"layout": "module_only", "module": {
            "type": "KeyMoments", "finding": f["id"], "title": "Smoke test rounds", "picks": [{"example": 0, "note": "Smoke test."}]}})
    plan = {"agenda": "Smoke test.", "moments": [{
        "id": "smoke", "intent": "WATCH", "title": "Smoke test", "question": "Does it build?", "blocks": blocks,
        "takeaway": "It builds."}]}
    with tempfile.TemporaryDirectory() as td:
        pj, html = Path(td) / "plan.json", Path(td) / "r.html"
        pj.write_text(json.dumps(plan), encoding="utf-8")
        af = Path(td) / "a.json"
        af.write_text(json.dumps(analysis), encoding="utf-8")
        env = dict(os.environ, PYTHONPATH=str(out / "src"))
        r = subprocess.run([sys.executable, "-m", "cs2di.cli", "report", str(batch), "--steamid", steamid, "--plan", str(pj),
                            "--analysis", str(af), "--out", str(html)], capture_output=True, text=True, env=env, cwd=out)
        if r.returncode or not html.exists():
            raise SystemExit("SMOKE TEST FAILED\n" + r.stdout + r.stderr)
        return r.stdout.strip().splitlines()[-1] + f" [{f['id']}]"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True)
    ap.add_argument("--player", required=True)
    ap.add_argument("--steamid", required=True)
    ap.add_argument("--batch-dir", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--example", required=True, type=Path, help="a coach plan written for a DIFFERENT player")
    ap.add_argument("--kind", default="pug")
    ap.add_argument("--expect", type=int, default=30, help="exact number of demo folders required")
    ap.add_argument("--no-batch-copy", action="store_true")
    a = ap.parse_args()

    batch = a.batch_dir
    demos = sorted(p.name for p in batch.iterdir() if p.is_dir())
    if len(demos) != a.expect:
        raise SystemExit(f"{a.id}: {len(demos)} demo folders, expected {a.expect}")
    gate = scan_batch(batch)
    bad = [g for g in gate if not g.passed]
    if bad:
        raise SystemExit(f"{a.id}: integrity gate failed for " + ", ".join(f"{g.demo_id}: {g.reasons}" for g in bad))
    missing = []
    for d in demos:
        with (batch / d / "players.csv").open(encoding="utf-8", newline="") as fh:
            if a.steamid not in {r["steamid"] for r in csv.DictReader(fh)}:
                missing.append(d)
    if missing:
        raise SystemExit(f"{a.id}: {a.player} is not in {len(missing)} demos, e.g. {missing[:2]}")

    out = a.out
    if out.exists():
        shutil.rmtree(out)
    (out / "data").mkdir(parents=True)
    (out / "tools").mkdir()

    digest = build_digest(batch, a.steamid)
    (out / "data/digest.json").write_text(json.dumps(digest, indent=2, default=str), encoding="utf-8")
    analysis = jsonable(analyse_batch(batch, a.steamid))
    (out / "data/findings_all.json").write_text(json.dumps(analysis, indent=1), encoding="utf-8")
    keep = usable(analysis)
    (out / "data/findings_shortlist.json").write_text(
        json.dumps({**{k: v for k, v in analysis.items() if k != "findings"}, "findings": keep}, indent=1), encoding="utf-8")
    (out / "data/findings_index.txt").write_text("\n".join(index_line(f) for f in keep) + "\n", encoding="utf-8")

    (out / "PROMPT.md").write_text(render_prompt(a.player, a.steamid, len(demos)), encoding="utf-8")
    for n in ("RULES.md", "MODULES.md"):
        shutil.copy(REPO / "coach/handoff" / n, out / n)
    shutil.copy(a.example, out / "EXAMPLE_plan_for_a_different_player.json")
    shutil.copytree(REPO / "src", out / "src", ignore=IGNORE)
    shutil.copytree(REPO / "assets", out / "assets", ignore=IGNORE)
    shutil.copy(REPO / "pyproject.toml", out / "pyproject.toml")
    shutil.copy(REPO / "scripts/moment_facts.py", out / "tools/moment_facts.py")
    (out / "README.md").write_text(README.format(player=a.player, pid=a.id, n=len(demos), today=date.today().isoformat()), encoding="utf-8")

    (out / "data/batch_demos.txt").write_text("\n".join(demos) + "\n", encoding="utf-8")
    if not a.no_batch_copy:
        shutil.copytree(batch, out / "data/batch", ignore=IGNORE)

    maps = Counter()
    fam = Counter()
    for d in demos:
        ms = json.loads((batch / d / "match_summary.json").read_text(encoding="utf-8"))
        hd = json.loads((batch / d / "header.json").read_text(encoding="utf-8"))
        maps[str(hd.get("map_name"))] += 1
        fam[str(ms.get("demo_source_family"))] += 1
    sc = digest["scope"]
    manifest = {"packet": a.id, "kind": a.kind, "player": a.player, "steamid": a.steamid, "matches": len(demos),
                "rounds": sc.get("rounds"), "maps": dict(sorted(maps.items())), "source_family": dict(fam),
                "findings": dict(Counter(f["status"] for f in analysis["findings"])), "usable_findings": len(keep),
                "with_replay_examples": sum(bool(f.get("examples")) for f in keep), "demo_folders": demos,
                "example_plan_from": str(a.example.relative_to(REPO)) if a.example.is_relative_to(REPO) else a.example.name,
                "generator": "scripts/build_packet.py", "prepared": date.today().isoformat()}
    (out / "MANIFEST.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    line = smoke_test(out, batch, a.steamid, analysis)
    print(f"OK {a.id}: {len(demos)} matches, {sc.get('rounds')} rounds, {len(keep)} usable findings "
          f"({manifest['findings']}); smoke: {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
