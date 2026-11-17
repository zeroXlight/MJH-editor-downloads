"""Event 323 predicates compare the added owner's ID (Buff OR Gift)."""

def owner_links(table,row,lookup):
    if table not in ('Buff','Gift'):return []
    found=[];seen=set();queue=[t['ConditionID'] for t in row.get('SkillTriggers',[]) if t.get('Event')==323 and t.get('ConditionID')]
    while queue:
        ident=queue.pop()
        if ident in seen:continue
        seen.add(ident);effect=lookup(ident) or {}
        if effect.get('Name')==501:
            arg=effect.get('EventArg1',[])
            if len(arg)==2:
                if arg[1]:
                    child_id=arg[1];visited=set()
                    while child_id and child_id not in visited:
                        visited.add(child_id);child=lookup(child_id) or {};value=child.get('EventArg1',[])
                        if child.get('Name')!=0 or len(value)!=2:break
                        if not value[1]:
                            if value[0]>0:found.append((child_id,['EventArg1',0],table,value[0]))
                            break
                        child_id=value[1]
                elif arg[0]>0:found.append((ident,['EventArg1',0],table,arg[0]))
        for i in range(1,14):
            arg=effect.get('EventArg'+str(i),[])
            if len(arg)==2 and arg[1]:queue.append(arg[1])
    return found

def packet_links(nodes):
    output={};owners={}
    lookup=lambda i:nodes.get('SkillEffect:'+str(i),{}).get('row',{})
    for node in nodes.values():
        for ident,path,table,value in owner_links(node['table'],node['row'],lookup):
            key=('SkillEffect:'+str(ident),tuple(path));target=table+':'+str(value)
            if key in owners and owners[key]!=target:
                raise ValueError('共享新增状态条件混用不同编号空间，不能安全重映射：'+key[0])
            owners[key]=target;output.setdefault(key[0],set()).add((tuple(path),target))
    return output
