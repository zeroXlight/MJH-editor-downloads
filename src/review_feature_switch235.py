"""Read-only review of the feature switch dialog and chest preview."""
from pathlib import Path
import time,json,sys,hashlib,traceback
from edition import VERSION,EDITION_NAME
def review_ui(window,bridge):
    out=(Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).parent.parent)/'验收资料';out.mkdir(exist_ok=True)
    result=dict(passed=False,version=VERSION,edition=EDITION_NAME)
    def walk(n):
        if not n:return
        yield n
        for c in n.get('children',[]):yield from walk(c)
        if n.get('body'):yield from walk(n['body'])
    def wait(fn):
        deadline=time.monotonic()+180
        while time.monotonic()<deadline:
            if fn():return
            time.sleep(.2)
        raise TimeoutError('功能开关界面等待超时')
    def capture(name):
        from System import Action
        from System.IO import MemoryStream
        from Microsoft.Web.WebView2.Core import CoreWebView2CapturePreviewImageFormat as Format
        h={}
        def begin():h['s']=MemoryStream();h['t']=window.native.browser.webview.CoreWebView2.CapturePreviewAsync(Format.Png,h['s'])
        window.native.Invoke(Action(begin));h['t'].GetAwaiter().GetResult();(out/name).write_bytes(bytes(h['s'].ToArray()));h['s'].Dispose()
    def invoke(label):
        wait(lambda:any(b['text']==label for b in bridge.state()['commands']))
        b=next(b for b in bridge.state()['commands'] if b['text']==label);bridge.command('invoke',{'id':b['id']})
    try:
        wait(lambda:not bridge.state().get('busy') and bridge.state().get('equipment',{}).get('list',{}).get('rows'))
        root=Path(bridge.state()['gamePath']);files=[root/'Save.sav',*list((root/'SaveFile').glob('*/Save.sav'))]
        before={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in files if p.is_file()}
        bridge.command('page',{'page':'features'})
        wait(lambda:any(n.get('kind')=='tabs' for n in walk(bridge.state().get('feature'))))
        form=next(n for n in walk(bridge.state()['feature']) if n['kind']=='tabs');tab=next(t for t in form['tabs'] if t['label']=='交互永久解锁')
        bridge.command('tab',{'id':form['id'],'key':tab['key']})
        invoke('预览宝箱自动入库');wait(lambda:'宝箱奖励入口' not in bridge.state().get('status','') and not bridge.state().get('busy'))
        wait(lambda:'开箱奖励按游戏原有掉落方案' in window.evaluate_js('document.body.innerText'))
        rect=window.evaluate_js("(()=>{let b=document.querySelector('.feature-manager-button'),r=b.getBoundingClientRect();return {x:r.x,right:r.right,width:innerWidth,label:b.innerText}})()")
        assert rect['right']>rect['width']*.8,rect
        window.evaluate_js("Array.from(document.querySelectorAll('button')).find(b=>b.innerText==='预览宝箱自动入库').scrollIntoView({block:'center'})")
        time.sleep(.5)
        capture('01-宝箱自动入库.png')
        bridge.command('manage_features')
        wait(lambda:any(d['title']=='管理已启用功能' for d in bridge.state().get('customDialogs',[])))
        def dialog():return next(d for d in bridge.state()['customDialogs'] if d['title']=='管理已启用功能')
        nodes=list(walk(dialog()['body']));(out/'功能开关界面节点.json').write_text(json.dumps(nodes,ensure_ascii=False,indent=2),'utf8')
        check=next(n for n in nodes if '宝箱物品自动入库' in n.get('text','') and n['kind']=='check')
        bridge.command('check',{'id':check['id'],'value':True})
        invoke('预览关闭选中功能')
        wait(lambda:any('宝箱物品自动入库：关闭' in str(n.get('value',n.get('text',''))) for n in walk(dialog()['body'])) and not bridge.state().get('busy'))
        capture('02-按功能关闭预览.png')
        window.evaluate_js("let d=document.querySelector('.dialog-scroll');d.scrollTop=d.scrollHeight")
        time.sleep(.5);capture('03-关闭结果预览.png')
        assert not bridge.errors,bridge.errors
        assert all(hashlib.sha256(p.read_bytes()).hexdigest()==h for p,h in before.items())
        result.update(passed=True,header_button=rect,chest_tab_preview=True,selected_disable_preview=True,preview_only=True,saves_unchanged=True,errors=bridge.errors)
    except Exception:result.update(error=traceback.format_exc(),last_state=bridge.state())
    finally:
        (out/'功能开关界面验收.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf8')
        bridge.allow_close=True;window.destroy()
