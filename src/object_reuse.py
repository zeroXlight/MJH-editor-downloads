"""Reuse equivalent effects after resolving typed dependencies, never identities.

Equality excludes labels only. All effect fields, restrictions, trigger order
and referenced effects must match. Cyclic gift/group links are checked together.
"""
import copy,json
from object_bundle import key,references

EFFECT_TABLES={'MartialItem','MartialFilter','Range','MartialRange','Gift','Buff','SuperImposed','SkillEffect','Condition'}
LABELS={'BaseID','NameID','DescID','DesID'}

def signature(row):
    return json.dumps({k:v for k,v in row.items() if k not in LABELS},sort_keys=True,ensure_ascii=False,separators=(',',':'))

def reuse_effects(packet,store,mapping,identities=None):
    reused=dict(identities or {});indexes={}
    for table in EFFECT_TABLES:
        if table=='Gift':continue # Gifts use original-ID, whole-graph checks.
        if not any(n['table']==table for n in packet['nodes'].values()):continue
        index={}
        for ident,row in sorted(store.table(table).items()):index.setdefault(signature(row),[]).append(ident)
        indexes[table]=index
    def labels_available(token,other):
        node=packet['nodes'][token]
        if node['table']=='SkillEffect' and node['row'].get('Name') in (451,537):
            from martial_editor import performance_blocks
            from lua_data import parse
            timing=performance_blocks(store.assets.script('SkillPerformance.lua')).get(other['BaseID'])
            a=copy.deepcopy(packet['extras'].get('effect_performance',{}).get(str(node['id'])))
            b=parse(timing[2]) if timing else None
            if isinstance(a,dict):a.pop('id',None)
            if isinstance(b,dict):b.pop('id',None)
            if a!=b:return False
        # Reusing an effect also keeps its target-side labels. Do not discard
        # a supplied text repair by reusing a row whose label is still missing.
        for edge in packet['edges'][token]:
            if edge['path'][0] not in LABELS or not edge['target'].startswith('Language:') or edge['target'] not in packet['nodes']:continue
            value=other.get(edge['path'][0],0)
            if value not in store.table('Language'):return False
        return True
    # A parent becomes comparable once its children have been reused. Each
    # successful pass reduces the unresolved set, giving a finite bound.
    for _ in range(len(packet['nodes'])+1):
        changed=False
        for token,node in packet['nodes'].items():
            if token in reused or node['table'] not in indexes:continue
            row=copy.deepcopy(node['row'])
            for edge in packet['edges'][token]:
                obj=row
                for part in edge['path'][:-1]:obj=obj[part]
                dest=mapping.get(edge['target'],int(edge['target'].split(':')[1]))
                obj[edge['path'][-1]]=str(dest) if edge.get('string') else dest
            sig=signature(row);candidates=indexes[node['table']].get(sig)
            if candidates is None:continue
            candidates=[i for i in candidates if labels_available(token,store.table(node['table'])[i])]
            if not candidates:continue
            ident=node['id'] if node['id'] in candidates else candidates[0]
            mapping[token]=ident;reused[token]=ident;changed=True
        if not changed:break
    # SuperImposed selects Gift rows; those Gifts point back to the same
    # group. A bottom-up-only comparison cannot resolve this legitimate cycle.
    shapes={}
    def links(token):return [e for e in packet['edges'][token] if e['path'][0] not in LABELS]
    def value_at(row,path):
        for part in path:row=row[part]
        return row
    def skeleton(token,row,source=False):
        row=copy.deepcopy(row)
        for e in links(token):
            obj=row
            for part in e['path'][:-1]:obj=obj[part]
            target=e['target'];table,old=target.split(':')
            if table in EFFECT_TABLES and target in packet['nodes']:v='@'+table
            else:v=mapping.get(target,int(old)) if source else value_at(row,e['path'])
            obj[e['path'][-1]]=v
        return signature(row)
    def candidates(token):
        node=packet['nodes'][token];shape=(node['table'],tuple((tuple(e['path']),e['target'].split(':')[0],e['target'] in packet['nodes']) for e in links(token)))
        if shape not in shapes:
            index={}
            for ident,row in sorted(store.table(node['table']).items()):
                try:sig=skeleton(token,row)
                except (KeyError,IndexError,TypeError):continue
                index.setdefault(sig,[]).append(ident)
            shapes[shape]=index
        return shapes[shape].get(skeleton(token,node['row'],True),[])
    def equivalent(token,ident,seen,proposed):
        pair=(token,ident)
        if pair in seen:return True
        if len(seen)>10000:return False
        if token in reused:return reused[token]==ident
        if packet['nodes'][token]['table']=='Gift':return False
        node=packet['nodes'][token];other=store.table(node['table']).get(ident)
        if other is None or not labels_available(token,other):return False
        try:
            if skeleton(token,node['row'],True)!=skeleton(token,other):return False
        except (KeyError,IndexError,TypeError):return False
        seen.add(pair);proposed.setdefault(token,ident)
        for e in links(token):
            target=e['target'];table,old=target.split(':')
            if table not in EFFECT_TABLES or target not in packet['nodes']:continue
            value=value_at(other,e['path'])
            if e.get('string'):
                if not isinstance(value,str) or not value.isdecimal():return False
                value=int(value)
            if type(value) is not int or value<=0 or not equivalent(target,value,seen,proposed):return False
        return True
    for token,node in packet['nodes'].items():
        if token in reused or node['table'] not in indexes:continue
        options=candidates(token)
        if node['id'] in options:options=[node['id']]+[i for i in options if i!=node['id']]
        for ident in options:
            proposed={}
            try:matched=equivalent(token,ident,set(),proposed)
            except RecursionError:matched=False
            if not matched:continue
            for t,i in proposed.items():
                if t not in reused:reused[t]=i;mapping[t]=i
            break
    return reused

def active_nodes(packet,reused):
    # Reverse relationships are part of the exported object: AoYi recipes,
    # books, all character variants and owned placement tasks.
    queue=[key('@Role' if packet['kind']=='Role' else packet['kind'],packet['root'])]
    for rec in packet['extras'].get('role_metadata',{}).values():
        task=(rec.get('position_task') or {}).get('Task')
        if task:queue.append(key('Task',task))
    active=set();seen=set()
    while queue:
        token=queue.pop()
        if token in seen:continue
        seen.add(token)
        if token.startswith('@Role:'):
            rid=int(token.split(':')[1])
            if str(rid) not in packet['role_groups']:continue
            queue.extend(key('Role',i) for i in packet['role_groups'][str(rid)])
            queue.extend(t for t,n in packet['nodes'].items() if n['table']=='NpcEvolute' and n['row'].get('RoleID')==rid)
            continue
        if token in reused or token not in packet['nodes']:continue
        active.add(token);node=packet['nodes'][token]
        queue.extend(e['target'] for e in packet['edges'][token])
        if node['table']=='Martial':
            queue.extend(t for t,n in packet['nodes'].items() if (n['table']=='AoYi' and n['row'].get('AoYiID')==node['id']) or (n['table']=='Item' and n['row'].get('MartialID')==node['id'] and n['row'].get('ItemType') in (15,16)))
        if node['table']=='Task':
            queue.extend(t for t,n in packet['nodes'].items() if n['table']=='TaskEdge' and n['row'].get('StateID')==node['row'].get('RootState'))
    return active
