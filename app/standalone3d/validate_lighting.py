"""Bounded lighting checks on already-prepared maps. No imports/rebuilds."""
import copy
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / 'data/.desktop/standalone3d'


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--max-ready-seconds',type=float,default=30)
    args=parser.parse_args()
    reports = []
    target = CACHE / 'validation/lighting'
    for path in sorted((CACHE / 'validation/pool').glob('*/fixture.json')):
        data = copy.deepcopy(json.loads(path.read_text(encoding='utf-8')))
        data['validation_fixture'].update(weapons=['ak47'], lighting_audit=True)
        folder = target / data['map']
        folder.mkdir(parents=True, exist_ok=True)
        fixture = folder / 'fixture.json'
        fixture.write_text(json.dumps(data), encoding='utf-8')
        process = subprocess.run(
            [sys.executable, str(ROOT/'app/desktop/embedded_smoke.py'),
             '--replay', str(fixture), '--timeout', '90', '--max-ready-seconds', str(args.max_ready_seconds)],
            capture_output=True, text=True, timeout=110)
        report = json.loads((CACHE/'embedded-check/result.json').read_text())
        report['map'] = data['map']
        report['loading_target_seconds']=args.max_ready_seconds
        report['meets_loading_target']=report.get('ready_seconds',float('inf'))<=args.max_ready_seconds
        report['process_returncode'] = process.returncode
        (folder/'result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        reports.append(report)
        print(data['map'], report.get('ok'), report.get('ready_seconds'),
              'seconds;', report.get('renderer_errors', []), flush=True)
        if process.returncode:
            print(process.stderr[-800:], flush=True)
    sources = ['main.gd', 'source_materials.gd', 'source_layered.gdshader',
               'source_water.gdshader', 'source_viewmodel.gd', 'source_bounce.gd',
               'source_bounce.gdshaderinc', 'source_probe_surface.gdshader',
               'source_reflections.gd', 'source_reflection.gdshaderinc',
               'source_direct.gd', 'source_direct.gdshaderinc', 'lighting_regressions.gd']
    revisions = {name: hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest() for name in sources}
    summary = {'maps': reports, 'renderer_sources': revisions,
               'ok': len(reports)==7 and all(r.get('ok') and not r['process_returncode'] for r in reports)}
    (target/'results.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    return 0 if summary['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
