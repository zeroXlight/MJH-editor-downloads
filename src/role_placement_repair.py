"""Recover only editor-owned placement graphs after native resources are updated."""
import copy,json
from codec import decode
from engine import SCHEMAS
from martial_editor import indexed_rows
from client_config import lua_rows

def _sources(lib,name):
    native={i:decode(v,name,SCHEMAS) for i,v in indexed_rows(lib.originals[lib.root/'TableData'/(name+'.bytes')])[0].items()}
    defaults=decode(b'',name,SCHEMAS);client={}
    for resource in lib.resources[name]:
        for i,row in lua_rows(lib.assets.script(resource),name,lib.enums).items():client[i]=defaults|row
    path=lib.own_jsons[name];raw=lib.originals.get(path)
    own={r['BaseID']:defaults|r for r in json.loads(raw.decode('utf-8-sig')).get('Items',[])} if raw else {}
    return native,client,own

def _binary_sources(lib,name):
    """Additional native loaders: StreamingAssets and embedded table blob."""
    copies=[];path=lib.root/'DreamRivakes_Data/StreamingAssets'/(name+'.bytes')
    if path.is_file():
        raw=path.read_bytes();lib.originals.setdefault(path,raw)
        copies.append({i:decode(v,name,SCHEMAS) for i,v in indexed_rows(raw)[0].items()})
    if name in lib.assets.scripts:
        _,q,n=lib.assets.scripts[name]
        copies.append({i:decode(v,name,SCHEMAS) for i,v in indexed_rows(lib.assets.data[q+4:q+4+n])[0].items()})
    return copies

def pending(lib):
    """Make the normal Save button available for a lost owned placement graph."""
    checks={};tasks=set()
    for token,record in lib.meta.items():
        if not token.isdecimal() or int(token) not in lib.roles or not record.get('settings',{}).get('location_path'):continue
        graph=record.get('position_task')
        if not graph:return True
        for table,key in [('Task','Task'),('TaskEdge','TaskEdge'),('TaskEvent','TaskEvent'),('Behavior','move'),('Behavior','unique')]:
            checks.setdefault(table,set()).add(graph.get(key))
        tasks.add(graph.get('Task'))
        checks.setdefault('NpcEvolute',set()).update(i for i,row in lib.tables['NpcEvolute'].items() if row.get('RoleID')==int(token))
    for table,ids in checks.items():
        a,b,_=_sources(lib,table)
        for i in ids:
            if i is None or any(rows.get(i)!=lib.tables[table].get(i) for rows in [a,b,*_binary_sources(lib,table)]):return True
    if tasks:
        a,b,_=_sources(lib,'Story')
        if any(not tasks.issubset(row.get('StartTask',[])) for rows in [a,b,*_binary_sources(lib,'Story')] for row in rows.values()):return True
    return False

def stage(lib):
    from role_locations import install_placement
    sources={};replicas={};restored=[];tasks=set()
    def sync(name,ident,expected):
        if name not in sources:
            sources[name]=_sources(lib,name);replicas[name]=_binary_sources(lib,name)
        native,client,own=sources[name];row=lib.tables[name].get(ident)
        if row is None or any(row.get(k)!=v for k,v in expected.items()):
            raise ValueError(f'人物放置配置与保存的位置不一致，未覆盖：{name} {ident}')
        actuals=[native.get(ident),client.get(ident),*(r.get(ident) for r in replicas[name])]
        if all(actual==row for actual in actuals):return
        if lib.overrides[name].get(ident):raise ValueError(f'人物放置配置存在外部MOD覆盖：{name} {ident}')
        for actual in actuals:
            if actual is not None and actual!=row and actual!=own.get(ident):
                raise ValueError(f'人物放置配置存在未知改动，未覆盖：{name} {ident}')
        lib.changes[name][ident]=copy.deepcopy(row);restored.append((name,ident))
    for token,record in list(lib.meta.items()):
        if not token.isdecimal() or int(token) not in lib.roles:continue
        rid=int(token);settings=record.get('settings',{});path=settings.get('location_path') or []
        if not path:continue
        path=lib.places.validate(settings['city'],path)
        owned=record.get('position_task')
        if not owned:
            # The saved explicit location authorizes a new graph, never a guess
            # about an original NPC's city or a save's current position.
            owned=install_placement(lib,rid,path,record);record['position_task']=owned
        if set(owned)!= {'Task','TaskEdge','TaskEvent','move','unique'} or any(type(v) is not int or v<=0 for v in owned.values()):
            raise ValueError('人物放置任务记录无效：'+token)
        task,edge,event=(owned[n] for n in ('Task','TaskEdge','TaskEvent'));tasks.add(task)
        sync('Task',task,dict(RootState=task,Type=0,NameID=0))
        sync('TaskEdge',edge,dict(StateID=task,Type=lib.enums['TaskEdgeType.TET_Succeed'],TaskEventID=event,ConditonSatisfyCallbackIDs=[owned['move'],owned['unique']]))
        sync('TaskEvent',event,dict(Event=lib.enums['Event.Event_MapEnter'],EventArg1=str(path[0])))
        for name,kind in [('move',385),('unique',386)]:sync('Behavior',owned[name],dict(Type=kind,Arg1=str(rid),Arg2=str(path[-1])))
        for ident,row in lib.tables['NpcEvolute'].items():
            if row.get('RoleID')==rid:sync('NpcEvolute',ident,dict(RoleID=rid,CityID=settings['city']))
    if tasks:
        # Never replay a retained whole Story row: updates can change plot,
        # difficulty and map rules. Merge only the owned task registrations.
        native,client,own=_sources(lib,'Story');extra=_binary_sources(lib,'Story')
        for ident,row in native.items():
            other=client.get(ident)
            if other is None or {k:v for k,v in row.items() if k!='StartTask'}!={k:v for k,v in other.items() if k!='StartTask'}:
                raise ValueError('人物放置所需剧情逻辑与显示配置不一致，未覆盖：Story '+str(ident))
            a=row.get('StartTask',[]);b=other.get('StartTask',[])
            for replica in extra:
                value=replica.get(ident)
                if value is None or {k:v for k,v in value.items() if k!='StartTask'}!={k:v for k,v in row.items() if k!='StartTask'} or [v for v in value.get('StartTask',[]) if v not in tasks]!=[v for v in a if v not in tasks]:
                    raise ValueError('人物放置所需剧情副本存在外部冲突：Story '+str(ident))
            if [v for v in a if v not in tasks]!=[v for v in b if v not in tasks]:
                raise ValueError('人物放置所需剧情任务存在外部冲突：Story '+str(ident))
            starts=list(dict.fromkeys([*a,*b,*sorted(tasks)]))
            if starts==a and starts==b and all(r[ident].get('StartTask',[])==starts for r in extra):continue
            desired=copy.deepcopy(row);desired['StartTask']=starts
            lib.tables['Story'][ident]=desired;lib.changes['Story'][ident]=desired
            # Keep overlapping MODs' unrelated fields; only register these tasks.
            for p,raw in lib.originals.items():
                if p==lib.own_jsons['Story'] or p.parent!=lib.own_jsons['Story'].parent or not p.name.startswith('Story_') or not raw:continue
                doc=json.loads(lib.files.get(p,raw).decode('utf-8-sig'));changed=False
                for r in doc.get('Items',[]):
                    if r.get('BaseID')==ident:
                        values=list(dict.fromkeys([*r.get('StartTask',[]),*starts]))
                        if values!=r.get('StartTask',[]):r['StartTask']=values;changed=True
                if changed:lib.files[p]=json.dumps(doc,ensure_ascii=False,indent=2).encode('utf8')
            restored.append(('Story',ident))
    if restored:
        lib.mod_warnings.append(f'已核实并补回 {len(restored)} 条人物生成／放置配置；已有存档如缺人物，请使用“补齐人物到指定存档”，不会自动改写旧档或队伍。')
    return restored
