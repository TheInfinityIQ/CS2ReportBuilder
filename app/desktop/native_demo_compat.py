"""Narrow, verified playback copies for late CChicken entity baselines.

Original replay downloads are read-only inputs and remain library identities.
The MIT-licensed parser is pinned locally; no network dependency or telemetry.
"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import uuid

from jobs import STATE, hidden_options, read_json, save_json
from extractor.job_lock import exclusive
import replay_inventory as replays

HERE=Path(__file__).parent
DRIVER=HERE/'demo_compat.cjs'
CORE=HERE/'vendor/faceit_demo_fixer/demofix.cjs'
EXPECTED_CORE='ef5d03143ef3dca7ed740ab5cfa932bddd87b14e1bb479d00b095cc7c84bd8e8'


def checksum(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(4*1024*1024),b''):digest.update(block)
    return digest.hexdigest()


def signature():
    core=CORE.read_bytes()
    if hashlib.sha256(core).hexdigest()!=EXPECTED_CORE:raise ValueError('The pinned demo compatibility parser changed; playback stopped.')
    digest=hashlib.sha256(core);digest.update(DRIVER.read_bytes());digest.update(Path(__file__).read_bytes())
    return digest.hexdigest()


def require_verified(runtime,adapter):
    record=read_json(STATE/'native-demo-compatibility.json',{}).get(runtime,{})
    if record.get('adapter')!=adapter:
        raise ValueError('This demo needs a playback compatibility copy, which has not been validated for this game version. The original download is unchanged.')


def prepare(source,sha,runtime,*,allow_unverified=False):
    source=Path(source).resolve()
    if not source.is_relative_to(replays.replay_root()) or not source.is_file() or source.suffix.casefold()!='.dem':
        raise ValueError('Only original downloads in replays can be prepared for playback.')
    if not isinstance(sha,str) or len(sha)!=64 or any(c not in '0123456789abcdef' for c in sha):raise ValueError('Invalid original demo identity.')
    adapter=signature();root=(STATE/'playback-compat').resolve();folder=root/adapter/sha
    if not folder.resolve().is_relative_to(root):raise ValueError('Playback cache left its application folder.')
    folder.mkdir(parents=True,exist_ok=True)
    manifest=folder/'manifest.json';output=folder/'playback.dem'
    with exclusive(folder/'prepare.lock'):
        cached=read_json(manifest,{})
        if cached.get('source_sha256')!=sha or cached.get('adapter')!=adapter:
            node=shutil.which('node')
            if not node:raise ValueError('The installed Node runtime is required to inspect this demo for the known startup crash.')
            size=source.stat().st_size
            if size>1024**3:raise ValueError('This demo exceeds the current 1 GiB compatibility-check limit.')
            if shutil.disk_usage(root).free<size*2+64*1024**2:raise ValueError('Not enough free space for a private playback compatibility copy.')
            temporary=folder/f'pending-{uuid.uuid4().hex}.dem'
            try:
                result=subprocess.run([node,'--max-old-space-size=512',str(DRIVER),str(source),str(temporary)],
                    capture_output=True,text=True,timeout=60,**hidden_options())
                if result.returncode:raise ValueError('Demo compatibility check failed: '+result.stderr.strip()[-800:])
                if len(result.stdout)>256*1024:raise ValueError('Unexpectedly large compatibility report.')
                cached=json.loads(result.stdout)
                if cached.get('source_sha256')!=sha:raise ValueError('The original demo changed during its compatibility check. Refresh the library.')
                needed=cached.get('report',{}).get('crashFix',{}).get('needed',False)
                if needed:
                    proof=cached.get('verification',{})
                    if not proof.get('gameplay_messages_identical') or not cached.get('playback_sha256') or not temporary.is_file():
                        raise ValueError('The playback copy did not pass its gameplay-preservation check.')
                    os.replace(temporary,output)
                cached['adapter']=adapter;save_json(manifest,cached)
            except subprocess.TimeoutExpired as exc:raise ValueError('Demo compatibility inspection exceeded its time limit. The original is unchanged.') from exc
            finally:
                if temporary.exists():temporary.unlink()
        needed=cached.get('report',{}).get('crashFix',{}).get('needed',False)
        if not needed:return {'path':source,'applied':False,'source_sha256':sha,'adapter':adapter}
        if not allow_unverified:require_verified(runtime,adapter)
        if output.is_symlink() or not output.resolve().is_relative_to(root) or checksum(output)!=cached.get('playback_sha256'):
            raise ValueError('The private playback copy changed. It was not launched; the original download is intact.')
        blocked=read_json(STATE/'native-demo-compat-crashes.json',{})
        key=f'{runtime}:{adapter}:{sha}'
        if key in blocked:raise ValueError('This demo already crashed with this compatibility copy and game version. Playback is blocked pending investigation; the original is intact.')
        return {'path':output,'applied':True,'source_sha256':sha,'playback_sha256':cached['playback_sha256'],
                'adapter':adapter,'verification':cached['verification'],'report':cached['report']}


def record_validation(result):
    required=('ok','demo_active','original_demo_unchanged','original_settings_unchanged','owned_process_stopped','screen_size_unchanged','private_config_confirmed')
    if not all(result.get(k) for k in required) or result.get('frames',0)<60 or result.get('stable_playback_seconds',0)<25:
        raise ValueError('Playback-copy validation did not pass all engine, duration and settings gates.')
    compat=result['compatibility']
    if not compat.get('applied') or compat.get('adapter')!=signature() or not compat.get('verification',{}).get('gameplay_messages_identical'):
        raise ValueError('Playback-copy provenance or structural verification is missing.')
    records=read_json(STATE/'native-demo-compatibility.json',{})
    records[result['runtime_fingerprint']]={'adapter':compat['adapter'],'fixture_original_sha256':compat['source_sha256'],
                                          'playback_sha256':compat['playback_sha256'],'seconds':result['stable_playback_seconds']}
    save_json(STATE/'native-demo-compatibility.json',records)


def record_crash(runtime,compat):
    if not compat or not compat.get('applied'):return
    records=read_json(STATE/'native-demo-compat-crashes.json',{})
    records[f'{runtime}:{compat["adapter"]}:{compat["source_sha256"]}']={'playback_sha256':compat['playback_sha256']}
    save_json(STATE/'native-demo-compat-crashes.json',records)
