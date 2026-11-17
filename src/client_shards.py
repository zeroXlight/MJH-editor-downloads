"""Read split client tables and reconcile proven editor migration duplicates."""
import copy,json,re
from client_config import lua_rows,Assets

def names(assets,table):
    return sorted((n for n in assets.scripts if re.fullmatch(re.escape(table)+r'\d*\.lua',n)),key=lambda n:int(re.search(r'(\d+)\.lua$',n)[1]) if re.search(r'(\d+)\.lua$',n) else -1)

def normalize_role(row,mapping):
    out=copy.deepcopy(row)
    if 'Kungfu' in out:out['Kungfu']=[mapping.get(i,i) for i in out['Kungfu']]
    return out

def repair_roles(assets,mapping,enums):
    """Only remove duplicates proven equivalent by the recorded ID migration.

    Keep the original numbered shard, preserve all other fields and scripts.
    Conflicting external records are left intact for read-only handling.
    """
    from martial_editor import patch_lua_rows,ROW_RE
    groups={};scripts={};count=0
    for resource in names(assets,'Role'):
        rows=lua_rows(assets.script(resource),'Role',enums)
        for ident,row in rows.items():groups.setdefault(ident,[]).append((resource,row))
    for ident,entries in groups.items():
        if len(entries)<2:continue
        normalized=[normalize_role(r,mapping) for _,r in entries]
        if not any(r!=n for (_,r),n in zip(entries,normalized)):continue
        if any(r!=normalized[0] for r in normalized[1:]):continue
        target,row=entries[-1]
        text=scripts.get(target,assets.script(target))
        scripts[target]=patch_lua_rows(text,{ident:normalized[0]})
        for resource,_ in entries[:-1]:
            text=scripts.get(resource,assets.script(resource))
            scripts[resource]=re.sub(ROW_RE,lambda m:'' if int(m[2])==ident else m[0],text)
        count+=1
    return scripts,count

def prepare(owner):
    path=owner.root/'装备编辑器配置/武学安全编号迁移.json'
    raw=path.read_bytes() if path.exists() else None;owner.originals.setdefault(path,raw)
    mapping={int(k):v for k,v in json.loads(raw.decode('utf8')).items()} if raw else {}
    owner.client_repairs,count=repair_roles(owner.assets,mapping,owner.enums)
    owner.client_rows_seen={};owner.client_duplicate_locations={}
    for resource,text in owner.client_repairs.items():owner.assets=Assets(owner.assets.replace_script(resource,text))
    if count:owner.mod_warnings.append(f'已识别并修正 {count} 条编号迁移产生的人物分表重复；保存后应用到游戏')

def merge(owner,table,resource,rows):
    seen=getattr(owner,'client_rows_seen',{})
    owner.client_rows_seen=seen
    originals=seen.setdefault(table,{})
    for ident,row in rows.items():
        previous=owner.locations[table].get(ident)
        if previous:
            if originals[ident]==row:
                duplicates=getattr(owner,'client_duplicate_locations',{})
                owner.client_duplicate_locations=duplicates
                duplicates.setdefault(table,{}).setdefault(ident,[previous]).append(resource)
                owner.mod_warnings.append(f'{table}:{ident} 在 {previous}、{resource} 重复，已合并相同记录')
            else:
                owner.overrides[table].setdefault(ident,[]).extend([previous,resource])
                owner.mod_warnings.append(f'{table}:{ident} 在客户端分表冲突，保留读取，跳过此记录的编辑')
            continue
        owner.locations[table][ident]=resource
        originals[ident]=copy.deepcopy(row)
        owner.tables[table].setdefault(ident,{}).update(row)

def targets(owner,table,ident,primary):
    return getattr(owner,'client_duplicate_locations',{}).get(table,{}).get(ident,[primary])

def staged(owner,raw):
    for resource,text in getattr(owner,'client_repairs',{}).items():raw=Assets(raw).replace_script(resource,text)
    return raw
