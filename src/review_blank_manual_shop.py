"""Read-only merchant preview inside each shipped executable."""
from pathlib import Path
import sys,json,hashlib

def checks(root):
    from blank_manual_shop import plan,SHOP,SHOP_ID
    from blank_manual_legacy import remove_script,MARKER
    from client_config import Assets,lua_rows
    root=Path(root).resolve();path=root/'DreamRivakes_Data/resources.assets'
    raw=path.read_bytes();a=Assets(raw);value=plan(root);p,o,results,notes,reads=value
    assert not notes
    assert all((q.read_bytes() if q.exists() else None)==v for q,v in o.items())
    assert not any(q.suffix.lower() in ('.sav','.dll') or q.stem in ('Martial','Story') for q in p)
    b=Assets(p.get(path,raw))
    from client_config import enum_values
    e=enum_values(b.script('common.lua'))|enum_values(b.script('Enum.lua'))
    assert lua_rows(b.script('Shop.lua'),'Shop',e)[SHOP_ID]==SHOP
    for name in ('MartialUI.lua','MartialUIS.lua'):
        assert b.script(name)==remove_script(a.script(name),name)
        assert MARKER not in b.script(name)
    allowed={'Shop','Shop.lua','MartialUI.lua','MartialUIS.lua'}
    for name,(_,q,n) in a.scripts.items():
        if name in allowed:continue
        _,r,m=b.scripts[name];assert a.data[q+4:q+4+n]==b.data[r+4:r+4+m],name
    def objects(v):return {x['id']:hashlib.sha256(v.data[v.start+x['off']:v.start+x['off']+x['length']]).hexdigest() for x in v.objects if x['kind']!=49}
    assert objects(a)==objects(b) and path.read_bytes()==raw
    return dict(shop_price_1_stock_20=True,copying_game_owned=True,native_methods_preserved=True,other_scripts_preserved=True,non_text_objects_preserved=True,no_save_or_dll_write=True,real_preimages=True,files=len(p),results=results)

def run():
    from edition import VERSION,EDITION_NAME
    from review_edition import output
    root=Path(sys.argv[sys.argv.index('--game')+1]).resolve()
    report=dict(passed=True,version=VERSION,edition=EDITION_NAME,frozen=bool(getattr(sys,'frozen',False)),checks=checks(root))
    (output()/'空白秘籍商店冻结验收.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')

if __name__=='__main__':run()
