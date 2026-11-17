"""Keep special mobile attack names where supported; select a real PC attack otherwise."""
MARK='-- MJH_MOBILE_ATTACK_FALLBACK_2310'
HELPER='''-- MJH_MOBILE_ATTACK_FALLBACK_2310
local mjhNativeAttackAction = getAttackAction
getAttackAction = function(modelID, info)
    local native = mjhNativeAttackAction(modelID, info)
    if not info or not info.mjhMobileAttackFallback or info.action ~= "attack" then return native end
    local timings = TableDataManager:GetInstance():GetTableData("SpineAnimaitionTime", modelID)
    if not timings then return native end
    local function valid(name)
        return name and timings[name] and (timings[name][1] or 0) > 0
    end
    if native and string.sub(native, 1, 7) == "attack_" and valid(native) then return native end
    if valid(info.oldActionName) then return info.oldActionName end
    local kind = SPINE_ATTACK_TYPE[info.type or 2] or "s"
    for _, prefix in ipairs({"attack_" .. kind, "attack_g"}) do
        for _, number in ipairs({2, 1, 101}) do
            local name = string.format("%s_%03d", prefix, number)
            if valid(name) then return name end
        end
    end
    local candidates = {}
    for name in pairs(timings) do
        if type(name) == "string" and string.sub(name, 1, 7) == "attack_" and valid(name) then
            candidates[#candidates+1] = name
        end
    end
    table.sort(candidates)
    return candidates[1] or native
end
'''
def patch(text):
    if MARK in text:return text
    import re
    anchor=re.search(r'return\s+BattleSceneAnimation\s*;?\s*$',text)
    if not anchor or 'getAttackAction = function(' not in text:raise ValueError('手游武学动作选择入口不兼容，未写入')
    return text[:anchor.start()]+HELPER+'\n'+text[anchor.start():]

def stage(store,payloads,installed,results):
    if '12916' not in installed:return
    import json
    from client_config import Assets
    from martial_editor import performance_blocks
    from lua_data import parse,dump
    from mobile_martial_restore import STATE
    path=store.root/'DreamRivakes_Data/resources.assets';raw=payloads.get(path,store.read(path));a=Assets(raw)
    state=json.loads(payloads.get(store.root/STATE,store.read(store.root/STATE)))
    batch=next((b for b in state.get('additional_batches',[]) if '12916' in b['installed']),state)
    ids={batch['nodes'][k] for k in ('Skill:62000','Skill:2055') if k in batch.get('nodes',{})}
    # Older source packets used 2054 before the graph was namespaced.
    if 'Skill:2054' in batch.get('nodes',{}):ids.add(batch['nodes']['Skill:2054'])
    text=a.script('SkillPerformance.lua');rows=performance_blocks(text);edits=[]
    for ident in ids:
        if ident not in rows:raise ValueError('无相剑诀动作记录缺失：'+str(ident))
        start,end,body=rows[ident];row=parse(body);changed=False
        for entry in row.get('skillEffect',{}).values():
            info=entry.get('actionInfo',{})
            if info.get('action')=='attack' and info.get('num') in (201,202) and not info.get('mjhMobileAttackFallback'):
                info['mjhMobileAttackFallback']=True;changed=True
        if changed:edits.append((start+text[start:end].index('{'),end,dump(row)))
    for start,end,body in sorted(edits,reverse=True):text=text[:start]+body+text[end:]
    if edits:raw=a.replace_script('SkillPerformance.lua',text);a=Assets(raw)
    old=a.script('BattleSceneAnimation.lua');new=patch(old)
    if new!=old:raw=a.replace_script('BattleSceneAnimation.lua',new)
    if raw!=payloads.get(path,store.read(path)):
        payloads[path]=raw;results.append('修复无相剑诀动作选择：保留模型自带201/202特殊动作；没有对应动作时使用该模型实际存在的攻击动作，保留手游特效。')
