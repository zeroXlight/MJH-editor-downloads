"""Acceptance on temporary game copies; real game and saves stay read-only."""
import gc,hashlib,json,shutil,tempfile
from pathlib import Path
from unittest.mock import patch
from six_attrs import plan,apply,binary_profile,patch_script,BEGIN,END
from client_config import Assets
from codec import fields,encoded,numeric_list
from martial_editor import indexed_rows
from edition import VERSION,EDITION_NAME

def sha(raw):return hashlib.sha256(raw).hexdigest()

def pure_checks():
    raw=numeric_list(1,[11])+encoded(2,encoded(1,11)+encoded(2,145),2)+encoded(2,encoded(1,19),2)+encoded(3,b'original hash',2)+encoded(33,77)
    out=binary_profile(raw,True);rows,index=indexed_rows(out)
    assert index==list(range(10001,10015))
    assert rows[11]==indexed_rows(raw)[0][11] and rows[19]==indexed_rows(raw)[0][19]
    assert binary_profile(out,False)==raw
    assert binary_profile(out,True)==out
    assert binary_profile(raw,False)==raw
    corrupt=out+encoded(34,1)
    try:binary_profile(corrupt,False)
    except ValueError:pass
    else:raise AssertionError('modified active table accepted')
    return ['原 PC 记录及未索引尾记录保留','转换表启用与关闭逐字节还原','未知 protobuf 字段保留','表幂等与冲突拒绝']

def run(game,output):
    game=Path(game).resolve();output=Path(output);output.mkdir(parents=True,exist_ok=True)
    report={'version':VERSION,'edition':EDITION_NAME,'passed':False,'checks':pure_checks()}
    try:
        preview=plan(game);original_hashes={p:sha(b) for p,b in preview.reads.items() if b is not None}
        save_hashes={p:sha(p.read_bytes()) for p in [game/'Save.sav',*list((game/'SaveFile').rglob('Save.sav'))] if p.is_file()}
        report['preview']=preview.results
        with tempfile.TemporaryDirectory(prefix='mjh-six-',dir=output.resolve()) as tmp:
            root=Path(tmp)
            for path,raw in preview.reads.items():
                if raw is None or not path.is_relative_to(game):continue
                p=root/path.relative_to(game);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
            for folder in ('TableData','ModProject/GameProject/Mod_MJH/Json','装备编辑器配置','mod/editor_model_textures'):
                if (game/folder).exists():shutil.copytree(game/folder,root/folder,dirs_exist_ok=True)
            dll=root/'DreamRivakes_Data/Plugins/ClientDll.dll';dll.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(game/dll.relative_to(root),dll)
            sentinel=root/'Save.sav';sentinel.write_bytes(b'original save format unchanged')
            first=plan(root)
            assert not any(p.suffix.lower()=='.sav' for p in first.payloads)
            old_asset=Assets(first.reads[root/'DreamRivakes_Data/resources.assets'])
            new_asset=Assets(first.payloads[root/'DreamRivakes_Data/resources.assets'])
            changed={n for n in old_asset.scripts if old_asset.data[old_asset.scripts[n][1]+4:old_asset.scripts[n][1]+4+old_asset.scripts[n][2]]!=new_asset.data[new_asset.scripts[n][1]+4:new_asset.scripts[n][1]+4+new_asset.scripts[n][2]]}
            assert changed.issubset({'AttrTrans','AttrTrans.lua','CharacterUI.lua','MartialDataManager.lua','ObserveUI.lua'}),changed
            for name in ('RoleAttrbase.lua','RoleAttrLevelup.lua','KungfuBase.lua'):
                assert old_asset.script(name)==new_asset.script(name)
            with patch('engine.ensure_closed'):backup=apply(first)
            report['changed_resources']=sorted(changed);del first,new_asset,old_asset;gc.collect()
            assert not plan(root).payloads
            report['checks']+=['实际事务备份与写入','重复启用无写入','仅目标资源改变','PC 基础成长和精通每级成长保留']
            enabled=plan(root,False)
            # A stale preview must not overwrite a changed input.
            table=root/'TableData/AttrTrans.bytes';raw=table.read_bytes();table.write_bytes(raw+encoded(35,1))
            with patch('engine.ensure_closed'):
                try:apply(enabled)
                except ValueError as e:assert '变化' in str(e)
                else:raise AssertionError('stale preview accepted')
            table.write_bytes(raw)
            with patch('engine.ensure_closed'):apply(enabled)
            assert not plan(root,False).payloads
            assert table.read_bytes()==binary_profile((game/'TableData/AttrTrans.bytes').read_bytes(),False)
            from growth_runtime import patch_runtime
            assert (root/'DreamRivakes_Data/Plugins/RaceLogic_Release_x64.dll').read_bytes()==patch_runtime((game/'DreamRivakes_Data/Plugins/RaceLogic_Release_x64.dll').read_bytes(),six_attrs=False)
            del enabled;gc.collect()
            # Resource overwrite: repair without editing any save data.
            with patch('engine.ensure_closed'):apply(plan(root))
            shutil.copy2(game/'DreamRivakes_Data/resources.assets',root/'DreamRivakes_Data/resources.assets')
            repair=plan(root);assert root/'DreamRivakes_Data/resources.assets' in repair.payloads
            assert root/'DreamRivakes_Data/Plugins/RaceLogic_Release_x64.dll' not in repair.payloads
            with patch('engine.ensure_closed'):apply(repair)
            assert not plan(root).payloads
            del repair;gc.collect()
            assert sentinel.read_bytes()==b'original save format unchanged'
            report['checks']+=['关闭逐字节恢复原生表和运行库','关闭幂等','过期预览拒绝','资源覆盖后重新启用修复','存档文件未写入']
        assert all(sha(p.read_bytes())==v for p,v in original_hashes.items())
        assert all(sha(p.read_bytes())==v for p,v in save_hashes.items())
        report['checks']+=['真实游戏配置和存档哈希不变'];report['passed']=True
    except Exception:
        import traceback
        report['error']=traceback.format_exc()
        raise
    finally:(output/'六项属性恢复验收.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    return report

def review_ui(window,bridge):
    import sys,time
    def walk(n):
        if not n:return
        yield n
        for child in n.get('children',[]):yield from walk(child)
        if n.get('body'):yield from walk(n['body'])
    def nodes():return list(walk(bridge.state().get('feature')))
    def wait(fn):
        end= time.monotonic()+90
        while time.monotonic()<end:
            if fn():return
            time.sleep(.15)
        raise TimeoutError('六属性界面等待超时')
    out=Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).parent.parent
    doc={'version':VERSION,'edition':EDITION_NAME,'passed':False}
    try:
        wait(lambda:not bridge.state().get('busy') and bridge.state().get('equipment',{}).get('saveOptions'))
        bridge.command('page',{'page':'features'})
        wait(lambda:any(n.get('kind')=='tabs' for n in nodes()))
        notebook=next(n for n in nodes() if n.get('kind')=='tabs')
        tab=next(t for t in notebook['tabs'] if t['label']=='恢复六项属性以及武学攻击')
        bridge.command('tab',{'id':notebook['id'],'key':tab['key']})
        wait(lambda:any(n.get('text')=='预览六项属性恢复' for n in nodes()))
        button=next(n for n in nodes() if n.get('text')=='预览六项属性恢复')
        bridge.command('invoke',{'id':button['id']})
        wait(lambda:any('统一攻击145' in n.get('value','') for n in nodes() if n.get('kind')=='text'))
        assert '恢复六项属性' in window.evaluate_js('document.body.innerText')
        for label in ['恢复精通、属性锻造','恢复武学精通、属性']:
            assert any(n.get('kind')=='check' and n.get('text','').startswith(label) for n in nodes()),[(n.get('kind'),n.get('text')) for n in nodes()]
        assert not bridge.errors,bridge.errors
        doc.update(passed=True,preview_only=True,errors=bridge.errors)
        from System import Action
        from System.IO import MemoryStream
        from Microsoft.Web.WebView2.Core import CoreWebView2CapturePreviewImageFormat as Format
        holder={}
        def capture():
            holder['stream']=MemoryStream();holder['task']=window.native.browser.webview.CoreWebView2.CapturePreviewAsync(Format.Png,holder['stream'])
        window.native.Invoke(Action(capture));holder['task'].GetAwaiter().GetResult()
        (out/'六项属性恢复界面.png').write_bytes(bytes(holder['stream'].ToArray()));holder['stream'].Dispose()
    finally:
        (out/'六项属性恢复界面验收.json').write_text(json.dumps(doc,ensure_ascii=False,indent=2),encoding='utf8')
        bridge.allow_close=True;window.destroy()
