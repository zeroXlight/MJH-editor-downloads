"""Bind ownership tests to real PC records; copy functional effect dependencies."""
import copy
from object_bundle import key
from mobile_martial_graph import links,expression_literal_links

ALIASES={'@NativeMartial':'Martial','@NativeGift':'Gift'}

def identity_edge(node,edge):
    table=node['table'];row=node['row'];path=edge['path'];target=edge['target'].split(':')[0]
    if table=='MartialFilter' and path==['MartialID']:return True
    if table=='Gift' and path==['AttrMartial']:return True
    if table=='Condition' and row['CondType'] in (185,193):return True
    if table=='SkillEffect':
        n=row['Name']
        return target=='Martial' and n in (384,386,498,526,536)
    return False

def prepare(packet,roots,store,performances):
    nodes=packet['nodes'];edges=packet['edges'];anchors=packet['anchors'];aliases={};bindings=[]
    # Event 323 is emitted by both Buff and Gift owners. Its predicate's
    # argument belongs to that owner's namespace, not always Gift.
    from event_condition_refs import packet_links
    event_links=packet_links(nodes)
    for token,extra in event_links.items():
        paths={path for path,target in extra}
        edges[token]=[e for e in edges[token] if tuple(e['path']) not in paths]
        edges[token].extend({'path':list(path),'target':target,'string':False} for path,target in sorted(extra))
    # Tiered gifts supplied by the imported SuperImposed chain remain in that
    # chain. Ownership predicates must test the gifts that chain actually gives.
    granted={e['target'] for t,ee in edges.items() if nodes[t]['table']=='SuperImposed' for e in ee}
    cache={}
    def native_target(token):
        if token in cache:return cache[token]
        table,ident=token.split(':');source=nodes[token]['row']
        label=nodes.get(key('Language',source['NameID']),{}).get('row',{}).get('Ch_Text')
        matches=[r for r in store.table(table).values() if label and store.table('Language').get(r['NameID'],{}).get('Ch_Text')==label]
        exact=next((r for r in matches if r['BaseID']==int(ident)),None)
        row=exact or (matches[0] if len(matches)==1 else None)
        if not row:raise ValueError('PC缺少可明确对应的原生持有条件：'+token+' '+str(label))
        cache[token]=row;return row
    queue=[key('Martial',i) for i in roots];active=set()
    while queue:
        token=queue.pop()
        if token in active or token not in nodes:continue
        active.add(token);node=nodes[token]
        for edge in edges[token]:
            target=edge['target']
            if target in nodes and target not in {key('Martial',i) for i in roots} and target not in granted and identity_edge(node,edge):
                row=native_target(target);table=nodes[target]['table'];alias='@Native'+table;replacement=key(alias,row['BaseID'])
                anchors[replacement]=copy.deepcopy(row);edge['target']=replacement
                obj=node['row']
                for part in edge['path'][:-1]:obj=obj[part]
                obj[edge['path'][-1]]=str(row['BaseID']) if edge.get('string') else row['BaseID']
                aliases[(token,tuple(edge['path']))]=alias
                bindings.append({'source':token,'path':edge['path'],'mobile':target,'native':key(table,row['BaseID'])})
            else:queue.append(target)
    # Literal expressions may hold an ownership-test identifier in a constant.
    # The graph's extra edge lives on the constant, whose operator is zero.
    for token in list(active):
        node=nodes[token]
        if node['table']!='SkillEffect':continue
        for child,target,ident in expression_literal_links(node['row'],lambda i:nodes.get(key('SkillEffect',i),{}).get('row',{})):
            ct=key('SkillEffect',child)
            if ct not in active:continue
            for edge in edges[ct]:
                if edge['path']!=['EventArg1',0] or edge['target']!=key(target,ident):continue
                proxy={'table':'SkillEffect','row':node['row']}
                if not identity_edge(proxy,edge) or edge['target'] in granted or edge['target'] in {key('Martial',i) for i in roots}:continue
                row=native_target(edge['target']);alias='@Native'+target;replacement=key(alias,row['BaseID'])
                anchors[replacement]=copy.deepcopy(row);old=edge['target'];edge['target']=replacement
                nodes[ct]['row']['EventArg1'][0]=row['BaseID'];aliases[(ct,('EventArg1',0))]=alias
                bindings.append({'source':ct,'path':['EventArg1',0],'mobile':old,'native':key(target,row['BaseID'])})
    # Recompute after replacing expression edges, then discard unreachable
    # whole martial trees. No duplicate collectible ordinary arts are created.
    queue=[key('Martial',i) for i in roots];active=set()
    while queue:
        token=queue.pop()
        if token in active or token not in nodes:continue
        active.add(token);queue.extend(e['target'] for e in edges[token])
    packet['nodes']={t:n for t,n in nodes.items() if t in active};packet['edges']={t:edges[t] for t in active}
    used={e['target'] for ee in packet['edges'].values() for e in ee}
    packet['anchors']={t:r for t,r in anchors.items() if t in used}
    for t,n in packet['nodes'].items():
        if n['table']=='Martial' and n['id'] not in roots:n['row'].update(Display=0,Drop=1,CouldCopy=0,Exclusive=[])
    def ref(table,row,enums):
        token=key(table,row['BaseID'])
        return [(path,aliases.get((token,tuple(path)),target),ident) for path,target,ident in links(table,row,enums)]
    def const(row,lookup):
        return [(child,aliases.get((key('SkillEffect',child),('EventArg1',0)),target),ident) for child,target,ident in expression_literal_links(row,lookup)]
    return {t:p for t,p in performances.items() if t in active},(ref,const),bindings
