"""Add one-shot native placement tasks to a selected Robot 2 save.

Never rebuild character instances or copy party state. Existing save bytes are
preserved except the task allocator counter and the count-prefixed task map.
The active-record seed is taken from a fully validated native task in that save.
"""
import copy,struct
from pathlib import Path
from dataclasses import dataclass
from engine import digest

TASK_BYTES=624
NPC_BYTES=48
COUNTER_BYTES=24
ZERO=bytes(16)

def u32(data,p):
    if p<0 or p+4>len(data):raise ValueError('存档记录越界')
    return struct.unpack_from('<I',data,p)[0]

@dataclass
class SaveLayout:
    task_offset:int
    task_count:int
    counter_offset:int
    maximum:int
    seed:bytes
    task_types:set
    npc_types:set

def inspect(data,lib):
    from save_format import validate_reader_header
    validate_reader_header(data)
    if not 19036<=len(data)<=100*1024*1024:raise ValueError('存档大小不在人物同步支持范围，未写入')
    # Allocator entries have sorted native manager kinds and zero dirty headers.
    counters=[]
    for p in range(128,len(data)-COUNTER_BYTES*5,4):
        n=u32(data,p)
        if not 5<=n<=64 or p+4+n*COUNTER_BYTES>len(data):continue
        if data[p+4:p+20]!=ZERO:continue
        keys=[];entries={}
        for k in range(n):
            off=p+4+k*COUNTER_BYTES;key=u32(data,off+16)
            if data[off:off+16]!=ZERO or not 1<=key<=64:break
            keys.append(key);entries[key]=(off+20,u32(data,off+20))
        else:
            if keys==sorted(set(keys)) and all(i in entries for i in (6,9,10,20)):counters.append((p,entries))
    if len(counters)!=1:raise ValueError('无法唯一识别存档的原生编号分配表，未写入')
    cp,entries=counters[0];counter,maximum=entries[9]
    if not 0<maximum<2147483000:raise ValueError('任务编号分配器无效')
    candidates=[]
    tasks=lib.tables['Task'];roles=lib.roles
    for p in range(cp+4,len(data)-TASK_BYTES,4):
        n=u32(data,p)
        if not 1<=n<=50000 or p+4+n*TASK_BYTES+4>len(data):continue
        if data[p+4:p+20]!=ZERO:continue
        if u32(data,p+24) not in tasks:continue
        last=p+4+(n-1)*TASK_BYTES
        if data[last:last+16]!=ZERO or u32(data,last+20) not in tasks:continue
        types=set();prior=0;seed=None
        for k in range(n):
            off=p+4+k*TASK_BYTES;record=data[off:off+TASK_BYTES];ident=u32(record,16);typ=u32(record,20)
            if record[:16]!=ZERO or not prior<ident<=maximum or typ not in tasks:break
            prior=ident;types.add(typ)
            # A pristine active task has only ID, type, root state and the native
            # active progress bits. Do not infer a seed from a finished task.
            masked=bytearray(record)
            for q in (16,20,280,416):masked[q:q+4]=bytes(4)
            if (not any(masked) and u32(record,280)==tasks[typ].get('RootState')
                    and u32(record,416)==0x20000):seed=record
        else:
            # Native serialization puts the lightweight NPC map immediately
            # after tasks. Prove that boundary using every entry, not a hit.
            np=p+4+n*TASK_BYTES;nn=u32(data,np)
            if not 1<=nn<=50000 or np+4+nn*NPC_BYTES>len(data):continue
            npc_types=set();prev=0
            for k in range(nn):
                off=np+4+k*NPC_BYTES;ident=u32(data,off+16);typ=u32(data,off+20)
                if data[off:off+16]!=ZERO or not prev<ident<=entries[6][1] or typ not in roles:break
                prev=ident;npc_types.add(typ)
            else:
                if seed is not None:candidates.append(SaveLayout(p,n,counter,maximum,seed,types,npc_types))
    if len(candidates)!=1:raise ValueError('未能验证唯一的原生活动任务表及人物表，已停止；不会猜测存档位置')
    return candidates[0]

def eligible(lib):
    return [(int(rid),lib.name(int(rid))) for rid,record in lib.meta.items()
            if isinstance(rid,str) and rid.isdecimal() and int(rid) in lib.roles and record.get('settings')]

def blocking_reference(raw,rid,lib):
    """Account card levels and wish progress do not prove a live/dead NPC.

    Exempt only their verified role-key fields. Every other occurrence remains
    a blocker, including actor, lightweight NPC, plot/death and unknown data.
    """
    from save_format import table_spans
    _,spans=table_spans(raw);allowed=set()
    for table,field in ((15,16),(56,20)):
        _,start,end,_,stride=spans[table]
        for off in range(start,end,stride):
            row=raw[off:off+stride]
            if u32(row,field)!=rid or any(row[:16]):continue
            if table==15:
                if u32(row,20)>10:continue
            else:
                # Native wishes can retain removed quest IDs after an update.
                # Check their serialized fields, not today's quest catalogue.
                flags=u32(row,32)
                if not u32(row,16) or not u32(row,24) or flags>>16 or flags&255 not in (1,2,3) or u32(row,36)!=0:continue
            allowed.add(off+field)
    needle=struct.pack('<I',rid);at=raw.find(needle)
    while at>=0:
        if at not in allowed:return True
        at=raw.find(needle,at+1)
    return False

def preview(lib,path,selected):
    path=Path(path).resolve()
    canonical=(path==lib.root/'Save.sav' or path.parent.parent==lib.root/'SaveFile')
    if path.name!='Save.sav' or not canonical or not path.is_file():raise ValueError('请选择当前游戏目录中的自动档或 SaveFile 下的存档')
    if lib.modified():raise ValueError('请先保存人物配置，再补齐旧档；未保存的草稿不会写入存档')
    raw=path.read_bytes();layout=inspect(raw,lib);available=dict(eligible(lib));rows=[]
    for rid in selected:
        if type(rid) is not int or rid not in available:raise ValueError('所选人物不是已保存的编辑角色')
        rec=lib.meta[str(rid)];settings=lib.options(rid);location=settings.get('location_path') or []
        city=settings['city'];rootmap=location[0] if location else lib.tables['City'][city].get('EnterMapID',0)
        destination=location[-1] if location else rootmap
        if rootmap not in lib.tables['Map'] or destination not in lib.tables['Map']:raise ValueError(available[rid]+' 缺少有效的城市或场景，请先编辑具体位置')
        # Keep live/dead/plot references protected; cross-round account progress
        # alone must not prevent generating a missing NPC in this round.
        previous=rec.get('save_restore_tasks',{}).get(path.relative_to(lib.root).as_posix())
        if rid in layout.npc_types:status='已有角色，保留进度'
        elif blocking_reference(raw,rid,lib):status='档内已有角色或剧情引用，保守跳过'
        elif previous and previous['Task'] in layout.task_types:status='已安排补齐任务，不重复添加'
        else:status='补齐缺失人物'
        rows.append(dict(rid=rid,name=available[rid],status=status,root_map=rootmap,destination=destination,
                         location=lib.places.describe(city,location) if location else lib.text(lib.tables['City'][city].get('NameID'))+'（城市入口）'))
    return dict(path=path,raw=raw,sha=digest(raw),layout=layout,rows=rows)

def plan(lib,proposal):
    path=proposal['path'];raw=proposal['raw']
    if path.read_bytes()!=raw:raise ValueError('所选存档在预览后发生变化，请重新预览')
    targets=[row for row in proposal['rows'] if row['status']=='补齐缺失人物']
    if not targets:raise ValueError('没有需要补齐的人物，存档未改动')
    layout=inspect(raw,lib);new=[];maximum=layout.maximum
    for row in targets:
        task=lib.new_id('Task');edge=lib.new_id('TaskEdge');event=lib.new_id('TaskEvent');move=lib.new_id('Behavior');unique=move+1
        lib.set('Task',task,{'RootState':task,'Type':0,'NameID':0})
        lib.set('TaskEvent',event,{'Event':lib.enums['Event.Event_MapEnter'],'EventArg1':str(row['root_map'])})
        for ident,kind in ((move,385),(unique,386)):
            lib.set('Behavior',ident,{'Type':kind,'Arg1':str(row['rid']),'Arg2':str(row['destination'])})
        lib.set('TaskEdge',edge,{'StateID':task,'Type':lib.enums['TaskEdgeType.TET_Succeed'],'TaskEventID':event,'ConditonSatisfyCallbackIDs':[move,unique]})
        key=path.relative_to(lib.root).as_posix()
        lib.meta[str(row['rid'])].setdefault('save_restore_tasks',{})[key]={'Task':task,'TaskEdge':edge,'TaskEvent':event,'move':move,'unique':unique}
        maximum+=1
        record=bytearray(layout.seed)
        for off,value in ((16,maximum),(20,task),(280,task)):struct.pack_into('<I',record,off,value)
        new.append(bytes(record))
    payloads,originals=lib.plan()
    edited=bytearray(raw);struct.pack_into('<I',edited,layout.counter_offset,maximum)
    struct.pack_into('<I',edited,layout.task_offset,layout.task_count+len(new))
    insertion=layout.task_offset+4+layout.task_count*TASK_BYTES
    edited[insertion:insertion]=b''.join(new);edited=bytes(edited)
    check=inspect(edited,lib)
    if check.task_count!=layout.task_count+len(new) or check.maximum!=maximum:raise ValueError('补齐任务回读失败')
    # A length change must shift the untouched suffix as one complete block.
    if edited[insertion+len(new)*TASK_BYTES:]!=raw[insertion:]:raise ValueError('存档尾部发生非预期变化')
    originals[path]=raw;payloads[path]=edited
    return payloads,originals,len(new)
