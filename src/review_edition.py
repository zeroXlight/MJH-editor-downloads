"""Read-only acceptance of the exact packaged executable and edition boundary."""
import json,sys,time,io,tempfile
from pathlib import Path
from edition import VERSION,MOBILE_ENABLED,EDITION_NAME,DISPLAY_VERSION

def output():return Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).parent

def review_disguise():
    from disguise_editor import plan,FIRST,LAST,DURATION
    from client_config import Assets
    root=Path(sys.argv[sys.argv.index('--game')+1]) if '--game' in sys.argv else Path(r'D:\game\steam\steamapps\common\xiake')
    payloads,originals,results,notes,_=plan(root)
    assert not notes,notes
    assert all((p.read_bytes() if p.exists() else None)==raw for p,raw in originals.items())
    catalog_path=root/'mod/editor_disguise/catalog.json'
    catalog=json.loads(payloads.get(catalog_path) or originals.get(catalog_path) or catalog_path.read_bytes())
    assert (catalog['first'],catalog['last'])==(FIRST,LAST)
    assert catalog['version']==2
    assert len({o['query_id'] for o in catalog['options']})==len(catalog['options'])
    assert all(('model' in o)!=('drawing' in o) for o in catalog['options'])
    assert sum(o['source']=='mobile' for o in catalog['options'])==(962 if MOBILE_ENABLED else 0)
    assets_path=root/'DreamRivakes_Data/resources.assets'
    data=Assets(payloads.get(assets_path) or originals[assets_path])
    from engine import DATA_ROOT
    assert (DATA_ROOT/'ui_assets/disguise_runtime.lua').read_text(encoding='utf8') in data.script('TableDataManager.lua')
    assert '-- MJH_DISGUISE_UI_V2212' in data.script('DisguiseUI.lua')
    assert '-- MJH_DISGUISE_UI_V223' not in data.script('DisguiseUI.lua')
    from disguise_reference import export
    export(root,(payloads,originals,results,notes,{}),output()/'模型与立绘总表.html')
    report={'version':VERSION,'edition':EDITION_NAME,'frozen_executable':getattr(sys,'frozen',False),
            'options':len(catalog['options']),'duration':DURATION,'reserved_range':[FIRST,LAST],
            'game_unchanged':True,'results':results,'notes':notes,'passed':True}
    (output()/'易容功能验收.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')

def review_resources():
    from mobile_models import catalog,missing_actions,AUXILIARY_TEXTURES,runtime_pending,plan_loader,repair_saved_bindings
    from types import SimpleNamespace
    report={'version':VERSION,'edition':EDITION_NAME,'mobile_enabled':MOBILE_ENABLED}
    if MOBILE_ENABLED:
        c=catalog();models=[m for m in c['models'] if m['id'].startswith('role_') and not missing_actions(m)]
        report.update(bindable_models=len(models),skins=sum(t['name'] not in AUXILIARY_TEXTURES for m in models for t in m['textures']),portraits=len(c['portraits']))
        assert (report['bindable_models'],report['skins'],report['portraits'])==(102,420,542)
    else:
        assert not (output()/'mobile_assets').exists()
        try:catalog()
        except ValueError as e:assert '标准版' in str(e)
        else:raise AssertionError('Standard edition exposed mobile catalog')
        assert runtime_pending(None) is False and plan_loader(None,b'unchanged')==b'unchanged'
        repair_saved_bindings(None)
        report['mobile_access_blocked']=True
    report['passed']=True
    (output()/'版别资源验收.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')

def review_ui(window,bridge):
    def wait(fn,seconds=180):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            if fn():return
            time.sleep(.2)
        raise TimeoutError('版别界面验收等待超时')
    def tabs(node):
        if not node:return None
        if node.get('kind')=='tabs':return node
        for child in node.get('children',[]):
            found=tabs(child)
            if found:return found
        return tabs(node.get('body'))
    def select(rid,query):
        bridge.command('set_main',{'key':'roleSearch','value':query});time.sleep(.4)
        wait(lambda:any(str(r['key'])==str(rid) for r in bridge.state()['module']['list']['rows']))
        bridge.command('select',{'id':bridge.state()['module']['list']['id'],'key':str(rid)})
        wait(lambda:tabs(bridge.state()['module'].get('form')) is not None and str(rid) in window.evaluate_js('document.body.innerText'))
    try:
        wait(lambda:bridge.state().get('equipment',{}).get('saveOptions') and not bridge.state().get('busy'))
        assert bridge.state()['version']==DISPLAY_VERSION
        assert bridge.state()['mobileEnabled']==MOBILE_ENABLED
        bridge.command('page',{'page':'features'})
        wait(lambda:tabs(bridge.state().get('feature')) is not None)
        features=[t['label'] for t in tabs(bridge.state()['feature'])['tabs']]
        assert '易容面具' in features
        assert any(b['text']=='预览易容面具修改' for b in bridge.state()['commands'])
        assert any(b['text']=='应用易容面具修改并备份' for b in bridge.state()['commands'])
        assert any(b['text']=='导出模型与立绘总表' for b in bridge.state()['commands'])
        bridge.command('page',{'page':'role'})
        wait(lambda:bridge.state().get('module',{}).get('loaded') and not bridge.state().get('busy'))
        select(1000012015,'江灵')
        labels=[t['label'] for t in tabs(bridge.state()['module']['form'])['tabs']]
        texts=[b['text'] for b in bridge.state()['commands']]
        assert ('手游模型与立绘' in labels)==MOBILE_ENABLED
        assert ('选择手游模型与皮肤' in texts)==MOBILE_ENABLED
        assert ('选择手游人物立绘' in texts)==MOBILE_ENABLED
        assert '上传立绘图片' in texts and '模型动作绑定检查' in texts
        custom_upload=False
        if MOBILE_ENABLED:
            form=tabs(bridge.state()['module']['form']);mobile_tab=next(t for t in form['tabs'] if t['label']=='手游模型与立绘')
            bridge.command('tab',{'id':form['id'],'key':mobile_tab['key']});time.sleep(.5)
            from role_ui import RolePage
            from tkinter import filedialog
            from mobile_models import catalog,read
            from PIL import Image
            def invoke(text):
                wait(lambda:not bridge.state().get('busy') and any(b['text']==text for b in bridge.state()['commands']))
                bridge.command('invoke',{'id':next(b['id'] for b in bridge.state()['commands'] if b['text']==text)})
                time.sleep(.3)
            upload=next(b for b in bridge.state()['commands'] if b['text']=='上传手游贴图')
            assert upload['disabled']
            old_picker=RolePage.picker;old_open=filedialog.askopenfilename
            try:
                RolePage.picker=lambda page,title,choices,*args,**kwargs:{'id':next(i for i,text in choices if text.startswith('role_ayue / role_ayue ·'))}
                invoke('选择手游模型与皮肤')
                wait(lambda:not bridge.state().get('busy') and 'Spine 3.7' in window.evaluate_js('document.body.innerText'))
                assert not next(b for b in bridge.state()['commands'] if b['text']=='上传手游贴图')['disabled']
                with tempfile.TemporaryDirectory() as tmp:
                    model=next(m for m in catalog()['models'] if m['id']=='role_ayue')
                    image=Image.open(io.BytesIO(read(model['textures'][0]))).convert('RGBA')
                    image=image.resize((1254,1254));image.putpixel((0,0),(251,201,211,17));path=Path(tmp)/'自定义阿月验收.png';image.save(path)
                    filedialog.askopenfilename=lambda *args,**kwargs:str(path)
                    invoke('上传手游贴图')
                    wait(lambda:not bridge.state().get('busy') and '已自动适配：1254×1254 → 512×512' in window.evaluate_js('document.body.innerText') and 'Spine 3.7' in window.evaluate_js('document.body.innerText'))
                    invoke('加入人物草稿')
                    wait(lambda:not bridge.state().get('busy') and '已加入草稿' in bridge.state().get('status',''))
                    invoke('预览手游模型')
                    wait(lambda:not bridge.state().get('busy') and '自定义贴图：自定义阿月验收.png' in window.evaluate_js('document.body.innerText') and 'Spine 3.7' in window.evaluate_js('document.body.innerText'))
                    from System import Action
                    from System.IO import MemoryStream
                    from Microsoft.Web.WebView2.Core import CoreWebView2CapturePreviewImageFormat as Format
                    holder={}
                    def capture():
                        holder['stream']=MemoryStream();holder['task']=window.native.browser.webview.CoreWebView2.CapturePreviewAsync(Format.Png,holder['stream'])
                    window.native.Invoke(Action(capture));holder['task'].GetAwaiter().GetResult()
                    (output()/'手游自定义贴图界面验收.png').write_bytes(bytes(holder['stream'].ToArray()));holder['stream'].Dispose()
                    invoke('恢复模板贴图')
                    wait(lambda:not bridge.state().get('busy') and '使用模板原贴图' in window.evaluate_js('document.body.innerText'))
                    assert next(b for b in bridge.state()['commands'] if b['text']=='恢复模板贴图')['disabled']
                    invoke('加入人物草稿')
                    wait(lambda:not bridge.state().get('busy') and '已加入草稿' in bridge.state().get('status',''))
                    custom_upload=True
            finally:RolePage.picker=old_picker;filedialog.askopenfilename=old_open
        # Existing mobile characters must remain readable even without bundled assets.
        select(1100325003,'南宫离')
        assert not bridge.errors,bridge.errors
        assert window.evaluate_js('JSON.stringify(window.__reviewErrors)')=='[]'
        report={'version':VERSION,'edition':EDITION_NAME,'tabs':labels,'feature_tabs':features,'custom_mobile_texture_upload_and_draft_preview_restore':custom_upload,'existing_mobile_character_readable':True,'no_game_write':True,'errors':bridge.errors,'passed':True}
        (output()/'版别界面验收.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    finally:bridge.allow_close=True;window.destroy()
