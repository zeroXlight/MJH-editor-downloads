-- Mobile PlatformAbilityShowUI layout, adapted to PC template-only viewing.
-- Rendering never calls character learning, equipment or point operations.
local ink=U.Color(.24,.23,.21,1)
local caption=U.Color(.50,.44,.37,1)
local function clearChildren(go)
    for i=go.transform.childCount-1,0,-1 do local child=go.transform:GetChild(i).gameObject;child:SetActive(false);U.Object.Destroy(child) end
end
local function labelValue(self,parent,label,value,x,y,w,labelWidth)
    labelWidth=labelWidth or 92
    text(self,parent,'Label',label,x,y,labelWidth,34,22).color=caption
    local t=text(self,parent,'Value',tostring(value),x+labelWidth,y,w-labelWidth-8,34,22)
    t.color=ink;t.alignment=U.TextAnchor.UpperRight;t.resizeTextForBestFit=true;t.resizeTextMinSize=15;t.resizeTextMaxSize=22
end
local function stripe(parent,y,w,h)
    imageAt(parent,'Stripe',nil,0,y,w,h).color=U.Color(.2,.2,.2,.045)
end
local function groupTitle(self,parent,value,y)
    local brush=self:FindChildComponent(self.comToggle_rank.gameObject,'Toggle','Image')
    local bg=imageAt(parent,'GroupInk',brush and brush.sprite or nil,0,y,290,30)
    bg.color=brush and brush.color or U.Color(.2,.2,.2,1)
    local t=text(self,parent,'GroupTitle','◇ '..value,10,y,280,32,23);t.color=U.Color(1,1,1,1)
end
function RoleCardsUpgradeUI:MJHRenderMobileContent(tab,data)
    local row=data.roledata;local grid=self.mjhDetailGrid
    clearChildren(grid);clearChildren(self.mjhMartialList)
    self.mjhMartialList:SetActive(false)
    self.mjhDetailText.gameObject:SetActive(false);self.mjhDetailText.text=''
    grid:SetActive(true)
    local vp=self.mjhDetailScroll.viewport;vp.anchoredPosition=DRCSRef.Vec2(16,-64);vp.sizeDelta=DRCSRef.Vec2(578,546)
    self.mjhDetailContent.sizeDelta=DRCSRef.Vec2(568,540)
    local backLabel=self.mjhDetailBack:GetComponentInChildren(typeof(U.UI.Text))
    backLabel.text=self.mjhMartialDetail and tab=='武学' and '返回武学' or '能力'
    backLabel.fontSize=self.mjhMartialDetail and tab=='武学' and 14 or 20
    local function note(value,y) text(self,grid.transform,'Notice',value,0,y,558,48,14).color=caption end
    if tab=='基础' then
        local attr=GetTableData('RoleAttr',row.AttributeID or 0) or {}
        labelValue(self,grid.transform,'生命',attr.HP or 0,0,8,190,65)
        labelValue(self,grid.transform,'门派',ClanDataManager:GetInstance():GetClanNameByBaseID(row.Clan) or '无',206,8,350,72)
        labelValue(self,grid.transform,'真气',attr.MP or 0,0,48,190,65)
        local favors={};for _,id in ipairs(row.Favor or {}) do favors[#favors+1]=RoleDataHelper.GetFavorName(id) end
        labelValue(self,grid.transform,'喜好',#favors>0 and table.concat(favors,' ') or '无',206,48,350,72)
        local groups={
            {104,{{'Strength','力道'},{'Agility','灵巧'},{'Energy','精力'},{'Constitution','体质'},{'Comprehension','悟性'},{'Power','内劲'}}},
            {214,{{'SwordMastery','剑法精通'},{'KnifeMastery','刀法精通'},{'FistMastery','拳掌精通'},{'LegMastery','腿法精通'},{'StickMastery','奇门精通'},{'NeedleMastery','暗器精通'},{'HealingMastery','医术精通'},{'SoulMastery','内功精通'}}},
            {360,{{'JianFaATK','剑法攻击'},{'DaoFaATK','刀法攻击'},{'QuanFaATK','拳掌攻击'},{'TuiFaATK','腿法攻击'},{'QiMenATK','奇门攻击'},{'AnQiATK','暗器攻击'},{'YiShuATK','医术攻击'},{'NeiGongATK','内功攻击'}}}}
        for _,g in ipairs(groups) do for i,a in ipairs(g[2]) do
            labelValue(self,grid.transform,a[2],attr[a[1]] or 0,((i-1)%3)*186,g[1]+math.floor((i-1)/3)*38,182,96)
        end end
        note('模板原值，只读；本周目等级、装备、加点和武学会影响实际面板。\n当前突破 +'..data.grade..' · 对应角色跨周目保留',492)
        self.mjhDetailContent.sizeDelta=DRCSRef.Vec2(568,540)
    elseif tab=='详细' then
        local attr=GetTableData('RoleAttr',row.AttributeID or 0) or {}
        local groups={{'攻击',{{'MingZhongZhi','命中'},{'BaoJiZhi','暴击'},{'LianJiZhi','连击'},{'BaoShangZhi','暴伤'}}},
            {'防御',{{'BaoJiDiKang','暴击抵抗'},{'LianJiDiKang','抗连击'},{'FanJiZhi','反击'},{'PoZhaoZhi','破招'},{'HPRecover','回合恢复生命'},{'MPRecover','回合回真气'},{'Defense','防御'},{'Speed','速度'},{'ShanBiZhi','闪避'},{'KungfuLimit','武学额外上限'}}}}
        local y=4
        for _,g in ipairs(groups) do
            groupTitle(self,grid.transform,g[1],y);y=y+34
            for i,a in ipairs(g[2]) do
                local yy=y+math.floor((i-1)/2)*39
                if i%2==1 then stripe(grid.transform,yy,558,38) end
                labelValue(self,grid.transform,a[2],attr[a[1]] or 0,((i-1)%2)*279,yy,275,160)
            end
            y=y+math.ceil(#g[2]/2)*39+18
        end
        note('模板配置值，只读；不推算未确定的战斗概率和条件增益。',y)
        self.mjhDetailContent.sizeDelta=DRCSRef.Vec2(568,y+48)
    elseif tab=='装备' then
        self.mjhEquipmentButtons={}
        local slots={{'Weapon','武器'},{'Clothes','衣服'},{'Shoe','鞋子'},{'Artifacts','神器'},{'Ornaments','饰品'},{'KungfuBook','秘籍'},{'Horse','坐骑'}}
        for i,slot in ipairs(slots) do
            local ident=row[slot[1]] or 0;local item=ident>0 and GetTableData('Item',ident) or nil
            local x=((i-1)%6)*94;local y=8+math.floor((i-1)/6)*114
            local b,t=button(self,grid.transform,'Equip'..i,'',x,y,84,84,function() self.mjhSelectedEquipment=i;self:MJHOpenDetails('装备') end)
            b:GetComponent('Image').color=U.Color(1,1,1,0)
            local frame=self:FindChildComponent(self.objItem_BaseInfoExclusive,'Frame','Image')
            local im=imageAt(b.transform,'Frame',frame and frame.sprite or nil,0,0,84,84)
            im.color=U.Color(1,1,1,item and 1 or .35)
            if item then local icon=imageAt(b.transform,'Icon',GetSprite(item.Icon),10,10,64,64);icon.preserveAspect=true
            else text(self,b.transform,'Empty','无',22,22,44,38,22).color=caption end
            text(self,grid.transform,'Slot',slot[2],x,y+85,84,26,17).alignment=U.TextAnchor.MiddleCenter
            self.mjhEquipmentButtons[i]=b
        end
        local index=math.min(#slots,self.mjhSelectedEquipment or 1);local slot=slots[index];local ident=row[slot[1]] or 0
        local item=ident>0 and GetTableData('Item',ident) or nil
        local title=text(self,grid.transform,'ItemName',slot[2]..' · '..(item and named('Item',ident) or '无默认装备'),0,252,556,38,24)
        if item then rankText(title,item.Rank) end
        local desc=text(self,grid.transform,'ItemDescription',item and (item.ItemDesc or '') or '按周目生成配置决定实际装备。',0,296,556,160,21)
        desc.color=ink
        note((item and ('编号 '..ident..' · 品质 '..item.Rank..'\n') or '')..'默认装备只读，可点选查看；不能穿戴、替换或修改。',470)
        self.mjhDetailContent.sizeDelta=DRCSRef.Vec2(568,530)
    elseif tab=='天赋' then
        local ids=mgr():MJHDefaultGifts(data.roleid,row,data.grade)
        local y=2
        for _,id in ipairs(ids) do
            local gift=GetTableData('Gift',id);local t=text(self,grid.transform,'GiftName',named('Gift',id),0,y,556,36,25);rankText(t,gift.Rank)
            y=y+38
            local d=text(self,grid.transform,'GiftDescription',GetLanguageByID(gift.DescID or 0) or '',0,y,556,1000,22);d.color=ink
            y=y+math.max(30,d.preferredHeight)+26
        end
        if #ids==0 then text(self,grid.transform,'Empty','无默认或突破解锁天赋',0,8,556,38,22) end
        note('角色默认与突破解锁天赋，只读；周目学习结果以实际角色为准。',y+4)
        self.mjhDetailContent.sizeDelta=DRCSRef.Vec2(568,y+56)
    else
        local arts=row.Kungfu or {};local levels=row.KungfuLevel or {}
        if self.mjhMartialRole~=data.roleid then self.mjhMartialRole=data.roleid;self.mjhMartialDetail=false;self.mjhMartialIndex=1 end
        self.mjhMartialButtons={}
        local y=2
        if not self.mjhMartialDetail then
            for i,id in ipairs(arts) do
                local martial=GetTableData('Martial',id);local index=i
                local b,t=button(self,grid.transform,'Martial'..id,named('Martial',id)..'    '..(levels[i] or 1)..'级',0,y,558,38,function()
                    self.mjhMartialIndex=index;self.mjhMartialDetail=true;self:MJHOpenDetails('武学')
                end)
                b:GetComponent('Image').color=U.Color(1,1,1,0);t.alignment=U.TextAnchor.UpperLeft;t.fontSize=25
                if martial then rankText(t,martial.Rank) end
                self.mjhMartialButtons[i]=b;y=y+42
                local d=text(self,grid.transform,'MartialDescription',martial and (GetLanguageByID(martial.DesID or 0) or '') or '缺少配置 '..id,0,y,556,1000,22);d.color=ink
                y=y+math.max(30,d.preferredHeight)+22
            end
            if #arts==0 then text(self,grid.transform,'Empty','没有固定默认武学，按人物 / 门派模板生成。',0,8,556,65,22);y=80 end
            note('默认武学，只读；点击武学名称查看完整词条。',y+4);y=y+56
        else
            local i=math.max(1,math.min(#arts,self.mjhMartialIndex or 1));local id=arts[i];local martial=id and GetTableData('Martial',id);local lv=levels[i] or 1
            if martial then
                local title=text(self,grid.transform,'MartialName',named('Martial',id)..' '..lv..'级',0,y,556,38,25);rankText(title,martial.Rank);y=y+44
                local info=text(self,grid.transform,'MartialInfo','编号 '..id..' · 修炼上限 '..martial.LvLimit..'级 · 冷却 '..martial.ColdTime..'回合',0,y,556,36,17);info.color=caption;y=y+42
                local clauses=MartialDataManager:GetInstance():GetMartialItemsDesc(martial,nil,lv,martial.LvLimit,true) or {}
                for _,clause in ipairs(clauses) do if clause.desc and clause.desc~='' then
                    local line=text(self,grid.transform,'Clause',(clause.prefix or '')..clause.desc,0,y,556,1000,22);line.color=ink;y=y+math.max(30,line.preferredHeight)+13
                end end
            end
            note('原生武学词条，只提供查看。右上角返回武学列表。',y+4);y=y+56
        end
        self.mjhDetailContent.sizeDelta=DRCSRef.Vec2(568,y)
    end
end

function RoleCardsUpgradeUI:MJHShowUpgradeEffects()
    local data=self:GetCurRoleCardData();if not data then return end
    if not self.mjhUpgradePanel then
        local panel=rect('MJHUpgradeEffectsPanel',self._gameObject.transform,550,86,620,610)
        panel:AddComponent(typeof(U.UI.Image)).color=U.Color(.97,.95,.90,1)
        local cv=panel:AddComponent(typeof(U.Canvas));local parent=self._gameObject:GetComponent(typeof(U.Canvas))
        cv.overrideSorting=true;cv.sortingLayerID=parent.sortingLayerID;cv.sortingOrder=parent.sortingOrder+1000
        panel:AddComponent(typeof(U.UI.GraphicRaycaster))
        self.mjhUpgradeTitle=text(self,panel.transform,'Title','升级效果',18,12,490,36,25)
        actionButton(self,panel.transform,'Close','返回',518,12,84,36,function() panel:SetActive(false) end)
        local vp=rect('Viewport',panel.transform,18,64,584,524)
        vp:AddComponent(typeof(U.UI.Image)).color=U.Color(1,1,1,1)
        vp:AddComponent(typeof(U.UI.Mask)).showMaskGraphic=false
        local content=rect('Content',vp.transform,0,0,574,1000)
        local sr=vp:AddComponent(typeof(U.UI.ScrollRect));sr.horizontal=false;sr.viewport=vp:GetComponent('RectTransform');sr.content=content:GetComponent('RectTransform')
        sr.movementType=U.UI.ScrollRect.MovementType.Clamped
        self.mjhUpgradePanel=panel;self.mjhUpgradeContent=content;self.mjhUpgradeScroll=sr
    end
    self.mjhUpgradePanel:SetActive(true);self.mjhUpgradePanel.transform:SetAsLastSibling()
    self.mjhUpgradeTitle.text=roleName(data.roleid,data.roledata)..' · 升级效果'
    clearChildren(self.mjhUpgradeContent)
    local y=0
    local notice=text(self,self.mjhUpgradeContent.transform,'Scope','六项基础属性随突破提高，攻击等数值按游戏规则换算。下方可查看每档突破消耗与专属天赋变化。',0,y,564,1000,17)
    y=y+notice.preferredHeight+16
    for level=0,9 do
        local label='+'..level..' → +'..(level+1)..'　消耗 '..mgr():MJHBreakthroughCost(level)..' 经脉点'
        if level==data.grade then label=label..'　当前可提升档位' end
        stripe(self.mjhUpgradeContent.transform,y,564,34)
        text(self,self.mjhUpgradeContent.transform,'Stage'..level,label,4,y+2,556,32,20).color=level==data.grade and U.Color(.65,.18,.12,1) or ink
        y=y+40
        local changes=mgr():MJHGrowthChanges(data.roleid,data.roledata,level)
        for _,entry in ipairs(changes) do
            local line=text(self,self.mjhUpgradeContent.transform,'Effect',entry[1]..'：'..entry[2]..' → '..entry[3],4,y,556,1000,19)
            y=y+math.max(28,line.preferredHeight)+6
        end
        y=y+12
    end
    self.mjhUpgradeContent:GetComponent('RectTransform').sizeDelta=DRCSRef.Vec2(574,y)
end
