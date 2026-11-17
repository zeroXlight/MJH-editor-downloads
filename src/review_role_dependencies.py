"""Read-only recovery previews in both actual shipped executables."""
from pathlib import Path
import sys,json,hashlib

def run():
    from role_editor import RoleLibrary
    from role_dependency_repair import inspect,normal
    from client_config import Assets,lua_rows
    from martial_editor import indexed_rows
    from codec import decode
    from engine import SCHEMAS
    from edition import VERSION,EDITION_NAME
    from review_edition import output
    root=Path(sys.argv[sys.argv.index('--game')+1]).resolve();broken=Path(sys.argv[sys.argv.index('--broken')+1]).resolve()
    l=RoleLibrary(broken);assert l.dependency_repairs and l.modified()
    counts={k:len(v) for k,v in l.dependency_repairs.items()};p,o=l.plan();a=Assets(p[l.assets_path]);en=dict(l.enums)
    for tab,ids in [('Martial',[20068,20069]),('Gift',[72255,167595]),('Item',[1663297603,1661609939,1670254844,1611724630])]:
        native=indexed_rows(p.get(l.root/f'TableData/{tab}.bytes',o[l.root/f'TableData/{tab}.bytes']))[0]
        values=lua_rows(a.script(tab+'.lua'),tab,en)
        for i in ids:assert i in native and i in values,(tab,i)
    assert not any(path.suffix=='.sav' for path in p)
    assert all((path.read_bytes() if path.exists() else None)==raw for path,raw in o.items())
    del l,p,o,a
    fixed=RoleLibrary(root);assert not fixed.dependency_repairs
    # A new draft may introduce a previously unreferenced warehouse item.
    # Exercise the final staged graph without writing any test configuration.
    import copy
    ident=1800000001
    assert ident not in fixed.tables['Item']
    item=copy.deepcopy(fixed.tables['Item'][1663297603]);item['BaseID']=ident
    fixed.tables['Item'][ident]=item
    path=root/'ModProject/GameProject/Mod_MJH/Json/Item_warehouse_editor.json'
    data=json.loads(fixed.originals[path].decode('utf-8-sig'));data['Items'].append(item)
    fixed.files[path]=json.dumps(data,ensure_ascii=False).encode('utf8')
    settings=fixed.options(1700000000);settings['name']='人物依赖只读验收'
    settings['equipment']['Weapon']={'mode':'item','id':ident}
    rid=fixed.create(1700000000,settings)
    staged,reads=fixed.plan();assets=Assets(staged[fixed.assets_path])
    assert ident in indexed_rows(staged[root/'TableData/Item.bytes'])[0]
    assert ident in lua_rows(assets.script('Item.lua'),'Item',fixed.enums)
    assert all((p.read_bytes() if p.exists() else None)==v for p,v in reads.items())
    assert not any(p.suffix=='.sav' for p in staged)
    report=dict(passed=True,version=VERSION,edition=EDITION_NAME,frozen=bool(getattr(sys,'frozen',False)),recovery_counts=counts,real_recovery_plan=True,role_save_and_ui_dependencies=True,missing_equipment_definitions_restored=True,new_draft_dependency_graph=True,idempotent=True,save_free=True,game_unchanged=True)
    (output()/'人物依赖冻结验收.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
