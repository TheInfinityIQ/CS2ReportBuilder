"""Read-only demo review navigation and user-owned saved moments."""
from __future__ import annotations
import csv
import gzip
import json
import math
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from jobs import ROOT, STATE, save_json
from extractor.job_lock import exclusive
import replay_inventory as replays

EVENTS = ('player_death', 'bomb_planted', 'bomb_defused', 'bomb_exploded')


def number(value):
    try:
        result=float(value)
        return result if math.isfinite(result) else None
    except (TypeError,ValueError):return None


def read_rows(path):
    if not path.is_file():return []
    with (gzip.open if path.suffix=='.gz' else open)(path,'rt',encoding='utf-8-sig',newline='') as stream:
        result=[]
        for row in csv.DictReader(stream):
            result.append(row)
            if len(result)>250000:raise ValueError('This event file exceeds the review limit.')
        return result


def library(path=STATE/'report-catalog.json', *, replay_root=None, cache=None):
    from jobs import read_json
    data=read_json(path,{})
    entries=data.get('entries',[]) if isinstance(data,dict) and data.get('version')==3 else []
    root=(ROOT/'data/analysis').resolve()
    analyzed={}
    for entry in entries:
        if not isinstance(entry,dict) or not isinstance(entry.get('source'),str) or not entry.get('sha'):continue
        folder=(root/entry['source']).resolve()
        if folder.is_relative_to(root) and (folder/'viewer_tracks_meta.json').is_file():
            analyzed.setdefault(entry['sha'],{**entry,'folder':folder})
    result={}
    for downloaded in replays.available(replay_root,cache=cache):
        sha=downloaded['sha']
        if sha in result:continue
        entry=analyzed.get(sha,{})
        metadata=downloaded['metadata'];relative=downloaded['relative'];name=downloaded['path'].stem
        date_match=re.search(r'_([A-Za-z]{3}-\d{2}-\d{4})_',name)
        date=entry.get('date') or ''
        if not date and date_match:
            try:date=datetime.strptime(date_match[1],'%b-%d-%Y').date().isoformat()
            except ValueError:pass
        map_name=entry.get('map') or metadata.get('map') or (relative.split('/')[0] if '/' in relative else '')
        if not map_name and date_match:
            tail=name[date_match.end():];parts=tail.split('_')
            map_name='_'.join(parts[:2]) if parts[0]=='de' and len(parts)>1 else parts[0]
        map_name=str(map_name or 'unknown').casefold()
        if not map_name.startswith('de_'):map_name='de_'+map_name
        title=name.replace('_',' ')
        result[sha]={**entry,'sha':sha,'source':entry.get('source') or 'download:'+sha,
            'game':entry.get('game') or sha,'folder':entry.get('folder'),'players':entry.get('players',{}),
            'demo_path':downloaded['path'],'file_stamp':downloaded['file_stamp'],'map':map_name,'date':date,
            'title':title,'search':' '.join([title,relative,entry.get('name',''),entry.get('source',''),date,
                *entry.get('players',{}),*[n for names in entry.get('players',{}).values() for n in names],
                *(entry.get('team') or {}).get('teams',{}).values()]).casefold()}
    return sorted(result.values(),key=lambda e:(e.get('date',''),e['title']),reverse=True)


def filter_library(entries,query='',map_name=None):
    terms=query.casefold().split()
    return [e for e in entries if (not map_name or e['map']==map_name) and all(t in e['search'] for t in terms)]


def analysis_stamp(entry):
    if not entry or not entry.get('folder'):return None
    try:
        value=(Path(entry['folder'])/'viewer_tracks_meta.json').stat()
        return value.st_mtime_ns,value.st_size
    except OSError:return None


def load_match(entry):
    folder=entry['folder'];meta=json.loads((folder/'viewer_tracks_meta.json').read_text(encoding='utf-8-sig'))
    if meta.get('demo_sha256')!=entry['sha']:raise ValueError('This analysis changed. Refresh the library before opening it.')
    rate=number(meta.get('tickrate'))
    if not rate or rate<=0:raise ValueError('The demo tick rate is missing.')
    rounds=[]
    for r in read_rows(folder/'rounds.csv'):
        start,freeze,end=[number(r.get(k)) for k in ('start_tick','freeze_end_tick','end_tick')]
        if None in (start,freeze,end) or end<=start:continue
        rounds.append(dict(number=int(float(r['round'])),start=int(start),freeze=int(max(start,min(end,freeze))),
                           end=int(end),ct=r.get('ct_team_clan_name') or 'CT',t=r.get('t_team_clan_name') or 'T',
                           score=f"{r.get('ct_score_before','?')}–{r.get('t_score_before','?')}",winner=r.get('winner',''),
                           complete=str(r.get('round_observation_complete','')).casefold()=='true'))
    rounds.sort(key=lambda r:r['start'])
    if not rounds:raise ValueError('This analysis has no usable round timeline.')
    events=[];missing=[]
    for kind in EVENTS:
        path=folder/'events'/f'{kind}.csv.gz'
        if not path.is_file():missing.append(kind);continue
        for index,row in enumerate(read_rows(path)):
            tick=number(row.get('tick'))
            if tick is None:continue
            rnd=next((r for r in rounds if r['start']<=tick<=r['end']),None)
            if not rnd:continue
            if kind=='player_death':
                description=f"{row.get('attacker_name') or 'World'} → {row.get('user_name') or 'Player'}"
                if row.get('weapon'):description+=' · '+row['weapon']
            else:description=kind.replace('_',' ').capitalize()
            events.append(dict(id=f'{kind}:{index}',kind=kind,tick=int(tick),round=rnd['number'],
                               text=description,players=[s for s in [row.get('user_steamid'),row.get('attacker_steamid'),row.get('assister_steamid')] if s]))
    events.sort(key=lambda e:(e['tick'],e['id']))
    # This extractor's demoparser event ticks are demo-relative. An explicit
    # imported server-tick schema may opt in; never infer origins from ranges.
    tick_space=meta.get('tick_space','demo')
    if tick_space not in ('demo','server'):raise ValueError('Unsupported analysis tick coordinate system.')
    return dict(rounds=rounds,events=events,rate=rate,missing=missing,tick_space=tick_space,
                start=rounds[0]['start'],end=max(r['end'] for r in rounds))


def event_target(match,event,lead=3):
    lead=number(lead)
    if lead is None or not 0<=lead<=30:raise ValueError('Choose between 0 and 30 seconds before the event.')
    rnd=next(r for r in match['rounds'] if r['number']==event['round'])
    return max(rnd['start'],int(event['tick']-lead*match['rate']))


def event_filter(events,round_number=None,kind='All events',player=None):
    return [e for e in events if (round_number is None or e['round']==round_number)
            and (kind=='All events' or (e['kind']=='player_death')==(kind=='Kills'))
            and (not player or player in e['players'])]


class Moments:
    def __init__(self,path=STATE/'review-moments.json'):self.path=Path(path)

    def read(self):
        if not self.path.exists():return []
        data=json.loads(self.path.read_text(encoding='utf-8-sig'))
        required={'id','sha','tick','round','map','source','title','note','saved'}
        if (not isinstance(data,list) or any(not isinstance(v,dict) or not required<=set(v)
                or any(not isinstance(v[k],str) for k in ('id','sha','map','source','title','note','saved'))
                or not v['id'] or not re.fullmatch('[a-f0-9]{64}',v['sha'])
                or type(v['tick']) is not int or v['tick']<0
                or type(v['round']) is not int or v['round']<1 for v in data)
                or len({v['id'] for v in data})!=len(data)):
            raise ValueError('Saved moments are unreadable. The original file was left unchanged.')
        return data

    def save(self,entry,tick,round_number,note):
        if type(tick) is not int or tick<0:raise ValueError('Choose a valid moment.')
        if not note.strip():raise ValueError('Give this moment a short name or note.')
        with exclusive(self.path.with_suffix('.lock')):
            values=self.read()
            old=next((v for v in values if v['sha']==entry['sha'] and v['tick']==tick),None)
            item=dict(id=old['id'] if old else uuid.uuid4().hex,sha=entry['sha'],tick=tick,round=round_number,
                      source=entry['source'],title=entry['title'],map=entry['map'],note=note.strip()[:2000],
                      saved=datetime.now(timezone.utc).isoformat())
            save_json(self.path,[item]+[v for v in values if v['id']!=item['id']])
        return item

    def remove(self,identifier):
        with exclusive(self.path.with_suffix('.lock')):
            save_json(self.path,[v for v in self.read() if v['id']!=identifier])
