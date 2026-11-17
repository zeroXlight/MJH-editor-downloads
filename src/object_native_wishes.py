"""Keep a verified native generic chain intact, including its literal wish IDs."""
from object_bundle import key

def reuse(packet,store,mapping):
    result={}
    for ident in (195,190):
        token=key('RoleWishQuest',ident)
        if token not in packet['nodes']:continue
        node=packet['nodes'][token]
        if node['row']!=store.table('RoleWishQuest').get(ident):continue
        queue=[token];seen=set()
        while queue:
            current=queue.pop()
            if current in seen:continue
            seen.add(current);entry=packet['nodes'].get(current)
            if entry is None:continue
            if entry['row']!=store.table(entry['table']).get(entry['id']):
                raise ValueError('原生通用情缘任务链与目标游戏不同，不能安全复用：'+current)
            queue.extend(e['target'] for e in packet['edges'].get(current,[]))
            if entry['table']=='Task':
                queue.extend(t for t,n in packet['nodes'].items() if n['table']=='TaskEdge' and n['row'].get('StateID')==entry['row'].get('RootState'))
            if entry['table']=='TaskEdge':
                states={entry['row'].get('ConditonSatisfyJumpStateID',0),entry['row'].get('ConditonNotSatisfyJumpStateID',0)}-{0}
                queue.extend(t for t,n in packet['nodes'].items() if n['table']=='TaskEdge' and n['row'].get('StateID') in states)
        # Hard-coded wish IDs inside native task arguments must retain native IDs.
        mapping[token]=ident;result[token]=ident
    return result

def mark_native_references(packet):
    # Original generic quests use story/text identifiers resolved outside these tables.
    # They are safe only while the exact original task edges are reused on the target.
    for token,row in list(packet['anchors'].items()):
        if row!={'missing':True} or token.split(':')[0] not in ('Story','Language'):continue
        sources=[t for t,edges in packet['edges'].items() if any(e['target']==token for e in edges)]
        if sources and all(t.startswith('TaskEdge:') and (4193000<=int(t.split(':')[1])<4194000 or 4342000<=int(t.split(':')[1])<4343000) for t in sources):
            packet['anchors'][token]={'native_chain_sources':sources}

def validate_native_reference(packet,store,token,row):
    sources=row.get('native_chain_sources',[])
    if not sources:raise ValueError('原生任务引用校验信息缺失：'+token)
    for source in sources:
        node=packet['nodes'].get(source,{})
        if node.get('table')!='TaskEdge' or not (4193000<=node.get('id',0)<4194000 or 4342000<=node.get('id',0)<4343000):raise ValueError('不支持的原生任务引用：'+source)
        if node['row']!=store.table('TaskEdge').get(node['id']):raise ValueError('原生任务引用来源与目标不同：'+source)
        if not any(e['target']==token for e in packet['edges'].get(source,[])):raise ValueError('原生任务引用绑定缺失：'+token)
