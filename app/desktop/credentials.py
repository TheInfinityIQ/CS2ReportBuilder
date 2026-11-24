"""User-scoped Windows Credential Manager storage; never write secrets to files."""
from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

TARGETS = {'FACEIT_API_KEY': 'CS2Toolbox/FACEIT/DataAPI',
           'FACEIT_DOWNLOAD_TOKEN': 'CS2Toolbox/FACEIT/DownloadsAPI'}


class Credential(ctypes.Structure):
    _fields_ = [('Flags', wintypes.DWORD), ('Type', wintypes.DWORD), ('TargetName', wintypes.LPWSTR),
                ('Comment', wintypes.LPWSTR), ('LastWritten', wintypes.FILETIME),
                ('CredentialBlobSize', wintypes.DWORD), ('CredentialBlob', ctypes.POINTER(ctypes.c_ubyte)),
                ('Persist', wintypes.DWORD), ('AttributeCount', wintypes.DWORD), ('Attributes', ctypes.c_void_p),
                ('TargetAlias', wintypes.LPWSTR), ('UserName', wintypes.LPWSTR)]


def api():
    if os.name != 'nt':
        raise OSError('Credential Manager is available on Windows. Use environment variables on other systems.')
    dll = ctypes.WinDLL('Advapi32.dll', use_last_error=True)
    dll.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.POINTER(Credential))]
    dll.CredReadW.restype = wintypes.BOOL
    dll.CredWriteW.argtypes = [ctypes.POINTER(Credential), wintypes.DWORD]
    dll.CredWriteW.restype = wintypes.BOOL
    dll.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
    dll.CredDeleteW.restype = wintypes.BOOL
    dll.CredFree.argtypes = [ctypes.c_void_p]
    dll.CredFree.restype = None
    return dll


def read_secret(name):
    if os.name != 'nt':
        return ''
    dll = api()
    pointer = ctypes.POINTER(Credential)()
    if not dll.CredReadW(TARGETS[name], 1, 0, ctypes.byref(pointer)):
        code = ctypes.get_last_error()
        if code == 1168:  # ERROR_NOT_FOUND
            return ''
        raise ctypes.WinError(code)
    try:
        value = pointer.contents
        return ctypes.string_at(value.CredentialBlob, value.CredentialBlobSize).decode('utf-16-le')
    finally:
        dll.CredFree(pointer)


def write_secret(name, secret):
    secret = secret.strip()
    if not secret:
        raise ValueError('Enter a credential first. Blank fields leave saved credentials unchanged.')
    data = secret.encode('utf-16-le')
    if len(data) > 2560:
        raise ValueError('The credential exceeds the Windows storage limit.')
    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    credential = Credential(Type=1, TargetName=TARGETS[name], Comment='CS2 Toolbox FACEIT access',
                            CredentialBlobSize=len(data), CredentialBlob=buffer, Persist=2,
                            UserName='FaceItAPI')
    if not api().CredWriteW(ctypes.byref(credential), 0):
        raise ctypes.WinError(ctypes.get_last_error())


def delete_secret(name):
    if not api().CredDeleteW(TARGETS[name], 1, 0) and ctypes.get_last_error() != 1168:
        raise ctypes.WinError(ctypes.get_last_error())


def get_secret(name):
    return os.environ.get(name, '').strip() or read_secret(name)
