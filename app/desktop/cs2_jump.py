"""Per-user HTML -> CS2 handoff. Only registered demo hashes and ticks are accepted."""
from __future__ import annotations
import csv
import hashlib
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from jobs import STATE, hidden_options, python_executable, read_json, save_json
from extractor.job_lock import exclusive
import replay_inventory as replays

SCHEME = 'cs2toolbox'
INDEX = STATE/'cs2-watch-demos.json'
DEFAULT_GAME = Path(r'C:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive\game')


def digest(path):
    checksum=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(4*1024*1024),b''):checksum.update(block)
    return checksum.hexdigest()


def parse_link(link):
    if not isinstance(link,str) or len(link)>500:raise ValueError('Invalid CS2 report link.')
    u=urlsplit(link)
    if u.scheme!=SCHEME or u.netloc!='watch' or u.path not in ('','/') or u.fragment:
        raise ValueError('Invalid CS2 report action.')
    q=parse_qs(u.query,strict_parsing=True)
    if set(q)!={'demo','tick'} or any(len(v)!=1 for v in q.values()):raise ValueError('Invalid CS2 report parameters.')
    sha,tick=q['demo'][0],q['tick'][0]
    if not re.fullmatch('[a-f0-9]{64}',sha) or not re.fullmatch('[0-9]{1,9}',tick):raise ValueError('Invalid demo identity or tick.')
    return sha,int(tick)


def register_analysis(folder,sha):
    if not re.fullmatch('[a-f0-9]{64}',str(sha)):return False
    folder=Path(folder).resolve()
    meta=read_json(folder/'viewer_tracks_meta.json',{})
    if meta.get('demo_sha256')!=sha:return False
    summary=read_json(folder/'match_summary.json',{})
    end=int(summary.get('end_tick') or 0)
    if end<=0:return False
    with exclusive(INDEX.with_suffix('.lock')):
        data=read_json(INDEX,{})
        old=data.get(sha,{})
        data[sha]={**old,'analysis':str(folder),'end_tick':max(end,old.get('end_tick',0))}
        save_json(INDEX,data)
    return True


def candidates(record,sha,game=DEFAULT_GAME):
    return [item['path'] for item in replays.available() if item['sha']==sha]


def resolve_demo(sha,tick,chooser=None):
    data=read_json(INDEX,{})
    record=data.get(sha)
    if not record:raise ValueError('This report is not registered on this PC. Rebuild it with this Toolbox, then try again.')
    if not 0<=tick<=record['end_tick']:raise ValueError('The requested moment is outside this demo.')
    for path in candidates(record,sha):
        try:return replays.verify(path,sha)
        except (replays.UnavailableDemo,OSError):continue
    # Legacy chooser arguments are deliberately ignored: playback never prompts
    # for, or falls back to, files outside the downloaded replay collection.
    raise replays.UnavailableDemo('This demo is not downloaded in replays. Refresh the downloaded-demo library.')


def console_path(path):
    value=Path(path).resolve().as_posix()
    if any(c in value for c in '\";\r\n') or not value.isascii():raise ValueError('CS2 needs a demo path with Basic Latin characters and no quotes or semicolons.')
    return '"'+value+'"'


def jump_command(tick):
    if type(tick) is not int or not 0<=tick<=999999999:raise ValueError('Invalid tick.')
    return f'demo_gototick {tick}\ndemo_pause\n'


def is_running():
    result=subprocess.run(['tasklist','/FI','IMAGENAME eq cs2.exe','/FO','CSV','/NH'],capture_output=True,text=True,timeout=5,**hidden_options())
    return any(row and row[0].casefold()=='cs2.exe' for row in csv.reader(io.StringIO(result.stdout)))


def install():
    if os.name!='nt':raise ValueError('CS2 report links currently support Windows.')
    import winreg
    python=Path(python_executable());windowed=python.with_name('pythonw.exe')
    command=f'"{windowed if windowed.is_file() else python}" "{Path(__file__).resolve()}" "%1"'
    key_path='Software\\Classes\\'+SCHEME
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,key_path+r'\shell\open\command') as key:
            previous=winreg.QueryValueEx(key,'')[0]
            if 'cs2_jump.py' not in previous:raise ValueError('Another application owns cs2toolbox links; its registration was left unchanged.')
    except FileNotFoundError:pass
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,key_path) as key:
        winreg.SetValueEx(key,'',0,winreg.REG_SZ,'URL:CS2 Toolbox Demo Review')
        winreg.SetValueEx(key,'URL Protocol',0,winreg.REG_SZ,'')
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,key_path+r'\shell\open\command') as key:
        winreg.SetValueEx(key,'',0,winreg.REG_SZ,command)
    print('CS2 report links enabled for this Windows user.',flush=True)


def launch(path,tick,status,game=DEFAULT_GAME,stop=None,timeout=150):
    """Fail closed until an adapter passes isolated settings-preservation tests."""
    jump_command(tick)
    console_path(path)
    if stop and stop.is_set():return
    if is_running():raise ValueError('CS2 is already running. Use Copy open command and Copy jump command in its console, or close it before opening another demo.')
    settings=read_json(STATE/'settings.json',{})
    game=Path(settings.get('cs2_game_directory') or game)
    from native_viewer import require_verified_launch
    require_verified_launch(game)


def watch(link):
    import tkinter as tk
    sha,tick=parse_link(link)
    window=tk.Tk();window.title('Watch in CS2 · Preview');window.geometry('590x275')
    status=tk.StringVar(value='Finding the original demo…')
    tk.Label(window,text='Watch the selected moment in CS2',font=('Segoe UI',14,'bold')).pack(anchor='w',padx=20,pady=(18,10))
    tk.Label(window,textvariable=status,wraplength=545,justify='left',font=('Segoe UI',10)).pack(anchor='w',padx=20,pady=8)
    path=resolve_demo(sha,tick)
    tk.Label(window,text=f'{path.name}\nTick {tick}',wraplength=545,justify='left').pack(anchor='w',padx=20,pady=8)
    row=tk.Frame(window);row.pack(anchor='w',padx=20,pady=12)
    def copy(text):window.clipboard_clear();window.clipboard_append(text);window.update()
    tk.Button(row,text='Copy open command',command=lambda:copy('playdemo '+console_path(path))).pack(side='left',padx=(0,8))
    tk.Button(row,text='Copy jump command',command=lambda:copy(jump_command(tick).replace('\n','; ').rstrip('; '))).pack(side='left')
    status.set('Original demo verified. Open CS2 normally and use the copied commands manually. Automatic launch awaits settings-preservation validation.')
    window.mainloop()


if __name__=='__main__':
    try:
        if sys.argv[1:]==['--install']:install()
        elif len(sys.argv)==2:watch(sys.argv[1])
        else:raise ValueError('Open a Watch in CS2 link from a Toolbox report.')
    except Exception as exc:
        if '--install' in sys.argv:print('ERROR: '+str(exc));raise SystemExit(1)
        import tkinter as tk
        from tkinter import messagebox
        root=tk.Tk();root.withdraw();messagebox.showerror('Unable to open CS2',str(exc),parent=root);root.destroy()
