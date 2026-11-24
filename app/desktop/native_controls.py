"""External demo controls. Experimental until the contained real-engine gate passes.

Protocol framing reference: theokyr/CS2RemoteConsole, libvconsole/src/vconsole.cpp.
Only structured playback actions are accepted; never arbitrary console strings.
"""
from __future__ import annotations
import ctypes as c
from ctypes import wintypes as w
from pathlib import Path
import re
import secrets
import socket
import struct
import subprocess
import time
import uuid
import hashlib

from jobs import STATE, read_json, save_json

# Installed vconcomm.dll writes a 16-bit version at +4 and a 32-bit
# length at +6. The frequently published IHH layout happens to match
# small packets, then loses framing on messages larger than 65,535 bytes.
HEADER=struct.Struct('>4sHIH')
SPEEDS=(.25,.5,1.,2.,4.,8.)


def command(action,value=None):
    simple={'pause':'demo_pause','resume':'demo_resume','step':'demo_step_tick 1',
            'info':'demo_info','position':'demo_gototick',
            'next_player':'spec_next','previous_player':'spec_prev'}
    if action in simple and value is None:return simple[action]
    if action=='speed' and type(value) in (int,float) and value in SPEEDS:
        return f'demo_timescale {value:g}'
    if action=='seek' and type(value) is int and 0<=value<=999999999:
        return f'demo_gototick {value} P'
    if action=='skip' and type(value) is int and value in (-640,640):
        return f'demo_gototick {value} R P'
    if action=='camera' and value in ('first_person','chase','free'):
        return 'spec_mode '+str({'first_person':2,'chase':3,'free':4}[value])
    if action=='lock_account' and type(value) is int and 0<=value<=4294967295:
        return 'spec_lock_to_accountid '+str(value)
    if action=='player_name' and isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9_-]{1,64}',value):
        return 'spec_player "'+value+'"'
    raise ValueError('Unsupported playback action or value.')


def verify_camera_contract(game):
    """Read the installed schema enum without loading/injecting a game DLL.

    Reject changed layouts instead of trusting historic CS:GO observer numbers.
    """
    import mmap
    path=Path(game)/'csgo/bin/win64/client.dll'
    names=['OBS_MODE_NONE','OBS_MODE_FIXED','OBS_MODE_IN_EYE','OBS_MODE_CHASE','OBS_MODE_ROAMING']
    with path.open('rb') as stream,mmap.mmap(stream.fileno(),0,access=mmap.ACCESS_READ) as image:
        pe=struct.unpack_from('<I',image,60)[0]
        if image[pe:pe+4]!=b'PE\0\0':raise ValueError('Unrecognized CS2 client binary.')
        count=struct.unpack_from('<H',image,pe+6)[0];optional=struct.unpack_from('<H',image,pe+20)[0]
        base=struct.unpack_from('<Q',image,pe+48)[0]
        sections=[struct.unpack_from('<IIII',image,pe+24+optional+i*40+8) for i in range(count)]
        entries=[]
        for name in names:
            offset=image.find(name.encode()+b'\0')
            addresses=[base+rva+offset-raw for _,rva,size,raw in sections if raw<=offset<raw+size]
            if len(addresses)!=1:raise ValueError('CS2 observer schema names changed; camera validation required.')
            entry=image.find(struct.pack('<Q',addresses[0]))
            if entry<0 or struct.unpack_from('<Q',image,entry+8)[0]!=len(entries):
                raise ValueError('CS2 observer enum values changed; camera validation required.')
            entries.append(entry)
        if entries!=[entries[0]+32*i for i in range(5)]:
            raise ValueError('CS2 observer enum layout changed; camera validation required.')
    return dict(zip(names,range(5)))


def packet(text):
    payload=text.encode('ascii')+b'\0'
    if len(payload)>4096 or '\n' in text or '\r' in text:raise ValueError('Invalid control packet.')
    return HEADER.pack(b'CMND',0xD4,HEADER.size+len(payload),0)+payload


class Decoder:
    def __init__(self):self.buffer=bytearray()

    def feed(self,data):
        self.buffer.extend(data);messages=[]
        if len(self.buffer)>1024*1024:raise ValueError('Control output exceeded its buffer limit.')
        while len(self.buffer)>=HEADER.size:
            kind,version,length,handle=HEADER.unpack_from(self.buffer)
            if length<HEADER.size:raise ValueError('Invalid VConsole packet length; header='+bytes(self.buffer[:12]).hex())
            if length>1024*1024:raise ValueError('VConsole packet exceeded its size limit.')
            if len(self.buffer)<length:break
            body=bytes(self.buffer[HEADER.size:length]);del self.buffer[:length]
            if kind==b'PRNT' and len(body)>=28:
                messages.append(body[28:].split(b'\0',1)[0].decode('utf-8',errors='replace'))
        return messages


def listeners(port):
    """Read actual IPv4 TCP listener ownership, never infer it from a title."""
    api=c.WinDLL('iphlpapi');size=w.DWORD()
    api.GetExtendedTcpTable.argtypes=[c.c_void_p,c.POINTER(w.DWORD),w.BOOL,w.ULONG,w.ULONG,w.ULONG]
    status=api.GetExtendedTcpTable(None,c.byref(size),False,2,5,0)
    if status not in (0,122):raise OSError(status,'TCP ownership lookup failed.')
    for _ in range(3):
        buf=c.create_string_buffer(size.value)
        status=api.GetExtendedTcpTable(buf,c.byref(size),False,2,5,0)
        if status==122:continue
        if status:raise OSError(status,'TCP ownership lookup failed.')
        count=struct.unpack_from('<I',buf.raw)[0];result=[]
        for i in range(count):
            state,addr,local,remote,rport,pid=struct.unpack_from('<6I',buf.raw,4+i*24)
            if state==2 and socket.ntohs(local & 0xffff)==port:
                result.append({'pid':pid,'address':socket.inet_ntoa(struct.pack('<I',addr))})
        return result
    raise OSError('TCP ownership table kept changing.')


class LocalGuard:
    """Administrator helper holds only temporary app/port-specific block filters.

    Start before the private engine. Stop only after that engine has exited.
    The separate helper watches this parent and the stop marker; no persistent
    firewall rule, game setting or network-profile preference is written.
    """
    def __init__(self,game):
        self.game=Path(game);self.folder=STATE/'native-controls'/uuid.uuid4().hex
        self.port=49152+secrets.randbelow(16384);self.handle=None;self.process=None

    def healthy(self):
        if not self.handle:return False
        api=c.WinDLL('kernel32');api.WaitForSingleObject.argtypes=[w.HANDLE,w.DWORD]
        return api.WaitForSingleObject(self.handle,0)==258

    def start(self,timeout=45):
        import os
        helper=Path(__file__).parent/'native_capture/build/control_guard.exe'
        if not helper.is_file():raise ValueError('Build the application control guard before testing playback controls.')
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
            probe.bind(('127.0.0.1',self.port))
        self.folder.mkdir(parents=True)
        class ExecuteInfo(c.Structure):
            _fields_=[('cbSize',w.DWORD),('fMask',w.ULONG),('hwnd',w.HWND),('lpVerb',w.LPCWSTR),
                ('lpFile',w.LPCWSTR),('lpParameters',w.LPCWSTR),('lpDirectory',w.LPCWSTR),('nShow',c.c_int),
                ('hInstApp',w.HINSTANCE),('lpIDList',c.c_void_p),('lpClass',w.LPCWSTR),('hkeyClass',w.HKEY),
                ('dwHotKey',w.DWORD),('hIcon',w.HANDLE),('hProcess',w.HANDLE)]
        info=ExecuteInfo();info.cbSize=c.sizeof(info);info.fMask=0x40|0x100;info.lpVerb='runas'
        info.lpFile=str(helper);info.nShow=0
        info.lpParameters=subprocess.list2cmdline([str(os.getpid()),str(self.port),
            str(self.game/'bin/win64/cs2.exe'),str(self.folder)])
        api=c.WinDLL('shell32',use_last_error=True)
        api.ShellExecuteExW.argtypes=[c.POINTER(ExecuteInfo)];api.ShellExecuteExW.restype=w.BOOL
        if not api.ShellExecuteExW(c.byref(info)):raise c.WinError(c.get_last_error())
        self.handle=info.hProcess
        try:
            until=time.monotonic()+timeout
            while time.monotonic()<until:
                result=read_json(self.folder/'guard-result.json',None)
                if result is not None:
                    if not result.get('ok') or len(result.get('filters',[]))!=2 or not all(result['filters']):
                        raise ValueError(f'Local control restriction failed: {result.get("error")}')
                    if result.get('port')!=self.port or not self.healthy():raise ValueError('The control restriction ended.')
                    return self
                if not self.healthy():raise ValueError('The control restriction helper exited before readiness.')
                time.sleep(.1)
            raise TimeoutError('The control restriction did not become ready.')
        except Exception:self.close();raise

    def close(self):
        if self.process and self.process.poll() is None:
            raise ValueError('Stop the owned engine before removing its local control restriction.')
        if self.folder.exists():(self.folder/'stop').touch()
        if self.handle:
            api=c.WinDLL('kernel32');api.WaitForSingleObject.argtypes=[w.HANDLE,w.DWORD]
            api.CloseHandle.argtypes=[w.HANDLE]
            if api.WaitForSingleObject(self.handle,5000)==258:raise TimeoutError('The control restriction is still closing.')
            api.CloseHandle(self.handle);self.handle=None


class Connection:
    def __init__(self,session,guard):
        self.session=session;self.guard=guard;self.socket=None;self.decoder=Decoder();self.verified=False

    def check(self):
        if not self.guard.healthy() or self.session.process.poll() is not None:
            raise ValueError('The contained private playback process is no longer available.')
        found=listeners(self.guard.port)
        if len(found)!=1 or found[0]['pid']!=self.session.process.pid:
            raise ValueError('The control listener does not belong to this private engine.')

    def connect(self):
        self.check()
        self.socket=socket.create_connection(('127.0.0.1',self.guard.port),timeout=2)
        self.check();nonce='TOOLBOX_'+uuid.uuid4().hex
        self.socket.sendall(packet('echo '+nonce))
        messages=self.read_until(lambda s:nonce in s,3)
        if not any(nonce in text for text in messages):raise ValueError('CS2 did not acknowledge the control handshake.')
        self.verified=True;return self

    def read_until(self,predicate,timeout):
        until=time.monotonic()+timeout;messages=[]
        while time.monotonic()<until:
            self.socket.settimeout(min(.25,max(.01,until-time.monotonic())))
            try:data=self.socket.recv(65536)
            except socket.timeout:continue
            if not data:raise ConnectionError('CS2 closed the control connection.')
            new=self.decoder.feed(data);messages.extend(new)
            if sum(map(len,messages))>1024*1024:raise ValueError('Control response exceeded its limit.')
            if any(predicate(line) for line in new):return messages
        return messages

    def send(self,action,value=None):
        if not self.verified:raise ValueError('Playback controls have not completed their handshake.')
        self.check();self.socket.sendall(packet(command(action,value)))

    def request(self,action,value=None):
        self.send(action,value)
        nonce='TOOLBOX_'+uuid.uuid4().hex
        self.socket.sendall(packet('echo '+nonce))
        messages=self.read_until(lambda text:nonce in text,3)
        if not any(nonce in text for text in messages):raise TimeoutError('The engine did not acknowledge the playback request.')
        if any(re.search(r'(?i)(unknown command|not currently playing|version mismatch)',text) for text in messages):
            raise ValueError('The engine rejected the playback request: '+''.join(messages)[-1000:])
        return messages

    def position(self):
        text=''.join(self.request('position'))
        match=re.search(r'Currently playing (\d+) of (\d+) ticks',text)
        if not match:raise ValueError('The engine did not report its demo tick in the expected format.')
        return {'tick':int(match[1]),'end':int(match[2])}

    def close(self):
        self.verified=False
        sock,self.socket=self.socket,None
        if sock:sock.close()


def playback_info(text):
    start=re.search(r'server_start_tick:\s*(\d+)',text)
    ticks=re.search(r'playback_ticks:\s*(\d+)',text)
    seconds=re.search(r'playback_time:\s*([\d.]+)',text)
    if not (ticks and seconds) or float(seconds[1])<=0:raise ValueError('The engine did not report demo duration.')
    rate=int(ticks[1])/float(seconds[1])
    if not 1<=rate<=256:raise ValueError('Unexpected demo tick rate.')
    return {'start_tick':int(start[1]) if start else None,'end':int(ticks[1]),'rate':rate}


def adapter_signature():
    helper=Path(__file__).parent/'native_capture/build/control_guard.exe'
    digest=hashlib.sha256(Path(__file__).read_bytes())
    digest.update(helper.read_bytes())
    return digest.hexdigest()


def record_validation(result):
    required=('pause','resume','speed','seek_forward','seek_backward')
    if not result.get('ok') or not all(result.get(k) for k in
            ('handshake','private_config_confirmed','original_settings_unchanged','owned_process_stopped','screen_size_unchanged','guard_stopped')):
        raise ValueError('The control check did not pass every protection and cleanup gate.')
    if not all(k in result.get('capabilities',[]) for k in required):raise ValueError('Core playback controls were not verified.')
    runtime=result['runtime_fingerprint']
    records=read_json(STATE/'native-control-compatibility.json',{})
    records[runtime]={'adapter':adapter_signature(),'capabilities':result['capabilities'],
                      'camera_requests':bool(result.get('camera_commands_accepted')),'tested_at':time.time()}
    save_json(STATE/'native-control-compatibility.json',records)


def require_verified(runtime):
    record=read_json(STATE/'native-control-compatibility.json',{}).get(runtime['fingerprint'],{})
    try:valid=record.get('adapter')==adapter_signature()
    except OSError:valid=False
    if not valid:raise ValueError('Playback controls need validation for this game version. Uncheck Enable demo controls to watch without them.')
    return record
