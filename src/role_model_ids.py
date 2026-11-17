"""Keep appearance IDs in the native signed-short transport range."""
import re
MIN_NEW=16000
MAX_ID=32767

def safe(ident):return type(ident) is int and 0<ident<=MAX_ID

def new_id(lib):
 from role_animation import animation_rows
 used=set(lib.tables['RoleModel'])|set(animation_rows(lib.assets.script('SpineAnimaitionTime.lua')))
 for i in range(MIN_NEW,MAX_ID+1):
  if i not in used:return i
 raise ValueError('安全人物模型编号已用完，未写入')

def migrate(lib):
 """Retain legacy rows for old saves; move editor-owned references and complete timing."""
 mapping={};protected=set()
 for rid,rec in lib.meta.items():
  if int(rid) not in lib.roles:continue
  art=lib.row(int(rid)).get('ArtID')
  if any(lib.overrides['Role'].get(i) for i in lib.roles[int(rid)]) or lib.overrides['RoleModel'].get(art):
   from mod_compatibility import note
   note(lib,'受其他MOD保护的人物模型未自动迁移：'+rid);protected.add(rid);continue
  if not art or safe(art):continue
  if art not in mapping:mapping[art]=lib.clone('RoleModel',art)
 for rid,rec in lib.meta.items():
  if int(rid) not in lib.roles or rid in protected:continue
  for ident in lib.roles[int(rid)]:
   old=lib.tables['Role'][ident].get('ArtID')
   if old in mapping:lib.set('Role',ident,{'ArtID':mapping[old]})
  if rec.get('art_id') in mapping:
   old=rec['art_id'];rec['art_id']=mapping[old];rec['animation_source']=old
   rec['owned_art']=True
  settings=rec.get('settings',{})
  if settings.get('model_source') in mapping:settings['model_source']=mapping[settings['model_source']]
 return mapping

BOUND_MARKER='-- MJH_MODEL_BINDING_V223'
ROLE_LOOKUP='''local _mjh_role_groups_source, _mjh_role_groups
local function _mjh_model_role(typeID)
    if not TB_Role then return nil end
    if TB_Role[typeID] then return TB_Role[typeID] end
    if _mjh_role_groups_source ~= TB_Role then
        _mjh_role_groups = {}
        for _, role in pairs(TB_Role) do
            if type(role) == "table" and role.RoleID and not _mjh_role_groups[role.RoleID] then
                _mjh_role_groups[role.RoleID] = role
            end
        end
        _mjh_role_groups_source = TB_Role
    end
    return _mjh_role_groups[typeID]
end
'''
HELPER='''-- MJH_MODEL_TRANSPORT_V237
-- MJH_MODEL_BINDING_V223
'''+ROLE_LOOKUP+'''local function _mjh_restore_model_id(data)
    if not data then return data end
    if MJHDisguiseIsSlot and MJHDisguiseIsSlot(data.uiModelID) then return data end
    local manager = TableDataManager:GetInstance()
    local role = _mjh_model_role(data.uiTypeID)
    local configured = role and role.ArtID
    local model = configured and manager:GetTableData("RoleModel", configured)
    if model and type(configured) == "number" and configured > 0 and configured <= 32767 and ((type(model.Texture) == "string" and string.sub(model.Texture, 1, 14) == "#model_editor/") or (type(model.Model) == "string" and string.sub(model.Model, 1, 11) == "mjh_mobile_")) then
        -- Follow the explicitly bound appearance in existing character packets.
        -- Keep equipment, party, location and progression fields untouched.
        data.uiModelID = configured
        return data
    end
    if not data.uiModelID or data.uiModelID >= 0 then return data end
    if manager:GetTableData("RoleModel", data.uiModelID) then return data end
    if model then
        data.uiModelID = configured
    end
    return data
end
'''

LEGACY_HELPER='''-- MJH_MODEL_TRANSPORT_V237
local function _mjh_restore_model_id(data)
    if not data or not data.uiModelID or data.uiModelID >= 0 then return data end
    if TableDataManager:GetInstance():GetTableData("RoleModel", data.uiModelID) then return data end
    local role = TB_Role and TB_Role[data.uiTypeID]
    if role and role.ArtID and TableDataManager:GetInstance():GetTableData("RoleModel", role.ArtID) then
        -- Repair the client view of an overflowed packet; do not change save/party state.
        data.uiModelID = role.ArtID
    end
    return data
end
'''

def patch_runtime(text):
 if BOUND_MARKER in text:return text
 start=text.index('function RoleDataManager:GetRoleData(roleID)');end=text.index('function RoleDataManager:IsMarryed',start)
 if '-- MJH_MODEL_TRANSPORT_V237' in text:
  old=text.index('-- MJH_MODEL_TRANSPORT_V237')
  if old>=start:raise ValueError('人物模型同步修复入口不兼容，未写入')
  return text[:old]+HELPER+text[start:]
 block=text[start:end]
 old='return info.RoleInfos[roleID];'
 if block.count(old)!=3:raise ValueError('人物模型传输修复入口不兼容，未写入')
 block=block.replace(old,'return _mjh_restore_model_id(info.RoleInfos[roleID]);')
 return text[:start]+HELPER+block+text[end:]

def repair(data):
 from client_config import Assets
 # Remove temporary per-frame diagnostic statements before publishing the repair.
 for name in ['RoleDataManager.lua','SpineRoleUI.lua','ResourcesMgr.lua']:
  a=Assets(data);text=a.script(name)
  text=re.sub(r'^.*DRCSRef\.Log(?:Error)?\("\[MJH_MODEL[^\r\n]*\r?\n','',text,flags=re.M)
  text=re.sub(r'^.*local _mjh_sr = objSpine:GetComponent\("SkeletonRenderer"\)\r?\n','',text,flags=re.M)
  text=re.sub(r'local _mjh_art = (TableDataManager:GetInstance\(\):GetTableData\("RoleModel", roleData.uiModelID\))\s+return _mjh_art',r'return \1',text)
  if text!=a.script(name):data=a.replace_script(name,text)
 a=Assets(data);old=a.script('RoleDataManager.lua');new=patch_runtime(old)
 return a.replace_script('RoleDataManager.lua',new) if old!=new else data
