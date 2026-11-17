"""Reconnect retained mobile installation records after game-file replacement."""
import copy,json,re
from pathlib import Path

def stage(root,prior,pack,payloads,originals,results):
    from object_bundle import Store,references
    from client_config import Assets,lua_rows
    from martial_editor import indexed_rows,patch_table,patch_lua_rows,performance_blocks
    from engine import SCHEMAS
    from codec import decode
    from language_routing import resource_for
    from mod_rows import read_rows
    root=Path(root);store=Store(root,payloads);owned={};warnings=[]
    directory=root/'ModProject/GameProject/Mod_MJH/Json'
    # The retained editor records are authoritative; never synthesize a missing
    # user-edited record from an older shipped graph.
    for path in sorted(directory.glob('*_martial_editor.json')):
        table=path.name.split('_',1)[0]
        if table not in SCHEMAS:continue
        raw=store.read(path)
        for row in read_rows(raw,table,SCHEMAS,warnings,path.name):
            row=copy.deepcopy(row)
            if table=='Language' and 'Text' in row:row['Ch_Text']=row.pop('Text')
            owned[table,row['BaseID']]=row
    if warnings:raise ValueError('手游恢复记录无法完整读取：'+'；'.join(warnings[:3]))
    roots={r['id'] for r in prior['installed'].values()}
    queue=[('Martial',i) for i in roots]
    queue += [('Item',i) for (t,i),r in owned.items() if t=='Item' and r.get('MartialID') in roots and r.get('ItemType') in (15,16)]
    selected={};seen=set()
    while queue:
        table,ident=queue.pop()
        if (table,ident) in seen or table.startswith('@') or table not in SCHEMAS:continue
        if table in ('Clan','Story','Role','City','Map','Task','TaskEdge','TaskEvent','Behavior'):continue
        seen.add((table,ident));row=owned.get((table,ident))
        if row is None:
            store.table(table)
            if table!='Language' and ident not in store.native[table]:
                raise ValueError('手游武学依赖缺少可核实的原生及编辑记录：'+table+' '+str(ident)+'；请先兼容大地图功能或恢复备份')
            continue
        actual=store.table(table).get(ident)
        if actual is None or any(actual.get(k)!=v for k,v in row.items()):
            raise ValueError('手游恢复记录被其他配置覆盖，未写入：'+table+' '+str(ident))
        selected.setdefault(table,{})[ident]=row
        from mobile_martial_identity import identity_edge
        for path,kind,target in references(table,row,store.enums):
            if identity_edge({'table':table,'row':row},{'path':path,'target':kind+':'+str(target)}):
                continue  # Native ownership predicates do not import another art's behavior.
            queue.append((kind,target))
    count=0;assets=store.assets.data
    for table,rows in selected.items():
        defaults=decode(b'',table,SCHEMAS);native=store.native.get(table,{})
        # Reject competing JSON definitions regardless of their sorting order.
        for path in sorted(directory.glob(table+'_*.json')):
            if path.name==table+'_martial_editor.json':continue
            for row in read_rows(store.read(path),table,SCHEMAS,[],path.name):
                wanted=rows.get(row['BaseID'])
                if wanted and any(row.get(k,defaults.get(k))!=v for k,v in wanted.items()):
                    raise ValueError('手游恢复遇到外部配置冲突：'+path.name+' '+str(row['BaseID']))
        resources=[n for n in store.assets.scripts if re.fullmatch(re.escape(table)+r'\d*\.lua',n)]
        scripts={n:lua_rows(store.assets.script(n),table,store.enums) for n in resources} if table!='Language' else {}
        changes={}
        for ident,row in rows.items():
            current=decode(native[ident],table,SCHEMAS) if ident in native else None
            correct=current is not None and all(current.get(k,defaults.get(k))==v for k,v in row.items())
            if table=='Language':
                from read_cache import language_script
                clients=[dict(language_script(store.assets.script(n))).get(ident) for n in resources]
                display=row.get('Ch_Text','') in clients
            else:display=any(ident in r and all(r[ident].get(k,defaults.get(k))==v for k,v in row.items()) for r in scripts.values())
            if not correct or not display:changes[ident]=row
        if not changes:continue
        count+=len(changes)
        for folder in ('TableData','DreamRivakes_Data/StreamingAssets'):
            path=root/folder/(table+'.bytes');raw=payloads.get(path,store.read(path))
            if raw is not None:payloads[path]=patch_table(raw,table,changes)
        a=Assets(assets)
        if table in a.scripts:
            _,q,n=a.scripts[table];assets=a.replace_blob(table,patch_table(a.data[q+4:q+4+n],table,changes))
        grouped={}
        for ident,row in changes.items():
            targets=[n for n,r in scripts.items() if ident in r]
            if table=='Language':targets=[resource_for(store.assets,ident)]
            if not targets:targets=resources[:1]
            if not targets:raise ValueError('手游恢复缺少客户端配置表：'+table)
            for name in targets:grouped.setdefault(name,{})[ident]=row['Ch_Text'] if table=='Language' else row
        for name,rows2 in grouped.items():
            a=Assets(assets);assets=a.replace_script(name,patch_lua_rows(a.script(name),rows2,table=='Language'))
    # A verified game-file replacement also removes presentation-only rows.
    # Insert missing rows; preserve every existing player-edited performance.
    a=Assets(assets);text=a.script('SkillPerformance.lua');existing=performance_blocks(text);entries=[]
    from lua_data import dump
    for mid,graph in pack['graphs'].items():
        batch=next((b for b in [*prior.get('additional_batches',[]),prior] if str(mid) in b['installed']),None)
        if batch is None:continue
        mappings=batch.get('nodes',{})
        for token,presentation in graph['performances'].items():
            ident=mappings.get(token);table=token.split(':')[0]
            if ident is None or ident in existing or ident not in selected.get(table,{}):continue
            p=copy.deepcopy(presentation)
            if 'id' in p:p['id']=ident
            entries.append(f'[{ident}] = '+dump(p)+',\n');existing[ident]=True
    if entries:
        end=re.search(r'\}\s*return\s+t\s*$',text)
        if not end:raise ValueError('手游动作表结构无法核实，未恢复')
        assets=a.replace_script('SkillPerformance.lua',text[:end.start()]+''.join(entries)+text[end.start():])
    path=root/'DreamRivakes_Data/resources.assets'
    if assets!=store.assets.data:payloads[path]=assets
    from growth_runtime import patch_runtime
    path=root/'DreamRivakes_Data/Plugins/RaceLogic_Release_x64.dll';raw=payloads.get(path,store.read(path));updated=patch_runtime(raw)
    if updated!=raw:payloads[path]=updated
    for p in store.reads:originals.setdefault(p,p.read_bytes() if p.exists() else None)
    # Reconnect additive evolution/shop pools and the native copying flag;
    # never restore an old full Clan/Story row over new-map configuration.
    from mobile_martial_acquisition import reconnect
    reconnect(Store(root,payloads),payloads,originals,prior['installed'])
    if count or entries:results.append(f'重新同步 {count} 条已安装手游武学配置及 {len(entries)} 条缺失动作记录；保留编号及已有进度。')
