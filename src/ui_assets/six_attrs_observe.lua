-- MJH_SIX_ATTACK_HELPER
local mjhOriginalObserveAttr=ObserveUI.RefreshAttr
function ObserveUI:RefreshAttr(role,db)
    mjhOriginalObserveAttr(self,role,db)
    if IsRogueLikeScript() or not role or
        (role.roleType~=ROLE_TYPE.INST_ROLE and role.roleType~=ROLE_TYPE.BATTLE_ROLE) then return end
    local attack=mjhSixAttack(role)
    for i,info in ipairs(self.l_roleDefenseAttacakAttr or {}) do
        if info.attrName=='MartialATK' then
            local row=self.objAttrBox3Item[i]
            row[1].text=attack.key;row[2].text=tostring(math.floor(attack.value+0.5))
        end
    end
end
