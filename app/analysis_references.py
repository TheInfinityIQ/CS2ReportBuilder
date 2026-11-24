"""Portable, hash-bound analysis references. Targets are data paths confined to the analysis root."""
from pathlib import Path
import json
import hashlib
import os
import re
import uuid

REFERENCE = 'analysis_reference.json'
CONTEXT_KEYS = ('id', 'url', 'source', 'owner', 'label', 'event', 'date', 'maps',
                'collection_kind', 'selected_player_id', 'selected_team_id', 'heatmap_identity')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def safe(root, path):
    root = Path(root).resolve();path = Path(path)
    if not path.is_absolute():path = root/path
    path = path.resolve()
    if not path.is_relative_to(root) or path == root:
        raise ValueError('Analysis reference escapes the analysis library.')
    return path


def reference(root, folder):
    folder = safe(root, folder);path = folder/REFERENCE
    if not path.is_file():return None
    if path.stat().st_size > 256*1024:raise ValueError('Analysis reference is unexpectedly large.')
    value = read(path)
    if not isinstance(value, dict):raise ValueError('Invalid analysis reference.')
    if value.get('version') != 1 or not re.fullmatch('[a-f0-9]{64}', str(value.get('demo_sha256', ''))):
        raise ValueError('Unknown reference version or invalid demo identity.')
    if not isinstance(value.get('target'), str):raise ValueError('Missing analysis reference target.')
    if any(not isinstance(value.get(k, {}), dict) for k in ('context', 'canonical_context')):
        raise ValueError('Invalid reference collection metadata.')
    if value.get('entity_hz', 16) not in (1, 2, 4, 8, 16, 32, 64):
        raise ValueError('Unsupported reference sampling rate.')
    safe(root, value['target'])
    return value


def resolve(root, folder, expected_sha=None):
    folder = safe(root, folder);seen = set();identity = expected_sha;schema = None
    for _ in range(16):
        if folder in seen:raise ValueError('Analysis reference cycle detected.')
        seen.add(folder);value = reference(root, folder)
        if value is None:
            meta = folder/'viewer_tracks_meta.json'
            if meta.is_file() and identity and read(meta).get('demo_sha256') != identity:
                raise ValueError('Analysis reference points to another demo.')
            summary = folder/'match_summary.json'
            if schema is not None and summary.is_file() and read(summary).get('schema_version') != schema:
                raise ValueError('Analysis reference schema changed; review required.')
            return folder
        if identity and value['demo_sha256'] != identity:
            raise ValueError('Analysis reference chain changes demo identity.')
        if schema is not None and value.get('analysis_schema') not in (None, schema):
            raise ValueError('Analysis reference chain changes schema.')
        schema = value.get('analysis_schema', schema)
        identity = value['demo_sha256'];folder = safe(root, value['target'])
    raise ValueError('Analysis reference chain exceeds its limit.')


def complete(folder, sha, hz=16):
    folder = Path(folder)
    try:
        if (folder/'.viewer_tracks_updating').exists():return False
        required = ('header.json', 'rounds.csv', 'player_rounds.csv', 'player_positions.csv.gz',
                    'economy.csv', 'grenade_throws.csv.gz', 'grenade_paths.csv.gz')
        if any(not (folder/name).is_file() for name in required) or not (folder/'events').is_dir():return False
        summary = read(folder/'match_summary.json');meta = read(folder/'viewer_tracks_meta.json')
        if summary.get('valid') is not True or meta.get('demo_sha256') != sha:return False
        if read(folder/'integrity_checks.json').get('integrity_ok') is not True:return False
        if not (folder/'viewer_tracks.csv.gz').is_file():return False
        if meta.get('interpolation_check', {}).get('ok') is not True:return False
        entities = folder/'viewer_v8/entity_meta.json'
        if entities.exists():
            state = read(entities)
            if state.get('demo_sha256') != sha or state.get('sampleHz') != int(hz):return False
            if state.get('validation', {}).get('passed') is not True:return False
        elif int(hz) != 16:return False
        for base, hashes in [(folder, meta.get('sha256_files', {})),
                             (folder/'viewer_v8', state.get('file_sha256', {}) if entities.exists() else {})]:
            for name, expected in hashes.items():
                if Path(name).name != name:return False
                with (base/name).open('rb') as stream:
                    if hashlib.file_digest(stream, 'sha256').hexdigest() != expected:return False
        receipt = folder/'analysis_run.json'
        if receipt.exists():
            state = read(receipt)
            if state.get('success_count') != 1 or any(state.get(k, 0) for k in ['failure_count', 'invalid_count', 'viewer_failure_count']):return False
        return True
    except (OSError, ValueError, TypeError, KeyError, AttributeError):return False


def find(root, sha, hz=16, candidates=(), *, discover=True, schema=None):
    root = Path(root).resolve();seen = set()
    paths = list(candidates)
    if discover and root.exists():paths.extend(p.parent for p in root.rglob('viewer_tracks_meta.json'))
    for path in paths:
        try:
            path = resolve(root, path, sha)
            if path in seen:continue
            seen.add(path)
            if schema is not None and read(path/'match_summary.json').get('schema_version') != schema:continue
            if complete(path, sha, hz):return path
        except (OSError, ValueError, TypeError):continue
    return None


def write(root, folder, target, sha, context, map_name, hz=16):
    folder, target = safe(root, folder), resolve(root, target, sha)
    if folder == target:return
    if not complete(target, sha, hz):raise ValueError('Cannot reference incomplete or mismatched analysis.')
    previous = reference(root, folder)
    if previous and (previous['demo_sha256'] != sha or previous.get('analysis_schema') not in
                     (None, read(target/'match_summary.json').get('schema_version'))):
        raise ValueError('Existing reference identity or schema changed; preserved for review.')
    if folder.exists() and any(p.name != REFERENCE for p in folder.iterdir()):
        raise ValueError('Existing analysis/user files are preserved; no reference was substituted.')
    # Follow to the real target, not another alias. Only public provider context
    # is stored; signed download URLs, credentials and account settings are excluded.
    source = {}
    try:source = read(target/'analysis_source.json').get('context') or {}
    except (OSError, ValueError):pass
    value = {'version': 1, 'demo_sha256': sha, 'target': target.relative_to(Path(root).resolve()).as_posix(),
             'map': map_name, 'context': {k: context[k] for k in CONTEXT_KEYS if k in context},
             'entity_hz': int(hz),
             'canonical_context': {k: source[k] for k in CONTEXT_KEYS if k in source},
             'analysis_schema': read(target/'match_summary.json').get('schema_version')}
    folder.mkdir(parents=True, exist_ok=True)
    stage = folder/(REFERENCE+'.'+uuid.uuid4().hex+'.tmp')
    stage.write_text(json.dumps(value, indent=2, allow_nan=False), encoding='utf-8')
    os.replace(stage, folder/REFERENCE)
