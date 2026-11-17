"""Offline Windows desktop shell: Fluent UI + Ant Design + Edge WebView2."""
import ctypes,json,os,sys,threading,time,traceback
from pathlib import Path

from edition import DISPLAY_VERSION
TITLE='梦江湖 - 已有装备/武学/人物编辑器 '+DISPLAY_VERSION+' --made by 零光6.1sol'

class DesktopAPI:
    def __init__(self,bridge,updater):
        self._bridge=bridge
        self._updater=updater
    def state(self,revision=None):
        snapshot=dict(self._bridge.state())
        update=self._updater.snapshot()
        snapshot['revision']=f"{snapshot.get('revision')}:{json.dumps(update, sort_keys=True)}"
        snapshot['update']=update
        return None if revision is not None and snapshot.get('revision')==revision else snapshot
    def command(self,name,args=None):return self._bridge.command(name,args)
    def update(self,action,mode=None):
        if action == 'mode':self._updater.change_mode(mode)
        elif action == 'check':self._updater.check()
        elif action == 'download':self._updater.download()
        elif action == 'cancel':self._updater.cancel()
        elif action in ('source','components'):self._updater.open_current(source=action == 'source')
        else:raise ValueError('未知更新操作。')
        return self._updater.snapshot()

def main():
    if '--blank-manual-shop-review' in sys.argv:
        from review_blank_manual_shop import run
        run();return
    if '--team-head-review' in sys.argv:
        from review_team_head import run
        run();return
    if '--object-anchor-review' in sys.argv:
        from review_object_anchor import run
        run();return
    if '--object-identity-review' in sys.argv:
        from review_object_identity import run
        run();return
    if '--role-dependencies-review' in sys.argv:
        from review_role_dependencies import run
        run();return
    if '--role-placement-review' in sys.argv:
        from review_role_placement import run
        run();return
    if '--nov15-runtime-review' in sys.argv:
        from review_nov15 import run
        run();return
    if '--nov5-runtime-review' in sys.argv:
        from review_nov5 import run
        run();return
    if '--shadow-bigmap-review' in sys.argv:
        from review_shadow_bigmap import run
        run();return
    if '--save-format-review' in sys.argv:
        from review_save_format import run
        run();return
    if '--role-breakthrough-review' in sys.argv:
        from review_role_breakthrough import run
        run();return
    if '--six-attrs-review' in sys.argv:
        from review_six238 import run
        run();return
    if '--release-review' in sys.argv:
        from review_release217 import run
        try:run()
        except Exception:
            from review_edition import output
            (output()/'发布验收失败.txt').write_text(traceback.format_exc(),'utf8')
            raise SystemExit(1)
        return
    if '--pet-review' in sys.argv:
        from review_pets import run
        game=sys.argv[sys.argv.index('--game')+1] if '--game' in sys.argv else r'D:\game\steam\steamapps\common\xiake'
        run(game);return
    if '--portrait-review' in sys.argv:
        from review_portraits import run
        run();return
    if '--shadow-load-review' in sys.argv:
        from library_cache import load_catalog
        from engine import Save,digest
        from edition import VERSION,EDITION_NAME
        game=Path(sys.argv[sys.argv.index('--game')+1]).resolve()
        before=digest((game/'Save.sav').read_bytes())
        catalog=load_catalog(game);save=Save(game/'Save.sav',catalog)
        assert save.patched({})==save.data
        from mod_compatibility import native_supported
        result={'passed':catalog.supported and native_supported(game),'version':VERSION,'edition':EDITION_NAME,
                'status':getattr(catalog,'shadow_status',''),'records':len(save.records),
                'unknown_templates':save.unknown_count,'main_role':save.main_role,
                'save_unchanged':digest((game/'Save.sav').read_bytes())==before}
        out=Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).parent.parent
        (out/'暗影自动兼容打包验收.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf8')
        if not result['passed']:raise SystemExit(2)
        return
    if '--six-preview-review' in sys.argv:
        from six_attrs import plan
        from edition import VERSION,EDITION_NAME
        game=sys.argv[sys.argv.index('--game')+1] if '--game' in sys.argv else r'D:\game\steam\steamapps\common\xiake'
        out=Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).parent.parent
        p=plan(game,True,'--restore-forge' in sys.argv,'--restore-martial' in sys.argv)
        (out/'六项属性打包验收.json').write_text(json.dumps({'passed':True,'version':VERSION,'edition':EDITION_NAME,'files':[str(p) for p in p.payloads],'results':p.results},ensure_ascii=False,indent=2),encoding='utf8')
        return
    if '--mastery-review' in sys.argv:
        from review_mastery import run
        game=sys.argv[sys.argv.index('--game')+1] if '--game' in sys.argv else r'D:\game\steam\steamapps\common\xiake'
        output=Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).parent.parent
        run(game,output)
        return
    if '--disguise-review' in sys.argv:
        from review_edition import review_disguise,output
        try:review_disguise()
        except Exception:
            from edition import VERSION,EDITION_NAME
            (output()/'易容功能验收.json').write_text(json.dumps({'version':VERSION,'edition':EDITION_NAME,'passed':False,'error':traceback.format_exc()},ensure_ascii=False,indent=2),encoding='utf8')
            raise SystemExit(1)
        return
    if '--edition-review' in sys.argv:
        from review_edition import review_resources
        review_resources();return
    if '--mobile-review' in sys.argv:
        from review_mobile260 import review
        review();return
    if '--hd-texture-review' in sys.argv:
        from review_hd259 import review
        review();return
    try:ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:pass
    import webview
    if any(a in sys.argv for a in ('--edition-ui-review','--feature-switch-review','--bigmap-ui-review','--feature-drag-review')) and '--game' in sys.argv:
        import app
        app.DEFAULT_GAME=sys.argv[sys.argv.index('--game')+1]
        if any(a in sys.argv for a in ('--feature-switch-review','--bigmap-ui-review','--feature-drag-review')):
            app.PREFS=Path(app.DEFAULT_GAME)/'装备编辑器配置/界面验收偏好.json'
    from desktop_bridge import DesktopBridge
    from editor_update import APP_MUTEX, EditorUpdate
    from engine import DATA_ROOT
    updater=EditorUpdate()
    updates_enabled=not any(a.startswith('--') and '-review' in a for a in sys.argv)
    kernel=ctypes.windll.kernel32
    kernel.CreateMutexW.restype=ctypes.c_void_p
    mutex=kernel.CreateMutexW(None,False,APP_MUTEX)
    bridge=DesktopBridge();bridge.start()
    entry=DATA_ROOT/'desktop_ui/dist/index.html'
    if not entry.is_file():raise FileNotFoundError('缺少离线界面资源：'+str(entry))
    window=webview.create_window(TITLE,str(entry),js_api=DesktopAPI(bridge,updater),width=1600,height=940,min_size=(1280,800),
                                 background_color='#f4f0e8',text_select=True)
    bridge.window=window
    close_result={}
    close_mode=next((a.split('=',1)[1] for a in sys.argv if a.startswith('--close-review=')),None)
    loaded=threading.Event();window.events.loaded+=loaded.set
    def closing():
        if bridge.allow_close:return True
        # FormClosing runs on WinForms' UI thread. Calling evaluate_js here
        # waits for that same thread and deadlocks WebView2.
        bridge.command('close')
        return False
    window.events.closing+=closing
    def after_start():
        if not loaded.wait(90):return
        if updates_enabled:updater.check()
        try:
            from System import Action
            from System.Drawing import Icon
            def set_icon():window.native.Icon=Icon(str(DATA_ROOT/'app.ico'))
            window.native.Invoke(Action(set_icon))
            size=window.evaluate_js('({w:innerWidth,h:innerHeight})')
            window.resize(window.width+1600-size['w'],window.height+900-size['h'])
            if '--feature-drag-review' in sys.argv:
                from review_feature_drag import review_ui
                review_ui(window,bridge)
            elif '--bigmap-ui-review' in sys.argv:
                from review_bigmap236 import review_ui
                review_ui(window,bridge)
            elif '--feature-switch-review' in sys.argv:
                from review_feature_switch235 import review_ui
                review_ui(window,bridge)
            elif '--copy-ui-review' in sys.argv:
                from review_equipment_copy import review_ui
                review_ui(window,bridge)
            elif '--six-ui-review' in sys.argv:
                from review_six_attrs import review_ui
                review_ui(window,bridge)
            elif '--mastery-ui-review' in sys.argv:
                from review_mastery import review_ui
                review_ui(window,bridge)
            elif '--edition-ui-review' in sys.argv:
                from review_edition import review_ui
                review_ui(window,bridge)
            elif '--mobile-ui-review' in sys.argv:
                from review_mobile_ui260 import review as review_mobile_ui
                review_mobile_ui(window,bridge)
            elif '--animation-review' in sys.argv:
                from review_animation258 import review as review_animation
                review_animation(window,bridge)
            elif '--pet-ui-review' in sys.argv:
                from review_pets import review_ui
                review_ui(window,bridge)
            elif '--features-review' in sys.argv:
                from review_features257 import review as review_features
                review_features(window,bridge)
            elif '--texture-review' in sys.argv:
                from review_texture_v253 import review as review_texture
                review_texture(window,bridge)
            elif '--image-review' in sys.argv:review_images(window,bridge)
            elif close_mode:close_result.update(review_close(window,bridge,close_mode))
            elif '--ui-review' in sys.argv:review(window,bridge)
        except Exception:
            if '--six-ui-review' in sys.argv:
                from review_six_attrs import review_ui
                review_ui(window,bridge)
            elif '--mastery-ui-review' in sys.argv:
                out=Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).parent.parent
                (out/'恢复武学精通界面验收.json').write_text(json.dumps({'passed':False,'error':traceback.format_exc()},ensure_ascii=False,indent=2),encoding='utf-8')
            path=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'MengJiangHuEquipEditor'
            path.mkdir(exist_ok=True,parents=True);(path/'desktop_v2150_error.log').write_text(traceback.format_exc(),encoding='utf8')
            if close_mode:close_result['error']=traceback.format_exc()
            if '--feature-drag-review' in sys.argv or '--copy-ui-review' in sys.argv or '--mastery-ui-review' in sys.argv or '--edition-ui-review' in sys.argv or '--mobile-ui-review' in sys.argv or '--animation-review' in sys.argv or '--features-review' in sys.argv or '--pet-ui-review' in sys.argv or '--ui-review' in sys.argv or '--image-review' in sys.argv or '--texture-review' in sys.argv or close_mode:
                bridge.allow_close=True;window.destroy()
    try:webview.start(after_start,gui='edgechromium',debug=False)
    finally:
        stopped=bridge.stop()
        if mutex:kernel.CloseHandle(ctypes.c_void_p(mutex))
        if updates_enabled and stopped and bridge.allow_close:
            updater.after_close()
        if close_mode:
            close_result.update(controllerStopped=stopped,controllerErrors=bridge.errors)
            out=Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent
            (out/('关闭验证-'+close_mode+'.json')).write_text(json.dumps(close_result,ensure_ascii=False,indent=2),encoding='utf8')

def review_close(window,bridge,mode):
    """Exercise native WM_CLOSE, including cancellation and a nested picker."""
    closed=threading.Event();window.events.closed+=closed.set
    def wait(predicate,timeout=45):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            if predicate():return
            time.sleep(.05)
        raise TimeoutError('关闭验收等待超时：'+mode)
    state=bridge.state
    wait(lambda:state().get('equipment',{}).get('saveOptions') and not state().get('busy'))
    data=state()['equipment'];row=data['list']['rows'][0]
    bridge.command('select',{'id':data['list']['id'],'key':row['key']});time.sleep(.3)
    if mode=='cancel':
        bridge.command('set_main',{'key':'grade','value':int(state()['equipment']['grade'])+1})
        wait(lambda:state().get('dirty',0)>0)
    if mode=='dialog':
        tree=state()['equipment']['groups']['white']
        bridge.command('select',{'id':tree['id'],'key':tree['rows'][0]['key']})
        bridge.command('attr',{'key':'white','mode':'edit'})
        wait(lambda:bool(state()['customDialogs']))
    def close():
        ctypes.windll.user32.PostMessageW(ctypes.c_void_p(window.native.Handle.ToInt64()),0x10,0,0)
    start=time.monotonic();close()
    cancelled=False
    if mode=='cancel':
        wait(lambda:bool(state()['dialogs']))
        for _ in range(8):close()
        time.sleep(.3)
        assert len(state()['dialogs'])==1,'重复关闭产生重复确认框'
        bridge.command('answer',{'id':state()['dialogs'][0]['id'],'value':'no'})
        wait(lambda:not bridge.close_pending and not state()['dialogs'])
        assert not closed.is_set() and window.evaluate_js('1+1')==2
        cancelled=True;close();wait(lambda:bool(state()['dialogs']))
        start=time.monotonic()
        bridge.command('answer',{'id':state()['dialogs'][0]['id'],'value':'yes'})
    wait(closed.is_set,10)
    return {'mode':mode,'nativeClose':True,'cancelKeepsResponsive':cancelled,'closeSeconds':round(time.monotonic()-start,3)}

def review_images(window,bridge):
    """Exercise original upload/render callbacks with drafts only, never save."""
    from tkinter import filedialog
    from System import Action
    from System.IO import MemoryStream
    from Microsoft.Web.WebView2.Core import CoreWebView2CapturePreviewImageFormat as Format
    out=(Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent)/'图片预览验收V2.1.51'
    out.mkdir(exist_ok=True);checks=[]
    def wait(predicate,timeout=90):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            if predicate():return
            time.sleep(.08)
        raise TimeoutError('图片预览验收超时')
    state=bridge.state
    def nodes(n):
        if not n:return
        yield n
        for child in n.get('children',[]):yield from nodes(child)
        if n.get('body'):yield from nodes(n['body'])
    def command(name,args):bridge.command(name,args);time.sleep(.25)
    def invoke(text):command('invoke',{'id':next(b for b in state()['commands'] if b['text']==text)['id']})
    def images(n):return [i for i in nodes(n) if i['kind']=='image']
    def dialog():return state().get('customDialogs',[])
    def image_ready():return window.evaluate_js("[...document.querySelectorAll('.editor-modal img')].some(i=>i.complete&&i.naturalWidth>0)")
    def capture(name):
        time.sleep(.4);holder={}
        def begin():
            holder['stream']=MemoryStream()
            holder['task']=window.native.browser.webview.CoreWebView2.CapturePreviewAsync(Format.Png,holder['stream'])
        window.native.Invoke(Action(begin));holder['task'].GetAwaiter().GetResult()
        (out/(name+'.png')).write_bytes(bytes(holder['stream'].ToArray()));holder['stream'].Dispose()
        checks.append(name)
    wait(lambda:state().get('equipment',{}).get('saveOptions') and not state().get('busy'))
    command('page',{'page':'role'});wait(lambda:state().get('module',{}).get('loaded') and not state().get('busy'))
    command('set_main',{'key':'roleSearch','value':'霜容'});wait(lambda:0<state()['module']['pagination']['total']<20)
    rows=state()['module']['list']['rows'];row=next((r for r in rows if int(r['key'])>=1600000000),rows[0])
    command('select',{'id':state()['module']['list']['id'],'key':row['key']})
    wait(lambda:bool(images(state()['module']['form'])))
    capture('01-已保存立绘缩略图')
    invoke('三场景立绘预览 / 调整构图');wait(lambda:bool(dialog()) and bool(images(dialog()[-1]['body'])));wait(image_ready)
    previous=None
    for label in ('普通对话','人物属性面板','互动转盘'):
        radio=next(n for n in nodes(dialog()[-1]['body']) if n['kind']=='radio' and n['text']==label)
        command('check',{'id':radio['id']})
        wait(lambda:bool(images(dialog()[-1]['body'])))
        if previous:wait(lambda:images(dialog()[-1]['body'])[0]['src']!=previous)
        wait(image_ready);previous=images(dialog()[-1]['body'])[0]['src'];capture('02-三场景-'+label)
    invoke('完成');wait(lambda:not dialog())
    source=next((Path(state()['gamePath'])/'ModProject/GameProject/Mod_MJH/Source/Other/role_editor').glob('*.png'))
    picker=filedialog.askopenfilename
    try:
        filedialog.askopenfilename=lambda **kw:str(source)
        invoke('上传立绘图片');wait(lambda:bool(dialog()) and bool(images(dialog()[-1]['body'])));wait(image_ready)
        before=images(dialog()[-1]['body'])[0]['src']
        slider=next(n for n in nodes(dialog()[-1]['body']) if n['kind']=='slider')
        command('value',{'id':slider['id'],'value':1.35})
        wait(lambda:images(dialog()[-1]['body'])[0]['src']!=before);capture('03-上传立绘调整构图')
        invoke('完成');wait(lambda:not dialog())
        form=state()['module']['form'];tab=next(t for t in form['tabs'] if t['label']=='队伍头像')
        command('tab',{'id':form['id'],'key':tab['key']})
        invoke('上传队伍头像');wait(lambda:bool(images(state()['module']['form'])))
        before=images(state()['module']['form'])[0]['src'];capture('04-队伍头像上传预览')
        slider=next(n for n in nodes(state()['module']['form']) if n['kind']=='slider')
        command('value',{'id':slider['id'],'value':1.5})
        wait(lambda:images(state()['module']['form'])[0]['src']!=before);capture('05-队伍头像裁剪调整')
    finally:filedialog.askopenfilename=picker
    result={'version':'V2.1.51','checks':checks,'errors':state().get('errors',[]),'jsErrors':window.evaluate_js('window.__reviewErrors||[]'),'draftOnly':True}
    (out/'图片预览验证.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    bridge.command('close');wait(lambda:bool(state()['dialogs']))
    bridge.command('answer',{'id':state()['dialogs'][0]['id'],'value':'yes'})

def review(window,bridge):
    """Exercise real UI through WebView, read data, and capture the actual HWND."""
    from System import Action
    from System.IO import MemoryStream
    from Microsoft.Web.WebView2.Core import CoreWebView2CapturePreviewImageFormat
    out=(Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent)/'UI验收V2.1.51';out.mkdir(exist_ok=True)
    errors=[];checks=[]
    def wait(predicate,timeout=180):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            if predicate():return
            time.sleep(.25)
        raise TimeoutError('UI review timed out')
    def state():return bridge.state()
    wait(lambda:bool(state().get('version')))
    wait(lambda:state().get('equipment',{}).get('saveOptions') and not state().get('busy'))
    wait(lambda:window.evaluate_js("!!document.querySelector('.desktop-app')"),timeout=45)
    def capture(name):
        time.sleep(.7)
        # Chromium is GPU-composited; PrintWindow only returns its background.
        # CapturePreviewAsync is the renderer's native, unobscured screenshot.
        holder={}
        def begin():
            stream=MemoryStream();holder['stream']=stream
            holder['task']=window.native.browser.webview.CoreWebView2.CapturePreviewAsync(CoreWebView2CapturePreviewImageFormat.Png,stream)
        window.native.Invoke(Action(begin))
        holder['task'].GetAwaiter().GetResult()
        raw=bytes(holder['stream'].ToArray());holder['stream'].Dispose()
        (out/(name+'.png')).write_bytes(raw)
        size=window.evaluate_js('({w:innerWidth,h:innerHeight})')
        (out/(name+'.txt')).write_text(window.evaluate_js('document.body.innerText'),encoding='utf8')
        checks.append({'capture':name,'size':[size['w'],size['h']]})
        if not getattr(sys,'frozen',False):print('Captured '+name,flush=True)
    def click(selector):
        result=window.evaluate_js(f"(()=>{{const e=document.querySelector({json.dumps(selector)});if(!e)return false;e.click();return true}})()")
        if not result:raise RuntimeError('Missing UI target '+selector)
        time.sleep(.5)
    def command(name,args):bridge.command(name,args);time.sleep(.5)
    def all_tabs():
        form=state()['module']['form']
        for tab in form['tabs']:
            command('tab',{'id':form['id'],'key':tab['key']})
            wait(lambda:state()['module']['form']['selected']==tab['key'])
        checks.append({'page':state()['page'],'tabs_checked':len(form['tabs'])})
        command('tab',{'id':form['id'],'key':form['tabs'][0]['key']})
    row=state()['equipment']['list']['rows'][0]
    command('select',{'id':state()['equipment']['list']['id'],'key':row['key']})
    capture('01-装备编辑-1600x900')
    # Grade changes are draft-only; revert through the actual existing callback.
    grade=state()['equipment']['grade'];command('set_main',{'key':'grade','value':min(20,int(grade)+1)})
    wait(lambda:state().get('dirty',0)>0)
    revert=next(b for b in state()['commands'] if b['text']=='撤销这件装备的存档修改')
    command('invoke',{'id':revert['id']});wait(lambda:not state().get('dirty'))
    checks.append({'draft_grade_revert':True})
    # Open and cancel the real existing attribute picker through the new modal.
    command('attr',{'key':'white','mode':'edit'})
    # A row must be selected before edit; use the actual table selection.
    if not state()['customDialogs']:
        tree=state()['equipment']['groups']['white'];command('select',{'id':tree['id'],'key':tree['rows'][0]['key']})
        command('attr',{'key':'white','mode':'edit'})
    wait(lambda:bool(state()['customDialogs']))
    capture('02-装备词条编辑对话框')
    dialog=state()['customDialogs'][-1];command('close_dialog',{'id':dialog['id']});wait(lambda:not state()['customDialogs'])
    click('[role="tab"][value="features"]') if False else command('page',{'page':'features'})
    wait(lambda:state().get('page')=='features' and 'feature' in state());capture('03-功能修改')
    command('page',{'page':'martial'});wait(lambda:state().get('module',{}).get('loaded') and not state().get('busy'))
    capture('04-武学编辑')
    all_tabs()
    scope=next(b for b in state()['commands'] if b['text']=='新增词条 / 作用范围')
    command('invoke',{'id':scope['id']});wait(lambda:bool(state()['customDialogs']))
    area=next(b for b in state()['commands'] if b['text']=='新增 / 编辑技能作用范围（命名 / 5×8 网格）')
    command('invoke',{'id':area['id']})
    wait(lambda:bool(state()['customDialogs']) and state()['customDialogs'][-1]['title']=='新增 / 编辑技能作用范围')
    def nodes(node):
        if not node:return
        yield node
        for child in node.get('children',[]):yield from nodes(child)
        if node.get('body'):yield from nodes(node['body'])
    grid=next(n for n in nodes(state()['customDialogs'][-1]['body']) if n['kind']=='canvas')
    for event,x,y in [('down',.1,.1),('move',.35,.35),('up',.35,.35)]:command('canvas',{'id':grid['id'],'event':event,'x':x,'y':y})
    window.evaluate_js("document.querySelector('.editor-modal .remote-canvas').scrollIntoView({block:'center'})")
    capture('07-武学范围网格')
    command('close_dialog',{'id':state()['customDialogs'][-1]['id']});wait(lambda:not state()['customDialogs'])
    command('page',{'page':'role'});wait(lambda:state().get('module',{}).get('loaded') and state()['page']=='role' and not state().get('busy'))
    rows=state()['module']['list']['rows']
    command('select',{'id':state()['module']['list']['id'],'key':rows[0]['key']})
    capture('05-人物编辑')
    all_tabs()
    command('page',{'page':'equipment'})
    size=window.evaluate_js('({w:innerWidth,h:innerHeight})');window.resize(window.width+1280-size['w'],window.height+800-size['h']);time.sleep(1)
    capture('06-装备编辑-1280x800')
    overflow=window.evaluate_js("({horizontal:document.documentElement.scrollWidth>innerWidth,vertical:document.documentElement.scrollHeight>innerHeight})")
    errors.extend(state().get('errors',[]));errors.extend(window.evaluate_js('window.__reviewErrors||[]'))
    result={'version':'V2.1.51','checks':checks,'errors':errors,'viewportOverflow':overflow,
            'windowTitle':window.title,'signaturePresent':'兰霜容天下第一！' in window.evaluate_js('document.body.textContent'),
            'libraries':{'FluentUI':'@fluentui/react-components','AntDesign':'antd'},'actualDataRows':len(state()['equipment']['list']['rows'])}
    (out/'验收验证.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    if not getattr(sys,'frozen',False):print(json.dumps(result,ensure_ascii=False),flush=True)
    bridge.allow_close=True;window.destroy()

if __name__=='__main__':
    try:main()
    except Exception:
        if any(arg.startswith('--') and arg.endswith('-review') for arg in sys.argv):
            out=Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent
            (out/'后台验收失败.txt').write_text(traceback.format_exc(),'utf8')
            raise SystemExit(1)
        raise
