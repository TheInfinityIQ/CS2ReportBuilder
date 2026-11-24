"""Cross-map recurrence of recorded observations, without causal classification."""


def evidence(snapshot):
    maps, opening_games, fast_games, fast_maps, immediate_maps = {}, set(), set(), set(), set()
    for game in snapshot['games']:
        row = maps.setdefault(game['map'],dict(openings=0,within10=0,within2=0))
        for rnd in game['rounds']:
            if rnd['opening'] != 'kill':
                continue
            row['openings'] += 1
            opening_games.add(game['sha'])
            first = next(e for e in rnd['events'] if e['enemy'])
            gap = (rnd['death']['tick']-first['tick'])/rnd['tickrate'] if rnd['death'] else None
            if gap is not None and gap <= 10:
                row['within10'] += 1
                fast_games.add(game['sha']); fast_maps.add(game['map'])
            if gap is not None and gap <= 2:
                row['within2'] += 1; immediate_maps.add(game['map'])
    return dict(version='1.0',unit='recorded opening-kill round',by_map=maps,
                opening_games=len(opening_games),opening_maps=sum(r['openings']>0 for r in maps.values()),
                fast_games=len(fast_games),fast_maps=len(fast_maps),immediate_maps=len(immediate_maps),
                interpretation='Recurrence of a recorded transition, not a validated shared cause or decision-quality rating')
