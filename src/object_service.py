"""Shared import planner used by UI and roundtrip validation."""
import copy
from object_bundle import key,sha,allocate,plan_import,normalize_owned_roles
from object_extras import import_extras
from object_runtime import finish_runtime

def prepare(store,packet,files):
    packet=normalize_owned_roles(copy.deepcopy(packet))
    from object_bundle import validate_packet
    validate_packet(packet)
    mapping={}
    from object_identity_reuse import reuse_identities
    identities=reuse_identities(packet,store,mapping,martial_names=True)
    from mobile_models import PREFIX
    for node in packet['nodes'].values():
        row=node['row']
        if node['table']=='RoleModel' and row.get('Model','').startswith(PREFIX):row['Texture']=row['Model']+'_texture'
    from mod_compatibility import native_supported
    from object_reuse import active_nodes
    can_patch=native_supported(store.root)
    if not can_patch:
        needed=active_nodes(packet,identities)
        from growth_runtime import custom_values
        from martial_ranges import AREA_START,AREA_END
        for token,node in packet['nodes'].items():
            if token not in needed:continue
            if node['table']=='MartialItem' and any(custom_values(node['row'],slot) for slot in (1,2)):
                raise ValueError('这份配置包含依赖编辑器运行库的独立成长，已跳过当前配置包导入；其他功能可继续使用')
            if node['table'] in ('Range','MartialRange') and AREA_START<=node['id']<AREA_END:
                raise ValueError('这份配置包含依赖编辑器运行库的自定义战斗范围，已跳过当前配置包导入；其他功能可继续使用')
    from object_growth_import import contextualize
    contextualize(packet,identities)
    needed=active_nodes(packet,identities)
    mapping=allocate(packet,store,defer_effects=True)|identities
    for token,values in packet['extras'].get('independent_growth',{}).items():
        cid,slot=map(int,token.split(':'))
        if key('MartialItem',cid) not in needed:continue
        if key('MartialItem',cid) in identities:continue
        if slot not in (1,2):raise ValueError('成长部位无效')
        row=packet['nodes'][key('MartialItem',cid)]['row']
        if not can_patch:
            from growth_runtime import custom_values
            if custom_values(row,slot):raise ValueError('所选配置包含必须依赖编辑器运行库的独立成长；当前仅跳过此配置包导入，其他编辑功能可继续使用')
            packet['extras'].setdefault('compatibility_warnings',[]).append('独立成长数值转换已跳过，保留目标游戏原生成长公式：'+token)
            continue
        if row.get('EffectEnum'+str(slot)) not in (7,9):raise ValueError('成长类型无效')
        from growth_runtime import MARKER
        if len(values)!=2 or values[1]!=MARKER or type(values[0]) is not int:raise ValueError('独立成长数据无效')
        row['Effect'+str(slot)+'Value']=values;row['Grade'+str(slot)]=0
    for tokenfield,entry in packet['extras'].get('images',{}).items():
        table,old,field=tokenfield.split(':');raw=files[entry['member']]
        if entry['directory']=='model_editor':
            from model_texture import PREFIX,png_bytes,template_info
            from types import SimpleNamespace
            row=packet['nodes'][key(table,int(old))]['row']
            info=template_info(SimpleNamespace(assets=store.assets,tables={'RoleModel':{1:row}}),1)
            raw=png_bytes(raw,info);files[entry['member']]=raw
            value=PREFIX+'tex_'+sha(raw)[:32]+'.png'
        else:value='#'+entry['directory']+'/'+sha(raw)+'.png'
        packet['nodes'][key(table,int(old))]['row'][field]=value
    from object_reuse import reuse_effects,active_nodes,EFFECT_TABLES
    reused=reuse_effects(packet,store,mapping,identities)
    from object_native_wishes import reuse as reuse_native_wishes
    reused.update(reuse_native_wishes(packet,store,mapping))
    active=active_nodes(packet,reused)
    pending={t:n for t,n in packet['nodes'].items() if t in active and n['table'] in EFFECT_TABLES and t not in reused}
    if pending:
        mapping.update(allocate({'nodes':pending,'role_groups':{}},store))
    # Unreachable records are pruned; keep a positive diagnostic mapping for
    # metadata lists, but they never allocate or write a target record.
    for token in mapping:
        if mapping[token]<0:mapping[token]=int(token.split(':')[1])
    packet['extras']['import_reused']=reused
    packet['extras']['import_identity_reused']={t:i for t,i in identities.items() if t.split(':')[0] in ('Martial','Gift')}
    packet['extras']['import_identity_policy']='same-id-first/same-name-combat/no-core-attrs-or-masteries/power-strict'
    if packet['kind']=='Role' and mapping[key('@Role',packet['root'])]!=packet['root']:
        old=str(packet['root']);suffix='（导入'+str(mapping[key('@Role',packet['root'])])[-6:]+'）'
        first=packet['nodes'][key('Role',packet['role_groups'][old][0])]['row']
        language=first.get('NameID') or first.get('GivennameID')
        if key('Language',language) in packet['nodes']:packet['nodes'][key('Language',language)]['row']['Ch_Text']+=suffix
        rec=packet['extras'].get('role_metadata',{}).get(old)
        if rec:rec['settings']['name']+=suffix
    payloads,originals,rows=plan_import(store,packet,mapping,active)
    import_extras(store,packet,mapping,rows,payloads,files)
    finish_runtime(store,packet,mapping,rows,payloads)
    if rows.get('Martial'):
        from martial_collection import augment
        notes=packet['extras'].setdefault('compatibility_warnings',[])
        augment(store.root,payloads,originals,notes)
    originals.update(store.reads)
    return packet,mapping,payloads,originals,rows
