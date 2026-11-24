"""Replay acquisition worker: staged downloads, series index, optional v8 analysis."""
from __future__ import annotations

import argparse
import gzip
import hashlib
from http.client import HTTPException
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from credentials import get_secret
from jobs import ROOT, STATE, build_extraction, hidden_options, save_json, python_executable
from analysis_layout import destination as analysis_destination
from sources import AccessError, Client, Resolver, SourceError, classify_link, map_name

DEFAULT_REPLAYS = Path(r'C:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive\game\csgo\replays')
ANALYSIS = ROOT / 'data/analysis'
INDEX_NAME = 'replay-library.json'
MONTHS = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')


def progress(phase, completed, total, detail=''):
    percent = round(100 * completed / total, 1) if total else 0
    print('TOOLBOX_PROGRESS ' + json.dumps(dict(phase=phase, percent=percent, detail=detail)), flush=True)


def safe_name(value, limit=70):
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '-', str(value)).strip(' .')
    value = re.sub(r'\s+', ' ', value)[:limit].rstrip(' .') or 'Unknown'
    if re.fullmatch(r'(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?', value):
        value = '_' + value
    return value


def filename(match, item, part=''):
    day = date.fromisoformat(match['date'])
    stamp = f'{MONTHS[day.month - 1]}-{day.day:02d}-{day.year}'
    a, b = item['score']
    separator = '-vs-' if match['source'] == 'faceit' else '-'
    return f'[{int(a)}{separator}{int(b)}]_{safe_name(match["label"], 60)}_{stamp}_{safe_name(item["map"] + part, 30)}_{safe_name(match["event"], 65)}.dem'


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def demo_map(path):
    with Path(path).open('rb') as stream:
        if stream.read(8) != b'PBDEMS2\0':
            raise SourceError('Downloaded content is not a CS2 demo (possibly a login/error page).')
    # Use the parser already shipped with the v8 extractor, for header metadata only.
    deps = str(ROOT / 'app/extractor/.deps')
    if deps not in sys.path:
        sys.path.insert(0, deps)
    try:
        from demoparser2 import DemoParser
        name = map_name(DemoParser(str(path)).parse_header().get('map_name', ''))
    except Exception as exc:
        raise SourceError('Could not read the CS2 demo header. Check extraction tools in Tools & setup.') from exc
    if not name:
        raise SourceError('Demo header has no map name.')
    return name


def bounded_copy(source, destination, limit, report=None):
    total = 0
    with Path(destination).open('xb') as output:
        while True:
            chunk = source.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > limit:
                raise SourceError('Download or unpacked demo exceeds available disk space / the 32 GiB per-file limit.')
            output.write(chunk)
            if report:
                report(total)
    return total


def space_limit(folder):
    return max(0, min(32 * 1024 ** 3, shutil.disk_usage(folder).free - 512 * 1024 ** 2))


def safe_member(name):
    normalized = name.replace('\\', '/')
    if normalized.startswith('/') or ':' in normalized or any(p in ('..', '') for p in normalized.split('/')):
        raise SourceError('Archive contains an unsafe member path.')
    return normalized.lower().endswith('.dem')


def unpack(archive, folder):
    """Never extract archive-controlled paths. Stream only .dem members to our names."""
    folder.mkdir()
    with archive.open('rb') as stream:
        magic = stream.read(8)
    if magic == b'PBDEMS2\0':
        target = folder / '0000.dem'
        archive.rename(target)
        return [(target, archive.name)]
    if magic.startswith(b'\x1f\x8b'):
        target = folder / '0000.dem'
        with gzip.open(archive, 'rb') as source:
            bounded_copy(source, target, space_limit(folder))
        return [(target, archive.name.removesuffix('.gz'))]
    if magic.startswith(b'\x28\xb5\x2f\xfd'):
        # pyarrow already ships with the extractor and supplies streaming Zstandard.
        deps = str(ROOT / 'app/extractor/.deps')
        if deps not in sys.path:
            sys.path.insert(0, deps)
        try:
            import pyarrow
        except ImportError:
            raise SourceError('Zstandard demos need the existing extraction tools. Run Tools & setup, or unpack the file manually and select its .dem.') from None
        target = folder / '0000.dem'
        with pyarrow.input_stream(str(archive), compression='zstd') as source:
            bounded_copy(source, target, space_limit(folder))
        return [(target, archive.name.removesuffix('.zst'))]
    demos = []
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as bundle:
            for entry in bundle.infolist():
                if entry.is_dir():
                    continue
                if not safe_member(entry.filename):
                    continue
                target = folder / f'{len(demos):04d}.dem'
                if entry.file_size > space_limit(folder):
                    raise SourceError('Not enough free disk space to unpack this demo.')
                with bundle.open(entry) as source:
                    bounded_copy(source, target, space_limit(folder))
                demos.append((target, entry.filename))
    elif magic.startswith((b'Rar!', b'7z\xbc\xaf\x27\x1c')):
        seven = shutil.which('7z') or next((str(p) for p in (Path(r'C:\Program Files\7-Zip\7z.exe'), Path(r'C:\Program Files (x86)\7-Zip\7z.exe')) if p.exists()), '')
        tar = shutil.which('tar')
        if not seven and not tar:
            raise SourceError('This archive needs 7-Zip or Windows tar. Install an archive tool, or unpack it manually and use Local analysis.')
        command = [seven, 'l', '-slt', '--', str(archive)] if seven else [tar, '-tf', str(archive)]
        listed = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace', **hidden_options())
        if listed.returncode:
            raise SourceError('The installed archive tool cannot read this archive. Use 7-Zip or unpack it manually.')
        names = re.findall(r'^Path = (.+)$', listed.stdout.split('----------', 1)[-1], re.M) if seven else listed.stdout.splitlines()
        for name in names:
            if not safe_member(name):
                continue
            target = folder / f'{len(demos):04d}.dem'
            command = [seven, 'x', '-so', '-spd', '--', str(archive), name] if seven else [tar, '-xOf', str(archive), '--', name]
            with tempfile.TemporaryFile() as errors:
                worker = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors, **hidden_options())
                try:
                    bounded_copy(worker.stdout, target, space_limit(folder))
                    if worker.wait():
                        raise SourceError('Archive decompression failed. No partial demo will be published.')
                finally:
                    worker.stdout.close()
                    if worker.poll() is None:
                        worker.kill()
                        worker.wait()
            demos.append((target, name))
    else:
        raise SourceError('Source returned an unsupported archive or an HTML error page.')
    if not demos:
        raise SourceError('Archive contains no .dem files.')
    return demos


@contextmanager
def library_lock(root):
    """OS-managed lock releases even if the job is stopped or crashes."""
    with (root / '.toolbox-library.lock').open('a+b') as stream:
        stream.seek(0, 2)
        if stream.tell() == 0:
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise SourceError('Another Toolbox job is writing to this replay library. Wait for it to finish.') from None
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


class Library:
    def __init__(self, root, log=print):
        self.root, self.log = Path(root).resolve(), log
        self.index_path = self.root / INDEX_NAME
        if self.index_path.exists():
            try:
                self.data = json.loads(self.index_path.read_text(encoding='utf-8'))
                if self.data['version'] != 1 or not all(isinstance(self.data[key], dict) for key in ('matches', 'files', 'assets')):
                    raise ValueError()
            except (ValueError, KeyError, TypeError):
                raise SourceError('Replay library index is invalid. Restore its backup before downloading; existing data is preserved.') from None
        else:
            self.data = {'version': 1, 'matches': {}, 'files': {}, 'assets': {}}
        self.existing = [p for p in self.root.rglob('*') if p.suffix.lower() == '.dem' and '.toolbox-staging' not in p.parts and p.is_file()]

    def save(self):
        self.data['updated_at'] = datetime.now(timezone.utc).isoformat()
        if self.index_path.exists():
            shutil.copy2(self.index_path, self.index_path.with_suffix('.json.bak'))
        save_json(self.index_path, self.data)

    def path(self, record):
        path = (self.root / record['path']).resolve()
        if not path.is_relative_to(self.root):
            raise SourceError('Replay index references a path outside the replay library.')
        return path

    def valid(self, digest):
        rec = self.data['files'].get(digest)
        if not rec:
            return False
        path = self.path(rec)
        try:
            stat = path.stat()
        except FileNotFoundError:
            return False
        if not path.is_file() or stat.st_size != rec['bytes']:return False
        if (stat.st_mtime_ns != rec['mtime_ns'] or stat.st_ctime_ns != rec.get('ctime_ns')
                or stat.st_ino != rec.get('inode')):
            if sha256(path) != digest:
                return False
            rec['mtime_ns'] = stat.st_mtime_ns
            rec['ctime_ns'], rec['inode'] = stat.st_ctime_ns, stat.st_ino
        return True

    def asset_files(self, key):
        ids = self.data['assets'].get(key, {}).get('files', [])
        return ids if ids and all(self.valid(digest) for digest in ids) else []

    def match_files(self, match):
        record = self.data['matches'].get(match['id'], {})
        ids = record.get('files', [])
        expected = {item['map'] for item in match['maps']}
        if (record.get('download_complete') and ids and all(self.valid(digest) for digest in ids)
                and expected <= {self.data['files'][digest]['map'] for digest in ids}):
            self.context(match)
            return ids
        return []

    def context(self, match):
        series = self.data['matches'].get(match['id'])
        if series and match['owner'] not in series.setdefault('contexts', []):
            series['contexts'].append(match['owner'])
            self.save()

    def add(self, match, staged, item, original, part=''):
        digest = sha256(staged)
        if self.valid(digest):
            target = self.path(self.data['files'][digest])
            self.log(f'Already downloaded (checksum): {target.name}')
        else:
            size = staged.stat().st_size
            # Existing, unindexed files are compared only if their size matches.
            target = next((p for p in self.existing if p.exists() and p.stat().st_size == size and sha256(p) == digest), None)
            if target:
                self.log(f'Found existing demo: {target.name}')
            else:
                target = self.root / safe_name(item['map']) / safe_name(match['owner'], 60) / filename(match, item, part)
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.resolve().is_relative_to(self.root):
                    raise SourceError('A replay subfolder points outside the selected library.')
                if target.exists():
                    target = target.with_stem(target.stem + '_' + digest[:10])
                # Publish atomically on the same volume, without replacing an existing file.
                # A killed worker can leave staging files, never a half-written final .dem.
                if os.name == 'nt':
                    staged.rename(target)  # Windows rename refuses existing targets.
                else:
                    os.link(staged, target)
                self.existing.append(target)
                self.log(f'Downloaded: {target.relative_to(self.root)}')
            stat = target.stat()
            self.data['files'][digest] = {'path': target.relative_to(self.root).as_posix(), 'sha256': digest,
                                         'bytes': stat.st_size, 'mtime_ns': stat.st_mtime_ns,
                                         'ctime_ns': stat.st_ctime_ns, 'inode': stat.st_ino,
                                         'map': item['map'], 'score': item['score'], 'original_name': original,
                                         'analysis': {}}
        series = self.data['matches'].setdefault(match['id'], {**{k: v for k, v in match.items() if k != 'downloads'}, 'files': [], 'contexts': []})
        if match['owner'] not in series['contexts']:
            series['contexts'].append(match['owner'])
        if digest not in series['files']:
            series['files'].append(digest)
        self.save()
        return digest


def asset_key(match, url):
    parts = urlsplit(url)
    return match['id'] + ':' + parts.netloc + parts.path  # do not persist expiring signatures


def ingest_archive(library, match, archive, folder, inspect=demo_map):
    demos = unpack(archive, folder)
    metadata = []
    for path, name in demos:
        mapped = inspect(path)
        candidates = [item for item in match['maps'] if item['map'] == mapped]
        if len(candidates) != 1:
            raise SourceError(f'Could not unambiguously match demo map {mapped} to the source scores.')
        metadata.append((path, name, candidates[0]))
    ids, counts = [], {}
    for path, name, item in metadata:
        counts[item['map']] = counts.get(item['map'], 0) + 1
        segmented = sum(m[2]['map'] == item['map'] for m in metadata) > 1
        part = f'-part{counts[item["map"]]}' if segmented else ''
        ids.append(library.add(match, path, item, name, part))
    return ids


def download(client, match, resource, target):
    url = resource
    if match['source'] == 'faceit':
        try:
            signed = client.json('https://open.faceit.com/download/v2/demos/download',
                                 token=get_secret('FACEIT_DOWNLOAD_TOKEN'), data={'resource_url': resource})
        except SourceError as exc:
            raise AccessError(f'FACEIT signing is unavailable: {exc}') from None
        url = signed.get('payload', {}).get('download_url', '')
        if not url:
            raise AccessError('FACEIT did not return a signed download URL.')
    try:
        response = client.open(url)
    except SourceError as exc:
        raise AccessError(f'Direct demo transfer is unavailable: {exc}') from None
    with response:
        length = int(response.headers.get('Content-Length') or 0)
        limit = space_limit(target.parent)
        if length > limit:
            raise SourceError('Not enough free space for this download plus a 512 MiB reserve.')
        last = [0.0]
        def report(received):
            if time.monotonic() - last[0] > 1:
                last[0] = time.monotonic()
                if length:
                    progress('Download', received, length, match['id'])
                else:
                    print(f'Downloading {match["id"]}: {received / 1024**2:.1f} MiB (size not supplied)', flush=True)
        received = bounded_copy(response, target, limit, report)
        if length and received != length:
            raise SourceError('Download was interrupted (file size does not match). Retry the job.')


def analyze(library, digests, hz='16', run=subprocess.run, contexts=None, destinations=None):
    """Percentage is completed demos / selected demos, never an invented tick ETA."""
    from extractor.resume_analysis import can_resume_core
    from extractor.job_lock import exclusive, lock_path
    import analysis_references as refs
    failures = []
    discovered = None
    digests = list(dict.fromkeys(digests))
    for index, digest in enumerate(digests):
        record = library.data['files'][digest]
        source = library.path(record)
        context = (contexts or {}).get(digest) or next((m for m in library.data['matches'].values() if digest in m.get('files', [])), None)
        if not context:
            failures.append(source.name)
            print(f'ERROR: No player/team collection metadata for {source.name}; analysis was not started.', flush=True)
            continue
        naming = next((item for item in context.get('maps', []) if item.get('map') == record['map']), None)
        try:stem = Path(filename(context, naming)).stem if naming else source.stem
        except (KeyError, TypeError, ValueError):stem = source.stem
        destination = analysis_destination(ANALYSIS, context, record['map'], stem)
        if digest in (destinations or {}):
            destination = refs.safe(ANALYSIS, destinations[digest])
        requested = destination
        try:
            alias = refs.reference(ANALYSIS, requested)
            if alias or not requested.exists():
                candidates = [p for p in record.get('analysis_outputs', {})]
                if record.get('analysis', {}).get('output'):candidates.append(record['analysis']['output'])
                if alias:
                    destination = refs.resolve(ANALYSIS, requested, digest)
                    candidates.insert(0, destination)
                if discovered is None:
                    discovered = [p.parent for p in Path(ANALYSIS).rglob('viewer_tracks_meta.json')]
                canonical = refs.find(ANALYSIS, digest, hz, [*candidates, *discovered], discover=False,
                                      schema=alias.get('analysis_schema') if alias else None)
                if canonical:
                    if canonical != requested:
                        with exclusive(STATE/'analysis-maintenance.lock'):
                            with exclusive(lock_path(canonical)), exclusive(lock_path(requested)):
                                refs.write(ANALYSIS, requested, canonical, digest, context, record['map'], hz)
                    result = {'status': 'completed', 'output': str(requested), 'canonical_output': str(canonical),
                              'reference': canonical != requested, 'hz': str(hz), 'sha256': digest}
                    record['analysis'] = result
                    record.setdefault('analysis_outputs', {})[str(requested)] = result
                    library.save()
                    print(f'Existing analysis reused: {requested} -> {canonical}', flush=True)
                    progress('Analysis', index + 1, len(digests), 'Verified shared analysis reference')
                    continue
        except (OSError, ValueError, RuntimeError) as exc:
            failures.append(source.name);print(f'ERROR: Analysis reference preserved: {exc}', flush=True)
            continue
        if destination.is_dir():
            try:
                owner = json.loads((destination / 'analysis_source.json').read_text(encoding='utf-8'))
            except (OSError, ValueError):
                owner = {}
            if owner.get('sha256') and owner['sha256'] != digest:
                destination = destination.with_name(destination.name + '_' + digest[:10])
        output = destination.parent
        receipt = destination / 'analysis_run.json'
        legacy = record.get('analysis', {})
        if legacy.get('output'):
            record.setdefault('analysis_outputs', {}).setdefault(legacy['output'], legacy)
        prior = record.setdefault('analysis_outputs', {}).get(str(destination), {})
        def ready():
            try:
                status = json.loads(receipt.read_text(encoding='utf-8'))
                meta = json.loads((destination / 'match_summary.json').read_text(encoding='utf-8'))
                viewer = json.loads((destination / 'viewer_tracks_meta.json').read_text(encoding='utf-8'))
                return (status.get('demo_count') == 1 and status.get('success_count') == 1 and meta.get('valid') is True
                        and viewer.get('demo_sha256') == digest
                        and len(status.get('results', [])) == 1 and status['results'][0].get('demo') == source.name
                        and not any(status.get(key, 0) for key in ('failure_count', 'invalid_count', 'viewer_failure_count')))
            except (OSError, ValueError, KeyError, TypeError, AttributeError):
                return False
        def record_source():
            save_json(destination / 'analysis_source.json', {'sha256': digest, 'demo': source.name,
                      'source_path': str(source), 'context': {k: context.get(k) for k in refs.CONTEXT_KEYS},
                      'map': record['map']})
        if not library.valid(digest):
            failures.append(source.name)
            print(f'ERROR: Source demo changed or is missing: {source.name}', flush=True)
        elif prior.get('hz') == str(hz) and ready():
            record['analysis'] = {'status': 'completed', 'output': str(destination), 'hz': str(hz), 'sha256': digest}
            record['analysis_outputs'][str(destination)] = record['analysis']
            if not (destination/'analysis_source.json').exists():
                record_source()
            library.save()
            print(f'Analysis already completed: {source.name}', flush=True)
        elif destination.exists() and not can_resume_core(destination, digest, entity_hz=hz):
            failures.append(source.name)
            print(f'ERROR: Existing analysis requires review; preserved: {destination}', flush=True)
        else:
            progress('Analysis', index, len(digests), f'{index}/{len(digests)} demos complete; analyzing {source.name}')
            print(f'Analyzing demo {index + 1}/{len(digests)}: {source.name}', flush=True)
            record['analysis'] = {'status': 'running', 'output': str(destination), 'hz': str(hz), 'sha256': digest}
            record['analysis_outputs'][str(destination)] = record['analysis']
            library.save()
            try:
                command = ([python_executable(), '-u', str(ROOT/'app/extractor/resume_analysis.py'),
                            '--demo', str(source), '--analysis', str(destination)] if destination.exists()
                           else build_extraction(source=str(source), output=str(output), hz=hz,
                                                 analysis_name=destination.name, organized=False))
                result = run(command,
                             stdout=sys.stdout, stderr=subprocess.STDOUT, **hidden_options())
                # The extractor writes integrity/viewer outcomes; do not trust process exit alone.
                ok = result.returncode == 0 and ready()
                if result.returncode == 0 and destination.is_dir() and ready():
                    record_source()
            except (OSError, ValueError) as exc:
                print(f'ERROR: Analysis could not finish: {type(exc).__name__}', flush=True)
                ok = False
            record['analysis']['status'] = 'completed' if ok else 'failed'
            if not ok:
                failures.append(source.name)
            library.save()
        progress('Analysis', index + 1, len(digests), f'{index + 1}/{len(digests)} demos processed; {len(failures)} failed')
    return failures


def run_plan(plan, root, with_analysis=False, hz='16', client=None, inspect=demo_map):
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    client = client or Client()
    failed, selected = list(plan.get('unavailable', [])), []
    analysis_contexts = {}
    with library_lock(root):
        library = Library(root)
        staging = root / '.toolbox-staging'
        staging.mkdir(exist_ok=True)
        for match in plan['matches']:
            try:
                known_match = library.match_files(match)
                if known_match:
                    selected.extend(known_match)
                    analysis_contexts.update({digest: match for digest in known_match})
                    print(f'Already downloaded: {match["id"]} ({len(known_match)} demos)', flush=True)
                    continue
                if not match['downloads']:
                    raise AccessError('This match requires browser download; FACEIT supplied no direct demo resources.')
                match_files = []
                for resource in match['downloads']:
                    key = asset_key(match, resource)
                    known = library.asset_files(key)
                    if known:
                        print(f'Already downloaded: {match["id"]} ({len(known)} demos)', flush=True)
                        match_files.extend(known)
                        selected.extend(known)
                        analysis_contexts.update({digest: match for digest in known})
                        for digest in known:
                            series = library.data['matches'].get(match['id'], {})
                            contexts = series.setdefault('contexts', [])
                            if match['owner'] not in contexts:
                                contexts.append(match['owner'])
                        library.save()
                        continue
                    with tempfile.TemporaryDirectory(prefix='job-', dir=staging) as temporary:
                        folder = Path(temporary)
                        archive = folder / 'download.part'
                        print(f'Downloading {match["id"]}…', flush=True)
                        download(client, match, resource, archive)
                        ids = ingest_archive(library, match, archive, folder / 'unpacked', inspect)
                        library.data['assets'][key] = {'files': ids}
                        library.save()
                        match_files.extend(ids)
                        selected.extend(ids)
                        analysis_contexts.update({digest: match for digest in ids})
                actual = {library.data['files'][digest]['map'] for digest in match_files}
                missing = {item['map'] for item in match['maps']} - actual
                if missing:
                    raise SourceError('Source archive is missing played maps: ' + ', '.join(sorted(missing)))
                library.data['matches'][match['id']]['download_complete'] = True
                library.save()
                print(f'Match ready: {match["id"]} — {len(match_files)} demos; series links saved.', flush=True)
            except AccessError:
                raise
            except (OSError, ValueError, RuntimeError, EOFError, HTTPException, zipfile.BadZipFile) as exc:
                print(f'ERROR: {match["id"]}: {exc}', flush=True)
                failed.append({'url': match['url'], 'reason': str(exc)})
        if with_analysis and selected:
            failed.extend({'reason': 'Analysis failed', 'demo': name} for name in analyze(library, selected, hz, contexts=analysis_contexts))
        print(f'Finished: {len(set(selected))} demos available; {len(failed)} unavailable/failed matches or analyses.', flush=True)
        for issue in failed:
            print('ERROR: ' + json.dumps(issue, ensure_ascii=False), flush=True)
        return 1 if failed else 0


def acquire_plan(plan, root, with_analysis=False, hz='16', *, method='auto', watch=None):
    """Shared Downloads routing, including the normal browser fallback."""
    if method not in ('auto', 'browser', 'direct'):raise SourceError('Unknown demo download method.')
    use_browser = (method == 'browser' or (method == 'auto' and (
        plan.get('resolved_with') == 'browser' or (any(m['source'] == 'faceit' for m in plan['matches'])
        and not get_secret('FACEIT_DOWNLOAD_TOKEN')))))
    if not use_browser:
        try:
            return run_plan(plan, root, with_analysis, hz)
        except AccessError:
            if method != 'auto':
                raise
            print('Downloads API/direct source access is unavailable. Switching to the browser companion.', flush=True)
    from browser_bridge import run_in_browser
    return run_in_browser(plan, root, watch or Path.home() / 'Downloads', with_analysis, hz)


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--resolve')
    mode.add_argument('--run', type=Path)
    mode.add_argument('--scan-team')
    parser.add_argument('--count', type=int, default=10)
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--replays', type=Path, default=DEFAULT_REPLAYS)
    parser.add_argument('--analyze', action='store_true')
    parser.add_argument('--hz', choices=['1', '2', '4', '8', '16', '32', '64'], default='16')
    parser.add_argument('--method', choices=['auto', 'browser', 'direct'], default='auto')
    parser.add_argument('--watch', type=Path, default=Path.home() / 'Downloads')
    parser.add_argument('--catalog', type=Path)
    parser.add_argument('--season')
    args = parser.parse_args()
    try:
        if args.scan_team:
            if not args.catalog:
                parser.error('--scan-team requires --catalog')
            from faceit_leagues import TeamLeagues
            catalog = TeamLeagues().scan(args.scan_team)
            save_json(args.catalog, catalog)
            print(f"Team scan ready: {catalog['team_name']} · {len(catalog['seasons'])} seasons. No demos downloaded.")
            return 0
        if args.resolve:
            if not args.plan:
                parser.error('--resolve requires --plan')
            link = classify_link(args.resolve)
            browser_review = args.method == 'browser' and link['source'] == 'hltv'
            if link['source'] == 'faceit' and link['kind'] == 'team':
                if not args.catalog or not args.season:
                    raise SourceError('Scan this team’s seasons and select one before reviewing downloads.')
                from faceit_leagues import TeamLeagues
                catalog = json.loads(args.catalog.read_text(encoding='utf-8'))
                plan = TeamLeagues().resolve_season(args.resolve, catalog, args.season)
            elif not browser_review:
                try:
                    plan = Resolver().resolve(args.resolve, args.count)
                except AccessError:
                    if args.method != 'auto' or link['source'] != 'hltv':
                        raise
                    print('Direct HLTV access is unavailable. Opening the browser companion for metadata review.', flush=True)
                    browser_review = True
            if browser_review:
                from browser_bridge import resolve_in_browser
                plan = resolve_in_browser(args.resolve, args.count)
            plan['resolved_with'] = 'browser' if browser_review else 'direct'
            save_json(args.plan, plan)
            print(f'Review ready: {len(plan["matches"])} matches resolved, {len(plan["unavailable"])} unavailable. No demos downloaded.')
            return 0
        plan = json.loads(args.run.read_text(encoding='utf-8'))
        if not plan.get('matches'):
            raise SourceError('This download plan has no available matches. Review the link again.')
        return acquire_plan(plan, args.replays, args.analyze, args.hz, method=args.method, watch=args.watch)
    except (OSError, ValueError, KeyError) as exc:
        print(f'ERROR: {exc}', flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
