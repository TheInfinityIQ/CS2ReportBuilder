"""Decode reference MP4s through Windows to verify the actual saved video."""
import argparse
import ctypes as c
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from native_viewer import capture_library
from jobs import save_json


class VideoFrames:
    """Bounded frame reads from an existing video; never starts a game."""
    def __init__(self,path):
        self.path=Path(path).resolve();self.dll=c.CDLL(str(capture_library()))
        self.dll.nv_video_frame.argtypes=[c.c_wchar_p,c.c_int64,c.c_void_p,c.c_uint32,
                                        c.POINTER(c.c_int),c.POINTER(c.c_int),c.POINTER(c.c_int64),c.POINTER(c.c_int)]
        self.dll.nv_video_frame.restype=c.c_int
        self.width=c.c_int();self.height=c.c_int();self.duration=c.c_int64();self.stride=c.c_int()
        self.read(0)
        size=abs(self.stride.value)*self.height.value
        if not 0<size<128*1024**2:raise ValueError('Decoded frame exceeds bounds')
        self.pixels=(c.c_uint8*size)()

    def read(self,seconds,pixels=None):
        code=self.dll.nv_video_frame(str(self.path),int(seconds*10000000),pixels,len(pixels) if pixels is not None else 0,
                                    c.byref(self.width),c.byref(self.height),c.byref(self.duration),c.byref(self.stride))
        if code!=1:raise ValueError(f'Video decode failed: {self.path.name}: {code:#x}')

    def at(self,seconds):
        from PIL import Image
        self.read(seconds,self.pixels)
        return Image.frombytes('RGB',(self.width.value,self.height.value),bytes(self.pixels),'raw','BGRX',abs(self.stride.value),-1 if self.stride.value>0 else 1)


def check(folder):
    results=[]
    for path in sorted(Path(folder).glob('*.mp4')):
        video=VideoFrames(path);captures=[]
        for seconds in [0,30,45,60]:
            if seconds>=video.duration.value/10000000:continue
            output=path.with_name(path.stem+'-decoded-'+str(seconds)+'.png')
            video.at(seconds).save(output)
            captures.append(str(output))
        results.append({'path':str(path),'width':video.width.value,'height':video.height.value,'duration_seconds':video.duration.value/10000000,
                        'decoded_frames':captures,'bytes':path.stat().st_size})
    save_json(Path(folder)/'video-check.json',{'videos':results})
    return results


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('folder',type=Path)
    print(json.dumps(check(parser.parse_args().folder),indent=2))
