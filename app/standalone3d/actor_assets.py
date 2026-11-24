"""Shared authored viewmodel/death poses, prepared once outside the game."""
import hashlib
from pathlib import Path
import subprocess

if __package__:
    from .backend import CACHE,CONVERTER,HERE,ROOT,read,save,digest
    from .stock_assets import _run
    from .launcher import find_godot
else:
    from backend import CACHE,CONVERTER,HERE,ROOT,read,save,digest
    from stock_assets import _run
    from launcher import find_godot

VERSION=2
ARM_SCHEMA=4
VM_ALIASES={'smokegrenade':'smoke','incgrenade':'incendiary','m4a1s':'m4a1'}


def ensure_actors(game,stock,progress):
    game=Path(game);identity={'schema':VERSION,'stock':stock['identity'],'bridge':digest(HERE/'resource_bridge/Program.cs')}
    key=hashlib.sha256(repr(identity).encode()).hexdigest()[:20];folder=CACHE/'actors'/key;folder.mkdir(parents=True,exist_ok=True)
    # Adding read-only material inspection does not alter the pose decoder.
    # Reuse validated format-1 banks for the same installed stock revision.
    # Bump VERSION/pose_format when the decoded pose contract actually changes.
    for path in (CACHE/'actors').glob('*/manifest.json'):
        previous=read(path,{})
        old_identity=previous.get('identity',{})
        if old_identity.get('schema')==VERSION and old_identity.get('stock')==stock['identity'] and previous.get('pose_format',1)==1 and previous.get('arm_schema')==ARM_SCHEMA:
            identity=old_identity;folder=path.parent;break
    receipt=folder/'manifest.json';cached=read(receipt,{})
    wanted=set(stock['weapons'])
    if cached.get('identity')==identity and cached.get('arm_schema')==ARM_SCHEMA and wanted<=set(cached.get('viewmodels',{})) and all(Path(cached['arms'][t]['scene']).is_file() for t in ['ct','t']):return cached
    dotnet=CACHE/'tools/dotnet-10/dotnet.exe';bridge=CACHE/'tools/resource-bridge/ResourceBridge.dll'
    if not dotnet.is_file() or not bridge.is_file():raise ValueError('The read-only actor resource bridge needs preparation in Toolbox tools setup.')
    catalog_path=folder/'catalog.json';catalog=read(catalog_path,[])
    if not catalog:
        sys_args=[str(CONVERTER),'-i',str(game/'csgo/pak01_dir.vpk'),'-l','-e','vnmclip_c,vmdl_c,vnmskel_c']
        p=subprocess.run(sys_args,capture_output=True,text=True,timeout=30,creationflags=subprocess.CREATE_NO_WINDOW)
        if p.returncode:raise ValueError('Could not inspect installed actor resources.')
        catalog=[x.split(' CRC:')[0] for x in p.stdout.splitlines() if ' CRC:' in x];save(catalog_path,catalog)
    compiled=folder/'compiled';compiled.mkdir(exist_ok=True)

    def decode(resource,kind):
        target=folder/'poses'/hashlib.sha256(resource.encode()).hexdigest()[:20];target.mkdir(parents=True,exist_ok=True)
        output=target/('model.json' if kind=='model' else 'clip.json')
        if not output.is_file():
            progress('actors',32,'Preparing authored stock actor poses once…')
            _run([dotnet,bridge,game/'csgo/pak01_dir.vpk',resource,target,compiled],folder,'reader.log',limit=256*1024**2,timeout=45)
        if not output.is_file():raise ValueError('Authored actor data was not prepared: '+resource)
        return str(output)

    arms={}
    for team,glove in [('ct','hardknuckle'),('t','fingerless')]:
        resource=f'agents/models/shared/arms/glove_{glove}/glove_{glove}.vmdl_c'
        target=folder/('arms_'+team);target.mkdir(exist_ok=True);scene=target/'model.scn'
        if not scene.is_file() or read(target/'arm-schema.json',{}).get('schema')!=ARM_SCHEMA:
            glb=target/'model.glb'
            _run([CONVERTER,'-i',game/'csgo/pak01_dir.vpk','-f',resource,'-d','--gltf_export_format','glb','--gltf_export_materials','--gltf_textures_adapt','--gltf_export_animations','--gltf_animation_list','__pose_only__','--game',game/'csgo/gameinfo.gi','-o',glb,'--threads','1'],target,'export.log',limit=64*1024**2,timeout=90)
            _run([find_godot(),'--headless','--path',HERE,'--log-file',target/'godot.log','--script',HERE/'prepare_scene.gd','--',glb,scene,'view_arms'],target,'prepare.log',limit=64*1024**2,timeout=90)
            save(target/'arm-schema.json',{'schema':ARM_SCHEMA})
        arms[team]={'scene':str(scene),'model':decode(resource,'model')}
    models={}
    for team in ['ct','t']:
        info=read(Path(stock['players'][team]).parent/'model.json',{})
        models[team]=decode(info['resource'],'model')
    deaths={}
    for action in ['death_chest_a','death_chest_b','death_gut_a']:
        resource=f'animation/anims/world/shared/{action}.vnmclip_c'
        if resource in catalog:deaths[action]=decode(resource,'clip')

    def choose(action,suffix,kind):
        paths=[p for p in catalog if p.startswith('animation/anims/viewmodel/') and '+' not in p]
        exact=[p for p in paths if Path(p).stem==action+'_'+suffix]
        if exact:return min(exact,key=len)
        related=[p for p in paths if Path(p).stem.startswith(action+'_') and Path(p).stem.endswith('_'+suffix)]
        if related:return min(related,key=len)
        fallback=f'animation/anims/viewmodel/{kind}/_default_{kind}/{action}_{kind}.vnmclip_c'
        return fallback if fallback in catalog else None

    viewmodels={};weapons={};gaps=[]
    for weapon,definition in stock['weapons'].items():
        if definition.get('utility'):
            # Utility model metadata lives beside its shared scene too.
            definitions={'smokegrenade':('smokegrenade','smokegrenade'),'hegrenade':('hegrenade','hegrenade'),'flashbang':('flashbang','flashbang'),'molotov':('molotov','molotov'),'incgrenade':('incendiary','incendiarygrenade'),'decoy':('decoy','decoy')}
            sub,name=definitions[weapon];resource=f'weapons/models/grenade/{sub}/weapon_{name}.vmdl_c'
        else:resource=read(Path(definition['scene']).parent/'model.json',{}).get('resource')
        if resource:weapons[weapon]=decode(resource,'model')
        suffix=VM_ALIASES.get(definition['clip'],definition['clip']);kind='pistol' if definition['class']=='pistol' else ('knife' if definition['class']=='knife' else 'rifle')
        clips={}
        for action in ['idle','shoot1','reload','draw']:
            selected=choose(action,suffix,kind)
            if weapon=='elite' and action=='shoot1':selected=choose('shoot_right1',suffix,kind)
            if weapon=='g3sg1' and action=='idle':selected=choose('idle1',suffix,kind)
            if weapon=='taser' and action=='reload':continue # Recharge, not a magazine reload.
            if action=='shoot1' and weapon=='knife':selected=choose('light_miss1','knife','knife')
            if selected:clips[action]=decode(selected,'clip')
            elif action not in ['reload','shoot1'] or kind not in ['knife']:gaps.append(weapon+':'+action)
        if 'idle' not in clips:raise ValueError('A stock viewmodel has no usable idle pose: '+weapon)
        viewmodels[weapon]=clips
    fallbacks=[]
    for weapon,clips in viewmodels.items():
        for action,path in clips.items():
            variants=read(path,{}).get('variants',[])
            if variants and '_default_' in variants[0].get('name','') and weapon!='knife':fallbacks.append(weapon+':'+action)
    result={'schema':VERSION,'arm_schema':ARM_SCHEMA,'identity':identity,'arms':arms,'models':models,'weapon_models':weapons,'deaths':deaths,'viewmodels':viewmodels,'capability_gaps':gaps,'generic_pose_fallbacks':fallbacks}
    save(receipt,result)
    return result
