"""Resolve battle-specific legacy model packets before any renderer/action lookup."""
from role_model_ids import ROLE_LOOKUP
BOUND_MARKER='-- MJH_BATTLE_BINDING_V223'
HELPER='''-- MJH_BATTLE_MODEL_V238
-- MJH_BATTLE_BINDING_V223
'''+ROLE_LOOKUP+'''local function _mjh_battle_model_id(roleTypeID, packetModelID, faceData)
    if MJHDisguiseIsSlot then
        if faceData and MJHDisguiseIsSlot(faceData.uiModelID) then return faceData.uiModelID end
        if MJHDisguiseIsSlot(packetModelID) then return packetModelID end
    end
    local manager = TableDataManager:GetInstance()
    local function valid(id)
        return type(id) == "number" and id > 0 and id <= 32767 and manager:GetTableData("RoleModel", id) ~= nil
    end
    local role = _mjh_model_role(roleTypeID)
    local configured = role and role.ArtID
    local model = valid(configured) and manager:GetTableData("RoleModel", configured)
    if model and ((type(model.Texture) == "string" and string.sub(model.Texture, 1, 14) == "#model_editor/") or (type(model.Model) == "string" and string.sub(model.Model, 1, 11) == "mjh_mobile_")) then return configured end
    local function restore(id)
        if valid(id) then return id end
        if type(id) == "number" and (id < 0 or id > 32767) and valid(configured) then return configured end
        return nil
    end
    local face = faceData and restore(faceData.uiModelID)
    if face then return face end
    local packet = restore(packetModelID)
    if packet then return packet end
    if valid(configured) then return configured end
    return packetModelID or 0
end
'''

LEGACY_HELPER='''-- MJH_BATTLE_MODEL_V238
local function _mjh_battle_model_id(roleTypeID, packetModelID, faceData)
    local manager = TableDataManager:GetInstance()
    local function valid(id)
        return type(id) == "number" and id > 0 and id <= 32767 and manager:GetTableData("RoleModel", id) ~= nil
    end
    local role = TB_Role and TB_Role[roleTypeID]
    local configured = role and role.ArtID
    local function restore(id)
        if valid(id) then return id end
        if type(id) == "number" and (id < 0 or id > 32767) and valid(configured) then return configured end
        return nil
    end
    local face = faceData and restore(faceData.uiModelID)
    if face then return face end
    local packet = restore(packetModelID)
    if packet then return packet end
    if valid(configured) then return configured end
    return packetModelID or 0
end
'''

def patch_unit(text):
 if BOUND_MARKER in text:return text
 anchor='function Unit:Init(kParent, kUnitData, uiModleID,uiTypeID,startTime,isImmediately)'
 if '-- MJH_BATTLE_MODEL_V238' in text:
  start=text.index('-- MJH_BATTLE_MODEL_V238');end=text.index(anchor)
  if start>=end:raise ValueError('战斗模型绑定修复入口不兼容，未写入')
  return text[:start]+HELPER+'\n'+text[end:]
 old='self.uiModleID = self.kRoleFaceData ~= nil and self.kRoleFaceData.uiModelID or uiModleID'
 if text.count(old)!=1:raise ValueError('战斗模型初始化入口不兼容，未写入')
 text=text.replace(old,'self.uiModleID = _mjh_battle_model_id(self.uiTypeID, uiModleID, self.kRoleFaceData)',1)
 if text.count(anchor)!=1:raise ValueError('战斗人物入口不兼容，未写入')
 return text.replace(anchor,HELPER+'\n'+anchor,1)

def repair(data):
 from client_config import Assets
 a=Assets(data);old=a.script('Unit.lua');new=patch_unit(old)
 return a.replace_script('Unit.lua',new) if old!=new else data
