-- MJH_SIX_ATTRS_227_BEGIN
-- MJH_MOBILE_CHARACTER_228: native mobile controls inside the character page.
local mjhMobileLayout={} -- populated from six_attrs_mobile_layout.lua
local mjhDisplayOrder={3,4,7,5,6,8}
local mjhSubmitOrder={3,4,5,6,7,8}
local mjhAttrNames={[3]='力道',[4]='体质',[5]='精力',[6]='内劲',[7]='灵巧',[8]='悟性'}

local function mjhRect(go,amin,amax,pivot,pos,size)
    local U=CS.UnityEngine
    local rt=go:GetComponent(typeof(U.RectTransform))
    rt.anchorMin=U.Vector2(amin.x,amin.y);rt.anchorMax=U.Vector2(amax.x,amax.y)
    rt.pivot=U.Vector2(pivot.x,pivot.y);rt.anchoredPosition=U.Vector2(pos.x,pos.y)
    rt.sizeDelta=U.Vector2(size.x,size.y);rt.localScale=U.Vector3(1,1,1)
    return rt
end
local function mjhDisableLayout(go)
    for _,kind in ipairs({CS.UnityEngine.UI.GridLayoutGroup,CS.UnityEngine.UI.HorizontalLayoutGroup,CS.UnityEngine.UI.VerticalLayoutGroup}) do
        local c=go:GetComponent(typeof(kind));if c then c.enabled=false end
    end
end

function CharacterUI:MJHMobileFit()
    local s=self.mjhMobileAttrs;if not s then return end
    local available=self.basic_box:GetComponent(typeof(CS.UnityEngine.RectTransform)).rect
    local scale=math.min(available.width/470,available.height/565)
    s.body.transform.localScale=CS.UnityEngine.Vector3(scale,scale,1)
end

function CharacterUI:MJHMobileBuild()
    if self.mjhMobileAttrs or IsRogueLikeScript() then return end
    local U=CS.UnityEngine;local UI=U.UI
    local body=U.GameObject('MJHMobileBasic',typeof(U.RectTransform))
    body.layer=self.basic_box.layer;body.transform:SetParent(self.basic_box.transform,false)
    mjhRect(body,{x=.5,y=.5},{x=.5,y=.5},{x=.5,y=.5},{x=0,y=0},{x=470,y=565})
    local s={body=body,rows={},draft={},role=self.selectRole}
    self.mjhMobileAttrs=s
    for _,name in ipairs({'Level','Life','Spirit','Basic','Master','Increase','Point'}) do
        local go=self:FindChild(self.basic_box,name)
        if go then go.transform:SetParent(body.transform,false) end
    end
    local basic=self:FindChild(body,'Basic');mjhDisableLayout(basic)
    for _,path in ipairs({'Basic/Primary','Basic/ActionTime','Basic/NeiLi','Basic/LiDao'}) do
        local go=self:FindChild(body,path);if go then go:SetActive(false) end
    end
    local master=self:FindChild(body,'Master');mjhDisableLayout(master)
    local attack=U.Object.Instantiate(self:FindChild(body,'Basic/defence'),basic.transform,false)
    attack.name='attack'
    s.attackLabel=self:FindChildComponent(attack,'Label',DRCSRef_Type.Text)
    s.attackValue=self:FindChildComponent(attack,'Number',DRCSRef_Type.Text)
    local primary=U.GameObject('Primary',typeof(U.RectTransform))
    primary.layer=self.basic_box.layer;primary.transform:SetParent(body.transform,false)
    local background=U.Object.Instantiate(self:FindChild(body,'Master/Back'),primary.transform,false)
    background.name='Back'
    local ignore=background:GetComponent(typeof(UI.LayoutElement)) or background:AddComponent(typeof(UI.LayoutElement))
    ignore.ignoreLayout=true
    mjhRect(background,{x=0,y=0},{x=1,y=1},{x=.5,y=.5},{x=0,y=0},{x=0,y=0})
    local grid=primary:AddComponent(typeof(UI.GridLayoutGroup))
    grid.cellSize=U.Vector2(225,50);grid.spacing=U.Vector2(5,0)
    grid.constraint=UI.GridLayoutGroup.Constraint.FixedColumnCount;grid.constraintCount=2
    grid.padding=CS.UnityEngine.RectOffset(8,0,0,0)
    for i,attr in ipairs(mjhDisplayOrder) do
        local row=LoadPrefabAndInit('Module/RoleAttr_Point',primary,true)
        if not row then error('缺少原生属性行预制体 Module/RoleAttr_Point') end
        row.name=tostring(i);row:SetActive(true)
        local label=self:FindChildComponent(row,'Label',DRCSRef_Type.Text)
        local value=self:FindChildComponent(row,'Value',DRCSRef_Type.Text)
        local plus=self:FindChildComponent(row,'Button_add',DRCSRef_Type.Button)
        local minus=self:FindChildComponent(row,'Button_minus',DRCSRef_Type.Button)
        s.rows[attr]={label=label,value=value,plus=plus,minus=minus}
        plus.onClick:RemoveAllListeners();minus.onClick:RemoveAllListeners()
        -- Original mobile hold-to-repeat interaction, with both pointer-up and
        -- click paths cancelling timers before any next role can receive them.
        local function bind(button,amount)
            self:AddEventTrigger(button.gameObject,l_DRCSRef.EventTriggerType.PointerDown,function()
                self:MJHMobileRelease();s.suppressClick=nil;self:MJHMobileChange(attr,amount)
                s.holdAttr=attr;s.holdAmount=amount;s.holdRole=self.selectRole
                s.timer=self:AddTimer(500,function() self:MJHMobileRepeat(attr,amount,150) end)
            end)
            self:AddEventTrigger(button.gameObject,l_DRCSRef.EventTriggerType.PointerUp,function()
                if s.timer then self:RemoveTimer(s.timer);s.timer=nil end
                -- Keep the pressed marker until onClick so a short press adds once.
                s.holdAttr=nil;s.holdAmount=nil;s.suppressClick=true
            end)
            self:AddEventTrigger(button.gameObject,l_DRCSRef.EventTriggerType.PointerExit,function()
                self:MJHMobileRelease()
            end)
            button.onClick:AddListener(function()
                if s.suppressClick then s.suppressClick=nil;self:MJHMobileRelease();return end
                self:MJHMobileRelease();self:MJHMobileChange(attr,amount)
            end)
        end
        bind(plus,1);bind(minus,-1)
    end
    local oldTips=self:FindChild(self.basic_box,'tips')
    if oldTips then oldTips:SetActive(false) end
    for _,r in ipairs(mjhMobileLayout) do
        local go=self:FindChild(body,r.path)
        if go then
            if r.path~='Primary' then mjhDisableLayout(go) end
            mjhRect(go,r.anchorMin,r.anchorMax,r.pivot,r.pos,r.size)
            if r.text then
                local t=go:GetComponent(typeof(UI.Text))
                if t then
                    t.fontSize=r.text.fontSize;t.alignment=r.text.alignment
                    t.color=U.Color(table.unpack(r.text.color));t.supportRichText=true
                end
            end
        end
    end
    -- The original mobile grid owns child row sizes and positions after layout.
    local point=self:FindChild(body,'Point');point:SetActive(true)
    s.points=self:FindChildComponent(point,'Value',DRCSRef_Type.Text)
    self:FindChildComponent(point,'Label',DRCSRef_Type.Text).text='剩余点数:'
    s.submit=self:FindChildComponent(point,'Button_add',DRCSRef_Type.Button)
    self:FindChildComponent(point,'Button_add/Text',DRCSRef_Type.Text).text='确定'
    s.submit.onClick:RemoveAllListeners();s.submit.onClick:AddListener(function() self:OnClick_Point_Submit() end)
    self:MJHMobileFit();self:MJHMobileRefresh()
end

function CharacterUI:MJHMobileRelease()
    local s=self.mjhMobileAttrs;if not s then return end
    if s.timer then self:RemoveTimer(s.timer);s.timer=nil end
    s.holdAttr=nil;s.holdAmount=nil;s.holdRole=nil
end
function CharacterUI:MJHMobileRepeat(attr,amount,delay)
    local s=self.mjhMobileAttrs
    if not s or s.holdRole~=self.selectRole or s.holdAttr~=attr or not self.basic_box.activeInHierarchy then self:MJHMobileRelease();return end
    if not self:MJHMobileChange(attr,amount) then self:MJHMobileRelease();return end
    s.timer=self:AddTimer(delay,function() self:MJHMobileRepeat(attr,amount,math.max(50,delay-5)) end)
end
function CharacterUI:MJHMobileChange(attr,amount)
    local s=self.mjhMobileAttrs
    local role=RoleDataManager:GetInstance():GetRoleData(self.selectRole)
    if not s or not role or s.role~=self.selectRole then return false end
    local used=0;for _,v in pairs(s.draft) do used=used+v end
    if amount>0 and used>=(role.uiRemainAttrPoint or 0) then return false end
    if amount<0 and (s.draft[attr] or 0)<=0 then return false end
    local limit=RoleDataManager:GetInstance():GetCurDiffValueLimit('AttrMaxValue') or 0
    if amount>0 and limit>0 and (role:GetAttr(attr) or 0)+(s.draft[attr] or 0)>=limit then return false end
    s.draft[attr]=(s.draft[attr] or 0)+amount
    self:MJHMobilePreviewConversions(role)
    self:RefreshAbility();self:MJHMobileRefresh();return true
end
function CharacterUI:MJHMobilePreviewConversions(role)
    local s=self.mjhMobileAttrs;self.array_attr_due_to_point={}
    local converted=RoleDataHelper.GetConvertAttr(s.draft,role.uiLevel or 1)
    for _,attrs in pairs(converted) do
        for attr,value in pairs(attrs) do self.array_attr_due_to_point[attr]=(self.array_attr_due_to_point[attr] or 0)+value end
    end
end
function CharacterUI:MJHMobileRefresh()
    local s=self.mjhMobileAttrs;if not s then return end
    local role=RoleDataManager:GetInstance():GetRoleData(self.selectRole)
    if not role or not role.GetAttr then return end
    if s.role~=self.selectRole then
        self:MJHMobileRelease();s.role=self.selectRole;s.draft={};self.array_attr_due_to_point={}
    end
    local used=0;for _,v in pairs(s.draft) do used=used+v end
    if used>(role.uiRemainAttrPoint or 0) then s.draft={};used=0;self.array_attr_due_to_point={} end
    self.uiRemainAttrPoint=(role.uiRemainAttrPoint or 0)-used
    s.points.text=tostring(self.uiRemainAttrPoint)
    local limit=RoleDataManager:GetInstance():GetCurDiffValueLimit('AttrMaxValue') or 0
    for attr,row in pairs(s.rows) do
        local value=role:GetAttr(attr) or 0;local n=s.draft[attr] or 0
        row.label.text=mjhAttrNames[attr]
        row.value.text=tostring(value)..(n>0 and ('<color=#228B22>+'..n..'</color>') or '')
        if limit>0 and value>=limit then row.value.text=row.value.text..'<color=#C53926>(限)</color>' end
        row.plus.gameObject:SetActive(self.uiRemainAttrPoint>0 and (limit<=0 or value+n<limit))
        row.minus.gameObject:SetActive(n>0)
    end
    s.submit.interactable=used>0
    local highest=RoleDataManager:GetInstance():GetMaxAttrack(role)
    s.attackLabel.text=highest.key;s.attackValue.text=tostring(highest.value)
    local preview=self.array_attr_due_to_point[highest.enum] or 0
    if preview>0 then s.attackValue.text=s.attackValue.text..'<color=#228B22>+'..math.floor(preview)..'</color>' end
    self:MJHMobileFit()
end
function CharacterUI:OnClick_Point_Submit()
    local s=self.mjhMobileAttrs
    local role=RoleDataManager:GetInstance():GetRoleData(self.selectRole)
    if not s or not role or s.role~=self.selectRole then return end
    local values={};local total=0
    for i,attr in ipairs(mjhSubmitOrder) do
        local n=s.draft[attr] or 0
        if type(n)~='number' or n<0 or n~=math.floor(n) then return end
        values[i-1]=n;total=total+n
    end
    if total<=0 or total>(role.uiRemainAttrPoint or 0) then return end
    self:MJHMobileRelease();s.suppressClick=nil
    local data=EncodeSendSeGC_ClickAddAttrPoint(self.selectRole,values)
    s.draft={};self.array_attr_due_to_point={}
    NetGameCmdSend(SGC_CLICK_ROLE_ADDATTRPOINT,data:GetCurPos(),data)
    WaitDisplayMsg();self:MJHMobileRefresh()
end

local mjhOriginalInitAbilityNode=CharacterUI.InitAbilityNode
function CharacterUI:InitAbilityNode()
    mjhOriginalInitAbilityNode(self)
    if not IsRogueLikeScript() then self:MJHMobileBuild() end
end
local mjhOriginalRefreshPoint=CharacterUI.RefreshPoint
function CharacterUI:RefreshPoint()
    if self.mjhMobileAttrs then self:MJHMobileRefresh() else mjhOriginalRefreshPoint(self) end
end
local mjhOriginalRefreshAbility=CharacterUI.RefreshAbility
function CharacterUI:RefreshAbility(...)
    local s=self.mjhMobileAttrs
    if s and s.role~=self.selectRole then
        self:MJHMobileRelease();s.role=self.selectRole;s.draft={};self.array_attr_due_to_point={}
    end
    mjhOriginalRefreshAbility(self,...)
    if self.mjhMobileAttrs then self:MJHMobileRefresh() end
end
local mjhOriginalDisable=CharacterUI.OnDisable
function CharacterUI:OnDisable(...)
    self:MJHMobileRelease()
    if self.mjhMobileAttrs then self.mjhMobileAttrs.draft={};self.mjhMobileAttrs.suppressClick=nil end
    self.array_attr_due_to_point={}
    if mjhOriginalDisable then return mjhOriginalDisable(self,...) end
end
-- MJH_SIX_ATTRS_227_END
