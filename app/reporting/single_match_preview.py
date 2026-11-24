"""Build three independent, read-only coaching previews from frozen match evidence."""

import argparse
import gzip
import json
from html import escape
from pathlib import Path

from build import opening_summary
from intake import sha


REVIEWS = {
    '53b3a125d08d': (
        'Plan for the second opponent',
        'You created three 5v4s on T side. You survived one of those rounds.',
        'Two openings from Apartments were followed by your death to a second opponent from Back Alley within 1.5 seconds. The team won one of those rounds and lost the other.',
        'Before taking the first fight from Apartments, decide who is watching Back Alley and where you will move if that approach is open. Use the information your team actually has.',
        'This is a repeat on one route in this match. The timing leaves little room to improvise after the kill, and the demo leaves teammate calls and available sightlines unresolved.',
    ),
    '070575f17bbe': (
        'Give the numbers advantage a job',
        'After the plant, you increased the numbers lead in one situation and eliminated the last defender in two others. Those are three distinct contributions in this match.',
        'Your team won all five reviewed T-side post-plants where you were alive and ahead in numbers at the plant. One still went to the bomb timer after you died and the teams drew level.',
        'As the plant finishes with a numbers lead, pick your job: watch a retake route, stay able to respond to a teammate, or play the bomb timer. Check that your position lets you do it.',
        'Team conversion describes the result of those five situations. The recorded events leave teammate coverage and the best position for each hold unresolved.',
    ),
    '1eea8b6cd6a0': (
        'Update the plan when the bomb goes down',
        'Twice as the last CT against three opponents, you found a kill after the plant and reduced the situation to 1v2.',
        'There were seven first last-alive situations against multiple opponents. In three CT situations, the bomb went down after you became last alive. The plant changed the objective while you were already outnumbered.',
        'When the plant goes down and the immediate fight allows, check the bomb timer, your route and your kit or utility before committing. Recheck after a kill if it changes what you can reach.',
        'The demo records the plant and the player counts. What you knew, your full resources at the decision and whether a retake or save was feasible remain unresolved.',
    ),
}


def match_evidence(game, facts, player):
    rounds = {row['id']: row for row in game['rounds']}
    if set(facts) != set(rounds) or any(
        row['sha256'] != game['sha'] or row['tracked_steamid'] != player['steamid']
        for row in facts.values()
    ):
        raise ValueError('Match facts do not match the selected eligible rounds and player.')
    key = game['sha'][:12]
    if key == '53b3a125d08d':
        summary = opening_summary(dict(target=player, games=[game]))
        rows = []
        for rnd in rounds.values():
            if rnd['opening'] != 'kill':
                continue
            first = next(event for event in rnd['events'] if event['enemy'])
            delay = (rnd['death']['tick'] - first['tick']) / rnd['tickrate'] if rnd['death'] else None
            rows.append((rnd['round'], first['attacker_place'], 'Survived' if delay is None else f'Died after {delay:.2f}s', rnd['win']))
        return f"{summary['total']} opening kills · {summary['within2']} deaths within two seconds", ('Round', 'Opening location', 'What followed', 'Team result'), rows
    if key == '070575f17bbe':
        rows = []
        for fact in facts.values():
            episode = fact['q1_postplant_advantage']
            if not episode['eligible']:
                continue
            state = episode['state_at_plant']
            rows.append((fact['round'], f"{state['own']}v{state['enemy']}", fact['round_reason'].replace('_', ' '), fact['team_round_win']))
        return f'{len(rows)} reviewed T post-plants with a numbers lead', ('Round', 'At plant', 'End condition', 'Team result'), rows
    rows = []
    for fact in facts.values():
        episode = fact['q2_last_alive']
        if episode is None:
            continue
        plant = episode['plant_tick']
        entry = episode['entry_tick']
        phase = 'Already planted' if episode['bomb_planted_at_entry'] else (
            f'Planted {(plant-entry)/fact["tickrate"]:.2f}s after entry' if plant and plant > entry else 'No later plant recorded')
        rows.append((fact['round'], fact['side'], f"1v{episode['entry_enemy_count']}", phase, fact['team_round_win']))
    return f'{len(rows)} first last-alive situations against multiple opponents', ('Round', 'Side', 'At entry', 'Bomb state', 'Team result'), rows


def card(game, facts, player):
    key = game['sha'][:12]
    title, positive, observation, cue, boundary = REVIEWS[key]
    scope, columns, rows = match_evidence(game, facts, player)
    headers = ''.join(f'<th scope="col">{escape(label)}</th>' for label in columns)
    rows = ''.join('<tr>'+''.join(f'<td>{escape(str(cell))}</td>' for cell in (*row[:-1], 'Win' if row[-1] else 'Loss'))+'</tr>' for row in rows)
    map_name = escape(game['map'].removeprefix('de_').title())
    return f'''<article id="{key}">
      <header><p class="meta">{map_name} · {escape(game['date'])}</p><h2>{escape(title)}</h2>
      <p class="meta">{escape(player['name'])} · {len(game['rounds'])} reviewed rounds · {len(game['excluded_rounds'])} excluded</p></header>
      <section><h3>What to keep</h3><p>{escape(positive)}</p></section>
      <section><h3>What this match showed</h3><p>{escape(observation)}</p></section>
      <section class="cue"><h3>What to try next</h3><p>{escape(cue)}</p></section>
      <p class="limit">{escape(boundary)}</p>
      <details><summary>Analyst Desk · {escape(scope)}</summary><div class="table"><table>
      <thead><tr>{headers}</tr></thead><tbody>{rows}</tbody></table></div>
      <p class="limit">Match reference <code>{key}</code></p></details>
    </article>'''


def load_preview_matches(analysis, readiness):
    snapshot = json.loads(analysis.read_text(encoding='utf-8'))
    manifest = json.loads(readiness.read_text(encoding='utf-8'))
    facts_name = 'round_facts.jsonl.gz'
    facts_path = readiness.with_name(facts_name)
    if (sha(analysis) != manifest['selection_sha256']
            or sha(facts_path) != manifest['artifacts'][facts_name]['sha256']):
        raise ValueError('Frozen analysis or handoff facts differ from the recorded hashes.')
    games = {game['sha'][:12]: game for game in snapshot['games'] if game['sha'][:12] in REVIEWS}
    selected_facts = {key: {} for key in REVIEWS}
    with gzip.open(facts_path,'rt',encoding='utf-8') as stream:
        for line in stream:
            row = json.loads(line)
            key = row['sha256'][:12]
            if key in selected_facts:
                selected_facts[key][row['round_id']] = row
    return games, selected_facts, snapshot['target']


def build(analysis, readiness):
    games, selected_facts, player = load_preview_matches(analysis, readiness)
    links = ''.join(f'<a href="#{key}">{escape(games[key]["map"].removeprefix("de_").title())}</a>' for key in REVIEWS)
    cards = ''.join(card(games[key], selected_facts[key], player) for key in REVIEWS)
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1"><title>CanadianIQ | One-game coaching previews</title>
    <style>
    *{{box-sizing:border-box}}body{{margin:0;background:#102029;color:#edf4f2;font:16px/1.6 system-ui,sans-serif}}
    main{{max-width:850px;margin:auto;padding:clamp(18px,5vw,48px)}}h1,h2,h3{{line-height:1.16;margin:0}}
    h1{{font-size:clamp(2rem,6vw,3.4rem)}}h2{{font-size:clamp(1.55rem,4vw,2.25rem)}}
    h3{{font-size:1rem;color:#aee8d3}}p{{margin:.55rem 0 0}}nav{{display:flex;flex-wrap:wrap;gap:12px;margin:22px 0}}
    a{{color:#b6f3db;text-underline-offset:.2em}}article{{margin:24px 0;padding:clamp(16px,4vw,32px);background:#182d38;border:1px solid #48616b;border-radius:12px}}
    .meta,.limit{{color:#c2d3d7;font-size:.9rem}}article header .meta:first-child{{margin:0 0 6px}}
    section,article>.limit,details{{margin-top:18px}}.cue{{background:#203d42;border-left:3px solid #aee8d3;padding:14px}}
    summary{{cursor:pointer;color:#b6f3db}}.table{{overflow:auto}}table{{width:100%;border-collapse:collapse;margin-top:12px}}
    th,td{{text-align:left;padding:8px;border-bottom:1px solid #48616b}}@media print{{body,article,.cue{{background:white;color:#182d38}}
    h3,.meta,.limit,a,summary{{color:#203d42}}article{{break-inside:avoid}}nav{{display:none}}}}
    </style></head><body><main><h1>One-game coaching reviews</h1>
    <p>Three previews for CanadianIQ. Each review uses only the events and situations from the match it names.</p>
    <nav aria-label="Choose a match">{links}</nav>{cards}</main></body></html>'''


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('analysis','readiness','output'):
        parser.add_argument('--'+flag,type=Path,required=True)
    args = parser.parse_args()
    args.output.write_text(build(args.analysis,args.readiness),encoding='utf-8')
