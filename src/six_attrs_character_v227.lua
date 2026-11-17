-- MJH_SIX_ATTRS_227_BEGIN
-- Native fields 3..8 and SGC_CLICK_ROLE_ADDATTRPOINT are unchanged.
local mjhSixNames = {'力道','体质','精力','内劲','灵巧','悟性'}
local mjhSixDesc = {
 '拳掌、刀法攻击各 +10；连击值 +1.25',
 '生命随等级换算；防御 +0.9；回合回血 +2；反击值 +1',
 '真气 +50；防御 +2.1；回合回气 +2；破招值 +1',
 '内功、医术、奇门、暗器攻击各 +10；暴击值 +1.5',
 '腿法、剑法攻击各 +10；命中值 +1.5',
 '天赋值 +2；暴击抵抗值 +1.25；抗连击值 +1；暴伤值 +1.2'
}

function CharacterUI:MJHSixBuild()
    if self.mjhSix then return end
    local U = CS.UnityEngine
    local UI = CS.UnityEngine.UI
    local font = self.akPrimaryControlCom[1].textLabel.font
    local function box(parent,name,x,y,w,h,color)
        local go = U.GameObject(name,typeof(U.RectTransform))
        go.transform:SetParent(parent,false)
        local rt = go:GetComponent(typeof(U.RectTransform))
        rt.anchorMin=U.Vector2(0.5,0.5);rt.anchorMax=U.Vector2(0.5,0.5)
        rt.anchoredPosition=U.Vector2(x,y);rt.sizeDelta=U.Vector2(w,h)
        if color then go:AddComponent(typeof(UI.Image)).color=color end
        return go
    end
    local function text(parent,name,value,x,y,w,h,size)
        local go=box(parent,name,x,y,w,h)
        local t=go:AddComponent(typeof(UI.Text));t.font=font;t.fontSize=size or 19
        t.color=U.Color(1,0.96,0.86,1);t.alignment=U.TextAnchor.MiddleLeft
        t.raycastTarget=false;t.text=value
        return t
    end
    local function button(parent,label,x,y,w,fn)
        local go=box(parent,label,x,y,w,36,U.Color(0.35,0.22,0.12,1))
        local b=go:AddComponent(typeof(UI.Button));b.targetGraphic=go:GetComponent(typeof(UI.Image))
        text(go.transform,'Text',label,0,0,w-10,34,18).alignment=U.TextAnchor.MiddleCenter
        b.onClick:AddListener(fn);return b
    end
    local go=box(self._gameObject.transform,'MJHSixAttrs',0,0,4096,4096,U.Color(0,0,0,0.75))
    local panel=box(go.transform,'Panel',0,0,1110,760,U.Color(0.12,0.10,0.08,1))
    local s={go=go,values={},draft={0,0,0,0,0,0}}
    self.mjhSix=s
    text(panel.transform,'Title','六项属性与八系攻击',-305,334,440,42,28)
    s.points=text(panel.transform,'Points','',125,334,360,42,21)
    button(panel.transform,'关闭',486,334,85,function() go:SetActive(false) end)
    text(panel.transform,'Hint','先分配待加点数，再提交；减号只撤销本次尚未提交的分配。',0,280,1030,40,19)
    local function change(i,n)
        local role=RoleDataManager:GetInstance():GetRoleData(self.selectRole)
        if not role or s.role~=self.selectRole then return end
        local total=0;for j=1,6 do total=total+s.draft[j] end
        if n>0 then n=math.min(n,(role.uiRemainAttrPoint or 0)-total) end
        s.draft[i]=math.max(0,s.draft[i]+n);self:MJHSixRefresh()
    end
    for i=1,6 do
        local row=i;local y=220-(i-1)*58
        s.values[i]=text(panel.transform,'Attr'..i,'',-390,y,270,42,21)
        button(panel.transform,'−1',-245,y,48,function() change(row,-1) end)
        button(panel.transform,'+1',-189,y,48,function() change(row,1) end)
        button(panel.transform,'+10',-126,y,62,function() change(row,10) end)
        text(panel.transform,'Desc'..i,mjhSixDesc[i],220,y,610,46,17)
    end
    s.attacks=text(panel.transform,'Attacks','',0,-174,1030,74,20)
    s.status=text(panel.transform,'Status','',-10,-254,1010,60,18)
    button(panel.transform,'清空本次分配',-134,-326,200,function()
        s.draft={0,0,0,0,0,0};self:MJHSixRefresh()
    end)
    button(panel.transform,'提交加点',134,-326,200,function() self:MJHSixSubmit() end)
    go:SetActive(false)
end

function CharacterUI:MJHSixRefresh()
    local s=self.mjhSix
    if not s or not s.go.activeSelf then return end
    local role=RoleDataManager:GetInstance():GetRoleData(self.selectRole)
    if not role or not role.GetAttr then s.status.text='当前角色数据尚未就绪。';return end
    if s.role~=self.selectRole then s.role=self.selectRole;s.draft={0,0,0,0,0,0} end
    local total=0;for i=1,6 do total=total+s.draft[i] end
    s.points.text=string.format('剩余点数 %d　待分配 %d',role.uiRemainAttrPoint or 0,total)
    for i=1,6 do
        s.values[i].text=string.format('%s　%d  <color=#86D88B>+%d</color>',mjhSixNames[i],role:GetAttr(i+2) or 0,s.draft[i])
    end
    s.attacks.text=string.format('拳掌 %d　刀法 %d　剑法 %d　腿法 %d\n内功 %d　医术 %d　奇门 %d　暗器 %d',
        role:GetAttr(24) or 0,role:GetAttr(23) or 0,role:GetAttr(22) or 0,role:GetAttr(25) or 0,
        role:GetAttr(29) or 0,role:GetAttr(28) or 0,role:GetAttr(26) or 0,role:GetAttr(27) or 0)
    s.status.text='加成以原生结算、取整和难度上限为准。悟性的天赋值不等于待分配天赋点。\n已提交点数使用原生存档保存；恢复关闭后仍保留。'
end

function CharacterUI:MJHSixSubmit()
    local s=self.mjhSix
    local role=RoleDataManager:GetInstance():GetRoleData(self.selectRole)
    if not s or not role or s.role~=self.selectRole then return end
    local values={};local total=0
    for i=1,6 do
        local n=s.draft[i]
        if type(n)~='number' or n<0 or n~=math.floor(n) then return end
        values[i-1]=n;total=total+n
    end
    if total<=0 or total>(role.uiRemainAttrPoint or 0) then
        s.status.text='可用点数不足或尚未分配；请清空后重新分配。';return
    end
    local data=EncodeSendSeGC_ClickAddAttrPoint(self.selectRole,values)
    s.draft={0,0,0,0,0,0}
    NetGameCmdSend(SGC_CLICK_ROLE_ADDATTRPOINT,data:GetCurPos(),data)
    WaitDisplayMsg();self:MJHSixRefresh()
end

local mjhSixOriginalRefreshPoint=CharacterUI.RefreshPoint
function CharacterUI:RefreshPoint()
    mjhSixOriginalRefreshPoint(self)
    if IsRogueLikeScript() then return end
    local com=self.akPrimaryControlCom and self.akPrimaryControlCom[1]
    if not com then return end
    com.textLabel.text='六属性 / 八系攻击'
    local role=RoleDataManager:GetInstance():GetRoleData(self.selectRole)
    com.textValue.text='查看 / 加点 ('..tostring(role and role.uiRemainAttrPoint or 0)..')'
    if not self.mjhSixButton then
        local go=com.textLabel.transform.parent.gameObject
        local image=go:GetComponent(typeof(CS.UnityEngine.UI.Image))
        if not image then image=go:AddComponent(typeof(CS.UnityEngine.UI.Image));image.color=CS.UnityEngine.Color(0,0,0,0.01) end
        image.raycastTarget=true
        self.mjhSixButton=go:AddComponent(typeof(CS.UnityEngine.UI.Button))
        self.mjhSixButton.targetGraphic=image
        self.mjhSixButton.onClick:AddListener(function()
            self:MJHSixBuild();self.mjhSix.go:SetActive(true);self.mjhSix.go.transform:SetAsLastSibling();self:MJHSixRefresh()
        end)
    end
    self:MJHSixRefresh()
end
-- MJH_SIX_ATTRS_227_END
