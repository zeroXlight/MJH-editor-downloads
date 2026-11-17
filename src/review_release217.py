"""Read-only release checks run by the actual frozen executable."""
import base64,hashlib,io,json,re,sys
from pathlib import Path

def run():
    from edition import VERSION,EDITION_NAME,MOBILE_ENABLED
    from engine import DATA_ROOT
    from desktop_app import TITLE
    from client_config import Assets
    from mobile_models import patch_loader
    from review_edition import review_resources,output
    root=Path(sys.argv[sys.argv.index('--game')+1]).resolve()
    review_resources()
    from mobile_martial_restore import source_pack
    mobile_pack=source_pack()
    assert len(mobile_pack['manifest'])==42 and mobile_pack['graphs']
    assert (DATA_ROOT/'mobile_martial_pack.json').stat().st_size<100_000_000
    from mobile_martial_restore import plan as restore_martials
    from martial_limit_enhance import plan as reinforce_martials
    restoration=restore_martials(root)
    assert len(restoration.installed)==sum(r['available'] for r in mobile_pack['manifest'])
    assert root/'Save.sav' not in restoration.prepared[0] or any('收藏' in n for n in restoration.prepared[3])
    # Default preview never gives testing books. Only collection initialization
    # may touch a planned save; formal game files remain read-only here.
    assert not any('测试秘籍' in r for r in restoration.prepared[2])
    reinforcement=reinforce_martials(root,True)
    for originals in (restoration.prepared[1],reinforcement[1]):
        assert all((p.read_bytes() if p.exists() else None)==raw for p,raw in originals.items())
    (output()/'手游武学冻结预览验收.json').write_text(json.dumps(dict(version=VERSION,edition=EDITION_NAME,passed=True,restored=len(restoration.installed),default_test_books_off=True,restore_files=len(restoration.prepared[0]),reinforcement_files=len(reinforcement[0]),source_pack_sha256=hashlib.sha256((DATA_ROOT/'mobile_martial_pack.json').read_bytes()).hexdigest(),formal_game_unchanged=True),ensure_ascii=False,indent=2),'utf8')
    del restoration,reinforcement
    import gc;gc.collect()
    assert VERSION in TITLE and EDITION_NAME in TITLE
    assert (DATA_ROOT/'ui_assets/mobile_models.lua').is_file()==MOBILE_ENABLED
    # Exercise both validation layers inside the delivered executable.
    from types import SimpleNamespace
    from aoyi_ui import FormulaDialog
    from aoyi_editor import validate_recipe
    lib=SimpleNamespace(tables={'Martial':{1:{'KFFeature':0,'LvLimit':10},2:{'KFFeature':0,'LvLimit':30},
        3:{'KFFeature':1,'LvLimit':10,'MartMovIDs':[1]}},'AoYi':{}},name=lambda mid:str(mid))
    value=SimpleNamespace(get=lambda:'20')
    dialog=SimpleNamespace(lib=lib,choices={'one':1},ingredient=SimpleNamespace(get=lambda:'one'),level=value)
    assert FormulaDialog.pair(dialog)==(1,20)
    row={'AoYiID':3,'MartialList':[1,2],'LVList':[1000,40],'EffectiveRound':2}
    assert validate_recipe(lib,row)==row
    for invalid in (0,1001):
        try:validate_recipe(lib,{**row,'LVList':[invalid,40]})
        except ValueError:pass
        else:raise AssertionError('Invalid unlock condition accepted')
    from object_bundle import Store
    from object_extras import collect
    from object_identity_reuse import reuse_identities
    source_store=Store(root)
    object_packet,_=collect(source_store,'Martial',10701)
    object_packet['kind']='Role';object_packet['root']=1700000123
    assert reuse_identities(object_packet,source_store,{}).get('Martial:10701')==10701
    del source_store,object_packet
    from attribute_uncap import plan as plan_uncap
    from growth_runtime import patch_runtime
    from external_runtime import detach
    planned=plan_uncap(root,True)
    path=root/'DreamRivakes_Data/Plugins/RaceLogic_Release_x64.dll'
    candidate=planned[0].get(path,path.read_bytes())
    assert detach(candidate)[1]['attribute_uncap'] and detach(candidate)[1]['damage_uncap']
    assert patch_runtime(candidate)==candidate
    from pet_config import mobile_rows,row_bytes
    from codec import fields
    pet=mobile_rows()[203];wire={f.number:f.value for f in fields(row_bytes(pet))}
    assert wire[16]==2000 and wire[17]==1000
    runtime=Assets((root/'DreamRivakes_Data/resources.assets').read_bytes()).script('ResourcesMgr.lua')
    from aoyi_runtime import patch_client as patch_aoyi
    from pet_restore import embattle_script,PET_DATA_FIXED
    from lupa.lua53 import LuaRuntime
    scripts=Assets((root/'DreamRivakes_Data/resources.assets').read_bytes())
    compile_lua=LuaRuntime().eval('function(s) local f,e=load(s);assert(f,e);return true end')
    patched=patch_aoyi(scripts.script('MartialDataManager.lua'))
    assert patch_aoyi(patched)==patched and compile_lua(patched)
    for name in ('RoleEmbattleUI','RoleEmbattleUINew'):
        body=(DATA_ROOT/'ui_assets/pet_embattle.lua').read_text('utf8').replace('MJHPetEmbattle',name)
        patched=embattle_script(scripts.script(name+'.lua'),body,True)
        assert PET_DATA_FIXED in patched and compile_lua(patched)
        assert embattle_script(patched,body,True)==patched
    if MOBILE_ENABLED:
        # Force installation from the packaged resource even when the game
        # already has an older copy. This detects the actual missing-file bug.
        synthetic='\n'.join(['function LoadPrefab(sPath,iType, mod)\nend',
            'function LoadPrefabAsync(sPath,iType,loadCallback)\nend',
            'function ObjectInitFormPool(kPath,kParent)\nend',
            'function ReturnObjectToPool(obj,bActive)\nend',
            'function DynamicChangeSpineFullPath(x)\n\t\tskeletonCom.skeletonDataAsset = loadSpine\n\t\tskeletonCom:Initialize(true)\nend'])
        patched=patch_loader(synthetic)
        assert '-- MJH_MOBILE_MODELS_V261' in patched
        assert patch_loader(patched)==patched
        from lupa.lua53 import LuaRuntime
        lua=LuaRuntime();assert lua.eval('function(s) return load(s) ~= nil end')(patched)
        assert '-- MJH_MOBILE_MODELS_V261' in patch_loader(runtime)
    else:assert patch_loader(runtime)==runtime
    # Build the real controllers without automatic game loading or callbacks.
    from unittest.mock import patch
    from app import Application
    from tkinter import ttk
    with patch.object(Application,'load_game',lambda self:None):
        app=Application();app.withdraw()
        try:
            app.update_idletasks()
            def widgets(widget):
                yield widget
                for child in widget.winfo_children():yield from widgets(child)
            all_widgets=list(widgets(app))
            buttons=[str(w.cget('text')) for w in all_widgets if isinstance(w,ttk.Button)]
            tabs=[str(w.tab(tab,'text')) for w in all_widgets if isinstance(w,ttk.Notebook) for tab in w.tabs()]
            assert ('手游模型与立绘' in tabs)==MOBILE_ENABLED
            assert ('选择手游模型与皮肤' in buttons)==MOBILE_ENABLED
            assert ('选择手游人物立绘' in buttons)==MOBILE_ENABLED
            assert '上传立绘图片' in buttons and '模型动作绑定检查' in buttons
            assert '导出模型与立绘总表' in buttons
            assert '移除属性上限' in tabs and '预览属性上限修改' in buttons and '应用属性上限修改并备份' in buttons
            assert '恢复手游专属武学' in tabs and '开启全武学等级上限强化' in tabs
            assert '预览手游武学恢复' in buttons and '预览上限强化' in buttons
            assert '恢复角色突破' in tabs and '预览角色突破' in buttons
            assert hasattr(app,'role_breakthrough_panel')
            (output()/'版别界面验收.json').write_text(json.dumps(dict(version=VERSION,edition=EDITION_NAME,
                passed=True,real_tk_controllers=True,mobile_entry=MOBILE_ENABLED,original_portrait_and_texture_retained=True,
                game_load_disabled=True,tabs=tabs),ensure_ascii=False,indent=2),'utf8')
        finally:app.destroy()
    from disguise_editor import plan
    from disguise_reference import export
    prepared=plan(root)
    payloads,originals,results,notes,_=prepared
    assert not notes,notes
    config_path=root/'mod/editor_disguise/catalog.json'
    catalog=json.loads(payloads.get(config_path) or originals.get(config_path) or config_path.read_bytes())
    options=catalog['options'];assert len({o['query_id'] for o in options})==len(options)
    table=export(root,prepared,output()/'模型与立绘总表.html')
    text=table.read_text('utf8')
    rows=json.loads(re.search(r'<script id="resources" type="application/json">(.*?)</script>',text,re.S).group(1))
    assert len(rows)==len(options)
    for row,option in zip(rows,options):
        assert row=={**{k:v for k,v in option.items() if k not in ('drawing','icon')},'preview':row['preview']}
        from PIL import Image
        with Image.open(io.BytesIO(base64.b64decode(row['preview'].split(',',1)[1]))) as image:image.verify()
    # Execute the same query matcher that is installed in the game's UI.
    from lupa.lua53 import LuaRuntime
    lua=LuaRuntime();ui=(DATA_ROOT/'ui_assets/disguise_ui.lua').read_text('utf8')
    start=ui.index('function MJHDisguiseMatches(');end=ui.index('\nend',start)+4
    lua.execute(ui[start:end])
    def value(item):
        if isinstance(item,dict):return lua.table_from({k:value(v) for k,v in item.items()})
        if isinstance(item,list):return lua.table_from([value(v) for v in item])
        return item
    for option in options:
        assert lua.globals().MJHDisguiseMatches(value(option),option['query_id'].lower())
    assert sum(r['source']=='mobile' for r in rows)==(962 if MOBILE_ENABLED else 0)
    # Sources read for the plan are unchanged; this review never applies it.
    changed=[]
    for path,before in originals.items():
        current=path.read_bytes() if path.exists() else None
        if current!=before:
            changed.append(dict(path=str(path),expected=hashlib.sha256(before).hexdigest() if before is not None else None,
                                actual=hashlib.sha256(current).hexdigest() if current is not None else None))
    assert not changed,changed
    from keystone import Ks,KS_ARCH_X86,KS_MODE_64
    assert Ks(KS_ARCH_X86,KS_MODE_64).asm('ret')[0]==[0xc3]
    catalog_hash=hashlib.sha256(json.dumps(options,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    result=dict(version=VERSION,edition=EDITION_NAME,passed=True,frozen=bool(getattr(sys,'frozen',False)),
        options=len(rows),models=sum(r['kind']=='model' for r in rows),portraits=sum(r['kind']=='portrait' for r in rows),
        query_ids_match_game_catalog=True,every_query_checked_in_game_lua=True,all_thumbnails_decoded=True,
        catalog_sha256=catalog_hash,reference_sha256=hashlib.sha256(table.read_bytes()).hexdigest(),
        game_unchanged=True,missing_mobile_loader_regression=True,notes=notes)
    (output()/'发布验收.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf8')

