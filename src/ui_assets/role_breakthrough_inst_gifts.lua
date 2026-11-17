-- Observation and battle screens call GetGifts, bypassing GetGiftTypeData.
-- Return a derived list; preserve indices, source records and learned gifts.
local mjhOriginalInstGifts=InstRole.GetGifts
function InstRole:GetGifts()
    local original=mjhOriginalInstGifts(self)
    local result={}
    local manager=GiftDataManager:GetInstance()
    for index,rawType in pairs(original) do
        local uid=(self.auiRoleGift or {})[index]
        local data=uid and manager:GetGiftTypeData(uid)
        result[index]=data and data.BaseID or rawType
    end
    return result
end
