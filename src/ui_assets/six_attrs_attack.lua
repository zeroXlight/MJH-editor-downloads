local mjhAttackNames={[22]='剑法攻击',[23]='刀法攻击',[24]='拳掌攻击',[25]='腿法攻击',
    [26]='奇门攻击',[27]='暗器攻击',[28]='医术攻击',[29]='内功攻击'}
local mjhWeaponAttacks={[9]=23,[10]=22,[11]=24,[12]=26,[13]=26,[18]=27,[19]=28,[27]=25,[28]=27,[29]=29}
local function mjhSixAttack(role)
    local owner=role.GetInstRole and role:GetInstRole() or role
    local item=nil
    if owner and owner.akEquipItem then
        local uid=owner.akEquipItem[REI_WEAPON]
        if uid and uid~=0 then item=ItemDataManager:GetInstance():GetItemTypeData(uid) end
    elseif role.GetEquipItemInfos then
        local info=(role:GetEquipItemInfos() or {})[REI_WEAPON]
        if info and info.iTypeID then item=GetTableData('Item',info.iTypeID) end
    end
    local attr=item and mjhWeaponAttacks[item.ItemType] or 24
    attr=attr or 24
    local function read(a) return tonumber(role:GetAttr(a,true)) or 0 end
    if item and item.ItemType==28 and read(28)>read(27) then attr=28 end
    return {enum=attr,key=mjhAttackNames[attr],value=read(attr)+read(99)}
end
