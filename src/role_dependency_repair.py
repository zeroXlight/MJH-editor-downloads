"""Synchronize proven editor-owned dependencies, without copying native plots."""
import copy,json,re
from pathlib import Path
from codec import decode,fields
from engine import SCHEMAS
from client_config import Assets,lua_rows,enum_values
from martial_editor import indexed_rows,encode_field,patch_table,patch_lua_rows

ALLOWED={'Martial','MartialItem','MartialFilter','Skill','SkillEffect','SuperImposed','Buff','Gift','Item','Language','MatGrowUPAttrGrade','AoYi','Range','MartialRange'}

def normal(name,row):
    row=dict(row)
    if name=='Language' and 'Text' in row:row['Ch_Text']=row.pop('Text')
    return decode(b''.join(encode_field(k,v,name) for k,v in row.items() if k in SCHEMAS[name]),name,SCHEMAS)

def inspect(lib,overlay=None):
    from object_bundle import Store,references
    store=Store.__new__(Store);store.root=lib.root;store.overlay=overlay or {};store.reads=dict(lib.originals)
    store.assets=Assets(store.overlay[lib.assets_path]) if lib.assets_path in store.overlay else lib.assets
    store.enums=lib.enums|{'False':0,'True':1};store.tables={};store.native={}
    directory=lib.root/'ModProject/GameProject/Mod_MJH/Json'
    lib.dependency_json_files=set(directory.glob('*.json'))
    path=lib.root/'装备编辑器配置/人物编辑.json';raw=store.read(path)
    if not raw:return {},{}
    metadata=json.loads(raw.decode('utf8'));wanted={};seen=set();queue=[]
    roleids={int(rid) for rid in metadata if rid.isdecimal()}
    queue.extend(('Role',i) for i,row in store.table('Role').items() if row.get('RoleID') in roleids)
    while queue:
        name,ident=queue.pop()
        if (name,ident) in seen:continue
        seen.add((name,ident))
        if len(seen)>30000:raise ValueError('人物依赖超过安全读取范围')
        row=store.table(name).get(ident)
        if row is None:continue # Never invent missing original plot/resources.
        if name in ALLOWED:wanted.setdefault(name,set()).add(ident)
        for _,target,value in references(name,row,store.enums):
            if target in ALLOWED:queue.append((target,int(value)))
    repairs={}
    for name,ids in wanted.items():
        owned={};foreign=set()
        paths=set(directory.glob(name+'_*.json'))|{p for p in store.overlay if p.parent==directory and p.name.startswith(name+'_') and p.suffix=='.json'}
        for p in sorted(paths):
            data=store.read(p)
            from mod_rows import read_rows
            warnings=[];records=read_rows(data,name,SCHEMAS,warnings,p.name)
            lib.mod_warnings.extend('人物依赖检查：'+message for message in warnings)
            isown=p.name in (name+'_martial_editor.json',name+'_role_editor.json','Item_warehouse_editor.json')
            for row in records:
                ident=row.get('BaseID')
                if ident not in ids:continue
                if isown:owned.setdefault(ident,[]).append(dict(row))
                else:foreign.add(ident)
        if not owned:continue
        sources=[]
        for folder in ('TableData','DreamRivakes_Data/StreamingAssets'):
            p=lib.root/folder/(name+'.bytes');data=store.read(p)
            if data:sources.append({i:decode(v,name,SCHEMAS) for i,v in indexed_rows(data)[0].items() if i in owned})
        if name in store.assets.scripts:
            _,q,n=store.assets.scripts[name];sources.append({i:decode(v,name,SCHEMAS) for i,v in indexed_rows(store.assets.data[q+4:q+4+n])[0].items() if i in owned})
        client={}
        for resource in store.assets.scripts:
            if not re.fullmatch(name+r'\d*\.lua',resource):continue
            if name=='Language':
                from read_cache import language_script
                values={i:normal(name,((sources[0].get(i,{}) if sources else {}) | {'BaseID':i,'Ch_Text':v})) for i,v in language_script(store.assets.script(resource)) if i in owned}
            else:
                values={}
                for i,v in lua_rows(store.assets.script(resource),name,store.enums).items():
                    if i not in owned:continue
                    from client_only_fields import without_empty_defaults
                    v=without_empty_defaults(name,v)
                    if set(v)-set(SCHEMAS[name]):raise ValueError(f'人物依赖包含未知客户端字段，未覆盖：{name} {i}')
                    values[i]=normal(name,v)
            for i,row in values.items():client.setdefault(i,[]).append(row)
        for ident,entries in owned.items():
            overlay={}
            for entry in entries:
                from client_only_fields import without_empty_defaults
                entry=without_empty_defaults(name,entry)
                unknown=set(entry)-set(SCHEMAS[name])-({'Text'} if name=='Language' else set())
                if unknown:raise ValueError(f'人物依赖包含未知编辑字段，未覆盖：{name} {ident}')
                for key,value in entry.items():
                    if key in overlay and overlay[key]!=value:raise ValueError(f'人物依赖存在多个编辑记录冲突：{name} {ident}')
                    overlay[key]=value
            # Retained JSON can own only two fields of a native expression.
            # Missing keys are not instructions to zero its original fields.
            base=next((s[ident] for s in sources if ident in s),None)
            if base is None:base=next(iter(client.get(ident,[])),None)
            if base is None:
                required={'SkillEffect':'Name','Skill':'Type','Item':'ItemType','Gift':'NameID','Martial':'NameID'}.get(name)
                if required and required not in overlay:raise ValueError(f'人物依赖只剩局部编辑记录，缺少完整定义，未伪造：{name} {ident}')
                base={}
            row=normal(name,base | overlay)
            actual=[s.get(ident) for s in sources]+client.get(ident,[None])
            if all(v==row for v in actual):continue
            if ident in foreign:raise ValueError(f'人物依赖存在外部MOD覆盖，未恢复：{name} {ident}')
            blank=decode(b'',name,SCHEMAS);blank['BaseID']=ident
            complete_native=bool(sources and sources[0].get(ident)==row)
            for v in actual:
                partial=complete_native and v is not None and all(value==blank.get(k) or value==row.get(k) for k,value in v.items())
                if v is not None and v!=row and v!=blank and not partial:
                    diff={k:(v.get(k),row.get(k)) for k in set(v)|set(row) if v.get(k)!=row.get(k)}
                    raise ValueError(f'人物依赖存在未知改动，未覆盖：{name} {ident}；差异：{diff}')
            repairs.setdefault(name,{})[ident]=row
    if set(directory.glob('*.json'))!=lib.dependency_json_files:raise ValueError('人物依赖文件列表在读取时变化，请刷新配置')
    return repairs,store.reads

def stage(lib,payloads,originals):
    repairs=getattr(lib,'dependency_repairs',{})
    changed_draft=lib.meta!=lib.meta_before
    if not repairs and not changed_draft:return
    directory=lib.root/'ModProject/GameProject/Mod_MJH/Json'
    if set(directory.glob('*.json'))!=lib.dependency_json_files:raise ValueError('人物依赖文件列表在预览后变化，请重新读取')
    for path in lib.dependency_paths:
        before=lib.originals[path]
        if (path.read_bytes() if path.exists() else None)!=before:raise ValueError('人物依赖配置在预览后变化，请重新读取：'+str(path))
        originals.setdefault(path,before)
    if changed_draft:
        # Inspect the final draft graph, including newly created characters.
        # Store.read still records physical disk bytes separately from overlay.
        repairs,reads=inspect(lib,payloads)
        for path,before in reads.items():
            if (path.read_bytes() if path.exists() else None)!=before:raise ValueError('人物依赖配置在预览后变化，请重新读取：'+str(path))
            originals.setdefault(path,before)
        if not repairs:return
    data=payloads.get(lib.assets_path,lib.originals[lib.assets_path])
    for name,rows in repairs.items():
        rows={i:r for i,r in rows.items() if i not in lib.changes.get(name,{})}
        if not rows:continue
        for folder in ('TableData','DreamRivakes_Data/StreamingAssets'):
            path=lib.root/folder/(name+'.bytes');before=originals.get(path)
            if before:
                current=payloads.get(path,before);existing=indexed_rows(current)[0]
                changed={i:r for i,r in rows.items() if i not in existing or decode(existing[i],name,SCHEMAS)!=r}
                if changed:payloads[path]=patch_table(current,name,changed,{})
        a=Assets(data)
        if name in a.scripts:
            _,q,n=a.scripts[name];current=data[q+4:q+4+n];existing=indexed_rows(current)[0]
            changed={i:r for i,r in rows.items() if i not in existing or decode(existing[i],name,SCHEMAS)!=r}
            if changed:data=a.replace_blob(name,patch_table(current,name,changed,{}))
        a=Assets(data);names=sorted(n for n in a.scripts if re.fullmatch(name+r'\d*\.lua',n));grouped={}
        for i,row in rows.items():
            targets=[]
            for n in names:
                pattern=rf'(?m)^\s*\[{i}\]\s*='
                if re.search(pattern,a.script(n)):targets.append(n)
            if not targets:
                from language_routing import resource_for
                targets=[resource_for(a,i) if name=='Language' else names[0]]
            for n in targets:grouped.setdefault(n,{})[i]=row['Ch_Text'] if name=='Language' else {k:v for k,v in row.items() if v!={}}
        for n,replacements in grouped.items():
            a=Assets(data);text=a.script(n)
            lib.enums.update(enum_values(text))
            if name=='Language':
                from read_cache import language_script
                existing=dict(language_script(text));changed={i:v for i,v in replacements.items() if existing.get(i)!=v}
            else:
                existing=lua_rows(text,name,lib.enums)
                changed={i:v for i,v in replacements.items() if i not in existing or normal(name,existing[i])!=normal(name,v)}
            if changed:data=a.replace_script(n,patch_lua_rows(text,changed,name=='Language'))
    payloads[lib.assets_path]=data
    lib.mod_warnings.append('已恢复人物关联武学、天赋、装备及词条的缺失逻辑／界面配置；已有存档中未曾生成的装备需单独补回，不重置学习进度。')
