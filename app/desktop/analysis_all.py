"""Review then repair downloaded-demo analyses and portable reference folders."""
from pathlib import Path
import argparse
import json
import sys
from jobs import ROOT, STATE, save_json
import downloads as d
import analysis_references as refs
from extractor.job_lock import exclusive, lock_path


def preview(replays, analysis):
    replays, analysis = Path(replays).resolve(), Path(analysis).resolve()
    items, issues = {}, []
    with d.library_lock(replays), exclusive(STATE/'analysis-maintenance.lock'):
        library = d.Library(replays)
        for match in library.data['matches'].values():
            for sha in match.get('files', []):
                if sha in library.data['files']:
                    items.setdefault(sha, {'sha': sha, 'context': {k: match[k] for k in refs.CONTEXT_KEYS if k in match}, 'references': []})
        for path in sorted(analysis.rglob(refs.REFERENCE)):
            sha = None
            try:
                value = refs.reference(analysis, path.parent);sha = value['demo_sha256']
                target = refs.resolve(analysis, path.parent, sha)
                context = value.get('canonical_context') or value.get('context') or {}
                item = items.setdefault(sha, {'sha': sha, 'context': context, 'references': []})
                item['references'].append(str(path.parent))
                item.setdefault('destination', str(target))
                item.setdefault('hz', value.get('entity_hz', 16))
                if item['hz'] != value.get('entity_hz', 16):
                    raise ValueError('References request conflicting sampling rates; review required.')
                schema = value.get('analysis_schema')
                if item.get('schema') not in (None, schema):
                    raise ValueError('References request conflicting analysis schemas; review required.')
                item['schema'] = schema
                if not item.get('context', {}).get('url'):
                    item['context'] = {**item.get('context', {}), **value.get('context', {})}
            except (OSError, ValueError, RuntimeError) as exc:
                issues.append({'reference': str(path), 'reason': str(exc)})
                if sha in items:items[sha]['blocked'] = str(exc)
        candidates = [p.parent for p in analysis.rglob('viewer_tracks_meta.json')]
        for item in items.values():
            item.setdefault('hz', 16)
            canonical = refs.find(analysis, item['sha'], item['hz'], candidates, discover=False, schema=item.get('schema'))
            item['canonical'] = str(canonical) if canonical else None
            item['analysis_needed'] = canonical is None
            item['download_needed'] = canonical is None and not library.valid(item['sha'])
        # Physical unindexed files require verified collection metadata, not a
        # nickname/filename guess. Expose them instead of silently ignoring them.
        indexed = {str(library.path(r)) for r in library.data['files'].values()}
        for path in library.existing:
            if str(path.resolve()) not in indexed:
                issues.append({'demo': str(path), 'reason': 'Unindexed demo: import/verify source metadata before automatic analysis.'})
    return {'version': 1, 'replays': str(replays), 'analysis': str(analysis),
            'items': list(items.values()), 'issues': issues,
            'counts': {'recordings': len(items), 'references': sum(len(i['references']) for i in items.values()),
                       'analysis_needed': sum(i['analysis_needed'] for i in items.values()),
                       'download_needed': sum(i['download_needed'] for i in items.values())}}


def provider_url(context):
    identity = context.get('id', '')
    if identity.startswith('faceit:'):return 'https://www.faceit.com/en/cs2/room/'+identity.split(':', 1)[1]
    if identity.startswith('hltv:'):return 'https://www.hltv.org/matches/'+identity.split(':', 1)[1]
    if context.get('url') and d.classify_link(context['url'])['kind'] == 'match':return context['url']
    raise ValueError('Missing demo has no verified acquisition URL/provider identity.')


def execute(plan, watch):
    if plan.get('version') != 1:raise ValueError('Unsupported analysis review plan.')
    replays, analysis = Path(plan['replays']).resolve(), Path(plan['analysis']).resolve()
    failures = list(plan.get('issues', []));d.ANALYSIS = analysis
    for index, item in enumerate(plan['items']):
        sha, hz, context = item['sha'], item['hz'], item['context']
        try:
            if item.get('blocked'):raise ValueError(item['blocked'])
            canonical = refs.find(analysis, sha, hz, schema=item.get('schema'))
            if canonical is None:
                if not item['analysis_needed']:raise ValueError('Previously valid analysis changed; preview again.')
                with d.library_lock(replays):
                    present = d.Library(replays).valid(sha)
                if not present:
                    if not item['download_needed']:raise ValueError('Demo disappeared since preview; preview again before downloading.')
                    # Reuse authenticated provider resolution/acquisition and its
                    # browser fallback. Never fetch a path or executable from a pointer.
                    resolved = d.Resolver().resolve(provider_url(context), count=1)
                    d.acquire_plan(resolved, replays, False, hz, method='auto', watch=watch)
                with d.library_lock(replays):
                    library = d.Library(replays)
                    if not library.valid(sha):raise ValueError('Acquisition did not restore the expected demo hash; reference preserved.')
                    destination = item.get('destination')
                    if destination:destination = refs.safe(analysis, destination)
                    errors = d.analyze(library, [sha], hz=str(hz), contexts={sha: context},
                                       destinations={sha: destination} if destination else None)
                    if errors:raise ValueError('Analysis failed; existing data and reference preserved.')
                canonical = refs.find(analysis, sha, hz, schema=item.get('schema'))
                if canonical is None:raise ValueError('No validated analysis was published.')
            for folder in item['references']:
                with exclusive(STATE/'analysis-maintenance.lock'):
                    value = refs.reference(analysis, folder)
                    if value['demo_sha256'] != sha:raise ValueError('Reference changed since review.')
                    with exclusive(lock_path(canonical)), exclusive(lock_path(Path(folder))):
                        refs.write(analysis, folder, canonical, sha, value.get('context') or context, value.get('map'), hz)
            print(f'Analysis verified: {sha} -> {canonical}', flush=True)
        except (OSError, ValueError, RuntimeError) as exc:
            failures.append({'sha': sha, 'reason': str(exc)});print(f'ERROR: {sha}: {exc}', flush=True)
        d.progress('Analyze all', index+1, len(plan['items']), f'{index+1}/{len(plan["items"])} recordings checked')
    result = {'recordings': len(plan['items']), 'unresolved': failures}
    save_json(STATE/'analysis-all-result.json', result)
    return 1 if failures else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--preview', type=Path);mode.add_argument('--execute', type=Path)
    parser.add_argument('--replays', type=Path, default=d.DEFAULT_REPLAYS)
    parser.add_argument('--analysis', type=Path, default=d.ANALYSIS)
    parser.add_argument('--watch', type=Path, default=Path.home()/'Downloads')
    args = parser.parse_args()
    if args.preview:
        value = preview(args.replays, args.analysis);save_json(args.preview, value)
        print(json.dumps(value['counts']), flush=True);return 0
    return execute(refs.read(args.execute), args.watch)


if __name__ == '__main__':
    raise SystemExit(main())
