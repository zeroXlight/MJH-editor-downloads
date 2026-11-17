"""Validated native save operations shared by the editor and BAT launchers.

No fixed record offsets, no execution of bundled PowerShell, no DLL hash lock.
Unknown layouts are rejected before preparing any write for that save.
"""
import json, struct, re
from pathlib import Path
from save_format import STRIDES,table_spans

LABELS = {'resources':'补足资源', 'meridian_exp':'增加经脉点900000', 'fragments':'补足武学残章至20级', 'achievements':'解锁难度与成就', 'collection':'补齐新增武学收藏'}
RESOURCE_COUNTS = {37:999,38:99999,39:99999}
ITEM_COUNTS = {805004:100,9698:999,1106:999,1006:999}

def u32(b,p): return struct.unpack_from('<I',b,p)[0]
def put(b,p,v): struct.pack_into('<I',b,p,v)
def record(size, **values):
    row=bytearray(size)
    for offset,value in values.items(): put(row,int(offset[1:]),value)
    return row

class NativeSave:
    def __init__(self, data):
        self.header_kind,spans=table_spans(data)
        self.header=bytearray(data[:760]);self.tables=[]
        for _,start,end,_,stride in spans:
            self.tables.append([bytearray(data[q:q+stride]) for q in range(start,end,stride)])
    def indexed(self, table, ordered=True):
        out={}; last=0
        for row in self.tables[table]:
            key=u32(row,16)
            if any(row[:16]) or not key or key in out or (ordered and key<=last):
                raise ValueError(f'存档表 {table} 的编号、顺序或前缀不兼容')
            out[key]=row; last=key
        return out
    def bytes(self):
        result=bytes(self.header)+b''.join(struct.pack('<I',len(rows))+b''.join(rows) for rows in self.tables)
        NativeSave(result)
        return result
    def script(self):
        row=self.indexed(0).get(2)
        if row is None or not u32(row,20): raise ValueError('未找到支持的主角剧本2，已跳过')
        return row
    def counter(self, kind, table):
        row=self.indexed(1).get(kind)
        if row is None: raise ValueError(f'缺少编号分配器 {kind}')
        maximum=max(self.indexed(table),default=0)
        if u32(row,20)<maximum: raise ValueError(f'编号分配器 {kind} 小于已有最大编号')
        return row

def patch_resources(save, config, notes):
    script=save.script(); owner=u32(script,20); put(script,56,100000000)
    rows=save.indexed(61,ordered=False)
    for key,row in rows.items():
        kind=u32(row,20); group=u32(row,32)
        if kind>=16777216 or key!=kind+group*16777216: raise ValueError('资源表编码不兼容')
    for kind,count in RESOURCE_COUNTS.items():
        row=rows.setdefault(kind,record(40,p16=kind,p20=kind)); put(row,24,count)
    save.tables[61]=[rows[k] for k in sorted(rows)]
    items=save.indexed(23); available=config['items']
    for ident,count in ITEM_COUNTS.items():
        matches=[r for r in items.values() if u32(r,24)==ident and u32(r,20)==owner and u32(r,28)>0 and u32(r,32)==0 and u32(r,36)==514]
        if ident not in available or len(matches)!=1:
            notes.append(f'道具 {ident}：配置缺失或没有唯一的主角背包记录，已跳过'); continue
        put(matches[0],28,count)

def patch_fragments(save, config, notes):
    script=save.script(); date=u32(script,136)
    if not 1<=date<=10000000: raise ValueError('剧本日期不兼容')
    unlocks=save.indexed(2); logs=save.indexed(46)
    counter=save.counter(18,2); logcounter=save.counter(19,46)
    # The low byte is a record subtype; preserve all existing types.
    if any(not (1 <= u32(r,32)>>24 <= 30 and (u32(r,32)>>16)&255 in (1,2)) for r in logs.values()): raise ValueError('残章日志表标记不兼容')
    by_martial={}
    for row in unlocks.values():
        if u32(row,28)==6: by_martial.setdefault(u32(row,24),[]).append(row)
    uid=u32(counter,20); lid=u32(logcounter,20); changed=0
    for ident in sorted(config['martials']):
        matches=by_martial.get(ident,[])
        if len(matches)>1: notes.append(f'武学 {ident} 的残章记录重复，已跳过'); continue
        old=u32(matches[0],20) if matches else 0
        if old>=10: continue
        if uid>=0xffffffff or lid+10-old>0xffffffff: raise ValueError('残章编号空间不足')
        if matches: put(matches[0],20,10)
        else:
            uid+=1; unlocks[uid]=record(32,p16=uid,p20=10,p24=ident,p28=6)
        for value in range(old,10):
            lid+=1; logs[lid]=record(40,p16=lid,p20=value,p24=ident,p28=date,p32=33619968)
        changed+=1
    put(counter,20,uid); put(logcounter,20,lid)
    save.tables[2]=[unlocks[k] for k in sorted(unlocks)]
    save.tables[46]=[logs[k] for k in sorted(logs)]
    return changed

def patch_achievements(save, config, notes):
    if save.header[747]>30: raise ValueError('难度进度字段不兼容')
    rows=save.indexed(3)
    if any(r[24]>1 for r in rows.values()): raise ValueError('成就领取状态不兼容')
    for ident,goal in config['achievements'].items():
        row=rows.setdefault(ident,record(32,p16=ident))
        old=struct.unpack_from('<i',row,20)[0]
        if (goal>=0 and old<goal) or (goal<0 and old>goal): struct.pack_into('<i',row,20,goal)
    save.tables[3]=[rows[k] for k in sorted(rows)]
    save.header[747]=max(save.header[747],config['difficulty'])

def patch_collection(save, config, notes):
    rows=save.indexed(2);counter=save.counter(18,2);uid=u32(counter,20)
    present={u32(row,24) for row in rows.values() if u32(row,28)==6}
    for ident in sorted(config['collection']-present):
        if uid>=0xffffffff:raise ValueError('收藏编号空间不足')
        uid+=1;rows[uid]=record(32,p16=uid,p20=0,p24=ident,p28=6)
    put(counter,20,uid);save.tables[2]=[rows[k] for k in sorted(rows)]

def patch_meridian_exp(save,config,notes):
    from meridian_resource import increase
    before,after=increase(save,900000)
    notes.append(f'经脉经验：{before} → {after}（增加 900000，与奇经八脉和宠物共用）')

PATCHERS={'resources':patch_resources,'meridian_exp':patch_meridian_exp,'fragments':patch_fragments,'achievements':patch_achievements,'collection':patch_collection}

def patch_save(data, action, config, notes):
    save=NativeSave(data); PATCHERS[action](save,config,notes); result=save.bytes()
    if action=='meridian_exp':
        # Additive actions are deliberately repeatable. Validate the delta and
        # exact payload rather than requiring an idempotent second application.
        from meridian_resource import balance
        before=NativeSave(data);after=NativeSave(result)
        if balance(after)-balance(before)!=900000:raise ValueError('经脉经验增量校验失败')
        after.tables[6]=before.tables[6]
        if after.bytes()!=data:raise ValueError('经脉修改影响了其他存档字段')
        return result
    check=NativeSave(result); PATCHERS[action](check,config,[])
    if check.bytes()!=result: raise ValueError('重复执行校验失败，未准备写入')
    return result

def load_config(root, action, notes, overlay=None):
    from object_bundle import Store
    from client_config import lua_rows, enum_values
    from codec import fields, values
    store=Store(root,overlay)
    def table(name, numbers):
        path=store.root/'TableData'/f'{name}.bytes'; raw=store.read(path)
        if not raw: raise ValueError('缺少当前游戏配置：'+name)
        rows={}
        for f in fields(raw):
            if f.number!=2: continue
            ids=values(f.value,1)
            if len(ids)!=1 or type(ids[0]) is not int or ids[0]<=0: notes.append(name+'：编号异常记录已跳过'); continue
            row={'BaseID':ids[0]}
            for key,number in numbers.items():
                v=values(f.value,number)
                if len(v)==1 and type(v[0]) is int: row[key]=v[0]-(1<<64) if v[0] >= 1<<63 else v[0]
            rows[ids[0]]=row
        if name+'.lua' in store.assets.scripts:
            text=store.assets.script(name+'.lua'); store.enums.update(enum_values(text))
            default_match=re.search(r'(?m)^local '+re.escape(name)+r'Default\s*=\s*(\{[^\r\n]*)',text)
            def selected(body):
                row={}
                for key in numbers:
                    match=re.search(r'\b'+key+r'\s*=\s*([^,}]+)',body)
                    if not match: continue
                    token=match[1].strip()
                    if re.fullmatch(r'-?\d+',token): row[key]=int(token)
                    elif token in store.enums and type(store.enums[token]) is int: row[key]=store.enums[token]
                    else: raise ValueError('未知字段 '+key)
                return row
            try: defaults=selected(default_match[1]) if default_match else {}
            except ValueError as error: defaults={}; notes.append(name+' 默认字段已跳过：'+str(error))
            for ident,body in re.findall(r'(?m)^\s*\[(\d+)\]\s*=\s*(\{[^\r\n]+)',text):
                ident=int(ident)
                try:
                    match=re.search(r'\bBaseID\s*=\s*(\d+)',body)
                    if not match or int(match[1])!=ident: raise ValueError('编号不匹配')
                    rows.setdefault(ident,{}).update(defaults|selected(body))
                except ValueError as error:
                    rows.pop(ident,None); notes.append(f'{name}:{ident} 配置已跳过：{error}')
        mod_paths=set((store.root/'ModProject').rglob('*.json'))
        mod_paths.update(Path(p) for p,raw in (overlay or {}).items() if raw is not None and Path(p).is_relative_to(store.root/'ModProject') and Path(p).suffix=='.json')
        for path in sorted(mod_paths):
            if path.stem.split('_')[0]!=name: continue
            try:
                obj=json.loads(store.read(path).decode('utf-8-sig'))
                for row in obj.get('Items',[]):
                    if not isinstance(row,dict) or type(row.get('BaseID')) is not int or row['BaseID']<=0:
                        notes.append(path.name+'：未知编号记录已跳过'); continue
                    rows.setdefault(row['BaseID'],{}).update(row)
            except (ValueError,TypeError,AttributeError) as error: notes.append(f'{path.name} 配置无法识别，已跳过：{error}')
        return rows
    def ids(rows): return {i for i in rows if 0<i<0x80000000}
    config={}
    if action=='resources': config['items']=ids(table('Item',{}))
    elif action=='fragments':
        rows=table('Martial',{'LvLimit':15,'Display':18})
        # Only visible martial arts with an ordinary trainable cap. Special
        # moves and hidden placeholders are not fragment targets.
        config['martials']={i for i,row in rows.items() if i in ids(rows) and row.get('Display',1)==1 and type(row.get('LvLimit',10)) is int and 10<=row.get('LvLimit',10)<=1000}
        if not config['martials']: raise ValueError('没有识别到可补足残章的武学')
    elif action=='collection':
        from caps import baseline
        native={int(i) for i in baseline()['proto']['Martial']}
        rows=table('Martial',{'Display':18,'Drop':8,'Rank':6})
        config['collection']={i for i,r in rows.items() if i not in native and 0<i<0x80000000 and r.get('Display',1)==1 and r.get('Drop',0)==0 and type(r.get('Rank')) is int and 1<=r['Rank']<=7}
    elif action=='achievements':
        rows=table('Achieve',{'ProgressMax':17}); goals={}
        for ident,row in rows.items():
            goal=row.get('ProgressMax',1)
            if 0<ident<0x80000000 and type(goal) is int and -(1<<31)<=goal<(1<<31): goals[ident]=goal
            else: notes.append(f'成就 {ident} 目标值未知，已跳过')
        story=table('Story',{'DifficultMax':34})
        levels=[r['DifficultMax'] for r in story.values() if type(r.get('DifficultMax')) is int and 1<=r['DifficultMax']<=30]
        if not goals or not levels: raise ValueError('无法确认当前游戏成就或难度配置')
        config.update(achievements=goals,difficulty=max(levels))
    return config,store.reads

def plan(root, paths, action):
    root=Path(root).resolve(); notes=[]; payloads={}; originals={}; results=[]
    if action not in PATCHERS: raise ValueError('未知功能')
    config,reads=load_config(root,action,notes)
    for p in paths:
        path=Path(p).resolve()
        if (not path.is_relative_to(root/'SaveFile') and path!=root/'Save.sav') or path.name!='Save.sav': raise ValueError('所选存档不在当前游戏存档目录内')
        try:
            before=path.read_bytes(); local=[]; after=patch_save(before,action,config,local)
            notes.extend(f'{path.parent.name}：{n}' for n in local)
            originals[path]=before
            if after!=before: payloads[path]=after
            label='自动存档' if path==root/'Save.sav' else path.parent.name
            extra=''
            if action=='collection':extra=f'（新增 {len(NativeSave(after).tables[2])-len(NativeSave(before).tables[2])} 条收藏记录）'
            results.append(f'{label}：'+('可修改' if after!=before else '已符合目标')+extra)
        except (ValueError,OSError,struct.error) as error:
            notes.append(f'{path.parent.name} 已跳过：{error}')
    return payloads,originals,results,notes,reads

def apply(root, prepared):
    from engine import transaction,ensure_closed
    payloads,originals,results,notes,reads=prepared
    ensure_closed()
    for path,before in reads.items():
        if (path.read_bytes() if path.exists() else None)!=before: raise ValueError('游戏配置已变化，请重新预览')
    return transaction(root,payloads,originals,'功能修改')
