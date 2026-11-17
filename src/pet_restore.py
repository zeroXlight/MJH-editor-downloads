"""Reviewable pet restoration, retaining native saves and native assist rules."""
from dataclasses import dataclass
from pathlib import Path
import json,re
from client_config import Assets

BEGIN='-- MJH_PET_213_BEGIN'
END='-- MJH_PET_213_END'
SPRITE_FIXED='GetSprite(v --[[MJH_PET_214_RANK_SPRITE]])'
FORM_GATE_FIXED='if not instdata --[[MJH_PET_214_FORM_GATE]] then'

def fix_rank_sprite(text,enabled,prior):
    pattern=r'GetSprite\(\s*v\s*,\s*typeof\(CS\.UnityEngine\.Sprite\)\s*\)'
    matches=list(re.finditer(pattern,text))
    if len(matches)>1 or text.count(SPRITE_FIXED)>1:raise ValueError('宠物品质图片调用出现重复，未覆盖')
    if enabled and matches:
        prior['rank_sprite_original']=matches[0].group()
        return text[:matches[0].start()]+SPRITE_FIXED+text[matches[0].end():]
    if not enabled and SPRITE_FIXED in text:
        return text.replace(SPRITE_FIXED,prior.get('rank_sprite_original','GetSprite(v,typeof(CS.UnityEngine.Sprite))'))
    return text

def fix_form_gate(text,enabled,prior):
    pattern=r'if not instdata or not instdata\.unlock then'
    matches=list(re.finditer(pattern,text))
    if len(matches)>1 or text.count(FORM_GATE_FIXED)>1:raise ValueError('宠物形态入口出现重复，未覆盖')
    if enabled and matches:
        prior['form_gate_original']=matches[0].group()
        return text[:matches[0].start()]+FORM_GATE_FIXED+text[matches[0].end():]
    if not enabled and FORM_GATE_FIXED in text:
        return text.replace(FORM_GATE_FIXED,prior.get('form_gate_original','if not instdata or not instdata.unlock then'))
    return text

STATE='装备编辑器配置/宠物恢复状态.json'
PET_DATA_NATIVE='self.aiPetdata = info["Pets"] or {}\n\tself.PetsNum = info["PetsNum"] or 0'
PET_DATA_FIXED='self.aiPetdata,self.PetsNum=self:MJHPetData() -- MJH_PET_DATA_217'

def embattle_script(text,body,enabled):
    # First remove the old wrapper; then patch before native sorting/grid
    # creation consumes the pet array. Disable restores the exact native lines.
    text=block(text,'',False)
    if PET_DATA_FIXED in text:
        if text.count(PET_DATA_FIXED)!=1:raise ValueError('宠物布阵数据入口重复，未覆盖')
        if not enabled:text=text.replace(PET_DATA_FIXED,PET_DATA_NATIVE)
    elif enabled:
        if text.count(PET_DATA_NATIVE)!=1:raise ValueError('宠物布阵数据入口不兼容，未覆盖')
        text=text.replace(PET_DATA_NATIVE,PET_DATA_FIXED,1)
    return block(text,body,enabled)

def block(text,body,enabled):
    text=text.replace('\r\n','\n').replace('\r','\n')
    if BEGIN in text or END in text:
        if text.count(BEGIN)!=1 or text.count(END)!=1:raise ValueError('宠物脚本标记异常')
        a=text.index(BEGIN);b=text.index(END,a)+len(END)
        if text[b:b+1]=='\n':b+=1
        text=text[:a]+text[b:]
    if not enabled:return text
    match=list(re.finditer(r'(?m)^return [A-Za-z_][A-Za-z_0-9]*;?\s*$',text))
    if len(match)!=1:raise ValueError('宠物脚本导出入口不兼容')
    at=match[0].start()
    return text[:at]+BEGIN+'\n'+body+'\n'+END+'\n'+text[at:]

@dataclass
class PetPlan:
    root:Path
    prepared:tuple
    enabled:bool
    save_inventory:tuple

def saves(root):
    return tuple(sorted(({root/'Save.sav'} if (root/'Save.sav').is_file() else set())|
                        set((root/'SaveFile').glob('*/Save.sav'))))

def plan(root,enabled=True):
    from engine import DATA_ROOT
    from pet_rules import grant_initial
    from pet_config import binary,lua_table
    from pet_runtime import patch as patch_runtime
    from shadow_runtime import require_ready,client_supported
    require_ready(root)
    root=Path(root).resolve()
    for folder in (root/'ModProject/GameProject',root/'BepInEx/plugins'):
        for path in folder.rglob('Pet*.json'):
            if path.stem.split('_')[0] in ('Pet','PetLevel'):raise ValueError('外部宠物覆盖配置需要先处理：'+str(path))
    reads={};payloads={};originals={};notes=[];results=[]
    def read(path,required=True):
        raw=path.read_bytes() if path.is_file() else None;reads[path]=raw
        if raw is None and required:raise ValueError('缺少游戏文件：'+str(path))
        return raw
    def write(path,before,after):
        if before!=after:originals[path]=before;payloads[path]=after
    state_path=root/STATE;prior_raw=read(state_path,False)
    prior=json.loads(prior_raw) if prior_raw else {}
    path=root/'TableData/Pet.bytes';raw=read(path)
    asset_path=root/'DreamRivakes_Data/resources.assets';asset_raw=read(asset_path);assets=Assets(asset_raw);replacements={}
    if enabled:
        if not prior.get('enabled'):
            prior['pet_bytes']=raw.hex();prior['pet_lua']=assets.script('Pet.lua')
            if 'Pet' in assets.scripts:
                _,q,n=assets.scripts['Pet'];prior['pet_blob']=assets.data[q+4:q+4+n].hex()
            stream=root/'DreamRivakes_Data/StreamingAssets/Pet.bytes'
            prior['pet_stream']=read(stream,False).hex() if stream.is_file() else None
        write(path,raw,binary(raw))
        if 'Pet' in assets.scripts:
            _,offset,size=assets.scripts['Pet'];blob=assets.data[offset+4:offset+4+size]
            replacements['Pet']=binary(blob)
        stream=root/'DreamRivakes_Data/StreamingAssets/Pet.bytes'
        stream_raw=read(stream,False)
        if stream_raw is not None:write(stream,stream_raw,binary(stream_raw))
        replacements['Pet.lua']=lua_table().encode('utf8')
    elif prior.get('pet_bytes') and prior.get('pet_lua'):
        write(path,raw,bytes.fromhex(prior['pet_bytes']))
        replacements['Pet.lua']=prior['pet_lua'].encode('utf8')
        if prior.get('pet_blob') and 'Pet' in assets.scripts:
            replacements['Pet']=bytes.fromhex(prior['pet_blob'])
        stream=root/'DreamRivakes_Data/StreamingAssets/Pet.bytes'
        if prior.get('pet_stream') is not None:
            stream_raw=read(stream,False);write(stream,stream_raw,bytes.fromhex(prior['pet_stream']))
    ui=(DATA_ROOT/'ui_assets/pet_restore.lua').read_text('utf8')+'\n'+(DATA_ROOT/'ui_assets/pet_layout.lua').read_text('utf8')
    manager='''
local mjhOriginalUpgrade=CardsUpgradeDataManager.GetUpgrade
function CardsUpgradeDataManager:GetUpgrade(kind,rank)
    if kind==1 then return 10 end
    return mjhOriginalUpgrade(self,kind,rank)
end
'''
    login='''
function LoginUI:OffLineLoginAction_Pets()
    SendMeridiansOpr(SMOT_REFRESH_ALL,0)
    SendRequestRolePetCardOperate(RPCRT_PET_CARD,RPCOT_REQ_DATA,0,0)
    OpenWindowImmediately('PetCardsUpgradeUI')
end
table.insert(tabMapSubBtn,{name='宠物培养',Action='OffLineLoginAction_Pets',Arrow=false})
'''
    for name,body in [('LoginUI.lua',login),('PetCardsUpgradeUI.lua',ui),('CardsUpgradeDataManager.lua',manager)]:
        text=assets.script(name);source=fix_form_gate(fix_rank_sprite(text,enabled,prior),enabled,prior) if name=='PetCardsUpgradeUI.lua' else text;after=block(source,body,enabled)
        if text!=after:replacements[name]=after.encode('utf8')
    for name in ('RoleEmbattleUI','RoleEmbattleUINew'):
        body=(DATA_ROOT/'ui_assets/pet_embattle.lua').read_text('utf8').replace('MJHPetEmbattle',name)
        text=assets.script(name+'.lua');after=embattle_script(text,body,enabled)
        if text!=after:replacements[name+'.lua']=after.encode('utf8')
    write(asset_path,asset_raw,assets.replace_blobs(replacements,normalize=True))
    dll=root/'DreamRivakes_Data/Plugins/ClientDll.dll';raw=read(dll)
    write(dll,raw,patch_runtime(raw,enabled,lambda parent:client_supported(root,parent)))
    from growth_runtime import patch_runtime as patch_battle
    race=root/'DreamRivakes_Data/Plugins/RaceLogic_Release_x64.dll';before=read(race)
    write(race,before,patch_battle(before,pets=enabled))
    inventory=saves(root)
    if enabled:
        for path in inventory:
            before=read(path)
            try:
                after,given=grant_initial(before);write(path,before,after)
                results.append(path.parent.name+('：首次赠送30000经脉经验' if given else '：已领取首次赠送，保留余额'))
            except ValueError as error:notes.append(str(path)+' 已跳过赠送：'+str(error))
    prior['enabled']=enabled;prior['version']='2.2.18'
    write(state_path,prior_raw,json.dumps(prior,ensure_ascii=False,indent=2).encode('utf8'))
    results[:0]=['恢复宠物：'+('启用' if enabled else '关闭'),
        '恢复游戏资源保留的10类50种形态；对应属性和成长取自手游。',
        '周目累计→宠物培养；培养总览分别显示剧情、擂台当前助战加成。',
        '形态按品质解锁：1000／2000／4000／8000／16000／32000／64000经脉经验。',
        '升级费用=向上取整(1000×1.5^当前等级)；基础形态5级可解锁进阶形态，进阶初始5级。',
        '修复宠物最终伤害附加值被错误放大10000倍的问题，+7000按7000写入实战；保留原有条件、概率与成长。',
        '已修复培养界面初始化及未解锁形态被隐藏的问题；基础形态+5后，在右侧选择形态解锁，再继续培养。',
        '只有实际助战的宠物生效，同一家族不同形态互斥；未助战不提供常驻全局收益。',
        '宠物数据更新只刷新宠物列表，保留踢馆场次、门派限制及战斗上下文；取消后按原生流程通知结束，修复布阵窗口反复弹出。',
        '关闭恢复保留培养记录、已用经脉和首次赠送标记，不退回已消费资源。']
    return PetPlan(root,(payloads,originals,results,notes,reads),enabled,inventory)

def apply(value):
    if saves(value.root)!=value.save_inventory:raise ValueError('存档列表已经变化，请重新预览')
    from engine import transaction,ensure_closed
    from change_log import entry
    payloads,originals,results,notes,reads=value.prepared
    ensure_closed()
    for path,before in reads.items():
        if (path.read_bytes() if path.is_file() else None)!=before:raise ValueError('文件已经变化，请重新预览：'+str(path))
    audit=[entry('功能','恢复宠物','启用' if value.enabled else '关闭',line) for line in results+notes]
    return transaction(value.root,payloads,originals,'恢复宠物',audit_entries=audit)
