"""Verify a Toolbox handoff and index unreviewed coaching opportunities."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import zipfile
from pathlib import Path


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def observed_sequence(row, start):
    """Recorded actions after entry; same-tick ordering is deliberately unknown."""
    events = []
    for number, event in enumerate(row['death_sequence']):
        if start <= event['tick'] <= row['end_tick']:
            events.append(dict(tick=event['tick'], kind='death',
                               actor=event.get('attacker_name') or event['attacker'],
                               affected=event.get('victim_name') or event['victim'],
                               detail=event.get('weapon'),
                               anchor=dict(round_id=row['round_id'], death_sequence_index=number)))
    for event in row['objective_events']:
        tick = float(event['tick'])
        if start <= tick <= row['end_tick']:
            events.append(dict(tick=tick, kind=Path(event['source']['file']).name.replace('.csv.gz',''),
                               actor=event.get('user_steamid'), affected=None, detail=None,
                               anchor=event['source']))
    events.sort(key=lambda e:e['tick'])
    for event in events:
        event['seconds_after_entry'] = (event['tick'] - start) / row['tickrate']
        event['same_tick_order_unresolved'] = sum(e['tick']==event['tick'] for e in events)>1
    return events


def prepare(readiness, session):
    readiness, session = Path(readiness), Path(session)
    manifest = json.loads(readiness.read_text(encoding='utf-8'))
    with zipfile.ZipFile(session) as archive:
        frozen = json.loads(archive.read('manifest.json'))
        session_info = json.loads(archive.read('session.json'))
    if manifest['target']['steamid'] != frozen['player']['steamid']:
        raise ValueError('Player identity differs from the coaching session.')
    if manifest['selection_sha256'] != frozen['files']['evidence/analysis.json']['sha256']:
        raise ValueError('Selected evidence differs from the coaching session.')
    games = {g['source']: g for g in frozen['games']}
    if set(games) != set(manifest['source_membership_hashes']):
        raise ValueError('Selected analysis folders differ from the coaching session.')
    for source, inventory in manifest['source_membership_hashes'].items():
        prefix = games[source]['archive_path'] + '/'
        expected = {n[len(prefix):]: v['sha256'] for n, v in frozen['files'].items()
                    if n.startswith(prefix)}
        if expected != {n: v['sha256'] for n, v in inventory.items()}:
            raise ValueError('Source revision differs from the coaching session: ' + source)
    data = {}
    for name, item in manifest['artifacts'].items():
        if name not in ('round_facts.jsonl.gz', 'flash_facts.jsonl.gz', 'blind_facts.jsonl.gz'):
            raise ValueError('Unsupported handoff artifact: ' + name)
        path = readiness.parent / name
        if path.stat().st_size != item['bytes'] or sha(path) != item['sha256']:
            raise ValueError('Handoff checksum differs: ' + name)
        with gzip.open(path, 'rt', encoding='utf-8') as stream:
            rows = [json.loads(line) for line in stream]
        if len(rows) != item['rows']:
            raise ValueError('Handoff row count differs: ' + name)
        data[name] = rows
    rounds = data['round_facts.jsonl.gz']
    flashes = data['flash_facts.jsonl.gz']
    by_round = {r['round_id']: r for r in rounds}
    if len(by_round) != len(rounds) or len({f['flash_id'] for f in flashes}) != len(flashes):
        raise ValueError('Duplicate situation identity in handoff.')
    if any(r['source'] not in games or r['game'] != games[r['source']]['game_id'] for r in rounds):
        raise ValueError('Round source/game identity differs.')
    entries = []
    for row in rounds:
        base = dict(round_id=row['round_id'], game=row['game'], source=row['source'],
                    map=row['map'], side=row['side'], team_round_win=row['team_round_win'],
                    state='eligible_interpretation_unresolved',
                    facts_artifact='round_facts.jsonl.gz')
        q1 = row.get('q1_postplant_advantage')
        if q1 and q1['eligible']:
            entries.append(dict(base, id=row['round_id'] + ':postplant', question='postplant',
                                context=q1, tickrate=row['tickrate'], entry_tick=q1['plant_tick'],
                                observed_sequence=observed_sequence(row,q1['plant_tick'])))
        q2 = row.get('q2_last_alive')
        if q2:
            entries.append(dict(base, id=row['round_id'] + ':lastalive', question='lastalive',
                                context=q2, tickrate=row['tickrate'], entry_tick=q2['entry_tick'],
                                observed_sequence=observed_sequence(row,q2['entry_tick'])))
    distinct_contacts = set()
    overlap_links = 0
    unresolved_order_links = 0
    for row in flashes:
        if row['source'] not in games or row['game'] != games[row['source']]['game_id']:
            raise ValueError('Flash source/game identity differs.')
        rid = row['round_id']
        if row['within_eligible_live_round'] and rid not in by_round:
            raise ValueError('Live flash has no eligible round.')
        contacts = []
        for overlap in row['temporal_teammate_overlaps']:
            effect = next((b for b in row['blind_effects']
                           if b['source']['csv_data_row'] == overlap['blind_csv_data_row']), None)
            if effect is None or effect['user_steamid'] != overlap['event']['user_steamid']:
                raise ValueError('Flash/contact opponent identity differs.')
            source_event = overlap['event']['source']
            event_id = (row['game'], source_event['file'], source_event['csv_data_row'])
            distinct_contacts.add(event_id)
            overlap_links += 1
            unresolved_order_links += bool(overlap['same_tick_order_unresolved'])
            contacts.append(dict(game=event_id[0], file=event_id[1], csv_data_row=event_id[2],
                                 same_tick_order_unresolved=overlap['same_tick_order_unresolved']))
        entries.append(dict(id=row['flash_id'], question='flash', round_id=rid,
                            source=row['source'], game=row['game'],
                            state=('eligible_interpretation_unresolved' if row['within_eligible_live_round']
                                   else 'ineligible'), facts_artifact='flash_facts.jsonl.gz',
                            detonation=row['detonation']['source'],
                            recorded_blind_events=len(row['blind_effects']),
                            recorded_temporal_overlaps=len(row['temporal_teammate_overlaps']),
                            contact_event_references=contacts,
                            missing_context=['No causal benefit established',
                                             'No continuous effective visual impairment established',
                                             'No overlap does not establish an ineffective flash']))
    counts = manifest['counts']
    actual = dict(q1_eligible=sum(e['question']=='postplant' for e in entries),
                  q2_episodes=sum(e['question']=='lastalive' for e in entries),
                  q3_attributable_detonations_all=len(flashes), rounds=len(rounds))
    if any(counts[k] != v for k, v in actual.items()):
        raise ValueError('Candidate populations differ from declared handoff counts.')
    return dict(version=1, session_id=session_info['id'], readiness_sha256=sha(readiness),
                contract_sha256=sha(Path(__file__).with_name('coaching_data_contract.json')),
                status='Evidence intake only; player-facing interpretation requires situation review',
                checks=dict(artifact_hashes=True, row_counts=True, unique_ids=True,
                            source_revisions_match_frozen_session=True),
                counts=counts, candidates=entries,
                overlap_accounting=dict(link_count=overlap_links,
                                        distinct_recorded_contact_events=len(distinct_contacts),
                                        same_tick_order_unresolved_links=unresolved_order_links,
                                        definition='Deduplicate by game/file/CSV data row; damage and death records remain distinct event types, not unique fights or assists'),
                editorial_gate=['Identify a future situation the player can recognize',
                                'Show a supported choice and feasible alternative',
                                'Review positive and disconfirming situations with comparable context',
                                'Retain unresolved context and avoid outcome-based judgments'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--readiness', required=True)
    parser.add_argument('--session', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = prepare(args.readiness, args.session)
    Path(args.output).write_text(json.dumps(result, indent=2, allow_nan=False), encoding='utf-8')
    print(json.dumps(dict(output=args.output, checks=result['checks'], counts=result['counts'])))
