"""Exercise integrated mobile controls in the actual desktop window, without saving."""
import json,sys,time
from pathlib import Path
def review(window,bridge):
    from System import Action
    from System.IO import MemoryStream
    from Microsoft.Web.WebView2.Core import CoreWebView2CapturePreviewImageFormat as Format
    from role_ui import RolePage
    out=(Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).parent)/'手游功能验收';out.mkdir(exist_ok=True)
    def wait(fn,seconds=150):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            if fn():return
            time.sleep(.2)
        raise TimeoutError('手游界面验收等待超时')
    def command(name,args):bridge.command(name,args);time.sleep(.4)
    def tabs(node):
        if not node:return None
        if node.get('kind')=='tabs':return node
        for child in node.get('children',[]):
            found=tabs(child)
            if found:return found
        return tabs(node.get('body'))
    def invoke(text):
        wait(lambda:any(b['text']==text for b in bridge.state()['commands']))
        command('invoke',{'id':next(b['id'] for b in bridge.state()['commands'] if b['text']==text)})
    def capture(name):
        time.sleep(.5);holder={}
        def begin():
            holder['stream']=MemoryStream();holder['task']=window.native.browser.webview.CoreWebView2.CapturePreviewAsync(Format.Png,holder['stream'])
        window.native.Invoke(Action(begin));holder['task'].GetAwaiter().GetResult()
        (out/(name+'.png')).write_bytes(bytes(holder['stream'].ToArray()));holder['stream'].Dispose()
    old=RolePage.picker
    try:
        wait(lambda:bridge.state().get('equipment',{}).get('saveOptions') and not bridge.state().get('busy'))
        command('page',{'page':'features'});wait(lambda:tabs(bridge.state().get('feature')) is not None)
        feature=tabs(bridge.state()['feature']);labels=[t['label'] for t in feature['tabs']]
        assert not any('主角立绘' in label for label in labels)
        command('page',{'page':'role'});wait(lambda:bridge.state().get('module',{}).get('loaded') and not bridge.state().get('busy'))
        command('set_main',{'key':'roleSearch','value':'江灵'})
        wait(lambda:any(str(r['key'])=='1000012015' for r in bridge.state()['module']['list']['rows']))
        command('select',{'id':bridge.state()['module']['list']['id'],'key':'1000012015'})
        wait(lambda:tabs(bridge.state()['module'].get('form')) is not None)
        form=tabs(bridge.state()['module']['form']);mobile=next(t for t in form['tabs'] if t['label']=='手游模型与立绘')
        command('tab',{'id':form['id'],'key':mobile['key']})
        def pick(page,title,choices,*args,**kwargs):
            query='role_tangming / role_tangming' if '模型' in title else 'major/major_nv'
            return {'id':next(i for i,text in choices if query in text)}
        RolePage.picker=pick
        invoke('选择手游模型与皮肤')
        wait(lambda:not bridge.state().get('busy') and 'Spine 3.7' in window.evaluate_js('document.body.innerText'))
        assert 'TypeError:' not in window.evaluate_js('document.body.innerText')
        assert window.evaluate_js('JSON.stringify(window.__reviewErrors)') == '[]'
        window.evaluate_js("Array.from(document.querySelectorAll('.module-form *')).filter(e=>e.scrollHeight>e.clientHeight+40&&e.clientHeight>100).forEach(e=>e.scrollTop=120)")
        capture('01-手游模型与动作预览')
        invoke('选择手游人物立绘')
        wait(lambda:'已选择手游人物立绘' in bridge.state().get('status',''))
        (out/'验收结果.json').write_text(json.dumps(dict(version=bridge.state()['version'],feature_tabs=labels,mobile_preview=True,mobile_portrait=True,no_game_write=True,errors=bridge.errors),ensure_ascii=False,indent=2),encoding='utf8')
        assert not bridge.errors,bridge.errors
    finally:RolePage.picker=old;bridge.allow_close=True;window.destroy()
