"""Exclusive local extraction and snapshot ownership, using only the stdlib."""

from contextlib import contextmanager
import ctypes
import hashlib
import json
import os
import socket
from pathlib import Path


def alive(pid):
    if os.name == "nt":
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return ctypes.get_last_error() != 87
        code = ctypes.c_ulong()
        try:
            return not kernel.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def lock_path(folder: Path) -> Path:
    folder = folder.resolve()
    key = hashlib.sha256(os.path.normcase(str(folder)).encode()).hexdigest()[:24]
    return folder.parent / ".cs2di_locks" / (key + ".lock")


@contextmanager
def exclusive(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    owner = json.dumps({"pid": os.getpid(), "host": socket.gethostname()}).encode()
    for attempt in range(2):
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            try:
                previous = path.read_bytes()
                state = json.loads(previous)
                if (
                    attempt == 0
                    and state.get("host") == socket.gethostname()
                    and not alive(int(state["pid"]))
                ):
                    if path.read_bytes() == previous:
                        path.unlink()
                        continue
            except (OSError, ValueError, KeyError, TypeError):
                pass
            raise RuntimeError(f"Output is owned by another job, or its lock needs review: {path}") from None
    with os.fdopen(fd, "wb") as stream:
        stream.write(owner)
    try:
        yield
    finally:
        if path.exists() and path.read_bytes() == owner:
            path.unlink()
