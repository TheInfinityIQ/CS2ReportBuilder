"""Small recorded HUD companion; reuses player identities and match markers."""
import math
from pathlib import Path
if __package__:
    from .backend import read,save
    from .stock_assets import canonical
else:
    from backend import read,save
    from stock_assets import canonical

def number(value,default=None):
    try:return int(value) if math.isfinite(float(value)) else default
    except (TypeError,ValueError):return default

def text(value,fallback=''):
    return fallback if value is None or str(value).lower()=='nan' or not str(value).strip() else str(value)

def flag(value):
    return value is True or text(value).lower() in {'true','1','1.0'}

def prepare_hud(parser,meta,folder,progress):
    identity=[1,meta['sha256'],meta['parser']]
    path=Path(folder)/'hud.json';cached=read(path,{})
    if cached.get('identity')==identity:return cached
    progress('hud',87,'Preparing recorded scores, round phases and kill-feed details once…')
    names=['round_start','round_freeze_end','round_end','player_death','bomb_planted','bomb_defused','bomb_exploded']
    tables=parser.parse_events(names,other=['team_rounds_total','total_rounds_played','is_warmup_period','team_clan_name'],player=['team_num'])
    start=min((int(r['tick']) for r in meta['rounds']),default=0)
    events=[];kills=[]
    for kind,table in tables:
        for row in table.to_dict('records'):
            tick=number(row.get('tick'),-1)
            if tick<start or tick>meta['info']['ticks'] or flag(row.get('is_warmup_period')):continue
            winner=text(row.get('winner')).upper()
            if kind=='round_end' and winner not in {'2','3','2.0','3.0','T','CT','TERRORIST','COUNTERTERRORIST'}:continue
            played=number(row.get('total_rounds_played'))
            event={'tick':tick,'kind':kind,'round':max(1,played if kind=='round_end' else played+1) if played is not None else None,
                   'ct_score':number(row.get('ct_team_rounds_total')),'t_score':number(row.get('t_team_rounds_total')),
                   'ct_name':text(row.get('ct_team_clan_name'),'CT'),'t_name':text(row.get('t_team_clan_name'),'T')}
            events.append(event)
            if kind=='player_death':
                kills.append({'tick':tick,'attacker':text(row.get('attacker_name'),'World'),'victim':text(row.get('user_name'),'Player'),
                              'attacker_id':text(row.get('attacker_steamid')),'victim_id':text(row.get('user_steamid')),
                              'attacker_team':number(row.get('attacker_team_num'),0),'victim_team':number(row.get('user_team_num'),0),
                              'weapon':canonical(text(row.get('weapon'))),'headshot':flag(row.get('headshot')),
                              'smoke':flag(row.get('thrusmoke')),'wallbang':number(row.get('penetrated'),0)>0,
                              'noscope':flag(row.get('noscope'))})
    events.sort(key=lambda e:(e['tick'],names.index(e['kind'])))
    kills.sort(key=lambda e:e['tick'])
    result={'identity':identity,'events':events,'kills':kills,'match_start':start,'clock':'elapsed_since_recorded_phase'}
    save(path,result);return result
