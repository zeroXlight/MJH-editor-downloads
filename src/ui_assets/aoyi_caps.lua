-- Use the owner's live ingredient limits, including the native extra levels.
-- Do not confuse them with uiLevel or the recipe's unlock thresholds.
function MartialDataManager:MJHAoyiMaxLevel(data)
    if not data or not data.uiRoleUID then return nil end
    local formulas=TableDataManager:GetInstance():GetTable('AoYi') or {}
    local recipe=nil
    for _,row in pairs(formulas) do
        if row.AoYiID==data.uiTypeID then
            if recipe then return nil end -- ambiguous external formulas
            recipe=row
        end
    end
    if not recipe or not recipe.MartialList or #recipe.MartialList==0 then return nil end
    local owned=self:GetRoleMartial(data.uiRoleUID)
    if not owned then return nil end
    local cap=nil
    for _,mid in ipairs(recipe.MartialList) do
        local ingredient=nil
        for _,candidate in pairs(owned) do
            if candidate.uiTypeID==mid and candidate.uiRoleUID==data.uiRoleUID then
                if ingredient then return nil end
                ingredient=candidate
            end
        end
        if not ingredient or type(ingredient.uiMaxLevel)~='number' or ingredient.uiMaxLevel<1 then return nil end
        cap=cap and math.min(cap,ingredient.uiMaxLevel) or ingredient.uiMaxLevel
    end
    return cap
end
