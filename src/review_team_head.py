"""Read-only regression checks for imported custom team-head sizing."""
from pathlib import Path
import hashlib,json,sys

def checks(root):
    from client_config import Assets
    from team_head_runtime import patch,repair,PATCH,LEGACY_PATCH
    path=root/'DreamRivakes_Data/resources.assets';raw=path.read_bytes();a=Assets(raw)
    text=a.script('TeamListUI.lua');new=patch(text);results={}
    bare=text.replace(LEGACY_PATCH,'').replace(PATCH,'')
    assert patch(bare)==bare.replace('comData.imgHead:SetNativeSize()','comData.imgHead:SetNativeSize()'+PATCH,1)
    results['native_script_install']=True
    assert patch(bare.replace('comData.imgHead:SetNativeSize()','comData.imgHead:SetNativeSize()'+LEGACY_PATCH,1))==patch(bare)
    results['exact_legacy_migration']=True
    assert patch(new)==new;results['idempotent_no_duplicate']=True
    assert new.replace(PATCH,'')==bare;results['surrounding_native_code_unchanged']=True
    assert '"#role_editor/"' in PATCH and '"#role_editor/head_"' not in PATCH
    results['hashed_upload_and_reimport_heads_share_fit']=True
    for key,bad in [
        ('modified_legacy_rejected',bare.replace('comData.imgHead:SetNativeSize()','comData.imgHead:SetNativeSize()'+LEGACY_PATCH.replace('local size = 128','local size = 129'),1)),
        ('modified_current_rejected',new.replace('local size = 128','local size = 129')),
        ('unknown_marker_rejected',bare+'\n-- MJH_TEAM_HEAD_FIT_UNKNOWN'),
        ('duplicate_entry_rejected',bare+'\ncomData.imgHead:SetNativeSize()')]:
        try:patch(bad)
        except ValueError:results[key]=True
        else:raise AssertionError(key)
    after=repair(raw);b=Assets(after)
    assert b.script('TeamListUI.lua')==new
    def objects(v):return {r['id']:hashlib.sha256(v.data[v.start+r['off']:v.start+r['off']+r['length']]).hexdigest() for r in v.objects if r['kind']!=49}
    assert objects(a)==objects(b);results['non_text_unity_assets_unchanged']=True
    for name in a.scripts:
        if name=='TeamListUI.lua':continue
        _,q,n=a.scripts[name];_,z,m=b.scripts[name]
        assert a.data[q+4:q+4+n]==b.data[z+4:z+4+m],name
    results['other_lua_and_portrait_logic_unchanged']=True
    assert path.read_bytes()==raw;results['read_only_review']=True
    return results

def run():
    from edition import VERSION,EDITION_NAME
    from review_edition import output
    root=Path(sys.argv[sys.argv.index('--game')+1]).resolve();results=checks(root)
    (output()/'队伍头像冻结验收.json').write_text(json.dumps(dict(passed=True,version=VERSION,edition=EDITION_NAME,frozen=bool(getattr(sys,'frozen',False)),checks=results,scope='实际资源脚本升级/幂等/冲突保护；真实Unity尺寸和画面另列。'),ensure_ascii=False,indent=2),'utf8')
    print('TEAM HEAD CHECKS PASS',len(results),flush=True)

if __name__=='__main__':run()
