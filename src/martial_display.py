"""Client-only clause labels and unlock display; battle tables are untouched."""
import json,re
from martial_editor import lua_value
from martial_preview import effect_scope

BEGIN='-- MJH clause display registry BEGIN'
END='-- MJH clause display registry END'
FUNCTION='function MartialDataManager:GenMartialItemTriggerDesc('

def owned_ids(lib,name):
    raw=lib.originals.get(lib.own_jsons[name])
    saved={int(r['BaseID']) for r in json.loads(raw.decode('utf-8-sig')).get('Items',[])} if raw else set()
    return saved|set(lib.changes[name])

def clause_label(lib,mid,row):
    if row.get('DesID',0):return lib.text(row['DesID'])
    result=[];custom_skills=owned_ids(lib,'Skill')
    for slot in (1,2):
        kind=row.get(f'EffectEnum{slot}',0)
        if not kind:
            from martial_ranges import clause_range
            if clause_range(lib,row,slot):
                skill=lib.tables['Skill'][row[f'SkillID{slot}']]
                result.append(lib.text(skill.get('DescID',0))+'（旧版停用记录，请在编辑器清除）')
            continue
        if kind in (8,10,12):
            attr=row.get(f'AttrEnum{slot}',0);values=row.get(f'Effect{slot}Value',[])
            if not values or row.get(f'Grade{slot}',0) or attr in (304,359) or any(values[1:]):return None
            name=lib.attr_names.get(str(attr))
            if not name:return None
            scope=effect_scope(lib,mid,row,slot)
            fid=row.get(f'MartialFilter{slot}',0)
            if lib.tables['MartialFilter'].get(fid,{}).get('MartialID')==mid:scope='本武学「'+lib.name(mid)+'」'
            scope=scope.replace('（游戏原生外功范围）','')
            value=lib.attr_display(attr,values[0])
            result.append(scope+'：'+name+('+' if values[0]>=0 else '')+value)
        elif kind==6 and row.get(f'SkillID{slot}') in custom_skills:
            skill=lib.tables['Skill'][row[f'SkillID{slot}']]
            if not skill.get('DescID'):return None
            result.append(lib.text(skill['DescID']))
        else:return None  # Keep native dynamic skill/growth descriptions.
    return '，'.join(result) if result else None

def registry(lib):
    ids=owned_ids(lib,'MartialItem');result={}
    for mid,m in lib.tables['Martial'].items():
        entries={cid:clause_label(lib,mid,lib.tables['MartialItem'][cid]) for cid in m.get('UnlockClauses',[]) if cid in ids and cid in lib.tables['MartialItem']}
        if entries:result[mid]=entries
    return result

def patch_client(text,lib):
    """Only known editor clauses get a level fallback. Conditions still gate it."""
    text=re.sub(re.escape(BEGIN)+r'.*?'+re.escape(END)+r'\r?\n?', '',text,flags=re.S)
    if text.count(FUNCTION)!=1:raise ValueError('客户端词条显示入口不匹配，未修改显示配置')
    entries=registry(lib)
    data='{'+','.join(f'[{mid}]={{'+','.join(f'[{cid}]='+('false' if label is None else lua_value(label)) for cid,label in rows.items())+'}' for mid,rows in sorted(entries.items()))+'}'
    text=text.replace(FUNCTION,BEGIN+'\nlocal _mjh_clause_labels = '+data+'\n'+END+'\n'+FUNCTION,1)
    if '-- MJH clause display logic V2.0.6' not in text:
        anchor='        for iStaticMatItemLv = 1,30 do'
        if text.count(anchor)!=1:raise ValueError('客户端解锁缓存显示逻辑不匹配')
        replacement='''        -- MJH clause display logic V2.0.6
        local _mjh_levels, _mjh_seen = {}, {}
        for _, lv in ipairs(staticMartialData.UnlockLvls or {}) do
            if not _mjh_seen[lv] then _mjh_levels[#_mjh_levels+1]=lv; _mjh_seen[lv]=true end
        end
        table.sort(_mjh_levels)
        for _, iStaticMatItemLv in ipairs(_mjh_levels) do'''
        text=text.replace(anchor,replacement,1)
        old='''            if (matItemUnlockLookUp and matItemUnlockLookUp[matItemID] and  (matItemUnlockLookUp[matItemID] >= levelCond)) and'''
        new='''            local _mjh_rows = _mjh_clause_labels[staticMartialData.BaseID]
            local _mjh_owned = _mjh_rows and _mjh_rows[matItemID] ~= nil
            local _mjh_cached = matItemUnlockLookUp and matItemUnlockLookUp[matItemID] and (matItemUnlockLookUp[matItemID] >= levelCond)
            if ((_mjh_cached and (not _mjh_owned or iMartialCurLevel >= levelCond)) or (_mjh_owned and iMartialCurLevel >= levelCond)) and'''
        if text.count(old)!=1:raise ValueError('客户端词条颜色逻辑不匹配')
        text=text.replace(old,new,1)
        old="            local strFinalDesc = strCondDesc .. table.concat(matItemDesc, ',')"
        new=old+'''
            local _mjh_rows = _mjh_clause_labels[staticMartialData.BaseID]
            local _mjh_desc = _mjh_rows and _mjh_rows[matItemID]
            if _mjh_desc and (state ~= "lock" or IsWindowOpen("CollectionMartialUI")) then
                strFinalDesc = strCondDesc .. _mjh_desc
            end'''
        if text.count(old)!=1:raise ValueError('客户端词条说明逻辑不匹配')
        text=text.replace(old,new,1)
    return text
