"""Validated utility commands and background jobs for the desktop app."""
from __future__ import annotations

import json
import ctypes
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / 'data' / '.desktop'


def python_executable():
    executable = Path(sys.executable)
    return str(executable.with_name('python.exe')) if executable.name.lower() == 'pythonw.exe' else str(executable)


def hidden_options():
    return {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {'start_new_session': True}


class WindowsProcessGroup:
    """A job object owns the worker and its descendants, including .NET helpers."""
    def __init__(self, process):
        self.handle = None
        if os.name != 'nt':
            return
        class Basic(ctypes.Structure):
            _fields_ = [('process_time', ctypes.c_int64), ('job_time', ctypes.c_int64), ('flags', ctypes.c_uint32),
                        ('min_ws', ctypes.c_size_t), ('max_ws', ctypes.c_size_t), ('active', ctypes.c_uint32),
                        ('affinity', ctypes.c_size_t), ('priority', ctypes.c_uint32), ('scheduling', ctypes.c_uint32)]
        class IO(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in ('read_ops', 'write_ops', 'other_ops', 'read_bytes', 'write_bytes', 'other_bytes')]
        class Limits(ctypes.Structure):
            _fields_ = [('basic', Basic), ('io', IO), ('process_memory', ctypes.c_size_t), ('job_memory', ctypes.c_size_t),
                        ('peak_process', ctypes.c_size_t), ('peak_job', ctypes.c_size_t)]
        self.api = ctypes.WinDLL('kernel32', use_last_error=True)
        self.api.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
        self.api.CreateJobObjectW.restype = ctypes.c_void_p
        self.api.SetInformationJobObject.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
        self.api.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self.api.TerminateJobObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        self.api.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = self.api.CreateJobObjectW(None, None)
        limits = Limits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if handle and self.api.SetInformationJobObject(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)) and self.api.AssignProcessToJobObject(handle, int(process._handle)):
            self.handle = handle
        elif handle:
            self.api.CloseHandle(handle)

    def terminate(self):
        return bool(self.handle and self.api.TerminateJobObject(self.handle, 1))

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None


def read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    stage = path.with_suffix('.tmp')
    stage.write_text(json.dumps(value, indent=2), encoding='utf-8')
    stage.replace(path)


def build_extraction(*, source, output, folder=False, entities=False, analysis='', round_number='', hz='16', replace=False):
    if not source.strip():
        raise ValueError('Choose a demo file or demo folder.')
    if not output.strip():
        raise ValueError('Choose an output folder.')
    source, output = Path(source.strip()), Path(output.strip())
    if not str(source) or not source.exists():
        raise ValueError('Choose an existing demo file or demo folder.')
    if folder:
        if not source.is_dir() or not next(source.rglob('*.dem'), None):
            raise ValueError('Choose a folder containing .dem files.')
    elif not source.is_file() or source.suffix.lower() != '.dem':
        raise ValueError('Choose a .dem replay file.')
    if not str(output) or output == Path('.'):
        raise ValueError('Choose an output folder.')
    if output.exists() and not output.is_dir():
        raise ValueError('The output must be a folder, not a file.')
    if str(hz) not in ('1', '2', '4', '8', '16', '32', '64'):
        raise ValueError('Choose a valid sampling rate.')
    cmd = [python_executable(), '-u', str(ROOT / 'app/extractor/extract_demos_v8.py'),
           '--demos' if folder else '--demo', str(source.resolve()), '--output', str(output.resolve()), '--entity-hz', str(hz)]
    if entities:
        cmd.append('--entities-only')
        if analysis.strip():
            path = Path(analysis)
            if not (path / 'rounds.csv').is_file():
                raise ValueError('The analysis folder must contain rounds.csv.')
            if folder:
                raise ValueError('Choose one demo when using an existing analysis.')
            cmd += ['--analysis', str(path.resolve())]
        if round_number.strip():
            if not analysis.strip() or not round_number.isdigit() or int(round_number) < 1:
                raise ValueError('Choose an existing analysis and a positive round number, or leave Round empty.')
            cmd += ['--round', round_number]
    if replace:
        cmd.append('--replace')
    return cmd


def build_viewer_export(analysis, round_number):
    folder = Path(analysis).resolve()
    if not (folder / 'rounds.csv').is_file() or not (folder / 'viewer_tracks.csv.gz').is_file():
        raise ValueError('Choose an analysis folder containing rounds.csv and viewer_tracks.csv.gz.')
    root = (ROOT / 'data/analysis').resolve()
    if not folder.is_relative_to(root):
        raise ValueError('Choose an analysis folder inside this project’s data/analysis folder.')
    if not str(round_number).isdigit() or int(round_number) < 1:
        raise ValueError('Choose a round number.')
    return [python_executable(), '-u', str(ROOT / 'app/modules/viewer2d/replay.py'),
            '--source', folder.relative_to(root).as_posix(), '--round', str(round_number)]


class JobRunner:
    def __init__(self, events=None, state_dir=STATE):
        self.events = events if events is not None else queue.Queue()
        self.state_dir = Path(state_dir)
        self.process = None
        self.process_group = None
        self.busy = False
        self.cancelled = threading.Event()
        self.process_ready = threading.Event()
        self._lock = threading.Lock()

    def start(self, title, command, output='', callback=None):
        with self._lock:
            if self.busy:
                raise RuntimeError('Wait for the current task to finish or stop it first.')
            self.busy = True
            self.cancelled.clear()
            self.process_ready.clear()
        thread = threading.Thread(target=self._run, args=(title, command, output, callback), daemon=True)
        thread.start()

    def _run(self, title, command, output, callback):
        start = time.monotonic()
        now = datetime.now().astimezone()
        log_dir = self.state_dir / 'logs'
        record = {'title': title, 'started': now.isoformat(timespec='seconds'), 'status': 'Failed',
                  'output': output, 'seconds': 0, 'log': ''}
        error = None
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            path = log_dir / (now.strftime('%Y%m%d-%H%M%S-%f') + '.log')
            record['log'] = str(path)
            with path.open('w', encoding='utf-8') as log:
                log.write(title + '\n' + now.isoformat() + '\n\n')
                env = {**os.environ, 'PYTHONIOENCODING': 'utf-8', 'PYTHONUNBUFFERED': '1',
                       'DOTNET_CLI_TELEMETRY_OPTOUT': '1', 'CS2_TOOLBOX_BACKGROUND': '1'}
                self.process = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                                text=True, encoding='utf-8', errors='replace', env=env, **hidden_options())
                self.process_group = WindowsProcessGroup(self.process)
                self.process_ready.set()
                self.events.put(('started', title))
                for line in self.process.stdout:
                    log.write(line)
                    log.flush()
                    self.events.put(('line', line))
                code = self.process.wait()
                self.process.stdout.close()
                record['returncode'] = code
                record['status'] = 'Stopped' if self.cancelled.is_set() else 'Completed' if code == 0 else 'Failed'
        except Exception as exc:
            error = str(exc)
            self.events.put(('line', '\n' + error + '\n'))
        finally:
            if self.process_group:
                self.process_group.close()
                self.process_group = None
            record['seconds'] = round(time.monotonic() - start, 1)
            if self.cancelled.is_set():
                record['status'] = 'Stopped'
            if error:
                record['error'] = error
            try:
                history_file = self.state_dir / 'history.json'
                history = read_json(history_file, [])
                save_json(history_file, ([record] + history)[:100])
            except OSError as exc:
                self.events.put(('line', f'Could not save history: {exc}\n'))
            self.process = None
            self.busy = False
            self.process_ready.set()
            self.events.put(('finished', (record, callback)))

    def stop(self):
        if not self.busy:
            return
        self.cancelled.set()
        threading.Thread(target=self._stop, daemon=True).start()

    def _stop(self):
        self.process_ready.wait(5)
        process = self.process
        if process is None or process.poll() is not None:
            return
        if os.name == 'nt':
            if not self.process_group or not self.process_group.terminate():
                try:
                    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                                   capture_output=True, timeout=8, **hidden_options())
                except (OSError, subprocess.TimeoutExpired):
                    pass
                if process.poll() is None:
                    process.kill()
        else:
            import signal
            os.killpg(process.pid, signal.SIGTERM)


def dependency_status():
    deps = ROOT / 'app/extractor/.deps'
    code = ('import sys,importlib.util,json;sys.path.insert(0,sys.argv[1]);'
            "print(json.dumps({m:bool(importlib.util.find_spec(m)) for m in ['demoparser2','pandas','numpy','pyarrow','polars']}))")
    result = subprocess.run([python_executable(), '-c', code, str(deps)], capture_output=True,
                            text=True, timeout=20, **hidden_options())
    modules = json.loads(result.stdout) if result.returncode == 0 else {}
    dotnet = shutil.which('dotnet')
    sdk = ''
    if dotnet:
        result = subprocess.run([dotnet, '--list-sdks'], capture_output=True, text=True, timeout=20, **hidden_options())
        sdk = next((line.split()[0] for line in result.stdout.splitlines() if line.startswith('9.')), '')
    return {'ready': len(modules) == 5 and all(modules.values()) and bool(sdk), 'modules': modules, 'sdk': sdk}
