"""Bounded stock-only asset preparation shared by every recording and map."""
from pathlib import Path
import hashlib
import json
import re
import struct
import subprocess
import sys
import time

if __package__:
    from .backend import CACHE,CONVERTER,HERE,ROOT,digest,read,save
    from .launcher import find_godot,runtime_version
else:
    from backend import CACHE,CONVERTER,HERE,ROOT,digest,read,save
    from launcher import find_godot,runtime_version

ADAPTER=1
ANIMATION_SCHEMA=6
AUDIO_SCHEMA=2
WORLD_FIRE={'elite':'shoot_right1_elite','cz75a':'shoot_cz75'}
# Demo display names and event IDs resolve to the same default equipment.
WEAPONS={
 'ak47':('AK-47','ak47','rif','ak'), 'm4a1':('M4A4','m4a4','rif','m4a4'),
 'm4a1_silencer':('M4A1-S','m4a1_silencer','rif','m4a1s'),
 'glock':('Glock-18','glock18','pist','glock'), 'usp_silencer':('USP-S','usp_silencer','pist','usp'),
 'hkp2000':('P2000','hkp2000','pist','hkp'), 'p250':('P250','p250','pist','p250'),
 'deagle':('Desert Eagle','deagle','pist','deagle'), 'elite':('Dual Berettas','elite','pist','elite'),
 'fiveseven':('Five-SeveN','fiveseven','pist','fiveseven'), 'tec9':('Tec-9','tec9','pist','tec9'),
 'revolver':('R8 Revolver','revolver','pist','revolver'), 'awp':('AWP','awp','snip','awp'),
 'ssg08':('SSG 08','ssg08','snip','ssg08'), 'aug':('AUG','aug','rif','aug'),
 'sg556':('SG 553','sg556','rif','sg556'), 'galilar':('Galil AR','galilar','rif','galilar'),
 'famas':('FAMAS','famas','rif','famas'), 'mac10':('MAC-10','mac10','smg','mac10'),
 'mp9':('MP9','mp9','smg','mp9'), 'nova':('Nova','nova','shot','nova'),
 'xm1014':('XM1014','xm1014','shot','xm1014'), 'taser':('Zeus x27','taser','eq','taser'),
 'knife':('knife','knife','knife','knife'),
 'mp5sd':('MP5-SD','mp5sd','smg','mp5sd'), 'mp7':('MP7','mp7','smg','mp7'),
 'ump45':('UMP-45','ump45','smg','ump45'), 'p90':('P90','p90','smg','p90'),
 'bizon':('PP-Bizon','bizon','smg','bizon'), 'cz75a':('CZ75-Auto','cz75a','pist','cz75a'),
 'g3sg1':('G3SG1','g3sg1','snip','g3sg1'), 'scar20':('SCAR-20','scar20','snip','scar20'),
 'negev':('Negev','negev','mach','negev'), 'm249':('M249','m249','mach','m249'),
 'mag7':('MAG-7','mag7','shot','mag7'), 'sawedoff':('Sawed-Off','sawedoff','shot','sawedoff'),
}


def canonical(value):
    value=str(value or '')
    if value.lower().startswith('weapon_'):value=value[7:]
    folded=value.casefold();compact=re.sub(r'[^a-z0-9]','',folded)
    utility={'Smoke Grenade':'smokegrenade','High Explosive Grenade':'hegrenade','HE Grenade':'hegrenade',
             'Flashbang':'flashbang','Molotov':'molotov','Incendiary Grenade':'incgrenade','Decoy Grenade':'decoy'}
    for label,key in utility.items():
        if folded==key or compact==re.sub(r'[^a-z0-9]','',label.casefold()):return key
    for key,(label,*_) in WEAPONS.items():
        if folded==key or compact==re.sub(r'[^a-z0-9]','',label.casefold()):return key
    if 'knife' in value.casefold() or any(x in value.casefold() for x in ['bayonet','daggers']):return 'knife'
    return value


def gltf_info(path):
    with Path(path).open('rb') as f:
        if f.read(4)!=b'glTF':raise ValueError('Invalid stock model export.')
        f.seek(12);size,kind=struct.unpack('<II',f.read(8))
        if kind!=0x4e4f534a or size>100*1024**2:raise ValueError('Stock model export is unexpectedly large.')
        return json.loads(f.read(size))


def _run(args,folder,log_name,*,limit=1_200_000_000,timeout=240,incremental=False,env=None):
    sys.path.insert(0,str(ROOT/'app/desktop'))
    from jobs import WindowsProcessGroup,hidden_options
    baseline=sum(p.stat().st_size for p in folder.rglob('*') if p.is_file()) if incremental else 0
    with (folder/log_name).open('wb') as log:
        process=subprocess.Popen([str(x) for x in args],cwd=folder,stdout=log,stderr=subprocess.STDOUT,env=env,**hidden_options())
        group=WindowsProcessGroup(process)
        try:
            if not group.handle:raise RuntimeError('Could not supervise stock asset preparation.')
            start=time.monotonic()
            while process.poll() is None:
                if time.monotonic()-start>timeout:raise TimeoutError('Stock asset preparation timed out.')
                if sum(p.stat().st_size for p in folder.rglob('*') if p.is_file())-baseline>limit:
                    raise ValueError('Stock asset preparation exceeded its bounded cache size.')
                time.sleep(.25)
            if process.returncode:raise ValueError('Stock asset preparation failed: '+str(folder/log_name))
            if sum(p.stat().st_size for p in folder.rglob('*') if p.is_file())-baseline>limit:
                raise ValueError('Stock asset preparation exceeded its bounded cache size.')
        finally:
            if process.poll() is None:group.terminate();process.wait(timeout=10)
            group.close()


def catalog(game):
    sys.path.insert(0,str(ROOT/'app/desktop'))
    from jobs import hidden_options
    args=[str(CONVERTER),'-i',str(game/'csgo/pak01_dir.vpk'),'-l','-e','vmdl_c,vsnd_c,vnmclip_c']
    p=subprocess.run(args,cwd=CACHE,capture_output=True,text=True,timeout=30,**hidden_options())
    if p.returncode:raise ValueError('Could not read installed stock resource index.')
    return {line.split(' CRC:',1)[0]:line.split(' CRC:',1)[1] for line in p.stdout.splitlines() if ' CRC:' in line}


def ensure_stock(game,weapon_names,progress):
    game=Path(game);godot=find_godot();version=runtime_version(godot)
    evidence={'pak_index':digest(game/'csgo/pak01_dir.vpk'),'runtime':version,'adapter':ADAPTER}
    key=hashlib.sha256(json.dumps(evidence,sort_keys=True).encode()).hexdigest()[:20]
    folder=CACHE/'stock'/key;folder.mkdir(parents=True,exist_ok=True)
    manifest=read(folder/'manifest.json',{})
    wanted=sorted({canonical(x) for x in weapon_names if canonical(x) in WEAPONS})
    if manifest.get('identity')==evidence and manifest.get('animation_schema')==ANIMATION_SCHEMA and manifest.get('audio_schema')==AUDIO_SCHEMA and set(wanted)<=set(manifest.get('weapons',{})):
        if all(Path(p).is_file() for p in [*manifest.get('players',{}).values(),*[x['scene'] for x in manifest['weapons'].values()]]):return manifest
    # Switching recordings grows one shared bank, rather than replacing its
    # clip/weapon set and forcing earlier recordings to prepare again.
    if manifest.get('identity')==evidence:
        wanted=sorted(set(wanted)|{key for key in manifest.get('weapons',{}) if key in WEAPONS})
    progress('stock',28,'Preparing shared stock player, weapon and sound assets…')
    entries=catalog(game)
    common=[f'animation/anims/world/{kind}/_default_{kind}/{action}_{kind}'
            for kind in ['rifle','pistol','knife'] for action in ['idle','idle_crouch','run_n','walk_n','crouch_n','jump_stand']]
    common += [f'animation/anims/world/{kind}/_default_{kind}/{action}_{direction}_{kind}'
               for kind in ['rifle','pistol','knife'] for action in ['run','walk','crouch']
               for direction in ['ne','e','se','s','sw','w','nw']]
    # Clip names are validated by the reader. Missing per-weapon clips remain
    # reported capabilities; they never become guessed animation identifiers.
    actions=[]
    for weapon in wanted:
        label,sub,category,clip=WEAPONS[weapon]
        group='pistol' if category=='pist' else 'rifle'
        suffixes={f'{action}_{clip}' for action in ['shoot','reload','reload_crouch']}
        suffixes.add(WORLD_FIRE.get(weapon,'shoot_'+clip))
        if weapon=='elite':suffixes.update(['shoot_left1_elite','shoot_right1_elite'])
        if weapon=='knife':suffixes.add('frontstab_knife')
        actions += [p.removesuffix('.vnmclip_c') for p in entries if p.startswith('animation/anims/world/')
                    and p.endswith('.vnmclip_c') and Path(p).stem in suffixes]
    manifest={'identity':evidence,'animation_schema':ANIMATION_SCHEMA,'audio_schema':AUDIO_SCHEMA,'players':{},'weapons':{},'sounds':{},'warnings':[]}
    def model(asset,name,animations=None):
        directory=folder/name;directory.mkdir(exist_ok=True);glb=directory/'model.glb';scene=directory/'model.scn'
        clip_key=hashlib.sha256(json.dumps(animations or [],sort_keys=True).encode()).hexdigest()
        if not scene.is_file() or read(directory/'model.json',{}).get('export_schema')!=2 or (animations and read(directory/'clips.json',{})!={'key':clip_key}):
            args=[CONVERTER,'-i',game/'csgo/pak01_dir.vpk','-f',asset,'-d','--gltf_export_format','glb',
                  '--gltf_export_materials','--gltf_textures_adapt','--game',game/'csgo/gameinfo.gi','-o',glb,'--threads','1']
            if animations:args += ['--gltf_export_animations','--gltf_compose_additive','--gltf_animation_list',','.join(animations)]
            else:args += ['--gltf_export_animations','--gltf_animation_list','__pose_only__']
            _run(args,directory,'export.log')
            info=gltf_info(glb)
            if not info.get('meshes') or (animations and (not info.get('skins') or len(info.get('animations',[]))<6)):
                raise ValueError('Installed player resource is a dummy or lacks usable animation: '+asset)
            _run([godot,'--headless','--path',HERE,'--script',HERE/'prepare_scene.gd','--',glb,scene,'stock'],directory,'prepare.log')
            if animations:save(directory/'clips.json',{'key':clip_key})
            save(directory/'model.json',{'export_schema':2,'resource':asset})
        # Native resources bundle their inputs. Keep one runtime copy rather
        # than retaining another GLB and PNG set beside every stock resource.
        for pattern in ('*.glb','*.png'):
            for temporary in directory.glob(pattern):
                if temporary.resolve().is_relative_to(directory.resolve()):temporary.unlink()
        return str(scene)
    for team,stem in [('ct','ctm_sas'),('t','tm_phoenix')]:
        progress('stock_players',29,'Preparing shared '+team.upper()+' rig and gameplay clips…')
        choices=[f'agents/models/{stem}/{stem}.vmdl_c',f'characters/models/{stem}/{stem}.vmdl_c']
        path=next((p for p in choices if p in entries and int(entries[p].split('size:')[-1])>10000),None)
        if not path:raise ValueError('A supported default '+team+' rig was not found in this game revision.')
        manifest['players'][team]=model(path,team,common+actions)
    for weapon_number,weapon in enumerate(wanted,1):
        label,sub,category,clip=WEAPONS[weapon]
        progress('stock_weapons',30,'Preparing stock weapon '+str(weapon_number)+'/'+str(len(wanted))+': '+label)
        candidates=[p for p in entries if p.startswith(f'weapons/models/{sub}/') and p.endswith('.vmdl_c')
                    and p.rsplit('/',1)[-1].startswith('weapon_') and not any(t in p for t in ['_mag.','_scope.','_suppressor.'])]
        candidates.sort(key=lambda p:(len(p),p))
        if not candidates:
            manifest['warnings'].append('Default weapon model unavailable: '+label);continue
        manifest['weapons'][weapon]={'scene':model(candidates[0],'weapon_'+weapon),'label':label,'clip':clip,
                                    'fire_animation':WORLD_FIRE.get(weapon,'frontstab_knife' if weapon=='knife' else 'shoot_'+clip),
                                    'class':'pistol' if category=='pist' or weapon=='taser' else ('knife' if weapon=='knife' else 'rifle')}
    def sound(asset):
        directory=folder/'audio';directory.mkdir(exist_ok=True)
        name=Path(asset).stem;existing=list(directory.rglob(name+'.wav'))+list(directory.rglob(name+'.mp3'))
        if not existing:
            _run([CONVERTER,'-i',game/'csgo/pak01_dir.vpk','-f',asset,'-d','-o',directory],directory,'export.log',limit=100_000_000,timeout=30)
            existing=list(directory.rglob(name+'.wav'))+list(directory.rglob(name+'.mp3'))
        return str(existing[0]) if existing else None
    for weapon in wanted:
        _,sub,_,_=WEAPONS[weapon]
        audio_sub={'m4a1':'m4a1','m4a1_silencer':'m4a1','usp_silencer':'usp','mp5sd':'mp5'}.get(weapon,sub)
        prefix=f'sounds/weapons/{audio_sub}/'
        files=[p for p in entries if p.startswith(prefix) and p.endswith('.vsnd_c')]
        fire_stem={'elite':'elites_01','galilar':'galil_01','m4a1':'m4a1_01','m4a1_silencer':'m4a1_silencer_01',
                   'usp_silencer':'usp_01','revolver':'revolver-1_01','tec9':'tec9_02','taser':'taser_shoot','knife':'knife_slash1',
                   'mp5sd':'mp5_01','ump45':'ump45_02','cz75a':'cz75_01'}.get(weapon,sub+'_01')
        for action,patterns in [('fire',[re.escape(fire_stem)+'$',rf'{re.escape(sub)}-1$',rf'{re.escape(weapon)}_01$']),
                                ('reload',[r'clipout_01$',r'magout_01$',r'clipout$',r'magout$',r'coverup$',r'insertshell_01$',r'clipin_01$'])]:
            chosen=next((p for pattern in patterns for p in files if re.search(pattern,Path(p).stem)),None)
            if chosen:
                out=sound(chosen)
                if out:manifest['sounds'][action+':'+weapon]=out
        unsilenced={'m4a1_silencer':'m4a1_us_01','usp_silencer':'usp_unsilenced_01'}.get(weapon)
        if unsilenced:
            chosen=next((p for p in files if Path(p).stem==unsilenced),None)
            if chosen:
                out=sound(chosen)
                if out:manifest['sounds']['fire_unsilenced:'+weapon]=out
    for key,asset in [('step','sounds/player/footsteps/concrete_ct_01.vsnd_c')]:
        if asset in entries:
            out=sound(asset)
            if out:manifest['sounds'][key]=out
    save(folder/'manifest.json',manifest)
    return manifest
