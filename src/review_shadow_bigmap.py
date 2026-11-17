"""Read-only checks exercised by both frozen editions on the supplied MOD."""
from pathlib import Path
import sys,json,hashlib

def run():
    from edition import VERSION,EDITION_NAME
    from review_edition import output
    from engine import Catalog,Save
    from feature_save import NativeSave
    from bigmap_profile import race_image,client_image
    from growth_runtime import _original
    from external_runtime import reattach,detach,plan
    from shadow_runtime import ready
    root=Path(sys.argv[sys.argv.index('--game')+1]).resolve()
    rp=root/'DreamRivakes_Data/Plugins/RaceLogic_Release_x64.dll'
    cp=root/'DreamRivakes_Data/Plugins/ClientDll.dll'
    raw=rp.read_bytes();client=cp.read_bytes();save=(root/'Save.sav').read_bytes()
    assert race_image(raw) and client_image(client) and ready(root)
    parent=_original(raw)
    patched=reattach(parent,dict(six_attrs=True,pets=True,role_breakthrough=True))
    assert detach(patched)[0]==parent
    bad=bytearray(parent);bad[0x23cb00]^=1
    assert not race_image(bytes(bad))
    bad=bytearray(client);bad[0x602541]^=1
    assert not client_image(bytes(bad))
    catalog=Catalog(root);s=Save(root/'Save.sav',catalog,save)
    assert catalog.supported and NativeSave(save).bytes()==save and s.patched({})==save
    result=plan(root,True)
    from shadow_loader_repair import plan as loader_plan
    loader=loader_plan(root)
    assert not loader[0], 'frozen review fixture must already have the loader fix'
    assert all((p.read_bytes() if p.exists() else None)==b for p,b in loader[4].items())
    assert not any(p.suffix.lower()=='.sav' for p in result[0])
    assert rp.read_bytes()==raw and cp.read_bytes()==client and (root/'Save.sav').read_bytes()==save
    report=dict(version=VERSION,edition=EDITION_NAME,passed=True,frozen=bool(getattr(sys,'frozen',False)),
        certified_shadow_bigmap=True,full_parent_restore_verified=True,unknown_changes_rejected=True,
        equipment=len(s.records),save_sha256=hashlib.sha256(save).hexdigest(),save_no_op_exact=True,
        restore_preview_files=len(result[0]),game_unchanged=True,standalone_legacy_tool_required=False)
    (output()/'暗影大地图冻结验收.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
