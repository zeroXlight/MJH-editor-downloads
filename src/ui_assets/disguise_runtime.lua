-- MJH_DISGUISE_RUNTIME_V223
-- Composite rows are immutable and shared by ID; saved games only reference the ID.
local _mjh_disguise_config, _mjh_disguise_registry
local _mjh_disguise_generation=1
local _mjh_disguise_tables=setmetatable({}, {__mode="k"})
local function _mjh_disguise_copy(value)
    if type(value) ~= "table" then return value end
    local out = {}; for k,v in pairs(value) do out[k] = _mjh_disguise_copy(v) end; return out
end
local function _mjh_disguise_numbers(value)
    if type(value)~="table" then return value end
    local out={}
    for key,item in pairs(value) do
        local numeric=type(key)=="string" and string.match(key,"^%d+$") and tonumber(key)
        out[numeric or key]=_mjh_disguise_numbers(item)
    end
    return out
end
local function _mjh_disguise_load()
    if _mjh_disguise_config then return end
    local json = require("Base/Json/dkjson")
    local file = CS.System.IO.File
    local root = "mod/editor_disguise/"
    _mjh_disguise_config = assert(json.decode(file.ReadAllText(root.."catalog.json")))
    local registry = {version=1, entries={}}
    if file.Exists(root.."registry.json") then
        registry = assert(json.decode(file.ReadAllText(root.."registry.json")))
    end
    assert(registry.version == 1 and type(registry.entries) == "table", "Disguise registry invalid")
    -- JSON objects stringify the mixed numeric duration key and named event keys.
    for _,entry in pairs(registry.entries) do entry.timing=_mjh_disguise_numbers(entry.timing) end
    _mjh_disguise_registry = registry
end
function MJHDisguiseIsSlot(id)
    if type(id) ~= "number" then return false end
    _mjh_disguise_load()
    return id >= _mjh_disguise_config.first and id <= _mjh_disguise_config.last
end
function MJHDisguisePopulate(name, tab)
    if name ~= "RoleModel" and name ~= "SpineAnimaitionTime" then return tab end
    _mjh_disguise_load()
    local cached=_mjh_disguise_tables[tab]
    if cached and cached.generation==_mjh_disguise_generation then
        local intact=true
        for id,row in pairs(cached.rows) do if tab[id]~=row then intact=false;break end end
        if intact then return tab end
    end
    local rendered={}
    for key, entry in pairs(_mjh_disguise_registry.entries) do
        local id = tonumber(key)
        assert(id and id >= _mjh_disguise_config.first and id <= _mjh_disguise_config.last, "Disguise slot invalid")
        tab[id] = name == "RoleModel" and _mjh_disguise_copy(entry.row) or _mjh_disguise_copy(entry.timing)
        rendered[id]=tab[id]
    end
    _mjh_disguise_tables[tab]={generation=_mjh_disguise_generation,rows=rendered}
    return tab
end
function MJHDisguiseOptions()
    _mjh_disguise_load();return _mjh_disguise_config.options
end
function MJHDisguiseChoose(roleID, option)
    _mjh_disguise_load()
    local manager = TableDataManager:GetInstance()
    local current = RoleDataManager:GetInstance():GetRoleArtDataByID(roleID)
    assert(current, "Current disguise appearance missing")
    local row = _mjh_disguise_copy(current)
    row.Drawing=current.Drawing;row.Head=current.Head
    local source = current.BaseID
    if option.model then
        local model = assert(manager:GetTableData("RoleModel", option.model))
        for _, key in ipairs({"ModelID","Model","Texture","Hue","ModelScale","WeaponPos","WeaponScale","InitWeapom"}) do row[key] = _mjh_disguise_copy(model[key]) end
        source = option.model
    end
    if option.drawing then
        row.Drawing = option.drawing
        if option.head and option.head ~= "" then row.Head = option.head end
    end
    row.__Drawing=nil;row.__Head=nil;row.PictureID=0
    local timings = manager:GetTable("SpineAnimaitionTime")
    local timing = assert(timings[source], "Disguise animation timing unavailable")
    local json = require("Base/Json/dkjson")
    local signatureRow=_mjh_disguise_copy(row);signatureRow.BaseID=nil
    -- Stable signatures compare encoded snapshots by field rather than table iteration order.
    local function same(a,b)
        if type(a)~=type(b) then return false end
        if type(a)~="table" then return a==b end
        for k,v in pairs(a) do if not same(v,b[k]) then return false end end
        for k in pairs(b) do if a[k]==nil then return false end end
        return true
    end
    for key,entry in pairs(_mjh_disguise_registry.entries) do
        local old=_mjh_disguise_copy(entry.row);old.BaseID=nil
        if same(old,signatureRow) and same(entry.timing,timing) then return tonumber(key) end
    end
    local id
    for candidate=_mjh_disguise_config.first,_mjh_disguise_config.last do
        if not _mjh_disguise_registry.entries[tostring(candidate)] then id=candidate;break end
    end
    assert(id,"易容外观组合已达到容量，请保留现有配置并联系编辑器作者扩展，不能覆盖存档正在使用的组合")
    row.BaseID=id
    local entry={row=row,timing=_mjh_disguise_copy(timing)}
    local nextRegistry=_mjh_disguise_copy(_mjh_disguise_registry);nextRegistry.entries[tostring(id)]=entry
    local text=json.encode(nextRegistry)
    local file=CS.System.IO.File;local path="mod/editor_disguise/registry.json"
    -- Write before sending the native mask command so failed writes never leave an unresolvable save ID.
    file.WriteAllText(path..".tmp",text)
    local check=assert(json.decode(file.ReadAllText(path..".tmp")))
    assert(check.entries[tostring(id)],"Disguise registry verification failed")
    if file.Exists(path) then file.Replace(path..".tmp",path,path..".bak",true) else file.Move(path..".tmp",path) end
    _mjh_disguise_registry=nextRegistry
    _mjh_disguise_generation=_mjh_disguise_generation+1
    manager:GetTable("RoleModel")
    manager:GetTable("SpineAnimaitionTime")
    return id
end
-- MJH_DISGUISE_RUNTIME_END
