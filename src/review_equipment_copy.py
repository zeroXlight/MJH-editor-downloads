"""Read-only desktop review of the copy dialog and quantity preview."""
from pathlib import Path
import time,json,hashlib,sys
from edition import VERSION,EDITION_NAME

def review_ui(window,bridge):
    out=Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).parent.parent
    doc={'passed':False,'version':VERSION,'edition':EDITION_NAME}
    def walk(n):
        if not n:return
        yield n
        for c in n.get('children',[]):yield from walk(c)
        if n.get('body'):yield from walk(n['body'])
    def wait(fn):
        end=time.monotonic()+120
        while time.monotonic()<end:
            if fn():return
            time.sleep(.15)
        raise TimeoutError('装备复制界面等待超时')
    try:
        wait(lambda:not bridge.state().get('busy') and bridge.state().get('equipment',{}).get('list',{}).get('rows'))
        root=Path(bridge.state()['gamePath'])
        files={root/'Save.sav'}|set((root/'SaveFile').glob('*/Save.sav'))
        before={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in files if p.is_file()}
        state=bridge.state();listing=state['equipment']['list']
        bridge.command('select',{'id':listing['id'],'key':listing['rows'][0]['key']})
        wait(lambda:bool(bridge.state()['equipment']['list']['selected']))
        cmd=next(b for b in bridge.state()['commands'] if b['text']=='复制装备')
        bridge.command('invoke',{'id':cmd['id']})
        wait(lambda:any(d['title']=='复制装备到周目仓库' for d in bridge.state().get('customDialogs',[])))
        def dialog():return next(d for d in bridge.state()['customDialogs'] if d['title']=='复制装备到周目仓库')
        nodes=list(walk(dialog()['body']));quantity=next(n for n in nodes if n['kind']=='input')
        bridge.command('value',{'id':quantity['id'],'value':'3'})
        preview=next(n for n in nodes if n.get('text')=='预览复制');bridge.command('invoke',{'id':preview['id']})
        wait(lambda:any('复制3件到周目仓库' in n.get('text','') for n in walk(dialog()['body'])))
        wait(lambda:not bridge.state()['busy'])
        assert any(n.get('text')=='复制并备份' and not n['disabled'] for n in walk(dialog()['body']))
        assert not bridge.errors,bridge.errors
        time.sleep(.6)
        from System import Action
        from System.IO import MemoryStream
        from Microsoft.Web.WebView2.Core import CoreWebView2CapturePreviewImageFormat as Format
        holder={}
        def capture():
            holder['stream']=MemoryStream();holder['task']=window.native.browser.webview.CoreWebView2.CapturePreviewAsync(Format.Png,holder['stream'])
        window.native.Invoke(Action(capture));holder['task'].GetAwaiter().GetResult()
        (out/'复制装备界面.png').write_bytes(bytes(holder['stream'].ToArray()));holder['stream'].Dispose()
        assert all(hashlib.sha256(p.read_bytes()).hexdigest()==value for p,value in before.items())
        bridge.command('close_dialog',{'id':dialog()['id']})
        doc.update(passed=True,quantity=3,preview_only=True,save_files_unchanged=True)
    finally:
        (out/'复制装备界面验收.json').write_text(json.dumps(doc,ensure_ascii=False,indent=2),'utf8')
        bridge.allow_close=True;window.destroy()
