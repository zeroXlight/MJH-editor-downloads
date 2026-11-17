"""Repair the weapon/HUD initialization failures preceding character and dialogue refresh."""
import re

WEAPON_BEGIN='-- MJH_WEAPON_INITIALIZATION_V236'
WEAPON='''function WeaponUI:UpdateBoneFollower()
    -- MJH_WEAPON_INITIALIZATION_V236
    local boneFollower = self.objWeaponNode:GetComponent("BoneFollower")
    self.sortingGroup = self.objWeaponNode:GetComponent("SortingGroup")
    if self.sortingGroup == nil then
        self.sortingGroup = self.objWeaponNode:AddComponent(typeof(DRCSRef.SortingGroup))
    end
    self.boneName = self.boneName or DEFAULT_SPINE_WEAPON_BONE
    -- Pooled views can be inactive, or have a new renderer. Never use the old owner.
    local renderer = self.objSpine.transform:GetComponent("SkeletonRenderer")
    self.skeletonRenderer = renderer
    if renderer and not renderer.skeleton and renderer.skeletonDataAsset then
        renderer:Initialize(false)
    end
    local skeleton = renderer and renderer.skeleton
    local bone = skeleton and skeleton:FindBone(self.boneName)
    if boneFollower then
        boneFollower.enabled = false
        boneFollower.skeletonRenderer = renderer
        if bone then
            boneFollower.followLocalScale = true
            boneFollower:SetBone(self.boneName)
            boneFollower.enabled = true
        end
    end
    -- A 3D view may have an unused, empty Spine node. Hide its unbound 2D weapon.
    self.objWeaponNode.gameObject:SetActive(bone ~= nil)
    local Layout = -1
    if self.boneName == DEFAULT_SPINE_WEAPON_BONE then Layout = 0 end
    if self.sortingGroup then self.sortingGroup.sortingOrder = Layout end
end'''

HUD_HELPER='''-- MJH_HUD_CANVAS_V236
local function _mjh_hud_canvas(uiWindow)
    if not uiWindow or not uiWindow._gameObject then return nil end
    local group = uiWindow._gameObject:GetComponent("CanvasGroup")
    if not group then
        group = uiWindow._gameObject:AddComponent(typeof(CS.UnityEngine.CanvasGroup))
    end
    return group
end
'''

def patch_weapon(text):
    pattern=r'function WeaponUI:UpdateBoneFollower\(\).*?\nend'
    matches=list(re.finditer(pattern,text,re.S))
    if len(matches)!=1:raise ValueError('武器骨骼绑定入口不兼容，未写入')
    m=matches[0];return text[:m.start()]+WEAPON+text[m.end():]

def patch_hud(text):
    if '-- MJH_HUD_CANVAS_V236' in text:return text
    anchor='function HideAllHUD()'
    if text.count(anchor)!=1:raise ValueError('对话界面切换入口不兼容，未写入')
    for alpha in (0,1):
        old=f'uiWindow._gameObject:GetComponent("CanvasGroup").alpha = {alpha}'
        if text.count(old)!=1:raise ValueError('界面显隐组件入口不兼容，未写入')
        new=f'local group = _mjh_hud_canvas(uiWindow)\n                if group then group.alpha = {alpha} end'
        text=text.replace(old,new,1)
    return text.replace(anchor,HUD_HELPER+anchor,1)

def repair(data):
    from client_config import Assets
    for name,patch in [('WeaponUI.lua',patch_weapon),('Functions.lua',patch_hud)]:
        a=Assets(data);old=a.script(name);new=patch(old)
        if old!=new:data=a.replace_script(name,new)
    return data
