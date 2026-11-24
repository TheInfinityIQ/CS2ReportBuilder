"""Watchable files are discovered from replays, never from analysis-only records."""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import re

from jobs import STATE, read_json, save_json
from extractor.job_lock import exclusive

DEFAULT_REPLAYS = Path(r'C:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive\game\csgo\replays')
CACHE = STATE/'replay-file-cache.json'
CACHE_VERSION = 2
SHA = re.compile(r'[a-f0-9]{64}')
MAGICS = (b'PBDEMS2\0', b'HL2DEMO\0')


class UnavailableDemo(ValueError):
    pass


def replay_root():
    return DEFAULT_REPLAYS.resolve()


def stamp(path):
    info = path.stat()
    return [info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_ino]


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4*1024*1024), b''): h.update(block)
    return h.hexdigest()


def available(root=None, *, cache=None):
    root = Path(root).resolve() if root is not None else replay_root()
    if not root.is_dir(): return []
    cache_path = Path(cache or CACHE)
    previous = read_json(cache_path, {})
    old = previous.get('files', {}) if isinstance(previous, dict) and previous.get('version') == CACHE_VERSION and previous.get('root') == str(root) else {}
    if not isinstance(old, dict): old = {}
    index = read_json(root/'replay-library.json', {})
    indexed = index.get('files', {}) if isinstance(index, dict) else {}
    hints = {}
    if isinstance(indexed, dict):
        for sha, item in indexed.items():
            if not SHA.fullmatch(str(sha)) or not isinstance(item, dict): continue
            relative = item.get('path')
            if not isinstance(relative, str): continue
            try:path = (root/relative).resolve()
            except (OSError,ValueError):continue
            if path.is_relative_to(root): hints[str(path).casefold()] = {**item, 'sha': sha}
    result = []; remembered = {}
    for base, dirs, names in os.walk(root, followlinks=False):
        directory = Path(base)
        dirs[:] = sorted(d for d in dirs if not d.startswith('.') and not (directory/d).is_symlink()
                         and not (directory/d).is_junction())
        for name in sorted(names):
            path = directory/name
            if name.startswith('.') or path.suffix.casefold() != '.dem' or path.is_symlink(): continue
            try:
                resolved = path.resolve()
                if not resolved.is_relative_to(root): continue
                relative = resolved.relative_to(root).as_posix()
                before = stamp(resolved)
                with resolved.open('rb') as stream:
                    if stream.read(8) not in MAGICS: continue
                hint = hints.get(str(resolved).casefold(), {})
                cached = old.get(relative, {})
                if not isinstance(cached, dict): cached = {}
                if cached.get('stamp') == before and SHA.fullmatch(str(cached.get('sha', ''))):
                    sha = cached['sha']
                elif [hint.get(key) for key in ('bytes', 'mtime_ns', 'ctime_ns', 'inode')] == before:
                    sha = hint['sha']
                else:
                    sha = digest(resolved)
                if stamp(resolved) != before: continue  # A download is still changing.
            except OSError: continue
            remembered[relative] = {'stamp': before, 'sha': sha}
            result.append({'sha': sha, 'path': resolved, 'relative': relative,
                           'file_stamp': before, 'metadata': hint if hint.get('sha') == sha else {}})
    data = {'version': CACHE_VERSION, 'root': str(root), 'files': remembered}
    if data != previous:
        try:
            with exclusive(cache_path.with_suffix('.lock')): save_json(cache_path, data)
        except (OSError, RuntimeError): pass  # A read-only listing remains usable without a cache write.
    return result


def verify(path, expected_sha, *, root=None):
    root = Path(root).resolve() if root is not None else replay_root()
    path = Path(path).resolve()
    if not path.is_relative_to(root) or path.suffix.casefold() != '.dem' or not path.is_file():
        raise UnavailableDemo('This demo is no longer available in replays. Refresh the downloaded-demo library.')
    try:
        before = stamp(path)
        actual = digest(path)
        after = stamp(path)
    except (FileNotFoundError, NotADirectoryError) as exc:
        raise UnavailableDemo('This demo is no longer available in replays. Refresh the downloaded-demo library.') from exc
    if after != before:
        raise UnavailableDemo('This downloaded demo is still changing. Refresh the library after its download finishes.')
    if not SHA.fullmatch(str(expected_sha)) or actual != expected_sha:
        # Prevent a same-size/timestamp replacement from remaining stuck behind
        # an old downloader hint after playback detects its changed content.
        try:
            with exclusive(CACHE.with_suffix('.lock')):
                data=read_json(CACHE,{})
                if not isinstance(data,dict) or data.get('version') != CACHE_VERSION or data.get('root')!=str(root):data={'version':CACHE_VERSION,'root':str(root),'files':{}}
                if not isinstance(data.get('files'),dict):data['files']={}
                data['files'][path.relative_to(root).as_posix()]={'stamp':before,'sha':actual}
                save_json(CACHE,data)
        except (OSError,RuntimeError):pass
        raise UnavailableDemo('This downloaded demo changed. Refresh the library before watching it.')
    return path


def resolve_entry(entry):
    if not entry.get('demo_path'): raise UnavailableDemo('This demo is not downloaded in replays.')
    return verify(entry['demo_path'], entry.get('sha'))
