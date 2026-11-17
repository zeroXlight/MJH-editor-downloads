"""Check the actual saved Jiang Linglu tangming binding through the desktop UI."""
import json,sys,time
from pathlib import Path

def review(window,bridge):
    from System import Action
    from System.IO import MemoryStream
    from Microsoft.Web.WebView2.Core import CoreWebView2CapturePreviewImageFormat as Format
    out=(Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).parent)/'动作验收V2.1.58';out.mkdir(exist_ok=True)
    def wait(fn,seconds=150):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            if fn():return
            time.sleep(.2)
        raise TimeoutError('动作绑定验收等待超时')
    def command(name,args):bridge.command(name,args);time.sleep(.4)
    try:
        wait(lambda:bridge.state().get('equipment',{}).get('saveOptions') and not bridge.state().get('busy'))
        command('page',{'page':'role'});wait(lambda:bridge.state().get('module',{}).get('loaded') and not bridge.state().get('busy'))
        command('set_main',{'key':'roleSearch','value':'江灵'})
        wait(lambda:any(str(r['key'])=='1000012015' for r in bridge.state()['module']['list']['rows']))
        command('select',{'id':bridge.state()['module']['list']['id'],'key':'1000012015'})
        wait(lambda:any(b['text']=='模型动作绑定检查' for b in bridge.state()['commands']))
        command('invoke',{'id':next(b['id'] for b in bridge.state()['commands'] if b['text']=='模型动作绑定检查')})
        wait(lambda:bool(bridge.state().get('dialogs')))
        dialogs=bridge.state()['dialogs'];result={'version':bridge.state()['version'],'dialogs':dialogs,'errors':bridge.errors,'no_game_write':True}
        (out/'验收结果.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
        assert '模型配置编号：1211' in json.dumps(dialogs,ensure_ascii=False),dialogs
        wait(lambda:'模型配置编号：1211' in window.evaluate_js('document.body.innerText'))
        holder={}
        def begin():
            holder['stream']=MemoryStream();holder['task']=window.native.browser.webview.CoreWebView2.CapturePreviewAsync(Format.Png,holder['stream'])
        window.native.Invoke(Action(begin));holder['task'].GetAwaiter().GetResult()
        (out/'tangming动作检查.png').write_bytes(bytes(holder['stream'].ToArray()));holder['stream'].Dispose()
        command('answer',{'id':dialogs[0]['id'],'value':'yes'})
    finally:bridge.allow_close=True;window.destroy()
