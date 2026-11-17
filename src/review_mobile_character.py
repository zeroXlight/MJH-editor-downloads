"""Execute the installed mobile-page Lua against explicit Unity test doubles."""
import json
from pathlib import Path
from lupa.lua53 import LuaRuntime
from six_attrs import character_script,patch_script,remove_block

def run(output):
    L=LuaRuntime(unpack_returned_tuples=True)
    L.execute('''
    typeof=function(v)return v end
    events={};timers={};sent={};created={}
    local function event()return {listeners={},AddListener=function(s,f)table.insert(s.listeners,f)end,RemoveAllListeners=function(s)s.listeners={}end,Invoke=function(s)for _,f in ipairs(s.listeners)do f()end end}end
    function object(name,parent)
      local o={name=name,layer=5,children={},activeSelf=true,activeInHierarchy=true,components={}}
      o.transform={gameObject=o,rect={width=349.6,height=372.67},localScale={x=1,y=1,z=1},
        anchorMin={x=0,y=0},anchorMax={x=1,y=1},pivot={x=.5,y=.5},anchoredPosition={x=0,y=0},sizeDelta={x=0,y=0}}
      o.transform.SetParent=function(t,p)
        if t.parent then for i,v in ipairs(t.parent.gameObject.children)do if v==o then table.remove(t.parent.gameObject.children,i);break end end end
        t.parent=p;if p then table.insert(p.gameObject.children,o)end
      end
      o.components.RectTransform=o.transform
      o.transform.GetSiblingIndex=function(t)
        if t.parent then for i,v in ipairs(t.parent.gameObject.children)do if v==o then return i-1 end end end;return 0
      end
      o.transform.SetSiblingIndex=function(t,index)
        if not t.parent then return end
        local a=t.parent.gameObject.children
        for i,v in ipairs(a)do if v==o then table.remove(a,i);break end end
        table.insert(a,math.min(index+1,#a+1),o)
      end
      o.GetComponent=function(s,k)return s.components[k]end
      o.transform.GetComponent=function(_,k)return o:GetComponent(k)end
      o.SetActive=function(s,v)s.activeSelf=v;s.activeInHierarchy=v end
      o.AddComponent=function(s,k)
        local c={gameObject=s,transform=s.transform,enabled=true,interactable=true,onClick=event()};s.components[k]=c
        if k=='EventTrigger' then c.triggers={Add=function(_,entry)
          events[s]=events[s] or {};events[s][entry.eventID]=function()entry.callback:Invoke()end
        end} end
        return c
      end
      if parent then o.transform:SetParent(parent.transform)end
      table.insert(created,o);return o
    end
    function find(o,path)
      local cur=o
      for part in path:gmatch('[^/]+')do
        local next
        for _,c in ipairs(cur.children)do if c.name==part then next=c;break end end
        if not next then return nil end
        cur=next
      end
      return cur
    end
    function text(parent,name)
      local go=object(name,parent);local t=go:AddComponent('Text');t.text='';return go
    end
    function button(parent,name)
      local go=object(name,parent);go:AddComponent('Button');return go
    end
    CS={UnityEngine={RectTransform='RectTransform',RectOffset=function(...)return {...}end,
      Vector2=function(x,y)return {x=x,y=y}end,Vector3=function(x,y,z)return {x=x,y=y,z=z}end,
      Color=function(...)return {...}end,Object={},Debug={LogError=function(err)lastError=err end},
      TextAnchor={UpperLeft=0,UpperCenter=1,UpperRight=2,MiddleLeft=3,MiddleCenter=4,MiddleRight=5,LowerLeft=6,LowerCenter=7,LowerRight=8},
      UI={GridLayoutGroup={Constraint={FixedColumnCount=1}},
      HorizontalLayoutGroup='HorizontalLayoutGroup',VerticalLayoutGroup='VerticalLayoutGroup',LayoutElement='LayoutElement',Text='Text',Button='Button'}}}
    CS.UnityEngine.GameObject=function(name)return object(name)end
    CS.UnityEngine.Object.Instantiate=function(o,parent)
      local function clone(src,parent)
        local go=object(src.name,parent)
        for k,c in pairs(src.components)do if k~='RectTransform' then local n=go:AddComponent(k);n.text=c.text end end
        for _,child in ipairs(src.children)do clone(child,go)end
        return go
      end
      return clone(o,parent.gameObject)
    end
    CS.UnityEngine.Object.Destroy=function(o)
      if o.gameObject then
        for k,v in pairs(o.gameObject.components)do if v==o then o.gameObject.components[k]=nil;break end end
      else o.transform:SetParent(nil);o.destroyed=true end
    end
    DRCSRef_Type={Text='Text',Button='Button'}
    DRCSRef={EventTriggerType={PointerDown=1,PointerUp=2,PointerExit=3},EventTrigger={Entry=function()return {callback=event()}end}}
    _ClassTypeof={EventTrigger='EventTrigger'}
    l_DRCSRef=DRCSRef -- lexical alias is provided by real CharacterUI.lua
    IsRogueLikeScript=function()return false end
    REI_WEAPON=0;weaponType=10
    ItemDataManager={GetInstance=function()return {GetItemTypeData=function()return {ItemType=weaponType}end}end}
    role={akEquipItem={[0]=123},uiID=1415,uiLevel=40,uiRemainAttrPoint=195,GetAttr=function(_,attr)return 1000+attr end}
    local manager={GetRoleData=function()return role end,GetCurDiffValueLimit=function()return 99999 end,
      GetMaxAttrack=function()return {enum=24,key='拳掌攻击',value=45210}end}
    RoleDataManager={GetInstance=function()return manager end}
    RoleDataHelper={GetConvertAttr=function(attrs,level)
      local r={};for a,n in pairs(attrs)do r[a]={[24]=n*10,[17]=n*50}end;return r
    end}
    EncodeSendSeGC_ClickAddAttrPoint=function(id,values)return {role=id,values=values,GetCurPos=function()return 28 end}end
    SGC_CLICK_ROLE_ADDATTRPOINT=156
    NetGameCmdSend=function(c,n,d)table.insert(sent,{command=c,size=n,data=d})end
    WaitDisplayMsg=function()end
    CharacterUI={InitAbilityNode=function()end,RefreshPoint=function()end,RefreshAbility=function()end}
    CharacterUI.FindChild=function(_,go,path)return find(go,path)end
    CharacterUI.FindChildComponent=function(_,go,path,kind)
      local child=find(go,path);assert(child,'missing component path '..path);return child:GetComponent(kind)
    end
    assert(CharacterUI.AddEventTrigger==nil) -- PC BaseWindow has no such method.
    CharacterUI.AddTimer=function(_,delay,fn)local t={delay=delay,fn=fn};timers[t]=true;return t end
    CharacterUI.RemoveTimer=function(_,t)timers[t]=nil end
    function makeSelf()
    self=setmetatable({basic_box=object('basic_box'),array_attr_due_to_point={},selectRole=1415},{__index=CharacterUI})
    local base=self.basic_box
    for _,name in ipairs({'Level','Life','Spirit'})do
      local go=object(name,base);text(go,'Text');local bar=object('Scrollbar',go);text(bar,'Value');object('Handle',object('Sliding Area',bar))
    end
    local basic=object('Basic',base)
    for _,name in ipairs({'defence','speed','NeiLi','LiDao','ActionTime'})do local row=object(name,basic);text(row,'Label');text(row,'Number')end
    local primary=object('Primary',basic);local row=object('1',primary);text(row,'Label');text(row,'Value')
    local master=object('Master',base);object('Back',master)
    for i=1,8 do local row=object(tostring(i),master);text(row,'Label');text(row,'Value')end
    local increase=object('Increase',base);text(increase,'Number');text(increase,'Value');button(increase,'Button');increase:SetActive(false)
    local point=object('Point',base);text(point,'Label');text(point,'Value');text(button(point,'Button_add'),'Text');point:SetActive(false)
    object('tips',base)
    basic:AddComponent(CS.UnityEngine.UI.GridLayoutGroup)
    master:AddComponent(CS.UnityEngine.UI.GridLayoutGroup)
    end
    makeSelf()
    LoadPrefabAndInit=function(path,parent)
      assert(path=='Module/RoleAttr_Point')
      local go=object('RoleAttr_Point',parent);text(go,'Label');text(go,'Value');button(go,'Button_add');button(go,'Button_minus');return go
    end
    ''')
    # This is the exact PC ResourcesMgr.lua global API, including argument order.
    L.execute('''
    function AddEventTrigger(objTransform,callBack,eventType)
        local eventTrigger=objTransform:GetComponent('EventTrigger')
        if eventTrigger==nil then eventTrigger=objTransform.gameObject:AddComponent(_ClassTypeof.EventTrigger)end
        eventType=eventType and eventType or DRCSRef.EventTriggerType.PointerClick
        local entry=DRCSRef.EventTrigger.Entry();entry.eventID=eventType
        entry.callback:AddListener(callBack);eventTrigger.triggers:Add(entry)
    end
    ''')
    L.execute(character_script())
    L.execute('''
    self:InitAbilityNode()
    local s=self.mjhMobileAttrs
    assert(s and not self.mjhSix,lastError)
    assert(s.attackLabel.text=='剑法攻击')
    weaponType=9;self:MJHMobileRefresh();assert(s.attackLabel.text=='刀法攻击' and s.attackValue.text=='1023')
    weaponType=29;self:MJHMobileRefresh();assert(s.attackLabel.text=='内功攻击')
    weaponType=28;self:MJHMobileRefresh();assert(s.attackLabel.text=='医术攻击')
    for weapon,attr in pairs({[9]=23,[10]=22,[11]=24,[12]=26,[13]=26,[27]=25,[29]=29})do weaponType=weapon;assert(self:MJHMobileAttack(role).enum==attr)end
    assert(s.reset and find(s.body,'Point/Reset/Text'):GetComponent('Text').text=='重置')
    assert(find(self.basic_box,'MJHMobileBasic/Point').activeSelf)
    assert(not find(s.body,'Basic/Primary').activeSelf)
    assert(s.rows[3].label.text=='力道' and s.rows[8].label.text=='悟性')
    assert(s.rows[3].label.fontSize==28 and s.rows[3].value.fontSize==24)
    assert(s.submit.interactable==false)
    assert(s.points.text=='195')
    assert(s.body.transform.localScale.x<1 and s.body.transform.localScale.x>0.6)
    for _,name in ipairs({'attack','defence','speed'})do
      local h=find(s.body,'Basic/'..name):GetComponent('HorizontalLayoutGroup')
      assert(h and h.enabled and h.spacing==0 and not h.childControlWidth and not h.childForceExpandWidth)
    end
    local expected={3,4,7,5,6,8}
    for i,a in ipairs(expected)do assert(find(s.body,'Primary/'..i..'/Label'):GetComponent('Text')==s.rows[a].label)end
    -- One native pointer press must allocate exactly one point.
    local plus=s.rows[3].plus
    events[plus.gameObject][1]();assert(s.draft[3]==1)
    events[plus.gameObject][2]();plus.onClick:Invoke();assert(s.draft[3]==1)
    assert(next(timers)==nil)
    -- Hold, then switch roles before the repeat callback: no point leaks.
    events[plus.gameObject][1]();local timer=s.timer
    self.selectRole=2008;timer.fn();self:RefreshPoint()
    assert(next(s.draft)==nil and next(timers)==nil)
    self.selectRole=1415;self:RefreshPoint()
    -- Every display position maps back to the original protocol's six slots.
    for a=3,8 do assert(self:MJHMobileChange(a,1))end
    assert(s.points.text=='189')
    assert(self.array_attr_due_to_point[24]==60)
    assert(s.rows[3].value.text:find('+1'))
    self:OnClick_Point_Submit()
    assert(#sent==1 and sent[1].command==156 and sent[1].size==28)
    for i=0,5 do assert(sent[1].data.values[i]==1)end
    self:OnClick_Point_Submit();assert(#sent==1)
    s.draft[3]=196;self:OnClick_Point_Submit();assert(#sent==1)
    self:RefreshPoint();assert(next(s.draft)==nil)
    assert(not self:MJHMobileChange(3,-1))
    events[plus.gameObject][1]();self:OnDisable();assert(next(s.draft)==nil and next(timers)==nil)
    self:MJHMobileReset();assert(#sent==2 and sent[2].data.values[0]==-2147481990)
    for i=1,5 do assert(sent[2].data.values[i]==0)end
    -- Build twice does not append another view or attach more callbacks.
    local n=#created;self:MJHMobileBuild();assert(#created==n)
    -- Fault injection before and after original controls have been reparented.
    local load=LoadPrefabAndInit
    local function signature(root)
      local out={}
      local function walk(go,path)
        local t=go:GetComponent('Text');local r=go.transform
        local g=go:GetComponent(CS.UnityEngine.UI.GridLayoutGroup)
        out[#out+1]=path..':'..tostring(go.activeSelf)..':'..(t and t.text or '')..':'..tostring(g and g.enabled)..':'..r.anchoredPosition.x..':'..r.anchoredPosition.y
        for _,c in ipairs(go.children)do walk(c,path..'/'..c.name)end
      end
      walk(root,'');return table.concat(out,'|')
    end
    for stage=1,3 do
      makeSelf();local original=signature(self.basic_box);lastError=nil
      if stage==1 then
        local count=0;LoadPrefabAndInit=function(...)count=count+1;if count==2 then error('prefab failure')end;return load(...)end
      elseif stage==2 then
        self.FindChildComponent=function(me,go,path,kind)
          if go.name=='Point' and path=='Label' then error('late point failure')end
          return CharacterUI.FindChildComponent(me,go,path,kind)
        end
      else self.MJHMobileRefresh=function()error('refresh failure')end end
      self:InitAbilityNode()
      assert(self.mjhMobileAttrs==nil and lastError)
      assert(signature(self.basic_box)==original,'original page not fully restored at stage '..stage..'\\nOLD='..original..'\\nNEW='..signature(self.basic_box))
      assert(find(self.basic_box,'MJHMobileBasic')==nil)
      LoadPrefabAndInit=load
    end
    ''')
    doc={'passed':True,'checks':['手游原生属性行预制体路径','两列三行与原生字体尺寸','嵌入角色页，无独立弹窗',
          '剩余点数、确定和重置按钮','刀剑拳棍拐杖扇按装备切换攻击','针匣兼容医术和暗器','重置使用原生退款协议','单击只加一次','长按切换角色取消','绿色属性与衍生收益预览','原生六槽156提交',
          '重复提交与超额提交拒绝','减号不退款已提交点数','关闭页面取消长按','重复构建不重复绑定',
          '使用PC原版全局AddEventTrigger真实参数顺序，禁止伪造类方法','预制体失败回退','原节点迁移后失败回退','首次刷新失败回退'],
          'limitation':'执行真实修改后Lua；Unity控件由替身提供，不等于游戏实机截图'}
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    (output/'手游角色页交互验收.json').write_text(json.dumps(doc,ensure_ascii=False,indent=2),encoding='utf8')
    return doc
