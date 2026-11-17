"""Initialize the collection list even when the prefab's first toggle is on."""
MARK='-- MJH_COLLECTION_READY_2310'
HELPER='''-- MJH_COLLECTION_READY_2310
local mjhCollectionInit = CollectionMartialUI.Init
local mjhCollectionEnable = CollectionMartialUI.OnEnable
local mjhCollectionSingle = CollectionMartialUI.OnRefSingleSkill
function CollectionMartialUI:Init(...)
    self.martialData = {}
    self.martialScreenData = {}
    mjhCollectionInit(self, ...)
    self._mjhCollectionReady = true
    -- An already-selected prefab toggle does not send onValueChanged.
    if not self.clickTypeData then
        self:OnClickTypeToggle(nil, "所有", true)
    end
    if self._mjhCollectionEnablePending and self._gameObject and self._gameObject.activeInHierarchy then
        self._mjhCollectionEnablePending = nil
        self:OnEnable()
    end
end
function CollectionMartialUI:OnEnable(...)
    if not self._mjhCollectionReady then
        self._mjhCollectionEnablePending = true
        return
    end
    self.collectionDataManager:GetMartialData(1, true)
    local category = DepartEnumType_Revert[self.clickTypeData or "所有"] or DepartEnumType.DET_All
    self:OnRefRightLeftSCList(category)
    self:RemoveEventListener('ONEVENT_MARTIALDATA_UPDATE')
    return mjhCollectionEnable(self, ...)
end
function CollectionMartialUI:OnRefSingleSkill(...)
    if not self._mjhCollectionReady then return end
    if not self.lvSCRightLeft or not self:GetClickMartialData() then
        self.clickSkillData = nil
        self:RefreshByFirstItem()
        return
    end
    return mjhCollectionSingle(self, ...)
end
'''
def patch(text):
    if MARK in text:return text
    import re
    anchor=re.search(r'return\s+CollectionMartialUI\s*;?\s*$',text)
    if not anchor or 'function CollectionMartialUI:Init()' not in text or 'function CollectionMartialUI:OnEnable()' not in text:
        raise ValueError('武学收藏初始化入口不兼容，未写入')
    return text[:anchor.start()]+HELPER+'\n'+text[anchor.start():]

def repair(data):
    from client_config import Assets
    a=Assets(data);replacements={}
    for name,fn in (('CollectionMartialUI.lua',patch),('CollectionDataManager.lua',patch_data)):
        before=a.script(name);after=fn(before)
        if after!=before:replacements[name]=after.encode('utf8')
    return a.replace_blobs(replacements) if replacements else data

def patch_data(text):
    import re
    mark='-- MJH_COLLECTION_MISSING_2310'
    if mark in text:return text
    old='if (martialData.Display == TBoolean.BOOL_YES) or (displayTable[martialData.BaseID]) then'
    if text.count(old)!=1:raise ValueError('武学收藏旧记录检查入口不兼容，未写入')
    new='''-- MJH_COLLECTION_MISSING_2310
        if not martialData then
            self.mjhMissingCollectionIDs = self.mjhMissingCollectionIDs or {}
            if not self.mjhMissingCollectionIDs[v.dwTypeID] then
                self.mjhMissingCollectionIDs[v.dwTypeID] = true
                CS.UnityEngine.Debug.LogWarning("MJH collection: martial config missing, retained unlock " .. tostring(v.dwTypeID))
            end
        end
        if martialData and ((martialData.Display == TBoolean.BOOL_YES) or displayTable[martialData.BaseID]) then'''
    text=text.replace(old,new)
    pattern=r'if not incompleteBookData then\s+return nil;\s+end'
    if len(re.findall(pattern,text))!=1:raise ValueError('武学收藏空列表入口不兼容，未写入')
    return re.sub(pattern,'if not incompleteBookData then\n        self.martialData = {}; self.allMartialData = {};\n        return nil;\n    end',text)
