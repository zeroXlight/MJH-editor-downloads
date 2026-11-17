"""Exercise both new tabs, native upload callback and preview without applying."""
import json,sys,time
from pathlib import Path

def review(window,bridge):
    from tkinter import filedialog
    from System import Action
    from System.IO import MemoryStream
    from Microsoft.Web.WebView2.Core import CoreWebView2CapturePreviewImageFormat as Format
    from PIL import Image,ImageDraw
    out=(Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).parent)/'功能验收V2.1.57';out.mkdir(exist_ok=True)
    sample=out/'测试立绘.png';im=Image.new('RGBA',(300,500));d=ImageDraw.Draw(im);d.ellipse((100,10,200,110),fill='#eac6a6');d.polygon([(150,80),(260,480),(40,480)],fill='#435d7c');im.save(sample)
    def log(text):
        with (out/'progress.log').open('a',encoding='utf8') as f:f.write(text+'\n')
    def wait(fn,seconds=150):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            if fn():return
            time.sleep(.2)
        raise TimeoutError('功能验收等待超时')
    def command(name,args):bridge.command(name,args);time.sleep(.4)
    def invoke(text):
        wait(lambda:any(x['text']==text for x in bridge.state()['commands']))
        command('invoke',{'id':next(x['id'] for x in bridge.state()['commands'] if x['text']==text)})
    def capture(name):
        time.sleep(.5);holder={}
        def begin():
            holder['stream']=MemoryStream();holder['task']=window.native.browser.webview.CoreWebView2.CapturePreviewAsync(Format.Png,holder['stream'])
        window.native.Invoke(Action(begin));holder['task'].GetAwaiter().GetResult()
        (out/(name+'.png')).write_bytes(bytes(holder['stream'].ToArray()));holder['stream'].Dispose()
    old=filedialog.askopenfilename
    try:
        wait(lambda:bridge.state().get('equipment',{}).get('saveOptions') and not bridge.state().get('busy'))
        log('equipment loaded');command('page',{'page':'features'});log(json.dumps(bridge.state().get('feature'),ensure_ascii=False)[:1500])
        def find_tabs(n):
            if not n:return None
            if n.get('kind')=='tabs':return n
            for child in n.get('children',[]):
                found=find_tabs(child)
                if found:return found
            return find_tabs(n.get('body'))
        wait(lambda:find_tabs(bridge.state().get('feature')))
        form=find_tabs(bridge.state()['feature']);tabs={t['label']:t['key'] for t in form['tabs']}
        command('tab',{'id':form['id'],'key':tabs['交互永久解锁']})
        log('unlock tab selected');invoke('预览永久解锁');log('unlock preview invoked')
        wait(lambda:'盘查、号召、决斗、乞讨：永久解锁' in window.evaluate_js('document.body.innerText'))
        capture('01-交互永久解锁')
        command('tab',{'id':form['id'],'key':tabs['主角立绘（指定存档）']})
        filedialog.askopenfilename=lambda *a,**k:str(sample)
        log('portrait tab selected');invoke('上传主角立绘图片');log('uploaded');invoke('预览主角立绘修改');log('portrait preview invoked')
        wait(lambda:'主角实例：' in window.evaluate_js('document.body.innerText'))
        capture('02-主角立绘预览')
        result={'version':bridge.state()['version'],'tabs':list(tabs),'upload_preview':True,'no_apply':True,'errors':bridge.errors}
        (out/'验收结果.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    finally:
        filedialog.askopenfilename=old;bridge.allow_close=True;window.destroy()
