"""Compatibility of referenced clans without importing global catalogues."""
from pathlib import Path
import copy,json,sys

def checks(root,bundle):
    from object_bundle import Store,read_bundle,anchor_compatible,CLAN_ACQUISITION_POOLS
    from object_identity_reuse import reuse_identities
    from object_extras import collect
    s=Store(root);p,files=read_bundle(bundle);out={};changed=[]
    for token,expected in p['anchors'].items():
        table,ident=token.split(':')
        if table!='Clan':continue
        actual=s.table(table).get(int(ident))
        assert anchor_compatible(table,expected,actual),token
        if expected!=actual:changed.append(token)
    assert 'Clan:93' in changed and len(changed)==6,changed
    out['user_six_clan_pool_differences_accepted']=True
    expected=p['anchors']['Clan:93'];actual=s.table('Clan')[93]
    for field in ['BaseID','NameID','ClanName','ClanType','Type','Location','SpecialRoleAttr','StoryIDs']:
        bad=copy.deepcopy(actual);value=bad[field]
        bad[field]=value+[999] if isinstance(value,list) else value+'changed' if isinstance(value,str) else value+1
        assert not anchor_compatible('Clan',expected,bad),field
    out['clan_identity_gameplay_and_location_changes_rejected']=True
    assert not anchor_compatible('Clan',expected,None);out['missing_clan_rejected']=True
    bad=copy.deepcopy(actual);bad['UnknownFutureField']=1
    assert not anchor_compatible('Clan',expected,bad);out['unknown_clan_fields_rejected']=True
    bad=copy.deepcopy(actual);bad['Sword']=['invalid']
    assert not anchor_compatible('Clan',expected,bad);out['invalid_pool_data_rejected']=True
    for table in ['City','Map','ResourceRoleModel']:
        token,row=next((t,r) for t,r in p['anchors'].items() if t.startswith(table+':'))
        bad=copy.deepcopy(row);bad['BaseID']+=1
        assert not anchor_compatible(table,row,bad),table
    out['city_map_model_protection_retained']=True
    # A pool-only difference must not force an otherwise identical native art
    # to become a duplicate through the recursive identity checker.
    own,_=collect(s,'Martial',10701);own['kind']='Role';own['root']=1700000000
    clan=next(t for t in own['anchors'] if t.startswith('Clan:'))
    own['anchors'][clan]['BestMartial'].append(1800001234)
    assert reuse_identities(own,s,{},martial_names=True).get('Martial:10701')==10701
    out['pool_difference_still_reuses_identical_martial']=True
    return out,changed

def run():
    from edition import VERSION,EDITION_NAME
    from review_edition import output
    root=Path(sys.argv[sys.argv.index('--game')+1]).resolve();bundle=Path(sys.argv[sys.argv.index('--bundle')+1]).resolve()
    results,changed=checks(root,bundle)
    report=dict(passed=True,version=VERSION,edition=EDITION_NAME,frozen=bool(getattr(sys,'frozen',False)),checks=results,changed_clans=changed,scope='真实用户配置包与新装原版的门派引用检查；完整导入/原生入队另列。')
    (output()/'门派引用导入冻结验收.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    print('CLAN ANCHOR CHECKS PASS',len(results),flush=True)

if __name__=='__main__':run()
