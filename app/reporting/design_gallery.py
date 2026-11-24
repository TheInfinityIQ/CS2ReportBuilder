"""Render an offline gallery of coaching report design prototypes."""

import argparse
import base64
import re
from html import escape
from pathlib import Path

from single_match_preview import REVIEWS, load_preview_matches, match_evidence

CONCEPTS = {
    'broadcast': ('Broadcast Brief', 'A match graphic up front, then a compact coaching read.'),
    'journal': ('Coach’s Journal', 'An editorial page with room for the coach’s reasoning.'),
    'tactical': ('Tactical Board', 'A map-led briefing with a focused reading column.'),
    'console': ('Analyst Console', 'Match facts at a glance, with a compact grid for the coaching.'),
    'film': ('Demo Debrief', 'A horizontal round strip gives the match a sense of sequence.'),
    'practice': ('Practice Card', 'A short, printable handout for the next session.'),
}

REFERENCES = [
    ('FACEIT Advanced Stats', 'https://support.faceit.com/hc/en-us/articles/19309126922140-FACEIT-CS2-Advanced-Stats',
     'The match page and scoreboard provide a familiar entry point. Broadcast Brief and Analyst Console use that quick orientation.'),
    ('Leetify', 'https://leetify.com/',
     'A short post-match observation can lead into a fuller report. Coach’s Journal and Practice Card put a single takeaway near the top.'),
    ('SCOPE.GG Match and Replay Guide', 'https://scope.gg/methodology/',
     'Match summaries and round-level investigation have different levels of detail. Tactical Board and Demo Debrief put that distinction into the layout.'),
]


def page(title, css, body, classes=''):
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title><style>{css}</style></head><body class="{classes}">{body}</body></html>'''


def map_label(game):
    return game['map'].removeprefix('de_').title()


def map_image(game):
    asset = Path(__file__).resolve().parents[1] / 'assets' / 'maps' / (game['map'] + '.png')
    encoded = base64.b64encode(asset.read_bytes()).decode('ascii')
    return f'<img class="radar" width="512" height="512" src="data:image/png;base64,{encoded}" alt="">'


def score(game):
    # The last recorded round exposes side scores. Match identity provides the
    # player-team ordering, including a possible excluded round earlier on.
    match = re.search(r'\[(\d+)-vs-(\d+)\]', game['source'])
    last = game['rounds'][-1]
    if not match:
        raise ValueError('Missing canonical match score.')
    own, opponent = map(int, match.groups())
    previous = sorted(last['score_before'])
    final = sorted([own, opponent])
    if sorted([previous[0] + 1, previous[1]]) != final and sorted([previous[0], previous[1] + 1]) != final:
        raise ValueError('Score differs from the final recorded round.')
    return own, opponent


def evidence_table(columns, rows):
    header = ''.join(f'<th scope="col">{escape(value)}</th>' for value in columns)
    lines = []
    for *cells, won in rows:
        values = [*cells, 'Win' if won else 'Loss']
        lines.append('<tr>'+''.join(f'<td>{escape(str(value))}</td>' for value in values)+'</tr>')
    return '<div class="scroll" tabindex="0" aria-label="Round evidence table"><table><thead><tr>'+header+'</tr></thead><tbody>'+''.join(lines)+'</tbody></table></div>'


def round_strip(game):
    by_number = {int(r['round']): r['win'] for r in game['rounds']}
    gaps = {int(r['round']) for r in game['excluded_rounds']}
    numbers = sorted(by_number.keys() | gaps)
    markers = []
    for number in numbers:
        label = 'Excluded' if number in gaps else 'Win' if by_number[number] else 'Loss'
        markers.append(f'<span class="{label.lower()}" title="Round {number}: {label}">{label[0]}</span>')
    return '<figure class="strip"><figcaption>Round results <small>W win · L loss · E excluded</small></figcaption><div>'+''.join(markers)+'</div></figure>'


def review(key, game, facts, player, style):
    title, positive, observation, cue, limit = REVIEWS[key]
    scope, columns, rows = match_evidence(game, facts, player)
    own, opponent = score(game)
    map_name = escape(map_label(game))
    name = escape(player['name'])
    context = f'{name} · {escape(game["date"])} · {map_name}'
    counts = f'{len(game["rounds"])} reviewed rounds'
    if game['excluded_rounds']:
        counts += f' · {len(game["excluded_rounds"])} excluded'
    result = 'Won' if own > opponent else 'Lost' if own < opponent else 'Draw'
    return f'''<article id="{key}" class="review">
<header class="hero">
  <div class="hero-copy"><p class="eyebrow">{context}</p><h1>{escape(title)}</h1></div>
  <div class="match-score"><p>Match result · {result}</p><strong>{own}<span>–</span>{opponent}</strong><small>{counts}</small></div>
  {map_image(game) if style in ('broadcast','tactical') else ''}
</header>
{round_strip(game) if style == 'film' else ''}
<div class="brief">
  <section class="keep"><h2>What to keep</h2><p>{escape(positive)}</p></section>
  <section class="finding"><h2>What this match showed</h2><p>{escape(observation)}</p></section>
  <section class="cue"><h2>What to try next</h2><p>{escape(cue)}</p></section>
  <p class="limit">{escape(limit)}</p>
</div>
<details class="desk"><summary>Analyst Desk</summary><p>{escape(scope)}</p>{evidence_table(columns,rows)}</details>
</article>'''


def gallery(css, output):
    items = []
    for key, (title, description) in CONCEPTS.items():
        thumbnail = key + '.web-preview.jpg'
        preview = (f'<img src="{thumbnail}" width="360" height="214" alt="">'
                   if (output / thumbnail).is_file()
                   else '<div class="sample" aria-hidden="true"><span>CANADIANIQ / MIRAGE</span><strong>Plan for the<br>second opponent</strong><b>13–10</b></div>')
        items.append(f'''<a class="tile {key}" href="{key}.html">
{preview}
<div class="caption"><h2>{title}</h2><p>{description}</p></div></a>''')
    sources = ''.join(f'<li>{escape(note)} <a href="{url}">{escape(title)}</a></li>' for title,url,note in REFERENCES)
    return page('CS2 Coaching Report Design Gallery',css,f'''<main class="gallery-main">
<header><p class="eyebrow">CS2 COACHING</p><h1>Report design gallery</h1>
<p>Six ways to present the same three match reviews. Open any direction to see how it handles Mirage, Inferno and Dust2.</p></header>
<div class="tiles">{''.join(items)}</div>
<section class="references"><h2>What informed these designs</h2><ul>{sources}</ul></section></main>''','gallery')


def build(analysis, readiness, output):
    games, facts, player = load_preview_matches(analysis, readiness)
    css = Path(__file__).with_suffix('.css').read_text(encoding='utf-8')
    output.mkdir(parents=True, exist_ok=True)
    for style, (title, _) in CONCEPTS.items():
        matches = ''.join(f'<a href="#{key}">{escape(map_label(games[key]))}</a>' for key in REVIEWS)
        cards = ''.join(review(key,games[key],facts[key],player,style) for key in REVIEWS)
        nav = f'''<header class="bar"><a href="index.html">← Design gallery</a>
<span>{title}</span><nav aria-label="Match reviews">{matches}</nav></header>'''
        (output / (style+'.html')).write_text(page(title,css,nav+'<main>'+cards+'</main>',style),encoding='utf-8')
    (output/'index.html').write_text(gallery(css,output),encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('analysis','readiness','output'):
        parser.add_argument('--'+flag,type=Path,required=True)
    args = parser.parse_args()
    build(args.analysis,args.readiness,args.output)
