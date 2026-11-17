"""Scoped restoration. Does not replace Martial, Item, AoYi or save files."""
import base64,copy,json,re
from pathlib import Path
from client_config import Assets,lua_rows
from codec import decode,fields,encoded,numeric_list
from engine import DATA_ROOT,SCHEMAS
from martial_editor import indexed_rows,patch_table,patch_lua_rows,ROW_RE
from martial_growth import growth_native

def remove_native(raw,identifiers):
    rows,index=indexed_rows(raw);index=[i for i in index if i not in identifiers]
    out=[];written=False
    for f in fields(raw):
        if f.number==1:
            if not written:out.append(numeric_list(1,index));written=True
        elif f.number==2:
            ident=next(x.value for x in fields(f.value) if x.number==1)
            if ident not in identifiers:out.append(f.raw)
        else:out.append(f.raw)
    result=b''.join(out);actual,idx=indexed_rows(result)
    if identifiers & set(actual) or idx!=index:raise ValueError('词条删除回读校验失败')
    return result

def own_ids(lib,name):
    raw=lib.originals.get(lib.own_jsons[name])
    return {int(r['BaseID']) for r in json.loads(raw.decode('utf-8-sig')).get('Items',[])} if raw else set()

def check_mod_snapshot(lib):
    directory=lib.own_jsons['Martial'].parent
    for name in ('Martial','MartialItem','MartialFilter','MatGrowUPAttrGrade','Range','MartialRange'):
        current=set(directory.glob(name+'_*.json')) if directory.exists() else set()
        expected={p for p in lib.originals if p.parent==directory and p.name.startswith(name+'_')}
        if current!=expected:raise ValueError('模组文件列表已变化，请重新读取后还原')
    mod=lib.root/'ModProject/GameProject'
    if mod.exists() and any(mod.rglob('KungfuBase_*.json')):raise ValueError('共享成长表被其他模组覆盖，未执行还原')

def apply_restore(lib,plan):
    from engine import transaction
    check_mod_snapshot(lib)
    payloads,originals,_=plan
    return transaction(lib.root,payloads,originals,'还原游戏基础词条')

def plan_restore(lib):
    if lib.modified():raise ValueError('请先保存或撤销武学草稿，再还原基础词条')
    check_mod_snapshot(lib)
    baseline=json.loads((DATA_ROOT/'clause_baseline.json').read_text(encoding='utf-8'))
    natives={n:base64.b64decode(v) for n,v in baseline['native'].items()}
    base={n:lua_rows(baseline['lua'][n],n,lib.enums) for n in ('Martial','MartialItem','MartialFilter','MatGrowUPAttrGrade')}
    for name in base:
        native_rows,_=indexed_rows(natives[name])
        for ident,raw in native_rows.items():base[name][ident]={**decode(raw,name,SCHEMAS),**base[name].get(ident,{})}
    # Refuse mismatched game data instead of applying a different version's defaults.
    known=set(base['Martial']) & set(lib.tables['Martial'])
    if len(known)<len(base['Martial'])*.95:raise ValueError('游戏基础表版本不匹配，未执行还原')
    changes={'Martial':{},'MartialItem':{},'MartialFilter':{},'MatGrowUPAttrGrade':{}}
    deletes={n:own_ids(lib,n)-set(base[n]) for n in ('MartialItem','MartialFilter','MatGrowUPAttrGrade')}
    for name in ('Range','MartialRange'):
        changes[name]={};deletes[name]=own_ids(lib,name)
    # Retained active moves or foreign ranges must never dangle after restoration.
    if any(r.get('SkillRange') in deletes['MartialRange'] for r in lib.tables['Skill'].values()):raise ValueError('主动技能直接引用了新增范围，请先改回原范围再还原基础词条')
    if any(i not in deletes['MartialRange'] and set(r.get('AttackRangeIDs',[])+r.get('AttackRangeIDs2',[])+r.get('CasterRangeIDs',[])+r.get('CasterRangeIDs2',[])) & deletes['Range'] for i,r in lib.tables['MartialRange'].items()):raise ValueError('其他范围仍引用新增格子配置，未执行还原')
    active={cid for m in lib.tables['Martial'].values() for cid in m.get('MartMovIDs',[])}
    deletes['MartialItem']-=active
    next_clause=max(1600000000,max(lib.tables['MartialItem'],default=0)+1)
    for mid,m in lib.tables['Martial'].items():
        if mid in base['Martial']:source=mid
        elif mid in own_ids(lib,'Martial'):
            source=lib.native_source(mid)
            if source not in base['Martial']:raise ValueError(f'自建武学 {lib.name(mid)}（{mid}）缺少原版模板来源，无法安全还原')
        else:
            # Third-party martial sequences are retained. Dangling refs are
            # rejected below rather than deleting someone else's content.
            continue
        original=base['Martial'][source]
        delta={k:copy.deepcopy(original.get(k,[])) for k in ('GrowProIDs','UnlockClauses','UnlockLvls')}
        if source!=mid:
            # Original self filters name the donor martial. A baseline copy
            # with filter 0 targets this new martial (kind 10), without keeping
            # authored scopes or changed attribute values. Preserve existing
            # independent skill graphs when they came from that base skill.
            skill_candidates={lib.tables['MartialItem'].get(cid,{}).get(f'SkillID{s}',0)
                              for key in ('GrowProIDs','UnlockClauses','MartMovIDs')
                              for cid in m.get(key,[]) for s in (1,2)}
            for key in ('GrowProIDs','UnlockClauses'):
                adapted=[]
                used_copies=set()
                for position,cid in enumerate(delta[key]):
                    row=copy.deepcopy(base['MartialItem'][cid]);changed=False
                    for s in (1,2):
                        n=str(s);f=base['MartialFilter'].get(row.get('MartialFilter'+n,0),{})
                        if f.get('MartialID')==source:row['MartialFilter'+n]=0;changed=True
                        sid=row.get('SkillID'+n,0)
                        target=next((i for i in sorted(skill_candidates) if lib.origins['Skill'].get(i)==sid),None) if sid else None
                        if target:row['SkillID'+n]=target;changed=True
                    if not changed:adapted.append(cid);continue
                    content={k:v for k,v in row.items() if k!='BaseID'}
                    candidates=list(m.get(key,[]))
                    if position<len(candidates):candidates=[candidates[position]]+candidates
                    reusable=next((i for i in candidates if i not in used_copies and
                                   {k:v for k,v in lib.tables['MartialItem'].get(i,{}).items() if k!='BaseID'}==content),None)
                    ident=reusable if reusable is not None else next_clause
                    if reusable is None:next_clause+=1;changes['MartialItem'][ident]=content|{'BaseID':ident}
                    deletes['MartialItem'].discard(ident);used_copies.add(ident);adapted.append(ident)
                delta[key]=adapted
        if any(m.get(k,[])!=v for k,v in delta.items()):changes['Martial'][mid]=delta
    for cid,row in base['MartialItem'].items():
        # A retained authored active move must keep its battle expressions.
        if cid in active and row.get('ItemType')==3:continue
        if row.get('ItemType') in (1,2) and lib.tables['MartialItem'].get(cid)!=row:changes['MartialItem'][cid]=row
    for name in ('MartialFilter','MatGrowUPAttrGrade'):
        for ident,row in base[name].items():
            if lib.tables[name].get(ident)!=row:changes[name][ident]=row
    # Clear added filters on retained active stages without deleting the move.
    for cid,row in lib.tables['MartialItem'].items():
        if cid in deletes['MartialItem']:continue
        delta={f'MartialFilter{s}':0 for s in (1,2) if row.get(f'MartialFilter{s}',0) in deletes['MartialFilter']}
        if delta and cid not in changes['MartialItem']:changes['MartialItem'][cid]=delta
    for name in changes:
        affected=set(changes[name])|deletes.get(name,set())
        if affected & set(lib.overrides[name]):raise ValueError(f'{name} 存在其他模组覆盖，无法安全还原；请先移除覆盖后重新读取')
    effective={n:{i:{**r,**changes[n].get(i,{})} for i,r in lib.tables[n].items() if i not in deletes.get(n,set())} for n in changes}
    for name,updates in changes.items():
        for i,r in updates.items():effective[name].setdefault(i,{'BaseID':i}).update(r)
    for mid,m in effective['Martial'].items():
        for key in ('GrowProIDs','UnlockClauses','MartMovIDs'):
            if any(cid and cid not in effective['MartialItem'] for cid in m.get(key,[])):raise ValueError(f'武学 {mid} 仍引用将删除的词条，未执行还原')
        if len(m.get('UnlockClauses',[]))!=len(m.get('UnlockLvls',[])):raise ValueError('解锁等级与词条数量不一致')
    for r in effective['MartialItem'].values():
        if any(r.get(f'MartialFilter{s}',0) and r[f'MartialFilter{s}'] not in effective['MartialFilter'] for s in (1,2)):
            raise ValueError('存在无法还原的作用范围引用')
    payloads={};originals=dict(lib.originals);assetdata=originals[lib.assets_path]
    for name,updates in changes.items():
        removed=deletes.get(name,set())
        if not updates and not removed:continue
        def native(raw):return remove_native(patch_table(raw,name,updates),removed)
        for folder in ('TableData','DreamRivakes_Data/StreamingAssets'):
            path=lib.root/folder/(name+'.bytes')
            if path.exists():
                old=originals.get(path,path.read_bytes());originals[path]=old;payloads[path]=native(old)
        a=Assets(assetdata)
        if name in a.scripts:
            _,q,n=a.scripts[name];assetdata=a.replace_blob(name,native(a.data[q+4:q+4+n]))
        for resource in lib.resources[name]:
            a=Assets(assetdata);text=a.script(resource)
            text=re.sub(ROW_RE,lambda m:'' if int(m[2]) in removed else m[0],text)
            rows={i:effective[name][i] for i in updates if lib.locations[name].get(i,lib.resources[name][0])==resource}
            if rows:text=patch_lua_rows(text,rows)
            parsed=lua_rows(text,name,lib.enums)
            if removed & set(parsed) or any(parsed.get(i)!=r for i,r in rows.items()):raise ValueError('还原客户端回读校验失败：'+name)
            assetdata=a.replace_script(resource,text)
        path=lib.own_jsons[name];old=originals.get(path);originals[path]=old
        obj=json.loads(old.decode('utf-8-sig')) if old else {'Items':[]}
        existing={int(r['BaseID']):r for r in obj.get('Items',[]) if int(r['BaseID']) not in removed}
        for i,r in updates.items():existing.setdefault(i,{}).update(copy.deepcopy(r)|{'BaseID':i})
        obj['Items']=list(existing.values())
        if old or existing:payloads[path]=json.dumps(obj,ensure_ascii=False,indent=2).encode('utf-8')
    # Restore shared per-level formula values too, keeping unrelated fields.
    from martial_growth import GrowthDraft,growth_lua
    growth=GrowthDraft(lib);originals.update(lib.originals)
    original_growth=growth_lua(baseline['lua']['KungfuBase'],lib.enums)
    growth.changes={i:r for i,r in original_growth.items() if growth.rows.get(i)!=r}
    if growth.changes:assetdata=growth.plan(lib,assetdata,payloads,originals)
    # Regenerate client labels from the restored rows, not the removed drafts.
    from martial_display import patch_client as patch_display
    restored=copy.copy(lib)
    restored.tables={**lib.tables,**effective}
    restored.changes={**lib.changes,**changes}
    a=Assets(assetdata)
    assetdata=a.replace_script('MartialDataManager.lua',patch_display(a.script('MartialDataManager.lua'),restored))
    from martial_ranges import plan as plan_ranges
    assetdata=plan_ranges(restored,assetdata,payloads,originals)
    path=lib.scope_path;originals[path]=lib.originals[path]
    if originals[path]:payloads[path]=b'{}'
    if assetdata!=originals[lib.assets_path]:payloads[lib.assets_path]=assetdata
    # Audit every read snapshot before confirmation; transaction rechecks writes.
    for path,old in originals.items():
        if (path.read_bytes() if path.exists() else None)!=old:raise ValueError('配置已变化，请重新读取：'+str(path))
    summary=(f'移除新增成长/解锁词条 {len(deletes["MartialItem"])} 条、作用范围 {len(deletes["MartialFilter"])} 条。\n'
             f'恢复 {len(changes["Martial"])} 门武学的基础成长/解锁列表；自建武学沿用原版模板。\n'
             '保留自建武学、秘奥义公式、招式动画/图标及装备实例。\n'
             '还原前自动备份，完成后请完全退出并重启游戏。')
    return payloads,originals,summary
