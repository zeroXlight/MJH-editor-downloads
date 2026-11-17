-- Native pet cultivation UI, funded by the native meridians balance.
local function exp()
    return tonumber(MeridiansDataManager:GetInstance():GetCurTotalExp()) or 0
end
local function cost(data)
    local level=data.grade or 0
    if level==0 then return 1000*2^((data.Petdata.Rank or 1)-1) end
    return math.ceil(1000*1.5^level)
end
local function cap(data)
    local chain=data.chain or data.Petdata.Chain
    return chain and #chain>0 and 5 or 10
end
local function unavailable(self,data)
    if (data.grade or 0)>=cap(data) then return '已达当前形态等级上限' end
    local root=self:GetCurPetCardData(nil,1)
    if data~=root and (data.grade or 0)==0 and (root.grade or 0)<5 then
        return '基础形态达到5级后，才能解锁进阶形态'
    end
    if exp()<cost(data) then return '经脉经验不足' end
end
local originalInit=PetCardsUpgradeUI.Init
function PetCardsUpgradeUI:Init(...)
    originalInit(self,...)
    local label=self:FindChildComponent(self.objBtnMyPets,'Text','Text')
    if label then label.text='培养总览' end
end
local originalInfo=PetCardsUpgradeUI.RefreashInfo
function PetCardsUpgradeUI:RefreashInfo(...)
    originalInfo(self,...)
    local data=self:GetCurPetCardData()
    self.str_unabletoast=unavailable(self,data)
    self.comText_BaseInfoName.text=GetLanguageByID(data.Petdata.NameID)..((data.grade or 0)>0 and (' +'..tostring(data.grade)) or '（未解锁）')
    self.ComBtn_GradeUp_text.text=(data.grade or 0)>=cap(data) and '已达上限'
        or ((data.grade or 0)==0 and '解锁形态' or '升级')
    self.ComBtn_GradeUpScrollBar_text.text=(data.grade or 0)>=cap(data)
        and ('经脉经验：'..tostring(exp())..'　请选择进阶形态')
        or ('经脉经验：'..tostring(exp())..'　'..((data.grade or 0)==0 and '解锁消耗：' or '升级消耗：')..string.format('%d',cost(data)))
    if (data.grade or 0)>=cap(data) and not (data.chain and #data.chain>0) then
        self.ComBtn_GradeUpScrollBar_text.text='经脉经验：'..tostring(exp())..'　已达形态等级上限'
    end
    if self.objBtn_GradeUp_extext then self.objBtn_GradeUp_extext:SetActive(false) end
    if self.objBtn_GradeUp_extext2 then self.objBtn_GradeUp_extext2:SetActive(false) end
    if self.objBtn_GradeUpScrollBar then
        self.objBtn_GradeUpScrollBar:SetActive(true)
        local bar=self.objBtn_GradeUpScrollBar:GetComponent('Scrollbar')
        if bar then bar.size=math.min(1,exp()/math.max(1,cost(data))) end
    end
    setUIGray(self.objBtn_GradeUp:GetComponent('Image'),self.str_unabletoast~=nil)
    self.mjhLastExp=exp()
end
local originalCard=PetCardsUpgradeUI.OnPetCardChanged
function PetCardsUpgradeUI:OnPetCardChanged(gameobj,index)
    originalCard(self,gameobj,index)
    local data=self:GetCurPetCardData(self.sort_list[index+1].cardlist_index,0)
    if not data then return end
    local value=self:FindChildComponent(gameobj.gameObject,'Info/Scrollbar/Value','Text')
    local progress=self:FindChildComponent(gameobj.gameObject,'Info/Scrollbar','Scrollbar')
    value.text=(data.grade or 0)>0 and (tostring(data.grade)..' / '..tostring(cap(data))) or '未解锁'
    progress.size=math.min(1,(data.grade or 0)/cap(data))
end
local originalHead=PetCardsUpgradeUI.OnHeadListChanged
function PetCardsUpgradeUI:OnHeadListChanged(obj,index)
    originalHead(self,obj,index)
    local data=self.datas_HeadList[index+1]
    if not data then return end
    local unlock=self:FindChild(obj.gameObject,'nameinfo/Unlock')
    local child=unlock.transform:Find('MJHCost')
    local go=child and child.gameObject
    if not go then
        go=CS.UnityEngine.GameObject('MJHCost',typeof(CS.UnityEngine.RectTransform))
        go.layer=unlock.layer;go.transform:SetParent(unlock.transform,false)
        local rect=go:GetComponent('RectTransform')
        rect.anchorMin=DRCSRef.Vec2(0,.5);rect.anchorMax=DRCSRef.Vec2(0,.5)
        rect.pivot=DRCSRef.Vec2(0,.5);rect.sizeDelta=DRCSRef.Vec2(160,22)
        rect.anchoredPosition=DRCSRef.Vec2(0,0)
    end
    local label=go:GetComponent('Text') or go:AddComponent(typeof(CS.UnityEngine.UI.Text))
    unlock:GetComponent('Image').enabled=false
    label.font=self:FindChildComponent(obj.gameObject,'nameinfo/Name','Text').font
    label.text=string.format('%d',cost(data))..'经脉'
    label.fontSize=16;label.color=CS.UnityEngine.Color(.3,.2,.1,1)
    label.horizontalOverflow=CS.UnityEngine.HorizontalWrapMode.Overflow
    label.alignment=CS.UnityEngine.TextAnchor.MiddleLeft
    label.raycastTarget=false
end
function PetCardsUpgradeUI:func_get_sort_num(data,indexroot)
    if (data.grade or 0)>=cap(data) then return 0 end
    return exp()>=cost(data) and 3 or 1
end
function PetCardsUpgradeUI:Onclick_Btn_GradeUp()
    local data=self:GetCurPetCardData()
    local reason=unavailable(self,data)
    if reason then SystemUICall:GetInstance():Toast(reason);return end
    local root=self:GetCurPetCardData(nil,1)
    self.old_grade=data.grade or 0;self.old_choseid=root.Petid
    if data~=root and (data.grade or 0)==0 then
        SendRequestRolePetCardOperate(RPCRT_PET_CARD,RPCOT_EVOLVE_PET_CARD,root.Petid,data.Petid)
    else
        SendRequestRolePetCardOperate(RPCRT_PET_CARD,RPCOT_LEVEL_UP_PET_CARD,data.Petid,0)
    end
end
local originalUpdate=PetCardsUpgradeUI.Update
function PetCardsUpgradeUI:Update(...)
    local manager=CardsUpgradeDataManager:GetInstance()
    if self.CardsMgr~=manager then
        self.CardsMgr=manager
        self:SetNeedUpdateData(true)
    end
    originalUpdate(self,...)
    if self.data_Chose_Index then
        local data=self:GetCurPetCardData()
        if data.Petid and (data.grade or 0)~=(self.CardsMgr:GetPetLevel(data.Petid) or 0) then
            self:SetNeedUpdateData(true)
        end
    end
    if self.mjhLastExp~=exp() and self.data_Chose_Index then self:RefreashInfo() end
end
function PetCardsUpgradeUI:ResetPetToBattle(petTypeID)
    local target=GetTableData('Pet',petTypeID)
    if not target then return end
    local root=target.cardItem1 or petTypeID
    local all=RoleDataManager:GetInstance():GetRoleEmbattleInfo() or {}
    for _,scheme in ipairs({EmBattleSchemeType.EBST_Help,EmBattleSchemeType.EBST_ArenaHelp}) do
        local formation=all[scheme] and all[scheme][1]
        local changed,used=false,false
        if formation then
            for index=#formation,1,-1 do
                local slot=formation[index]
                local pet=(slot.bPet or 0)>0 and GetTableData('Pet',slot.uiRoleID)
                if pet and (pet.cardItem1 or slot.uiRoleID)==root then
                    if used then table.remove(formation,index)
                    else slot.uiRoleID=petTypeID;used=true end
                    changed=true
                end
            end
            if changed then SendUpdateEmbattleData(formation,scheme,1) end
        end
    end
end
local function overview(scheme)
    local manager=CardsUpgradeDataManager:GetInstance()
    local all=RoleDataManager:GetInstance():GetRoleEmbattleInfo() or {}
    local formations=all[scheme] or {};local active=formations[1] or {}
    local totals,details,roots={},{},{}
    for _,slot in pairs(active) do
        if (slot.bPet or 0)>0 then
            local id=slot.uiRoleID
            local pet=GetTableData('Pet',id)
            local level=manager:GetPetLevel(id) or 0
            local root=pet and (pet.cardItem1 or id) or id
            if pet and level>0 and not roots[root] then
                roots[root]=true
                details[#details+1]=GetLanguageByID(pet.NameID)..' +'..tostring(level)
                for n=1,4 do
                    if (pet['Attr'..n] or 0)==1 and level>=(pet['Attr'..n..'Level'] or 0) then
                        local attr=pet['Attr'..n..'Value1']
                        local value=(pet['Attr'..n..'Init'] or 0)+(pet['Attr'..n..'Grow'] or 0)*(level-(pet['Attr'..n..'Level'] or 0))
                        totals[attr]=(totals[attr] or 0)+value
                    end
                end
                for _,line in ipairs(manager:GetPetCardDesc(id,level) or {}) do
                    if line.lock==false then details[#details+1]='  '..(line.basedesc or '') end
                end
            end
        end
    end
    local ids={};for attr,_ in pairs(totals) do ids[#ids+1]=attr end;table.sort(ids)
    local lines={}
    for _,attr in ipairs(ids) do
        local _,percent=MartialDataManager:GetInstance():AttrValueIsPermyriad(attr)
        local value=percent and (tostring(totals[attr]/100)..'%') or tostring(totals[attr])
        lines[#lines+1]=GetLanguageByEnum(attr)..' +'..value
    end
    if #details==0 then return '当前没有宠物进入此助战阵容，生效加成为0。' end
    lines[#lines+1]='条件加成、概率效果及各宠物详情：'
    for _,line in ipairs(details) do lines[#lines+1]=line end
    return table.concat(lines,'\n')
end
function PetCardsUpgradeUI:Onclick_Btn_ShowMyPets()
    OpenWindowImmediately('TipsPopUI',{title='宠物培养总览',content=
        '经脉经验：'..tostring(exp())..'\n只有进入助战阵容的宠物生效；同一家族只计一个形态。\n\n剧情助战总值\n'
        ..overview(EmBattleSchemeType.EBST_Help)..'\n\n擂台助战总值\n'
        ..overview(EmBattleSchemeType.EBST_ArenaHelp)})
end
