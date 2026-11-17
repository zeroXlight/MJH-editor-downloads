"""Client targeting and preview for actor-centred named areas."""
HELPERS = '''
local function _mjh_area(unit, martial)
    if not martial then return nil end
    for _, area in ipairs(_mjh_named_areas) do
        if area.target == martial.iMartialID then
            for _, source in pairs(unit.akMartialData or {}) do
                if source.iMartialID == area.source and source:IsEmbattle() and (source.iMartialLevel or 0) >= area.level then return area end
            end
        end
    end
end
local function _mjh_direction(cx,cy,ux,uy,face)
    local dx,dy = cx-ux,cy-uy
    if dx == 0 and dy == 0 then return face or 1,0 end
    if math.abs(dx) >= math.abs(dy) then return dx >= 0 and 1 or -1,0 end
    return 0,dy >= 0 and 1 or -1
end
local function _mjh_cast(unit,x,y)
    local martial = unit.akMartialData[unit.iCurChooseSkillIndex]
    local area = _mjh_area(unit,martial)
    if not area then return false,nil end
    local fx,fy = _mjh_direction(x,y,unit.iGridX,unit.iGridY,unit.iFace)
    local best,score
    local seen = {}
    local points = {}
    for _, offsets in ipairs({martial.aiCastRangePos or {},martial.aiCastRangePosY or {}}) do
        for _, offset in ipairs(offsets) do
            points[#points+1] = {unit.iGridX+offset[1],unit.iGridY+offset[2]}
        end
    end
    -- Recompute from current position and original cast vectors. Movement-stage
    -- candidates contain only damageX/Y and must never be interpreted as casts.
    for _, point in ipairs(points) do
        local cx,cy = point[1],point[2]
        local key = cx*100+cy
        if not seen[key] and unit.kPathFinder:IsInside(cx,cy) and unit:IsInCastRange(cx,cy) then
            seen[key] = true
            local grids, hash = unit:GetSkillDamageRangeByPos(martial,cx,cy,unit.iGridX,unit.iGridY,martial.eDepartEnum)
            local hasTarget = false
            for _, grid in ipairs(grids) do
                if grid[3] and unit.kPathFinder:IsTargetGrid(grid[1],grid[2],martial:GetTargetType(),unit.iUnitIndex,unit.iCamp,martial) then hasTarget = true; break end
            end
            if hasTarget then
                local data = {skillPosX=cx,skillPosY=cy,damageX=x,damageY=y}
                if cx == x and cy == y then return true,data end
                if hash[x*100+y] then
                    local ax,ay = _mjh_direction(cx,cy,unit.iGridX,unit.iGridY,unit.iFace)
                    local value = (ax == fx and ay == fy and 0 or 10000) + (cx-x)^2 + (cy-y)^2
                    if not score or value < score then best,score = data,value end
                end
            end
        end
    end
    return best ~= nil,best
end
'''

INDICATOR = '''    -- MJH actor area V2.0.13 BEGIN
    local area = _mjh_area(self,kMartialData)
    if area then
        local ux,uy = iUnitPosX or self.iGridX or 0,iUnitPosY or self.iGridY or 0
        local fx,fy = _mjh_direction(iCastPosX or ux,iCastPosY or uy,ux,uy,self.iFace)
        if #area.positions == 135 then fx,fy = 1,0 end
        local grids,hash = {},{}
        for _, offset in ipairs(area.positions) do
            local x = ux + offset[1]*fx - offset[2]*fy
            local y = uy + offset[1]*fy + offset[2]*fx
            if self.kPathFinder:IsInside(x,y) then grids[#grids+1] = {x,y,true}; hash[x*100+y] = true end
        end
        return grids,hash
    end
    -- MJH actor area V2.0.13 END
'''

PICK = '''    -- MJH actor pick V2.0.13 BEGIN
    if UnitMgr:GetInstance():GetChooseState() == OPT_STATE.CHOOSE_SKILL and _mjh_area(self,self.akMartialData[self.iCurChooseSkillIndex]) then return _mjh_cast(self,x,y) end
    -- MJH actor pick V2.0.13 END
'''

PREVIEW = '''    -- MJH actor preview V2.0.13 BEGIN
    local namedMartial = self.akMartialData[self.iCurChooseSkillIndex]
    if _mjh_area(self,namedMartial) then
        local ok,data = _mjh_cast(self,x,y)
        local grids = {}
        if ok then
            grids = self:GetSkillDamageRangeByPos(namedMartial,data.skillPosX,data.skillPosY,self.iGridX,self.iGridY,namedMartial.eDepartEnum)
        elseif self:IsInCastRange(x,y) then
            grids = self:GetSkillDamageRangeByPos(namedMartial,x,y,self.iGridX,self.iGridY,namedMartial.eDepartEnum)
        end
        LogicMain:GetInstance():ShowSkillDamageRangeGrid(grids)
        return
    end
    -- MJH actor preview V2.0.13 END
'''
