"""Supporting evidence for the report, using its existing computed observations."""
import html
import json
from collections import Counter


def records(snapshot, opening):
    rounds = [r for g in snapshot['games'] for r in g['rounds']]
    definitions = [
        ('games','Selected games',len(snapshot['games']),None,'Unique selected complete games for this player.'),
        ('rounds','Eligible rounds',len(rounds),None,'Complete, reconciled rounds with a usable death sequence.'),
        ('omitted','Omitted rounds',sum(len(g['excluded_rounds']) for g in snapshot['games']),None,'Withheld from report calculations; source records are retained.'),
        ('opening_kills','Own opening kills',opening['total'],len(rounds),'First opposing-team kill credited to this player; ambiguous first death ticks excluded.'),
        ('opening_games','Games containing an own opening kill',len({r['sha'] for r in rounds if r['opening']=='kill'}),len(snapshot['games']),'Unique selected games containing at least one eligible own opening kill.'),
        ('within2','Death within 2 seconds',opening['within2'],opening['total'],'Own death tick minus own opening-kill tick, divided by match tick rate; interval <=2 seconds.'),
        ('twoToTen','Death over 2 to 10 seconds',opening['twoToTen'],opening['total'],'The same interval, >2 and <=10 seconds.'),
        ('later','Later death',opening['later'],opening['total'],'Own death >10 seconds after own opening kill, before recorded round end.'),
        ('survived','Survived the round',opening['survived'],opening['total'],'No own death in the eligible opening-kill round; not a decision-quality judgment.'),
    ]
    return [dict(id=k,label=label,value=value,denominator=denom,definition=definition,
                 version='1.0',kind='deterministic derivation',unit='count',
                 inputs=['rounds.csv','player_rounds.csv','events/player_death.csv.gz'],
                 scope='Selected games and eligible rounds for Steam ID '+snapshot['target']['steamid'])
            for k,label,value,denom,definition in definitions]


def render(snapshot, opening, cases):
    esc = lambda v: html.escape(str(v),quote=True)
    measures = records(snapshot, opening)
    table = ''.join(f'<tr data-measure="{m["id"]}"><td><strong>{esc(m["label"])}</strong><br><span>{esc(m["definition"])}</span></td><td>{m["value"]:,}</td><td>{m["denominator"] if m["denominator"] is not None else "—"}</td></tr>' for m in measures)
    contexts = []
    rounds = [r for g in snapshot['games'] for r in g['rounds']]
    for dimension in ('map','side'):
        for key in sorted({r[dimension] for r in rounds}):
            subset = [r for r in rounds if r[dimension]==key]
            contexts.append(f'<tr><td>{esc(dimension.title())}</td><td>{esc(key.removeprefix("de_"))}</td><td>{len(subset)}</td><td>{sum(r["opening"]=="kill" for r in subset)}</td></tr>')
    limits = ''.join(f'<article><h4>{esc(c["record"]["map"].removeprefix("de_").title())} · Round {c["record"]["round"]}</h4><p>{esc(c["limit"])}</p><code>{esc(c["record"]["id"])}</code></article>' for c in cases)
    warnings = Counter(str(w.get('code','unspecified')) for g in snapshot['games'] for w in g.get('warnings',[]))
    warning_text = '; '.join(f'{esc(code)}: {n}' for code,n in sorted(warnings.items())) or 'No recorded integrity warnings in the selected games.'
    content = f'''<details class="analyst-desk" id="analyst-desk"><summary>Analyst Desk · inspect the evidence behind the coaching</summary><div class="desk-body">
<p>The player report teaches the decision. This desk records the supporting observations, definitions and limits; these figures do not diagnose intent, awareness or decision quality.</p>
<h3>Figures used in this report</h3><div class="table-scroll"><table><thead><tr><th>Observation and definition</th><th>Count</th><th>Eligible denominator</th></tr></thead><tbody>{table}</tbody></table></div>
<h3>Context represented in the sample</h3><table><thead><tr><th>Dimension</th><th>Context</th><th>Eligible rounds</th><th>Own opening kills</th></tr></thead><tbody>{''.join(contexts)}</tbody></table>
<h3>Interpretation boundaries for the selected situations</h3><div class="desk-limits">{limits}</div>
<h3>Source quality and remaining questions</h3><p>Recorded warning counts: {warning_text}</p><p>Source warnings and omitted rounds remain inspectable in the game list above. Tick intervals are not reaction times. Sampled facing and approximate spotted state are not verified angle clearing or player knowledge. Voice calls and tactical intent remain unresolved.</p>
<p>Future review asks whether the player's next exposure fits available information and the objective. A change in the quick-death count alone cannot answer that question.</p><p class="small">Measure definitions v1.0 · canonical player IDs remain strings · previous sessions preserve their original definitions.</p>
</div></details>'''
    return content, measures
