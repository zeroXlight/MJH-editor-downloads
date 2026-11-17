"""Portable selected-object graphs with explicit typed reference paths.

Packets contain data only. No arbitrary Lua, native patches or save bytes are
accepted. Common world/resource anchors are checked, never overwritten.
"""
import copy,json,re,zipfile,hashlib,secrets,io,base64,os,tempfile
from pathlib import Path
from codec import decode,patch,encoded,fields,numeric_list
from engine import SCHEMAS
from client_config import Assets,lua_rows,enum_values
from martial_editor import indexed_rows,patch_lua_rows,encode_field
from language_routing import resource_for

FORMAT='mjh-selected-object';VERSION=2;MAX_SIZE=80*1024*1024
ANCHORS={'Clan','City','Map','ResourceRoleModel'}
CLAN_ACQUISITION_POOLS={'Fist','Knife','Leg','Sword','Stick','Dart','Magic','HighMartial','BestMartial'}

def anchor_compatible(table,expected,actual):
    """A referenced clan keeps the target's own martial acquisition pools.

    Restoration changes those catalogues without changing the clan identity.
    All other fields, missing clans and unknown schema fields remain strict.
    This check never writes the source catalogue into the target game.
    """
    if expected==actual:return True
    if table!='Clan' or not isinstance(expected,dict) or not isinstance(actual,dict):return False
    if (set(expected)|set(actual))-set(SCHEMAS['Clan']):return False
    if any(expected.get(k)!=actual.get(k) for k in (set(expected)|set(actual))-CLAN_ACQUISITION_POOLS):return False
    for k in CLAN_ACQUISITION_POOLS:
        for row in (expected,actual):
            if not isinstance(row.get(k,[]),list) or any(type(v) is not int or not 0<v<2147483647 for v in row.get(k,[])):return False
    return True
REFS={
 'Martial':{'NameID':'Language','DesID':'Language','ClanID':'Clan','GrowProIDs':'MartialItem','MartMovIDs':'MartialItem','UnlockClauses':'MartialItem','Exclusive':'@Role'},
 'AoYi':{'AoYiID':'Martial','MartialList':'Martial','GiftList':'Gift'},
 'MartialItem':{'DesID':'Language','CondID':'Condition','SkillID1':'Skill','SkillID2':'Skill','MartialFilter1':'MartialFilter','MartialFilter2':'MartialFilter'},
 'MartialFilter':{'MartialID':'Martial','ClanID':'Clan'},
 'Skill':{'NameID':'Language','DescID':'Language','ClanID':'Clan','SkillRange':'MartialRange','MartialItemID':'MartialItem','SurperType':'SuperImposed'},
 'Gift':{'NameID':'Language','DescID':'Language','AttrMartial':'Martial','ClanID':'Clan','SurperType':'SuperImposed'},
 # Despite the legacy field name, NPC/DefaultRole resolve BuffList as Gift.
 'SuperImposed':{'BuffList':'Gift','SuperType':'SuperImposed'},
 'Buff':{'NameID':'Language','DescID':'Language'},
 'Item':{'MartialID':'Martial','GiftID':'Gift','BlueGift':'Gift','BlueMartial':'Martial','OrigItemID':'Item','Clan':'Clan','PersonalTreasure':'@Role','FragmentRole':'@Role','DropCondID':'Condition'},
 'MartialRange':{'CasterRangeIDs':'Range','AttackRangeIDs':'Range','CasterRangeIDs2':'Range','AttackRangeIDs2':'Range'},
 'Range':{'NameID':'Language'},
 'Role':{'RoleID':'@Role','NameID':'Language','SurnameID':'Language','GivennameID':'Language','IntroduceID':'Language','TitleID':'RoleTitle','Clan':'Clan','Kungfu':'Martial','Gift':'Gift','AttributeID':'RoleAttr','ArtID':'RoleModel','WishQuestID':'RoleWishQuest','EvoInitCity':'City',**{k:'Item' for k in ('Weapon','Artifacts','Clothes','Shoe','Ornaments','KungfuBook','Horse','Bag')}},
 'RoleTitle':{'TitleID':'Language'},
 'RoleModel':{'ModelID':'ResourceRoleModel'},
 'NpcEvolute':{'RoleID':'@Role','CityID':'City'},
 'RoleWishQuest':{'NameID':'Language','DescID':'Language','TaskID':'Task'},
 'Task':{'NameID':'Language','TaskDescID':'Language','RegainStoryID':'Story'},
 'TaskEdge':{'TaskEventID':'TaskEvent','ConditonSatisfyCallbackIDs':'Behavior','ConditonNotSatisfyCallbackIDs':'Behavior','ConditionID':'Condition','DescIDs':'Language','EndingDescID':'Language','ConditonSatisfyStoryID':'Story','ConditonNotSatisfyStoryID':'Story'},
}

def sha(raw):return hashlib.sha256(raw).hexdigest()
def key(table,ident):return f'{table}:{ident}'

class IncompleteGraph(ValueError):
    def __init__(self,report):
        self.report=report
        required=[r for r in report if r['required']]
        super().__init__('发现 '+str(len(required))+' 条必需依赖缺失，不能生成完整配置包：'+', '.join(r['target'] for r in required[:8]))

def missing_report(packet):
    report=[]
    for token,row in sorted(packet.get('anchors',{}).items()):
        if row!={'missing':True}:continue
        refs=[{'source':t,'path':e['path']} for t,edges in packet['edges'].items() for e in edges if e['target']==token]
        optional=token.startswith('Language:') and bool(refs) and all(r['path'][0] in ('DescID','DesID','IntroduceID','TaskDescID') or (r['source'].startswith('Range:') and r['path']==['NameID']) for r in refs)
        report.append({'target':token,'required':not optional,'references':refs,'reason':'来源缺少显示文本，保留编号与实际效果数据' if optional else '必需关联配置缺失，停止导出／导入'})
    return report

def check_complete(packet):
    report=missing_report(packet)
    if any(r['required'] for r in report):raise IncompleteGraph(report)
    return report

class Store:
    def __init__(self,root,overlay=None):
        self.root=Path(root).resolve();self.overlay=overlay or {};self.reads={};self.tables={};self.native={}
        raw=self.read(self.root/'DreamRivakes_Data/resources.assets');self.assets=Assets(raw)
        self.enums=enum_values(self.assets.script('common.lua'))|enum_values(self.assets.script('Enum.lua'))|{'False':0,'True':1}
    def read(self,path):
        path=Path(path)
        if path not in self.reads:self.reads[path]=path.read_bytes() if path.exists() else None
        return self.overlay.get(path,self.reads[path])
    def table(self,name):
        if name in self.tables:return self.tables[name]
        # This client resource table has no server protobuf schema. It is a
        # read-only anchor: verify the selected model, never import its files.
        if name=='ResourceRoleModel':
            text=self.assets.script('ResourceRoleModel.lua')
            self.enums.update(enum_values(text))
            rows=lua_rows(text,name,self.enums)
            directory=self.root/'ModProject/GameProject/Mod_MJH/Json'
            paths=set(directory.glob(name+'_*.json'))|{p for p in self.overlay if p.parent==directory and p.name.startswith(name+'_')}
            for path in sorted(paths):
                raw=self.read(path)
                if not raw:continue
                from mod_rows import read_rows
                warnings=[]
                for row in read_rows(raw,name,SCHEMAS,warnings,path.name):rows.setdefault(row['BaseID'],{}).update(row)
                if not hasattr(self,'mod_warnings'):self.mod_warnings=[]
                self.mod_warnings.extend(warnings)
            self.native[name]={};self.tables[name]=rows;return rows
        if name not in SCHEMAS:raise ValueError('尚未支持关联表：'+name)
        raw=self.read(self.root/'TableData'/f'{name}.bytes')
        if not raw:raise ValueError('缺少关联配置表：'+name)
        self.native[name]=indexed_rows(raw)[0]
        rows={i:decode(r,name,SCHEMAS) for i,r in self.native[name].items()}
        pattern=r'Language\d*\.lua' if name=='Language' else re.escape(name)+r'\d*\.lua'
        for resource in self.assets.scripts:
            if not re.fullmatch(pattern,resource):continue
            text=self.assets.script(resource);self.enums.update(enum_values(text))
            if name=='Language':
                from read_cache import language_script
                values={i:{'BaseID':i,'Ch_Text':v} for i,v in language_script(text)}
            else:values=lua_rows(text,name,self.enums)
            for ident,row in values.items():rows.setdefault(ident,{}).update(row)
        directory=self.root/'ModProject/GameProject/Mod_MJH/Json'
        paths=set(directory.glob(name+'_*.json'))|{p for p in self.overlay if p.parent==directory and p.name.startswith(name+'_')}
        from mod_rows import read_rows
        warnings=[]
        for path in sorted(paths):
            data=self.read(path)
            if not data:continue
            for row in read_rows(data,name,SCHEMAS,warnings,path.name):
                row=copy.deepcopy(row)
                if name=='Language' and 'Text' in row:row['Ch_Text']=row.pop('Text')
                rows.setdefault(row['BaseID'],{}).update(row)
        if not hasattr(self,'mod_warnings'):self.mod_warnings=[]
        self.mod_warnings.extend(warnings)
        self.tables[name]=rows;return rows

def references(table,row,enums):
    refs=[]
    def add(path,target,value):
        if type(value) is int and value>0:refs.append((path,target,value))
    for field,target in REFS.get(table,{}).items():
        value=row.get(field,0)
        if isinstance(value,list):
            for i,v in enumerate(value):add([field,i],target,v)
        else:add([field],target,value)
    for i,trigger in enumerate(row.get('SkillTriggers',[])):
        for field,target in [('ConditionID','SkillEffect'),('EffectID','SkillEffect'),('EffectGroupFargID','SkillEffect'),('EffectCampGroupFargID','SkillEffect')]:add(['SkillTriggers',i,field],target,trigger.get(field,0))
    if table=='SkillEffect':
        for n in range(1,14):
            field='EventArg'+str(n);value=row.get(field,[])
            if len(value)==2:add([field,1],'SkillEffect',value[1])
        kind=row.get('Name')
        literals={enums.get('SkillEffectDescription.SED_SkillLogic_CommonInitiativeSkill'):{1:'SkillEffect'},
                  enums.get('SkillEffectDescription.SED_SkillLogic_CommonFanJiProcess'):{1:'Martial',2:'Skill'},
                  464:{1:'SkillEffect'},423:{2:'Martial',3:'Skill'},434:{2:'Buff'},448:{2:'Buff'},
                  744:{1:'Martial',2:'MartialRange'},745:{1:'Martial',2:'MartialRange'}}
        from mobile_martial_graph import LITERALS
        for operator,typed in LITERALS.items():
            if typed:literals.setdefault(operator,{}).update(typed)
        if kind==498:
            selector=row.get('EventArg1',[])
            target={1:'Skill',2:'Martial'}.get(selector[0]) if len(selector)==2 and selector[1]==0 else None
            if target:literals[498]={3:target}
        for n,target in literals.get(kind,{}).items():
            value=row.get('EventArg'+str(n),[])
            if len(value)==2 and not value[1]:add(['EventArg'+str(n),0],target,value[0])
    if table=='Condition':
        field,target={185:('CondArg2','Gift'),193:('CondArg1','Martial')}.get(row.get('CondType'),(None,None))
        if field and str(row.get(field,'')).isdecimal() and int(row[field])>0:refs.append(([field],target,int(row[field])))
    if table=='Behavior' and row.get('Type')==737:
        value=row.get('Arg1','')
        if isinstance(value,str) and value.isdecimal():refs.append((['Arg1'],'Task',int(value)))
    if table=='Behavior' and row.get('Type') in (385,386):
        for field,target in [('Arg1','@Role'),('Arg2','Map')]:
            v=row.get(field,'')
            if isinstance(v,str) and v.isdecimal():refs.append(([field],target,int(v)))
    return refs

def constant_links(row,lookup):
    types={423:{2:'Martial',3:'Skill'},434:{2:'Buff'},448:{2:'Buff'},744:{2:'MartialRange'},745:{2:'MartialRange'}}
    from mobile_martial_graph import LITERALS
    for operator,typed in LITERALS.items():
        if typed:types.setdefault(operator,{}).update(typed)
    if row.get('Name')==498 and row.get('EventArg1') in ([1,0],[2,0]):types[498]={3:'Skill' if row['EventArg1'][0]==1 else 'Martial'}
    links=[]
    for n,target in types.get(row.get('Name'),{}).items():
        arg=row.get('EventArg'+str(n),[])
        if len(arg)!=2 or not arg[1]:continue
        child=lookup(arg[1]);value=child.get('EventArg1',[])
        if child.get('Name')==0 and len(value)==2 and value[0]>0 and not value[1]:links.append((arg[1],target,value[0]))
    return links

def export_graph(store,kind,ident):
    if kind not in ('Martial','Role','Item','Task'):raise ValueError('对象类别无效')
    nodes={};anchors={};role_groups={};queue=[];seen=set();edges={};extras={};constant_edges={};performance_cache=None;timing_cache=None
    def enqueue(table,i):
        if i:queue.append((table,int(i)))
    enqueue('@Role' if kind=='Role' else kind,ident)
    while queue:
        table,i=queue.pop();token=key(table,i)
        if token in seen:continue
        seen.add(token)
        if len(seen)>30000:raise ValueError('关联配置超过 30000 条，停止导出')
        if table=='@Role':
            variants=[r for r in store.table('Role').values() if r.get('RoleID')==i]
            if not variants:raise ValueError('缺少人物原型：'+str(i))
            if kind!='Role' or i!=ident:
                anchors[token]={'variants':sorted(r['BaseID'] for r in variants)}
                continue
            role_groups[str(i)]=[r['BaseID'] for r in variants]
            for r in variants:enqueue('Role',r['BaseID'])
            for e in store.table('NpcEvolute').values():
                if e.get('RoleID')==i:enqueue('NpcEvolute',e['BaseID'])
            continue
        row=store.table(table).get(i)
        if row is None and table in SCHEMAS and not (table==kind and i==ident):
            anchors[token]={'missing':True};extras.setdefault('source_missing',[]).append(token);continue
        if row is None:raise ValueError(f'缺少关联数据 {table} {i}')
        if table in ANCHORS:
            anchors[token]=copy.deepcopy(row);continue
        from client_only_fields import without_empty_defaults
        row=without_empty_defaults(table,row)
        unknown=set(row)-set(SCHEMAS[table])
        if unknown:extras.setdefault('compatibility_warnings',[]).append(token+'：不支持的MOD扩展字段未打包：'+','.join(sorted(unknown)))
        row={k:v for k,v in row.items() if k in SCHEMAS[table]}
        nodes[token]={'table':table,'id':i,'row':copy.deepcopy(row),'wire':base64.b64encode(store.native[table].get(i,b'')).decode()}
        edges[token]=[]
        from event_condition_refs import owner_links
        for child,path,target,value in owner_links(table,row,lambda i:store.table('SkillEffect').get(i,{})):
            edge={'path':path,'target':key(target,value),'string':False}
            prior=constant_edges.setdefault(key('SkillEffect',child),[])
            if edge not in prior:prior.append(edge)
            enqueue(target,value)
        for path,target,value in references(table,row,store.enums):
            edges[token].append({'path':path,'target':key(target,value),'string':isinstance(path[0],str) and isinstance(row.get(path[0]),str)})
            enqueue(target,value)
        if table=='SkillEffect':
            for child,target,value in constant_links(row,lambda i:store.table('SkillEffect').get(i,{})):
                edge={'path':['EventArg1',0],'target':key(target,value),'string':False}
                prior=constant_edges.setdefault(key('SkillEffect',child),[])
                if edge not in prior:prior.append(edge)
                enqueue(target,value)
        if table=='Martial':
            for a in store.table('AoYi').values():
                if a.get('AoYiID')==i:enqueue('AoYi',a['BaseID'])
            for book in store.table('Item').values():
                if book.get('MartialID')==i and book.get('ItemType') in (15,16):enqueue('Item',book['BaseID'])
        if table=='Task':
            for e in store.table('TaskEdge').values():
                if e.get('StateID')==row.get('RootState'):enqueue('TaskEdge',e['BaseID'])
        if table=='TaskEdge':
            states={row.get('ConditonSatisfyJumpStateID',0),row.get('ConditonNotSatisfyJumpStateID',0)}-{0}
            for child in store.table('TaskEdge').values():
                if child.get('StateID') in states:enqueue('TaskEdge',child['BaseID'])
        if table=='RoleModel':
            from role_animation import animation_rows
            from lua_data import parse
            if timing_cache is None:timing_cache=animation_rows(store.assets.script('SpineAnimaitionTime.lua'))
            timing=timing_cache.get(i)
            if not timing:raise ValueError('人物模型缺少完整动作数据：'+str(i))
            extras.setdefault('model_timing',{})[str(i)]=parse(timing[2])
        if table=='Skill' or (table=='SkillEffect' and row.get('Name') in (451,537)):
            from martial_editor import performance_blocks
            from lua_data import parse
            if performance_cache is None:performance_cache=performance_blocks(store.assets.script('SkillPerformance.lua'))
            timing=performance_cache.get(i)
            if timing:extras.setdefault('skill_performance' if table=='Skill' else 'effect_performance',{})[str(i)]=parse(timing[2])
    for token,values in constant_edges.items():
        if len({(tuple(e['path']),e['target']) for e in values})>1:raise ValueError('共享常量表达式被用于不同编号类型，不能安全重映射')
        edges[token].extend(values)
    packet=dict(format=FORMAT,version=VERSION,kind=kind,root=ident,nodes=nodes,edges=edges,anchors=anchors,role_groups=role_groups,extras=extras,
                enums={k:v for k,v in store.enums.items() if k in ('SkillEffectDescription.SED_SkillLogic_CommonInitiativeSkill','SkillEffectDescription.SED_SkillLogic_CommonFanJiProcess')})
    from object_native_wishes import mark_native_references
    mark_native_references(packet)
    extras.setdefault('compatibility_warnings',[]).extend(getattr(store,'mod_warnings',[]))
    extras['dependency_report']=check_complete(packet)
    return packet

def normalize_owned_roles(packet):
    # A separately exported placement Task can anchor its owning Role, while
    # the merged character packet already contains every owned variant.
    for rid,variants in packet.get('role_groups',{}).items():
        token=key('@Role',int(rid));anchor=packet.get('anchors',{}).get(token)
        if anchor is None:continue
        actual=sorted(n['id'] for n in packet['nodes'].values() if n['table']=='Role' and n['row'].get('RoleID')==int(rid))
        if sorted(variants)!=actual or not actual or anchor!={'variants':actual}:
            raise ValueError('包内人物与外部人物引用不一致：'+token)
        del packet['anchors'][token]
    return packet

def write_bundle(path,packet,files=None):
    packet=normalize_owned_roles(copy.deepcopy(packet))
    validate_packet(packet)
    files=files or {};data=json.dumps(packet,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf8')
    manifest={'data_sha256':sha(data),'files':{n:sha(raw) for n,raw in files.items()}}
    path=Path(path);fd,temp=tempfile.mkstemp(prefix='.mjh_export_',suffix='.tmp',dir=path.parent);os.close(fd)
    try:
        with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED) as z:
            z.writestr('object.json',data);z.writestr('manifest.json',json.dumps(manifest))
            for name,raw in files.items():z.writestr(name,raw)
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)

def read_bundle(path,allow_legacy=False):
    with zipfile.ZipFile(path) as z:
        if sum(i.file_size for i in z.infolist())>MAX_SIZE:raise ValueError('配置包超过 80 MB')
        if len(z.namelist())!=len(set(z.namelist())):raise ValueError('配置包包含重复文件')
        manifest=json.loads(z.read('manifest.json'));data=z.read('object.json')
        if sha(data)!=manifest['data_sha256']:raise ValueError('配置包校验失败')
        packet=json.loads(data);files={}
        for name,h in manifest.get('files',{}).items():
            mobile=bool(re.fullmatch(r'mobile/[0-9a-f]{32}/(?:binding\.lua|model\.skel|model\.atlas|texture\.png)',name))
            if not mobile and not re.fullmatch(r'images/[0-9a-f]{64}\.png',name):raise ValueError('配置包资源路径无效')
            raw=z.read(name)
            if sha(raw)!=h:raise ValueError('图片校验失败')
            if mobile:
                files[name]=raw;continue
            from PIL import Image
            with Image.open(io.BytesIO(raw)) as im:
                if im.format!='PNG' or im.width*im.height>20000000:raise ValueError('配置包图片格式／尺寸无效')
                im.verify()
            files[name]=raw
        if packet.get('version')==VERSION:normalize_owned_roles(packet)
        validate_packet(packet,legacy=allow_legacy and packet.get('version')==1)
        return packet,files

def validate_packet(p,legacy=False,reference_rules=None):
    if p.get('format')==FORMAT and p.get('version')==1 and not legacy:raise ValueError('此配置包由旧版依赖识别规则生成，请用 V2.0.32 重新导出或修复后再导入；未写入游戏')
    if p.get('format')!=FORMAT or p.get('version')!=(1 if legacy else VERSION) or p.get('kind') not in ('Martial','Role','Item'):raise ValueError('不是所选对象配置包')
    if not isinstance(p.get('nodes'),dict) or not 1<=len(p['nodes'])<=30000:raise ValueError('配置包记录数量无效')
    for token,node in p['nodes'].items():
        table=node['table'];ident=node['id']
        if table not in SCHEMAS or table in ANCHORS or type(ident) is not int or not 0<ident<2147483647 or token!=key(table,ident):raise ValueError('配置记录编号／类型无效')
        row=node['row']
        if not isinstance(row,dict) or row.get('BaseID')!=ident or set(row)-set(SCHEMAS[table]):raise ValueError('配置记录字段无效：'+token)
        # Roundtrip validates scalar and nested protobuf value types.
        for field,value in row.items():encode_field(field,value,table)
        for edge in p.get('edges',{}).get(token,[]):
            if edge['target'] not in p['nodes'] and edge['target'] not in p.get('anchors',{}) and not (edge['target'].startswith('@Role:') and edge['target'].split(':')[1] in p.get('role_groups',{})):raise ValueError('配置包关联数据缺失')
            value=row
            for part in edge['path']:value=value[part]
            if str(value)!=edge['target'].split(':')[1]:raise ValueError('配置包引用位置不匹配')
    # Rebuild all recognized links to prevent omissions or changing constant
    # stats into arbitrary references in a tampered edge list.
    if legacy:return # Data-only repair reads rows, then rebuilds all links.
    check_complete(p)
    enums=p.get('enums',{})
    extra={}
    from event_condition_refs import packet_links
    extra.update(packet_links(p['nodes']))
    reference_fn,constant_fn=reference_rules or (references,constant_links)
    for token,node in p['nodes'].items():
        if node['table']!='SkillEffect':continue
        for child,target,value in constant_fn(node['row'],lambda i:p['nodes'].get(key('SkillEffect',i),{}).get('row',{})):
            extra.setdefault(key('SkillEffect',child),set()).add((('EventArg1',0),key(target,value)))
    for token,node in p['nodes'].items():
        recognized={(tuple(path),key(t,i)) for path,t,i in reference_fn(node['table'],node['row'],enums)}
        recognized.update(extra.get(token,set()))
        supplied={(tuple(e['path']),e['target']) for e in p['edges'].get(token,[])}
        if recognized!=supplied:raise ValueError('配置包引用清单不完整或包含非引用字段：'+token)

def allocate(packet,store,defer_effects=False):
    mapping={};occupied={}
    for token,node in packet['nodes'].items():
        table=node['table']
        if table in occupied:continue
        occupied[table]=set(store.table(table))
        # Updates/Steam verification can replace the primary table while an
        # older native copy survives in StreamingAssets or resources.assets.
        # Reserve IDs in every copy that plan_import will append to.
        for folder in ('TableData','DreamRivakes_Data/StreamingAssets'):
            raw=store.read(store.root/folder/(table+'.bytes'))
            if raw:occupied[table].update(indexed_rows(raw)[0])
        if table in store.assets.scripts:
            _,q,n=store.assets.scripts[table]
            occupied[table].update(indexed_rows(store.assets.data[q+4:q+4+n])[0])
        if table=='SkillEffect' and packet.get('extras',{}).get('effect_performance'):
            from martial_editor import performance_blocks
            occupied[table].update(performance_blocks(store.assets.script('SkillPerformance.lua')))
        if table=='Skill':
            from martial_editor import performance_blocks
            occupied[table].update(performance_blocks(store.assets.script('SkillPerformance.lua')))
            occupied[table].update((i-400000000)//1000 for i in store.table('SkillEffect') if 400000000<=i<500000000)
        if table=='RoleModel':
            from role_animation import animation_rows
            occupied[table].update(animation_rows(store.assets.script('SpineAnimaitionTime.lua'))) 
    occupied['@Role']={r['RoleID'] for r in store.table('Role').values()} if packet.get('role_groups') else set()
    tokens=[*packet['nodes'],*(key('@Role',int(i)) for i in packet.get('role_groups',{}))]
    reserved={}
    for token in tokens:
        table,old=token.split(':');reserved.setdefault(table,set()).add(int(old))
    for token in tokens:
        table,old=token.split(':');old=int(old);used=occupied[table]
        if defer_effects:
            from object_reuse import EFFECT_TABLES
            if table in EFFECT_TABLES:
                mapping[token]=-len(mapping)-1
                continue
        from role_model_ids import safe as safe_model_id
        if old not in used and (table!='RoleModel' or safe_model_id(old)) and (table!='Martial' or 0<old<=65535):new=old
        else:
            lo,hi=(16000,32767) if table=='RoleModel' else (30000,65535) if table=='Skill' else (156,255) if table=='SuperImposed' else (60000,120000) if table=='Buff' else (70000,200000) if table=='Gift' else (20000,29999) if table=='Martial' else (1700000000,1700999999) if table in ('Range','MartialRange') else (2000000000,2099999999) if table=='Language' else (1700000000,1799999999) if table=='@Role' else (1600000000,1699999999)
            for _ in range(10000):
                if table=='Language':
                    from language_routing import split_size
                    size=split_size(store.assets);shards=[int(re.fullmatch(r'Language(\d+)\.lua',s)[1]) for s in store.assets.scripts if re.fullmatch(r'Language(\d+)\.lua',s)]
                    shard=max(s for s in shards if s*size<2100000000);low=shard*size;high=min((shard+1)*size-1,2099999999);new=low+secrets.randbelow(high-low+1)
                else:new=secrets.randbelow(hi-lo+1)+lo
                if new not in used and new not in reserved[table]:break
            else:raise ValueError('随机编号区间不足：'+table)
        mapping[token]=new;used.add(new)
    return mapping

def remap_rows(packet,mapping,active=None):
    rows={}
    for token,node in packet['nodes'].items():
        if active is not None and token not in active:continue
        table=node['table'];row=copy.deepcopy(node['row']);row['BaseID']=mapping[token]
        for edge in packet['edges'][token]:
            target=edge['target'];value=mapping.get(target,int(target.split(':')[1]));obj=row
            for part in edge['path'][:-1]:obj=obj[part]
            obj[edge['path'][-1]]=str(value) if edge.get('string') else value
        rows.setdefault(table,{})[mapping[token]]=row
    # Task states form their own namespace, independent of Task/TaskEdge IDs.
    states={node['row']['RootState']:rows['Task'][mapping[token]] for token,node in packet['nodes'].items() if node['table']=='Task' and (active is None or token in active)}
    statemap={old:row['BaseID'] for old,row in states.items()}
    for row in rows.get('Task',{}).values():row['RootState']=statemap.get(row['RootState'],row['RootState'])
    for row in rows.get('TaskEdge',{}).values():row['StateID']=statemap.get(row['StateID'],row['StateID'])
    return rows

def append_rows(raw,table,rows,seeds):
    current,index=indexed_rows(raw);added={}
    for ident,row in rows.items():
        if ident in current:raise ValueError('编号映射仍发生冲突：'+table+' '+str(ident))
        seed=seeds[ident]
        replacements={SCHEMAS[table][k]['number']:encode_field(k,v,table) for k,v in row.items()}
        added[ident]=patch(seed,replacements)
    wanted=index+sorted(added);indexed=set(index);order=wanted+[i for i in current if i not in indexed]
    out=bytearray();done=False
    for f in fields(raw):
        if f.number in (1,2):
            if not done:
                out.extend(numeric_list(1,wanted))
                for i in order:out.extend(encoded(2,added.get(i,current.get(i)),2))
                done=True
        else:out.extend(f.raw)
    if not done:raise ValueError('目标配置表缺少记录区')
    result=bytes(out);check,idx=indexed_rows(result)
    for ident,row in rows.items():
        actual=decode(check[ident],table,SCHEMAS)
        if any(actual[k]!=v for k,v in row.items()):raise ValueError('导入记录回读失败：'+table)
    if any(check[i]!=v for i,v in current.items()):raise ValueError('已有配置发生变化')
    return result

def plan_import(store,packet,mapping,active=None,reference_rules=None,native_aliases=None):
    validate_packet(packet,reference_rules=reference_rules)
    if any(store.enums.get(k)!=v for k,v in packet.get('enums',{}).items()):raise ValueError('目标技能表达式类型与来源游戏不一致')
    for token,row in packet.get('anchors',{}).items():
        table,i=token.split(':')
        if native_aliases and table in native_aliases:
            actual=store.table(native_aliases[table]).get(int(i))
            if actual!=row:raise ValueError('原生持有条件记录已变化：'+token)
        elif table=='@Role':
            actual=sorted(r['BaseID'] for r in store.table('Role').values() if r.get('RoleID')==int(i))
            if row!={'variants':actual} or not actual:raise ValueError('关联原生人物在目标中不存在或变体不同：'+token)
        elif isinstance(row,dict) and 'native_chain_sources' in row:
            common=key('RoleWishQuest',195)
            if common not in packet['nodes'] or mapping.get(common)!=195 or (active is not None and common in active):raise ValueError('原生通用任务链必须经过完整校验并复用，未导入')
            from object_native_wishes import validate_native_reference
            validate_native_reference(packet,store,token,row)
        elif row=={'missing':True}:
            if table not in SCHEMAS or store.table(table).get(int(i)) is not None:raise ValueError('来源缺失的记录在目标中已有定义：'+token)
        elif table not in ANCHORS or not anchor_compatible(table,row,store.table(table).get(int(i))):raise ValueError('目标游戏公共场景／资源配置不同：'+token)
    rows=remap_rows(packet,mapping,active);payloads={};assets=store.assets.data
    for table,records in rows.items():
        seeds={mapping[token]:base64.b64decode(n['wire'],validate=True) for token,n in packet['nodes'].items() if n['table']==table}
        for directory in ('TableData','DreamRivakes_Data/StreamingAssets'):
            path=store.root/directory/(table+'.bytes');raw=store.read(path)
            if raw:payloads[path]=append_rows(raw,table,records,seeds)
        a=Assets(assets)
        if table in a.scripts:
            _,q,n=a.scripts[table];assets=a.replace_blob(table,append_rows(a.data[q+4:q+4+n],table,records,seeds))
        a=Assets(assets);resources=[s for s in a.scripts if re.fullmatch(r'Language\d*\.lua' if table=='Language' else re.escape(table)+r'\d*\.lua',s)]
        if not resources:raise ValueError('目标客户端缺少 '+table+' 表')
        grouped={}
        for ident,row in records.items():
            resource=resource_for(a,ident) if table=='Language' else resources[0]
            grouped.setdefault(resource,{})[ident]=row['Ch_Text'] if table=='Language' else row
        for resource,rs in grouped.items():
            a=Assets(assets);assets=a.replace_script(resource,patch_lua_rows(a.script(resource),rs,table=='Language'))
        mods={}
        for row in records.values():
            owner='role_editor' if table in ('Role','RoleAttr','RoleModel','NpcEvolute','Task','TaskEdge','TaskEvent','Behavior','Story','RoleTitle') else 'martial_editor'
            if table=='Item' and 1 in row.get('Feature',[]) and row.get('ItemType') not in (15,16):owner='warehouse_editor'
            mods.setdefault(owner,[]).append(row)
        for owner,values in mods.items():
            path=store.root/'ModProject/GameProject/Mod_MJH/Json'/f'{table}_{owner}.json';raw=store.read(path)
            obj=json.loads(raw.decode('utf8')) if raw else {'Items':[]}
            for row in values:
                r=copy.deepcopy(row)
                if table=='Language':r['Text']=r.pop('Ch_Text')
                obj['Items'].append(r)
            payloads[path]=json.dumps(obj,ensure_ascii=False,indent=2).encode()
    from lua_data import dump
    from martial_editor import performance_blocks
    from role_animation import animation_rows
    for category,table,script,reader,ending in [('skill_performance','Skill','SkillPerformance.lua',performance_blocks,r'\}\s*return\s+t\s*$'),('effect_performance','SkillEffect','SkillPerformance.lua',performance_blocks,r'\}\s*return\s+t\s*$'),('model_timing','RoleModel','SpineAnimaitionTime.lua',animation_rows,r'\}\s*return\s+spineAnimaition\b')]:
        values=packet['extras'].get(category,{})
        if not values:continue
        a=Assets(assets);text=a.script(script);entries=[]
        existing=reader(text)
        for old,value in values.items():
            if active is not None and key(table,int(old)) not in active:continue
            ident=mapping[key(table,int(old))]
            if ident in existing:raise ValueError('动画编号已被占用')
            value=copy.deepcopy(value)
            if category in ('skill_performance','effect_performance') and isinstance(value,dict) and 'id' in value:value['id']=ident
            entries.append(f'[{ident}] = '+dump(value)+',\n')
        match=re.search(ending,text)
        if not match:raise ValueError('目标动画表结构不兼容')
        assets=a.replace_script(script,text[:match.start()]+''.join(entries)+text[match.start():])
    payloads[store.root/'DreamRivakes_Data/resources.assets']=assets
    return payloads,dict(store.reads),rows
