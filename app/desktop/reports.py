"""Build self-contained HTML heatmap/replay reports from existing analysis only."""
from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import html
import json
import mimetypes
import os
import re
import sys
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from jobs import ROOT, STATE, analysis_component, save_json
from cs2_jump import register_analysis

VIEWER = ROOT / 'app/modules/viewer2d'
sys.path.insert(0, str(VIEWER))
import replay
from heatmap import Heatmaps, identity, read_json, revision, rows, steam
from extractor.job_lock import exclusive

ANALYSIS = ROOT / 'data/analysis'
MAX_PAYLOAD = 256 * 1024 * 1024
CATALOG_VERSION = 3


def progress(phase, percent, detail):
    print('TOOLBOX_PROGRESS ' + json.dumps(dict(phase=phase, percent=round(percent,1), detail=detail)), flush=True)


def team_key(name):
    return 'recorded-team:' + hashlib.sha256(name.casefold().encode()).hexdigest()[:20]


def saved_contexts():
    """Recover older league imports from saved provider facts, without requests.

    Hash links are preferred. A legacy naming link requires the complete canonical
    demo name AND the two recorded clan names to match those saved provider facts.
    """
    from downloads import DEFAULT_REPLAYS, INDEX_NAME, filename
    by_hash, by_name = defaultdict(list), defaultdict(list)
    settings = read_json(STATE/'settings.json')
    location = settings.get('download_root') or str(DEFAULT_REPLAYS)
    try:
        library = read_json(Path(location)/INDEX_NAME)
    except (OSError,ValueError,TypeError):
        library = {}
    matches = list(library.get('matches',{}).values())
    try:
        matches += read_json(STATE/'download-plan.json').get('matches',[])
    except (OSError,ValueError,TypeError):
        pass
    for match in matches:
        for digest in match.get('files',[]):by_hash[digest].append(match)
        for item in match.get('maps',[]):
            try:by_name[analysis_component(Path(filename(match,item)).stem,220)].append(match)
            except (ValueError,KeyError,TypeError):pass
    return by_hash,by_name


def team_binding(folder, summary, context, player_rows, round_rows):
    """Use verified IDs when supplied; otherwise link exact recorded clan labels.

    This fallback is restricted to organized competition. It never guesses which
    PUG lineups constitute a persistent team, or merges historical team aliases.
    """
    info, _ = identity(folder, summary)
    if info and info['mode'] == 'team':
        return info
    competition = (summary.get('demo_source_family') == 'tournament_sourcetv' or
                   context.get('collection_kind') == 'team')
    if not competition:
        return None
    canonical = {r['round']: r for r in round_rows}
    clans, membership = {}, {}
    for p in player_rows:
        if not steam(p.get('steamid')):
            continue
        rnd = canonical.get(p.get('round'), {})
        side = p.get('side')
        name = rnd.get('ct_team_clan_name' if side == 'CT' else 't_team_clan_name' if side in ('T', 'TERRORIST') else '')
        if not name or name.casefold() in ('ct', 't', 'terrorists', 'counter-terrorists'):
            return None
        key = team_key(name)
        if p['steamid'] in membership and membership[p['steamid']] != key:
            return None
        clans[key], membership[p['steamid']] = name, key
    if len(clans) != 2 or not membership:
        return None
    # When saved league metadata identifies the selected organization, retain its
    # provider ID, while unnamed-ID opponents remain exact recorded-name groups.
    owner = context.get('owner')
    owner_key = team_key(owner) if isinstance(owner,str) else None
    if context.get('selected_team_id') and owner_key in clans:
        provider_key = context.get('source','provider')+':team:'+context['selected_team_id']
        clans[provider_key] = clans.pop(owner_key)
        membership = {sid:provider_key if tid==owner_key else tid for sid,tid in membership.items()}
    selected, opponent = sorted(clans)
    return dict(mode='team', tracked=None, bundle='team:' + selected, teams=clans,
                membership=membership, selected_team=selected, opponent=opponent,
                recorded_names=True)


def scan(analysis=ANALYSIS, notify=progress):
    analysis = Path(analysis).resolve()
    entries, skipped = [], []
    by_hash,by_name = saved_contexts()
    paths = sorted(analysis.rglob('viewer_tracks_meta.json'))
    for i, path in enumerate(paths):
        folder = path.parent
        if not folder.resolve().is_relative_to(analysis):
            continue
        source = folder.relative_to(analysis).as_posix()
        try:
            summary = read_json(folder/'match_summary.json')
            integrity = read_json(folder/'integrity_checks.json')
            meta = read_json(path)
            caps = read_json(folder/'source_capabilities.json')
            provenance = read_json(folder/'analysis_source.json')
            context = provenance.get('context') or {}
            if summary.get('valid') is not True or summary.get('round_table_valid') is False or integrity.get('integrity_ok') is not True:
                raise ValueError('Analysis did not pass validity/integrity checks.')
            if not (folder/'viewer_tracks.csv.gz').is_file():
                raise ValueError('Movement data unavailable.')
            digest = meta.get('demo_sha256') or provenance.get('sha256')
            if not digest:
                raise ValueError('Demo identity unavailable.')
            player_rows, round_rows = list(rows(folder/'player_rounds.csv')), list(rows(folder/'rounds.csv'))
            if not context:
                recorded_clans = {r.get(k) for r in round_rows for k in ('ct_team_clan_name','t_team_clan_name')} - {None,''}
                candidates = by_hash.get(digest,[]) or by_name.get(folder.name.removeprefix('Analysis_'),[])
                candidates = [m for m in candidates if set(m.get('teams',[]))==recorded_clans]
                if len({m['id'] for m in candidates})==1:
                    context = dict(candidates[0])
                    if context.get('league_season'):context['collection_kind']='team'
            names = defaultdict(set)
            coverage = defaultdict(set)
            canonical = {r['round']:r for r in round_rows}
            for p in player_rows:
                if steam(p.get('steamid')):
                    names[p['steamid']].add(p.get('name') or p['steamid'])
                    rnd = canonical.get(p.get('round'), {})
                    try:
                        rid = 'completed-round:'+str(int(float(rnd['ct_score_before'])+float(rnd['t_score_before'])))
                    except (KeyError,ValueError,TypeError):
                        rid = digest+':'+(p.get('parser_round') or p.get('round',''))
                    coverage[p['steamid']].add(rid)
            if not names or not round_rows:
                raise ValueError('No recorded players/rounds.')
            map_name = summary.get('map_name') or read_json(folder/'header.json').get('map_name')
            if not (ROOT/'app/assets/maps'/f'{map_name}.png').is_file():
                raise ValueError('Map radar unavailable.')
            entries.append(dict(source=source, name=folder.name.removeprefix('Analysis_'), map=map_name,
                                sha=digest, game=(str(context['id']) + ':' + map_name) if context.get('id') else digest,
                                date=context.get('date', ''), players={k:sorted(v) for k,v in names.items()},
                                coverage={k:sorted(v) for k,v in coverage.items()},
                                team=team_binding(folder, summary, context, player_rows, round_rows),
                                rounds=len(round_rows), hz=meta.get('sample_hz', 0),
                                entities=(folder/'viewer_v8/entity_meta.json').is_file(),
                                heat_ready=(caps.get('event_streams',{}).get('player_death',{}).get('parsed') is True
                                            and (folder/'events/player_death.csv.gz').is_file()),
                                revision=list(revision(folder))))
        except (OSError, ValueError, TypeError, KeyError) as exc:
            skipped.append(dict(source=source, reason=str(exc)))
        if i % 25 == 0 or i + 1 == len(paths):
            notify('Finding report games', 100*(i+1)/max(1,len(paths)), f'{i+1}/{len(paths)} analyses')
    # A download's provider match ID also identifies older copies with that hash.
    linked = defaultdict(set)
    for e in entries:
        if e['game'] != e['sha']:
            linked[e['sha']].add(e['game'])
    for e in entries:
        if len(linked[e['sha']]) == 1:
            e['game'] = next(iter(linked[e['sha']]))
    # Keep the richest copy of each recording, retaining distinct split segments.
    best = {}
    for e in entries:
        old = best.get(e['sha'])
        if old is None or (e['heat_ready'], e['team'] is not None, e['entities'], e['rounds'], e['hz']) > (old['heat_ready'], old['team'] is not None, old['entities'], old['rounds'], old['hz']):
            best[e['sha']] = e
    entries = sorted(best.values(), key=lambda e:(e['date'],e['source']), reverse=True)
    targets = {}
    for e in entries:
        for sid, names in e['players'].items():
            t = targets.setdefault('player:'+sid, dict(id='player:'+sid, mode='player', name=names[0],
                                                     steamid=sid, aliases=[], games=[]))
            t['aliases'] = sorted(set(t['aliases']) | set(names))
            t['games'].append(e['source'])
        if e['team']:
            for tid, name in e['team']['teams'].items():
                key = 'team:'+tid
                t = targets.setdefault(key, dict(id=key, mode='team', name=name, team_id=tid, aliases=[name], games=[]))
                t['games'].append(e['source'])
    return dict(version=CATALOG_VERSION, analysis=str(analysis), entries=entries,
                targets=sorted(targets.values(), key=lambda t:(t['mode'],t['name'].casefold(),t['id'])), skipped=skipped)


def entry_identity(entry, target):
    if target['mode'] == 'player':
        sid = target['steamid']
        return dict(mode='player', tracked=sid, bundle='player:'+sid, teams={}, selected_team=None)
    info = dict(entry['team'])
    info.update(selected_team=target['team_id'], bundle=target['id'],
                opponent=next(t for t in info['teams'] if t != target['team_id']))
    return info


def report_context(entries, target):
    players, opponents, games = {}, {}, {}
    for e in entries:
        info = entry_identity(e, target)
        games.setdefault(e['game'], dict(source=e['source'], game=e['game'], name=e['name']))
        if target['mode'] == 'team':
            o = opponents.setdefault(info['opponent'], dict(id=info['opponent'], name=info['teams'][info['opponent']], keys=set()))
            o['keys'].add(e['game'])
        for sid, names in e['players'].items():
            if target['mode'] == 'player' and sid != target['steamid']:
                continue
            team = info.get('membership', {}).get(sid)
            p = players.setdefault(sid, dict(id=sid, names=set(), group='Team A' if team==info['selected_team'] else 'Opponents', coverage={}))
            p['names'].update(names)
            c = p['coverage'].setdefault(e['game'],dict(ids=set(), opponent=info.get('opponent')))
            c['ids'].update(e['coverage'][sid])
    for p in players.values():
        p['coverage'] = {key:dict(rounds=len(c['ids']),opponent=c['opponent']) for key,c in p['coverage'].items()}
    return dict(available=True, mode=target['mode'], tracked=target.get('steamid'), map=entries[0]['map'],
                teamName=target['name'], games=list(games.values()),
                opponents=[dict(id=o['id'], name=o['name'], games=len(o['keys'])) for o in opponents.values()],
                players=[dict(**p, games=len(p['coverage']), rounds=sum(c['rounds'] for c in p['coverage'].values()))
                         | {'names':sorted(p['names'])} for p in players.values()])


def packed(value):
    raw = json.dumps(value, separators=(',', ':'), allow_nan=False).encode()
    return base64.b64encode(gzip.compress(raw, mtime=0)).decode('ascii')


def js_json(value):
    return json.dumps(value, separators=(',', ':'), ensure_ascii=True, allow_nan=False).replace('<', '\\u003c')


def bundle_page(manifest, movement, packets, assets):
    helpers = []
    for name in ('engine.mjs','geometry.mjs','shots.mjs','heatmap-ui.js'):
        source = (VIEWER/name).read_text(encoding='utf-8')
        exports = re.findall(r'export (?:const|function|class) (\w+)', source)
        helpers.append('const {'+','.join(exports)+'}=(()=>{\n'+source.replace('export ', '')+
                       '\nreturn {'+','.join(exports)+'};})();\n')
    worker = (VIEWER/'portable-heatmap.mjs').read_text(encoding='utf-8').replace('export ', '')
    worker += '\ninstallWorker('+js_json(manifest)+','+js_json(movement)+');'
    provider = (VIEWER/'portable-report.js').read_text(encoding='utf-8')
    script = ('const reportManifest='+js_json(manifest)+';\nconst reportPackets='+js_json(packets)+
              ';\nconst reportAssets='+js_json(assets)+';\nconst reportWorker='+js_json(worker)+';\n'+
              provider+'\n'+''.join(helpers)+'\n'+
              re.sub(r'^import .*;\r?\n', '', (VIEWER/'viewer.js').read_text(encoding='utf-8'), flags=re.M))
    page = (VIEWER/'index.html').read_text(encoding='utf-8')
    page = page.replace('<link rel="stylesheet" href="viewer.css">', '<style>'+ (VIEWER/'viewer.css').read_text(encoding='utf-8')+'</style>')
    page, n = re.subn(r'<script type="module" src="viewer.js\?v=\d+"></script>', lambda _: '<script>'+script.replace('</script','<\\/script')+'</script>', page)
    if n != 1:
        raise ValueError('Viewer template changed; report integration must be updated.')
    page = page.replace('<title>CS2 · Round viewer</title>', '<title>'+html.escape(manifest['title'])+'</title>')
    # Additional portable navigation; the normal local viewer is unaffected.
    heading = '<div class="aside-heading"><span class="eyebrow">MATCH LIBRARY</span>'
    page = page.replace(heading, '<div class="aside-heading"><span class="eyebrow">'+html.escape(manifest['title'])+
                        '</span><label>Map <select id="report-map" aria-label="Report map"></select></label>'+
                        '<small>Offline report · '+str(len(manifest['games']))+' recordings · '+
                        str(sum(len(g['rounds']) for g in manifest['games']))+' rounds</small>'+
                        '<button id="watch-cs2" type="button" disabled>Watch in CS2 · Preview</button>'+
                        '<small id="watch-cs2-status" role="status">Enable CS2 report links in Toolbox → Tools &amp; setup once on this PC. The original demo is required.</small></div>'+heading)
    return page


def build(request, catalog=None, notify=progress):
    catalog = catalog or scan(notify=notify)
    if catalog.get('version') != CATALOG_VERSION:
        raise ValueError('Refresh analyzed games before building this report.')
    target = next((t for t in catalog['targets'] if t['id']==request.get('target')), None)
    selected = request.get('sources')
    if not target or not isinstance(selected,list) or not selected or not set(selected) <= set(target['games']):
        raise ValueError('Choose a team/player and at least one of their available games. Refresh the library if it changed.')
    entries = [e for e in catalog['entries'] if e['source'] in set(selected)]
    if len(entries) != len(set(selected)):
        raise ValueError('Some selected analysis folders are no longer available. Refresh the library.')
    if not any(e['heat_ready'] for e in entries):
        raise ValueError('These games have replay data but lack validated death-stream metadata for heatmaps. Choose games marked Ready, or analyze those demos again first.')
    output = Path(request.get('output', '')).expanduser().absolute()
    if output.suffix.lower() != '.html':
        raise ValueError('Choose an .html report filename.')
    if output.resolve().is_relative_to(Path(catalog['analysis']).resolve()):
        raise ValueError('Save reports outside the analysis library.')
    if output.exists() and request.get('replace_stamp') != [output.stat().st_size, output.stat().st_mtime_ns]:
        raise ValueError('The output already exists or changed since it was selected. Choose the save location again.')
    calibration = read_json(ROOT/'app/assets/maps/map-data.json')
    service = Heatmaps(catalog['analysis'], calibration)
    old_analysis = replay.ANALYSIS
    replay.ANALYSIS = Path(catalog['analysis'])
    replay.read_match.cache_clear()
    packets, movement, games, payload_size = {}, {}, [], 0
    try:
        for index, entry in enumerate(entries):
            source = entry['source']
            folder = service.safe(source)
            if list(revision(folder)) != [tuple(r) for r in entry['revision']]:
                raise ValueError('Analysis changed since selection: '+source)
            working = {**entry, 'identity':entry_identity(entry,target)}
            notify('Preparing movement',95*index/len(entries),f'{index+1}/{len(entries)} recordings · {entry["map"].removeprefix("de_")}')
            prepared = service.prepare(working)
            # Heat controls end at 120s. Retain a boundary sample for clipping.
            for rnd in prepared['rounds']:
                for p in rnd['players']:
                    track, limit = p['track'], rnd['start']+120*prepared['rate']
                    end = next((i+1 for i,point in enumerate(track) if point[0]>limit), len(track))
                    p['track'] = track[:end]
            movement[source] = packed(prepared)
            payload_size += len(movement[source])
            game = dict(source=source, game=entry['game'], name=entry['name'], map=entry['map'],
                        opponent=working['identity'].get('opponent'), rounds=[], sha=entry['sha'],
                        nativeWatch=register_analysis(folder,entry['sha']))
            packets[source] = {}
            canonical = list(rows(folder/'rounds.csv'))
            for j, row in enumerate(canonical):
                number = int(float(row['round']))
                notify('Building HTML report', 95*(index+(j/max(1,len(canonical))))/len(entries),
                       f'{index+1}/{len(entries)} recordings · round {number} · {entry["map"].removeprefix("de_")}')
                packet = replay.build_replay(source, number)
                packet['provenance'] = dict(demoSha256=entry['sha'], reportTarget=target['id'])
                packets[source][str(number)] = packed(packet)
                payload_size += len(packets[source][str(number)])
                if payload_size > MAX_PAYLOAD:
                    raise ValueError('This selection exceeds the 256 MB offline report limit. Select fewer games or one map and build separate reports.')
                game['rounds'].append(number)
            games.append(game)
            replay.read_match.cache_clear()
        maps = sorted({e['map'] for e in entries})
        contexts = {m:report_context([e for e in entries if e['map']==m], target) for m in maps}
        manifest = dict(version=1,title=target['name']+' · Heatmap report',
                        target={k:v for k,v in target.items() if k not in ('games','aliases')}, games=games,
                        contexts=contexts, created=datetime.now(timezone.utc).isoformat(),
                        identityNote='Teams without provider IDs are grouped by exact recorded clan names; renamed teams remain separate.')
        assets = {}
        paths = list((ROOT/'app/assets/weapons').glob('*.svg'))
        for m in maps:
            paths += [ROOT/'app/assets/maps'/f'{m}.png']
            lower = ROOT/'app/assets/maps'/f'{m}_lower.png'
            if lower.is_file(): paths.append(lower)
        for path in paths:
            mime = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
            assets[path.relative_to(ROOT/'app/assets').as_posix()] = 'data:'+mime+';base64,'+base64.b64encode(path.read_bytes()).decode()
        notify('Saving HTML report',97,f'{len(games)} recordings · {len(maps)} maps')
        page = bundle_page(manifest,movement,packets,assets)
        output.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=output.parent,prefix='.'+output.stem+'-',suffix='.part',delete=False) as f:
            stage = Path(f.name)
            f.write(page.encode('utf-8'))
        try:
            if output.exists() and request.get('replace_stamp') != [output.stat().st_size,output.stat().st_mtime_ns]:
                raise ValueError('The chosen output changed while the report was building.')
            os.replace(stage,output)
        finally:
            stage.unlink(missing_ok=True)
        notify('Report ready',100,str(output))
        return dict(output=str(output), recordings=len(games), games=len({g['game'] for g in games}),
                    rounds=sum(len(g['rounds']) for g in games), bytes=output.stat().st_size)
    finally:
        replay.read_match.cache_clear()
        replay.ANALYSIS = old_analysis
        service.executor.shutdown(wait=False,cancel_futures=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action',required=True)
    sub.add_parser('catalog').add_argument('--output',type=Path,required=True)
    sub.add_parser('build').add_argument('--request',type=Path,required=True)
    args = parser.parse_args()
    # Serialize against extraction and directory repairs, preserving a coherent snapshot.
    with exclusive(STATE/'analysis-maintenance.lock'):
        if args.action == 'catalog':
            catalog=scan()
            save_json(args.output,catalog)
            print(f"Found {len(catalog['targets'])} teams/players and {len(catalog['entries'])} recordings; {len(catalog['skipped'])} unavailable analyses.",flush=True)
        else:
            request=read_json(args.request)
            catalog=read_json(STATE/'report-catalog.json')
            print(json.dumps(build(request,catalog)),flush=True)


if __name__ == '__main__':
    try:
        main()
    except (ValueError,OSError,RuntimeError) as exc:
        print('ERROR: '+str(exc),flush=True)
        raise SystemExit(1)
