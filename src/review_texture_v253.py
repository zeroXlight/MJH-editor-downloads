"""Instrumented WebView UI acceptance: choose template, import, preview, draft only."""
import hashlib,json,sys,time
from pathlib import Path

def review(window,bridge):
    from tkinter import filedialog
    from System import Action
    from System.IO import MemoryStream
    from Microsoft.Web.WebView2.Core import CoreWebView2CapturePreviewImageFormat as Format
    out=(Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent)/'贴图功能验收V2.1.53'
    out.mkdir(exist_ok=True);checks=[];state=bridge.state
    def wait(predicate,timeout=180):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            if predicate():return
            time.sleep(.1)
        raise TimeoutError('贴图验收等待超时：'+str(state().get('status')))
    def nodes(n):
        if not n:return
        yield n
        for c in n.get('children',[]):yield from nodes(c)
        if n.get('body'):yield from nodes(n['body'])
    def command(name,args):bridge.command(name,args);time.sleep(.3)
    def form_nodes():return list(nodes(state()['module']['form']))
    def invoke(text):
        button=next(n for n in form_nodes() if n['kind']=='button' and n['text']==text)
        command('invoke',{'id':button['id']})
    def capture(name):
        time.sleep(.5);holder={}
        def begin():
            holder['stream']=MemoryStream();holder['task']=window.native.browser.webview.CoreWebView2.CapturePreviewAsync(Format.Png,holder['stream'])
        window.native.Invoke(Action(begin));holder['task'].GetAwaiter().GetResult()
        (out/(name+'.png')).write_bytes(bytes(holder['stream'].ToArray()));holder['stream'].Dispose();checks.append(name)
    try:
        print('Texture review: loading editor',flush=True)
        wait(lambda:state().get('equipment',{}).get('saveOptions') and not state().get('busy'))
        game=Path(state()['gamePath']);asset=game/'DreamRivakes_Data/resources.assets';before=hashlib.sha256(asset.read_bytes()).hexdigest()
        command('page',{'page':'role'});wait(lambda:state().get('module',{}).get('loaded') and not state().get('busy'))
        command('set_main',{'key':'roleSearch','value':'霜容'})
        wait(lambda:state()['module'].get('query')=='霜容' and bool(state()['module']['list']['rows']))
        rows=state()['module']['list']['rows'];row=next((r for r in rows if int(r['key'])>=1600000000),rows[0])
        command('select',{'id':state()['module']['list']['id'],'key':row['key']});wait(lambda:state()['module']['current'] is not None)
        form=state()['module']['form'];tab=next(t for t in form['tabs'] if t['label']=='模型贴图')
        command('tab',{'id':form['id'],'key':tab['key']});wait(lambda:state()['module']['form']['selected']==tab['key'])
        step2=next(n for n in form_nodes() if n['kind']=='button' and n['text'].startswith('2. 导入'))
        assert step2['disabled'],'Import must be disabled before choosing template'
        capture('01-先选择模板-导入禁用')
        invoke('1. 选择骨骼/贴图模板');wait(lambda:bool(state()['customDialogs']) and not state()['busy'])
        dialog=state()['customDialogs'][-1];listbox=next(n for n in nodes(dialog['body']) if n['kind']=='list')
        index=next(i for i,s in enumerate(listbox['options']) if 'role_ymlg' in s)
        command('list_select',{'id':listbox['id'],'index':index})
        capture('02-全部骨骼模板选择')
        ok=next(n for n in nodes(state()['customDialogs'][-1]['body']) if n['kind']=='button' and n['text']=='确定')
        command('invoke',{'id':ok['id']});wait(lambda:not state()['customDialogs'])
        assert not next(n for n in form_nodes() if n['kind']=='button' and n['text'].startswith('2. 导入'))['disabled']
        source=Path(r'C:\Users\ADMINI~1\AppData\Local\Temp\codex-clipboard-4c5421f1-abfa-495e-8406-2864f6e6a58e.png')
        original=filedialog.askopenfilename
        try:
            filedialog.askopenfilename=lambda **kw:str(source)
            invoke('2. 导入自定义贴图并绑定人物')
            wait(lambda:not state()['busy'] and len([n for n in form_nodes() if n['kind']=='image'])>=2)
        finally:filedialog.askopenfilename=original
        wait(lambda:window.evaluate_js("document.querySelectorAll('.image-preview img').length>=2 && [...document.querySelectorAll('.image-preview img')].every(i=>i.complete&&i.naturalWidth>0)"),45)
        assert '1254×1254' in str(state()['module']['form']), 'Missing source resize dimensions'
        assert '512×512' in str(state()['module']['form']), 'Missing target resize dimensions'
        capture('03-1254贴图自动缩放及预览')
        command('invoke',{'id':next(b['id'] for b in state()['module']['buttons'] if b['text']=='加入人物草稿')})
        wait(lambda:not state()['busy'] and '已加入草稿' in state()['status'])
        capture('04-独立人物绑定草稿')
        assert hashlib.sha256(asset.read_bytes()).hexdigest()==before
        assert not state().get('errors'),state().get('errors')
        result={'version':'V2.1.53','checks':checks,'draftOnly':True,'gameAssetsUnchanged':True,'controllerErrors':state().get('errors',[]),'jsErrors':window.evaluate_js('window.__reviewErrors||[]')}
        (out/'验收验证.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
        print('Texture review: PASS',flush=True)
    except Exception:
        import traceback
        (out/'验收错误.txt').write_text(traceback.format_exc()+'\n'+str(state()),encoding='utf8');raise
    finally:
        bridge.allow_close=True;window.destroy()
