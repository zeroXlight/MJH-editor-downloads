"""Read-only November runtime checks in each shipped executable."""
from pathlib import Path
import sys,json,hashlib

def run():
    from edition import VERSION,EDITION_NAME
    from review_edition import output
    from bigmap_profile import november15_parent,race_image,client_image
    from growth_runtime import _original,_build_runtime,patch_runtime
    from external_runtime import detach
    from object_bundle import Store
    from mobile_effect_resources import stage
    from role_breakthrough import plan
    from feature_save import NativeSave
    root=Path(sys.argv[sys.argv.index('--game')+1]).resolve()
    rp=root/'DreamRivakes_Data/Plugins/RaceLogic_Release_x64.dll';cp=root/'DreamRivakes_Data/Plugins/ClientDll.dll'
    before=rp.read_bytes();parent=_original(before)
    assert november15_parent(parent) and race_image(before) and client_image(cp.read_bytes())
    for mode in (True,2):
        image=patch_runtime(before,role_breakthrough=mode)
        assert detach(image)[0]==parent and detach(image)[1]['role_breakthrough']==mode
    store=Store(root);p={};results=[]
    stage(store,p,{'10821':{},'12916':{}},results)
    assert not p,'fixture must have both current effect packs'
    value=plan(root,True);assert not value[0],[(str(p),len(v or b'')) for p,v in value[0].items()]
    save=(root/'Save.sav').read_bytes();assert NativeSave(save).bytes()==save
    assert rp.read_bytes()==before
    report=dict(passed=True,version=VERSION,edition=EDITION_NAME,frozen=bool(getattr(sys,'frozen',False)),parent_sha256=hashlib.sha256(parent).hexdigest(),native_roundtrip=True,role_progression_no_op=True,effect_material_links_verified=True,save_no_op=True,game_unchanged=True)
    (output()/'新版运行库冻结验收.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
