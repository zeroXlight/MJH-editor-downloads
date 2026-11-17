-- Account progress remains in native RoleCard records; pet maps are untouched.
-- MJH_VISIBLE_ROLE_ROSTER
local mjhPreviousUpgrade=CardsUpgradeDataManager.GetUpgrade
function CardsUpgradeDataManager:GetUpgrade(kind,rank)
    if kind==2 then return 10 end
    return mjhPreviousUpgrade(self,kind,rank)
end
function CardsUpgradeDataManager:MJHIsCustomRole(id,row)
    return mjhSavedCustom[id] or (id>=1700000000 and (row.BaseID or 0)>=1600000000)
end
local function mjhRoleRows()
    local rows={}
    for key,row in pairs(TB_Role or TableDataManager:GetInstance():GetTable('Role') or {}) do
        if type(row)=='table' then
            local id=row.RoleID or row.BaseID or key
            local custom=type(id)=='number' and CardsUpgradeDataManager:GetInstance():MJHIsCustomRole(id,row)
            if type(id)=='number' and id>0 and (mjhMobileRoster[id] or custom) and row.Status~=27 and (row.Rank or 0)>0 and (row.Rank or 0)<=8 then
                local old=rows[id]
                if not old or (row.Index or 0)<(old.Index or 0) then rows[id]=row end
            end
        end
    end
    return rows
end
function CardsUpgradeDataManager:MJHBreakthroughRoles()
    local rows=mjhRoleRows()
    self.roleIdCardListMap=self.roleIdCardListMap or {}
    for id,_ in pairs(rows) do
        self.roleIdCardListMap[id]=self.roleIdCardListMap[id] or {level=0,piece=0}
        -- Only the visible mobile roster and player creations are shown.
        self.roleIdCardListMap[id].unlock=true
        self.roleIdCardListMap[id].IsHide=false
    end
    return rows
end
local mjhOldRoleList=CardsUpgradeDataManager.GetEntireRoleCardList
function CardsUpgradeDataManager:GetEntireRoleCardList()
    mjhOldRoleList(self)
    self:MJHBreakthroughRoles()
    return self.roleIdCardListMap
end
local mjhOldRoleInfo=CardsUpgradeDataManager.SetRolePetInfo
function CardsUpgradeDataManager:SetRolePetInfo(info)
    if info and info.uiCardType==0 then self:MJHBreakthroughRoles() end
    return mjhOldRoleInfo(self,info)
end
function CardsUpgradeDataManager:MJHBreakthroughCost(level)
    local pieces={1,2,4,6,8,12,16,24,32,50}
    return pieces[level+1] and pieces[level+1]*500 or nil
end
function CardsUpgradeDataManager:MJHDefaultGifts(id,row,level)
    local replace={};local trees=self:GetGiftTreeByTypeID(id) or {}
    for tree in pairs(trees) do
        local config=GetTableData('RoleWishTree',tree)
        local selected=self:GetTreeGift(id,level,tree)
        if config and selected and selected>0 then
            for _,old in ipairs(config.AllGiftIDs or {}) do replace[old]=selected end
        end
    end
    local ids={};local seen={}
    for _,original in ipairs(row.Gift or {}) do
        local chosen=replace[original] or original
        if not seen[chosen] then ids[#ids+1]=chosen;seen[chosen]=true end
    end
    local extra=self:GetCurEffctStateByRoleID(id,RoleCardEffect.RCE_GetGift,level)
    if extra and extra>0 and not seen[extra] then ids[#ids+1]=extra end
    return ids
end
function CardsUpgradeDataManager:MJHResolveDefaultGift(roleid,original,level)
    local trees=self.map_Role2GiftTree and self.map_Role2GiftTree[roleid]
    if not trees then
        self.mjhFallbackGiftTrees=self.mjhFallbackGiftTrees or {}
        trees=self.mjhFallbackGiftTrees[roleid]
        if not trees then
            trees={};self.mjhFallbackGiftTrees[roleid]=trees
            for _,row in pairs(TableDataManager:GetInstance():GetTable('RoleCard') or {}) do
                if row.RoleID==roleid and row.EffectEnum==RoleCardEffect.RCE_GiftTreeUp then trees[row.EffectValue1]=true end
            end
        end
    end
    for tree in pairs(trees) do
        local config=GetTableData('RoleWishTree',tree)
        if config then for _,member in ipairs(config.AllGiftIDs or {}) do
            if member==original then return self:GetTreeGift(roleid,level,tree) or original end
        end end
    end
    return original
end
function CardsUpgradeDataManager:MJHGrowthChanges(id,row,level)
    local out={};local nextLevel=math.min(10,level+1)
    local function add(label,before,after) if before~=after then out[#out+1]={label,tostring(before),tostring(after)} end end
    add('六项基础属性','+'..(level*20)..'%','+'..(nextLevel*20)..'%')
    local quality=RoleCardEffect.RCE_RoleQualityUp
    local before=(row.Rank or 1)+(self:GetCurEffctStateByRoleID(id,quality,level) or 0)
    local after=(row.Rank or 1)+(self:GetCurEffctStateByRoleID(id,quality,nextLevel) or 0)
    before=math.min(8,before);after=math.min(8,after)
    add('角色品质',GetLanguageByID(RankType_Lang[before]) or tostring(before),GetLanguageByID(RankType_Lang[after]) or tostring(after))
    local kind=RoleCardEffect.RCE_Disposition
    add('初始好感加成',self:GetCurEffctStateByRoleID(id,kind,level) or 0,self:GetCurEffctStateByRoleID(id,kind,nextLevel) or 0)
    local old=self:MJHDefaultGifts(id,row,level);local new=self:MJHDefaultGifts(id,row,nextLevel)
    local function name(gift)
        local config=GetTableData('Gift',gift)
        return config and GetLanguageByID(config.NameID) or tostring(gift or '无')
    end
    for i,gift in ipairs(new) do add('专属天赋',name(old[i]),name(gift)) end
    return out
end
