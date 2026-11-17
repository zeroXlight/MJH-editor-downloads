"""AoYi formulas, using the game's protobuf and client Lua configuration."""
import copy

AUSTRAIN_FEATURE = 1  # KFFeatureType.KFFT_AustrianMartialArts

def recipe_cap(lib,row):
    mids=row.get('MartialList',[])
    if not mids:raise ValueError('组合武学为空，无法计算奥义上限')
    caps=[lib.tables['Martial'].get(mid,{}).get('LvLimit',0) for mid in mids]
    if any(type(cap) is not int or not 1<=cap<=1000 for cap in caps):
        raise ValueError('组成武学缺少有效的修炼上限，未修改奥义上限')
    return min(caps)

def sync_caps(lib):
    """Synchronize result caps from ingredient CAPS, not unlock thresholds."""
    from mod_compatibility import note
    desired={};conflicts=set()
    for ident,row in lib.tables['AoYi'].items():
        target=row.get('AoYiID');martial=lib.tables['Martial'].get(target)
        if not martial or martial.get('KFFeature')!=AUSTRAIN_FEATURE:continue
        if any(lib.tables['Martial'].get(mid,{}).get('KFFeature')==AUSTRAIN_FEATURE for mid in row.get('MartialList',[])):
            note(lib,f'奥义公式 {ident} 含嵌套组合，未自动改变上限');continue
        try:cap=recipe_cap(lib,row)
        except ValueError as error:note(lib,f'奥义公式 {ident} 上限已跳过：{error}');continue
        if target in desired and desired[target]!=cap:conflicts.add(target)
        desired[target]=cap
    changes=[]
    for target,cap in desired.items():
        if lib.tables['Martial'][target].get('LvLimit')==cap:continue
        if target in conflicts or target in lib.overrides.get('Martial',{}):
            note(lib,f'奥义 {target} 有冲突公式或外部覆盖，未自动修改上限');continue
        changes.append((target,cap))
    for target,cap in changes:lib.set('Martial',target,{'LvLimit':cap})
    return len(changes)

def result_choices(lib):
    return {i:lib.name(i) for i,m in lib.tables['Martial'].items()
            if m.get('KFFeature') == AUSTRAIN_FEATURE and m.get('MartMovIDs')}

def ingredient_choices(lib):
    # Nested AoYi formulas require a different dependency/update mechanism.
    return {i:lib.name(i) for i,m in lib.tables['Martial'].items()
            if m.get('KFFeature') != AUSTRAIN_FEATURE}

def validate_recipe(lib,row,editing=None):
    target=row.get('AoYiID',0)
    if target not in result_choices(lib):raise ValueError('结果请选择有完整招式的秘奥义武学，或复制现有秘奥义创建新功法')
    mids=row.get('MartialList',[]);levels=row.get('LVList',[])
    if not 2 <= len(mids) <= 64:raise ValueError('组成武学需要 2～64 门；原版公式通常为 2～3 门')
    if len(mids)!=len(levels):raise ValueError('组成武学和所需等级数量不一致')
    if len(mids)!=len(set(mids)):raise ValueError('同一公式不能重复加入相同武学')
    valid=ingredient_choices(lib)
    for mid,level in zip(mids,levels):
        if mid not in valid:raise ValueError(f'组成武学 {mid} 不存在或属于秘奥义，暂不支持嵌套组合')
        if type(level) is not int or not 1<=level<=1000:raise ValueError('所需等级须为 1～1000 的整数')
    turn=row.get('EffectiveRound',0)
    if type(turn) is not int or not 1<=turn<=1000:raise ValueError('可用回合须为 1～1000 的整数（仅该回合可用）')
    for ident,recipe in lib.tables['AoYi'].items():
        if ident!=editing and recipe.get('AoYiID')==target:
            raise ValueError(f'《{lib.name(target)}》已有公式 {ident}，请编辑该公式或复制为新功法')
    return row

def recipe_text(lib,row):
    mid=row.get('AoYiID',0);name=lib.name(mid) if mid in lib.tables['Martial'] else '未知武学'
    lines=[f'《{name}》 · 武学 ID {mid} · 公式 ID {row.get("BaseID","待生成")}',
           f'仅第 {row.get("EffectiveRound",0)} 回合可用。组合条件：']
    for ident,level in zip(row.get('MartialList',[]),row.get('LVList',[])):
        label=lib.name(ident) if ident in lib.tables['Martial'] else '未知武学'
        lines.append(f'《{label}》 · ID {ident} ≥ {level} 级')
    lines.append('组合所需等级可独立设置，不受组成武学修炼上限限制。')
    lines.append('全部组成武学满足等级后解锁；奥义当前等级遵循原生组合机制。结果武学的修炼上限同步为组成武学修炼上限的最低值，与解锁所需等级分开计算。')
    caps=[lib.tables['Martial'].get(i,{}).get('LvLimit',0) for i in row.get('MartialList',[])]
    if caps:lines.append(f'组成武学当前基础修炼上限的最低值：{min(caps)} 级。')
    lines.append('游戏内上限按该角色各材料武学动态上限的最低值显示，包含原生额外上限加成；材料实际等级不会被当作修炼上限。')
    lines.append('威力、效果、图标和动画由结果武学自身配置决定，可在武学编辑中继续修改。')
    if row.get('GiftList'):lines.append('原公式的天赋字段已保留；现有公式未使用该字段，编辑器不添加未验证的天赋条件。')
    return '\n'.join(lines)

def save_recipe(lib,template,ingredients,turn,*,editing=None,new_name=None):
    """Atomic draft edit: new results clone complete existing AoYi martial data."""
    with lib.edit():
        if editing is not None and editing not in lib.tables['AoYi']:raise ValueError('待修改公式不存在')
        if template not in result_choices(lib):raise ValueError('请选择有效的秘奥义结果 / 模板')
        if new_name is not None and not new_name.strip():raise ValueError('请输入新秘奥义名称')
        candidate={'AoYiID':template,'MartialList':[p[0] for p in ingredients],
                   'LVList':[p[1] for p in ingredients],'EffectiveRound':turn}
        # Check before copying expensive combat structures. Uniqueness is checked
        # after the clone; new_name creates a distinct result martial.
        probe=copy.copy(lib);probe.tables={**lib.tables,'AoYi':{} if new_name is not None else lib.tables['AoYi']}
        validate_recipe(probe,candidate,editing)
        target=lib.new_martial(template,new_name.strip()) if new_name is not None else template
        ident=editing if editing is not None else lib.new_id('AoYi',1)
        candidate['AoYiID']=target;candidate['BaseID']=ident
        candidate['GiftList']=list(lib.tables['AoYi'].get(ident,{}).get('GiftList',[]))
        validate_recipe(lib,candidate,editing)
        lib.set('AoYi',ident,candidate)
        lib.set('Martial',target,{'LvLimit':recipe_cap(lib,candidate)})
        return ident,target

def report_payload(lib,payloads,originals):
    if not lib.changes['AoYi']:return
    path=lib.root/'装备编辑器配置/秘奥义组合说明.txt'
    originals[path]=path.read_bytes() if path.exists() else None
    text='秘奥义组合配置（以本次读取及草稿为准）\n\n'+'\n\n'.join(recipe_text(lib,r) for _,r in sorted(lib.tables['AoYi'].items()))
    payloads[path]=text.encode('utf-8')
