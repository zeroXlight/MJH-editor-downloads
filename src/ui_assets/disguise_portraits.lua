-- MJH_DISGUISE_PORTRAIT_LOADER_BEGIN
-- Only bundled mobile mask portraits use this loader. Native/mod images delegate unchanged.
local function _mjh_disguise_portrait(name)
    if type(name)~="string" or not (string.match(name,"^#role_editor/disguise_cg_[0-9a-f]+%.png$")
        or string.match(name,"^#role_editor/disguise_[0-9a-f]+%.png$")
        or string.match(name,"^#role_editor/head_mobile_[0-9a-f]+%.png$")) then return false,nil end
    local path="ModProject/GameProject/Mod_MJH/Source/Other/"..string.sub(name,2)
    local manager=WorkShopResourceDataManager:GetInstance()
    local cache=manager.akResourceData
    if cache and cache[path] then return true,cache[path] end
    local U=CS.UnityEngine
    local texture
    local ok,sprite=pcall(function()
        if not DRCSRef.File.Exists(path) then return nil end
        -- The APK source textures have a single mip level. Keep that property when
        -- loading PNGs so quality settings cannot select a smaller generated mip.
        texture=U.Texture2D(2,2,U.TextureFormat.RGBA32,false)
        if not U.ImageConversion.LoadImage(texture,DRCSRef.File.ReadAllBytes(path)) then return nil end
        texture.name=name;texture.filterMode=U.FilterMode.Bilinear;texture.wrapMode=U.TextureWrapMode.Clamp
        return U.Sprite.Create(texture,U.Rect(0,0,texture.width,texture.height),U.Vector2(0.5,0.5))
    end)
    if not ok or not sprite then
        if texture then U.Object.Destroy(texture) end
        DRCSRef.LogError("Mobile disguise portrait failed: "..path..(ok and "" or (" / "..tostring(sprite))))
        return true,nil
    end
    if cache then cache[path]=sprite end
    return true,sprite
end
local _mjh_disguise_get_sprite=GetSprite
function GetSprite(name,bLocal)
    local handled,sprite=_mjh_disguise_portrait(name)
    if handled then return sprite end
    return _mjh_disguise_get_sprite(name,bLocal)
end
local _mjh_disguise_get_sprite_async=GetSpriteAsync
function GetSpriteAsync(path,component,onLoad)
    local handled,sprite=_mjh_disguise_portrait(path)
    if not handled then return _mjh_disguise_get_sprite_async(path,component,onLoad) end
    if IsValidObj(component) then
        component.sprite=sprite
        if sprite and onLoad then onLoad() end
    end
end
-- MJH_DISGUISE_PORTRAIT_LOADER_END
