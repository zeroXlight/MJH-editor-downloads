"""Scope authoring and compilation into disjoint native category filters."""
import copy
from martial_editor import DEPARTS, RANKS
from martial_preview import clan_names

FIELDS = ('MartialID','ClanID','MartialType','Rank','Toxic','Multistage','AutoMartialType')

def signature(row):
    values = [int(row.get(k,0)) for k in FIELDS]
    if values[2] == 15: values[2] = 0
    return tuple(values)

def criteria(lib, category=0, rank=0, clan=0):
    if category not in (0,*DEPARTS) or rank not in (0,*RANKS):
        raise ValueError('请选择有效类别和品质')
    if clan and clan not in clan_names(lib): raise ValueError('门派不存在')
    return dict(zip(FIELDS,(0,clan,0 if category==15 else category,rank,0,0,0)))

def matching(lib,row):
    result=[]
    for mid,m in lib.tables['Martial'].items():
        if row.get('MartialID') and row['MartialID']!=mid: continue
        if row.get('ClanID') and row['ClanID']!=m.get('ClanID'): continue
        if row.get('Rank') and row['Rank']!=m.get('Rank'): continue
        dep=row.get('MartialType',0)
        if dep==10:
            if m.get('DepartEnum')==4: continue
        elif dep not in (0,15) and dep!=m.get('DepartEnum'): continue
        result.append(mid)
    return result

def find(lib,row):
    # Native outer-work filters exclude lightness/medicine. Only our compiled
    # group is equivalent to the requested "all categories except inner work".
    return next((i for i,r in sorted(lib.tables['MartialFilter'].items())
                 if signature(r)==signature(row) and
                 (row.get('MartialType')!=10 or str(i) in lib.scope_groups)),None)

def create(lib,category=0,rank=0,clan=0):
    row=criteria(lib,category,rank,clan);ident=find(lib,row)
    if ident is not None:return ident,False
    ident=lib.new_id('MartialFilter')
    with lib.edit():
        lib.set('MartialFilter',ident,row)
        if category==10:lib.scope_groups[str(ident)]={'category':10,'rank':rank,'clan':clan}
    return ident,True

def compile_groups(lib):
    """Split two-effect stages before expanding; never multiply the other slot."""
    groups={int(i) for i in lib.scope_groups}
    if not groups:return
    from client_config import lua_rows
    kftypes=lua_rows(lib.assets.script('Kftype.lua'),'Kftype',lib.enums)
    concrete=sorted(set(kftypes)-{0,4,10,15})
    with lib.edit():
        for mid,m in list(lib.tables['Martial'].items()):
            for key in ('GrowProIDs','UnlockClauses'):
                sequence=list(m.get(key,[]));levels=list(m.get('UnlockLvls',[]));new=[];newlevels=[];changed=False
                for index,cid in enumerate(sequence):
                    row=lib.tables['MartialItem'].get(cid,{})
                    if not any(row.get(f'MartialFilter{s}',0) in groups for s in (1,2)):
                        new.append(cid)
                        if key=='UnlockClauses':newlevels.append(levels[index])
                        continue
                    changed=True
                    for slot in (1,2):
                        n=str(slot);fid=row.get('MartialFilter'+n,0)
                        if not row.get('EffectEnum'+n):continue
                        if fid in groups and row.get('EffectEnum'+n)!=10:
                            raise ValueError('“内功以外”组合范围仅支持固定武学属性效果（10）；角色属性与每级成长不使用武学筛选')
                        targets=[]
                        if fid in groups:
                            scope=lib.tables['MartialFilter'][fid]
                            for category in concrete:targets.append(create(lib,category,scope.get('Rank',0),scope.get('ClanID',0))[0])
                            # Legacy martial records can have no Kftype entry.
                            # Use an exact martial filter for those outliers.
                            for target_mid in matching(lib,scope):
                                if lib.tables['Martial'][target_mid]['DepartEnum'] in concrete:continue
                                special=criteria(lib,0,scope.get('Rank',0),scope.get('ClanID',0));special['MartialID']=target_mid
                                target=find(lib,special)
                                if target is None:
                                    target=lib.new_id('MartialFilter');lib.set('MartialFilter',target,special)
                                targets.append(target)
                        else:targets=[fid]
                        for target in targets:
                            delta=copy.deepcopy(row);other=str(3-slot)
                            for field in ('EffectEnum','AttrEnum','SkillID','MartialFilter','Grade'):delta[field+other]=0
                            delta['Effect'+other+'Value']=[];delta['DesID']=0
                            delta['MartialFilter'+n]=target
                            cloned=lib.clone('MartialItem',cid);lib.set('MartialItem',cloned,delta);new.append(cloned)
                            if key=='UnlockClauses':newlevels.append(levels[index])
                if changed:lib._stage_sequence(mid,key,new,newlevels)
        for m in lib.tables['Martial'].values():
            for cid in m.get('MartMovIDs',[]):
                if any(lib.tables['MartialItem'][cid].get(f'MartialFilter{s}',0) in groups for s in (1,2)):
                    raise ValueError('组合外功范围请添加到解锁属性阶段，不能用作主动招式范围')
