"""Start/reuse the local viewer without opening terminal windows."""
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request

from jobs import ROOT, STATE, hidden_options, python_executable


def is_viewer(url):
    try:
        with urllib.request.urlopen(url, timeout=.5) as response:
            page = response.read(4096).decode('utf-8', errors='replace')
        return '<title>CS2 · Round viewer</title>' in page
    except (OSError, urllib.error.URLError):
        return False


class ViewerService:
    def __init__(self, events):
        self.events = events
        self.process = None
        self.url = None
        self.opening = False
        self.closed = threading.Event()

    def open(self):
        if self.opening:
            return
        self.opening = True
        threading.Thread(target=self._open, daemon=True).start()

    def _open(self):
        try:
            if self.url and is_viewer(self.url):
                self.events.put(('viewer_ready', self.url))
                return
            for port in [8766, 8765, *range(8770, 8781)]:
                if self.closed.is_set():
                    return
                url = f'http://127.0.0.1:{port}/modules/viewer2d/'
                if is_viewer(url):
                    self.url = url
                    self.events.put(('viewer_ready', url))
                    return
                with socket.socket() as probe:
                    try:
                        probe.bind(('127.0.0.1', port))
                    except OSError:
                        continue
                logs = STATE / 'logs'
                logs.mkdir(parents=True, exist_ok=True)
                with (logs / 'viewer-server.log').open('a', encoding='utf-8') as log:
                    self.process = subprocess.Popen([python_executable(), '-u', str(ROOT / 'app/modules/viewer2d/server.py'), '--port', str(port)],
                                                    cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, **hidden_options())
                for _ in range(40):
                    if self.closed.wait(.1):
                        return
                    if self.process.poll() is not None:
                        raise RuntimeError('The viewer could not start. Check viewer-server.log in Activity logs.')
                    if is_viewer(url):
                        self.url = url
                        self.events.put(('viewer_ready', url))
                        return
                raise RuntimeError('The viewer did not become ready in time.')
            raise RuntimeError('No local viewer port is available.')
        except Exception as exc:
            self.events.put(('error', str(exc)))
        finally:
            self.opening = False
            if self.closed.is_set():
                self.stop()

    def stop(self):
        self.closed.set()
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
