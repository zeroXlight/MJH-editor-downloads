"""Readable configuration scopes and reports; never infer combat damage from UI text."""
import json
import re
from martial_editor import DEPARTS, RANKS, SECTIONS


def clan_names(lib):
    if hasattr(lib, '_preview_clans'):
        return lib._preview_clans
    # Only names are needed. Clan.lua also contains constants unrelated to martial filters.
    result = {int(i): lib.text(int(n)) for i, n in re.findall(
        r'\[(\d+)\]\s*=\s*\{[^\r\n]*?\bNameID=(\d+)', lib.assets.script('Clan.lua'))}
    for path in sorted((lib.root / 'ModProject/GameProject/Mod_MJH/Json').glob('Clan_*.json')):
        for row in json.loads(path.read_text(encoding='utf-8-sig')).get('Items', []):
            if 'NameID' in row:
                result[int(row['BaseID'])] = lib.text(row['NameID'])
    lib._preview_clans = result
    return result


def filter_description(lib, mid, fid):
    """Same priority as GetMartialFilterDesc, including automatic category."""
    if not fid:
        return '不额外筛选（按效果类型作用）'
    row = lib.tables['MartialFilter'].get(fid)
    if row is None:
        return f'未知筛选条件 {fid}（无法确认作用范围）'
    target = row.get('MartialID', 0)
    if target:
        return lib.name(target) if target in lib.tables['Martial'] else f'未知武学 {target}'
    clan = row.get('ClanID', 0)
    prefix = clan_names(lib).get(clan, f'门派 {clan}') if clan else '所有'
    rank = row.get('Rank', 0)
    if rank:
        prefix += RANKS.get(rank, f'品质 {rank}') + '品质'
    for field, yes in [('Toxic', '有毒'), ('Multistage', '多段')]:
        value = row.get(field, 0)
        if value == lib.enums.get('TBoolean.BOOL_YES', 1):
            prefix += yes
        elif value:
            prefix += f'未知{field}条件 {value}'
    auto = row.get('AutoMartialType') == lib.enums.get('TBoolean.BOOL_YES', 1)
    depart = lib.tables['Martial'][mid].get('DepartEnum', 0) if auto else row.get('MartialType', 0)
    result=prefix + (DEPARTS.get(depart, f'类别 {depart}') if depart and depart != 15 else '武学') + ('（跟随本武学类别）' if auto else '')
    if str(fid) in getattr(lib,'scope_groups',{}):result+='（内功以外所有类别；保存时按类别展开）'
    elif depart==10:result+='（游戏原生外功范围）'
    return result


def filter_choices(lib, mid):
    owners={}
    for ident,m in lib.tables['Martial'].items():
        for key in SECTIONS.values():
            for cid in m.get(key,[]):
                row=lib.tables['MartialItem'].get(cid,{})
                for slot in (1,2):
                    fid=row.get(f'MartialFilter{slot}',0)
                    if fid:
                        names=owners.setdefault(fid,[]);name=lib.name(ident)
                        if name not in names and len(names)<3:names.append(name)
    choices={'不额外筛选 · 0':0}
    for fid in sorted(lib.tables['MartialFilter']):
        label=f'{filter_description(lib,mid,fid)} · {fid}'
        if fid in owners:label+='（来源：'+' / '.join(owners[fid])+'）'
        choices[label]=fid
    return choices


def effect_scope(lib, mid, row, slot):
    kind = row.get(f'EffectEnum{slot}', 0)
    fid = row.get(f'MartialFilter{slot}', 0)
    if kind in (7, 8):
        return '修炼者自身' + (f'（附带筛选：{filter_description(lib, mid, fid)}；需校验是否适用）' if fid else '')
    if fid:
        return filter_description(lib, mid, fid)
    if kind in (9, 10):
        return '本武学「' + lib.name(mid) + '」'
    if kind == 12:
        return '本系别武学（' + DEPARTS.get(lib.tables['Martial'][mid]['DepartEnum'], '未知') + '）'
    return '按技能 / 模板逻辑执行' if kind else '无效果'


def describe_effects(lib, mid, key, row):
    results = []
    for slot in (1, 2):
        kind = row.get(f'EffectEnum{slot}', 0)
        from martial_ranges import clause_range,range_name
        area=clause_range(lib,row,slot) if key=='UnlockClauses' else None
        if area:
            scope='指定武学「'+lib.name(area['target'])+'」'
            name='改变技能作用范围'+('（已启用）' if area['enabled'] else '（旧版停用记录，建议清除）')
            value=range_name(lib,area['range'])+' · '+str(area['range'])
            if not area['enabled']:value+='；请在管理范围词条中清除；旧版停用未能可靠取消效果'
            results.append({'scope':scope,'name':name,'value':value,'text':lib.text(lib.tables['Skill'][area['skill']].get('DescID',0))+'；'+name+' '+value,'filter':0})
            continue
        if not kind:
            continue
        attr = row.get(f'AttrEnum{slot}', 0)
        values = row.get(f'Effect{slot}Value', [])
        scope = effect_scope(lib, mid, row, slot)
        name = lib.attr_names.get(str(attr), f'属性 {attr}')
        if kind in (7, 9):
            value = '沿用游戏成长公式（请在每级成长窗口选择属性与数值）'
            if key=='GrowProIDs' and row.get('BaseID') in lib.tables['Martial'][mid].get(key,[]):
                try:
                    index=lib.tables['Martial'][mid][key].index(row['BaseID']);p=lib.growth_profile(mid,key,index,slot)
                    value=lib.growth.display(lib,p)
                    if p.get('independent'):value+='（独立成长，仅当前武学）'
                except ValueError as e:value+='；'+str(e)
            name = '每级' + name
        elif kind in (8, 10, 12):
            if attr in (304, 359):
                value = '按游戏武学威力公式计算；填写数值不作为固定加成'
            elif values:
                value = ('+' if values[0] >= 0 else '') + lib.attr_display(attr, values[0])
                if any(values[1:]):
                    value += f'；成长参数 {values[1:]}（按原生公式结算）'
            else:
                value = f'游戏等级公式，档次 {row.get(f"Grade{slot}", 0)}'
            if attr == 302:
                value += '（最终伤害修正系数，并非等额增伤）'
        elif kind in (6, 11):
            skill = lib.tables['Skill'].get(row.get(f'SkillID{slot}', 0), {})
            name = lib.text(skill.get('NameID', 0)) or '未知技能'
            value = lib.text(skill.get('DescID', 0)) or '按战斗表达式执行'
        else:
            name = lib.labels.get(('MartialItemEffect', kind), f'效果类型 {kind}')
            value = f'参数 {values}；额外等级 {row.get(f"Grade{slot}", 0)}'
        results.append({'scope': scope, 'name': name, 'value': value,
                        'text': f'{scope}：{name} {value}', 'filter': row.get(f'MartialFilter{slot}', 0)})
    return results


def stage_description(lib, mid, key, row, level=None):
    title = next(n for n, k in SECTIONS.items() if k == key)
    if key == 'UnlockClauses':
        title += f' {level}级'
    lines = [title] + [f'第 {i} 项：{r["text"]}' for i, r in enumerate(describe_effects(lib, mid, key, row), 1)]
    if row.get('CondID', 0):
        lines.append(f'还需满足阶段条件 {row["CondID"]}；等级达到不代表已触发。')
    if row.get('DesID', 0):
        lines.append('模板固定说明：' + lib.text(row['DesID']))
    return '\n'.join(lines)


def martial_report(lib, mid):
    m = lib.tables['Martial'][mid]
    lines = [f'{lib.name(mid)} · ID {mid}', '当前配置的完整效果说明（包含内存中已加入草稿的修改）',
             '这是作用范围与配置加成预览；实际战斗伤害还受角色、敌人、触发条件及原生公式影响。', '']
    from martial_forms import reference_names,references_text
    clan=m.get('ClanID',0);lines.extend([f'所属门派：{clan} · '+reference_names(lib,'ClanID').get(clan,'未知名称'),
        '学习条件：'+references_text(lib,'LearnCondition',m.get('LearnCondition',[]),m.get('LearnConditionValue',[])),
        '附加标签：'+references_text(lib,'MartialTags',m.get('MartialTags',[])),
        f'阴 / 阳系数：阳性 {m.get("MascCoef",0)/10000:g}；阴性 {m.get("FemiCoef",0)/10000:g}', ''])
    for section, key in SECTIONS.items():
        lines.append('【' + section + '】')
        for index, cid in enumerate(m.get(key, [])):
            row = lib.tables['MartialItem'].get(cid, {})
            level = m.get('UnlockLvls', [])[index] if key == 'UnlockClauses' else None
            lines.append(stage_description(lib, mid, key, row, level))
        lines.append('')
    from martial_ranges import references,range_name
    incoming=references(lib,target=mid)
    if incoming:
        lines.append('【其他武学提供的技能范围词条】')
        for ref in incoming:
            if ref['source']==mid:continue
            lines.append(('已启用' if ref['enabled'] else '已停用')+' · '+lib.name(ref['source'])+' · '+str(ref['source'])+' → '+range_name(lib,ref['range'])+'（'+str(lib.tables['Martial'][ref['source']]['UnlockLvls'][ref['index']])+'级解锁）')
        lines.append('启用词条仍需提供武学装备并达到等级；停用请在管理范围词条中清除；旧版停用未能可靠取消效果。')
    lines.append('【适用性校验】')
    if lib.growth and lib.growth.changes:
        lines.append('本次修改了共享成长表；同类别 / 品质并使用该成长的其他武学也会改变。')
    lines.extend(lib.effect_audit(mid))
    return '\n'.join(lines)


def report_payloads(lib, payloads, originals):
    """Report all martial arts referencing changed rows, including shared definitions."""
    changed = set(lib.changes['Martial'])
    for mid, m in lib.tables['Martial'].items():
        refs = [c for key in SECTIONS.values() for c in m.get(key, [])]
        if any(c in lib.changes['MartialItem'] for c in refs):
            changed.add(mid)
        for cid in refs:
            row = lib.tables['MartialItem'].get(cid, {})
            if any(row.get(f'MartialFilter{s}', 0) in lib.changes['MartialFilter'] or
                   row.get(f'SkillID{s}', 0) in lib.changes['Skill'] for s in (1, 2)):
                changed.add(mid)
        if lib.growth and lib.growth.changes:
            for cid in m.get('GrowProIDs',[]):
                row=lib.tables['MartialItem'].get(cid,{})
                for slot in (1,2):
                    if row.get(f'EffectEnum{slot}') not in (7,9):continue
                    from codec import decode
                    from engine import SCHEMAS
                    if any(g['AttrType']==row.get(f'AttrEnum{slot}') and g['IsRoleAttr']==int(row.get(f'EffectEnum{slot}')==7) and (g['KfType']==0 or g['KfType']==m['DepartEnum']) and g['RankDatas'][m['Rank']]!=decode(lib.growth.native[gid],'KungfuBase',SCHEMAS)['RankDatas'][m['Rank']] for gid,g in lib.growth.changes.items()):changed.add(mid)
    for mid in sorted(changed):
        path = lib.root / f'装备编辑器配置/武学效果说明/{mid}.txt'
        originals.setdefault(path, path.read_bytes() if path.exists() else None)
        payloads[path] = martial_report(lib, mid).encode('utf-8-sig')
