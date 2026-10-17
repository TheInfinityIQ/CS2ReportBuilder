"""Resumable full v8 rebuild; old analysis is preserved. Default is a plan only."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from demo_layout import demo_files
from job_lock import exclusive

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / 'data/.desktop/rebuild-v8'
OUTPUT = ROOT / 'data/analysis/v8_rebuild'


def stamp(): return datetime.now(timezone.utc).isoformat()


def save(path, value):
    stage=path.with_suffix('.tmp')
    stage.write_text(json.dumps(value,indent=2),encoding='utf-8')
    stage.replace(path)


def plan(demos, output):
    result=[]
    for folder in sorted(demos.iterdir()):
        files=demo_files(folder) if folder.is_dir() else [folder] if folder.suffix.lower()=='.dem' else []
        for file in files:
            collection=folder.name if folder.is_dir() else 'loose_demos'
            stat=file.stat()
            result.append({'key':file.relative_to(demos).as_posix(),'source':str(file.resolve()),
                'size':stat.st_size,'mtime_ns':stat.st_mtime_ns,
                'collection':str((output/('analyzed_'+collection+'_v8')).resolve()),
                'output':str((output/('analyzed_'+collection+'_v8')/file.stem).resolve())})
    targets=[r['output'].casefold() for r in result]
    if len(set(targets))!=len(targets): raise ValueError('Duplicate output destinations')
    return result


def completed(folder):
    try:
        summary=json.loads((folder/'match_summary.json').read_text(encoding='utf-8-sig'))
        viewer=json.loads((folder/'viewer_tracks_meta.json').read_text(encoding='utf-8-sig'))
        entity=json.loads((folder/'viewer_v8/entity_meta.json').read_text(encoding='utf-8-sig'))
        return bool(summary.get('valid') and viewer.get('interpolation_check',{}).get('ok')
                    and entity.get('validation',{}).get('passed')
                    and entity.get('demo_sha256') and entity.get('demo_sha256')==viewer.get('demo_sha256')
                    and all((folder/name).is_file() for name in ('rounds.csv','viewer_tracks.csv.gz','grenade_paths.csv.gz'))
                    and (folder/'viewer_v8/smoke_decode_meta.json').is_file())
    except (OSError,ValueError): return False


def run(items, state=STATE, min_free_gb=12):
    state.mkdir(parents=True,exist_ok=True)
    with exclusive(state/'run.lock'):
        path=state/'progress.json'
        previous=json.loads(path.read_text()) if path.exists() else {}
        records=previous.get('results',{})
        sources=[p for p in Path(__file__).parent.glob('*.py') if not p.name.startswith('test_')]
        sources.extend((Path(__file__).parent/'entity_v8').glob('*.cs'))
        revision=hashlib.sha256(b''.join(p.read_bytes() for p in sorted(sources))).hexdigest()
        status={'status':'running','started':stamp(),'updated':stamp(),'pid':os.getpid(),
                'total':len(items),'completed':0,'failed':0,'current':'','message':'Preparing full v8 rebuild',
                'results':{},'output':str(OUTPUT),'free_gb':0}
        (state/'stop.request').unlink(missing_ok=True)
        save(path,status)
        try:
            for index,item in enumerate(items):
                status['remaining']=len(items)-index
                if (state/'stop.request').exists():
                    status.update(status='stopped',message='Stopped between demos; resume preserves completed results.')
                    break
                free=shutil.disk_usage(ROOT).free/1024**3
                status['free_gb']=round(free,2)
                if free<min_free_gb:
                    status.update(status='low_disk',message=f'Paused with {free:.1f} GB free; {min_free_gb:g} GB reserve required.')
                    break
                old=records.get(item['key'],{})
                signature=[item['size'],item['mtime_ns'],revision]
                if old.get('status')=='completed' and old.get('signature')==signature and completed(Path(item['output'])):
                    status['results'][item['key']]=old;status['completed']+=1
                    continue
                destination=Path(item['output'])
                record={'status':'running','signature':signature,'output':item['output'],'started':stamp()}
                status['current']=item['key'];status['message']='Starting demo';status['results'][item['key']]=record
                save(path,status)
                command=[sys.executable,'-u',str(ROOT/'app/extractor/extract_demos_v8.py'),'--demo',item['source'],
                         '--output',item['collection'],'--entity-hz','16']
                if destination.exists():
                    if old.get('output')!=item['output']:
                        record.update(status='failed',error='Existing output is not owned by this rebuild; preserved.')
                        status['failed']+=1;save(path,status);continue
                    command.append('--replace')
                log=state/(hashlib.sha256(item['key'].encode()).hexdigest()[:16]+'.log')
                record['log']=str(log)
                env={**os.environ,'PYTHONIOENCODING':'utf-8','PYTHONUNBUFFERED':'1','CS2_TOOLBOX_BACKGROUND':'1',
                     'DOTNET_CLI_TELEMETRY_OPTOUT':'1'}
                options={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
                start=time.monotonic();last=0
                with log.open('w',encoding='utf-8') as out:
                    with subprocess.Popen(command,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                            encoding='utf-8',errors='replace',env=env,**options) as child:
                        status['worker_pid']=child.pid
                        for line in child.stdout:
                            out.write(line);out.flush()
                            status['message']=line.strip()[-250:]
                            if time.monotonic()-last>1:
                                status['updated']=stamp();save(path,status);last=time.monotonic()
                        code=child.wait()
                success=code==0 and completed(destination)
                record.update(status='completed' if success else 'failed',exit_code=code,
                              seconds=round(time.monotonic()-start,1),finished=stamp())
                if not success: record['error']='Extraction or output validation failed; see this demo log.'
                status['completed' if success else 'failed']+=1
                status['updated']=stamp();save(path,status)
                print(f"{index+1}/{len(items)} {record['status']}: {item['key']}",flush=True)
            else:
                status.update(status='completed_with_failures' if status['failed'] else 'completed',remaining=0,
                              message='Rebuild finished. Failed demos retain their logs and can be retried.')
        except BaseException as exc:
            status.update(status='interrupted',message=f'{type(exc).__name__}: {exc}')
            raise
        finally:
            status.update(current='',updated=stamp());save(path,status)
        return status


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',action='store_true')
    parser.add_argument('--stop',action='store_true',help='Stop after the current demo')
    parser.add_argument('--first',help='Process this relative demo path first, then the rest')
    args=parser.parse_args()
    if args.stop:
        STATE.mkdir(parents=True,exist_ok=True);(STATE/'stop.request').touch()
        print('Stop requested after the current demo.')
    else:
        items=plan(ROOT/'data/demos',OUTPUT)
        if args.first:
            if args.first not in {i['key'] for i in items}: parser.error('--first must match a demo path in the plan')
            items.sort(key=lambda item:item['key']!=args.first)
        print(f'{len(items)} demos; {sum(i["size"] for i in items)/1024**3:.2f} GB originals; output: {OUTPUT}',flush=True)
        if args.run: run(items)
