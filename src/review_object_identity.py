"""Real-game graph matching regression checks for recursive character imports."""
from pathlib import Path
import copy,json,sys

def rename_martial(packet,old,new):
    from object_bundle import key
    p=copy.deepcopy(packet);token=key('Martial',old);replacement=key('Martial',new)
    node=p['nodes'].pop(token);node['id']=new;node['row']['BaseID']=new;p['nodes'][replacement]=node
    p['edges'][replacement]=p['edges'].pop(token)
    for owner,edges in p['edges'].items():
        for edge in edges:
            if edge['target']!=token:continue
            row=p['nodes'][owner]['row']
            for part in edge['path'][:-1]:row=row[part]
            row[edge['path'][-1]]=str(new) if edge.get('string') else new;edge['target']=replacement
    by=p['extras'].get('independent_growth_by_martial',{})
    if str(old) in by:by[str(new)]=by.pop(str(old))
    origins=p['extras'].get('origins',{}).get('Martial',{})
    if str(old) in origins:origins[str(new)]=origins.pop(str(old))
    for rec in p['extras'].get('role_metadata',{}).values():
        settings=rec.get('settings',{})
        if 'kungfu' in settings:settings['kungfu']=[(new if i==old else i,lv) for i,lv in settings['kungfu']]
    if p['kind']=='Martial' and p['root']==old:p['root']=new
    return p

def checks(root):
    from object_bundle import Store,key,references,validate_packet
    from object_extras import collect
    from object_identity_reuse import reuse_identities
    from growth_runtime import MARKER
    s=Store(root);base,_=collect(s,'Martial',20068)
    p=rename_martial(base,20068,1800000068);validate_packet(p)
    p['kind']='Role';p['root']=1700000000
    token='Martial:1800000068';cid=p['nodes'][token]['row']['GrowProIDs'][0]
    class Target:
        root=s.root;assets=s.assets;enums=s.enums;native=s.native
        def table(self,name):
            rows=s.table(name)
            return {20068:rows[20068]} if name=='Martial' else rows
    target=Target();out={}
    def match(q):return reuse_identities(q,target,{},martial_names=True)
    assert token not in reuse_identities(p,target,{})
    assert match(p).get(token)==20068;out['different_id_same_name_same_combat']=True
    q=copy.deepcopy(p);row=q['nodes'][token]['row'];row['LvLimit']+=10
    assert match(q).get(token)==20068;out['target_cap_kept_without_duplicate']=True
    for attr in [*range(3,17),17,18,19,20,99]:
        ident=1801000000+attr;t=key('MartialItem',ident)
        q['nodes'][t]=dict(table='MartialItem',id=ident,row=dict(BaseID=ident,ItemType=1,EffectEnum1=7,AttrEnum1=attr,Effect1Value=[123,MARKER]),wire='')
        q['edges'][t]=[];row['GrowProIDs'].append(ident)
        q['edges'][token].append(dict(path=['GrowProIDs',len(row['GrowProIDs'])-1],target=t,string=False))
    assert match(q).get(token)==20068;out['role_attributes_and_masteries_ignored']=True
    q=copy.deepcopy(p);c=q['nodes'][key('MartialItem',cid)]['row'];c.update(EffectEnum2=8,AttrEnum2=10,Effect2Value=[99])
    reused=match(q);assert reused.get(token)==20068 and key('MartialItem',cid) not in reused
    out['mixed_clause_core_ignored_without_global_clause_reuse']=True
    # Move retained power to slot 2: owner-specific captured growth follows it.
    q=copy.deepcopy(p);c=q['nodes'][key('MartialItem',cid)]['row']
    for f in ('EffectEnum{n}','AttrEnum{n}','SkillID{n}','MartialFilter{n}','Effect{n}Value','Grade{n}'):c[f.format(n=2)]=copy.deepcopy(c.get(f.format(n=1),[] if 'Value' in f else 0))
    c.update(EffectEnum1=7,AttrEnum1=3,Effect1Value=[999,MARKER],SkillID1=0,MartialFilter1=0,Grade1=0)
    for values in [q['extras'].get('independent_growth',{}),q['extras'].get('independent_growth_by_martial',{}).get('1800000068',{})]:
        if f'{cid}:1' in values:values[f'{cid}:2']=values.pop(f'{cid}:1')
    assert match(q).get(token)==20068;out['mixed_slot_growth_owner_preserved']=True
    q=copy.deepcopy(p);q['nodes'][key('MartialItem',cid)]['row']['Effect1Value']=[0,MARKER]
    q['extras'].setdefault('independent_growth_by_martial',{}).setdefault('1800000068',{})[f'{cid}:1']=[0,MARKER]
    q['extras'].setdefault('independent_growth',{})[f'{cid}:1']=[0,MARKER]
    assert token not in match(q);out['power_coefficient_difference_rejected']=True
    q=copy.deepcopy(p);q['nodes'][token]['row']['ColdTime']+=1
    assert token not in match(q);out['casting_difference_rejected']=True
    q=copy.deepcopy(p);effect=next(t for t,n in q['nodes'].items() if n['table']=='SkillEffect');q['nodes'][effect]['row']['ArgCount']+=1
    assert token not in match(q);out['recursive_effect_difference_rejected']=True
    q=copy.deepcopy(p);q['nodes'][token]['row']['Exclusive']=[1700000000]
    q['edges'][token].append(dict(path=['Exclusive',0],target='@Role:1700000000',string=False));q['role_groups']['1700000000']=[]
    assert token not in match(q);out['imported_owner_exclusive_not_reused']=True
    q=copy.deepcopy(p);q['nodes'][key('Language',q['nodes'][token]['row']['NameID'])]['row']['Ch_Text']='同名武学回归测试缺失'
    assert token not in match(q);out['different_name_not_merged']=True
    direct=copy.deepcopy(base)
    assert 'Martial:20068' not in reuse_identities(direct,s,{},martial_names=True)
    out['explicit_root_copy_stays_independent']=True
    # Gift matching is still an original-ID, whole-function comparison.
    gift=next(t for t,n in base['nodes'].items() if n['table']=='Gift')
    q=copy.deepcopy(base);q['kind']='Role';q['root']=1700000000;q['nodes'][gift]['row']['Cost']=123456
    assert gift not in reuse_identities(q,s,{},martial_names=True);out['gift_full_comparison_retained']=True
    originals=copy.deepcopy(s.table('Martial')[20068]);match(p);assert s.table('Martial')[20068]==originals
    out['target_rows_unchanged']=True
    return out

def run():
    from edition import VERSION,EDITION_NAME
    from review_edition import output
    root=Path(sys.argv[sys.argv.index('--game')+1]).resolve();result=checks(root)
    report=dict(passed=True,version=VERSION,edition=EDITION_NAME,frozen=bool(getattr(sys,'frozen',False)),checks=result,scope='真实游戏依赖图的匹配与拒绝回归；完整人物导入和原生验证另列，不冒充全部武学战斗重测。')
    (output()/'同名武学导入冻结验收.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    print('IDENTITY CHECKS PASS',len(result),flush=True)

if __name__=='__main__':run()
