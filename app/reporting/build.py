"""Build a portable coaching report from a frozen evidence snapshot and reviewed copy."""
from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import mimetypes
import os
import re
import sys
import tempfile
from collections import Counter
from pathlib import Path

from analyze import ROOT, VERSION, read_json, safe_folder, toolbox_reports
from desk import render as render_desk
from situation_insights import render as render_situations, desk as situation_desk
from themes import evidence as theme_evidence


def escape(value):
    return html.escape(str(value), quote=True)


def json_script(value):
    return json.dumps(value, ensure_ascii=True, allow_nan=False).replace('<', '\\u003c')


def verify(snapshot):
    if snapshot.get('version') != VERSION:
        raise ValueError('Unsupported evidence snapshot version.')
    games = snapshot['games']
    if not 1 <= len(games) <= 50 or len({g['sha'] for g in games}) != len(games) or len({g['game'] for g in games}) != len(games):
        raise ValueError('Expected 1–50 unique games.')
    for game in games:
        folder = safe_folder(snapshot['analysis'], game['source'])
        for file, digest in game['inputs'].items():
            path = (folder / file).resolve()
            if not path.is_relative_to(folder) or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError('Evidence input changed: ' + game['source'] + '/' + file)


def opening_summary(snapshot):
    sid = snapshot['target']['steamid']
    opening = [r for g in snapshot['games'] for r in g['rounds'] if r['opening'] == 'kill']
    counts = Counter()
    for rnd in opening:
        first = next(e for e in rnd['events'] if e['enemy'])
        if first['attacker'] != sid:
            raise ValueError('Opening-kill identity mismatch.')
        gap = (rnd['death']['tick']-first['tick'])/rnd['tickrate'] if rnd['death'] else None
        key = 'within2' if gap is not None and gap <= 2 else 'twoToTen' if gap is not None and gap <= 10 else 'later' if gap is not None else 'survived'
        counts[key] += 1
    return dict(total=len(opening), **{k:counts[k] for k in ('within2','twoToTen','later','survived')})


def selected_cases(snapshot, coaching):
    if snapshot['target']['steamid'] != coaching['steamid']:
        raise ValueError('Reviewed coaching belongs to a different player.')
    records = {r['id']:r for g in snapshot['games'] for r in g['rounds']}
    cases = []
    if not coaching.get('cases'):
        raise ValueError('Reviewed coaching requires representative evidence.')
    for copy in coaching['cases']:
        rnd = records.get(copy['round_id'])
        if not rnd or rnd['opening'] != 'kill':
            raise ValueError('Reviewed round is outside eligible opening-kill evidence.')
        cases.append(dict(copy, record=rnd))
    return cases


def bundle_evidence(snapshot, cases):
    """Reuse the established Toolbox renderer and portable bundler, in memory only."""
    replay = toolbox_reports.replay
    previous_analysis = replay.ANALYSIS
    replay.ANALYSIS = Path(snapshot['analysis'])
    replay.read_match.cache_clear()
    grouped = {}
    for case in cases:
        r = case['record']
        grouped.setdefault(r['source'], []).append(r)
    packets, games, fingerprints = {}, [], {}
    try:
        for source, rounds in grouped.items():
            folder = safe_folder(snapshot['analysis'], source)
            inputs = sorted(p for p in folder.rglob('*') if p.is_file() and (p.suffix in ('.json','.csv','.gz') or p.name.endswith('.json.gz')))
            before = {p.relative_to(folder).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
            entries = {r['round']:r for r in rounds}
            packets[source] = {}
            for rnd in entries.values():
                packet = replay.build_replay(source, rnd['round'])
                packet['rounds'] = [r for r in packet['rounds'] if r['round'] in entries]
                packet['provenance'] = dict(demoSha256=rnd['sha'], reportTarget='player:'+snapshot['target']['steamid'])
                packets[source][str(rnd['round'])] = toolbox_reports.packed(packet)
            after = {p.relative_to(folder).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
            if before != after:
                raise ValueError('Replay inputs changed while building: '+source)
            fingerprints[source] = before
            first = rounds[0]
            games.append(dict(source=source, game=first['sha'], sha=first['sha'],
                              name=first['map'].removeprefix('de_').title()+' · '+first['date'],
                              map=first['map'], rounds=sorted(entries), nativeWatch=False))
            replay.read_match.cache_clear()
        maps = sorted({r['record']['map'] for r in cases})
        assets = {}
        paths = list((ROOT/'app/assets/weapons').glob('*.svg'))
        for map_name in maps:
            paths.append(ROOT/'app/assets/maps'/f'{map_name}.png')
            lower = ROOT/'app/assets/maps'/f'{map_name}_lower.png'
            if lower.exists():
                paths.append(lower)
        for p in paths:
            mime = mimetypes.guess_type(p.name)[0] or 'application/octet-stream'
            assets[p.relative_to(ROOT/'app/assets').as_posix()] = 'data:'+mime+';base64,'+base64.b64encode(p.read_bytes()).decode()
        manifest = dict(version=1, title='Coaching evidence · '+snapshot['target']['name'],
                        target={'mode':'player','steamid':snapshot['target']['steamid']}, games=games,
                        contexts={m:dict(available=False,reason='This evidence view contains selected rounds, not a batch heat map.') for m in maps})
        page = toolbox_reports.bundle_page(manifest, {}, packets, assets)
        # Adapt the exported copy only; never edit the Tool Developer's renderer.
        page = page.replace('</head>', '<style>.heatmap-panel,#watch-cs2,#watch-cs2-status{display:none!important}</style></head>')
        render_entry = 'function render() {\n  ctx.clearRect'
        if render_entry not in page:
            raise ValueError('Viewer rendering contract changed; update the report adapter.')
        # Closing the modal temporarily gives the embedded canvas zero bounds.
        page = page.replace(render_entry, 'function render() {\n  if(width<=100||height<=40)return;\n  ctx.clearRect')
        bridge = '''
window.addEventListener('message',async event=>{
  if(event.source!==parent)return;
  if(event.data?.type==='coaching-pause'){setPlaying(false);return;}
  if(event.data?.type!=='coaching-seek')return;
  const item=event.data;
  if(!reportManifest.games.some(g=>g.source===item.source&&g.rounds.includes(item.round)))return;
  await loadRound(item.source,item.round);
  if(replay?.source!==item.source||replay?.round!==item.round)return;
  setPlaying(false);seek(item.tick);follow=null;zoom=1;pan=[0,0];
  parent.postMessage({type:'coaching-loaded',round:replay.round,tick},'*');
});
requestAnimationFrame(animate);boot().then(()=>{
  heatmap.enabled=false;heatmap.root.hidden=true;
  parent.postMessage({type:'coaching-ready'},'*');
});'''
        if 'requestAnimationFrame(animate);boot();' not in page:
            raise ValueError('Viewer boot contract changed; update the report adapter.')
        page = page.replace('requestAnimationFrame(animate);boot();', bridge)
        return page, fingerprints
    finally:
        replay.read_match.cache_clear()
        replay.ANALYSIS = previous_analysis


def render(snapshot, coaching, cases, viewer):
    summary = opening_summary(snapshot)
    themes = theme_evidence(snapshot)
    games = snapshot['games']
    total = snapshot['totals']
    excluded = sum(len(g['excluded_rounds']) for g in games)
    date_min, date_max = min(g['date'] for g in games), max(g['date'] for g in games)
    fmt = lambda value: __import__('datetime').date.fromisoformat(value).strftime('%b %d, %Y')
    digest = hashlib.sha256(json.dumps(snapshot,sort_keys=True).encode()).hexdigest()
    desk_html, measures = render_desk(snapshot, summary, cases)
    positive_situations, development_situations, reviewed_situations = render_situations(snapshot, coaching)
    desk_html = desk_html.replace('</div></details>', situation_desk(snapshot,coaching)+'</div></details>')
    payload = dict(player=snapshot['target'], summary=summary, cases=cases,
                   games=[dict({k:v for k,v in g.items() if k!='rounds'},eligible_rounds=len(g['rounds'])) for g in games],
                   totals=total, excluded=excluded, digest=digest, practice=coaching['practice'], measures=measures,
                   situation_insights=reviewed_situations, situation_review=coaching.get('situation_review'), theme_evidence=themes,
                   theme_review=coaching.get('theme_review'))
    segments = [('within2','Within 2s','immediate'),('twoToTen','Over 2s to 10s','soon'),('later','Death after 10s','later'),('survived','Survived the round','survived')]
    chart = ''.join(f'<div class="bar-segment {cls}" style="width:{summary[key]/summary["total"]*100 if summary["total"] else 0}%" title="{label}: {summary[key]}"><b>{summary[key]}</b></div>' for key,label,cls in segments)
    legend = ''.join(f'<li><i class="dot {cls}"></i><span>{label}</span><b>{summary[key]}</b></li>' for key,label,cls in segments)
    tabs = ''.join(f'<button role="tab" id="case-tab-{i}" aria-selected="{str(i==0).lower()}" aria-controls="case-panel" tabindex="{0 if i==0 else -1}" data-case="{i}"><span>0{i+1}</span>{escape(c["label"])}</button>' for i,c in enumerate(cases))
    by_map = Counter(g['map'] for g in games)
    scope = ''.join(f'<tr><td>{escape(m.removeprefix("de_").title())}</td><td>{n}</td><td>{total["maps"][m]}</td></tr>' for m,n in sorted(by_map.items()))
    # The complete teaching narrative is server-rendered: reading requires no tabs or scripts.
    reading_cases = []
    for index, case in sorted(enumerate(cases), key=lambda item: (item[1]['record']['death'] is not None, not item[1]['record']['win'], item[0])):
        rnd = case['record']
        first = next(e for e in rnd['events'] if e['enemy'])
        if rnd['death']:
            gap = (rnd['death']['tick']-first['tick'])/rnd['tickrate']
            ending = f'<strong>{escape("v".join(map(str,rnd["death"]["after"])))}</strong><span>Your death · +{gap:.2f}s</span>'
        else:
            ending = '<strong>Alive</strong><span>You survive the round</span>'
        badge = 'Opening + survival' if not rnd['death'] else 'Compare the context'
        reading_cases.append(
            f'<article class="reading-case" data-reading-case="{index}">'
            f'<div class="reading-case-copy"><div class="case-kicker"><span>{badge}</span><span>{escape(rnd["map"].removeprefix("de_").title())} · R{rnd["round"]} · {rnd["side"]} · {rnd["date"]}</span></div>'
            f'<h3>{escape(case["heading"])}</h3><p>{escape(case["observation"])}</p>'
            f'<p class="case-meaning">{escape(case["interpretation"])}</p>'
            f'<div class="reading-cue"><span>TAKE INTO YOUR NEXT MATCH</span><p>{escape(case["question"])}</p></div>'
            f'<p class="reading-limit">{escape(case["limit"])}</p></div>'
            f'<figure class="sequence"><figcaption>Recorded sequence <span>Round {"won" if rnd["win"] else "lost"}</span></figcaption>'
            f'<div><strong>{escape("v".join(map(str,first["before"])))}</strong><span>Before the opening kill</span></div>'
            f'<div><strong>{escape("v".join(map(str,first["after"])))}</strong><span>Your opening kill · {first["seconds"]:.2f}s</span></div>'
            f'<div>{ending}</div></figure></article>')
    opening_games = len({r['sha'] for g in games for r in g['rounds'] if r['opening']=='kill'})
    represented = ' · '.join(f'{m.removeprefix("de_").title()} {n}' for m,n in by_map.most_common(3))
    capitals = re.findall(r'[A-Z]',snapshot['target']['name'])
    initials = capitals[0]+capitals[-1] if len(capitals)>1 else snapshot['target']['name'][:2].upper()
    text = (Path(__file__).with_name('template.html')).read_text(encoding='utf-8')
    # Specific situations live only in the deeper evidence view. The primary
    # reading path synthesizes recurrence across the selected map pool.
    start = text.index(' <details class="evidence-tools">')
    end = text.index('\n</section>',start)
    tools = text[start:end].replace('@@TABS@@',tabs)
    text = text[:start]+text[end:]
    map_rows = ''.join(f'<tr><td>{escape(m.removeprefix("de_").title())}</td><td>{v["openings"]}</td><td>{v["within10"]}</td><td>{v["within2"]}</td></tr>' for m,v in sorted(themes['by_map'].items()))
    theme_desk = '<h3>Cross-map recurrence behind the primary focus</h3><p>These counts show where the recorded transition occurs. They do not establish a common cause, a benchmark or avoidable deaths; map samples are uneven.</p><table><thead><tr><th>Map</th><th>Own opening kills</th><th>Own death within 10s</th><th>Within 2s</th></tr></thead><tbody>'+map_rows+'</tbody></table>'
    desk_html = desk_html.replace('</div></details>', theme_desk+'<h3>Optional individual examples</h3><p>Examples illustrate the questions and limits; they are not the basis for a cross-map diagnosis.</p><div class="reading-cases">'+''.join(reading_cases)+'</div>'+tools+'</div></details>')
    replacements = dict(TITLE=escape(coaching['title']), NAME=escape(snapshot['target']['name']), STEAMID=escape(snapshot['target']['steamid']),
                        INTRO=escape(coaching['intro']), STATUS=escape(coaching['status']), BOUNDARY=escape(coaching['boundary']),
                        GAMES=str(len(games)), ROUNDS=f'{total["rounds"]:,}', EXCLUDED=str(excluded), MAP_COUNT=str(len(by_map)),
                        DATE_RANGE=escape(fmt(date_min)+' — '+fmt(date_max)), OPENINGS=str(summary['total']),
                        FAST=str(summary['within2']+summary['twoToTen']), IMMEDIATE=str(summary['within2']),
                        CHART=chart, LEGEND=legend, TABS=tabs, SCOPE=scope, READING_CASES=''.join(reading_cases), ANALYST_DESK=desk_html,
                        SURVIVED=str(summary['survived']), OPENING_GAMES=str(opening_games), REPRESENTED_MAPS=escape(represented),
                        INITIALS=escape(initials),
                        OPENING_MAPS=str(themes['opening_maps']), FAST_GAMES=str(themes['fast_games']), FAST_MAPS=str(themes['fast_maps']), IMMEDIATE_MAPS=str(themes['immediate_maps']),
                        POSITIVE_SITUATION=positive_situations, DEVELOPMENT_SITUATION=development_situations,
                        PRACTICE_BEFORE=escape(coaching['practice']['before']), PRACTICE_AFTER=escape(coaching['practice']['after']),
                        PRACTICE_REVIEW=escape(coaching['practice']['review']), PRACTICE_SUCCESS=escape(coaching['practice']['success']),
                        PAYLOAD=json_script(payload), VIEWER=json_script(viewer),
                        CSS=Path(__file__).with_name('report.css').read_text(encoding='utf-8')+'\n'+Path(__file__).with_name('presentation.css').read_text(encoding='utf-8'),
                        JS=Path(__file__).with_name('report.js').read_text(encoding='utf-8'))
    for key, value in replacements.items():
        text = text.replace('@@'+key+'@@', value)
    return text, payload


def build(evidence_path, coaching_path, output, replace=False):
    snapshot, coaching = read_json(evidence_path), read_json(coaching_path)
    output = Path(output).resolve()
    if output.suffix.lower() != '.html' or output.is_relative_to(Path(snapshot['analysis']).resolve()) or output.resolve() in (Path(evidence_path).resolve(),Path(coaching_path).resolve()):
        raise ValueError('Choose an HTML output outside the analysis library and input files.')
    if output.exists() and not replace:
        raise ValueError('Output already exists; pass --replace to replace this generated report.')
    stamp = (output.stat().st_size, output.stat().st_mtime_ns) if output.exists() else None
    verify(snapshot)
    cases = selected_cases(snapshot, coaching)
    viewer, fingerprints = bundle_evidence(snapshot, cases)
    page, payload = render(snapshot, coaching, cases, viewer)
    verify(snapshot)
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = None
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent, prefix='.'+output.stem+'-',suffix='.part',delete=False) as f:
            stage = Path(f.name)
            f.write(page.encode('utf-8'))
        current = (output.stat().st_size, output.stat().st_mtime_ns) if output.exists() else None
        if current != stamp:
            raise ValueError('Output changed during the build; preserving the newer file.')
        os.replace(stage, output)
    finally:
        if stage:
            stage.unlink(missing_ok=True)
    record = dict(report_sha256=hashlib.sha256(output.read_bytes()).hexdigest(), evidence_digest=payload['digest'],
                  analysis_sha256=hashlib.sha256(Path(evidence_path).read_bytes()).hexdigest(),
                  coaching_sha256=hashlib.sha256(Path(coaching_path).read_bytes()).hexdigest(),
                  builder_version=VERSION, player=snapshot['target'], selection=snapshot['selection'],
                  replay_inputs=fingerprints, summary=payload['summary'], bytes=output.stat().st_size)
    output.with_suffix('.build.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    return record


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--analysis', type=Path, required=True)
    p.add_argument('--coaching', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--replace', action='store_true')
    args = p.parse_args()
    result = build(args.analysis, args.coaching, args.output, args.replace)
    print(json.dumps({k:result[k] for k in ('summary','bytes','report_sha256')}))


if __name__ == '__main__':
    main()
