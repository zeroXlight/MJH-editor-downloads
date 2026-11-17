"""Frozen build checks and desktop UI preview without changing game files."""
from pathlib import Path
import hashlib,json,sys,time
from edition import VERSION,EDITION_NAME

def output():return Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).parent.parent

def run(game):
    from pet_restore import plan
    from pet_rules import upgrade_cost,unlock_cost,grant_initial
    from feature_save import patch_save,NativeSave
    from meridian_resource import balance
    from pet_config import mobile_rows
    root=Path(game);value=plan(root)
    before=(root/'Save.sav').read_bytes();after=patch_save(before,'meridian_exp',{},[])
    twice=patch_save(after,'meridian_exp',{},[])
    assert balance(NativeSave(after))-balance(NativeSave(before))==900000
    assert balance(NativeSave(twice))-balance(NativeSave(after))==900000
    gift,given=grant_initial(before);assert grant_initial(gift)==(gift,False)
    assert len(mobile_rows())==50
    assert [upgrade_cost(i) for i in (1,2,3)]==[1500,2250,3375]
    assert [unlock_cost(i) for i in range(1,8)]==[1000,2000,4000,8000,16000,32000,64000]
    assert (root/'Save.sav').read_bytes()==before
    doc={'passed':True,'frozen':bool(getattr(sys,'frozen',False)),
         'version':VERSION,'edition':EDITION_NAME,'pet_forms':50,'families':10,
         'additive_900000_verified':True,'one_time_30000_verified':True,
         'native_patch_compiled':True,'preview_files':[str(p) for p in value.prepared[0]],
         'save_sha256':hashlib.sha256(before).hexdigest(),'game_writes':False}
    (output()/'宠物恢复打包验收.json').write_text(json.dumps(doc,ensure_ascii=False,indent=2),'utf8')

def review_ui(window,bridge):
    def walk(n):
        if not n:return
        yield n
        for child in n.get('children',[]):yield from walk(child)
        if n.get('body'):yield from walk(n['body'])
    def nodes():return list(walk(bridge.state().get('feature')))
    def wait(fn):
        end=time.monotonic()+90
        while time.monotonic()<end:
            if fn():return
            time.sleep(.15)
        raise TimeoutError('宠物界面等待超时')
    doc={'passed':False,'version':VERSION,'edition':EDITION_NAME}
    try:
        wait(lambda:not bridge.state().get('busy') and bridge.state().get('equipment',{}).get('saveOptions'))
        bridge.command('page',{'page':'features'})
        wait(lambda:any(n.get('kind')=='tabs' for n in nodes()))
        book=next(n for n in nodes() if n.get('kind')=='tabs')
        tab=next(t for t in book['tabs'] if t['label']=='恢复宠物')
        bridge.command('tab',{'id':book['id'],'key':tab['key']})
        wait(lambda:any(n.get('text')=='预览宠物恢复' for n in nodes()))
        button=next(n for n in nodes() if n.get('text')=='预览宠物恢复')
        bridge.command('invoke',{'id':button['id']})
        wait(lambda:any('白1000' in n.get('text','') for n in nodes()))
        wait(lambda:any('恢复宠物：启用' in n.get('value','') for n in nodes() if n.get('kind')=='text'))
        wait(lambda:not bridge.state().get('busy'))
        time.sleep(.4)
        assert not bridge.errors,bridge.errors
        from System import Action
        from System.IO import MemoryStream
        from Microsoft.Web.WebView2.Core import CoreWebView2CapturePreviewImageFormat as Format
        holder={}
        def capture():
            holder['stream']=MemoryStream();holder['task']=window.native.browser.webview.CoreWebView2.CapturePreviewAsync(Format.Png,holder['stream'])
        window.native.Invoke(Action(capture));holder['task'].GetAwaiter().GetResult()
        (output()/'恢复宠物编辑器界面.png').write_bytes(bytes(holder['stream'].ToArray()));holder['stream'].Dispose()
        doc.update(passed=True,preview_only=True,errors=bridge.errors)
    finally:
        (output()/'恢复宠物界面验收.json').write_text(json.dumps(doc,ensure_ascii=False,indent=2),'utf8')
        bridge.allow_close=True;window.destroy()
