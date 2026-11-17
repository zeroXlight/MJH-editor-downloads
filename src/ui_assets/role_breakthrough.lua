-- Read-only native role information with independent meridian-funded upgrades.
local U=CS.UnityEngine
local function balance() return tonumber(MeridiansDataManager:GetInstance():GetCurTotalExp()) or 0 end
local function mgr() return CardsUpgradeDataManager:GetInstance() end
local function named(tableName,id)
    local row=GetTableData(tableName,id)
    if not row then return '缺少配置 '..tostring(id) end
    local nameId=row.NameID or row.ItemNameID
    local name=nameId and GetLanguageByID(nameId) or row.ItemName or row.Name or ''
    return name~='' and name or (tableName..' '..tostring(id))
end
local function roleName(id,row)
    local s=row.NameID and GetLanguageByID(row.NameID) or ''
    return s~='' and s or ('角色 '..tostring(id))
end
local function rect(name,parent,x,y,w,h)
    local go=U.GameObject(name,typeof(U.RectTransform));go.layer=parent.gameObject.layer
    go.transform:SetParent(parent,false)
    local r=go:GetComponent('RectTransform');r.anchorMin=DRCSRef.Vec2(0,1);r.anchorMax=DRCSRef.Vec2(0,1)
    r.pivot=DRCSRef.Vec2(0,1);r.anchoredPosition=DRCSRef.Vec2(x,-y);r.sizeDelta=DRCSRef.Vec2(w,h)
    return go
end
local function text(self,parent,name,value,x,y,w,h,size)
    local go=rect(name,parent,x,y,w,h);local t=go:AddComponent(typeof(U.UI.Text))
    t.font=self.comText_BaseInfoName.font;t.text=value;t.fontSize=size or 21;t.color=U.Color(.16,.13,.10,1)
    t.alignment=U.TextAnchor.UpperLeft;t.supportRichText=true;t.raycastTarget=false
    t.horizontalOverflow=U.HorizontalWrapMode.Wrap;t.verticalOverflow=U.VerticalWrapMode.Overflow
    return t
end
local function button(self,parent,name,value,x,y,w,h,action)
    local go=rect(name,parent,x,y,w,h);local im=go:AddComponent(typeof(U.UI.Image));im.color=U.Color(.91,.86,.76,1)
    local b=go:AddComponent(typeof(U.UI.Button));b.targetGraphic=im
    local t=text(self,go.transform,'Label',value,8,7,w-16,h-10,20);t.alignment=U.TextAnchor.MiddleCenter
    self:AddButtonClickListener(b,action);return b,t
end
local function actionButton(self,parent,name,value,x,y,w,h,action)
    local b,t=button(self,parent,name,value,x,y,w,h,action)
    local original=self.objBtn_GradeUp:GetComponent('Image');local im=b:GetComponent('Image')
    im.sprite=original.sprite;im.type=original.type;im.color=U.Color(1,1,1,1);t.color=U.Color(1,1,1,1)
    return b,t
end
local function rankText(t,rank)
    rank=rank or 1
    if rank==1 then t.color=U.Color(.23,.21,.18,1)
    elseif rank==2 then t.color=U.Color(.13,.4,.2,1)
    else
        t.color=getRankColor(rank)
        local edge=t.gameObject:AddComponent(typeof(U.UI.Shadow));edge.effectColor=U.Color(.15,.12,.08,.8);edge.effectDistance=DRCSRef.Vec2(1,-1)
    end
end
local oldInit=RoleCardsUpgradeUI.Init
local nativeInfo=RoleCardsUpgradeUI.RefreashInfo
local function imageAt(parent,name,sprite,x,y,w,h)
    local go=rect(name,parent,x,y,w,h);local im=go:AddComponent(typeof(U.UI.Image));im.sprite=sprite;im.raycastTarget=false
    return im
end
local function mobileTab(self,parent,name,value,x,y,w,h,action)
    local b,t=button(self,parent,name,value,x,y,w,h,action);t.fontSize=22
    local brush=self:FindChildComponent(self.comToggle_rank.gameObject,'Toggle','Image')
    local bg=b:GetComponent('Image');if brush then bg.sprite=brush.sprite;bg.type=brush.type end
    bg.color=U.Color(1,1,1,0)
    local line=self:FindChildComponent(self.comToggle_rank.gameObject,'Image','Image')
    local underline=imageAt(b.transform,'Underline',line and line.sprite or nil,5,h-4,w-10,3)
    underline.color=U.Color(.5,.48,.44,1)
    local tint=brush and brush.sprite and U.Color(brush.color.r,brush.color.g,brush.color.b,1) or U.Color(.16,.15,.13,1)
    return b,t,underline,tint
end
local function selectMobileTab(b,t,line,on,tint)
    b:GetComponent('Image').color=on and (tint or U.Color(1,1,1,1)) or U.Color(1,1,1,0)
    t.color=on and U.Color(1,1,1,1) or U.Color(.2,.19,.17,1)
    line.gameObject:SetActive(not on)
end
function RoleCardsUpgradeUI:Init(...)
    oldInit(self,...)
    -- This prefab only supplies canvases for RoleInfo. Its list/background
    -- otherwise inherit layer 1000 and fall behind LoginUI's layer 1001.
    -- Use the same parent-relative order as BaseWindow, without hiding LoginUI
    -- or promoting this window above confirmation dialogs.
    local canvas=self._gameObject:GetComponent(typeof(U.Canvas)) or self._gameObject:AddComponent(typeof(U.Canvas))
    local parentCanvas=self._gameObject.transform.parent:GetComponentInParent(typeof(U.Canvas))
    local order=WINDOW_ORDER_INFO.RoleCardsUpgradeUI
    canvas.overrideSorting=true;canvas.additionalShaderChannels=31
    canvas.sortingLayerID=parentCanvas and parentCanvas.sortingLayerID or 0
    canvas.sortingOrder=(parentCanvas and parentCanvas.sortingOrder or 0)+(order and order.order or 330)
    if not self._gameObject:GetComponent(typeof(U.UI.GraphicRaycaster)) then self._gameObject:AddComponent(typeof(U.UI.GraphicRaycaster)) end
    self.Toggle_Bond.gameObject:SetActive(true)
    self:RemoveToggleClickListener(self.Toggle_Bond)
    self:AddToggleClickListener(self.Toggle_Bond,function(on) if on and not self.mjhSyncingSide then self:MJHOpenDetails('基础') end end)
    local label=self.Toggle_Bond:GetComponentInChildren(typeof(U.UI.Text));if label then label.text='培养' end
    self:RemoveToggleClickListener(self.Toggle_ability)
    self:AddToggleClickListener(self.Toggle_ability,function(on) if on and not self.mjhSyncingSide then self:MJHCloseDetails() end end)
    if self.btnDiscuss then self.btnDiscuss.gameObject:SetActive(false) end
    if self.btnWishTaskInfo then self.btnWishTaskInfo.gameObject:SetActive(false) end
    self.objSC_Panal:SetActive(true)
    self.comLoopScrollView.gameObject:SetActive(true)
    self.objNavbox:SetActive(false)
    self.comText_BaseInfoGift_Button.gameObject:SetActive(false)
    self.mjhReadOnlyText={text=''} -- source summary retained for diagnostics, never drawn over the native overview.
    self.mjhBalanceLabel=text(self,self._gameObject.transform,'MJHMeridians','',860,16,310,40,23)
    self.mjhConfigButton=button(self,self.objPanal_RoleInfo.transform,'MJHDetails','配置',558,658,100,40,function() self:MJHOpenDetails('基础') end)
    self.mjhUpgradeEffectsButton=actionButton(self,self.objPanal_RoleInfo.transform,'MJHUpgradeEffects','升级效果',558,418,120,40,function() self:MJHShowUpgradeEffects() end)
    local original=self.objBtn_GradeUp:GetComponent('Image');local target=self.mjhConfigButton:GetComponent('Image')
    target.sprite=original.sprite;target.type=original.type;target.color=U.Color(1,1,1,1)
    self.mjhConfigButton:GetComponentInChildren(typeof(U.UI.Text)).color=U.Color(1,1,1,1)
    -- Search by stable role ID or displayed name, without altering role data.
    local parent=self.objNPCList.transform
    local left=self.objNPCList:GetComponent('RectTransform').rect
    local listWidth=480
    local search=rect('MJHSearch',parent,36,83,listWidth,32)
    local image=search:AddComponent(typeof(U.UI.Image));image.color=U.Color(1,1,1,.8)
    local input=search:AddComponent(typeof(U.UI.InputField));local label=text(self,search.transform,'Text','',7,6,listWidth-14,27,19)
    input.textComponent=label
    local ph=text(self,search.transform,'Placeholder','搜索角色名称 / 编号',7,6,listWidth-14,27,18);ph.color=U.Color(.5,.45,.4,1);input.placeholder=ph
    input.onValueChanged:AddListener(function(value) if self.mjhResettingSearch then return end;self.mjhSearch=value;self.last_chose_id=nil;self.data_Chose_Index=nil;self:SetNeedUpdateData(true) end)
    self.mjhSearchField=input
    self.mjhSort='rank';self.mjhSortDescending=true;self.mjhSortTabs={}
    for i,entry in ipairs({{'grade','等级'},{'rank','品质'},{'main','主角'}}) do
        local kind=entry[1];local b,t,line,tint=mobileTab(self,parent,'MJHSort'..kind,entry[2],42+(i-1)*108,120,102,38,function()
            if kind=='main' then self.mjhMainOnly=not self.mjhMainOnly;self:SetNeedUpdateData(true)
            else self:MJHSortCards(kind) end
        end)
        self.mjhSortTabs[kind]={b,t,line,tint}
    end
    local filter=button(self,parent,'MJHFilter','筛',402,123,40,34,function() self.mjhFilterPanel:SetActive(not self.mjhFilterPanel.activeSelf) end)
    local filterBG=filter:GetComponent('Image');filterBG.sprite=original.sprite;filterBG.type=original.type;filterBG.color=U.Color(1,1,1,1)
    filter:GetComponentInChildren(typeof(U.UI.Text)).color=U.Color(1,1,1,1)
    -- Reuse the original card prefab and its portrait mask, selection frame,
    -- rarity effects and pooled scrolling instead of approximating them.
    local loop=self.comLoopScrollView.gameObject
    loop.transform:SetParent(parent,false)
    local lr=loop:GetComponent('RectTransform');lr.anchorMin=DRCSRef.Vec2(0,1);lr.anchorMax=DRCSRef.Vec2(0,1)
    lr.pivot=DRCSRef.Vec2(0,1);lr.anchoredPosition=DRCSRef.Vec2(40,-160);lr.sizeDelta=DRCSRef.Vec2(472,510)
    self.mjhNativeCardCells={};self.mjhListButtons={};self.obj_card_list={}
    self.mjhPageText=text(self,parent,'MJHRosterCount','',42,676,470,24,14)
    local popup=rect('MJHFilterPanel',parent,176,160,300,152);popup:AddComponent(typeof(U.UI.Image)).color=U.Color(.96,.94,.89,1)
    self.mjhFilterPanel=popup;popup:SetActive(false)
    text(self,popup.transform,'Title','筛选角色',12,8,270,30,21)
    for i,entry in ipairs({{'all','全部名单'},{'upgraded','已突破'},{'custom','玩家自建'}}) do
        local choice=entry[1]
        button(self,popup.transform,'Filter'..choice,entry[2],12,42+(i-1)*34,276,32,function()
            self.mjhRoleFilter=choice;self.mjhMainOnly=false;popup:SetActive(false);self:SetNeedUpdateData(true)
        end)
    end
end
function RoleCardsUpgradeUI:MJHSortCards(kind)
    local wasMain=self.mjhMainOnly;self.mjhMainOnly=false
    self.mjhSortDescending=self.mjhSort~=kind or not self.mjhSortDescending
    self.mjhSort=kind;self.mjhPage=1;self.iUpdateFlag=1
    if wasMain then self:SetNeedUpdateData(true) end
end
function RoleCardsUpgradeUI:OnEnable()
    OpenWindowBar({windowstr='RoleCardsUpgradeUI',topBtnState={bBackBtn=false,bBondPellet=false,bGoodEvil=false,bSilver=false,bCoin=false},bSaveToCache=false})
end
function RoleCardsUpgradeUI:MJHCloseDetails()
    self.mjhActiveDetail=nil
    self.mjhSyncingSide=true;self.Toggle_ability.isOn=true;self.Toggle_Bond.isOn=false;self.mjhSyncingSide=false
    if self.mjhDetailPanel then self.mjhDetailPanel:SetActive(false) end
    self.objPanal_RoleInfo:SetActive(true)
end
function RoleCardsUpgradeUI:MJHOpenDetails(tab)
    local data=self:GetCurRoleCardData();if not data then return end
    if self.mjhUpgradePanel then self.mjhUpgradePanel:SetActive(false) end
    if tab=='能力' then tab='基础' end
    self.mjhActiveDetail=tab
    self.mjhSyncingSide=true;self.Toggle_Bond.isOn=true;self.Toggle_ability.isOn=false;self.mjhSyncingSide=false
    if not self.mjhDetailPanel then
        local w=610;local h=598
        local go=rect('MJHReadOnlyDetails',self._gameObject.transform,556,82,w,618)
        go:AddComponent(typeof(U.UI.Image)).color=U.Color(1,1,1,0)
        local canvas=go:AddComponent(typeof(U.Canvas));canvas.overrideSorting=true
        local parentCanvas=self.objPanal_RoleInfo:GetComponentInParent(typeof(U.Canvas))
        if parentCanvas then canvas.sortingLayerID=parentCanvas.sortingLayerID;canvas.sortingOrder=parentCanvas.sortingOrder+1000
        else canvas.sortingOrder=1000 end
        go:AddComponent(typeof(U.UI.GraphicRaycaster))
        self.mjhDetailPanel=go
        self.mjhDetailTitle=text(self,go.transform,'Title','',16,-28,w-125,25,15)
        self.mjhDetailBack=actionButton(self,go.transform,'Close','能力',w-88,-28,80,28,function()
            if self.mjhMartialDetail then self.mjhMartialDetail=false;self:MJHOpenDetails('武学') else self:MJHCloseDetails() end
        end)
        self.mjhDetailTabs={}
        for i,name in ipairs({'基础','详细','装备','武学','天赋'}) do
            local chosen=name
            local b,t,line,tint=mobileTab(self,go.transform,'Tab'..i,name,16+(i-1)*112,6,104,38,function() self:MJHOpenDetails(chosen) end)
            self.mjhDetailTabs[name]=b;self.mjhDetailTabs[name..'_style']={t,line,tint}
        end
        local vp=rect('Viewport',go.transform,16,64,w-32,546)
        vp:AddComponent(typeof(U.UI.Image)).color=U.Color(1,1,1,1)
        vp:AddComponent(typeof(U.UI.Mask)).showMaskGraphic=false
        local content=rect('Content',vp.transform,0,0,w-42,1000)
        local sr=vp:AddComponent(typeof(U.UI.ScrollRect));sr.horizontal=false;sr.viewport=vp:GetComponent('RectTransform');sr.content=content:GetComponent('RectTransform')
        sr.movementType=U.UI.ScrollRect.MovementType.Clamped
        self.mjhDetailScroll=sr;self.mjhDetailContent=content:GetComponent('RectTransform')
        self.mjhDetailText=text(self,content.transform,'Text','',4,0,w-48,1000,20)
        self.mjhDetailGrid=rect('Attributes',content.transform,0,0,w-42,1000)
        self.mjhMartialList=rect('MartialList',go.transform,16,94,170,h-114)
    end
    self.mjhDetailPanel:SetActive(true);self.mjhDetailPanel.transform:SetAsLastSibling()
    self.objPanal_RoleInfo:SetActive(false)
    self.mjhDetailTitle.text=roleName(data.roleid,data.roledata)..' +'..data.grade..' · '..data.roleid..' · 模板资料'
    for _,name in ipairs({'基础','详细','装备','武学','天赋'}) do
        local style=self.mjhDetailTabs[name..'_style'];selectMobileTab(self.mjhDetailTabs[name],style[1],style[2],name==tab,style[3])
    end
    self:MJHRenderMobileContent(tab,data)
    self.mjhDetailScroll.verticalNormalizedPosition=1
end

function RoleCardsUpgradeUI:InitDataList()
    self.dataRoleCardList={};self.mapRoleCardList={};self.sort_list_rank={};self.sort_list_grade={};self.sort_list_rank_ex={};self.sort_list_grade_ex={}
    local rows=mgr():MJHBreakthroughRoles();local cards=mgr():GetEntireRoleCardList();local query=string.lower(self.mjhSearch or '')
    for id,row in pairs(rows) do
        local n=roleName(id,row)
        local inst=cards[id] or {};local level=inst.level or 0
        local custom=mgr():MJHIsCustomRole(id,row) and true or false
        local main=custom or (self.role_create_map and self.role_create_map[id]) or false
        local filter=self.mjhRoleFilter or 'all'
        local show=(not self.mjhMainOnly or main) and (filter~='upgraded' or level>0) and (filter~='custom' or custom)
        if show and (query=='' or string.find(string.lower(n..' '..tostring(id)),query,1,true)) then
            local quality=mgr():GetCurEffctStateByRoleID(id,RoleCardEffect.RCE_RoleQualityUp,level) or 0
            local entry={roleid=id,roledata=row,grade=level,piece=balance(),unlock=true,rank=math.min(8,(row.Rank or 1)+quality),
                num4map=#self.dataRoleCardList+1,needpiece=mgr():MJHBreakthroughCost(level) or math.huge,custom=custom,is_main=main}
            table.insert(self.dataRoleCardList,entry);self.mapRoleCardList[id]=entry
        end
    end
    self.mjhPage=1
end
function RoleCardsUpgradeUI:GetCurRoleCardData(index)
    if index then
        local row=self.dataRoleCardList[index]
        if row and row.rank>7 then local view={};for k,v in pairs(row) do view[k]=v end;view.rank=7;return view end
        return row
    end
    return self.mjhSelectedData
end
function RoleCardsUpgradeUI:RefreashList()
    table.sort(self.dataRoleCardList,function(a,b)
        if self.mjhSort=='rank' and a.rank~=b.rank then return self.mjhSortDescending and a.rank>b.rank or not self.mjhSortDescending and a.rank<b.rank end
        if self.mjhSort=='grade' and a.grade~=b.grade then return self.mjhSortDescending and a.grade>b.grade or not self.mjhSortDescending and a.grade<b.grade end
        return a.roleid<b.roleid
    end)
    local old=self.last_chose_id or (self.mjhSelectedData and self.mjhSelectedData.roleid)
    self.last_chose_id=nil
    self.mjhSelectedData=old and self.mapRoleCardList[old] or nil
    for kind,parts in pairs(self.mjhSortTabs) do selectMobileTab(parts[1],parts[2],parts[3],kind=='main' and self.mjhMainOnly or kind==self.mjhSort and not self.mjhMainOnly,parts[4]) end
    self.mjhPageRows=self.dataRoleCardList
    self.obj_card_list={};self.mjhNativeCardCells={};self.mjhListButtons={}
    self.comLoopScrollView.totalCount=#self.dataRoleCardList
    self.comLoopScrollView:StopMovement()
    self.comLoopScrollView:RefillCells()
    self.mjhPageText.text='共 '..#self.dataRoleCardList..' 人  ·  滚轮或拖动浏览'
    if not self.mjhSelectedData then self.mjhSelectedData=self.dataRoleCardList[1] end
    if self.mjhInitialDetails and self.mjhSelectedData then self.mjhInitialDetails=false;self:MJHOpenDetails('基础') end
    self.iUpdateFlag=2
end
local nativeCard=RoleCardsUpgradeUI.OnRoleCardChanged
function RoleCardsUpgradeUI:OnRoleCardChanged(go,index)
    nativeCard(self,go,index)
    local row=self.dataRoleCardList[index+1];if not row then return end
    local cell=go.gameObject;self.mjhNativeCardCells[index+1]=cell
    local b=self:FindChildComponent(cell,'ImgBG','DRButton')
    local info=self:FindChild(cell,'Info');local proxy=self:FindChildComponent(cell,'Info/head','Image')
    local clip=self:FindChild(info,'MJHHeadClip')
    if not clip then clip=rect('MJHHeadClip',info.transform,0,0,140,144);clip:AddComponent(typeof(U.UI.RectMask2D));clip.transform:SetAsFirstSibling() end
    local visible=self:FindChildComponent(clip,'Portrait','Image')
    if not visible then visible=imageAt(clip.transform,'Portrait',nil,0,0,140,144) end
    visible.sprite=proxy.sprite;proxy.color=U.Color(1,1,1,0)
    local hr=visible.rectTransform;hr.anchorMin=DRCSRef.Vec2(.5,.5);hr.anchorMax=DRCSRef.Vec2(.5,.5);hr.pivot=DRCSRef.Vec2(.5,.5);hr.anchoredPosition=DRCSRef.Vec2(0,0)
    if visible.sprite then local r=visible.sprite.rect;local scale=math.max(140/r.width,144/r.height);hr.sizeDelta=DRCSRef.Vec2(r.width*scale,r.height*scale) end
    self.mjhListButtons[index+1]={button=b,head=visible}
    self:FindChild(cell,'ImgBG_chose'):SetActive(self.mjhSelectedData and self.mjhSelectedData.roleid==row.roleid or false)
    local main=self:FindChild(cell,'Info/img_mainrole');main:SetActive(row.is_main)
    local flag=self:FindChild(info,'MJHCustomTag')
    if row.custom and not flag then flag=text(self,info.transform,'MJHCustomTag','自建',80,10,55,24,14).gameObject end
    if flag then flag:SetActive(row.custom) end
    local scrollbar=self:FindChildComponent(cell,'Info/Scrollbar','Scrollbar');scrollbar.size=row.needpiece<math.huge and math.min(1,balance()/row.needpiece) or 1
    local cost=self:FindChildComponent(cell,'Info/Scrollbar/Value','Text');cost.resizeTextForBestFit=true;cost.resizeTextMinSize=11;cost.resizeTextMaxSize=18
    local name=self:FindChildComponent(cell,'Info/Text_title','Text');name.resizeTextForBestFit=true;name.resizeTextMinSize=12;name.resizeTextMaxSize=19
end
function RoleCardsUpgradeUI:OnClick_Chose_Card(index)
    self.mjhSelectedData=self.dataRoleCardList[index];self.data_Chose_Index=index;self.iUpdateFlag=2
    self.mjhMartialDetail=false;self.mjhSelectedEquipment=nil
    for i,cell in pairs(self.mjhNativeCardCells) do self:FindChild(cell,'ImgBG_chose'):SetActive(i==index) end
end

function RoleCardsUpgradeUI:RefreshRedPoint()
    self.objToggleRedPoint_ability:SetActive(false);self.objToggleRedPoint_bond:SetActive(false)
end
function RoleCardsUpgradeUI:GetRedPointStateBond() return false end
function RoleCardsUpgradeUI:GetRedPointStateAbility(data)
    return data and data.grade<math.min(10,mgr():GetUpgrade(2,data.rank)) and balance()>=data.needpiece or false
end
function RoleCardsUpgradeUI:RefreashInfo()
    local data=self:GetCurRoleCardData()
    if not data or not data.roledata then
        self:MJHCloseDetails();self.objBaseInfoPanal:SetActive(false);self.objGradeInfoPanal:SetActive(false)
        self.comText_BaseInfoName.text='没有匹配的角色';self.comText_BaseInfoTitle.text='请修改查询条件'
        self.mjhReadOnlyText.text='';self.objActor_BaseInfoSpine:SetActive(false);self.comBtn_GradeUp.interactable=false
        self.mjhConfigButton.interactable=false;self.mjhUpgradeEffectsButton.interactable=false
        if self.mjhUpgradePanel then self.mjhUpgradePanel:SetActive(false) end
        self.ComBtn_GradeUpScrollBar_text.text='';self.comtextBtn_GradeUP.text='没有选择角色';return
    end
    local row=data.roledata;local level=data.grade;local cap=math.min(10,mgr():GetUpgrade(2,data.rank))
    self.objBaseInfoPanal:SetActive(true);self.objGradeInfoPanal:SetActive(true)
    nativeInfo(self)
    self.mjhConfigButton.interactable=true;self.mjhUpgradeEffectsButton.interactable=true
    self.comText_BaseInfoName.text=roleName(data.roleid,row)..' +'..level
    self.comText_BaseInfoName.color=(data.rank==1 or data.rank>=8) and U.Color(.23,.21,.18,1) or getRankColor(data.rank)
    self.comText_BaseInfoTitle.text='编号 '..data.roleid..' · 跨周目生效'
    self.comText_BaseInfoTitle.fontSize=16
    local lines={'<b>基础属性</b>（模板原值，只读）'}
    local attr=GetTableData('RoleAttr',row.AttributeID or 0)
    local attrs={{'Strength','力道'},{'Agility','灵巧'},{'Power','内劲'},{'Constitution','体质'},{'Energy','精力'},{'Comprehension','悟性'},
        {'HP','生命'},{'MP','真气'},{'MartialATK','武学攻击'},{'Defense','防御'},{'Speed','速度'}}
    if attr then for _,a in ipairs(attrs) do table.insert(lines,a[2]..'：'..tostring(attr[a[1]] or 0)) end
    else table.insert(lines,'使用门派 / 人物类型及等级生成属性') end
    table.insert(lines,'基础属性加成：+'..tostring(level*20)..'%（按原生范围计算，不乘装备和后天加点）')
    table.insert(lines,'\n<b>天赋</b>（原始配置）')
    local gifts=row.Gift or {};if #gifts==0 then table.insert(lines,'无默认天赋') end
    for _,id in ipairs(gifts) do table.insert(lines,named('Gift',id)..' · '..id) end
    table.insert(lines,'\n<b>默认装备</b>')
    for _,slot in ipairs({{'Weapon','武器'},{'Artifacts','神器'},{'Clothes','衣服'},{'Shoe','鞋子'},{'Ornaments','饰品'},{'KungfuBook','秘籍'},{'Horse','坐骑'}}) do
        local id=row[slot[1]] or 0
        table.insert(lines,slot[2]..'：'..(id>0 and (named('Item',id)..' · '..id) or '无'))
    end
    table.insert(lines,'\n<b>默认武学</b>')
    local arts=row.Kungfu or {};if #arts==0 then table.insert(lines,'按人物 / 门派模板生成') end
    for i,id in ipairs(arts) do table.insert(lines,named('Martial',id)..' · '..id..'（'..tostring((row.KungfuLevel or {})[i] or 1)..'级）') end
    table.insert(lines,'\n实际人物还受生成模板、等级、装备和已学武学影响；此处不能修改配置。')
    self.mjhReadOnlyText.text=table.concat(lines,'\n')
    self.spineRoleUINew:SetRoleDataByBaseID(data.roleid);self.spineRoleUINew:UpdateRoleSpine();self.objActor_BaseInfoSpine:SetActive(true)
    local cost=mgr():MJHBreakthroughCost(level)
    self.comBtn_GradeUp.interactable=not self.mjhPendingUpgrade and level<cap and cost and balance()>=cost or false
    self.comtextBtn_GradeUP.text=self.mjhPendingUpgrade and '正在突破…' or level>=cap and '已达当前突破上限' or '突破'
    self.ComBtn_GradeUpScrollBar_text.text='经脉点 '..string.format('%.0f',balance())..(cost and (' / 消耗 '..cost) or ' · 已满级')
    self.ComBtn_GradeUpScrollBar.size=cost and math.min(1,balance()/cost) or 1
    self.mjhLastBalance=balance()
    self.mjhBalanceLabel.text='经脉点　'..string.format('%.0f',balance())
    for i,cell in pairs(self.mjhNativeCardCells) do self:FindChild(cell,'ImgBG_chose'):SetActive(self.dataRoleCardList[i] and self.dataRoleCardList[i].roleid==data.roleid or false) end
    if self.mjhActiveDetail then self:MJHOpenDetails(self.mjhActiveDetail) else self.objPanal_RoleInfo:SetActive(true) end
    if self.mjhUpgradePanel and self.mjhUpgradePanel.activeSelf then self:MJHShowUpgradeEffects() end
end
function RoleCardsUpgradeUI:RefreashGradeInfo()
    for _,go in ipairs(self.objs_Gradeinfo) do self:RefreashGradeInfoPerLine(go,'','','') end
    self.objs_Gradeinfo[4]:SetActive(false)
    local data=self:GetCurRoleCardData();if not data or not data.roledata then return end
    local nextLevel=math.min(10,data.grade+1)
    self:RefreashGradeInfoPerLine(self.objs_Gradeinfo[1],'角色突破',tostring(data.grade),tostring(nextLevel))
    self:RefreashGradeInfoPerLine(self.objs_Gradeinfo[2],'基础属性加成','+'..tostring(data.grade*20)..'%','+'..tostring(nextLevel*20)..'%')
    local before=mgr():GetCurEffctStateByRoleID(data.roleid,RoleCardEffect.RCE_Disposition,data.grade)
    local after=mgr():GetCurEffctStateByRoleID(data.roleid,RoleCardEffect.RCE_Disposition,nextLevel)
    if before~=after then self:RefreashGradeInfoPerLine(self.objs_Gradeinfo[3],'初始好感加成',tostring(before),tostring(after))
    else self:RefreashGradeInfoPerLine(self.objs_Gradeinfo[3],'经脉点消耗','',tostring(mgr():MJHBreakthroughCost(data.grade) or '已满级')) end
end
function RoleCardsUpgradeUI:Onclick_Btn_GradeUp()
    if self.mjhPendingUpgrade then return end
    local data=self:GetCurRoleCardData();if not data or not data.roledata then return end
    local cost=mgr():MJHBreakthroughCost(data.grade)
    if data.grade>=math.min(10,mgr():GetUpgrade(2,data.rank)) or not cost then SystemUICall:GetInstance():Toast('已达当前突破上限');return end
    if balance()<cost then SystemUICall:GetInstance():Toast('经脉点不足');return end
    self.mjhPendingUpgrade={id=data.roleid,level=data.grade,time=U.Time.realtimeSinceStartup}
    self.comBtn_GradeUp.interactable=false
    self.comtextBtn_GradeUP.text='正在突破…'
    self.last_chose_id=data.roleid
    SendRequestRolePetCardOperate(RPCRT_ROLE_CARD,RPCOT_LEVEL_UP_ROLE_CARD,data.roleid,0)
    SendMeridiansOpr(SMOT_REFRESH_ALL,0)
    self:SetNeedUpdateData(true)
end
local oldRefresh=RoleCardsUpgradeUI.RefreshUI
function RoleCardsUpgradeUI:RefreshUI(...)
    self.mjhPendingUpgrade=nil
    if self.mjhUpgradePanel then self.mjhUpgradePanel:SetActive(false) end
    self.mjhResettingSearch=true;self.mjhSearch=''
    if self.mjhSearchField then self.mjhSearchField.text='' end
    self.mjhResettingSearch=false
    self:MJHCloseDetails()
    self.mjhInitialDetails=true
    oldRefresh(self,...)
    self.eChosenTab=1;self.objPanal_Bond:SetActive(false);self.objPanal_RoleInfo:SetActive(true)
    self.data_Chose_Toggle_Nav=1;self.eSortType=1;self.data_Chose_Index=nil;self.iUpdateFlag=1
end
function RoleCardsUpgradeUI:Update(...)
    -- Consume a balance change once. Leaving the old balance here restarted
    -- phase 1 every frame, so phase 2 never refreshed the selected role.
    local currentBalance=balance()
    if self.mjhLastBalance and self.mjhLastBalance~=currentBalance then
        self.mjhLastBalance=currentBalance;self:SetNeedUpdateData(true)
    end
    local selected=self:GetCurRoleCardData()
    local cards=mgr().roleIdCardListMap or {}
    if selected and cards[selected.roleid] and cards[selected.roleid].level~=selected.grade then self:SetNeedUpdateData(true) end
    local pending=self.mjhPendingUpgrade
    if pending and ((cards[pending.id] and (cards[pending.id].level or 0)>pending.level) or U.Time.realtimeSinceStartup-pending.time>=5) then
        self.mjhPendingUpgrade=nil;self:SetNeedUpdateData(true)
    end
    if self.iNeedUpdateData then self.iNeedUpdateData=false;self:InitDataList();self.iUpdateFlag=1 end
    if self.iUpdateFlag==1 then self:RefreashList()
    elseif self.iUpdateFlag==2 then self.iUpdateFlag=0;self:RefreashInfo();self:RefreashGradeInfo() end
end
