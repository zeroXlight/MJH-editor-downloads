-- MJH_DISGUISE_UI_V2212
disguisetype_convert[11]="更改模型"
disguisetype_convert[12]="更改立绘"
table.insert(navtype_sort,11);table.insert(navtype_sort,12)

function MJHDisguiseMatches(option,query)
    for token in string.gmatch(string.lower(query or ""),"%S+") do
        local prefix,number=string.match(token,"^([mp])(%d+)$")
        local digits=string.match(token,"^%d+$")
        if prefix or digits then
            local code=string.lower(option.query_id or "")
            local found=tonumber(string.sub(code,2))==tonumber(number or digits) and (not prefix or string.sub(code,1,1)==prefix)
            if not prefix then
                for _,field in ipairs({"aliases","role_ids"}) do
                    for _,id in ipairs(option[field] or {}) do if tonumber(id)==tonumber(digits) then found=true end end
                end
            end
            if not found then return false end
        elseif not string.find(string.lower(option.search or option.label or ""),token,1,true) then return false end
    end
    return true
end

local function _mjh_text(parent,name,font)
    local U=CS.UnityEngine
    local go=U.GameObject(name,typeof(U.RectTransform));go.transform:SetParent(parent,false)
    local text=go:AddComponent(typeof(U.UI.Text));text.font=font;text.fontSize=20;text.color=U.Color(0.2,0.16,0.12,1)
    text.alignment=U.TextAnchor.MiddleLeft;text.supportRichText=false
    local rect=go.transform;rect.anchorMin=U.Vector2(0,0);rect.anchorMax=U.Vector2(1,1);rect.offsetMin=U.Vector2(12,0);rect.offsetMax=U.Vector2(-12,0)
    return text
end
local _mjh_init=DisguiseUI.Init
function DisguiseUI:Init()
    _mjh_init(self)
    local U=CS.UnityEngine
    local go=U.GameObject("MJH_DisguiseSearch",typeof(U.RectTransform));go.transform:SetParent(self.objSC_disguise.transform,false)
    local rect=go.transform;rect.anchorMin=U.Vector2(0,1);rect.anchorMax=U.Vector2(1,1);rect.pivot=U.Vector2(0.5,1)
    rect.sizeDelta=U.Vector2(-215,44);rect.anchoredPosition=U.Vector2(-105,0)
    local bg=go:AddComponent(typeof(U.UI.Image));bg.color=U.Color(0.97,0.94,0.86,1)
    local input=go:AddComponent(typeof(U.UI.InputField));input.targetGraphic=bg;input.characterLimit=120
    input.textComponent=_mjh_text(rect,"Query",self.comRoleName_Text.font)
    local hint=_mjh_text(rect,"Placeholder",self.comRoleName_Text.font);hint.text="本分类：编号 / 人物 / 资源名";hint.color=U.Color(0.5,0.46,0.4,1)
    input.placeholder=hint
    local status=_mjh_text(self.objSC_disguise.transform,"MJH_DisguiseResults",self.comRoleName_Text.font)
    local statusRect=status.transform;statusRect.anchorMin=U.Vector2(1,1);statusRect.anchorMax=U.Vector2(1,1);statusRect.pivot=U.Vector2(1,1)
    statusRect.sizeDelta=U.Vector2(205,44);statusRect.anchoredPosition=U.Vector2(-4,0);status.alignment=U.TextAnchor.MiddleRight;status.fontSize=18
    self._mjh_search=go;self._mjh_input=input;self._mjh_status=status
    self._mjh_viewport=self:FindChild(self.objSC_disguise,"Viewport").transform
    self._mjh_viewport_top=self._mjh_viewport.offsetMax
    input.onValueChanged:AddListener(function(value)
        if self._mjh_search_muted then return end
        self._mjh_queries=self._mjh_queries or {};self._mjh_queries[self._mjh_kind or 11]=value
        self._mjh_disguise_page=1;self:ChooseNav(self._mjh_kind or 11)
    end)
    go:SetActive(false);status.gameObject:SetActive(false)
end
local _mjh_refresh=DisguiseUI.RefreshUI
function DisguiseUI:RefreshUI(roleID)
    local tab=TableDataManager:GetInstance():GetTable("DisguiseItem")
    for id,row in pairs(tab) do if row._mjh_option then tab[id]=nil end end
    for index,option in ipairs(MJHDisguiseOptions()) do
        local kind=option.kind=="model" and 11 or 12
        tab[1900000000+index]={BaseID=1900000000+index,DisguiseTypeList={kind},Lock=0,_mjh_option=option}
    end
    self._mjh_disguise_page=1;self._mjh_queries={};self._mjh_kind=nil
    _mjh_refresh(self,roleID)
    table.sort(self.disguiseTypeMap[11] or {});table.sort(self.disguiseTypeMap[12] or {})
end
local _mjh_choose_nav=DisguiseUI.ChooseNav
function DisguiseUI:ChooseNav(kind)
    local custom=kind==11 or kind==12
    if self._mjh_search then
        self._mjh_search:SetActive(custom);self._mjh_status.gameObject:SetActive(custom)
        local top=self._mjh_viewport_top
        self._mjh_viewport.offsetMax=CS.UnityEngine.Vector2(top.x,top.y-(custom and 54 or 0))
    end
    if not custom then self._mjh_kind=nil;return _mjh_choose_nav(self,kind) end
    if self._mjh_kind~=kind then self._mjh_disguise_page=1 end
    self._mjh_kind=kind
    local query=(self._mjh_queries or {})[kind] or ""
    if self._mjh_input and self._mjh_input.text~=query then self._mjh_search_muted=true;self._mjh_input.text=query;self._mjh_search_muted=false end
    local ids={}
    table.sort(self.disguiseTypeMap[kind] or {})
    for _,id in ipairs(self.disguiseTypeMap[kind] or {}) do
        local entry=TableDataManager:GetInstance():GetTableData("DisguiseItem",id)
        if MJHDisguiseMatches(entry._mjh_option,query) then table.insert(ids,id) end
    end
    local size=60;local pages=math.max(1,math.ceil(#ids/size))
    local page=math.max(1,math.min(self._mjh_disguise_page or 1,pages));self._mjh_disguise_page=page
    self._mjh_result_count=#ids
    self.comDetailText.text=disguisetype_convert[kind].." · "..page.." / "..pages
    if self._mjh_status then self._mjh_status.text=#ids.." 项 · "..page.." / "..pages.." 页" end
    local entries={}
    if page>1 then table.insert(entries,{_mjh_page=page-1,_mjh_kind=kind,_mjh_label="〈 上一页"}) end
    for i=(page-1)*size+1,math.min(page*size,#ids) do table.insert(entries,TableDataManager:GetInstance():GetTableData("DisguiseItem",ids[i])) end
    if page<pages then table.insert(entries,{_mjh_page=page+1,_mjh_kind=kind,_mjh_label="下一页 〉"}) end
    for i,entry in ipairs(entries) do
        if not self.blockObjsList[i] then self.blockObjsList[i]=CloneObj(self.objDisguise_template,self.objDisguise_content) end
        local obj=self.blockObjsList[i];obj:SetActive(true);self:UpdateDisguiseBlock(obj,entry)
    end
    for i=#entries+1,#self.blockObjsList do self.blockObjsList[i]:SetActive(false) end
    self.objDisguise_content.transform.localPosition=DRCSRef.Vec3(0,0,0)
end
local _mjh_update=DisguiseUI.UpdateDisguiseBlock
function DisguiseUI:UpdateDisguiseBlock(obj,entry)
    if not entry or (not entry._mjh_option and not entry._mjh_page) then return _mjh_update(self,obj,entry) end
    local option=entry._mjh_option
    local image=self:FindChildComponent(obj,"mask/img_drawing","Image")
    local label=self:FindChild(obj,"mask/label_name");label:SetActive(true)
    self:FindChildComponent(label,"Text","Text").text=option and (option.query_id.." · "..option.label) or entry._mjh_label
    image.sprite=option and GetSprite(option.icon) or nil;image.enabled=option~=nil
    local button=self:FindChildComponent(obj,"img_bg","Button");self:RemoveButtonClickListener(button)
    self:AddButtonClickListener(button,function()
        if entry._mjh_page then self._mjh_disguise_page=entry._mjh_page;self:ChooseNav(entry._mjh_kind) else self:ShowDetail(entry.BaseID) end
    end)
end
local _mjh_detail=DisguiseUI.ShowDetail
function DisguiseUI:ShowDetail(id)
    local entry=TableDataManager:GetInstance():GetTableData("DisguiseItem",id)
    if not entry or not entry._mjh_option then return _mjh_detail(self,id) end
    self.selectDisguiseID=id;self.objDetail:SetActive(true)
    local option=entry._mjh_option
    local headNote=option.kind=="portrait" and (option.head and "（同步对应头像）" or "（保留原头像）") or ""
    self.comDetailText.text=option.query_id.." · "..option.label..headNote
    self.comDetailDrawing_Image.sprite=GetSprite(option.drawing or option.icon)
end
local _mjh_send=SendClickRoleDisguise
SendClickRoleDisguise=function(roleID,id,use)
    local entry=id and TableDataManager:GetInstance():GetTableData("DisguiseItem",id)
    if use and entry and entry._mjh_option then
        local ok,result=pcall(MJHDisguiseChoose,roleID,entry._mjh_option)
        if not ok then SystemUICall:GetInstance():Toast(tostring(result));return end
        id=result
    end
    return _mjh_send(roleID,id,use)
end
-- MJH_DISGUISE_UI_END
