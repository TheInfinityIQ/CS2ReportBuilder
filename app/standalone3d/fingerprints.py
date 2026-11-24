"""Reuse SHA-256 only while the same file's OS change stamp is unchanged."""
from pathlib import Path
import ctypes
import os

if __package__:
    from .backend import CACHE, digest, read, save
else:
    from backend import CACHE, digest, read, save


def stamp(path):
    stat = path.stat()
    result = [stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns]
    if os.name == 'nt':
        # NTFS ChangeTime catches in-place writes even if LastWriteTime is restored.
        # If it cannot be obtained, do not enable the quick fingerprint path.
        from ctypes import wintypes
        class BasicInfo(ctypes.Structure):
            _fields_ = [(name, ctypes.c_longlong) for name in ('creation','access','write','change')]+[('attributes',wintypes.DWORD)]
        api = ctypes.WinDLL('kernel32', use_last_error=True)
        api.CreateFileW.argtypes = [wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
        api.CreateFileW.restype = wintypes.HANDLE
        api.GetFileInformationByHandleEx.argtypes = [wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD]
        api.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = api.CreateFileW(str(path),0,7,None,3,0,None)
        if handle == ctypes.c_void_p(-1).value: return None
        try:
            info = BasicInfo()
            if not api.GetFileInformationByHandleEx(handle,0,ctypes.byref(info),ctypes.sizeof(info)): return None
            result += [info.creation, info.write, info.change]
        finally: api.CloseHandle(handle)
    return result


def fingerprint(path):
    path = Path(path).resolve(); key = str(path)
    cache = CACHE/'file-fingerprints.json'
    before = stamp(path); entries = read(cache,{})
    previous = entries.get(key,{})
    if before is not None and previous.get('stamp') == before and len(previous.get('sha256','')) == 64:
        return previous['sha256']
    value = digest(path)
    after = stamp(path)
    if before is not None and before == after:
        entries[key] = {'stamp':after, 'sha256':value}
        save(cache,entries)
    elif before != after:
        raise ValueError('The demo or installed asset changed while being checked. Retry after the file has finished updating.')
    return value
