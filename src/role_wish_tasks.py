"""One-shot native initializer for already-owned legacy characters.

The game's existing-character invitation path returns before opening wish tasks.
Use the original 4214 graph with literal owner parameters; no fake client entries.
"""
import struct
from role_save_sync import inspect as inspect_tasks,TASK_BYTES
from role_wish_save import present

def ensure(lib,rid,mode='full'):
    rec=lib.meta[str(rid)];meta_field={'full':'wish_restore_task','friend':'wish_friend_restore_task','treasure':'wish_treasure_restore_task'}[mode];owned=rec.get(meta_field)
    if owned and owned.get('Task') in lib.tables['Task']:
        expected={'full':[('4342',str(rid)+'|195'),('4193',str(rid)+'|190')],'friend':[('4193',str(rid)+'|190')],'treasure':[('4342',str(rid)+'|195')]}[mode]
        actual=[(lib.tables['Behavior'].get(i,{}).get('Arg1'),lib.tables['Behavior'].get(i,{}).get('Arg5')) for i in owned.get('Behavior',[])]
        if owned.get('owner')!=rid or actual!=expected:raise ValueError('人物情缘初始化任务绑定不匹配，未修改存档')
        return owned['Task']
    source,first,count={'full':(4214,421401,6),'friend':(4192,419201,4),'treasure':(4217,421701,4)}[mode]
    task=lib.clone('Task',source)
    edges=[r for r in lib.tables['TaskEdge'].values() if first<=r.get('StateID',0)<first+count]
    if len(edges)!=count:raise ValueError('原生通用心愿初始化状态不完整')
    occupied={r.get('StateID',0) for r in lib.tables['TaskEdge'].values()}|{r.get('RootState',0) for r in lib.tables['Task'].values()}
    start=max(1900000000,max((i for i in occupied if i>=1900000000),default=1899999999)+1)
    states={first+i:start+i for i in range(count)}
    callbacks={}
    creates={'full':[(4214004,195),(4214005,190)],'friend':[(4192004,190)],'treasure':[(4217004,195)]}[mode]
    owner_get={'full':4214003,'friend':4192003,'treasure':4217003}[mode]
    for old,wish in creates:
        new=lib.clone('Behavior',old);lib.set('Behavior',new,{'Arg5':str(rid)+'|'+str(wish)});callbacks[old]=new
    lib.set('Task',task,{'RootState':start,'SpecialFlag':[],'NameID':0})
    created=[]
    for old in sorted(edges,key=lambda r:r['BaseID']):
        ident=lib.clone('TaskEdge',old['BaseID']);delta={'StateID':states[old['StateID']]}
        for field in ['ConditonSatisfyJumpStateID','ConditonNotSatisfyJumpStateID']:delta[field]=states.get(old[field],old[field])
        for field in ['ConditonSatisfyCallbackIDs','ConditonNotSatisfyCallbackIDs']:
            delta[field]=[callbacks.get(i,i) for i in old[field] if i!=owner_get]
        lib.set('TaskEdge',ident,delta);created.append(ident)
    owned={'Task':task,'states':list(states.values()),'TaskEdge':created,'Behavior':list(callbacks.values()),'owner':rid}
    rec[meta_field]=owned
    return task

def fill(raw,lib,selected=None):
    selected=set(selected) if selected is not None else {int(rid) for rid,rec in lib.meta.items() if rec.get('wish_restore_needed')}
    targets=[rid for rid in sorted(selected) if str(rid) in lib.meta and rid>=1700000000 and present(raw,rid,2147483647)]
    if not targets:return raw,[]
    layout=inspect_tasks(raw,lib);new=[];report=[];maximum=layout.maximum
    from role_wish_save import inspect as inspect_wishes
    wishes=inspect_wishes(raw,lib)
    for rid in targets:
        states={wish:flags&255 for uid,role,wish,flags,record in wishes.records if role==rid and (flags>>8)&255==wishes.script}
        treasure_done=states.get(195,0)>=2;friend_done=states.get(190,0)>=2
        if treasure_done and friend_done:continue
        active=[lib.meta[str(rid)].get(k,{}).get('Task') for k in ['wish_restore_task','wish_friend_restore_task','wish_treasure_restore_task']]
        if any(t in layout.task_types for t in active):continue
        mode='friend' if treasure_done else 'treasure' if friend_done else 'full'
        task=ensure(lib,rid,mode)
        if task in layout.task_types:continue
        maximum+=1;record=bytearray(layout.seed)
        for off,value in [(16,maximum),(20,task),(280,lib.tables['Task'][task]['RootState'])]:struct.pack_into('<I',record,off,value)
        new.append(bytes(record));report.append({'role':rid,'task':task,'instance':maximum})
    if not new:return raw,[]
    out=bytearray(raw);struct.pack_into('<I',out,layout.counter_offset,maximum);struct.pack_into('<I',out,layout.task_offset,layout.task_count+len(new))
    end=layout.task_offset+4+layout.task_count*TASK_BYTES;out[end:end]=b''.join(new);out=bytes(out)
    check=inspect_tasks(out,lib)
    assert check.task_count==layout.task_count+len(new) and check.maximum==maximum
    assert out[end+len(new)*TASK_BYTES:]==raw[end:]
    assert out[layout.task_offset+4:end]==raw[layout.task_offset+4:end]
    return out,report
