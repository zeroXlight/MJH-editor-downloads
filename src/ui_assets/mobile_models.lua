-- MJH_MOBILE_MODELS_V261
local _mjh_mobile_cache = {}
local _mjh_mobile_stash = nil
local function _mjh_mobile_key(path)
    if type(path) ~= "string" then return nil end
    return string.match(path, "mjh_mobile_([0-9a-f]+)")
end
local function _mjh_mobile_prepare(component)
    component.initialSkinName = ""
    local flags = CS.System.Enum.Parse(typeof(CS.System.Reflection.BindingFlags), "Instance, Public, NonPublic")
    -- The public AnimationName setter dereferences AnimationState before Awake.
    local field = component:GetType():GetField("_animationName", flags)
    if field then field:SetValue(component, "") end
    local start = component:GetType():GetField("startingAnimation", flags)
    if start then start:SetValue(component, "") end
end
local function _mjh_mobile_load(path, requestedType)
    local key = _mjh_mobile_key(path)
    if not key or #key ~= 32 then error("Invalid mobile model key") end
    local cached = _mjh_mobile_cache[key]
    if not cached then
        local dir = "mod/editor_mobile_models/" .. key .. "/"
        local config = assert(load(DRCSRef.File.ReadAllText(dir .. "binding.lua")))()
        local U = CS.UnityEngine
        local S = CS.Spine
        local native = LoadPrefab("Actor/" .. config.base .. "/" .. config.base .. "_prefab", _ClassTypeof.GameObject)
        if not native then error("Mobile model carrier missing: " .. config.base) end
        if not _mjh_mobile_stash then
            _mjh_mobile_stash = U.GameObject("MJH_MobileModelTemplates")
            _mjh_mobile_stash:SetActive(false)
            U.Object.DontDestroyOnLoad(_mjh_mobile_stash)
        end
        -- Keep templates inactive in the hierarchy, but activeSelf true for instances.
        local prefab = U.Object.Instantiate(native, _mjh_mobile_stash.transform, false)
        prefab.name = "mjh_mobile_" .. key
        local component = prefab:GetComponent(typeof(S.Unity.SkeletonAnimation))
        if not component or not component.skeletonDataAsset or component.skeletonDataAsset.atlasAssets.Length == 0 then
            U.Object.Destroy(prefab)
            -- Some native prefab shells intentionally have no assigned skeleton.
            local fallback = LoadPrefab("Actor/role_zhouguniang/role_zhouguniang_prefab", _ClassTypeof.GameObject)
            if not fallback then error("Mobile model component template unavailable") end
            prefab = U.Object.Instantiate(fallback, _mjh_mobile_stash.transform, false)
            prefab.name = "mjh_mobile_" .. key
            component = prefab:GetComponent(typeof(S.Unity.SkeletonAnimation))
        end
        if not component then error("Mobile model carrier has no SkeletonAnimation") end
        local texture = U.Texture2D(2, 2, U.TextureFormat.RGBA32, false)
        if not U.ImageConversion.LoadImage(texture, DRCSRef.File.ReadAllBytes(dir .. "texture.png")) then error("Mobile texture invalid") end
        texture.name = string.gsub(config.page, "%.png$", "")
        texture.filterMode = U.FilterMode.Bilinear
        texture.wrapMode = U.TextureWrapMode.Clamp
        local material = U.Material(component.skeletonDataAsset.atlasAssets[0].PrimaryMaterial)
        material.mainTexture = texture
        -- Android ETC textures use straight alpha after decoding to PNG.
        material:EnableKeyword("_STRAIGHT_ALPHA_INPUT")
        material:SetFloat("_StraightAlphaInput", 1)
        local textures = {texture}
        local atlas = DRCSRef.SpineAtlasAsset.CreateRuntimeInstance(U.TextAsset(DRCSRef.File.ReadAllText(dir .. "model.atlas")), textures, material, true)
        local attachmentLoader = S.AtlasAttachmentLoader(atlas:GetAtlas())
        local parser = S.SkeletonBinary(attachmentLoader)
        parser.Scale = config.scale or component.skeletonDataAsset.scale
        local stream = CS.System.IO.MemoryStream(DRCSRef.File.ReadAllBytes(dir .. "model.skel"))
        local data = parser:ReadSkeletonData(stream)
        stream:Dispose()
        local asset = U.ScriptableObject.CreateInstance(typeof(S.Unity.SkeletonDataAsset))
        asset.name = prefab.name .. "_SkeletonData"
        asset.atlasAssets = {atlas}
        asset.scale = parser.Scale
        asset.defaultMix = component.skeletonDataAsset.defaultMix
        -- GetSkeletonData checks this reference before its cached data.
        asset.skeletonJSON = U.TextAsset("{}")
        -- This runtime exposes no public setter; only the cached data is replaced.
        local flags = CS.System.Enum.Parse(typeof(CS.System.Reflection.BindingFlags), "Instance, NonPublic")
        local field = asset:GetType():GetField("skeletonData", flags)
        if not field then error("Unsupported Spine runtime: skeletonData field missing") end
        field:SetValue(asset, data)
        local stateField = asset:GetType():GetField("stateData", flags)
        if not stateField then error("Unsupported Spine runtime: stateData field missing") end
        stateField:SetValue(asset, S.AnimationStateData(data))
        asset:FillStateData()
        component.skeletonDataAsset = asset
        _mjh_mobile_prepare(component)
        component:Initialize(true)
        prefab:SetActive(true)
        cached = {prefab=prefab, asset=asset, texture=texture, atlas=atlas, material=material}
        _mjh_mobile_cache[key] = cached
    end
    if requestedType == _ClassTypeof.Texture or requestedType == typeof(CS.UnityEngine.Texture2D) or string.match(path, "_texture$") then return cached.texture end
    if requestedType == _ClassTypeof.SkeletonDataAsset or string.find(string.lower(path), "_skeletondata", 1, true) then return cached.asset end
    return cached.prefab
end
