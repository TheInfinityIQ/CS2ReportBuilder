"""Preview, journal, and reverse analysis-directory repairs without extraction."""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import os
import re
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlencode

from jobs import ROOT, STATE, read_json, save_json
from analysis_layout import analysis_name, collection, component, validate_root
from extractor.job_lock import exclusive
from extractor.game_catalog import team_hints
from sources import Resolver, SourceError

ANALYSIS = ROOT / 'data/analysis'
CONTROL_FILES = {'manifest.json', 'batch_run_summary.json', 'batch_validation_summary.json', '00_INDEX.md'}
PATH_KEYS = {'source', 'analysis', 'analysis_folder', 'output', 'output_path', 'collection', 'folder',
             'path', 'source_folder', 'output_dir', 'analysis_dir', 'stem'}
MAX_JSON = 64 * 1024 ** 2


def digest_bytes(data):
    return hashlib.sha256(data).hexdigest()


def reparse(path):
    return path.is_symlink() or bool(getattr(path.lstat(), 'st_file_attributes', 0) & 0x400)


def safe_path(path, root):
    path, root = Path(path).absolute(), Path(root).resolve()
    if not path.resolve().is_relative_to(root) or path.resolve() == root:
        raise SourceError(f'Path is outside the repair boundary: {path}')
    current = path
    while current != root:
        if current.exists() and reparse(current):
            raise SourceError(f'Linked/reparse paths are not moved: {current}')
        current = current.parent
    return path


def walk(root):
    for base, dirs, files in os.walk(root, followlinks=False):
        base = Path(base)
        for name in list(dirs):
            if reparse(base / name):
                raise SourceError(f'Linked directory requires manual review: {base / name}')
        dirs.sort()
        yield base, dirs, files


def inventory(folder):
    checksum, count, size = hashlib.sha256(), 0, 0
    for base, dirs, files in walk(folder):
        for name in sorted(dirs):
            checksum.update(('D:' + (base / name).relative_to(folder).as_posix() + '\n').encode())
        for name in sorted(files):
            path = base / name
            if reparse(path):
                raise SourceError('Linked files require manual review.')
            stat = path.stat()
            count += 1
            size += stat.st_size
            checksum.update(json.dumps([path.relative_to(folder).as_posix(), stat.st_size, stat.st_mtime_ns], separators=(',', ':')).encode())
    return {'signature': checksum.hexdigest(), 'files': count, 'bytes': size}


def load_json(path):
    if path.stat().st_size > MAX_JSON:
        raise SourceError(f'JSON exceeds the repair safety limit: {path}')
    return json.loads(path.read_text(encoding='utf-8-sig'))


def normalized(value):
    return value.replace('\\', '/').rstrip('/')


class PathRemapper:
    """Compile once; each string checks only its own directory prefixes."""
    def __init__(self, mappings, root):
        self.prefixes = {}
        for item in sorted(mappings, key=lambda m: len(m['old']), reverse=True):
            old, new = Path(item['old']), Path(item['new'])
            variants = [(normalized(str(old)), normalized(str(new)), False)]
            if old.is_relative_to(root) and new.is_relative_to(root):
                before, after = old.relative_to(root).as_posix(), new.relative_to(root).as_posix()
                variants.append((before, after, '/' not in before))
            for before, after, restricted in variants:
                self.prefixes.setdefault(before.casefold(), (after, not item.get('exact'), restricted))
        # Replay exports repeat many labels. Bound retained strings independently of data size.
        self.cached_text = lru_cache(maxsize=8192)(self._text)

    def _text(self, value, path_key):
        text = normalized(value)
        end = len(text)
        while end >= 0:
            found = self.prefixes.get(text[:end].casefold())
            if found:
                after, descendants, restricted = found
                if (end == len(text) or descendants) and (not restricted or path_key):
                    changed = after + text[end:]
                    return changed.replace('/', '\\') if '\\' in value and '/' not in value else changed
            end = text.rfind('/', 0, end)
        return value

    def text(self, value, key=''):
        return (self.cached_text if len(value) <= 4096 else self._text)(value, key in PATH_KEYS)

    def json(self, value, key=''):
        if not self.prefixes:
            return value
        if isinstance(value, str):
            return self.text(value, key)
        if isinstance(value, list):
            return [self.json(item, key) for item in value]
        if isinstance(value, dict):
            result = {}
            for k, v in value.items():
                changed = self.text(k, 'path')
                if changed in result:
                    raise SourceError('Two metadata keys would merge after the repair; manual review is required.')
                result[changed] = self.json(v, k)
            return result
        return value


def compiled(mappings, root):
    return mappings if isinstance(mappings, PathRemapper) else PathRemapper(mappings, root)


def container_destination(container, datasets):
    """Keep map-folder selections pointed at maps when removing a team layer."""
    is_map = all(Path(d['old']).parent == container and
                 Path(d['new']).parent.name.casefold() == container.name.casefold() for d in datasets)
    return Path(os.path.commonpath([str(Path(d['new']).parent) if is_map else d['collection'] for d in datasets]))


def remap_text(value, mappings, root, key=''):
    return compiled(mappings, root).text(value, key)


def remap_json(value, mappings, root, key=''):
    return compiled(mappings, root).json(value, key)


def restore_json(current, original, forward, reverse, root):
    """Restore unchanged fields while retaining preferences/history added since repair."""
    forward, reverse = compiled(forward, root), compiled(reverse, root)
    changed = remap_json(original, forward, root)
    if current == changed:
        return original
    if isinstance(current, dict) and isinstance(original, dict):
        result = remap_json(current, reverse, root)
        for key, old_value in original.items():
            after_key = remap_text(key, forward, root, 'path')
            if after_key in current:
                restored_key = remap_text(after_key, reverse, root, 'path')
                value = restore_json(current[after_key], old_value, forward, reverse, root)
                if after_key == key or current[after_key] == changed[after_key]:
                    result.pop(restored_key, None)
                    result[key] = value
                else:
                    result[restored_key] = value
        return result
    if isinstance(current, list) and isinstance(original, list):
        result = []
        for item in current:
            matched = next((i for i, value in enumerate(changed) if item == value), None)
            result.append(original[matched] if matched is not None else remap_json(item, reverse, root))
        return result
    return remap_json(current, reverse, root)


class DirectoryFix:
    def __init__(self, root=ANALYSIS, state=STATE, resolver=None, replay_indices=None, catalog=None, log=print):
        self.root = validate_root(root)
        self.state = Path(state).resolve()
        self.resolver = resolver or Resolver()
        self.log, self.profiles = log, {}
        settings = read_json(self.state / 'settings.json', {})
        if replay_indices is None:
            from downloads import DEFAULT_REPLAYS
            replay_indices = [Path(settings.get('download_root') or DEFAULT_REPLAYS) / 'replay-library.json', DEFAULT_REPLAYS / 'replay-library.json']
        self.indices = list(dict.fromkeys(Path(p).resolve() for p in replay_indices))
        self.catalog = Path(catalog).resolve() if catalog else self.root.parent / 'game_catalog.sqlite3'
        self.lock = self.state / 'analysis-maintenance.lock'

    def progress(self, phase, percent, detail):
        self.log('TOOLBOX_PROGRESS ' + json.dumps({'phase': phase, 'percent': percent, 'detail': detail}))

    def profile(self, player_id=None, steam_id=None):
        lookup = ('id', player_id) if player_id else ('steam', steam_id)
        if not lookup[1]:
            raise SourceError('No stable FACEIT account ID or SteamID64 is available.')
        if lookup not in self.profiles:
            try:
                path = 'players/' + str(uuid.UUID(player_id)) if player_id else 'players?' + urlencode({'game': 'cs2', 'game_player_id': steam_id})
                data = self.resolver.faceit(path)
                if not isinstance(data, dict) or not isinstance(data.get('games'), dict):
                    raise SourceError('FACEIT returned an invalid player identity response.')
                uid = str(uuid.UUID(data['player_id']))
                actual_steam = str(data.get('games', {}).get('cs2', {}).get('game_player_id') or '')
                if (player_id and uid != str(uuid.UUID(player_id))) or (steam_id and actual_steam != str(steam_id)) or not data.get('nickname'):
                    raise SourceError('FACEIT identity response does not match the requested stable ID.')
                self.profiles[lookup] = {'player_id': uid, 'steam_id64': actual_steam, 'nickname': data['nickname']}
            except (ValueError, KeyError, OSError) as exc:
                self.profiles[lookup] = {'error': str(exc)}
        found = self.profiles[lookup]
        if 'error' in found:
            raise SourceError(found['error'])
        return found

    def library_contexts(self):
        found = {}
        for path in self.indices:
            if not path.exists():
                continue
            data = load_json(path)
            for match in data.get('matches', {}).values():
                for sha in match.get('files', []):
                    found.setdefault(sha, []).append(match)
        return found

    def canonical_stem(self, folder, stem, formatted, historical, context, map_name, player, summary):
        """Prefer recorded metadata; never invent dates or infer fixed teams from CT/T."""
        if formatted:
            return re.sub(r'^\[(\d+)-(\d+)\]', r'[\1-vs-\2]', stem) if player or context.get('source') == 'faceit' else stem
        from downloads import filename
        mapped = str(map_name).removeprefix('de_').lower()
        options = [m for m in context.get('maps', []) if m.get('map') == mapped]
        historical_name = None
        if player and (folder / 'players.csv').is_file():
            with (folder / 'players.csv').open(encoding='utf-8-sig', newline='') as stream:
                names = {r['name'] for r in csv.DictReader(stream) if r.get('steamid') == player['steam_id64']}
            if len(names) == 1:
                historical_name = next(iter(names))
        label = historical_name or (historical[1] if historical else context.get('label'))
        naming = {**context, 'label': label}
        if len(options) == 1 and naming.get('date') and label:
            return Path(filename(naming, options[0])).stem
        if not (player and historical and label):
            raise SourceError('The original match date/score is unavailable; a complete filename cannot be reconstructed.')
        naming.update(source='faceit', date=datetime.strptime(historical[2], '%m-%d-%Y').date().isoformat(), event='FaceIt')
        # Scoreboard clan identities align the final score without assuming that CT/T stay fixed.
        if not summary.get('contains_full_match_likely') or not summary.get('map_complete_likely'):
            raise SourceError('A complete final score cannot be verified for this game.')
        with (folder / 'scoreboard.csv').open(encoding='utf-8-sig', newline='') as stream:
            clans = {r.get('team_clan_name') for r in csv.DictReader(stream) if r.get('steamid') == player['steam_id64']}
        clans.discard(''); clans.discard(None)
        with (folder / 'rounds.csv').open(encoding='utf-8-sig', newline='') as stream:
            final = None
            for final in csv.DictReader(stream):
                pass
        if len(clans) != 1 or not final:
            raise SourceError('The player’s team cannot be aligned to the final score.')
        clan = next(iter(clans))
        sides = [side for side in ('ct', 't') if final.get(side + '_team_clan_name') == clan]
        if len(sides) != 1 or final.get('round_observation_complete', '').lower() not in ('true', '1'):
            raise SourceError('The final score is incomplete or its team identity is ambiguous.')
        own = sides[0]; other = 't' if own == 'ct' else 'ct'
        scores = [int(final[side + '_score_after']) for side in (own, other)]
        return Path(filename(naming, {'map': mapped, 'score': scores})).stem

    def classify(self, folder, libraries):
        summary = load_json(folder / 'match_summary.json')
        viewer = load_json(folder / 'viewer_tracks_meta.json') if (folder / 'viewer_tracks_meta.json').is_file() else {}
        source = load_json(folder / 'analysis_source.json') if (folder / 'analysis_source.json').is_file() else {}
        if not all(isinstance(value, dict) for value in (summary, viewer, source)):
            raise SourceError('Analysis metadata is not a JSON object.')
        context = dict(source.get('context') or {})
        sha = source.get('sha256') or viewer.get('demo_sha256')
        candidates = libraries.get(sha, [])
        if not context.get('owner') and len(candidates) == 1:
            context = dict(candidates[0])
        elif candidates:
            same = [c for c in candidates if c.get('id') == context.get('id')]
            if len(same) == 1:
                context = {**same[0], **context}
        demo = source.get('demo') or viewer.get('demo_file') or folder.name.removeprefix('Analysis_')
        stem = Path(str(demo).replace('\\', '/').rsplit('/', 1)[-1]).stem if str(demo).lower().endswith('.dem') else str(demo)
        invalid = folder.name.endswith('__INVALID_v8')
        stem = stem.removesuffix('__INVALID_v8')
        map_name = summary.get('map_name') or viewer.get('map')
        if not map_name:
            raise SourceError('Map metadata is missing.')
        parents = [p for p in folder.parents if p != self.root and p.is_relative_to(self.root)]
        old_collection = next((p for p in parents if p.name.startswith(('analyzed_', 'Analysis_'))), None)
        collection_label = old_collection.name if old_collection else ''
        formatted = re.fullmatch(r'\[[0-9]+(?:-vs-|-)[0-9]+\]_(.+)_([A-Za-z]{3}-[0-9]{2}-[0-9]{4})_([^_]+)_(.+)', stem)
        historical = re.match(r'(.+?)_([0-9]{2}-[0-9]{2}-[0-9]{4})_', stem)
        family = summary.get('demo_source_family', '')
        faceit = context.get('source') == 'faceit' or str(family).startswith('faceit')
        kind = context.get('collection_kind')
        if not kind:
            if context.get('source') == 'faceit' and context.get('label') == context.get('owner'):
                kind = 'player'
            elif faceit and ((formatted and '-vs-' not in formatted[1]) or historical or '_demos' in collection_label):
                kind = 'player'
            else:
                kind = 'team'
        identity_record = None
        if kind == 'player':
            if not faceit:
                raise SourceError('Current-name player repair is supported only for verified FACEIT games.')
            hint = context.get('owner') or summary.get('target_player')
            if not hint and old_collection:
                hint = re.sub(r'_demos(?:_v[0-9]+)?$|_v[0-9]+$', '', collection_label.removeprefix('analyzed_').removeprefix('Analysis_'))
            fallback = historical[1] if historical else formatted[1] if formatted else None
            player_id = context.get('selected_player_id')
            steam_id = str(summary.get('target_steamid') or '')
            if not steam_id and (folder / 'players.csv').is_file():
                with (folder / 'players.csv').open(encoding='utf-8-sig', newline='') as stream:
                    players = list(csv.DictReader(stream))
                hints = {str(hint or '').casefold(), str(fallback or '').casefold()} - {''}
                matches = {p.get('steamid', '').strip() for p in players if p.get('name', '').casefold() in hints}
                if len(matches) == 1:
                    steam_id = next(iter(matches))
                elif len(matches) > 1 and not player_id:
                    raise SourceError('Collection and historical nicknames identify different accounts.')
            if steam_id and not re.fullmatch(r'[0-9]{17}', steam_id):
                raise SourceError('Ambiguous or invalid player SteamID64.')
            identity_record = self.profile(player_id, steam_id or None)
            context.update(source='faceit', collection_kind='player', owner=identity_record['nickname'])
        else:
            event = context.get('event') or (formatted[4] if formatted else '')
            if not event and old_collection:
                event = re.sub(r'_v[0-9]+$', '', collection_label.removeprefix('analyzed_'))
            owner = context.get('owner') or (formatted[1] if formatted else '')
            if not owner:
                teams = team_hints(stem)
                owner = '-vs-'.join(teams) if len(teams) == 2 else ''
            if not event or not owner:
                raise SourceError('Tournament/team context cannot be determined safely.')
            context.update(collection_kind='team', owner=owner, event=event)
        stem = self.canonical_stem(folder, stem, formatted, historical, context, map_name, identity_record, summary)
        target_collection = collection(self.root, context)
        target = target_collection / component(str(map_name).removeprefix('de_').lower(), 40) / (analysis_name(stem) + ('__INVALID_v8' if invalid else ''))
        return target, target_collection, identity_record, stem

    def reference_files(self, datasets):
        files = set()
        for base, dirs, names in walk(self.root):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            files.update(base / name for name in names if name.endswith('.json'))
        if self.state.is_dir():
            for base, dirs, names in walk(self.state):
                dirs[:] = [d for d in dirs if d not in ('directory-fixes', 'logs', 'tests') and not d.startswith('.')]
                files.update(base / name for name in names if name.endswith('.json'))
        viewer = ROOT / 'app/modules/viewer2d'
        if viewer.is_dir() and self.root == ANALYSIS.resolve():
            files.update(viewer.rglob('*.json'))
        files.update(path for path in self.indices if path.exists())
        return sorted(files)

    def output_locks(self):
        found = []
        for base, dirs, files in walk(self.root):
            if base.name == '.cs2di_locks':
                found.extend(str(base / name) for name in files if name.endswith('.lock'))
                dirs[:] = []
            elif '.viewer_tracks_updating' in files:
                found.append(str(base / '.viewer_tracks_updating'))
        return found

    def plan(self):
        if not self.root.is_dir():
            raise SourceError('The analysis directory does not exist yet.')
        identifier = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:8]
        run_dir = self.state / 'directory-fixes' / identifier
        self.progress('Directory preview', 0, 'Checking running analysis jobs and saved match details…')
        datasets, skipped, active = [], [], self.output_locks()
        libraries = self.library_contexts()
        scanned = 0
        self.log('Inspecting analysis folders and verifying FACEIT player identities…')
        for base, dirs, files in walk(self.root):
            if base.name == '.cs2di_locks':
                dirs[:] = []
                continue
            if base.name.startswith('.'):
                dirs[:] = []
                continue
            if 'match_summary.json' not in files:
                continue
            dirs[:] = []
            scanned += 1
            try:
                safe_path(base, self.root)
                target, target_collection, player, stem = self.classify(base, libraries)
                safe_path(target, self.root)
                if target != base and (target.is_relative_to(base) or base.is_relative_to(target)):
                    raise SourceError('Source and destination overlap.')
                nested = []
                for parent, children, _ in walk(base):
                    normalized_children = [component(name).casefold() for name in children]
                    if len(set(normalized_children)) != len(normalized_children):
                        raise SourceError('Internal folder names collide after normalization.')
                    for name in children:
                        rel = (parent / name).relative_to(base)
                        cleaned = Path(*(component(part) for part in rel.parts))
                        if cleaned != rel:
                            nested.append({'old': rel.as_posix(), 'new': cleaned.as_posix()})
                        sibling = parent / component(name)
                        if sibling != parent / name and sibling.exists():
                            raise SourceError('An internal folder name collides after normalization.')
                datasets.append({'old': str(base), 'new': str(target), 'collection': str(target_collection),
                                 'player': player, 'historical_demo': stem, 'nested': nested, **inventory(base)})
            except (OSError, ValueError, KeyError, TypeError) as exc:
                skipped.append({'folder': str(base), 'reason': str(exc)})
            if scanned % 25 == 0:
                self.log(f'Inspected {scanned} analysis folders: {len(datasets)} resolved; {len(skipped)} need review.')
        self.progress('Directory preview', 50, f'Folder scan complete: {scanned} inspected; checking destination conflicts…')
        occupied = {Path(d['old']) for d in datasets}
        if self.catalog.exists():
            with closing(sqlite3.connect('file:' + self.catalog.as_posix() + '?mode=ro', uri=True)) as db:
                occupied.update(Path(r[0]) for r in db.execute('SELECT analysis FROM games'))
        assigned = set()
        for item in sorted(datasets, key=lambda d: d['old'] != d['new']):
            target, source = Path(item['new']), Path(item['old'])
            if source.parent == target.parent and re.fullmatch(re.escape(target.name) + r'_[a-f0-9]{10}', source.name):
                target = source  # A preserved duplicate from an earlier repair is already organized.
                item['new'] = str(source)
            if target != source and (target.exists() or target in occupied or target in assigned):
                target = target.with_name(target.name + '_' + hashlib.sha256(str(source).encode()).hexdigest()[:10])
                if target.exists() or target in assigned or target in occupied:
                    skipped.append({'folder': item['old'], 'reason': 'Destination collision needs manual review.'})
                    item['blocked'] = True
                    continue
                item['new'] = str(target)
            assigned.add(target)
        datasets = [d for d in datasets if not d.get('blocked')]
        mappings = []
        for d in datasets:
            if d['old'] != d['new']:
                mappings.append({'old': d['old'], 'new': d['new']})
            for nested in d['nested']:
                mappings.append({'old': str(Path(d['old']) / nested['old']), 'new': str(Path(d['new']) / nested['new'])})
        moves = [d for d in datasets if d['old'] != d['new'] or d['nested']]
        containers = {p for d in moves for p in Path(d['old']).parents if p != self.root and p.is_relative_to(self.root)}
        for container in containers:
            affected = [d for d in datasets if Path(d['old']).is_relative_to(container)]
            if affected and not any(Path(s['folder']).is_relative_to(container) for s in skipped):
                common = container_destination(container, affected)
                if container != common:
                    mappings.append({'old': str(container), 'new': str(common), 'exact': True})
        cleared = {Path(d['old']) for d in moves if d['old'] != d['new']}
        archive = []
        for parent in sorted(containers, key=lambda p: len(p.parts), reverse=True):
            remaining = [p for p in parent.iterdir() if p not in cleared and p.name != '.cs2di_locks']
            if not remaining or all(p.is_file() and p.name in CONTROL_FILES for p in remaining):
                for path in remaining:
                    target = run_dir / 'collection-reports' / path.relative_to(self.root)
                    archive.append({'old': str(path), 'new': str(target), 'sha256': digest_bytes(path.read_bytes())})
                cleared.add(parent)
        references, errors = [], []
        latest = read_json(self.state / 'directory-fixes/latest-fix.json', {})
        pending = read_json(latest.get('journal', ''), {}) if latest.get('journal') else {}
        if pending and pending.get('status') not in ('completed', 'undone'):
            errors.append('The previous repair was interrupted. Use Undo last fix before starting another repair.')
        self.progress('Directory preview', 60, 'Finding saved viewer, library and analysis references…')
        paths = self.reference_files(datasets) if mappings else []
        mapper = compiled(mappings, self.root)
        self.log(f'Checking saved references: {len(paths)} JSON files; {len(mappings)} folder mappings (lookup built once).')
        for index, path in enumerate(paths):
            try:
                if index % 25 == 0 or path.stat().st_size >= 1024 ** 2:
                    self.progress('Directory preview', 60 + 35 * index / len(paths),
                                  f'Checking saved references {index + 1}/{len(paths)}: {path}')
                data = load_json(path)
                changed = remap_json(data, mapper, self.root)
                if changed != data:
                    references.append({'path': str(path), 'sha256': digest_bytes(path.read_bytes())})
            except (OSError, ValueError) as exc:
                errors.append(f'{path}: {exc}')
        self.progress('Directory preview', 96, f'References checked: {len(references)} need updates. Preparing the preview report…')
        catalog_hash = digest_bytes(self.catalog.read_bytes()) if self.catalog.exists() else None
        plan = {'version': 1, 'id': identifier, 'root': str(self.root), 'created_at': datetime.now(timezone.utc).isoformat(),
                'moves': moves, 'mappings': mappings, 'archive': archive, 'references': references,
                'catalog': str(self.catalog) if self.catalog.exists() else None, 'catalog_hash': catalog_hash,
                'skipped': skipped, 'errors': errors, 'active_locks': active,
                'files': sum(d['files'] for d in moves), 'bytes': sum(d['bytes'] for d in moves),
                'metadata_backup_bytes': sum(Path(r['path']).stat().st_size for r in references) + (self.catalog.stat().st_size if self.catalog.exists() else 0)}
        run_dir.mkdir(parents=True, exist_ok=True)
        save_json(run_dir / 'plan.json', plan)
        self.report(plan, run_dir / 'preview.html')
        save_json(self.state / 'directory-fixes/latest-preview.json', {'plan': str(run_dir / 'plan.json')})
        self.progress('Directory preview', 100, 'Preview report saved. No analysis moved.')
        self.log(f"Preview ready: {len(moves)} folders, {plan['files']} files, {plan['bytes']/1024**3:.2f} GiB; {len(skipped)} unresolved. No analysis moved.")
        return plan

    def report(self, plan, path):
        rows = ''.join('<tr><td>' + html.escape(d['old']) + '</td><td>' + html.escape(d['new']) + '</td></tr>' for d in plan['moves'])
        skipped = ''.join('<li>' + html.escape(d['folder'] + ': ' + d['reason']) + '</li>' for d in plan['skipped'])
        errors = ''.join('<li>' + html.escape(e) + '</li>' for e in plan['errors'] + ['Extraction lock requires review: ' + p for p in plan['active_locks']])
        page = '<!doctype html><meta charset="utf-8"><title>Analysis directory repair preview</title><style>body{font:15px system-ui;max-width:1400px;margin:40px auto;padding:0 24px;background:#101923;color:#e0eaf2}table{border-collapse:collapse;width:100%}td,th{padding:12px;border:1px solid #405368;text-align:left;overflow-wrap:anywhere}td{width:50%}li{margin:8px 0}</style>'
        page += f"<h1>Analysis directory repair preview</h1><p>{len(plan['moves'])} folders · {plan['files']} files · {plan['bytes']/1024**3:.2f} GiB relocated using directory renames. No extraction or demo downloads.</p>"
        page += '<p>FACEIT collection folders use verified current account names. Individual game folders retain the historical demo basename. Duplicate analysis versions stay separate. Stored references and the game catalog are updated; metadata/catalog backups and an undo journal are retained.</p>'
        page += '<table><tr><th>Current folder</th><th>Proposed folder</th></tr>' + rows + '</table><h2>Unresolved — left in place</h2><ul>' + skipped + '</ul><h2>Blocking checks</h2><ul>' + errors + '</ul>'
        path.write_text(page, encoding='utf-8')

    def _assert_plan(self, plan):
        if plan.get('version') != 1 or Path(plan.get('root', '')).resolve() != self.root or not re.fullmatch(r'[0-9]{8}-[0-9]{6}-[a-f0-9]{8}', plan.get('id', '')):
            raise SourceError('Invalid repair plan or analysis root.')
        if plan.get('errors') or plan.get('active_locks'):
            raise SourceError('Resolve the blocking checks/active extraction locks and preview again.')
        if self.output_locks():
            raise SourceError('An extraction/viewer job started after preview. Stop it and preview again.')
        run_dir = self.state / 'directory-fixes' / plan['id']
        permitted = set()
        for item in plan['moves']:
            safe_path(item['old'], self.root)
            safe_path(item['new'], self.root)
            if not Path(item['old']).is_dir():
                raise SourceError('An analysis folder disappeared after preview.')
            permitted.add((item['old'], item['new'], False))
            for nested in item['nested']:
                before, after = Path(nested['old']), Path(nested['new'])
                if before.is_absolute() or '..' in before.parts or after != Path(*(component(p) for p in before.parts)):
                    raise SourceError('Invalid internal folder rename in the preview.')
                permitted.add((str(Path(item['old']) / before), str(Path(item['new']) / after), False))
            if inventory(Path(item['old']))['signature'] != item['signature']:
                raise SourceError('Analysis changed after preview. Preview again before applying.')
            if item['new'] != item['old'] and Path(item['new']).exists():
                raise SourceError('A destination appeared after preview. Nothing has moved.')
        for mapping in plan['mappings']:
            old = safe_path(mapping['old'], self.root)
            new = Path(mapping['new']).resolve()
            if new != self.root:
                safe_path(new, self.root)
            if (str(old), str(new), bool(mapping.get('exact'))) not in permitted:
                affected = [d for d in plan['moves'] if Path(d['old']).is_relative_to(old)]
                if not mapping.get('exact') or not affected or new != container_destination(old, affected):
                    raise SourceError('Unexpected reference mapping in the preview.')
        for item in plan['archive']:
            old = safe_path(item['old'], self.root)
            expected = run_dir / 'collection-reports' / old.relative_to(self.root)
            if old.name not in CONTROL_FILES or Path(item['new']) != expected or digest_bytes(old.read_bytes()) != item['sha256']:
                raise SourceError('Collection reports changed after preview.')
        allowed = {p.resolve() for p in self.reference_files([])}
        planned = {Path(ref['path']).resolve() for ref in plan['references']}
        mapper = compiled(plan['mappings'], self.root)
        for path in allowed:
            data = load_json(path)
            if remap_json(data, mapper, self.root) != data and path not in planned:
                raise SourceError('A new stored reference appeared after preview. Preview again.')
        for ref in plan['references']:
            path = Path(ref['path'])
            flexible = path.resolve() in {self.state / 'settings.json', self.state / 'history.json'}
            if path.resolve() not in allowed or (not flexible and digest_bytes(path.read_bytes()) != ref['sha256']):
                raise SourceError('A stored reference changed after preview. Preview again.')
            remap_json(load_json(path), mapper, self.root)
        if plan.get('catalog') and (Path(plan['catalog']).resolve() != self.catalog or digest_bytes(self.catalog.read_bytes()) != plan['catalog_hash']):
            raise SourceError('The game catalog changed after preview. Preview again.')
        if self.catalog.exists():
            with closing(sqlite3.connect('file:' + self.catalog.as_posix() + '?mode=ro', uri=True)) as db:
                for query in ('SELECT analysis,collection,signature,verified,payload FROM games LIMIT 1',
                              'SELECT analysis FROM players LIMIT 1', 'SELECT analysis FROM teams LIMIT 1',
                              'SELECT raw,analysis,fingerprint FROM sources LIMIT 1'):
                    db.execute(query)

    def _rename(self, source, target, journal, run_dir, *, archive=False):
        safe_path(source, run_dir if archive and Path(source).is_relative_to(run_dir) else self.root)
        safe_path(target, run_dir if archive else self.root)
        if target.exists():
            raise SourceError(f'Refusing to replace an existing path: {target}')
        target.parent.mkdir(parents=True, exist_ok=True)
        operation = {'old': str(source), 'new': str(target), 'status': 'prepared', 'archive': archive}
        journal['operations'].append(operation)
        save_json(run_dir / 'journal.json', journal)
        source.rename(target)
        operation['status'] = 'done'
        save_json(run_dir / 'journal.json', journal)

    def _catalog_update(self, mappings):
        if not self.catalog.exists():
            return
        mappings = compiled(mappings, self.root)
        with closing(sqlite3.connect(self.catalog, timeout=30)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {'games', 'players', 'teams', 'sources'} <= tables:
                raise SourceError('The game catalog schema is not recognized.')
            games = db.execute('SELECT analysis,collection,payload FROM games').fetchall()
            affected = []
            for old, old_collection, payload in games:
                new = remap_text(old, mappings, self.root, 'path')
                if new != old:
                    temporary = old + '.__directory_fix_' + uuid.uuid4().hex
                    for table in ('games', 'players', 'teams', 'sources'):
                        db.execute(f'UPDATE {table} SET analysis=? WHERE analysis=?', (temporary, old))
                    affected.append((temporary, new, old_collection, payload))
            for temporary, new, old_collection, payload in affected:
                if db.execute('SELECT 1 FROM games WHERE analysis=?', (new,)).fetchone():
                    raise SourceError('A game catalog destination collides; repair aborted.')
                for table in ('games', 'players', 'teams', 'sources'):
                    db.execute(f'UPDATE {table} SET analysis=? WHERE analysis=?', (new, temporary))
                changed = remap_json(json.loads(payload), mappings, self.root)
                db.execute('UPDATE games SET collection=?, signature=NULL, verified=0, payload=? WHERE analysis=?',
                           (str(Path(new).parent), json.dumps(changed), new))
            for raw, in db.execute('SELECT raw FROM sources').fetchall():
                new = remap_text(raw, mappings, self.root, 'path')
                if new != raw:
                    db.execute('UPDATE sources SET raw=?,fingerprint=NULL WHERE raw=?', (new, raw))

    def apply(self, plan):
        with exclusive(self.lock):
            self._assert_plan(plan)
            run_dir = self.state / 'directory-fixes' / plan['id']
            if (run_dir / 'journal.json').exists():
                raise SourceError('This preview was already used. Preview again or undo the existing repair.')
            run_dir.mkdir(parents=True, exist_ok=True)
            journal = {'version': 1, 'root': str(self.root), 'id': plan['id'], 'status': 'running',
                       'operations': [], 'files': [], 'catalog_backup': None, 'post': [], 'mappings': plan['mappings']}
            save_json(run_dir / 'journal.json', journal)
            try:
                mapper = compiled(plan['mappings'], self.root)
                if self.catalog.exists():
                    backup = run_dir / 'game_catalog.before.sqlite3'
                    with closing(sqlite3.connect(self.catalog)) as source, closing(sqlite3.connect(backup)) as target:
                        source.backup(target)
                    journal['catalog_backup'] = str(backup)
                for item in plan['moves']:
                    source = Path(item['old'])
                    for nested in sorted(item['nested'], key=lambda n: len(Path(n['old']).parts), reverse=True):
                        old = source / nested['old']
                        new = old.with_name(component(old.name))
                        if old != new:
                            self._rename(old, new, journal, run_dir)
                    if item['old'] != item['new']:
                        self._rename(source, Path(item['new']), journal, run_dir)
                    self.log(f"Moved: {item['old']} → {item['new']}")
                for item in plan['archive']:
                    source = Path(item['old'])
                    safe_path(source, self.root)
                    expected = run_dir / 'collection-reports' / source.relative_to(self.root)
                    if expected != Path(item['new']) or digest_bytes(source.read_bytes()) != item['sha256']:
                        raise SourceError('Collection metadata changed after preview.')
                    self._rename(source, expected, journal, run_dir, archive=True)
                physical = compiled(plan['mappings'] + [{'old': a['old'], 'new': a['new']} for a in plan['archive']], self.root)
                for ref in plan['references']:
                    original = Path(ref['path'])
                    path = Path(remap_text(str(original), physical, self.root, 'path'))
                    old = path.read_bytes()
                    flexible = original.resolve() in {self.state / 'settings.json', self.state / 'history.json'}
                    if not flexible and digest_bytes(old) != ref['sha256']:
                        raise SourceError('A reference changed while folders were being moved.')
                    changed = remap_json(json.loads(old.decode('utf-8-sig')), mapper, self.root)
                    data = (json.dumps(changed, indent=2, ensure_ascii=False) + '\n').encode()
                    backup = run_dir / 'backups' / (str(len(journal['files'])) + '.json')
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    backup.write_bytes(old)
                    record = {'path': str(path), 'backup': str(backup), 'before': digest_bytes(old), 'after': digest_bytes(data), 'status': 'prepared'}
                    journal['files'].append(record)
                    save_json(run_dir / 'journal.json', journal)
                    stage = path.with_name(path.name + '.directory-fix.tmp')
                    stage.write_bytes(data)
                    stage.replace(path)
                    record['status'] = 'done'
                    save_json(run_dir / 'journal.json', journal)
                self._catalog_update(plan['mappings'])
                for item in plan['moves']:
                    journal['post'].append({'path': item['new'], **inventory(Path(item['new']))})
                journal['mappings'] = plan['mappings']
                journal['status'] = 'completed'
                save_json(run_dir / 'journal.json', journal)
                save_json(self.state / 'directory-fixes/latest-fix.json', {'journal': str(run_dir / 'journal.json')})
                for item in plan['moves']:
                    parent = Path(item['old']).parent
                    while parent != self.root and parent.is_relative_to(self.root):
                        try:
                            safe_path(parent, self.root)
                            locks = parent / '.cs2di_locks'
                            if locks.is_dir():
                                safe_path(locks, self.root)
                                try:
                                    locks.rmdir()  # Only an empty lock directory; never remove live locks.
                                except OSError:
                                    pass
                            parent.rmdir()
                        except OSError:
                            break
                        parent = parent.parent
                self.log(f"Directory repair complete. Undo journal: {run_dir / 'journal.json'}")
                return journal
            except BaseException:
                journal['status'] = 'needs_rollback'
                save_json(run_dir / 'journal.json', journal)
                self.log('Repair interrupted. The journal and metadata/catalog backups are preserved. Use Undo last fix before retrying.')
                save_json(self.state / 'directory-fixes/latest-fix.json', {'journal': str(run_dir / 'journal.json')})
                raise

    def undo(self, path):
        path = Path(path).resolve()
        safe_path(path, self.state / 'directory-fixes')
        journal = load_json(path)
        if journal.get('root') != str(self.root) or journal.get('version') != 1 or journal.get('status') == 'undone':
            raise SourceError('Invalid or already restored undo journal.')
        run_dir = path.parent
        with exclusive(self.lock):
            for item in journal.get('post', []) if journal['status'] == 'completed' else []:
                checked = safe_path(item['path'], self.root)
                if not checked.is_dir() or inventory(checked)['signature'] != item['signature']:
                    raise SourceError('An analysis changed since the repair. Undo requires manual review.')
            completed = []
            for operation in journal['operations']:
                source, target = Path(operation['old']), Path(operation['new'])
                safe_path(source, self.root)
                safe_path(target, run_dir if operation.get('archive') else self.root)
                if operation['status'] == 'undone':
                    continue
                if operation['status'] == 'done' or (target.exists() and not source.exists()):
                    completed.append(operation)
                elif source.exists() and not target.exists():
                    continue
                else:
                    raise SourceError('An interrupted rename is ambiguous; manual review is required.')
            # Simulate reverse directory renames before touching metadata or the catalog.
            simulated = []
            def exists_after_steps(candidate):
                candidate = Path(candidate)
                for moved, restored in reversed(simulated):
                    if candidate == restored or candidate.is_relative_to(restored):
                        candidate = moved / candidate.relative_to(restored)
                    elif candidate == moved or candidate.is_relative_to(moved):
                        return False
                return candidate.exists()
            for operation in reversed(completed):
                moved, restored = Path(operation['new']), Path(operation['old'])
                if exists_after_steps(restored) or not exists_after_steps(moved):
                    raise SourceError('An original name is occupied or a moved folder is missing. Undo made no changes.')
                simulated.append((moved, restored))
            reverse = [{'old': m['new'], 'new': m['old'], 'exact': m.get('exact', False)} for m in journal.get('mappings', []) if not m.get('exact')]
            forward, reverse = compiled(journal.get('mappings', []), self.root), compiled(reverse, self.root)
            allowed = {p.resolve() for p in self.reference_files([])}
            replacements = []
            for item in reversed(journal['files']) if not journal.get('metadata_restored') else []:
                current, backup = Path(item['path']), Path(item['backup'])
                safe_path(backup, run_dir)
                if current.is_relative_to(run_dir / 'collection-reports'):
                    safe_path(current, run_dir)
                elif current.resolve() not in allowed:
                    raise SourceError('A saved metadata path is no longer in the repair scope.')
                if not current.exists() or digest_bytes(backup.read_bytes()) != item['before']:
                    raise SourceError('A rewritten metadata file is missing; use the saved backups for manual recovery.')
                data = current.read_bytes()
                if digest_bytes(data) == item['after']:
                    replacement = backup.read_bytes()
                elif digest_bytes(data) == item['before']:
                    continue
                else:
                    # Keep newer history/preferences; reverse only affected dataset references.
                    restored = restore_json(json.loads(data.decode('utf-8-sig')), load_json(backup), forward, reverse, self.root)
                    replacement = (json.dumps(restored, indent=2, ensure_ascii=False) + '\n').encode()
                replacements.append((current, replacement))
            journal['status'] = 'undoing'
            save_json(path, journal)
            for current, replacement in replacements:
                stage = current.with_name(current.name + '.directory-fix.tmp')
                stage.write_bytes(replacement)
                stage.replace(current)
            journal['metadata_restored'] = True
            save_json(path, journal)
            if not journal.get('catalog_restored'):
                self._catalog_update(reverse)
                journal['catalog_restored'] = True
                save_json(path, journal)
            for operation in reversed(completed):
                source, target = Path(operation['new']), Path(operation['old'])
                if target.exists():
                    raise SourceError('An original folder name is occupied. Undo stopped without overwriting it.')
                target.parent.mkdir(parents=True, exist_ok=True)
                source.rename(target)
                operation['status'] = 'undone'
                save_json(path, journal)
            journal['status'] = 'undone'
            save_json(path, journal)
            for operation in completed:
                parent = Path(operation['new']).parent
                while parent != self.root and parent.is_relative_to(self.root):
                    try:
                        safe_path(parent, self.root)
                        parent.rmdir()
                    except OSError:
                        break
                    parent = parent.parent
            self.log('Directory repair undone. Original folder names restored; no analysis rerun.')
        return journal


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--preview', action='store_true')
    mode.add_argument('--apply', type=Path)
    mode.add_argument('--undo', type=Path)
    args = parser.parse_args()
    try:
        fixer = DirectoryFix()
        if args.preview:
            fixer.plan()
        elif args.apply:
            fixer.apply(load_json(args.apply))
        else:
            fixer.undo(args.undo)
        return 0
    except (OSError, ValueError, sqlite3.Error, RuntimeError) as exc:
        print('ERROR: ' + str(exc), flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
