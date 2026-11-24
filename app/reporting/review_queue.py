"""Build an exploratory comparison queue, never automatic coaching judgments."""
from __future__ import annotations

import argparse
import html
import json
from collections import defaultdict
from pathlib import Path

from intake import sha


def matching_key(entry):
    context = entry['context']
    # Raw site IDs have no validated identity across games. Bomb phase matters
    # for last-alive options; never match a planted objective to a preplant one.
    if entry['question'] == 'postplant':
        state = context['state_at_plant']
        site = context.get('plant_site_id_recorded')
        if site is None:
            return None
        return (entry['game'], entry['map'], entry['side'], str(site), state['own'], state['enemy'])
    if entry['question'] == 'lastalive':
        phase = context.get('bomb_planted_at_entry')
        if not isinstance(phase, bool):
            return None
        return (entry['game'], entry['map'], entry['side'], context['entry_enemy_count'], phase)
    return None


def build(index):
    groups = defaultdict(list)
    for entry in index['candidates']:
        if entry['state'] != 'eligible_interpretation_unresolved' or entry['question'] == 'flash':
            continue
        key = matching_key(entry)
        if key is not None:
            groups[(entry['question'], key)].append(entry)
    cards = []
    per_question = defaultdict(int)
    for (question, key), entries in sorted(groups.items(), key=lambda x: (-len(x[1]), str(x[0]))):
        if len(entries) < 2 or per_question[question] >= 2:
            continue
        # Choose by the situation question and source order, without filtering
        # wins, losses, deaths or recorded contact. Outcomes remain context.
        selected = entries[:2]
        cards.append(dict(id='comparison:' + str(len(cards)+1), question=question,
                          purpose='Review choices in partially matched situations; outcomes do not select or rate examples',
                          matched_context=list(key), candidate_ids=[e['id'] for e in selected],
                          round_ids=[e['round_id'] for e in selected],
                          team_round_outcomes=[e['team_round_win'] for e in selected],
                          evidence_sequences=[dict(candidate_id=e['id'], round_id=e['round_id'],
                              entry_tick=e.get('entry_tick'), tickrate=e.get('tickrate'),
                              start_context=e['context'], observed_sequence=e.get('observed_sequence',[]))
                              for e in selected],
                          source_context_limits={e['id']: e['context'].get('interpretation_unresolved', []) for e in selected},
                          not_matched=['Health/equipment', 'Actual clock and feasible objective timing',
                                       'Known information', 'Routes, sightlines and response access'],
                          status='unreviewed', review=dict(
                              recognizable_future_situation=None,
                              observed_choice_and_source_anchors=None,
                              information_available_to_player=None,
                              feasible_alternative_and_constraints=None,
                              supported_positive_example=None,
                              disconfirming_evidence=None,
                              practice_cue=None,
                              observable_followup_behavior=None,
                              remaining_unknowns=None)))
        per_question[question] += 1
    return dict(version=1, session_id=index['session_id'],
                readiness_sha256=index['readiness_sha256'],
                interpretation='Situation-first exploratory review only. Outcome is not decision quality.',
                selection_policy='Group by the decision question and available starting context, order groups by opportunity count, retain source order, choose two per group with at most two groups per question. No outcome/contact/death filtering. This is exploration, not representative inference.',
                population_policy='Full candidate populations remain in the review index; this small queue is not a rate denominator or a representative sample.',
                promotion_gate='Reviewed choices, available information, feasible alternatives, supporting/disconfirming evidence and a teachable future situation are required before any coaching edit.',
                comparisons=cards)


def markdown(queue):
    lines = ['# Situation review queue', '', queue['interpretation'], '', queue['population_policy'], '',
             'Matched raw site IDs are restricted to the same game. Bomb phase is matched for last-alive episodes. Health, equipment, clock, available information and feasible access still need review.', '']
    for card in queue['comparisons']:
        lines += [f'## {card["question"]}: {card["id"]}', '',
                  f'Review `{card["round_ids"][0]}` and `{card["round_ids"][1]}`. Outcomes were not used to select them.', '',
                  'Status: unreviewed. Neither round is a certified positive or negative example.', '']
    lines += ['## Before a player-facing lesson', '',
              'Record the recognizable future situation, observed choice, information available to the player and a feasible alternative. Review supporting positive and disconfirming evidence. Then specify one practice cue and what fresh, comparable behavior would indicate progress.', '',
              'Flash contact overlaps remain descriptive records. Shared damage/death source rows must be deduplicated across flashes; neither an overlap nor its absence establishes flash effectiveness.', '']
    return '\n'.join(lines)


def worksheet(queue):
    """Read-only review worksheet: observed events and unknowns, no coaching labels."""
    esc = lambda value:html.escape(str(value))
    parts = ['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Coaching evidence review</title>',
             '<style>body{font:17px/1.55 system-ui;margin:0;background:#f3f2ef;color:#20262d}main{max-width:1060px;margin:auto;padding:32px}article{background:white;border:1px solid #c4c9cf;padding:24px;margin:24px 0}h1,h2{line-height:1.2}table{border-collapse:collapse;width:100%;font-size:15px}th,td{text-align:left;vertical-align:top;padding:8px;border-bottom:1px solid #dce0e4}code{overflow-wrap:anywhere}aside{padding:16px;background:#eef1f5}summary{font-weight:bold}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.5 monospace}@media print{body{background:white}article{break-before:page}main{padding:0}}@media(max-width:600px){main{padding:12px}article{padding:12px}table{font-size:13px}}</style><main>',
             '<h1>Coaching evidence review</h1><p>Internal worksheet · recorded facts · interpretation pending</p>',
             '<p>'+esc(queue['interpretation'])+'</p><p>'+esc(queue['population_policy'])+'</p>',
             '<aside>Read each sequence before judging its outcome. Available information, actual clock, equipment and feasible alternatives remain to be established. Recorded positions do not prove player knowledge. Event times below are elapsed since episode entry, not the player’s remaining clock.</aside>']
    for card in queue['comparisons']:
        parts.append('<article><h2>'+esc(card['question'])+' · '+esc(card['id'])+'</h2>')
        for sequence in card['evidence_sequences']:
            parts.append('<h3>'+esc(sequence['round_id'])+'</h3><p>Entry tick '+esc(sequence['entry_tick'])+' · '+esc(sequence['tickrate'])+' ticks/second</p>')
            context = sequence['start_context']
            state = context.get('state_at_plant') or context.get('entry_state') or {}
            parts.append('<p>Recorded start: '+esc(state.get('own','unknown'))+' teammates including the player versus '+esc(state.get('enemy','unknown'))+' opponents.</p>')
            parts.append('<ul>'+''.join('<li>'+esc(s)+'</li>' for s in context.get('interpretation_unresolved',[]))+'</ul>')
            parts.append('<table><thead><tr><th>After entry</th><th>Recorded action</th><th>Anchor</th></tr></thead><tbody>')
            for event in sequence['observed_sequence']:
                action = event['kind']+' · '+str(event.get('actor') or 'unknown')
                if event.get('affected'):action += ' → '+str(event['affected'])
                if event.get('detail'):action += ' · '+str(event['detail'])
                if event['same_tick_order_unresolved']:action += ' · within-tick order unresolved'
                parts.append('<tr><td>'+esc(f"{event['seconds_after_entry']:.2f}s")+'</td><td>'+esc(action)+'</td><td><code>'+esc(json.dumps(event['anchor']))+'</code></td></tr>')
            parts.append('</tbody></table>')
        parts.append('<h3>Review before a lesson</h3><p>What could reasonably be known? What options were feasible? Which observed choice was useful, and what evidence challenges that interpretation? What should the player recognize next time?</p><p>No positive/negative rating, practice cue or identity has been assigned.</p></article>')
    parts.append('</main></html>')
    return ''.join(parts)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = build(json.loads(Path(args.index).read_text(encoding='utf-8')))
    result['review_index_sha256'] = sha(args.index)
    output = Path(args.output)
    output.write_text(json.dumps(result, indent=2, allow_nan=False), encoding='utf-8')
    output.with_suffix('.md').write_text(markdown(result), encoding='utf-8')
    output.with_suffix('.html').write_text(worksheet(result), encoding='utf-8')
    print(json.dumps(dict(output=str(output), comparisons=len(result['comparisons']))))
