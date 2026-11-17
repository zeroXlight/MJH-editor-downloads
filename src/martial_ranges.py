"""Independent named damage areas. Cast distances and native templates stay intact."""
import copy,re,json
from client_config import Assets
from martial_editor import lua_value
AREA_START=1700000000
AREA_END=1701000000
BEGIN='-- MJH named area registry V2.0.8 BEGIN'
END='-- MJH named area registry V2.0.8 END'
FUNCTION='function Unit:GetSkillDamageRangeByPos(kMartialData,iCastPosX,iCastPosY,iUnitPosX,iUnitPosY,eDepartEnum)'
CELLS={(x,y) for y in range(-2,3) for x in range(-3,5)}

def expression_graph(lib,root):
    result={};pending=[root]
    while pending:
        ident=pending.pop()
        if not ident or ident in result:continue
        row=lib.tables['SkillEffect'].get(ident)
        if row is None:raise ValueError('技能范围表达式引用缺失')
        result[ident]=row
        for n in range(1,14):
            arg=row.get('EventArg'+str(n),[])
            if len(arg)==2 and arg[1]:pending.append(arg[1])
    return result

def battle_binding(lib,sid,node):
    """744/745 take instance IDs; 498 compares that instance's prototype ID."""
    matches=[]
    for trigger in lib.tables['Skill'][sid].get('SkillTriggers',[]):
        if node['BaseID'] not in expression_graph(lib,trigger['EffectID']):continue
        expected=308 if node['Name']==744 else 313
        if trigger['Event']!=expected:raise ValueError('技能范围触发时机不正确')
        condition=expression_graph(lib,trigger['ConditionID'])
        for row in condition.values():
            arg=row.get('EventArg2',[])
            if row['Name']==498 and row.get('EventArg1')==[2,0] and len(arg)==2 and arg[0]==0 and condition.get(arg[1],{}).get('Name')==355:
                proto=row.get('EventArg3',[])
                if len(proto)==2 and proto[0]>0 and proto[1]==0:matches.append((proto[0],arg[1]))
    if len(matches)!=1:raise ValueError('技能范围缺少唯一的目标武学与战斗实例条件')
    target,expr=matches[0]
    arg=node.get('EventArg1',[])
    valid=arg in ([target,0],[0,expr])
    if not valid and len(arg)==2 and arg[0]==0:
        # Equivalent current-martial instance expressions may retain different
        # IDs after dependency reuse. They still resolve the same battle object.
        expected=lib.tables['SkillEffect'].get(expr,{})
        actual=lib.tables['SkillEffect'].get(arg[1],{})
        valid=actual.get('Name')==355 and {k:v for k,v in actual.items() if k!='BaseID'}=={k:v for k,v in expected.items() if k!='BaseID'}
    if not valid:raise ValueError('技能范围施放条件与目标武学不一致')
    return target,expr

def repair_bindings(lib):
    """Upgrade old editor clauses in place, without replacing areas or stages."""
    fixed=set()
    for ref in references(lib):
        sid=ref['skill'];graph=lib.effect_graph(sid)
        for node in graph.values():
            if node['Name'] not in (744,745):continue
            target,expr=battle_binding(lib,sid,node)
            if target!=ref['target']:raise ValueError('技能范围还原目标不一致')
            if node.get('EventArg1')!=[0,expr]:
                lib.set('SkillEffect',node['BaseID'],{'EventArg1':[0,expr]});fixed.add(sid)
    registry(lib)
    return len(fixed)

def area_values(name,cells,fullscreen=False):
    name=name.strip()
    if not name:raise ValueError('请为技能作用范围取名')
    if len(name)>80:raise ValueError('范围名称最多 80 个字')
    cells=set(cells)
    if not cells or not cells<=CELLS:raise ValueError('范围不能为空，且只能选择 5×8 网格中的格子')
    positions=[(x,y) for y in range(-4,5) for x in range(-7,8)] if fullscreen else sorted(cells,key=lambda p:(p[1],p[0]))
    return name,positions

def create_range(lib,name,cells,fullscreen=False):
    name,positions=area_values(name,cells,fullscreen)
    ident=lib.new_id('Range',AREA_START)
    if ident>=AREA_END:raise ValueError('自定义范围编号已耗尽')
    lib.set('Range',ident,{'NameID':lib.set_text(0,name),'PosXs':[p[0] for p in positions],'PosYs':[p[1] for p in positions]})
    return ident

def clause_range(lib,row,slot):
    """Retain the graph on a no-effect slot so a disabled clause can be restored."""
    kind=row.get('EffectEnum'+str(slot),0);sid=row.get('SkillID'+str(slot),0)
    if kind not in (0,6) or sid not in lib.tables['Skill']:return None
    for node in lib.effect_graph(sid).values():
        args=node.get('EventArg2',[])
        if node['Name']!=744 or len(args)!=2 or args[1] or not AREA_START<=args[0]<AREA_END:continue
        mr=lib.tables['MartialRange'].get(args[0],{});ids=mr.get('AttackRangeIDs',[])
        if len(ids)!=1:continue
        target,_=battle_binding(lib,sid,node)
        return {'slot':slot,'skill':sid,'target':target,'range':ids[0],'martial_range':args[0],'enabled':kind==6}
    return None


def references(lib,rid=None,source=None,target=None):
    result=[]
    for mid,m in lib.tables['Martial'].items():
        if source is not None and mid!=source:continue
        for index,cid in enumerate(m.get('UnlockClauses',[])):
            c=lib.tables['MartialItem'].get(cid,{})
            for slot in (1,2):
                ref=clause_range(lib,c,slot)
                if ref is None:continue
                if rid is not None and ref['range']!=rid or target is not None and ref['target']!=target:continue
                result.append({'source':mid,'index':index,**ref})
    return result


def set_enabled(lib,source,index,slot,enabled):
    m=lib.tables['Martial'][source]
    row=lib.tables['MartialItem'][m['UnlockClauses'][index]]
    ref=clause_range(lib,row,slot)
    if ref is None:raise ValueError('请选择自定义技能范围词条')
    if ref['enabled']==bool(enabled):return
    # Native effect enum 0 registers no passive skill; retaining SkillID preserves
    # the name, area, and trigger graph without executing the 744/745 setters.
    lib.edit_clause(source,'UnlockClauses',index,{'EffectEnum'+str(slot):6 if enabled else 0})
    registry(lib)  # Reject conflicting active providers; caller uses lib.edit().


def clear_clause(lib,source,index,slot):
    """Remove the actual unlock association, including V214 dormant records."""
    row=lib.tables['MartialItem'][lib.tables['Martial'][source]['UnlockClauses'][index]]
    if clause_range(lib,row,slot) is None:raise ValueError('请选择自定义技能范围词条')
    other=3-slot
    meaningful=(row.get('EffectEnum'+str(other),0) or row.get('SkillID'+str(other),0)
                or row.get('AttrEnum'+str(other),0) or any(row.get('Effect'+str(other)+'Value',[])))
    if meaningful:
        n=str(slot)
        lib.edit_clause(source,'UnlockClauses',index,{'EffectEnum'+n:0,'SkillID'+n:0,'AttrEnum'+n:0,
            'Effect'+n+'Value':[],'Grade'+n:0,'MartialFilter'+n:0,'DesID':0})
    else:lib.remove_stage(source,'UnlockClauses',index)
    registry(lib)


def clear_target(lib,target):
    refs=references(lib,target=target)
    for ref in sorted(refs,key=lambda r:(r['source'],r['index'],r['slot']),reverse=True):
        clear_clause(lib,ref['source'],ref['index'],ref['slot'])
    return len(refs)


def update_range(lib,rid,name,cells,fullscreen=False):
    from mod_compatibility import require_native
    require_native(lib,'自定义战斗命中范围')
    name,positions=area_values(name,cells,fullscreen)
    if not AREA_START<=rid<AREA_END or rid not in lib.tables['Range']:raise ValueError('请选择已创建的命名范围')
    row=lib.tables['Range'][rid]
    delta={'PosXs':[p[0] for p in positions],'PosYs':[p[1] for p in positions]}
    if range_name(lib,rid)!=name:delta['NameID']=lib.set_text(0,name)
    if all(row.get(k)==v for k,v in delta.items()):return
    lib.set('Range',rid,delta)
    for ref in references(lib,rid=rid):
        mr=lib.tables['MartialRange'][ref['martial_range']]
        if mr.get('Name')!=name:lib.set('MartialRange',ref['martial_range'],{'Name':name})
    sync_names(lib)
    registry(lib)

def apply_clause(lib,source,target,rid,level=5):
    if not isinstance(level,int) or not 1<=level<=255:raise ValueError('解锁等级需为 1～255')
    local=references(lib,source=source,target=target)
    if not local:return add_clause(lib,source,target,rid,level)
    if len(local)!=1:raise ValueError('当前武学有重复范围词条，请先删除重复阶段后再修改')
    ref=local[0]
    for other in references(lib,target=target):
        if (other['source'],other['index'],other['slot'])!=(source,ref['index'],ref['slot']) and other['enabled'] and ref['enabled'] and other['range']!=rid:
            raise ValueError('其他武学也为此目标提供旧范围，请选中旧命名范围并“修改所选范围”，或先移除其他旧词条')
    if rid not in lib.tables['Range'] or not lib.tables['Range'][rid].get('PosXs'):raise ValueError('范围不能为空')
    if ref['range']!=rid:
        sid,mapping=lib.own_skill(source,'UnlockClauses',ref['index'],ref['slot'])
        mrid=lib.new_id('MartialRange',AREA_START)
        if mrid>=AREA_END:raise ValueError('自定义范围引用编号已耗尽')
        lib.clone('MartialRange',ref['martial_range'],mrid)
        lib.set('MartialRange',mrid,{'Name':range_name(lib,rid),'AttackRangeIDs':[rid],'AttackRangeIDs2':[]})
        for node in lib.effect_graph(sid).values():
            if node['Name']==744 and node.get('EventArg2')==[ref['martial_range'],0]:lib.set('SkillEffect',node['BaseID'],{'EventArg2':[mrid,0]})
    lib.unlock_level(source,ref['index'],level)
    sync_names(lib);registry(lib)
    return ref['index']

def range_name(lib,ident):
    return lib.text(lib.tables['Range'][ident].get('NameID',0)) or '范围 '+str(ident)

def display_name(name):
    # Keep the saved name; avoid repeating its trailing ‘范围’ in the sentence.
    return name[:-2] if name.endswith('范围') and len(name)>2 else name

def add_clause(lib,source,target,rid,level=5):
    from mod_compatibility import require_native
    require_native(lib,'自定义战斗命中范围')
    if source not in lib.tables['Martial'] or target not in lib.tables['Martial']:raise ValueError('请选择现有武学')
    if not isinstance(level,int) or not 1<=level<=255:raise ValueError('解锁等级需为 1～255')
    r=lib.tables['Range'].get(rid)
    if not r or not r.get('PosXs') or len(r['PosXs'])!=len(r.get('PosYs',[])):raise ValueError('范围不能为空')
    m=lib.tables['Martial'][target]
    if not m.get('MartMovIDs'):raise ValueError('目标武学没有主动招式，不能设置战斗作用范围')
    # Hidden-weapon target finding uses an independent piercing ray, not damage grids.
    if m.get('DepartEnum') in (1,6):raise ValueError('暗器穿透寻敌和轻功移动使用独立路径，目前不能安全替换为网格范围')
    for e in registry(lib):
        if e['target']==target and e['range']!=rid:raise ValueError('目标武学已有其他自定义范围，请先删除旧范围词条，避免多种范围互相覆盖')
    donor=lib.tables['Skill'].get(50095,{})
    graph=lib.effect_graph(50095)
    expected={450095001:512,450095002:0,450095003:503,450095004:498,450095005:355,450095006:0,450095007:692,450095008:512,450095009:0,450095010:503,450095011:498,450095012:355,450095013:0,450095014:693}
    if {i:r['Name'] for i,r in graph.items()}!=expected or [t['Event'] for t in donor.get('SkillTriggers',[])]!=[308,313] or any(graph[i].get('EventArg3')!=[10110,0] for i in (450095004,450095011)):
        raise ValueError('原生降龙掌范围模板已被修改，无法安全创建范围词条')
    original_skill=lib.tables['MartialItem'][m['MartMovIDs'][0]]['SkillID1']
    original_range=lib.tables['Skill'][original_skill]['SkillRange']
    mrid=lib.new_id('MartialRange',AREA_START)
    if mrid>=AREA_END:raise ValueError('自定义范围引用编号已耗尽')
    lib.clone('MartialRange',original_range,mrid)
    lib.set('MartialRange',mrid,{'Name':range_name(lib,rid),'AttackRangeIDs':[rid],'AttackRangeIDs2':[]})
    index=lib.add_stage(source,'UnlockClauses',100000182,level,delta={'CondID':0,'DesID':0,'MartialFilter1':0,'EffectEnum1':6,'SkillID1':50095,'EffectEnum2':0,'SkillID2':0,'Flags':[],'ItemFeature':[],'Rank':0,'DepartEnum':0})
    sid,mapping=lib.own_skill(source,'UnlockClauses',index,1)
    for old,new in mapping.items():
        row=lib.tables['SkillEffect'][new]
        if row['Name']==498:lib.set('SkillEffect',new,{'EventArg3':[target,0]})
        elif row['Name']==692:lib.set('SkillEffect',new,{'Name':744,'EventArg1':[target,0],'EventArg2':[mrid,0],'EventArg3':[10000,0]})
        elif row['Name']==693:lib.set('SkillEffect',new,{'Name':745,'EventArg1':[target,0],'EventArg2':[]})
    description='改变《'+lib.name(target)+'》技能范围为'+display_name(range_name(lib,rid))
    lib.set('Skill',sid,{'NameID':lib.set_text(0,description),'DescID':lib.set_text(0,description)})
    repair_bindings(lib)
    return index

def registry(lib):
    result=[];targets={}
    for mid,m in lib.tables['Martial'].items():
        if mid in getattr(lib,'retired_martials',set()):continue
        for cid,level in zip(m.get('UnlockClauses',[]),m.get('UnlockLvls',[])):
            c=lib.tables['MartialItem'].get(cid,{})
            for slot in (1,2):
                if c.get('EffectEnum'+str(slot))!=6:continue
                sid=c.get('SkillID'+str(slot),0)
                if sid not in lib.tables['Skill']:continue
                graph=lib.effect_graph(sid)
                setters=[r for r in graph.values() if r['Name']==744 and len(r.get('EventArg2',[]))==2 and not r['EventArg2'][1] and AREA_START<=r['EventArg2'][0]<AREA_END]
                for r in setters:
                    if c.get('CondID') or c.get('MartialFilter'+str(slot)):raise ValueError('自定义技能范围词条暂不支持附加条件，请移除条件后保存')
                    if r.get('EventArg3')!=[10000,0]:raise ValueError('自定义技能范围战斗参数不匹配，请重新创建范围词条')
                    target,_=battle_binding(lib,sid,r);mr=lib.tables['MartialRange'].get(r['EventArg2'][0],{})
                    ids=mr.get('AttackRangeIDs',[])
                    if len(ids)!=1 or mr.get('AttackRangeIDs2'):raise ValueError('自定义作用范围引用不正确')
                    rid=ids[0];area=lib.tables['Range'].get(rid,{})
                    if not area.get('PosXs') or len(area['PosXs'])!=len(area.get('PosYs',[])):raise ValueError('技能范围不能为空')
                    if target not in lib.tables['Martial']:raise ValueError('技能范围目标武学不存在')
                    if target in targets and targets[target]!=rid:raise ValueError('同一武学配置了不同自定义范围，请删除冲突的范围词条')
                    targets[target]=rid
                    resets=[x for x in graph.values() if x['Name']==745]
                    if len(resets)!=1 or battle_binding(lib,sid,resets[0])[0]!=target:raise ValueError('技能范围缺少施放后还原表达式')
                    if any(x['Name']==498 and x.get('EventArg3')!=[target,0] for x in graph.values()):raise ValueError('技能范围施放条件与目标武学不一致')
                    result.append({'source':mid,'target':target,'level':level,'range':rid,'positions':[list(p) for p in zip(area['PosXs'],area['PosYs'])]})
    return result

def sync_names(lib):
    # Names follow the current target martial and reused area after later edits.
    for mid,m in lib.tables['Martial'].items():
        for cid in m.get('UnlockClauses',[]):
            c=lib.tables['MartialItem'].get(cid,{})
            for slot in (1,2):
                if c.get('EffectEnum'+str(slot)) not in (0,6):continue
                sid=c.get('SkillID'+str(slot),0)
                if sid not in lib.tables['Skill']:continue
                for r in lib.effect_graph(sid).values():
                    args=r.get('EventArg2',[])
                    if r['Name']!=744 or len(args)!=2 or args[1] or not AREA_START<=args[0]<AREA_END:continue
                    mr=lib.tables['MartialRange'].get(args[0],{});ids=mr.get('AttackRangeIDs',[]);target,_=battle_binding(lib,sid,r)
                    if len(ids)!=1 or ids[0] not in lib.tables['Range'] or target not in lib.tables['Martial']:continue
                    desc='改变《'+lib.name(target)+'》技能范围为'+display_name(range_name(lib,ids[0]))
                    skill=lib.tables['Skill'][sid]
                    for field in ('NameID','DescID'):
                        if lib.text(skill.get(field,0))!=desc:lib.set('Skill',sid,{field:lib.set_text(0,desc)})

def patch_client(text,lib):
    from range_client import HELPERS,INDICATOR,PICK,PREVIEW
    text=text.replace('\r\n','\n')
    text=re.sub(re.escape(BEGIN)+r'.*?'+re.escape(END)+r'\r?\n?', '',text,flags=re.S)
    # Upgrade the earlier unbounded body once, instead of retaining stale logic.
    text=re.sub(r'    -- MJH area indicator V2\.0\.8\r?\n.*?\r?\n    end\r?\n(?=\s*if not kMartialData then)', '',text,flags=re.S)
    for kind in ('area','pick','preview'):
        text=re.sub(r'    -- MJH actor '+kind+r' V2\.0\.(?:12|13) BEGIN.*?    -- MJH actor '+kind+r' V2\.0\.(?:12|13) END\r?\n', '',text,flags=re.S)
    if text.count(FUNCTION)!=1:raise ValueError('客户端范围指示器入口不匹配')
    logic=BEGIN+"\nlocal _mjh_named_areas = "+lua_value(registry(lib))+"\n"+HELPERS+END+"\n"
    anchor='function Unit:IsAttackUnitGrid(x,y)'
    if text.count(anchor)!=1:raise ValueError('客户端范围方向选择入口不匹配')
    text=text.replace(anchor,logic+anchor,1)
    text=text.replace(FUNCTION+'\n',FUNCTION+'\n'+INDICATOR,1)
    for function,body in ((anchor,PICK),('function Unit:IsIncludeAttackGrid(targetX,targetY)',PICK.replace('_mjh_cast(self,x,y)','_mjh_cast(self,targetX,targetY)')),('function Unit:ShowSkillDamageRange(x,y)',PREVIEW)):
        if text.count(function)!=1:raise ValueError('客户端范围选择入口不匹配')
        text=text.replace(function+'\n',function+'\n'+body,1)
    return text

def plan(lib,assets,payloads,originals):
    from mod_compatibility import native_supported,note
    if not native_supported(lib.root):
        note(lib,'自定义范围运行库同步已跳过：保留当前MOD运行库和已有范围配置')
        return assets
    entries=registry(lib)
    a=Assets(assets);text=a.script('Unit.lua')
    if entries or BEGIN in text:assets=a.replace_script('Unit.lua',patch_client(text,lib))
    if entries:
        owned=set(lib.changes['MartialRange'])
        raw=originals.get(lib.own_jsons['MartialRange'])
        if raw:owned.update(int(r['BaseID']) for r in json.loads(raw.decode('utf-8-sig')).get('Items',[]))
        if any(AREA_START<=i<AREA_END and (i not in owned or i in lib.overrides['MartialRange']) for i in lib.tables['MartialRange']):raise ValueError('其他模组占用了自定义技能范围编号区间，请移除冲突后重新读取')
        from growth_runtime import patch_runtime
        p=lib.root/'DreamRivakes_Data/Plugins/RaceLogic_Release_x64.dll'
        before=originals.setdefault(p,p.read_bytes())
        if p.read_bytes()!=before:raise ValueError('运行库读取后发生变化，请重新读取')
        # Growth may have staged a compatible patch already; upgrade that image.
        payloads[p]=patch_runtime(payloads.get(p,before),area_only=True,areas=entries)
    else:
        # Removing the final clause must also remove its native hit-grid registry.
        from growth_runtime import installed_areas,patch_runtime
        p=lib.root/'DreamRivakes_Data/Plugins/RaceLogic_Release_x64.dll'
        before=originals.setdefault(p,p.read_bytes())
        staged=payloads.get(p,before)
        from range_runtime import AREA_MAGIC,LEGACY_AREA_MAGIC
        if (AREA_MAGIC in staged or LEGACY_AREA_MAGIC in staged) and installed_areas(staged):payloads[p]=patch_runtime(staged,area_only=True,areas=[])
    return assets
