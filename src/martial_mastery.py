"""Restore native mastery growth in synchronized logic, client and MOD tables."""
import copy
import json
from dataclasses import dataclass
from pathlib import Path

from client_config import Assets, lua_rows
from codec import decode, fields, encoded
from engine import SCHEMAS
from martial_editor import indexed_rows, patch_lua_rows, patch_table, encode_field, RANKS, DEPARTS
from martial_growth import growth_native, growth_lua
from object_bundle import Store

# depart: (attribute, existing ordinary growth clause)
MASTERY = {7:(9,52515),3:(10,52525),2:(11,52535),8:(12,52545),
           5:(13,52555),1:(14,52565),9:(15,50162),4:(16,52575)}
DEFAULT_GOLD = 12
DEFAULT_DARK_GOLD = 18


def mod_files(root):
    directory = root/'ModProject/GameProject/Mod_MJH/Json'
    return tuple(sorted(p for name in ('Martial','MartialItem','KungfuBase')
                        for p in directory.glob(name+'_*.json')))


def native_rows(raw,name):
    return growth_native(raw) if name=='KungfuBase' else indexed_rows(raw)[0]


def patch_native(raw,name,deltas):
    if name!='KungfuBase':return patch_table(raw,name,deltas)
    ids=list(growth_native(raw));position=0;out=[]
    for f in fields(raw):
        if f.number!=2:out.append(f.raw);continue
        ident=ids[position];position+=1
        if ident not in deltas:out.append(f.raw);continue
        keep=b''.join(x.raw for x in fields(f.value) if x.number!=5)
        out.append(encoded(2,keep+encode_field('RankDatas',deltas[ident]['RankDatas'],name),2))
    return b''.join(out)


@dataclass
class MasteryPlan:
    root: Path
    payloads: dict
    originals: dict
    results: list
    notes: list
    reads: dict
    mods: tuple

    def prepared(self):
        return self.payloads,self.originals,self.results,self.notes,self.reads


def choose_changes(martials, clauses, formulas, gold, dark_gold):
    """Pure selection: preserve existing/custom growth, add absent native links."""
    adjust=gold is not None or dark_gold is not None
    for value in (gold,dark_gold):
        if adjust and (type(value) is not int or not 1 <= value <= 1000):
            raise ValueError('每级精通请输入 1～1000 的整数')
    changes={}; notes=[]; results=[]; counts={6:0,7:0}; existing={6:0,7:0}
    for ident,m in sorted(martials.items()):
        rank=m.get('Rank');depart=m.get('DepartEnum')
        if rank not in counts:continue
        if m.get('Display',1)!=1 or not 10<=m.get('LvLimit',10)<=1000:continue
        if depart not in MASTERY:continue
        attr,clause=MASTERY[depart];ids=m.get('GrowProIDs',[])
        if any(cid not in clauses for cid in ids):
            notes.append(f'武学 {ident}：成长词条依赖缺失，跳过补回，保留原配置。');continue
        if any(clauses[cid].get('EffectEnum'+str(slot))==7 and
               clauses[cid].get('AttrEnum'+str(slot))==attr
               for cid in ids for slot in (1,2)):
            existing[rank]+=1;continue
        c=clauses.get(clause,{})
        if (c.get('EffectEnum1')!=7 or c.get('AttrEnum1')!=attr or c.get('CondID',0)
            or c.get('MartialFilter1',0) or c.get('EffectEnum2',0)
            or len(c.get('Effect1Value',[]))!=1):
            raise ValueError('原生精通成长模板不兼容：'+str(clause))
        changes[ident]={'GrowProIDs':[clause]+list(ids)};counts[rank]+=1
        results.append(f'{RANKS[rank]}武学 {ident}（{DEPARTS[depart]}）：补回精通成长词条 {clause}')
    growth={}
    for attr in range(9,17):
        ident=49152+attr;r=formulas.get(ident)
        if (not r or r.get('AttrType')!=attr or r.get('KfType')!=0 or
            r.get('IsRoleAttr')!=1 or r.get('IsGrowup')!=1 or len(r.get('RankDatas',[]))<8):
            raise ValueError('无法确认原生精通成长公式：'+str(ident))
        values=list(r['RankDatas']);old=(values[6],values[7])
        if adjust:values[6]=gold;values[7]=dark_gold
        if values!=r['RankDatas']:growth[ident]={'RankDatas':values}
        results.append(f'精通属性 {attr}：金色每级 +{old[0]} → +{values[6]}；暗金每级 +{old[1]} → +{values[7]}')
    results[:0]=[f'恢复武学精通：金色每级 +{gold}，暗金每级 +{dark_gold}。' if adjust else '恢复武学精通：仅补回缺失词条，保留当前每级精通数值（不改成长公式）。',
                f'补回金色 {counts[6]} 门、暗金 {counts[7]} 门；已有对应成长 {sum(existing.values())} 门保持词条不变。',
                '作用于八类普通可训练武学；轻功、阵法、登场技及隐藏／不可训练武学不自动添加。',
                '共享原生成长采用所选数值；已有独立成长数值及条件保持原样。' if adjust else '保留当前共享成长和独立成长数值；可另行勾选调整每级精通。',
                '旧档、新档读取后按现有武学等级计算；不修改已学等级、残章或突破进度。']
    return {'Martial':changes,'KungfuBase':growth},results,notes


def plan(root, gold=None, dark_gold=None):
    root=Path(root).resolve();inventory=mod_files(root);store=Store(root)
    from feature_fields import state as switch_state,mobile_growth
    switches=switch_state(root);dormant=mobile_growth(switches)
    martials=copy.deepcopy(store.table('Martial'));clauses=store.table('MartialItem')
    for ident,e in dormant.items():
        if ident in martials:martials[ident]['GrowProIDs']=copy.deepcopy(e['on'])
    formula_mods=list((root/'ModProject/GameProject').rglob('KungfuBase_*.json'))
    if formula_mods:raise ValueError('检测到外部成长表 MOD 覆盖，请先同步或移除覆盖后再恢复精通：'+formula_mods[0].name)
    formula_path=root/'TableData/KungfuBase.bytes'
    store.native['KungfuBase']=growth_native(store.read(formula_path))
    formulas=growth_lua(store.assets.script('KungfuBase.lua'),store.enums)
    if getattr(store,'mod_warnings',[]):
        raise ValueError('武学／成长 MOD 含有无法解析的记录，请先修复：'+'；'.join(store.mod_warnings[:3]))
    changes,results,notes=choose_changes(martials,clauses,formulas,gold,dark_gold)
    payloads={};originals={};assets=store.assets
    # Native growth must match its client definition: do not silently replace
    # unknown formulas or let description and actual settlement diverge.
    for ident in range(49161,49169):
        raw=store.native['KungfuBase'].get(ident)
        if raw is None:raise ValueError('逻辑成长公式缺失：'+str(ident))
        if decode(raw,'KungfuBase',SCHEMAS)!=formulas[ident]:
            raise ValueError('逻辑／显示／MOD成长公式不同步，请先同步：'+str(ident))
    used={cid for delta in changes['Martial'].values() for cid in delta['GrowProIDs'][:1]}
    for cid in used:
        raw=store.native['MartialItem'].get(cid)
        if raw is None or decode(raw,'MartialItem',SCHEMAS)!=clauses[cid]:
            raise ValueError('精通成长模板逻辑与显示不同步：'+str(cid))
    for name,deltas in changes.items():
        if name=='Martial' and dormant:
            for ident,delta in deltas.items():
                if ident in dormant:dormant[ident]['on']=copy.deepcopy(delta['GrowProIDs'])
            deltas={i:d for i,d in deltas.items() if i not in dormant}
        if not deltas:continue
        path=root/'TableData'/f'{name}.bytes';before=store.read(path)
        after=patch_native(before,name,deltas)
        check=native_rows(after,name)
        for ident,delta in deltas.items():
            row=decode(check[ident],name,SCHEMAS)
            if any(row.get(k)!=v for k,v in delta.items()):raise ValueError('逻辑表回读失败')
        if after!=before:payloads[path]=after;originals[path]=before
        # Synchronize every server/client copy used by this installation.
        streaming=root/'DreamRivakes_Data/StreamingAssets'/f'{name}.bytes'
        raw=store.read(streaming)
        if raw is not None:
            out=patch_native(raw,name,deltas)
            if out!=raw:payloads[streaming]=out;originals[streaming]=raw
        if name in assets.scripts:
            _,q,n=assets.scripts[name];raw=assets.data[q+4:q+4+n]
            assets=Assets(assets.replace_blob(name,patch_native(raw,name,deltas)))
        remaining=set(deltas)
        import re
        resources=[n for n in assets.scripts if re.fullmatch(re.escape(name)+r'\d*\.lua',n)]
        for resource in resources:
            text=assets.script(resource)
            rows=growth_lua(text,store.enums) if name=='KungfuBase' else lua_rows(text,name,store.enums)
            updated={i:{**rows[i],**deltas[i]} for i in deltas if i in rows}
            if not updated:continue
            out=patch_lua_rows(text,updated)
            parsed=growth_lua(out,store.enums) if name=='KungfuBase' else lua_rows(out,name,store.enums)
            if any(parsed[i]!=r for i,r in updated.items()):raise ValueError('显示表回读失败')
            assets=Assets(assets.replace_script(resource,out));remaining-=set(updated)
        if remaining:raise ValueError('客户端缺少待恢复的武学／成长记录：'+str(sorted(remaining)[:8]))
        for path in inventory:
            if not path.name.startswith(name+'_'):continue
            raw=store.read(path)
            try:obj=json.loads(raw.decode('utf-8-sig'))
            except (ValueError,UnicodeError) as error:raise ValueError('MOD 无法读取：'+path.name) from error
            rows=obj.get('Items') if isinstance(obj,dict) else obj
            if not isinstance(rows,list):raise ValueError('MOD 表格式不支持：'+path.name)
            changed=False
            for row in rows:
                delta=deltas.get(row.get('BaseID'))
                if delta and any(row.get(k)!=v for k,v in delta.items()):row.update(copy.deepcopy(delta));changed=True
            if changed:
                after=json.dumps(obj,ensure_ascii=False,indent=2).encode('utf-8')
                payloads[path]=after;originals[path]=raw
    asset_path=root/'DreamRivakes_Data/resources.assets'
    if changes['Martial'] or changes['KungfuBase']:
        after=assets.normalize_text_lengths()
        if after!=store.read(asset_path):payloads[asset_path]=after;originals[asset_path]=store.read(asset_path)
    results.insert(2,f'将写入 {len(payloads)} 个配置文件；预览尚未修改游戏。')
    from feature_fields import mastery_entries,state as field_state,STATE as FIELD_STATE
    receipt=root/'装备编辑器配置/武学精通恢复记录.json';old_receipt=store.read(receipt)
    remembered=mastery_entries(store)[0]
    bykey={(e['table'],e['id'],e['field'],e.get('index')):e for e in remembered}
    for ident,delta in changes['Martial'].items():
        key=('Martial',ident,'GrowProIDs',None)
        e=bykey.setdefault(key,dict(table='Martial',id=ident,field='GrowProIDs',off=copy.deepcopy(martials[ident]['GrowProIDs'])))
        e['on']=copy.deepcopy(delta['GrowProIDs'])
    for ident,delta in changes['KungfuBase'].items():
        for index in (6,7):
            key=('KungfuBase',ident,'RankDatas',index)
            e=bykey.setdefault(key,dict(table='KungfuBase',id=ident,field='RankDatas',index=index,off=formulas[ident]['RankDatas'][index]))
            e['on']=delta['RankDatas'][index]
    raw=json.dumps(dict(version=1,entries=list(bykey.values())),ensure_ascii=False,indent=2).encode('utf8')
    if raw!=old_receipt:payloads[receipt]=raw;originals[receipt]=old_receipt
    doc=switches
    if doc['features'].get('mastery',{}).get('suspended'):
        doc['features']['mastery']['suspended']=False
    if doc['features'].get('mastery'):
        doc['features']['mastery']['entries']=list(bykey.values())
    if dormant or doc['features'].get('mastery'):
        p=root/FIELD_STATE;originals[p]=store.read(p);payloads[p]=json.dumps(doc,ensure_ascii=False,indent=2).encode('utf8')
    return MasteryPlan(root,payloads,originals,results,notes,store.reads,inventory)


def apply(prepared):
    if mod_files(prepared.root)!=prepared.mods:raise ValueError('MOD 文件列表已变化，请重新预览')
    from feature_save import apply as apply_files
    return apply_files(prepared.root,prepared.prepared())
