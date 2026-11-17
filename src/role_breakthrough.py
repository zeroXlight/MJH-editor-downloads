"""Independent, transactional restoration of cross-round role breakthroughs."""
from pathlib import Path
import json,re,hashlib
STATE='装备编辑器配置/角色突破恢复.json'
BEGIN='-- MJH_ROLE_BREAKTHROUGH_2311_BEGIN'
END='-- MJH_ROLE_BREAKTHROUGH_2311_END'
def _sha(s):return hashlib.sha256(s.encode('utf8')).hexdigest()

def script(text,body,enabled,expected=None,append_only=False):
    text=text.replace('\r\n','\n').replace('\r','\n')
    if BEGIN in text or END in text:
        if text.count(BEGIN)!=1 or text.count(END)!=1:raise ValueError('角色突破脚本标记异常')
        at=text.index(BEGIN);end=text.index(END,at)+len(END)
        old=text[at:end]
        if expected and _sha(old)!=expected:raise ValueError('角色突破脚本已被外部修改，未覆盖')
        if text[end:end+1]=='\n':end+=1
        if enabled:
            # Keep this owned block in its established position. Moving it
            # past pet support on every preview changes wrapper order and
            # creates a needless resource write when both are already active.
            replacement=BEGIN+'\n'+body.strip()+'\n'+END+'\n'
            return text[:at]+replacement+text[end:]
        text=text[:at]+text[end:]
    if not enabled:return text
    matches=list(re.finditer(r'(?m)^return [A-Za-z_][A-Za-z_0-9]*;?\s*$',text))
    if append_only and not matches:return text.rstrip()+'\n'+BEGIN+'\n'+body.strip()+'\n'+END+'\n'
    if len(matches)!=1:raise ValueError('角色突破脚本导出入口不兼容')
    at=matches[0].start();return text[:at]+BEGIN+'\n'+body.strip()+'\n'+END+'\n'+text[at:]

def plan(root,enabled=True):
    from engine import DATA_ROOT
    from object_bundle import Store
    from client_config import Assets,lua_rows
    from role_breakthrough_client import patch,detach,COSTS
    from growth_runtime import patch_runtime
    from bigmap_profile import client_image,race_image
    root=Path(root).resolve();store=Store(root);a=store.assets;payloads={}
    state=root/STATE;raw=store.read(state);prior=json.loads(raw) if raw else {}
    client=root/'DreamRivakes_Data/Plugins/ClientDll.dll';race=root/'DreamRivakes_Data/Plugins/RaceLogic_Release_x64.dll'
    cr=store.read(client);rr=store.read(race)
    if not client_image(cr) or not race_image(rr):raise ValueError('角色突破目前只认证当前大地图游戏运行库；未修改文件')
    if enabled:
        curves=lua_rows(a.script('RolePiece.lua'),'RolePiece',store.enums)
        for i,c in enumerate(COSTS,1):
            row=curves.get(i,{})
            if row.get('Level')!=i or row.get('Piece',0)*500!=c or row.get('AttrAdd')!=2000*i:
                raise ValueError(f'角色突破第{i}级规则已被外部修改，请先核对；未覆盖原规则')
        from martial_editor import indexed_rows
        from codec import fields
        sources=[]
        for folder in ('TableData','DreamRivakes_Data/StreamingAssets'):
            p=root/folder/'RolePiece.bytes';data=store.read(p)
            if data is not None:sources.append((str(p),data))
        if 'RolePiece' in a.scripts:
            _,at,size=a.scripts['RolePiece'];sources.append(('内嵌RolePiece',a.data[at+4:at+4+size]))
        for name,data in sources:
            rows=indexed_rows(data)[0]
            for i,c in enumerate(COSTS,1):
                values={f.number:f.value for f in fields(rows.get(i,b'')) if f.wire==0}
                if [values.get(k) for k in (1,2,3,4)]!=[i,i,c//500,i*2000]:raise ValueError('角色突破逻辑 / 显示规则不一致：'+name)
    if not enabled and not prior and not detach(cr)[1]:raise ValueError('未检测到角色突破安装记录')
    login='''
function LoginUI:MJHOpenRoleBreakthrough()
    SendMeridiansOpr(SMOT_REFRESH_ALL,0)
    SendRequestRolePetCardOperate(RPCRT_ROLE_CARD,RPCOT_REQ_DATA,0,0)
    OpenWindowImmediately('RoleCardsUpgradeUI')
end
table.insert(tabMapSubBtn,{name='角色突破',Action='MJHOpenRoleBreakthrough',Arrow=false})
'''
    from role_breakthrough_roster import roster
    roster_lua,roster_info=roster(store)
    bodies={'LoginUI.lua':login,
        'CardsUpgradeDataManager.lua':(DATA_ROOT/'ui_assets/role_breakthrough_manager.lua').read_text('utf8'),
        'GiftDataManager.lua':(DATA_ROOT/'ui_assets/role_breakthrough_gifts.lua').read_text('utf8'),
        'InstRole.lua':(DATA_ROOT/'ui_assets/role_breakthrough_inst_gifts.lua').read_text('utf8'),
        'RoleCardsUpgradeUI.lua':(DATA_ROOT/'ui_assets/role_breakthrough.lua').read_text('utf8')+'\n'+(DATA_ROOT/'ui_assets/role_breakthrough_panels.lua').read_text('utf8')}
    bodies['CardsUpgradeDataManager.lua']=bodies['CardsUpgradeDataManager.lua'].replace('-- MJH_VISIBLE_ROLE_ROSTER',roster_lua)
    from role_breakthrough_data import prepare as prepare_growth
    growth_bodies,growth_receipt,growth_pack,growth_blobs=prepare_growth(store,enabled,prior.get('growth'),payloads)
    # Card/tree changes are independent of inventory. Weapon growth is deferred.
    for name in ('RoleCard.lua','RoleWishTree.lua'):
        if enabled or prior.get('growth'):bodies[name]=growth_bodies.get(name,'')
    if not enabled:
        bodies['CardsUpgradeDataManager.lua']='''
-- Retain account records, but do not expose their bonuses while suspended.
function CardsUpgradeDataManager:GetRoleCardLevelByRoleBaseID(id) return 0 end
local mjhOriginalEffect=CardsUpgradeDataManager.GetCurEffctStateByRoleID
function CardsUpgradeDataManager:GetCurEffctStateByRoleID(id,kind,level)
    return mjhOriginalEffect(self,id,kind,0)
end
'''
    changes={};hashes={}
    for name,body in bodies.items():
        active=enabled or name=='CardsUpgradeDataManager.lua'
        text=a.script(name);after=script(text,body,active,prior.get('scripts',{}).get(name),append_only=name in ('GiftDataManager.lua','InstRole.lua'))
        if name=='RoleCardsUpgradeUI.lua':
            before='GetSprite(v,typeof(CS.UnityEngine.Sprite))';fixed='GetSprite(v --[[MJH_ROLEBT_SPRITE]])'
            if enabled:after=after.replace(before,fixed)
            else:after=after.replace(fixed,before)
        if active:
            at=after.index(BEGIN);end=after.index(END,at)+len(END);hashes[name]=_sha(after[at:end])
        from lua_whitespace import compiler
        if not compiler()(after.encode('utf8')):raise ValueError('角色突破脚本语法检查失败：'+name)
        if after!=text:changes[name]=after.encode('utf8')
    changes.update(growth_blobs)
    p=root/'DreamRivakes_Data/resources.assets';payloads[p]=a.replace_blobs(changes)
    payloads[client]=patch(cr,enabled);payloads[race]=patch_runtime(rr,role_breakthrough=True if enabled else 2)
    payloads[state]=json.dumps(dict(version=1,enabled=enabled,scripts=hashes,card_to_meridian=500,max_level=10,stage_cap_removed=bool(enabled),client_revision=2,attribute_sync_revision=2,growth=growth_receipt),ensure_ascii=False,indent=2).encode('utf8')
    payloads={p:v for p,v in payloads.items() if store.read(p)!=v}
    results=['启用角色突破。入口：游戏主菜单 → 周目累计 → 角色突破。' if enabled else '关闭角色突破入口及突破加成，保留突破等级、已消耗资源及所有其他功能。',
        '名单按原版手游角色卡筛选，匹配当前PC人物；额外保留玩家自建角色，按编号合并候选，支持名称 / 编号查询。',
        '手游名单 '+str(roster_info['mobile_source_count'])+' 人，当前PC匹配 '+str(roster_info['mobile_present'])+' 人；自建角色 '+str(roster_info['custom_present'])+' 人。未匹配PC的手游角色不凭空新增。',
        '基础属性、天赋、默认装备与武学只读；原有配置、学习进度和装备不改动。',
        '角色突破统一最高+10，解除手游开服时间 / 剧本进度导致的+5阶段限制；保留角色、品质、余额与逐级费用检查。1张角色卡换算为500经脉点。',
        '各级消耗：'+ '、'.join(map(str,COSTS))+' 经脉点；基础属性原生加成从20%到200%。',
        '突破按对应人物编号跨周目保存；按手游先提高六项基础属性，再走原生换算，不直接倍乘最终面板、装备或后天加点。',
        '恢复可核实的默认专属天赋阶段，手动学习的天赋与存档原始编号保留；缺少PC对应实现的分支保留原效果。专属武器本轮暂缓。',
        '能力页模型下方为“升级效果”，可查十档成长；“配置”位于左下方，仍为只读详情。',
        '突破后同步当前周目已存在角色的属性缓存；窗口实时刷新等级、加成、下一级费用与经脉余额，无需重新进入。',
        '启停不回写任何存档、不补发资源、不改变宠物、经脉、六属性、武学及属性上限等其他选项。重启游戏后生效。']
    return payloads,dict(store.reads),results,[],dict(store.reads)
