"""Finish interrupted additive viewer preparation without replacing valid core data."""
from pathlib import Path
import argparse
import hashlib
import json
import sys


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def can_resume_core(folder, expected_sha, entity_hz=None):
    folder = Path(folder)
    try:
        return (not (folder/'analysis_run.json').exists()
                and read(folder/'match_summary.json').get('valid') is True
                and read(folder/'integrity_checks.json').get('integrity_ok') is True
                and read(folder/'match_summary.json').get('viewer_entities_v8', {}).get('demo_sha256') == expected_sha
                and read(folder/'viewer_v8/entity_meta.json').get('demo_sha256') == expected_sha
                and (entity_hz is None or read(folder/'viewer_v8/entity_meta.json').get('sampleHz') == int(entity_hz)))
    except (OSError, ValueError, TypeError, AttributeError):
        return False


def resume_owned(demo, folder):
    """Caller owns both the maintenance lock and this analysis's lock."""
    from extract_viewer_tracks import NEW_FILES, _process_demo_unlocked
    from extract_demos_v8 import write_json
    from game_catalog import notify_output, file_stamp
    demo, folder = Path(demo).resolve(), Path(folder).resolve()
    source_sha = digest(demo)
    if not can_resume_core(folder, source_sha):
        raise ValueError('Existing core is not a verified interrupted analysis; preserved.')
    entity = read(folder/'viewer_v8/entity_meta.json')
    for name, expected in entity.get('file_sha256', {}).items():
        path = folder/'viewer_v8'/name
        if Path(name).name != name or digest(path) != expected:
            raise ValueError('Existing entity data changed; preserved.')
    if not entity.get('file_sha256') or entity.get('validation', {}).get('passed') is not True:
        raise ValueError('Existing entity validation unavailable; preserved.')
    preserved = {p.relative_to(folder): digest(p) for p in folder.rglob('*')
                 if p.is_file() and p.name not in NEW_FILES and not p.name.startswith('.viewer_')}
    print('Resuming only missing viewer tracks; verified core analysis is preserved.', flush=True)
    result = _process_demo_unlocked(demo, folder, 16, True, False)
    viewer = read(folder/'viewer_tracks_meta.json')
    if viewer.get('demo_sha256') != source_sha or viewer.get('interpolation_check', {}).get('ok') is not True:
        raise ValueError('Resumed viewer did not pass validation; core preserved.')
    for name, expected in viewer.get('sha256_files', {}).items():
        if Path(name).name != name or digest(folder/name) != expected:
            raise ValueError('Viewer checksum validation failed; core preserved.')
    if any(not (folder/name).is_file() or digest(folder/name) != expected for name, expected in preserved.items()):
        raise ValueError('Core analysis changed while resuming; completion receipt withheld.')
    meta = read(folder/'match_summary.json')
    record = {'demo': demo.name, 'stem': folder.name, 'success': True,
              'viewer_status': result['status'], 'viewer_hz': 16, 'output_kind': 'canonical',
              'output_path': str(folder), 'resumed_viewer_only': True}
    for key in ['valid', 'round_table_valid', 'coaching_valid', 'map_complete_likely',
                'contains_full_match_likely', 'integrity_hard_failure_count',
                'integrity_soft_warning_count', 'demo_source_family']:
        record[key] = meta.get(key)
    write_json({'demo_count': 1, 'success_count': 1, 'failure_count': 0, 'invalid_count': 0,
                'viewer_failure_count': 0, 'results': [record]}, folder/'analysis_run.json')
    notify_output(folder, demo, owned=True, source_sha=source_sha, source_stamp=file_stamp(demo))
    print('Interrupted analysis recovered and validated.', flush=True)


def main():
    here = Path(__file__).resolve().parent
    sys.path[:0] = [str(here), str(here/'.deps'), str(here.parent)]
    from job_lock import exclusive, lock_path
    from demo_layout import data_root
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--demo', type=Path, required=True)
    parser.add_argument('--analysis', type=Path, required=True)
    args = parser.parse_args()
    with exclusive(data_root()/'.desktop/analysis-maintenance.lock'), exclusive(lock_path(args.analysis)):
        resume_owned(args.demo, args.analysis)


if __name__ == '__main__':
    main()
