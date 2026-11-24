"""Personal Skybox inventory + newest-missing FACEIT demos. No Skybox secrets leave the browser."""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import re
import secrets
import threading
import time
import uuid
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode

from downloads import DEFAULT_REPLAYS, INDEX_NAME, Library, library_lock, progress, acquire_plan
from jobs import STATE, python_executable
from sources import AccessError, Resolver, SourceError, classify_link

SKYBOX = 'https://edge.skybox.gg/u/demos/personal'
PROTOCOL = 1
CHUNK = 4 * 1024 * 1024
MAX_FILE = 1024 * 1024 * 1024
HASH = re.compile(r'(?:[a-f0-9]{16}|[a-f0-9]{64})\Z')
FACEIT_ID = re.compile(r'1-[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}\Z')


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    stage = path.with_suffix('.tmp')
    stage.write_text(json.dumps(value, indent=2), encoding='utf-8')
    stage.replace(path)


def load_json(path, default):
    path = Path(path)
    if not path.is_file(): return default
    try: return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise SourceError('Skybox state is unreadable. Existing state was preserved; inspect it before retrying.') from exc


@dataclass
class Inventory:
    account: str
    hashes: set
    match_ids: set
    pending_hashes: set
    pending_ids: set
    count: int

    @classmethod
    def parse(cls, value):
        if not isinstance(value, dict) or value.get('complete') is not True:
            raise SourceError('Skybox inventory is incomplete. No uploads will start.')
        account = value.get('account')
        if not isinstance(account,str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,100}',account):
            raise SourceError('Skybox account identity is unavailable.')
        def identifiers(key, pattern):
            items=value.get(key,[])
            if not isinstance(items,list) or len(items)>100000 or any(not isinstance(s,str) or not pattern.fullmatch(s) for s in items):
                raise SourceError('Skybox inventory contains invalid identifiers.')
            return set(items)
        hashes=identifiers('hashes',HASH)
        count=value.get('count')
        if type(count) is not int or count!=len(hashes):
            raise SourceError('Skybox inventory count changed or pagination was incomplete.')
        return cls(account,hashes,identifiers('match_ids',FACEIT_ID),
                   identifiers('pending_hashes',HASH),identifiers('pending_ids',FACEIT_ID),count)

    def contains(self, digest):
        # Native Skybox client also checks the 16-character legacy hash prefix.
        return digest in self.hashes or digest[:16] in self.hashes or digest in self.pending_hashes


class SkyboxBridge:
    """One paired tab; only explicit current-file tickets can read bounded byte chunks."""
    def __init__(self, root=DEFAULT_REPLAYS, opener=webbrowser.open, timeout=1200):
        self.root=Path(root).resolve();self.opener=opener;self.timeout=timeout
        self.token=secrets.token_urlsafe(32);self.owner=None;self.task=None
        self.file=None;self.result=None;self.error=None;self.ready=threading.Event();self.lock=threading.RLock()
        self.launched=False
        bridge=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*_):pass
            def do_POST(self):
                size=int(self.headers.get('Content-Length','0')) if self.headers.get('Content-Length','').isdigit() else 0
                host=self.headers.get('Host','')
                origin=self.headers.get('Origin')
                if (host!=f'127.0.0.1:{bridge.server.server_port}' or origin not in (None,'https://edge.skybox.gg')
                    or not hmac.compare_digest(self.headers.get('X-CS2-Skybox',''),bridge.token)):
                    self.send_error(403);return
                if not 0<size<1024*1024:
                    self.send_error(400);return
                try:
                    data=bridge.dispatch(self.path,json.loads(self.rfile.read(size)))
                    payload=json.dumps(data).encode();status=200
                except (ValueError,OSError,KeyError,TypeError):
                    payload=json.dumps({'error':'Skybox bridge rejected this request. Check the current task and connection.'}).encode();status=400
                self.send_response(status);self.send_header('Content-Type','application/json')
                self.send_header('Content-Length',str(len(payload)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(payload)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);self.server.daemon_threads=True
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)

    def __enter__(self):self.thread.start();return self
    def __exit__(self,*_):
        self.server.shutdown();self.server.server_close();self.thread.join(2)

    def dispatch(self, route, body):
        if not isinstance(body,dict) or body.get('version')!=PROTOCOL:
            raise SourceError('Companion version mismatch.')
        owner=body.get('owner','')
        if not isinstance(owner,str) or not re.fullmatch(r'[a-zA-Z0-9-]{16,80}',owner):
            raise SourceError('Invalid tab identity.')
        with self.lock:
            if self.owner is not None and owner!=self.owner:
                raise SourceError('Another tab owns this upload job.')
            self.owner=owner
            if route=='/state':return {'task':self.task}
            if not self.task or body.get('id')!=self.task['id']:
                raise SourceError('Stale Skybox task.')
            if route=='/claim':
                if self.task['status']!='pending':raise SourceError('Task already claimed.')
                self.task['status']='claimed';return {'ok':True}
            if self.task['status']!='claimed':raise SourceError('Claim the task first.')
            if route=='/file':
                return self.file_chunk(body.get('ticket'),body.get('offset'))
            if route=='/result':
                self.result=body.get('result');self.task['status']='done';self.ready.set();return {'ok':True}
            if route=='/problem':
                # Never persist arbitrary browser errors, auth responses, or URLs.
                issue=body.get('issue','')
                safe=issue if isinstance(issue,str) and re.fullmatch(r'Toolbox[A-Za-z]{1,40}: [A-Za-z_, ]{1,180}',issue) else 'Browser task failed or lost its response'
                self.error='Skybox: '+safe+'. Check sign-in/access in the companion panel; no automatic retry was made.'
                self.task['status']='failed';self.ready.set();return {'ok':True}
            raise SourceError('Unsupported bridge request.')

    def register_file(self, path, digest, match_id):
        path=Path(path).resolve()
        if not path.is_relative_to(self.root) or path.suffix.lower()!='.dem' or not path.is_file():
            raise SourceError('Only selected physical demos in the replay library may be uploaded.')
        if not re.fullmatch(r'[a-f0-9]{64}',digest):raise SourceError('Missing local demo identity.')
        if not FACEIT_ID.fullmatch(match_id):raise SourceError('Missing FACEIT match identity.')
        stat=path.stat()
        if not 7<stat.st_size<=MAX_FILE:raise SourceError('Skybox upload supports demos up to 1 GiB per file.')
        with path.open('rb') as stream:
            if stream.read(7)!=b'PBDEMS2':raise SourceError('Not a CS2 demo header.')
        ticket=uuid.uuid4().hex
        self.file={'path':path,'ticket':ticket,'bytes':stat.st_size,'mtime_ns':stat.st_mtime_ns}
        return {'ticket':ticket,'bytes':stat.st_size,'modified':int(stat.st_mtime*1000),
                'filename':f'{match_id}__{digest[:12]}.dem','chunk':CHUNK}

    def file_chunk(self,ticket,offset):
        if not self.file or ticket!=self.file['ticket'] or type(offset) is not int or not 0<=offset<self.file['bytes']:
            raise SourceError('Invalid demo read ticket or offset.')
        path=self.file['path'];stat=path.stat()
        if path.resolve()!=path or not path.resolve().is_relative_to(self.root) or (stat.st_size,stat.st_mtime_ns)!=(self.file['bytes'],self.file['mtime_ns']):
            raise SourceError('Demo changed since selection.')
        with path.open('rb') as stream:
            stream.seek(offset);data=stream.read(CHUNK)
        return {'offset':offset,'bytes':base64.b64encode(data).decode(),'next':offset+len(data)}

    def ask(self, mode, **details):
        with self.lock:
            self.ready.clear();self.result=None;self.error=None
            self.task={'id':uuid.uuid4().hex,'mode':mode,'status':'pending',**details}
        if not self.launched:
            fragment=urlencode({'cs2skybox':PROTOCOL,'port':self.server.server_port,'pair':self.token})
            self.opener(SKYBOX+'#'+fragment);self.launched=True
            print('Skybox companion: keep the opened tab logged in. Update CS2Toolbox.user.js from Tools & setup if prompted.',flush=True)
        if not self.ready.wait(self.timeout):
            raise SourceError('Skybox companion did not respond. Update/enable CS2Toolbox.user.js (version 1.1.2 or newer), sign in, then restart. Any uncertain upload will not be repeated automatically.')
        if self.error:raise SourceError(self.error)
        return self.result


class Journal:
    def __init__(self, directory, account, player):
        scope=hashlib.sha256((account+'\0'+player).encode()).hexdigest()[:24]
        self.path=Path(directory)/(scope+'.json')
        self.data=load_json(self.path,{'version':1,'hashes':{},'attempts':{}})
        if self.data.get('version')!=1 or not isinstance(self.data.get('attempts'),dict) or not isinstance(self.data.get('hashes'),dict):
            raise SourceError('Skybox journal schema is unsupported; existing state was preserved.')

    def save(self):atomic_json(self.path,self.data)


def newest_history(resolver, player_id, limit=1000):
    seen=set();offset=0;previous=None
    while offset<limit:
        items=resolver.faceit(f'players/{player_id}/history?game=cs2&offset={offset}&limit={min(50,limit-offset)}').get('items')
        if not isinstance(items,list):raise SourceError('FACEIT history format was not recognized.')
        if not items:return
        ordered=sorted(items,key=lambda i:int(i.get('finished_at') or 0),reverse=True)
        for item in ordered:
            mid=item.get('match_id','');finished=item.get('finished_at')
            if not FACEIT_ID.fullmatch(mid) or type(finished) is not int or finished<=0:
                raise SourceError('FACEIT history is missing a stable match identity or finish time.')
            if mid in seen:continue
            if previous is not None and finished>previous:
                raise SourceError('FACEIT history changed or is not newest-first. Restart to refresh the selection.')
            seen.add(mid);previous=finished
            yield mid
        offset+=len(items)
        if len(items)<50:return


def sync_newest(*, profile, count, root, bridge, directory=STATE/'skybox', method='automatic', watch=None, steamid='',
                resolver=None, download_plan=None):
    if type(count) is not int or not 1<=count<=100:raise SourceError('Choose 1–100 new demos.')
    resolver=resolver or Resolver()
    if steamid:
        if not re.fullmatch(r'\d{17}',steamid):raise SourceError('Invalid selected player SteamID64.')
        player=resolver.faceit('players?'+urlencode({'game':'cs2','game_player_id':steamid}))
        if str(player.get('games',{}).get('cs2',{}).get('game_player_id',''))!=steamid:
            raise SourceError('FACEIT account does not match the selected library player.')
    else:
        link=classify_link(profile)
        if link['source']!='faceit' or link['kind']!='player':raise SourceError('Use a FACEIT player profile for newest missing demos.')
        player=resolver.faceit('players?'+urlencode({'nickname':link['id'],'game':'cs2'}))
    player_id=player.get('player_id');nickname=player.get('nickname')
    if not isinstance(player_id,str) or not re.fullmatch(r'[a-fA-F0-9-]{36}',player_id) or not nickname:
        raise SourceError('FACEIT player identity could not be resolved.')
    inventory=Inventory.parse(bridge.ask('inventory'))
    print(f'Skybox inventory: {inventory.count} processed demos; {len(inventory.pending_hashes)} identified pending demos.',flush=True)
    journal=Journal(directory,inventory.account,player_id)
    totals={'accepted':0,'existing':0,'pending':0,'unavailable':0,'review_required':0,'checked_matches':0,'requested':count}
    history=iter(newest_history(resolver,player_id))
    exhausted=False
    while totals['accepted']<count and not exhausted:
        # Build one multi-match plan for the existing downloader. Do not alternate
        # FACEIT acquisition and Skybox uploads for every individual match.
        batch=[];planned_maps=0;remaining=count-totals['accepted']
        library=Library(root,log=lambda *_:None)
        while planned_maps<remaining:
            try:mid=next(history)
            except StopIteration:exhausted=True;break
            totals['checked_matches']+=1
            progress('Planning FACEIT download batch',planned_maps,remaining,
                     f"{len(batch)} matches selected; {totals['existing']} duplicates skipped")
            try:match=resolver.faceit_match(mid,nickname,player_id=player_id)
            except AccessError:raise
            except (SourceError,KeyError,TypeError):totals['unavailable']+=1;continue
            maps=match.get('maps',[])
            if not maps:totals['unavailable']+=1;continue
            if len(maps)==1 and mid in inventory.match_ids:
                totals['existing']+=1;continue
            if len(maps)==1 and mid in inventory.pending_ids:
                totals['pending']+=1;continue
            # Cached identities exclude already-uploaded local files before sizing
            # the download batch. Reusing hashes requires the same file fingerprint.
            local=library.match_files(match);known=review=0
            for sha in dict.fromkeys(local):
                path=library.path(library.data['files'][sha]);stat=path.stat()
                cached=journal.data['hashes'].get(sha,{})
                if cached.get('fingerprint')!=[stat.st_size,stat.st_mtime_ns]:continue
                digest=cached.get('blake3','')
                if not re.fullmatch('[a-f0-9]{64}',digest):continue
                if inventory.contains(digest):known+=1
                elif journal.data['attempts'].get(digest,{}).get('state') in ('accepted','sending','uncertain'):review+=1
            if local and known+review==len(set(local)):
                totals['existing']+=known;totals['review_required']+=review;continue
            batch.append((mid,match));planned_maps+=max(1,len(maps)-known-review)
        if not batch:break
        missing=[match for _,match in batch if not library.match_files(match)]
        if missing:
            plan={'version':1,'matches':missing,'unavailable':[]}
            progress('Downloading FACEIT batch',0,len(missing),
                     f"Existing Downloads tool: {len(missing)} matches; Skybox uploads start after acquisition")
            if download_plan is not None:code=download_plan(plan,root,with_analysis=False)
            else:code=acquire_plan(plan,root,with_analysis=False,method='browser' if method=='browser' else 'auto',watch=watch)
            # A partially successful downloader can return nonzero. Its physical
            # indexed receipts, not its exit code alone, decide which files exist.
            if code:print('Some FACEIT downloads were unavailable; checking completed library receipts.',flush=True)
            library=Library(root,log=lambda *_:None)
        progress('Uploading downloaded demos to Skybox',totals['accepted'],count,
                 f"Download batch complete; checking {len(batch)} match receipts")
        for mid,match in batch:
            if totals['accepted']>=count:break
            files=library.match_files(match)
            if not files:totals['unavailable']+=1;continue
            for sha in dict.fromkeys(files):
                if totals['accepted']>=count:break
                record=library.data['files'][sha];path=library.path(record)
                meta=bridge.register_file(path,sha,mid)
                cached=journal.data['hashes'].get(sha,{})
                fingerprint=[meta['bytes'],path.stat().st_mtime_ns]
                if cached.get('fingerprint')==fingerprint and re.fullmatch('[a-f0-9]{64}',cached.get('blake3','')):
                    digest=cached['blake3']
                else:
                    result=bridge.ask('hash',file=meta,account=inventory.account)
                    digest=result.get('hash') if isinstance(result,dict) else None
                    if not isinstance(digest,str) or not re.fullmatch('[a-f0-9]{64}',digest):raise SourceError('Skybox file hash was not returned.')
                    journal.data['hashes'][sha]={'fingerprint':fingerprint,'blake3':digest};journal.save()
                if inventory.contains(digest):
                    totals['existing']+=1
                    journal.data['attempts'][digest]={'state':'confirmed','match':mid};journal.save();continue
                attempt=journal.data['attempts'].get(digest,{})
                if attempt.get('state') in ('accepted','sending','uncertain'):
                    totals['review_required']+=1
                    print('A previous upload is accepted or uncertain but not yet visible. Inspect Skybox before retrying that demo; it was not resent.',flush=True)
                    continue
                # Durable intent precedes every provider mutation. No automatic retry on lost receipts.
                journal.data['attempts'][digest]={'state':'sending','match':mid,'started':time.time()};journal.save()
                try:
                    receipt=bridge.ask('upload',file=meta,hash=digest,account=inventory.account,match_id=mid)
                    if not isinstance(receipt,dict) or receipt.get('state') not in ('accepted','already_present'):
                        raise SourceError('Skybox did not confirm upload acceptance.')
                except Exception:
                    journal.data['attempts'][digest]['state']='uncertain';journal.save();raise
                journal.data['attempts'][digest]['state']='accepted';journal.save()
                inventory.hashes.add(digest)
                if receipt['state']=='already_present':totals['existing']+=1
                else:totals['accepted']+=1
                progress('Uploading downloaded demos to Skybox',totals['accepted'],count,
                         f"{totals['accepted']}/{count} new demos accepted; processing continues on Skybox")
    atomic_json(Path(directory)/'last-sync.json',totals)
    print(f"Skybox finished: {totals['accepted']}/{count} new demos accepted; {totals['existing']} already present, {totals['pending']} pending, {totals['unavailable']} unavailable, {totals['review_required']} require review. Acceptance is not completed analysis.",flush=True)
    return totals


def build_command(*, profile='', count='10', root='', inventory=False, method='automatic', watch='', steamid=''):
    if not root.strip():raise SourceError('Choose your replay library folder.')
    command=[python_executable(),'-u',str(Path(__file__).resolve()),'--root',str(Path(root).resolve())]
    if inventory:return command+['--inventory']
    if steamid:
        if not re.fullmatch(r'\d{17}',steamid):raise SourceError('Invalid selected player SteamID64.')
    else:
        link=classify_link(profile)
        if link['source']!='faceit' or link['kind']!='player':raise SourceError('Paste a FACEIT player profile.')
    try:n=int(count)
    except (ValueError,TypeError):raise SourceError('Choose a whole number of new demos.') from None
    if not 1<=n<=100:raise SourceError('Choose 1–100 new demos.')
    if method not in ('automatic','browser'):raise SourceError('Choose Automatic or Browser downloads.')
    if method=='browser' and (not watch.strip() or not Path(watch).is_dir()):raise SourceError('Choose your existing browser downloads folder.')
    return command+['--upload']+(['--steamid',steamid] if steamid else ['--faceit',profile])+['--count',str(n),'--method',method]+(['--watch',watch] if watch.strip() else [])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    action=parser.add_mutually_exclusive_group(required=True);action.add_argument('--inventory',action='store_true');action.add_argument('--upload',action='store_true')
    parser.add_argument('--root',type=Path,default=DEFAULT_REPLAYS);parser.add_argument('--faceit');parser.add_argument('--count',type=int,default=10)
    parser.add_argument('--method',choices=['automatic','browser'],default='automatic');parser.add_argument('--watch',type=Path);parser.add_argument('--steamid',default='')
    args=parser.parse_args()
    directory=STATE/'skybox';directory.mkdir(parents=True,exist_ok=True)
    # Reuse the established cross-process lock without locking the replay library
    # across downloader calls (which acquire their own replay-library lock).
    with library_lock(directory), SkyboxBridge(args.root) as bridge:
        if args.inventory:
            value=bridge.ask('inventory');inv=Inventory.parse(value)
            atomic_json(directory/'inventory.json',value)
            print(f'Skybox inventory complete: {inv.count} processed demos; {len(inv.pending_hashes)} identified pending demos.',flush=True)
        else:
            result=sync_newest(profile=args.faceit or '',count=args.count,root=args.root,bridge=bridge,
                               directory=directory,method=args.method,watch=args.watch,steamid=args.steamid)
            return 0 if result['accepted']==args.count else 2
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except (SourceError,OSError) as exc:
        print('ERROR: '+str(exc),flush=True);raise SystemExit(1)
