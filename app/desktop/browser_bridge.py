"""Short-lived loopback bridge for the Toolbox browser companion.

Only page metadata and click acknowledgements cross the bridge. Authentication
stays in the browser. Original browser downloads are never moved or deleted.
"""
from __future__ import annotations

import hmac
import json
import re
import secrets
import tempfile
import threading
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from downloads import (Library, analyze, bounded_copy, demo_map, ingest_archive,
                       library_lock, progress, space_limit)
from jobs import STATE, save_json
from sources import AccessError, Resolver, SourceError, parse_html

PROTOCOL = 1
MAX_BODY = 3 * 1024 * 1024
COMPANION = Path(__file__).with_name('userscripts') / 'CS2Toolbox.user.js'


class BrowserCancelled(SourceError):
    pass


class BrowserStopped(AccessError):
    """Stop the batch for login, verification, or a broken companion connection."""


def canonical(url):
    parsed = urlsplit(url)
    host = (parsed.hostname or '').lower().removeprefix('www.')
    if parsed.scheme != 'https' or host not in ('faceit.com', 'hltv.org') or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise SourceError('The companion can navigate only HTTPS FACEIT and HLTV pages.')
    path = parsed.path.rstrip('/') or '/'
    if host == 'faceit.com' and not re.fullmatch(r'/[a-z]{2}/cs2/room/1-[a-fA-F0-9-]{36}', path):
        raise SourceError('The companion needs a FACEIT CS2 match page.')
    if host == 'hltv.org' and not re.fullmatch(r'/(?:results|(?:matches|team|events)/\d+(?:/[^/]+)?)', path):
        raise SourceError('The companion needs an HLTV results, team, event, or match page.')
    return urlunsplit(('https', 'www.' + host, path, urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=True))), ''))


class BrowserBridge:
    def __init__(self, opener=webbrowser.open, timeout=180):
        self.opener, self.timeout = opener, timeout
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.RLock()
        self.ready = threading.Event()
        self.task = self.result = self.error = None
        self.owner, self.heartbeat = '', 0
        self.download_watch = None
        self.retry_capable = False
        self.click_at = None
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass  # Never log the per-run pairing value or page payload.

            def do_POST(self):
                result, code = {}, 200
                try:
                    expected_host = f'127.0.0.1:{self.server.server_port}'
                    if self.headers.get('Host') != expected_host:
                        raise PermissionError('Invalid helper host.')
                    if not hmac.compare_digest(self.headers.get('X-CS2-Token', ''), bridge.token):
                        raise PermissionError('Pairing expired. Start this job from Toolbox again.')
                    length = int(self.headers.get('Content-Length', '0'))
                    if length <= 0 or length > MAX_BODY:
                        raise ValueError('Invalid companion message size.')
                    self.connection.settimeout(10)
                    body = json.loads(self.rfile.read(length))
                    result = bridge.dispatch(self.path, body)
                except PermissionError as exc:
                    code, result = 403, {'error': str(exc)}
                except (ValueError, KeyError, TypeError, OSError) as exc:
                    code, result = 400, {'error': str(exc)}
                data = json.dumps(result).encode()
                self.send_response(code)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(data)

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        self.port = self.server.server_port
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.launched = False

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)

    def dispatch(self, route, body):
        if not isinstance(body, dict) or body.get('version') != PROTOCOL:
            raise SourceError('Companion version mismatch. Install the Toolbox companion from Tools & setup.')
        owner = body.get('owner', '')
        if not isinstance(owner, str) or not re.fullmatch(r'[a-zA-Z0-9-]{16,80}', owner):
            raise SourceError('Invalid companion tab identity.')
        with self.lock:
            now = time.monotonic()
            if self.owner and owner != self.owner and now - self.heartbeat < 20:
                raise SourceError('Another tab owns this job. Close it and wait 20 seconds before resuming here.')
            self.owner, self.heartbeat = owner, now
            self.retry_capable = isinstance(body.get('capabilities'), list) and 'download-retry-v1' in body['capabilities']
            if route == '/state':
                return {'task': self.task}
            if not self.task or body.get('id') != self.task['id']:
                raise SourceError('Stale task. Start this job from Toolbox again.')
            if canonical(body.get('url', '')) != self.task['url']:
                raise SourceError('Wrong page or filters. No file was accepted for this task.')
            if route == '/problem':
                self.error = str(body.get('message', 'Browser action failed.'))[:500]
                self.ready.set()
            elif route == '/snapshot' and self.task['mode'] == 'inspect' and self.task['status'] == 'pending':
                html = body.get('html')
                if not isinstance(html, str) or len(html.encode()) > MAX_BODY - 4096:
                    raise SourceError('Page metadata is too large or missing.')
                self.result = html
                self.task['status'] = 'received'
                self.ready.set()
            elif route == '/claim' and self.task['mode'] == 'download':
                if self.task['status'] != 'pending':
                    raise SourceError('This download was already claimed. No second click is allowed.')
                # A late first response can start while the retry page loads.
                # Recheck before authorizing another click, including anonymous
                # browser partials whose ownership cannot yet be established.
                if self.task.get('attempt', 1) > 1 and self.download_watch and download_activity(**self.download_watch):
                    self.task['status'] = 'download_observed'
                    self.result = {'claimed_at': time.time(), 'download_observed': True}
                    self.ready.set()
                    return {'ok': True, 'click': False}
                self.task['status'] = 'claimed'
                self.result = {'claimed_at': time.time()}
                self.click_at = None if self.retry_capable else time.monotonic()
                self.ready.set()
                return {'ok': True, 'acknowledge_click': self.retry_capable}
            elif route == '/clicked' and self.task['mode'] == 'download' and self.task['status'] == 'claimed':
                if self.click_at is None:
                    self.click_at = time.monotonic()
            else:
                raise SourceError('Unsupported companion action.')
            return {'ok': True}

    def ask(self, mode, url):
        url = canonical(url)
        with self.lock:
            self.ready.clear()
            self.result = self.error = None
            self.click_at = None
            self.task = {'id': uuid.uuid4().hex, 'mode': mode, 'url': url, 'status': 'pending', 'attempt': 1}
        if not self.launched:
            fragment = urlencode({'cs2toolbox': PROTOCOL, 'port': self.port, 'pair': self.token})
            self.opener(url + '#' + fragment)
            self.launched = True
            print('Browser companion: keep the opened tab running. Complete any login or site verification yourself.', flush=True)
        if not self.ready.wait(self.timeout):
            raise BrowserStopped('Browser companion did not respond. Install/enable CS2 Toolbox Browser Companion, disable the old collectors, and start this job again.')
        self.check()
        return self.result

    def check(self):
        if self.error:
            raise BrowserStopped('Browser companion: ' + self.error)

    def watch_download(self, watch, before, identities):
        self.download_watch = dict(watch=watch, before=before, since=time.time(), identities=identities)

    def retry_download(self):
        with self.lock:
            if not self.retry_capable:
                return None
            if self.click_at is None:
                return None
            if not self.task or self.task['mode'] != 'download' or self.task['status'] != 'claimed':
                return None
            if self.task.get('attempt', 1) >= 3:
                return None
            if self.download_watch and download_activity(**self.download_watch):
                return None
            self.ready.clear()
            self.result = self.error = None
            self.click_at = None
            self.task = {**self.task, 'id': uuid.uuid4().hex, 'status': 'pending',
                         'attempt': self.task.get('attempt', 1) + 1, 'reload': True}
        if not self.ready.wait(self.timeout):
            raise BrowserStopped('Download retry did not respond. Check the companion, login or site verification.')
        self.check()
        return self.result

    def html(self, url):
        return parse_html(self.ask('inspect', url))


def resolve_in_browser(value, count):
    with BrowserBridge() as bridge:
        return Resolver(client=bridge).resolve(value, count)


def files_snapshot(folder):
    if not folder.is_dir():
        raise SourceError('Choose the existing folder your browser saves downloads into.')
    snapshot = {}
    for path in folder.iterdir():
        try:
            if path.is_file():
                state = path.stat()
                snapshot[path.name] = (state.st_size, state.st_mtime_ns)
        except FileNotFoundError:
            continue  # Browser renamed a partial between enumeration and stat.
    return snapshot


def ready_downloads(folder, before, since, identities, stable, now=None):
    """Auto-adopt only identity-bearing filenames, never the newest unrelated file."""
    now = time.monotonic() if now is None else now
    found = []
    current = files_snapshot(folder)
    for name, stat in current.items():
        lower = name.lower()
        if lower.endswith(('.crdownload', '.part', '.tmp', '.download')) or stat[0] == 0:
            continue
        if stat == before.get(name) or stat[1] / 1e9 < since - 2:
            continue
        if not any(identity.casefold() in lower for identity in identities):
            continue
        # A visible final filename alone is not sufficient while a sibling partial exists.
        if any(p.casefold().startswith(lower) and p.lower().endswith(('.crdownload', '.part', '.tmp', '.download')) for p in current):
            continue
        if stable.get(name, (None, 0))[0] != stat:
            stable[name] = (stat, now)
            continue
        if now - stable[name][1] >= 3:
            found.append(folder / name)
    return sorted(found)


def request_archives(match, watch, reason, directory=STATE / 'browser-requests', timeout=1800):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    identity = uuid.uuid4().hex
    request = directory / (identity + '.json')
    reply = directory / (identity + '.reply.json')
    save_json(request, {'match': match['id'], 'label': match['label'], 'watch': str(watch), 'reason': reason})
    print('TOOLBOX_FILES ' + identity, flush=True)
    end = time.monotonic() + timeout
    try:
        while time.monotonic() < end:
            if reply.exists():
                paths = json.loads(reply.read_text(encoding='utf-8')).get('files', [])
                if not paths:
                    raise BrowserCancelled('Archive selection cancelled. Existing downloads and analysis are kept.')
                if not isinstance(paths, list) or not all(isinstance(p, str) for p in paths):
                    raise SourceError('Invalid archive selection.')
                return [Path(p) for p in paths]
            time.sleep(.25)
        raise BrowserCancelled('Archive selection timed out. Start the job again; existing downloads are kept.')
    finally:
        request.unlink(missing_ok=True)
        reply.unlink(missing_ok=True)


def archive_identity(match):
    if match['source'] == 'faceit':
        return [match['id'].split(':', 1)[1]]
    # A random token avoids confusing a match ID with a year or a map score in a filename.
    # HLTV archives do not have a guaranteed provider-ID naming contract.
    return []


def download_activity(watch, before, since, identities):
    """Evidence of a start, never proof that a complete archive is usable.

    Unknown browser partials suppress retries conservatively; they are not
    imported or attributed to this match. Unrelated completed files do not count.
    """
    for name, state in files_snapshot(watch).items():
        if state == before.get(name) or state[1] / 1e9 < since - 2:
            continue
        if any(identity.casefold() in name.casefold() for identity in identities):
            return True
        if name.lower().endswith(('.crdownload', '.part', '.tmp', '.download')):
            return True
    return False


def await_archives(bridge, match, watch, before, claimed_at, select=request_archives, timeout=300):
    identities, stable = archive_identity(match), {}
    if not identities:
        return select(match, watch, 'When the browser download finishes, select ALL archives for this match. HLTV filenames do not reliably carry the match ID.')
    end = time.monotonic() + timeout
    click_started = time.monotonic()
    attempts, started = 1, False
    observed_click = None
    while time.monotonic() < end:
        bridge.check()
        ready = ready_downloads(watch, before, claimed_at, identities, stable)
        if ready:
            return ready
        actual_click = getattr(bridge, 'click_at', click_started)
        if actual_click is not None and actual_click != observed_click:
            observed_click = actual_click
            click_started = actual_click
        started = started or download_activity(watch, before, claimed_at, identities)
        if actual_click is not None and not started and time.monotonic() - click_started >= 3 and getattr(bridge, 'retry_capable', False) and hasattr(bridge, 'retry_download'):
            if attempts >= 3:
                return select(match, watch, 'No download activity after three attempts. Check login/download prompts or select the archive manually.')
            print(f'No download activity after 3 seconds; refreshing FACEIT before attempt {attempts + 1}/3.', flush=True)
            retry = bridge.retry_download()
            if retry is None:
                started = True  # A late/ambiguous partial suppresses another click.
            else:
                attempts += 1
                started = bool(retry.get('download_observed'))
                click_started = time.monotonic()
        time.sleep(.5)
    return select(match, watch, 'No completed file with the exact FACEIT match ID was found in the browser folder. Select its downloaded archive(s), or cancel.')


def import_archives(library, match, paths, staging, inspect=demo_map):
    ids = []
    for original in paths:
        original = Path(original)
        if not original.is_file() or original.name.lower().endswith(('.crdownload', '.part', '.tmp', '.download')):
            raise SourceError('Select completed download files, not an in-progress browser download.')
        with tempfile.TemporaryDirectory(prefix='browser-', dir=staging) as temporary:
            folder = Path(temporary)
            archive = folder / original.name
            before = original.stat()
            with original.open('rb') as source:
                bounded_copy(source, archive, space_limit(folder))
            after = original.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise SourceError('The browser file changed during import. Wait for it to finish, then retry.')
            ids.extend(ingest_archive(library, match, archive, folder / 'unpacked', inspect))
    return ids


def run_in_browser(plan, root, watch, with_analysis=False, hz='16', *,
                   bridge_factory=BrowserBridge, select=request_archives, inspect=demo_map):
    root, watch = Path(root).resolve(), Path(watch).resolve()
    files_snapshot(watch)  # validate before launching a tab or creating output
    root.mkdir(parents=True, exist_ok=True)
    failed, selected = list(plan.get('unavailable', [])), []
    analysis_contexts = {}
    with library_lock(root), bridge_factory() as bridge:
        library = Library(root)
        staging = root / '.toolbox-staging'
        staging.mkdir(exist_ok=True)
        for index, match in enumerate(plan['matches']):
            try:
                ids = library.match_files(match)
                if ids:
                    selected.extend(ids)
                    analysis_contexts.update({digest: match for digest in ids})
                    print(f'Already downloaded: {match["id"]} ({len(ids)} demos)', flush=True)
                    continue
                before = files_snapshot(watch)
                if hasattr(bridge, 'watch_download'):
                    bridge.watch_download(watch, before, archive_identity(match))
                print(f'Browser download: {match["id"]} — {match["label"]}', flush=True)
                claim = bridge.ask('download', match['url'])
                paths = await_archives(bridge, match, watch, before, claim['claimed_at'], select)
                ids = import_archives(library, match, paths, staging, inspect)
                manual = not archive_identity(match) or any(not any(identity.casefold() in p.name.casefold() for identity in archive_identity(match)) for p in paths)
                # Every played map must be represented. Do not assume WATCH DEMO returned all maps.
                for _ in range(len(match['maps']) + 1):
                    represented = {library.data['files'][digest]['map'] for digest in ids}
                    missing = {item['map'] for item in match['maps']} - represented
                    if not missing:
                        break
                    extra = select(match, watch, 'Missing played maps: ' + ', '.join(sorted(missing)) + '. Download their demos in the browser and select the remaining archive(s).')
                    ids.extend(import_archives(library, match, extra, staging, inspect))
                    manual = True
                if {item['map'] for item in match['maps']} - {library.data['files'][digest]['map'] for digest in ids}:
                    raise SourceError('Selected archives still do not cover all played maps.')
                selected.extend(ids)
                analysis_contexts.update({digest: match for digest in ids})
                record = library.data['matches'][match['id']]
                record['download_complete'] = True
                record['download_method'] = 'browser'
                record['archive_provenance'] = 'user_selected' if manual else 'match_id_filename'
                library.save()
                print(f'Match ready: {match["id"]} — {len(set(ids))} demos; browser originals kept.', flush=True)
                progress('Browser downloads', index + 1, len(plan['matches']), match['id'])
            except (BrowserCancelled, BrowserStopped):
                raise
            except (OSError, ValueError, RuntimeError, EOFError) as exc:
                print(f'ERROR: {match["id"]}: {exc}', flush=True)
                failed.append({'match': match['id'], 'reason': str(exc)})
        if with_analysis and selected:
            failed.extend({'demo': name, 'reason': 'Analysis failed'} for name in analyze(library, selected, hz, contexts=analysis_contexts))
    print(f'Browser job finished: {len(set(selected))} demos available; {len(failed)} unavailable/failed matches or analyses.', flush=True)
    return 1 if failed else 0
