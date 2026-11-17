-- Native display/save pools retain the original type. Derive only the local
-- player's default exclusive talent view; never rewrite pool records.
local mjhOriginalGiftType=GiftDataManager.GetGiftTypeData
function GiftDataManager:GetGiftTypeData(id)
    local original=mjhOriginalGiftType(self,id)
    if not original or self.bIsObserveData or self.bIsArenaObserveData or GetGameState()==-1 then return original end
    local instance=self:GetGiftData(id)
    if not instance or instance.uiGiftSourceType~=1 then return original end
    local game=globalDataPool:getData('GameData') or {}
    local pool=game.RoleInfos or {}
    local cards=CardsUpgradeDataManager:GetInstance()
    for _,role in pairs(pool) do
        for _,uid in pairs(role.auiRoleGift or {}) do
            if uid==id then
                local roleid=role.uiTypeID
                local level=tonumber(role.uiOverlayLevel) or cards:GetRoleCardLevelByRoleBaseID(roleid) or 0
                local chosen=cards:MJHResolveDefaultGift(roleid,instance.uiTypeID,level)
                return GetTableData('Gift',chosen) or original
            end
        end
    end
    return original
end
