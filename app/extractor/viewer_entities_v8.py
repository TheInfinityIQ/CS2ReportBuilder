"""Build, validate and atomically publish the v8 networked-entity sidecars."""
from __future__ import annotations

import base64
import csv
import gzip
import hashlib
import json
import math
import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from smoke_voxels_v8 import decode_stream

HERE = Path(__file__).resolve().parent
PROJECT = HERE / 'entity_v8' / 'EntityExtractor.csproj'
DLL = PROJECT.parent / 'bin' / 'Release' / 'net9.0' / 'EntityExtractor.dll'
FILES = ('loot_tracks.jsonl.gz', 'inferno_patches.jsonl.gz', 'smoke_frames.jsonl.gz')
BACKGROUND = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}


def round_window(analysis, round_number):
    with (Path(analysis) / 'rounds.csv').open(encoding='utf-8-sig', newline='') as f:
        row = next((r for r in csv.DictReader(f) if int(r['round']) == round_number), None)
    if row is None:
        raise ValueError(f'Round {round_number} not found in {analysis}')
    return int(float(row['freeze_end_tick'])), int(float(row['end_tick']))


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def iter_rows(path):
    with gzip.open(path, 'rt', encoding='utf-8-sig') as f:
        for line in f:
            yield json.loads(line)


def validate_sidecars(folder, start=0, end=None, analysis=None):
    """Reject corrupt streams, stale entity identities, and mismatched source clocks."""
    counts, first_geometry = {}, {'smoke_frames.jsonl.gz': [], 'inferno_patches.jsonl.gz': []}
    for name in FILES:
        previous_tick, active, seen, count = -1, set(), set(), 0
        for row in iter_rows(folder / name):
            tick, identity, action = row['tick'], row['id'], row['action']
            if not isinstance(tick, int) or tick < previous_tick or tick < start or (end is not None and tick > end):
                raise ValueError(f'{name}: invalid or unordered tick {tick}')
            previous_tick = tick
            if not isinstance(identity, str) or not identity.isdigit():
                raise ValueError(f'{name}: entity handle must be a decimal string')
            if action == 'upsert':
                state = row['state']
                if state.get('id') != identity or identity != str((int(state['serial']) << 14) | int(state['entityIndex'])):
                    raise ValueError(f'{name}: handle/serial/index identity mismatch')
                if not all(math.isfinite(state[k]) for k in ('x', 'y', 'z')):
                    raise ValueError(f'{name}: nonfinite entity coordinates')
                if 'patches' in state:
                    indices = [p['index'] for p in state['patches']]
                    if len(indices) != len(set(indices)) or len(indices) > state['fireCount']:
                        raise ValueError('Invalid fire patch indices/count')
                    for p in state['patches']:
                        if not isinstance(p['burning'], bool) or not all(math.isfinite(p[k]) for k in ('x', 'y', 'z')):
                            raise ValueError('Invalid fire patch state')
                if 'voxelBase64' in state:
                    raw = base64.b64decode(state['voxelBase64'], validate=True)
                    if len(raw) != state['payloadBytes']:
                        raise ValueError('Smoke raw-buffer byte count mismatch')
                if identity not in seen and name in first_geometry:
                    first_geometry[name].append(row)
                seen.add(identity)
                active.add(identity)
            elif action in ('removed', 'pickup'):
                if identity not in active:
                    raise ValueError(f'{name}: removal without an observed entity')
                active.remove(identity)
            else:
                raise ValueError(f'{name}: unknown action {action}')
            count += 1
        counts[name] = count
    alignment = {'status': 'not_checked', 'matched': 0, 'checked': 0}
    if analysis:
        alignment = check_alignment(first_geometry, Path(analysis), start)
    return {'passed': True, 'counts': counts, 'alignment': alignment}


def check_alignment(first_geometry, analysis, start):
    matched = checked = 0
    maximum_delta = 0
    for stream, event in [('smoke_frames.jsonl.gz', 'smokegrenade_detonate'),
                          ('inferno_patches.jsonl.gz', 'inferno_startburn')]:
        file = analysis / 'events' / f'{event}.csv.gz'
        if not file.exists():
            continue
        with gzip.open(file, 'rt', encoding='utf-8-sig') as f:
            events = list(csv.DictReader(f))
        for row in first_geometry[stream]:
            if row['tick'] <= start:  # Already alive at a selected-window boundary.
                continue
            state = row['state']
            p = state['patches'][0] if state.get('patches') else state
            checked += 1
            deltas = [math.hypot(float(e['x']) - p['x'], float(e['y']) - p['y'])
                      for e in events if abs(int(e['tick']) - row['tick']) <= 1]
            # SmokeDetonationPos and event x/y are separate network fields. On the
            # validation demo they differ by up to 3.45 units on the same tick.
            if deltas and min(deltas) < 8:
                matched += 1
                maximum_delta = max(maximum_delta, min(deltas))
            else:
                raise ValueError(f'Entity/event alignment failed: {event}, tick {row["tick"]}, entity {row["id"]}')
    return {'status': 'verified_against_demoparser_events' if checked else 'no_comparable_events',
            'matched': matched, 'checked': checked, 'tick_tolerance': 1, 'position_tolerance_units': 8,
            'maximum_observed_position_delta_units': maximum_delta}


def build_backend():
    if not shutil.which('dotnet'):
        raise RuntimeError('The v8 entity pass requires the .NET 9 SDK. See README_v8.md.')
    sources = [PROJECT, PROJECT.parent / 'Program.cs']
    if DLL.exists() and DLL.stat().st_mtime >= max(p.stat().st_mtime for p in sources):
        return
    env = {**os.environ, 'DOTNET_CLI_TELEMETRY_OPTOUT': '1', 'DOTNET_SKIP_FIRST_TIME_EXPERIENCE': '1'}
    subprocess.run(['dotnet', 'build', str(PROJECT), '-c', 'Release', '--nologo'],
                   check=True, cwd=HERE, env=env, timeout=300, **BACKGROUND)


def extract_entities(demo, destination, hz=16, start=0, end=None, analysis=None):
    """Existing sidecars survive backend/validation failures; publish only a verified set."""
    demo, destination = Path(demo).resolve(), Path(destination).resolve()
    if hz not in (1, 2, 4, 8, 16, 32, 64):
        raise ValueError('Entity sample Hz must divide 64')
    if not demo.is_file() or demo.suffix.lower() != '.dem':
        raise ValueError(f'Not a demo file: {demo}')
    if start < 0 or end is not None and end < start:
        raise ValueError('Invalid tick window')
    if analysis is None and (destination.parent / 'rounds.csv').exists():
        analysis = destination.parent
    if analysis and start == 0 and end is None:
        with (Path(analysis) / 'rounds.csv').open(encoding='utf-8-sig', newline='') as f:
            rounds = list(csv.DictReader(f))
        if rounds:
            start = min(int(float(r['start_tick'])) for r in rounds)
            end = max(int(float(r['end_tick'])) for r in rounds)
    digest = sha256(demo)
    if analysis:
        metadata = Path(analysis) / 'viewer_tracks_meta.json'
        if metadata.exists():
            expected = json.loads(metadata.read_text(encoding='utf-8-sig')).get('demo_sha256')
            if expected and expected != digest:
                raise ValueError('--analysis belongs to a different demo (SHA-256 mismatch)')
    build_backend()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.viewer-v8-', dir=destination.parent) as temp:
        stage = Path(temp) / 'viewer_v8'
        subprocess.run(['dotnet', str(DLL), str(demo), str(stage), str(hz), str(start),
                        str(end if end is not None else 2147483647)], check=True, timeout=1800, **BACKGROUND)
        validation = validate_sidecars(stage, start, end, analysis)
        metadata_path = stage / 'entity_meta.json'
        meta = json.loads(metadata_path.read_text(encoding='utf-8-sig'))
        expected = {FILES[0]: meta['counts']['loot'], FILES[1]: meta['counts']['fire'], FILES[2]: meta['counts']['smoke']}
        if validation['counts'] != expected:
            raise ValueError('Entity metadata row counts do not match sidecars')
        smoke = decode_stream(stage / 'smoke_frames.jsonl.gz', stage / 'smoke_voxels.jsonl.gz')
        (stage / 'smoke_decode_meta.json').write_text(json.dumps(smoke, indent=2), encoding='utf-8')
        meta['capabilities']['smokeGeometry'] = smoke['geometry'] if smoke['status'] == 'decoded' else smoke['status']
        meta['capabilities']['smokeVoxels'] = 'raw_preserved_with_experimental_decode'
        meta['files'] = [*FILES, 'smoke_voxels.jsonl.gz', 'smoke_decode_meta.json']
        meta.update(demo_sha256=digest, validation=validation,
                    smoke_decoder={k: v for k, v in smoke.items() if k != 'changes'},
                    file_sha256={name: sha256(stage / name) for name in (*FILES, 'smoke_voxels.jsonl.gz', 'smoke_decode_meta.json')})
        metadata_path.write_text(json.dumps(meta, indent=2), encoding='utf-8')
        backup = destination.with_name('.viewer-v8-backup-' + uuid.uuid4().hex)
        if destination.exists():
            destination.rename(backup)
        try:
            stage.rename(destination)
        except BaseException:
            if backup.exists():
                backup.rename(destination)
            raise
        if backup.exists():
            # Only delete the generated backup inside this exact output parent.
            if backup.resolve().parent != destination.parent or not backup.name.startswith('.viewer-v8-backup-'):
                raise ValueError('Unsafe backup cleanup path')
            shutil.rmtree(backup)
    return meta
