-- Keep the native mobile arrangement; add its missing scrollable trait panel.
local U=CS.UnityEngine
local UI=CS.UnityEngine.UI
local function rect(go,x,y,w,h)
    local r=go:GetComponent(typeof(U.RectTransform))
    r.anchorMin=DRCSRef.Vec2(.5,.5);r.anchorMax=DRCSRef.Vec2(.5,.5)
    r.pivot=DRCSRef.Vec2(.5,.5);r.anchoredPosition=DRCSRef.Vec2(x,y)
    r.sizeDelta=DRCSRef.Vec2(w,h)
    return r
end
local function child(name,parent)
    local go=U.GameObject(name,typeof(U.RectTransform))
    go.layer=parent.layer;go.transform:SetParent(parent.transform,false)
    return go
end
local layoutInit=PetCardsUpgradeUI.Init
function PetCardsUpgradeUI:Init(...)
    layoutInit(self,...)
    if self.mjhPetScroll then return end
    local view=child('MJHPetTraitScroll',self.objGradeInfoPanal)
    rect(view,2.4,19.045,684.8,173.31)
    local image=view:AddComponent(typeof(UI.Image))
    image.color=U.Color(1,1,1,.001);image.raycastTarget=true
    local viewport=child('Viewport',view)
    local vr=rect(viewport,0,0,0,0)
    vr.anchorMin=DRCSRef.Vec2(0,0);vr.anchorMax=DRCSRef.Vec2(1,1)
    viewport:AddComponent(typeof(UI.RectMask2D))
    local content=self:FindChild(self.objGradeInfoPanal,'GradeList')
    content.transform:SetParent(viewport.transform,false)
    local cr=rect(content,2,0,680,0)
    cr.anchorMin=DRCSRef.Vec2(0,1);cr.anchorMax=DRCSRef.Vec2(0,1)
    cr.pivot=DRCSRef.Vec2(0,1)
    local group=content:GetComponent(typeof(UI.VerticalLayoutGroup))
    group.spacing=8;group.childControlWidth=true;group.childControlHeight=true
    group.childForceExpandWidth=true;group.childForceExpandHeight=false
    group.childAlignment=U.TextAnchor.UpperLeft
    local fit=content:GetComponent(typeof(UI.ContentSizeFitter)) or content:AddComponent(typeof(UI.ContentSizeFitter))
    fit.horizontalFit=UI.ContentSizeFitter.FitMode.Unconstrained
    fit.verticalFit=UI.ContentSizeFitter.FitMode.PreferredSize
    local scroll=view:AddComponent(typeof(UI.ScrollRect))
    scroll.viewport=vr;scroll.content=cr;scroll.horizontal=false;scroll.vertical=true
    scroll.movementType=UI.ScrollRect.MovementType.Clamped;scroll.scrollSensitivity=30
    self.mjhPetScroll=scroll;self.mjhPetTraitContent=cr
    local balance=self.ComBtn_GradeUpScrollBar_text
    balance.transform:SetParent(self.objGradeInfoPanal.transform,false)
    rect(balance.gameObject,0,-82,650,28)
    balance.fontSize=22;balance.alignment=U.TextAnchor.MiddleCenter
    balance.color=U.Color(.24,.24,.24,1)
    local outline=balance:GetComponent('OutlineEx');if outline then outline.enabled=false end
    local title=self.comText_BaseInfoName
    title.resizeTextForBestFit=true;title.resizeTextMinSize=18;title.resizeTextMaxSize=28
end
local layoutLine=PetCardsUpgradeUI.RefreashGradeInfoPerLine
function PetCardsUpgradeUI:RefreashGradeInfoPerLine(obj,info)
    layoutLine(self,obj,info)
    if not obj then return end
    local label=self:FindChildComponent(obj,'Text_base','Text')
    local show=info and info.basedesc and info.basedesc~=''
    obj:SetActive(show and true or false)
    if not show then return end
    label.horizontalOverflow=U.HorizontalWrapMode.Wrap
    -- Keep the final numeric gain together when a long condition needs two lines.
    local suffix=label.text:match('([%+%-][%d%.%%]+)$')
    if suffix and label.preferredWidth>415 then
        label.text=label.text:sub(1,#label.text-#suffix)..'\n'..suffix
    end
    label.verticalOverflow=U.VerticalWrapMode.Overflow
    local lr=label.rectTransform
    lr.sizeDelta=DRCSRef.Vec2(415,120)
    local height=math.max(44,label.preferredHeight+16)
    lr.sizeDelta=DRCSRef.Vec2(415,height)
    local element=obj:GetComponent(typeof(UI.LayoutElement)) or obj:AddComponent(typeof(UI.LayoutElement))
    element.minHeight=height;element.preferredHeight=height;element.flexibleHeight=0
    self:FindChild(obj,'img_add').transform.localPosition=DRCSRef.Vec3(125,0,0)
    self:FindChild(obj,'img_lock').transform.localPosition=DRCSRef.Vec3(180,0,0)
    local nextText=self:FindChildComponent(obj,'Text_next','Text')
    nextText.rectTransform.anchoredPosition=DRCSRef.Vec2(-12,0)
    nextText.rectTransform.sizeDelta=DRCSRef.Vec2(120,30)
end
local layoutInfo=PetCardsUpgradeUI.RefreashGradeInfo
function PetCardsUpgradeUI:RefreashGradeInfo(...)
    layoutInfo(self,...)
    if self.mjhPetTraitContent then
        UI.LayoutRebuilder.ForceRebuildLayoutImmediate(self.mjhPetTraitContent)
        self.mjhPetScroll.verticalNormalizedPosition=1
    end
end
