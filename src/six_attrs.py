"""Six-attribute profile with dormant PC rows and unchanged native save fields."""
from pathlib import Path
import json
from dataclasses import dataclass
from codec import fields,encoded,numeric_list
from client_config import Assets,enum_values
from martial_editor import indexed_rows
from engine import DATA_ROOT

BEGIN='-- MJH_SIX_ATTRS_227_BEGIN'
END='-- MJH_SIX_ATTRS_227_END'
TABLE_META=50000
TABLE_MAGIC=b'MJHSIX227INDEX\0'
IDS=set(range(10001,10015))
NAMES=['BaseID','OriAttr','Value']+sum(([f'ConvertAttr{i}',f'ConvertValue{i}'] for i in range(1,6)),[])
SOURCE='APK com.tencent.dianhun.wdxk 1.0.17 / SHA256 fa9264dd20b2b7702bbf6821640130bc0ceff28930e3f18a97b6e55dccf31ec4'
OLD_PREVIEW="        local int_temp = AttrType['ATTR_MARTIAL_ATK']\n        number_base_damagevalue = functrans(int_temp) or number_base_damagevalue"
NEW_PREVIEW=BEGIN+"\n        local mjhAttackMap={[1]=27,[2]=23,[3]=22,[4]=29,[5]=26,[7]=24,[8]=25,[9]=28}\n        local mjhAttack=mjhAttackMap[martialBaseData.DepartEnum]\n        local int_temp = mjhAttack or 99\n        number_base_damagevalue=(functrans(int_temp) or 0)+(mjhAttack and (functrans(99) or 0) or 0)\n        "+END

def mobile_rows():
    doc=json.loads((DATA_ROOT/'six_attrs_data.json').read_text('utf8'))
    if len(doc)!=14:raise ValueError('六属性原版数值文件不完整')
    return {10000+int(k):{**v,'BaseID':10000+int(k)} for k,v in sorted(doc.items(),key=lambda item:int(item[0]))}

def binary_profile(raw,enabled):
    fs=fields(raw);rows,index=indexed_rows(raw)
    meta=[f for f in fs if f.number==TABLE_META]
    if meta:
        if len(meta)!=1 or meta[0].wire!=2 or not meta[0].value.startswith(TABLE_MAGIC):raise ValueError('六属性保留数据标识不兼容')
        if index!=list(range(10001,10015)) or not IDS.issubset(rows):raise ValueError('六属性活动索引已被外部修改')
        baseline=meta[0].value[len(TABLE_MAGIC):]
        indexed_rows(baseline)
        if any(f.number==TABLE_META for f in fields(baseline)):raise ValueError('六属性保留数据不允许嵌套')
        if binary_profile(baseline,True)!=raw:raise ValueError('六属性转换数据已被其他修改覆盖，请先处理冲突')
    else:
        if IDS&set(rows):raise ValueError('六属性预留记录编号已被其他配置占用')
        baseline=raw
    if not enabled:return baseline
    fs=fields(baseline)
    active=[b''.join(encoded(j+1,r.get(k,0)) for j,k in enumerate(NAMES)) for r in mobile_rows().values()]
    return (numeric_list(1,range(10001,10015))+b''.join(encoded(2,r,2) for r in active)
            +b''.join(f.raw for f in fs if f.number!=1)+encoded(TABLE_META,TABLE_MAGIC+baseline,2))

def remove_block(text,replacement=''):
    if BEGIN not in text and END not in text:return text
    if text.count(BEGIN)!=1 or text.count(END)!=1:raise ValueError('六属性脚本标记不完整')
    a=text.index(BEGIN);b=text.index(END,a)+len(END)
    return text[:a]+replacement+text[b:]

def character_script():
    template=(DATA_ROOT/'six_attrs_character.lua').read_text('utf8').strip()
    layout=(DATA_ROOT/'six_attrs_mobile_layout.lua').read_text('utf8')
    template=template.replace('-- MJH_SIX_ATTACK_HELPER',(DATA_ROOT/'ui_assets/six_attrs_attack.lua').read_text('utf8'))
    return template.replace('local mjhMobileLayout={} -- populated from six_attrs_mobile_layout.lua',
                            'local mjhMobileLayout=(function()\n'+layout+'\nend)()')

DETAIL_BEGIN='-- MJH_MOBILE_ATTACK_LIST_228_BEGIN'
DETAIL_END='-- MJH_MOBILE_ATTACK_LIST_228_END'
DETAIL_BLOCK=DETAIL_BEGIN+'\n'+''.join('    {[AttrType.'+enum+'] = "'+label+'"},\n' for enum,label in [
    ('ATTR_JIANFAATK','剑法攻击'),('ATTR_DAOFAATK','刀法攻击'),('ATTR_QUANZHANGATK','拳掌攻击'),
    ('ATTR_TUIFAATK','腿法攻击'),('ATTR_QIMENATK','奇门攻击'),('ATTR_ANQIATK','暗器攻击'),
    ('ATTR_YISHUATK','医术攻击'),('ATTR_NEIGONGATK','内功攻击')])+DETAIL_END+'\n'

def detail_script(text,enabled):
    if DETAIL_BEGIN in text:
        if text.count(DETAIL_BEGIN)!=1 or text.count(DETAIL_END)!=1:raise ValueError('八系攻击列表标识不完整')
        a=text.index(DETAIL_BEGIN);b=text.index(DETAIL_END,a)+len(DETAIL_END)+1
        if text[a:b]!=DETAIL_BLOCK:raise ValueError('八系攻击列表被其他修改覆盖')
        if enabled:return text
        text=text[:a]+text[b:]
    if enabled:
        anchor='local array_attack = {'
        if text.count(anchor)!=1:raise ValueError('角色攻击详情列表入口不兼容')
        text=text.replace(anchor+'\n',anchor+'\n'+DETAIL_BLOCK,1)
    return text

def patch_script(name,text,enabled):
    text=text.replace('\r\n','\n').replace('\r','\n')
    if enabled and BEGIN in text:
        a=text.index(BEGIN);b=text.index(END,a)+len(END)
        current=text[a:b]
        expected=(NEW_PREVIEW if name=='MartialDataManager.lua' else
                  character_script() if name=='CharacterUI.lua' else
                  BEGIN+'\n'+(DATA_ROOT/'ui_assets/six_attrs_observe.lua').read_text('utf8').strip().replace('-- MJH_SIX_ATTACK_HELPER',(DATA_ROOT/'ui_assets/six_attrs_attack.lua').read_text('utf8'))+'\n'+END if name=='ObserveUI.lua' else None)
        if expected is not None:
            if current!=expected:
                legacy=[]
                if name=='CharacterUI.lua':
                    for version in ('227','228','229','2316'):
                        old=(DATA_ROOT/('six_attrs_character_v'+version+'.lua')).read_text('utf8').strip()
                        if version in ('228','229','2316'):
                            layout=(DATA_ROOT/'six_attrs_mobile_layout.lua').read_text('utf8')
                            old=old.replace('local mjhMobileLayout={} -- populated from six_attrs_mobile_layout.lua','local mjhMobileLayout=(function()\n'+layout+'\nend)()')
                        legacy.append(old)
                if current not in legacy:raise ValueError('六属性脚本已被其他修改覆盖：'+name)
                text=text[:a]+expected+text[b:]
            return detail_script(text,True) if name=='CharacterUI.lua' else text
        if name=='AttrTrans.lua':
            clean=remove_block(text)
            # Ignore only the separator newline when validating an installed block.
            rebuilt=patch_script(name,clean,True)
            aa=rebuilt.index(BEGIN);bb=rebuilt.index(END,aa)+len(END)
            if current!=rebuilt[aa:bb]:raise ValueError('六属性转换脚本已被其他修改覆盖')
            return text
    if name=='MartialDataManager.lua':
        text=remove_block(text,OLD_PREVIEW)
        if enabled:
            if text.count(OLD_PREVIEW)!=1:raise ValueError('武学伤害预览入口已改变，保留原脚本')
            text=text.replace(OLD_PREVIEW,NEW_PREVIEW)
    elif name=='CharacterUI.lua':
        text=detail_script(remove_block(text),enabled).rstrip()
        if enabled:
            if text.count('return CharacterUI')!=1:raise ValueError('角色界面导出入口不兼容')
            text=text.replace('return CharacterUI',character_script()+'\nreturn CharacterUI')
        text+='\n'
    elif name=='ObserveUI.lua':
        text=remove_block(text)
        if enabled:
            anchor='return ObserveUI'
            if text.count(anchor)!=1:raise ValueError('观察界面导出入口不兼容')
            block=(DATA_ROOT/'ui_assets/six_attrs_observe.lua').read_text('utf8').strip()
            block=block.replace('-- MJH_SIX_ATTACK_HELPER',(DATA_ROOT/'ui_assets/six_attrs_attack.lua').read_text('utf8'))
            text=text.replace(anchor,BEGIN+'\n'+block+'\n'+END+'\n'+anchor)
    elif name=='AttrTrans.lua':
        text=remove_block(text)
        if enabled:
            anchor='return AttrTrans'
            if text.count(anchor)!=1:raise ValueError('属性转换表导出入口不兼容')
            rows=mobile_rows()
            body='\n'.join('  ['+str(i)+']={'+','.join(k+'='+str(r.get(k,0)) for k in NAMES)+'},' for i,r in rows.items())
            block=BEGIN+'\nlocal MJHSixLegacyAttrTrans=AttrTrans\nAttrTrans={\n'+body+'\n}\n'+END+'\n'
            text=text.replace(anchor,block+anchor)
    else:raise ValueError('未知六属性脚本')
    return text

def mod_inventory(root):
    folder=root/'ModProject/GameProject'
    return tuple(sorted(p for p in folder.rglob('*') if p.is_file() and p.name.lower().startswith('attrtrans') and p.suffix.lower() in ('.json','.bytes','.lua')))

@dataclass
class SixPlan:
    root:Path
    payloads:dict
    originals:dict
    results:list
    notes:list
    reads:dict
    inventory:tuple
    def prepared(self):return self.payloads,self.originals,self.results,self.notes,self.reads

def plan(root,enabled=True,restore_forge=False,restore_martial=False):
    from shadow_runtime import require_ready
    require_ready(root)
    root=Path(root).resolve();inventory=mod_inventory(root)
    if inventory:raise ValueError('检测到外部 AttrTrans 覆盖，请先处理：'+str(inventory[0]))
    reads={};payloads={};originals={}
    # Game-file replacement leaves old six-attribute receipts behind. Apply the
    # same strictly certified reconciliation used by the big-map migration,
    # including when this standalone feature is used to disable restoration.
    from bigmap_profile import race_image
    race=root/'DreamRivakes_Data/Plugins/RaceLogic_Release_x64.dll'
    migration_report=[]
    if race_image(race.read_bytes()):
        from bigmap_data_repair import stage as repair
        pending,previous,migration_report,warnings,observed=repair(root)
        payloads.update(pending);originals.update(previous);reads.update(observed)
    def read(p,required=True):
        on_disk=p.read_bytes() if p.is_file() else None
        reads[p]=originals.get(p,on_disk)
        raw=payloads.get(p,on_disk)
        if required and raw is None:raise ValueError('缺少游戏文件：'+str(p))
        return raw
    def write(p,before,after):
        if before!=after:originals.setdefault(p,before);payloads[p]=after
    asset_path=root/'DreamRivakes_Data/resources.assets';before=read(asset_path);assets=Assets(before)
    enums=enum_values(assets.script('common.lua'))
    for name,value in [('ATTR_LIDAO',3),('ATTR_TIZHI',4),('ATTR_JINGLI',5),('ATTR_NEIJIN',6),('ATTR_LINGQIAO',7),('ATTR_WUXING',8),('ATTR_MARTIAL_ATK',145)]:
        if enums.get('AttrType.'+name)!=value:raise ValueError('属性枚举不兼容：'+name)
    for name in ('AttrTrans.lua','CharacterUI.lua','MartialDataManager.lua','ObserveUI.lua'):
        text=assets.script(name);after=patch_script(name,text,enabled)
        if text.replace('\r\n','\n').replace('\r','\n')!=after:assets=Assets(assets.replace_script(name,after))
    for p in (root/'TableData/AttrTrans.bytes',root/'DreamRivakes_Data/StreamingAssets/AttrTrans.bytes'):
        raw=read(p,p.parent.name=='TableData')
        if raw is not None:write(p,raw,binary_profile(raw,enabled))
    if 'AttrTrans' in assets.scripts:
        _,q,n=assets.scripts['AttrTrans'];raw=assets.data[q+4:q+4+n]
        after=binary_profile(raw,enabled)
        if after!=raw:assets=Assets(assets.replace_blob('AttrTrans',after))
    write(asset_path,before,assets.normalize_text_lengths())
    from growth_runtime import patch_runtime
    from six_attrs_runtime import MAGIC
    dll=root/'DreamRivakes_Data/Plugins/RaceLogic_Release_x64.dll';raw=read(dll)
    from six_attrs_points import MAGIC as POINTS_MAGIC,migration_candidates
    bootstrap=None;migration_notes=[]
    if enabled and POINTS_MAGIC not in raw:bootstrap,migration_notes=migration_candidates(root,reads)
    if enabled or MAGIC in raw:write(dll,raw,patch_runtime(raw,six_attrs=enabled,six_bootstrap=bootstrap))
    from six_attrs_options import prepare,inventory as option_inventory
    option_files=option_inventory(root)
    option_report=prepare(root,enabled,restore_forge,restore_martial,payloads,originals,reads)
    # Overlay readers observe staged bytes; the transaction must validate the
    # real files that were read before any reconciliation was staged.
    for p,raw in originals.items():
        if p in reads:reads[p]=raw
    from compatibility import validate_native_writes
    validate_native_writes(root,payloads,originals)
    state=root/'装备编辑器配置/六项属性恢复状态.json';old=read(state,False)
    doc={'format':'mjh-six-attrs-2210','enabled':enabled,'restore_forge':bool(enabled and restore_forge),'restore_martial':bool(enabled and restore_martial),'source':SOURCE,'save_format':'original','profile':'PC基础成长 + 手游六属性与精通转换；统一攻击145停用'}
    write(state,old,json.dumps(doc,ensure_ascii=False,indent=2).encode('utf8'))
    if enabled:
        results=['恢复六项属性以及武学攻击：启用。',
          '六项：力道、体质、精力、内劲、灵巧、悟性；包括全部手游 AttrTrans 衍生加成。',
          '八项精通分别转对应攻击 +10，并采用手游原表的连击／命中／暴击值转换。',
          '原有 PC 转换记录仍完整保留为未索引记录；启用期间不再参与转换。',
          '统一攻击145及其装备／成长来源完整保留；实际攻击与预览改取对应八系攻击 + 原生基础攻击99。',
          'PC 生命、真气、防御、速度的基础表及等级成长继续保留；本功能不整表替换为手游成长。',
          '原生每级5点及额外属性点机制不变；旧档余额沿用，不重复赠点，不重置已分配点数。',
          '按手游原界面恢复：角色页内两列三行六属性、原生加减按钮、剩余点数和确定按钮；长按连续加减。',
          '主面板按装备武器类型显示对应攻击，详情页列出八系攻击；待加属性及衍生加成绿色预览，确定后走原生扣点与保存。']
    else:results=['恢复六项属性以及武学攻击：关闭。','恢复保留的 PC 转换记录、统一攻击取值及客户端界面。','已分配属性、剩余点数继续保留在原生存档中；再次启用可以继续使用。']
    results+=migration_report+option_report+migration_notes+['重置退回原生记录且可核实的已分配点数；保留装备、武学和丹药等其他来源。',
              '不修改 Save.sav、SaveAI.sav、存档布局、角色或武学实例编号。',
              '重新下载资源可能覆盖部分或全部恢复文件；存档不依赖新格式，再次预览启用可修复恢复功能。',
              f'将写入 {len(payloads)} 个文件，应用时自动备份。']
    payloads={p:b for p,b in payloads.items() if b!=originals.get(p)}
    result=SixPlan(root,payloads,originals,results,[],reads,inventory)
    result.option_inventory=option_files
    return result

def apply(prepared):
    if mod_inventory(prepared.root)!=prepared.inventory:raise ValueError('外部转换表列表已变化，请重新预览')
    from six_attrs_options import inventory as option_inventory
    if option_inventory(prepared.root)!=getattr(prepared,'option_inventory',()):raise ValueError('附加恢复 MOD 文件列表已变化，请重新预览')
    from feature_save import apply as apply_files
    return apply_files(prepared.root,prepared.prepared())
