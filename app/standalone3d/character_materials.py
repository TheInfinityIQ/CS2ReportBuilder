"""Shared source material flags, with temporary raw inputs only."""
from pathlib import Path
import tempfile
if __package__:
    from .backend import CACHE,read
    from .stock_assets import _run
else:
    from backend import CACHE,read
    from stock_assets import _run


def prepare_character_materials(game,stock):
    root=CACHE/'character-materials'/stock['identity']['pak_index'][:20];root.mkdir(parents=True,exist_ok=True)
    result={}
    for team,scene in stock['players'].items():
        target=root/(team+'.json')
        if not target.is_file():
            resource=read(Path(scene).parent/'model.json',{})['resource']
            with tempfile.TemporaryDirectory(prefix=team+'-',dir=root) as job:
                job=Path(job)
                _run([CACHE/'tools/dotnet-10/dotnet.exe',CACHE/'tools/resource-bridge/ResourceBridge.dll',Path(game)/'csgo/pak01_dir.vpk',resource,job,job/'compiled','materials'],job,'reader.log',limit=64*1024**2,timeout=45)
                if not read(job/'materials.json',[]):raise ValueError('Source character materials could not be inspected.')
                (job/'materials.json').replace(target)
        result[team]=read(target,[])
    return result
