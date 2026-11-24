"""Start Toolbox's owned Godot renderer. Never starts CS2."""
import os
from pathlib import Path
import subprocess
import sys
import re
from functools import lru_cache

if __package__:
    from .backend import CACHE,DEFAULT_GAME,HERE,ROOT,read,save,downloaded_demos
else:
    from backend import CACHE,DEFAULT_GAME,HERE,ROOT,read,save,downloaded_demos


def steam_runtimes():
    steam=Path(os.environ.get('ProgramFiles(x86)',r'C:\Program Files (x86)'))/'Steam'
    libraries=[steam]
    try:
        text=(steam/'steamapps/libraryfolders.vdf').read_text(encoding='utf-8')
        libraries += [Path(value.replace('\\\\','\\')) for value in re.findall(r'"path"\s*"([^"]+)"',text)]
    except OSError:pass
    return [folder/'steamapps/common/Godot Engine/godot.windows.opt.tools.64.exe' for folder in dict.fromkeys(libraries)]


def find_godot():
    settings=read(CACHE/'settings.json',{})
    candidates=[*steam_runtimes(),settings.get('godot_executable',''),
        str(Path.home()/'Developer/Godot_Engines/4.6/Godotv4.6.1.exe'),
        str(Path.home()/'Developer/Godot_Engines/4.4/Godot_v4.4.1-stable_win64.exe')]
    for value in candidates:
        path=Path(value)
        if path.is_file() and 'godot' in path.name.casefold() and 'console' not in path.name.casefold():return path.resolve()
    raise ValueError('A Godot 4 runtime was not found. Set godot_executable in data/.desktop/standalone3d/settings.json.')


def runtime_version(executable):
    path=Path(executable).resolve();stamp=path.stat()
    signature=(stamp.st_dev,stamp.st_ino,stamp.st_size,stamp.st_mtime_ns,stamp.st_ctime_ns)
    return _runtime_version(str(path),signature)


@lru_cache(maxsize=16)
def _runtime_version(executable,signature):
    # One query per executable revision in this worker. A Steam update, moved
    # runtime or deleted executable must never inherit the previous version.
    return subprocess.check_output([executable,'--version'],text=True,timeout=8,
        **({'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {})).strip()


def launch(demo=None,*,parent=None,session=None,size=(1000,650),replay=None,smoke=None,screenshot=None):
    if not parent or not session:
        raise ValueError('The 3D renderer must be opened inside CS2 Toolbox.')
    godot=find_godot();CACHE.mkdir(parents=True,exist_ok=True)
    settings=read(ROOT/'data/.desktop/settings.json',{})
    game=Path(settings.get('cs2_game_directory') or DEFAULT_GAME)
    if demo and replay is None and smoke is None:
        if __package__:
            from .prepared_cache import find_ready
        else:
            from prepared_cache import find_ready
        replay=find_ready(demo,game,godot)
    python=Path(sys.executable)
    windowed=python.with_name('pythonw.exe')
    library=CACHE/'library.json'
    save(library,downloaded_demos())
    session=Path(session);session.mkdir(parents=True,exist_ok=True)
    args=[str(godot),'--path',str(HERE),'--log-file',str(session/'viewer.log'),
          '--wid',str(int(parent)),'--windowed','--single-window','--position','-32000,-32000',
          '--resolution',f'{max(1,size[0])}x{max(1,size[1])}','--',
          '--python',str(windowed if windowed.is_file() else python),'--backend',str(HERE/'backend.py'),
          '--cache',str(CACHE),'--game',str(game),'--library',str(library),
          '--embedded','true','--session',str(session)]
    renderer=os.environ.get('CS2_TOOLBOX_RENDERER')
    if renderer in {'forward_plus','mobile','gl_compatibility'}:args[1:1]=['--rendering-method',renderer]
    render_thread=os.environ.get('CS2_TOOLBOX_RENDER_THREAD')
    if render_thread in {'safe','separate'}:args[1:1]=['--render-thread',render_thread]
    for key,value in [('demo',demo),('replay',replay),('smoke',smoke),('screenshot',screenshot)]:
        if value is not None:args.extend(['--'+key,str(Path(value).resolve())])
    # Vulkan mailbox avoids tearing without waiting on two nested windows'
    # presentation intervals. This affects only the owned renderer process.
    present=os.environ.get('CS2_TOOLBOX_PRESENT','mailbox' if renderer!='gl_compatibility' else '')
    if present in {'disabled','loading_only','mailbox'}:args.extend(['--present',present])
    # Scope Godot's shader/user cache to Toolbox. The child receives its own
    # environment; Windows' normal application folders and game settings stay
    # untouched. A writable directory avoids recompiling every launch.
    environment=os.environ.copy()
    runtime_data=CACHE/'runtime-data';(runtime_data/'CS2StandaloneReplay').mkdir(parents=True,exist_ok=True)
    validation_cache=os.environ.get('CS2_TOOLBOX_VALIDATION_RUNTIME','')
    if smoke is not None and re.fullmatch(r'[a-z0-9_-]{1,48}',validation_cache):
        runtime_data=CACHE/'validation/runtime'/validation_cache
        (runtime_data/'CS2StandaloneReplay').mkdir(parents=True,exist_ok=True)
    environment['APPDATA']=str(runtime_data.resolve())
    environment['LOCALAPPDATA']=str(runtime_data.resolve())
    return subprocess.Popen(args,cwd=HERE,env=environment,**({'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}))


def main():
    # Historical shortcuts now enter Toolbox; there is no floating player path.
    sys.path.insert(0,str(ROOT/'app/desktop'))
    from main import Toolbox
    if os.name=='nt':
        import ctypes
        try:ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (OSError,AttributeError):pass
    app=Toolbox();app.show_page('viewer');app.mainloop()
    return 0


if __name__=='__main__':raise SystemExit(main())
