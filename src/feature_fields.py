"""Suspend owned fields/scripts without reverting a save or an entire asset."""
from pathlib import Path
import copy,json,re
from object_bundle import Store
from client_config import Assets,lua_rows
from martial_editor import patch_table,patch_lua_rows
STATE='装备编辑器配置/功能字段开关.json'

def table_rows(store,table):
    if table!='KungfuBase':return store.table(table)
    from martial_growth import growth_native,growth_lua
    from codec import decode
    from engine import SCHEMAS
    rows={i:decode(r,table,SCHEMAS) for i,r in growth_native(store.read(store.root/'TableData/KungfuBase.bytes')).items()}
    for i,r in growth_lua(store.assets.script('KungfuBase.lua'),store.enums).items():rows.setdefault(i,{}).update(r)
    for p in sorted((store.root/'ModProject/GameProject').rglob('KungfuBase_*.json')):
        doc=json.loads(store.read(p).decode('utf-8-sig'));records=doc.get('Items',[]) if isinstance(doc,dict) else doc
        for row in records:rows.setdefault(row['BaseID'],{}).update(row)
    return rows

def state(root):
    p=Path(root)/STATE
    return json.loads(p.read_text('utf8')) if p.exists() else {'version':1,'features':{}}

def mobile_growth(doc):
    record=doc['features'].get('mobile',{})
    return {e['id']:e for e in record.get('entries',[]) if e['table']=='Martial' and e['field']=='GrowProIDs'} if record.get('suspended') else {}

def sync(store,updates):
    payloads={};originals={};assets=store.assets
    for table,deltas in updates.items():
        from martial_mastery import patch_native
        for directory in ('TableData','DreamRivakes_Data/StreamingAssets'):
            p=store.root/directory/(table+'.bytes');raw=store.read(p)
            if raw is not None:payloads[p]=patch_native(raw,table,deltas);originals[p]=raw
        if table in assets.scripts:
            _,q,n=assets.scripts[table];assets=Assets(assets.replace_blob(table,patch_native(assets.data[q+4:q+4+n],table,deltas)))
        for script in list(assets.scripts):
            if not re.fullmatch(re.escape(table)+r'\d*\.lua',script):continue
            from martial_growth import growth_lua
            current=growth_lua(assets.script(script),store.enums) if table=='KungfuBase' else lua_rows(assets.script(script),table,store.enums)
            selected={i:{**current[i],**d} for i,d in deltas.items() if i in current}
            if selected:assets=Assets(assets.replace_script(script,patch_lua_rows(assets.script(script),selected)))
        # A later JSON override must not undo the switch. Update just the
        # selected fields in every override that already contains this ID.
        for p in sorted((store.root/'ModProject/GameProject').rglob(table+'_*.json')):
            raw=store.read(p);doc=json.loads(raw.decode('utf-8-sig'));rows=doc.get('Items',[]) if isinstance(doc,dict) else doc;changed=False
            for row in rows:
                delta=deltas.get(row.get('BaseID'))
                if delta:
                    for key,value in delta.items():
                        if row.get(key)!=value:row[key]=copy.deepcopy(value);changed=True
            if changed:payloads[p]=json.dumps(doc,ensure_ascii=False,indent=2).encode('utf8');originals[p]=raw
    p=store.root/'DreamRivakes_Data/resources.assets'
    if assets.data!=store.assets.data:payloads[p]=assets.normalize_text_lengths();originals[p]=store.assets.data
    return payloads,originals

def switch(root,key,enabled,make_entries=None):
    store=Store(root);doc=state(root);prior=doc['features'].get(key)
    if enabled and (not prior or not prior.get('suspended')):return {},{},['当前无需重新启用。'],[],{}
    if not enabled and prior and prior.get('suspended'):return {},{},['当前已经关闭。'],[],{}
    if enabled:entries=prior['entries'];scripts=prior.get('scripts',[])
    else:
        if make_entries is None:raise ValueError('缺少可核实的功能恢复记录')
        entries,scripts=make_entries(store)
        if not entries and not scripts:raise ValueError('没有可安全关闭的已启用记录')
    updates={};tables={};dormant=mobile_growth(doc)
    for e in entries:
        allowed={'mobile':{'Martial':{'GrowProIDs','MartMovIDs','UnlockClauses','UnlockLvls'}},
                 'mastery':{'Martial':{'GrowProIDs'},'KungfuBase':{'RankDatas'}},'disguise':{}}
        if e.get('field') not in allowed.get(key,{}).get(e.get('table'),set()):raise ValueError('功能恢复记录包含非本功能字段')
        if e.get('table')=='KungfuBase' and e.get('index') not in (6,7):raise ValueError('精通成长恢复位置无效')
        if e['table'] not in tables:tables[e['table']]=table_rows(store,e['table'])
        row=tables[e['table']].get(e['id'])
        if not row:raise ValueError('功能配置记录已不存在：'+str(e['id']))
        value=copy.deepcopy(dormant[e['id']]['on']) if key=='mastery' and e['table']=='Martial' and e['id'] in dormant else row.get(e['field'])
        index=e.get('index');current=value[index] if index is not None else value
        wanted=e['on'] if enabled else e['off'];expected=e['off'] if enabled else e['on']
        if key=='mastery' and e['field']=='GrowProIDs':
            # Mastery owns the added clause, not unrelated growth clauses
            # added later by six-attribute restoration or martial editing.
            added=set(e['on'])-set(e['off']);removed=set(e['off'])-set(e['on'])
            discard=removed if enabled else added;insert=added if enabled else removed
            wanted=[v for v in current if v not in discard]
            for value in (e['on'] if enabled else e['off']):
                if value in insert and value not in wanted:wanted.insert(min((e['on'] if enabled else e['off']).index(value),len(wanted)),value)
        elif current!=wanted and current!=expected:raise ValueError('功能字段已被其他修改改变，未覆盖：'+e['table']+' '+str(e['id'])+' '+e['field'])
        if current==wanted:continue
        if key=='mastery' and e['table']=='Martial' and e['id'] in dormant:
            dormant[e['id']]['on']=copy.deepcopy(wanted);continue
        delta=updates.setdefault(e['table'],{}).setdefault(e['id'],{})
        if index is None:delta[e['field']]=copy.deepcopy(wanted)
        else:
            values=delta.setdefault(e['field'],copy.deepcopy(value));values[index]=wanted
    payloads,originals=sync(store,updates)
    p=store.root/'DreamRivakes_Data/resources.assets';assets=Assets(payloads.get(p,store.assets.data))
    for script in scripts:
        if key!='disguise' or script.get('name')!='DisguiseUI.lua':raise ValueError('功能恢复记录包含非本功能脚本')
        wanted=script['on'] if enabled else script['off'];expected=script['off'] if enabled else script['on'];current=assets.script(script['name'])
        if current==wanted:continue
        if current!=expected:raise ValueError('功能脚本已被其他修改改变，未覆盖：'+script['name'])
        assets=Assets(assets.replace_script(script['name'],wanted))
    if assets.data!=store.assets.data:payloads[p]=assets.normalize_text_lengths();originals[p]=store.assets.data
    doc['features'][key]={'suspended':not enabled,'entries':entries,'scripts':scripts}
    p=store.root/STATE;originals[p]=store.read(p);payloads[p]=json.dumps(doc,ensure_ascii=False,indent=2).encode('utf8')
    return payloads,originals,[('重新启用' if enabled else '关闭')+'：仅修改本功能字段，保留其他配置及存档进度。'],[],store.reads

def rebase_mastery(root):
    """Reapply an active mastery overlay after a known six-attribute change."""
    doc=state(root);record=doc['features'].get('mastery',{})
    if not record.get('suspended'):return
    store=Store(root);tables={};dormant=mobile_growth(doc)
    for e in record['entries']:
        if e['table'] not in tables:tables[e['table']]=table_rows(store,e['table'])
        row=tables[e['table']][e['id']];current=copy.deepcopy(dormant[e['id']]['on'] if e['table']=='Martial' and e['id'] in dormant else row[e['field']])
        if e['field']=='GrowProIDs':
            added=set(e.setdefault('intent_add',[v for v in e['on'] if v not in e['off']]))
            removed=set(e.setdefault('intent_remove',[v for v in e['off'] if v not in e['on']]))
            on=[v for v in current if v not in removed]
            for v in e['on']:
                if v in added and v not in on:on.insert(0,v)
            e['off']=current;e['on']=on
        else:e['off']=current[e['index']]
    (Path(root)/STATE).write_text(json.dumps(doc,ensure_ascii=False,indent=2),'utf8')

def mobile_entries(store):
    p=store.root/'装备编辑器配置/手游专属武学恢复.json'
    if not p.exists():return [],[]
    installed=json.loads(p.read_text('utf8')).get('installed',{});entries=[]
    for rec in installed.values():
        row=store.table('Martial').get(rec['id'])
        if row is None:raise ValueError('已恢复的手游武学记录缺失')
        for field in ('GrowProIDs','MartMovIDs','UnlockClauses','UnlockLvls'):
            entries.append(dict(table='Martial',id=rec['id'],field=field,on=copy.deepcopy(row[field]),off=[]))
    return entries,[]

def disguise_entries(store):
    name='DisguiseUI.lua';text=store.assets.script(name);starts=[text.index(m) for m in ('-- MJH_DISGUISE_UI_V223','-- MJH_DISGUISE_UI_V224','-- MJH_DISGUISE_UI_V2212') if m in text]
    if len(starts)!=1 or text.count('-- MJH_DISGUISE_UI_END')!=1:raise ValueError('易容扩展界面边界不兼容，未关闭')
    end=text.index('-- MJH_DISGUISE_UI_END',starts[0])+len('-- MJH_DISGUISE_UI_END')
    return [],[dict(name=name,on=text,off=text[:starts[0]]+text[end:])]

def mastery_entries(store):
    tracked=state(store.root)['features'].get('mastery')
    if tracked is not None:return copy.deepcopy(tracked['entries']),[]
    p=store.root/'装备编辑器配置/武学精通恢复记录.json'
    if p.exists():return json.loads(p.read_text('utf8'))['entries'],[]
    # Legacy releases did not keep a feature receipt. Use only verified backup
    # preimages and remove exactly the native mastery clause absent there.
    from martial_mastery import MASTERY,native_rows
    from codec import decode
    from engine import SCHEMAS,digest
    baseline={};formula={}
    for manifest in sorted((store.root/'装备编辑器备份').glob('*/manifest.json')):
        doc=json.loads(manifest.read_text('utf8'))
        if not doc.get('complete') or Path(doc.get('root','')).resolve()!=store.root:continue
        for entry in doc.get('entries',[]):
            table={'TableData/Martial.bytes':'Martial','TableData/KungfuBase.bytes':'KungfuBase'}.get(entry['path'].replace('\\','/'))
            if not table or not entry.get('exists'):continue
            source=(manifest.parent/entry['backup']).resolve()
            if not source.is_relative_to(manifest.parent.resolve()):raise ValueError('备份来源越界')
            raw=source.read_bytes()
            if digest(raw)!=entry['before_sha256']:raise ValueError('精通恢复原值备份校验失败')
            target=baseline if table=='Martial' else formula
            for i,row in native_rows(raw,table).items():target.setdefault(i,decode(row,table,SCHEMAS))
    entries=[]
    for i,row in store.table('Martial').items():
        old=baseline.get(i);spec=MASTERY.get(row.get('DepartEnum'))
        if not old or not spec or row.get('Rank') not in (6,7):continue
        clause=spec[1];on=row.get('GrowProIDs',[])
        if clause in on and clause not in old.get('GrowProIDs',[]):
            entries.append(dict(table='Martial',id=i,field='GrowProIDs',on=copy.deepcopy(on),off=[v for v in on if v!=clause]))
    if entries:
        from martial_growth import growth_lua
        current=growth_lua(store.assets.script('KungfuBase.lua'),store.enums)
        for i in range(49161,49169):
            if i not in formula or i not in current:continue
            for index in (6,7):
                old=formula[i]['RankDatas'][index];new=current[i]['RankDatas'][index]
                if old!=new:entries.append(dict(table='KungfuBase',id=i,field='RankDatas',index=index,on=new,off=old))
    return entries,[]
