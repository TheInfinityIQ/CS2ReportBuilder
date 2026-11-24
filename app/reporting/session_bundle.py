"""Lossless private coaching-session archive; no extraction and no source rewrites."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import tempfile
import zipfile
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from analyze import read_json, safe_folder, toolbox_reports
from build import verify
from desk import records
from extractor.job_lock import exclusive, lock_path


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
    return h.hexdigest()


def reject_link(path):
    info = path.lstat()
    if path.is_symlink() or getattr(info,'st_file_attributes',0) & getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',0x400):
        raise ValueError('Linked/reparse source paths are not supported: '+str(path))


def inventory(folder):
    reject_link(folder)
    found = {}
    for base, directories, files in os.walk(folder,followlinks=False):
        for name in directories+files: reject_link(Path(base)/name)
        for name in files:
            path = Path(base)/name
            if not path.is_file(): raise ValueError('Non-file analysis member: '+str(path))
            info = path.stat()
            found[path.relative_to(folder).as_posix()] = (info.st_size,info.st_mtime_ns)
    return found


def safe_member(name):
    parts = PurePosixPath(name).parts
    return bool(parts) and not name.startswith(('/', '\\')) and '\\' not in name and ':' not in name and all(p not in ('..','.') for p in parts) and str(PurePosixPath(name))==name


def validate(archive):
    """Verify without extracting or trusting executable contents or supplied paths."""
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        if len(names)!=len(set(names)) or any(not safe_member(n) for n in names):
            raise ValueError('Unsafe or duplicate archive member.')
        if z.getinfo('manifest.json').file_size>16*1024*1024:
            raise ValueError('Manifest is too large.')
        manifest = json.loads(z.read('manifest.json'))
        if manifest.get('version')!=1 or not isinstance(manifest.get('files'),dict):
            raise ValueError('Unsupported session manifest.')
        files = manifest['files']
        if set(names)!=set(files)|{'manifest.json'}:
            raise ValueError('Archive membership differs from its manifest.')
        if sum(z.getinfo(n).file_size for n in files)>8*1024**3:
            raise ValueError('Archive exceeds the 8 GiB validation bound.')
        for name, item in files.items():
            info = z.getinfo(name)
            if info.file_size!=item['bytes'] or stat.S_ISLNK(info.external_attr>>16):
                raise ValueError('Invalid member type/size: '+name)
            h = hashlib.sha256();size=0
            with z.open(name) as f:
                for block in iter(lambda:f.read(1024*1024),b''):
                    size+=len(block)
                    if size>item['bytes']:raise ValueError('Expanded size differs: '+name)
                    h.update(block)
            if size!=item['bytes'] or h.hexdigest()!=item['sha256']:
                raise ValueError('Archive checksum mismatch: '+name)
        session = json.loads(z.read('session.json'))
        if session.get('player',{}).get('steamid')!=manifest.get('player',{}).get('steamid'):
            raise ValueError('Session player identity mismatch.')
        games=manifest.get('games',[])
        if not 1<=len(games)<=50 or len({g['archive_path'] for g in games})!=len(games):
            raise ValueError('Invalid selected analysis-directory population.')
        if not {'report.html','report.build.json','coaching.json','measures.json','evidence/analysis.json','session.json'}<=set(files):
            raise ValueError('Required session artifacts are missing.')
        selected_members=set()
        for game in games:
            if not game['archive_path'].startswith('analysis/') or not safe_member(game['archive_path']):
                raise ValueError('Invalid analysis-directory prefix.')
            prefix = game['archive_path']+'/'
            members = {n[len(prefix):]:v['sha256'] for n,v in files.items() if n.startswith(prefix)}
            selected_members.update(prefix+n for n in members)
            revision = hashlib.sha256(json.dumps(members,sort_keys=True).encode()).hexdigest()
            if revision!=game['content_revision'] or len(members)!=game['files']:
                raise ValueError('Analysis membership/revision mismatch.')
        if selected_members!={n for n in files if n.startswith('analysis/')}:
            raise ValueError('Unassigned analysis data in archive.')
        return dict(session_id=session['id'],games=len(manifest['games']),
                    source_files=sum(g['files'] for g in manifest['games']),
                    files=len(files),source_bytes=sum(g['bytes'] for g in manifest['games']))


def create(evidence, coaching, report, output, replace=False):
    evidence,coaching,report,output = map(lambda p:Path(p).resolve(),(evidence,coaching,report,output))
    snapshot = read_json(evidence)
    root = Path(snapshot['analysis']).resolve()
    if output.suffix.lower()!='.zip' or output.is_relative_to(root):
        raise ValueError('Choose a ZIP output outside the analysis library.')
    if output.exists() and not replace:raise ValueError('Archive exists; use --replace deliberately.')
    stamp = (output.stat().st_size,output.stat().st_mtime_ns) if output.exists() else None
    build_path = report.with_suffix('.build.json')
    build = read_json(build_path)
    expected = {'report_sha256':report,'analysis_sha256':evidence,'coaching_sha256':coaching}
    if any(build.get(k)!=digest(p) for k,p in expected.items()):
        raise ValueError('Report/evidence/coaching fingerprints differ. Build the report first.')
    player = {k:v for k,v in snapshot['target'].items() if k!='games'}
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent,prefix='.session-stage-') as temp:
        stage = Path(temp).resolve()
        if stage.parent!=output.parent:raise ValueError('Unexpected staging location.')
        files, games = {}, []
        def track(path):
            files[path.relative_to(stage).as_posix()] = dict(bytes=path.stat().st_size,sha256=digest(path))
        def document(name,value):
            path=stage/name;path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(json.dumps(value,indent=2,allow_nan=False),encoding='utf-8');track(path)
        selected=[]
        for g in snapshot['games']:
            raw=root/g['source']
            for part in [raw,*raw.parents]:
                if part==root:break
                reject_link(part)
            selected.append((g,safe_folder(root,g['source'])))
        # Same lock order as extraction: global maintenance, then sorted folders.
        with ExitStack() as locks:
            locks.enter_context(exclusive(toolbox_reports.STATE/'analysis-maintenance.lock'))
            for folder in sorted({p for _,p in selected},key=lambda p:str(p).casefold()):
                locks.enter_context(exclusive(lock_path(folder)))
            verify(snapshot)
            for index,(game,folder) in enumerate(selected,1):
                print(f'Snapshotting analysis {index}/{len(selected)}',flush=True)
                before=inventory(folder);prefix=f'analysis/{index:04d}'
                member_hashes={}
                for relative in sorted(before):
                    src=folder/relative;dst=stage/prefix/relative
                    dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst);track(dst)
                    member_hashes[relative]=files[prefix+'/'+relative]['sha256']
                if inventory(folder)!=before or any(digest(folder/name)!=sha for name,sha in member_hashes.items()):
                    raise ValueError('Analysis changed during snapshot: '+game['source'])
                summary=read_json(folder/'match_summary.json');meta=read_json(folder/'viewer_tracks_meta.json')
                games.append(dict(source=game['source'],game_id=game['game'],demo_sha256=game['sha'],archive_path=prefix,
                                  content_revision=hashlib.sha256(json.dumps(member_hashes,sort_keys=True).encode()).hexdigest(),
                                  schema=summary.get('schema_version'),runtime=summary.get('runtime_environment'),
                                  tickrate=summary.get('tickrate'),track_metadata=meta,
                                  files=len(before),bytes=sum(size for size,_ in before.values())))
            verify(snapshot)
        # Freeze delivered artifacts too, then release source ownership before compression.
        for source,name in [(report,'report.html'),(build_path,'report.build.json'),(evidence,'evidence/analysis.json'),(coaching,'coaching.json')]:
            dest=stage/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dest);track(dest)
        if any(digest(stage/name)!=build[key] for key,name in [('report_sha256','report.html'),('analysis_sha256','evidence/analysis.json'),('coaching_sha256','coaching.json')]):
            raise ValueError('Delivered artifacts changed during snapshot.')
        document('measures.json',records(snapshot,build['summary']))
        reviewed_copy=read_json(stage/'coaching.json')
        document('session.json',dict(version=1,id='session-'+build['report_sha256'][:24],player=player,
                  evidence_digest=build['evidence_digest'],previous_session_ids=reviewed_copy.get('previous_session_ids',[]),
                  session_relationship=reviewed_copy.get('session_relationship','Original delivered session'),
                  created=datetime.now(timezone.utc).isoformat(),selection=snapshot['selection'],totals=snapshot['totals'],
                  coaching='coaching.json',measures='measures.json',
                  interpretation='Frozen delivered coaching; observations and player recollections remain distinct.',
                  player_notes='Optional user export, not automatically harvested from browser storage.'))
        manifest=dict(version=1,player=player,games=games,files=files,
                      completeness='Every file from each selected analysis directory; original demos and global account/job settings are outside scope.')
        (stage/'manifest.json').write_text(json.dumps(manifest,indent=2,allow_nan=False),encoding='utf-8')
        archive=stage/'session.zip'
        with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=3,allowZip64=True) as z:
            for name in sorted(set(files)|{'manifest.json'}):
                z.write(stage/name,name,compress_type=zipfile.ZIP_STORED if name.endswith(('.gz','.png','.jpg')) else zipfile.ZIP_DEFLATED)
        result=validate(archive)
        current=(output.stat().st_size,output.stat().st_mtime_ns) if output.exists() else None
        if stamp!=current:raise ValueError('Destination changed during export; preserving it.')
        os.replace(archive,output)
    return dict(result,output=str(output),bytes=output.stat().st_size,sha256=digest(output))


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    build=sub.add_parser('create')
    for flag in ['analysis','coaching','report','output']:build.add_argument('--'+flag,type=Path,required=True)
    build.add_argument('--replace',action='store_true')
    check=sub.add_parser('validate');check.add_argument('archive',type=Path)
    args=p.parse_args()
    result=validate(args.archive) if args.action=='validate' else create(args.analysis,args.coaching,args.report,args.output,args.replace)
    print(json.dumps(result))


if __name__=='__main__':main()
