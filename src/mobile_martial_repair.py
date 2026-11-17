"""Revisioned repair of editor-owned imported effects; keep IDs and progress."""
import copy,json
from pathlib import Path

def stage(store,pack,prior):
    from engine import DATA_ROOT
    from object_bundle import allocate,remap_rows
    from martial_editor import MartialLibrary
    revision=prior.get('effect_revision',1)
    name=('ui_assets/mobile_martial_revision7.json' if revision>=7 else
          'ui_assets/mobile_martial_revision6.json' if revision>=5 else 'mobile_martial_repair_baseline.json')
    baseline=json.loads((DATA_ROOT/name).read_text('utf8'))
    nodes={};edges={};oldnodes={};oldedges={}
    for mid in pack['graphs']:
        nodes.update(copy.deepcopy(pack['graphs'][mid]['nodes']));edges.update(copy.deepcopy(pack['graphs'][mid]['edges']))
    oldnodes=baseline['nodes'];oldedges=baseline['edges']
    # Recreate the previous released graph's verified native identity bindings;
    # comparing against a pre-V2.3.1 graph mistakes our own repaired rows for MODs.
    if prior.get('effect_revision',1)>=5:
        for binding in prior.get('native_identity_bindings',[]):
            source=binding['source'];path=binding['path'];native=binding['native']
            if source not in oldnodes:continue
            value=oldnodes[source]['row']
            for part in path[:-1]:value=value[part]
            value[path[-1]]=int(native.split(':')[1])
            for edge in oldedges.get(source,[]):
                if edge['path']==path:edge['target']='@Native'+native
    packet={'nodes':nodes,'edges':edges,'anchors':{t:r for g in pack['graphs'].values() for t,r in g['anchors'].items()},'role_groups':{},'extras':{}}
    from mobile_martial_identity import prepare
    prepare(packet,set(map(int,pack['graphs'])),store,{})
    nodes=packet['nodes'];edges=packet['edges']
    previous=prior['nodes'];mapping=allocate(packet,store)
    mapping.update({t:i for t,i in previous.items() if t in nodes})
    wanted={t for t in nodes if t not in previous or mapping[t] not in store.table(nodes[t]['table']) or t not in oldnodes or nodes[t]!=oldnodes[t] or edges[t]!=oldedges.get(t)}
    # Existing learning/book records remain protected. Missing functional
    # dependencies, such as a hidden follow-up skill, must be installed too.
    wanted={t for t in wanted if t not in previous or
            nodes[t]['table'] in ('SkillEffect','Buff','Language','Skill','MartialRange')}
    rows=remap_rows(packet,mapping,wanted)
    oldpacket={'nodes':oldnodes,'edges':oldedges,'role_groups':{}}
    oldmapped=remap_rows(oldpacket,previous,{t for t in wanted if t in oldnodes and t in previous})
    lib=MartialLibrary(store.root);changes=[]
    for table,records in rows.items():
        for ident,row in records.items():
            actual=store.table(table).get(ident)
            if actual==row:continue
            if actual is not None:
                expected=oldmapped.get(table,{}).get(ident)
                if expected is None or actual!=expected:
                    raise ValueError('待修复的手游效果已被其他修改改变，未写入：'+table+' '+str(ident))
            if table in lib.tables:lib.set(table,ident,row)
            changes.append(table+':'+str(ident))
    payloads,originals=lib.plan(preserve_imported=True)
    from martial_editor import patch_table,patch_lua_rows
    from client_config import Assets
    import re
    for table,records in rows.items():
        if table in lib.tables:continue
        for directory in ('TableData','DreamRivakes_Data/StreamingAssets'):
            path=store.root/directory/(table+'.bytes');raw=store.read(path)
            if raw:payloads[path]=patch_table(raw,table,records)
        path=store.root/'DreamRivakes_Data/resources.assets';assets=Assets(payloads.get(path,store.assets.data))
        if table in assets.scripts:
            _,q,n=assets.scripts[table];assets=Assets(assets.replace_blob(table,patch_table(assets.data[q+4:q+4+n],table,records)))
        for script in list(assets.scripts):
            if re.fullmatch(re.escape(table)+r'\d*\.lua',script):
                from client_config import lua_rows
                existing=lua_rows(assets.script(script),table,store.enums)
                selected={i:r for i,r in records.items() if i in existing or script==table+'.lua'}
                if selected:assets=Assets(assets.replace_script(script,patch_lua_rows(assets.script(script),selected)))
        payloads[path]=assets.data
        path=store.root/'ModProject/GameProject/Mod_MJH/Json'/f'{table}_martial_editor.json';raw=store.read(path);obj=json.loads(raw) if raw else {'Items':[]}
        byid={r['BaseID']:r for r in obj['Items']};byid.update(records);obj['Items']=list(byid.values());payloads[path]=json.dumps(obj,ensure_ascii=False,indent=2).encode('utf8')
    # Newly introduced supporting skills need their own presentation records.
    # Preserve every existing performance, including external MOD additions.
    from martial_editor import performance_blocks
    from lua_data import dump
    path=store.root/'DreamRivakes_Data/resources.assets'
    assets=Assets(payloads.get(path,store.assets.data));text=assets.script('SkillPerformance.lua')
    occupied=performance_blocks(text);entries=[]
    presentations={t:p for graph in pack['graphs'].values() for t,p in graph['performances'].items()}
    for token,performance in presentations.items():
        if token not in wanted or token in previous:continue
        ident=mapping[token]
        if ident in occupied:raise ValueError('新增手游招式动画编号被占用，未写入：'+str(ident))
        value=copy.deepcopy(performance)
        if 'id' in value:value['id']=ident
        entries.append(f'[{ident}] = '+dump(value)+',\n')
    if entries:
        match=re.search(r'\}\s*return\s+t\s*$',text)
        if not match:raise ValueError('目标招式动画表结构不兼容')
        payloads[path]=assets.replace_script('SkillPerformance.lua',text[:match.start()]+''.join(entries)+text[match.start():])
    originals.update(store.reads)
    state=copy.deepcopy(prior);state['nodes'].update({t:mapping[t] for t in nodes});state['effect_revision']=pack['revision'];state['repaired_effects']=changes
    return payloads,originals,state,changes
