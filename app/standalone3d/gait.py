"""One small locomotion calibration shared by all demos using an actor bank."""
import hashlib
import json
from pathlib import Path
if __package__:
    from .backend import CACHE,HERE,read,save
    from .launcher import find_godot,runtime_version
    from .stock_assets import _run
else:
    from backend import CACHE,HERE,read,save
    from launcher import find_godot,runtime_version
    from stock_assets import _run

def prepare_gait(stock,progress=lambda *args:None):
    runtime=find_godot()
    identity=[1,stock['players'],runtime_version(runtime)]
    key=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:20]
    folder=CACHE/'gait'/key;output=folder/'calibration.json'
    result=read(output,{})
    if result.get('identity')!=identity:
        folder.mkdir(parents=True,exist_ok=True);save(folder/'bank.json',stock)
        progress('actors',89,'Calibrating shared walking and running animations…')
        _run([runtime,'--headless','--path',HERE,'--log-file',folder/'godot.log',
              '--script',HERE/'prepare_gait.gd','--',folder/'bank.json',output],folder,'prepare.log',limit=16*1024**2,timeout=45)
        result=read(output,{})
        if len(result.get('strides',{}))<24:raise ValueError('Stock locomotion calibration is incomplete.')
        result['identity']=identity;save(output,result)
    return result['strides']
