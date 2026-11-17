from pathlib import Path
import sys,time,json,traceback,hashlib
from edition import VERSION,EDITION_NAME
def review_ui(window,bridge):
    out=(Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).parent.parent)/'验收资料';out.mkdir(exist_ok=True)
    doc=dict(passed=False,version=VERSION,edition=EDITION_NAME)
    def walk(n):
        if not n:return
        yield n
        for c in n.get('children',[]):yield from walk(c)
        if n.get('body'):yield from walk(n['body'])
    def wait(fn,seconds=240):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            if fn():return
            time.sleep(.2)
        raise TimeoutError('大地图兼容界面等待超时')
    def capture(name):
        from System import Action
        from System.IO import MemoryStream
        from Microsoft.Web.WebView2.Core import CoreWebView2CapturePreviewImageFormat as Format
        h={}
        def begin():h['s']=MemoryStream();h['t']=window.native.browser.webview.CoreWebView2.CapturePreviewAsync(Format.Png,h['s'])
        window.native.Invoke(Action(begin));h['t'].GetAwaiter().GetResult();(out/name).write_bytes(bytes(h['s'].ToArray()));h['s'].Dispose()
    def invoke(text):
        wait(lambda:any(b['text']==text for b in bridge.state()['commands']))
        b=next(b for b in bridge.state()['commands'] if b['text']==text);bridge.command('invoke',{'id':b['id']})
    try:
        wait(lambda:bridge.state().get('equipment',{}).get('list',{}).get('rows') and not bridge.state().get('busy'))
        root=Path(bridge.state()['gamePath']);saves={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in [root/'Save.sav',*list((root/'SaveFile').rglob('*.sav'))]}
        rect=window.evaluate_js("(()=>{let e=document.querySelector('.bigmap-compat-button'),r=e.getBoundingClientRect();return {x:r.x,right:r.right,width:innerWidth,label:e.innerText}})()")
        assert rect['right']<=rect['width'] and rect['x']>0,rect;capture('大地图兼容-01入口.png')
        bridge.command('bigmap_compat');wait(lambda:any(d['title']=='兼容大地图版本' for d in bridge.state().get('customDialogs',[])))
        def dialog():return next(d for d in bridge.state()['customDialogs'] if d['title']=='兼容大地图版本')
        nodes=list(walk(dialog()['body']));checks=[n for n in nodes if n['kind']=='check'];assert len(checks)==10
        for n in checks:
            desired=n['text']=='宝箱物品自动入库'
            if n['value']!=desired:bridge.command('check',{'id':n['id']});time.sleep(.15)
        invoke('检查并预览大地图兼容')
        wait(lambda:any('大地图城市、场景和剧情配置保持原样' in str(n.get('value','')) for n in walk(dialog()['body'])) and not bridge.state()['busy'],600)
        window.evaluate_js("let d=document.querySelector('.dialog-scroll');d.scrollTop=d.scrollHeight")
        time.sleep(.5);capture('大地图兼容-02预览.png')
        assert not bridge.errors,bridge.errors
        assert all(hashlib.sha256(p.read_bytes()).hexdigest()==h for p,h in saves.items())
        doc.update(passed=True,button_rect=rect,feature_checkboxes=len(checks),preview_only=True,saves_unchanged=True,errors=bridge.errors)
    except Exception:doc.update(error=traceback.format_exc(),last_state=bridge.state())
    finally:
        (out/'大地图界面验收.json').write_text(json.dumps(doc,ensure_ascii=False,indent=2),'utf8');bridge.allow_close=True;window.destroy()
