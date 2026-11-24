"""Capture only Toolbox's own window for review-layout checks; no desktop automation."""
import argparse
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import time
from unittest.mock import patch

import main
import demo_review
from native_view_panel import NativeViewPanel
from jobs import STATE


def capture(window,path):
    from PIL import Image
    user=ctypes.WinDLL('user32');gdi=ctypes.WinDLL('gdi32')
    user.GetAncestor.argtypes=[wintypes.HWND,wintypes.UINT];user.GetAncestor.restype=wintypes.HWND
    user.GetWindowDC.argtypes=[wintypes.HWND];user.GetWindowDC.restype=wintypes.HDC
    user.GetWindowRect.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.RECT)]
    user.PrintWindow.argtypes=[wintypes.HWND,wintypes.HDC,wintypes.UINT]
    user.ReleaseDC.argtypes=[wintypes.HWND,wintypes.HDC]
    gdi.CreateCompatibleDC.argtypes=[wintypes.HDC];gdi.CreateCompatibleDC.restype=wintypes.HDC
    gdi.CreateCompatibleBitmap.argtypes=[wintypes.HDC,ctypes.c_int,ctypes.c_int];gdi.CreateCompatibleBitmap.restype=wintypes.HBITMAP
    gdi.SelectObject.argtypes=[wintypes.HDC,wintypes.HANDLE];gdi.SelectObject.restype=wintypes.HANDLE
    gdi.GetDIBits.argtypes=[wintypes.HDC,wintypes.HBITMAP,wintypes.UINT,wintypes.UINT,ctypes.c_void_p,ctypes.c_void_p,wintypes.UINT]
    gdi.DeleteObject.argtypes=[wintypes.HANDLE];gdi.DeleteDC.argtypes=[wintypes.HDC]
    handle=user.GetAncestor(window.winfo_id(),2);rect=wintypes.RECT();user.GetWindowRect(handle,ctypes.byref(rect))
    width,height=rect.right-rect.left,rect.bottom-rect.top
    dc=user.GetWindowDC(handle);memory=gdi.CreateCompatibleDC(dc);bitmap=gdi.CreateCompatibleBitmap(dc,width,height)
    previous=gdi.SelectObject(memory,bitmap)
    try:
        if not user.PrintWindow(handle,memory,2):raise RuntimeError('Toolbox window capture failed')
        header=ctypes.create_string_buffer(40)
        import struct
        header.raw=struct.pack('<IiiHHIIiiII',40,width,-height,1,32,0,width*height*4,0,0,0,0)
        pixels=ctypes.create_string_buffer(width*height*4)
        if not gdi.GetDIBits(memory,bitmap,0,height,pixels,header,0):raise RuntimeError('Toolbox capture pixels unavailable')
        Image.frombytes('RGB',(width,height),pixels.raw,'raw','BGRX').save(path)
    finally:
        gdi.SelectObject(memory,previous);gdi.DeleteObject(bitmap);gdi.DeleteDC(memory);user.ReleaseDC(handle,dc)


def run(label,width,height):
    try:ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (OSError,AttributeError):pass
    output=STATE/'review-ui-check';output.mkdir(parents=True,exist_ok=True)
    patches=[patch.object(main.Toolbox,'check_dependencies'),patch.object(main.Toolbox,'save_settings'),
             patch.object(main.Toolbox,'page_download'),patch.object(main.Toolbox,'dark_title'),
             patch.object(NativeViewPanel,'check_version'),patch.object(demo_review.DemoReview,'load_library'),
             patch.object(demo_review.model.Moments,'read',return_value=[])]
    for item in patches:item.start()
    app=main.Toolbox();app.geometry(f'{width}x{height}');app.show_page('viewer');review=app.review_workspace
    entries=demo_review.model.library();review.events.put(('library',None,entries));review.poll()
    app.update();time.sleep(.12);app.update()
    capture(app,output/(label+'-library.png'))
    review.search.set('no-such-demo-for-layout-check');review.filter_games();app.update()
    capture(app,output/(label+'-no-results.png'));review.clear_filters()
    entry=next((e for e in entries if e.get('folder')),None)
    if entry:
        index=review.visible.index(entry);review.games.selection_set(str(index));review.choose_game()
        deadline=time.monotonic()+5
        while not review.match and time.monotonic()<deadline:app.update();time.sleep(.02)
        if hasattr(review,'analysis_tab'):review.tabs.select(review.analysis_tab)
        else:review.tabs.select(0)
        app.update();capture(app,output/(label+'-moments.png'))
        if hasattr(review,'moment_tabs'):
            review.moment_tabs.select(review.event_tab);app.update();capture(app,output/(label+'-events.png'))
            review.moment_tabs.select(review.round_tab)
    if hasattr(review,'analysis_tab'):
        raw=next((e for e in entries if not e.get('folder')),None)
        if raw:
            review.games.selection_set(str(review.visible.index(raw)));review.choose_game()
            review.tabs.select(review.analysis_tab);app.update();capture(app,output/(label+'-no-analysis.png'))
    review.tabs.select(review.embedded_view);app.update();capture(app,output/(label+'-watch.png'))
    print(json.dumps({'library':str(output/(label+'-library.png')),'count':len(entries),'match_loaded':bool(review.match),'width':width,'height':height}))
    for timer in app.tk.call('after','info'):app.tk.call('after','cancel',timer)
    app.close()
    for item in reversed(patches):item.stop()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--label',default='after');parser.add_argument('--width',type=int,default=1180);parser.add_argument('--height',type=int,default=850)
    args=parser.parse_args();run(args.label,args.width,args.height)
