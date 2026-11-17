"""Martial configuration drafts and lossless, synchronized game-table writes."""
import copy, json, math, re, struct
from contextlib import contextmanager
from pathlib import Path
from codec import decode, fields, encoded, patch, numeric_list, read_varint, varint
from client_config import Assets, enum_values, lua_rows, literal
from engine import SCHEMAS, table_rows, META

TABLES = ('Martial','MartialItem','MartialFilter','Skill','SkillEffect','SuperImposed','Gift','Item','Role','Language','MatGrowUPAttrGrade','AoYi','Range','MartialRange')
SECTIONS = {'成长':'GrowProIDs', '招式':'MartMovIDs', '解锁':'UnlockClauses'}
DEPARTS = {1:'暗器',2:'刀法',3:'剑法',4:'内功',5:'奇门',6:'轻功',7:'拳掌',8:'腿法',9:'医术',10:'外功',11:'登场技',12:'群医',13:'阵法',14:'毒系',15:'所有'}
RANKS = {1:'白',2:'绿',3:'蓝',4:'紫',5:'橙',6:'金',7:'暗金'}
ROW_RE = r'(?m)^([ \t]*\[(\d+)\]\s*=\s*)(\{[^\r\n]+\}),?'
LANG_RE = r'(?m)^([ \t]*\[(\d+)\]\s*=\s*)("(?:\\.|[^"\\])*"),?'

def performance_blocks(text):
    result={}
    for m in re.finditer(r'(?m)^\s*\[(0x[0-9a-fA-F]+|\d+)\]\s*=\s*\{',text):
        start=m.end()-1;depth=0;quote=None;escape=False
        for pos in range(start,len(text)):
            char=text[pos]
            if quote:
                if escape:escape=False
                elif char=='\\':escape=True
                elif char==quote:quote=None
            elif char in ('"',"'"):quote=char
            elif char=='{':depth+=1
            elif char=='}':
                depth-=1
                if depth==0:result[int(m[1],0) if m[1].startswith('0x') else int(m[1])]=(m.start(),pos+1,text[start:pos+1]);break
    return result

def patch_performances(text,mapping):
    blocks=performance_blocks(text);replacements=[];additions=[]
    for ident,source in mapping.items():
        if source not in blocks:raise ValueError('所选招式没有原生动画模板：'+str(source))
        body=re.sub(r'(\["id"\]\s*=\s*)(0x[0-9a-fA-F]+|\d+)',lambda m:m[1]+str(ident),blocks[source][2],count=1)
        entry='\n\t['+str(ident)+'] = '+body
        if ident in blocks:replacements.append((*blocks[ident][:2],entry))
        else:additions.append(entry+',')
    for start,end,entry in sorted(replacements,reverse=True):text=text[:start]+entry+text[end:]
    if additions:
        match=re.search(r'\}\s*return\s+t\s*$',text)
        if not match:raise ValueError('招式动画表结构不支持')
        text=text[:match.start()]+'\n'.join(additions)+'\n'+text[match.start():]
    return text

def lua_value(obj):
    if isinstance(obj,dict):return '{'+''.join((k if re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*',k) else '['+lua_value(k)+']')+'='+lua_value(v)+',' for k,v in obj.items())+'}'
    if isinstance(obj,list):return '{'+','.join(lua_value(v) for v in obj)+'}'
    if isinstance(obj,str):return '"'+obj.replace('\\','\\\\').replace('"','\\"').replace('\n','\\n').replace('\r','\\r').replace('\t','\\t')+'"'
    if isinstance(obj,bool):return 'true' if obj else 'false'
    if not isinstance(obj,(int,float)) or not math.isfinite(obj):raise ValueError('配置值必须是有限数值')
    return str(obj)

def patch_lua_rows(text, replacements, language=False):
    seen=set();pattern=LANG_RE if language else ROW_RE
    def change(m):
        ident=int(m[2])
        if ident not in replacements:return m[0]
        seen.add(ident)
        return m[1]+lua_value(replacements[ident])+','
    out=re.sub(pattern,change,text)
    missing=set(replacements)-seen
    if missing:
        matches=list(re.finditer(pattern,out))
        if not matches:raise ValueError('客户端配置没有可插入的记录')
        pos=matches[-1].end()
        out=out[:pos]+''.join('\n  ['+str(i)+']='+lua_value(replacements[i])+',' for i in sorted(missing))+out[pos:]
    return out

def encode_field(key,value,name):
    spec=SCHEMAS[name][key];number=spec['number'];typ=spec['type']
    seq=value if spec['label']==3 else [value]
    if not isinstance(seq,list):raise ValueError('数组字段格式不正确：'+key)
    result=b''
    for v in seq:
        if typ==9:result+=encoded(number,str(v).encode('utf-8'),2)
        elif typ==11:
            if not v and spec['label']!=3:continue
            sub=spec['type_name'].split('.')[-1]
            result+=encoded(number,b''.join(encode_field(k,x,sub) for k,x in v.items() if k in SCHEMAS[sub]),2)
        elif typ in (1,2):
            if not math.isfinite(float(v)):raise ValueError('数值必须有限')
            result+=varint((number<<3)|(1 if typ==1 else 5))+struct.pack('<d' if typ==1 else '<f',float(v))
        else:
            if not isinstance(v,int):raise ValueError('整数字段格式不正确：'+key)
            if typ==5 and not -(1<<31)<=v<(1<<31):raise ValueError(key+' 超出 32 位整数范围')
            if typ==3 and not -(1<<63)<=v<(1<<63):raise ValueError(key+' 超出 64 位整数范围')
            result+=encoded(number,v)
    return result

def indexed_rows(data):
    rows={};index=[]
    for f in fields(data):
        if f.number==2 and f.wire==2:
            ids=[x.value for x in fields(f.value) if x.number==1 and x.wire==0]
            if len(ids)!=1 or ids[0] in rows:raise ValueError('配置记录编号异常')
            rows[ids[0]]=f.value
        elif f.number==1:
            if f.wire==0:index.append(f.value)
            elif f.wire==2:
                pos=0
                while pos<len(f.value):v,pos=read_varint(f.value,pos);index.append(v)
            else:raise ValueError('配置索引格式不支持')
    if len(index)!=len(set(index)) or not set(index).issubset(rows):raise ValueError('配置索引与记录不一致')
    return rows,index

def patch_table(data,name,changes,sources=None):
    rows,index=indexed_rows(data);updated={};sources=sources or {}
    for ident,delta in changes.items():
        base=rows.get(ident,rows.get(sources.get(ident),b''))
        replacements={SCHEMAS[name][k]['number']:encode_field(k,v,name) for k,v in delta.items() if k in SCHEMAS[name]}
        replacements[1]=encoded(1,ident)
        updated[ident]=patch(base,replacements)
    new_ids=sorted(set(changes)-set(rows))
    # The native manager maps IndexIDs[i] to Items[i], rather than looking at
    # each record's BaseID. Keep unindexed records at the end, after all indexed
    # records (including new ones). Appending index IDs and records separately
    # shifts every new lookup when the original table has unindexed tail rows.
    wanted=index+new_ids
    indexed=set(wanted)
    ordered=wanted+[ident for ident in rows if ident not in indexed]
    out=bytearray();index_written=False;rows_written=False
    for f in fields(data):
        if f.number==1 and new_ids:
            if not index_written:out.extend(numeric_list(1,index+new_ids));index_written=True
        elif f.number==2:
            if not rows_written:
                if new_ids and not index_written:
                    out.extend(numeric_list(1,wanted));index_written=True
                for ident in ordered:
                    out.extend(encoded(2,updated.get(ident,rows.get(ident)),2))
                rows_written=True
        else:out.extend(f.raw)
    if not rows_written:
        if new_ids and not index_written:out.extend(numeric_list(1,wanted))
        for ident in ordered:out.extend(encoded(2,updated.get(ident,rows.get(ident)),2))
    result=bytes(out);check,actual_index=indexed_rows(result)
    if list(check)[:len(actual_index)]!=actual_index:
        raise ValueError('配置索引位置与记录顺序不一致：'+name)
    for ident,delta in changes.items():
        row=decode(check[ident],name,SCHEMAS)
        for key,value in delta.items():
            if key in SCHEMAS[name] and row[key]!=value:
                if isinstance(value,float) and abs(row[key]-value)<1e-5:continue
                raise ValueError(f'{name} {ident} 的 {key} 回读不一致')
    return result

class MartialLibrary:
    def __init__(self,root):
        self.root=Path(root).resolve();self.originals={};self.tables={};self.changes={n:{} for n in TABLES};self.sources={n:{} for n in TABLES}
        self.assets_path=self.root/'DreamRivakes_Data/resources.assets'
        raw=self.assets_path.read_bytes();self.originals[self.assets_path]=raw;self.assets=Assets(raw)
        self.enums=enum_values(self.assets.script('common.lua'))|enum_values(self.assets.script('Enum.lua'))
        self.mod_warnings=[]
        from client_shards import prepare,merge,names as shard_names
        self.overrides={}
        prepare(self)
        self.resources={};self.resource_rows={};self.locations={};self.overrides={};self.own_jsons={}
        for name in TABLES:
            path=self.root/f'TableData/{name}.bytes';raw=path.read_bytes();self.originals[path]=raw
            if name=='Language':
                from read_cache import native_language
                self.tables[name]={i:dict(row) for i,row in native_language(raw)}
            elif name=='SkillEffect':
                from read_cache import native_effects
                self.tables[name]=native_effects(raw)
            else:
                rows,_=indexed_rows(raw)
                self.tables[name]={i:decode(row,name,SCHEMAS) for i,row in rows.items()}
            native_rows=copy.deepcopy(self.tables[name])
            if name=='Language':names=[k for k in self.assets.scripts if re.fullmatch(r'Language\d+\.lua',k)]
            elif name=='SkillEffect':names=['SkillEffect.lua']+sorted(k for k in self.assets.scripts if re.fullmatch(r'SkillEffect\d+\.lua',k))
            else:names=shard_names(self.assets,name)
            self.resources[name]=names;self.locations[name]={};self.overrides[name]={}
            for resource in names:
                text=self.assets.script(resource);self.enums.update(enum_values(text))
                if name=='Language':
                    from read_cache import language_script
                    client={i:{'BaseID':i,'Ch_Text':value} for i,value in language_script(text)}
                elif name=='SkillEffect':
                    from read_cache import effect_script
                    client=effect_script(text,self.enums)
                else:client=lua_rows(text,name,self.enums)
                self.resource_rows[resource]=client
                merge(self,name,resource,client)
            client_rows=copy.deepcopy(self.tables[name])
            jsondir=self.root/'ModProject/GameProject/Mod_MJH/Json'
            own=jsondir/(name+'_martial_editor.json');self.own_jsons[name]=own
            if jsondir.exists():
                for path in sorted(jsondir.glob(name+'_*.json')):
                    raw=path.read_bytes();self.originals[path]=raw
                    from mod_rows import read_rows
                    rows=read_rows(raw,name,SCHEMAS,self.mod_warnings,path.name)
                    from editor_data_repair import role_rows,remember
                    if name=='Role':rows=role_rows(self,path,rows,native_rows)
                    if path==own:remember(self,name,rows,native_rows,client_rows)
                    for row in rows:
                        ident=int(row['BaseID'])
                        if path!=own:self.overrides[name].setdefault(ident,[]).append(path.name)
                        row=copy.deepcopy(row)
                        if name=='Language' and 'Text' in row:row['Ch_Text']=row.pop('Text')
                        self.tables[name].setdefault(ident,{}).update(row)
            # Newly imported/retained MOD rows may have no client row yet.
            # Use that row's actual target shard defaults, including Lua-only
            # fields added by the game. Never invent protobuf field numbers.
            if name!='Language':
                defaults={}
                for resource in names:
                    match=re.search(r'(?m)^local '+re.escape(name)+r'Default\s*=\s*(\{[^\r\n]+)',self.assets.script(resource))
                    defaults[resource]=literal(match[1],self.enums) if match else {}
                for ident,row in self.tables[name].items():
                    for key,value in defaults.get(self.locations[name].get(ident,names[0]),{}).items():
                        if key not in row:row[key]=copy.deepcopy(value)
        from growth_runtime import custom_values
        self.native_clause_original={i:copy.deepcopy(r) for i,r in self.tables['MartialItem'].items() if any(custom_values(r,slot) for slot in (1,2))}
        self.compat_notes=[]
        from editor_data_repair import finish
        finish(self)
        from shadow_compat import prepare_routes
        prepare_routes(self)
        self.attr_names=META['attributes'];self._undo=None
        self.percent={}
        raw=(self.root/'TableData/AttrIsPercent.bytes').read_bytes()
        self.originals[self.root/'TableData/AttrIsPercent.bytes']=raw
        for r in table_rows(raw):
            row=decode(r,'AttrIsPercent',SCHEMAS);self.percent[row['BaseID']]=row
        self.labels={}
        enumtext=self.assets.script('Enum.lua')+'\n'+self.assets.script('common.lua')
        for category,body in re.findall(r'(?m)^\s*(\w+)\s*=\s*\{(.*?)^\s*\}',enumtext,re.S):
            for key,number,label in re.findall(r'^\s*(\w+)\s*=\s*(-?\d+)\s*[;,]\s*--\s*([^\r\n]+)',body,re.M):
                self.labels[(category,int(number))]=label.strip()
        line_labels={key:label.strip() for key,label in re.findall(r'(?m)^\s*(\w+)\s*=\s*-?\d+\s*[;,]\s*--\s*([^\r\n]+)',enumtext)}
        for key,value in self.enums.items():
            category,_,field=key.partition('.')
            if field in line_labels:self.labels[category,value]=line_labels[field]
        self.clause_owned={};self.skill_owned={};self.book_templates={}
        self.animations={};self.animation_path=self.root/'装备编辑器配置/武学动画映射.json'
        animation_raw=self.animation_path.read_bytes() if self.animation_path.exists() else None
        self.originals[self.animation_path]=animation_raw
        if animation_raw:self.animations={int(i):int(v) for i,v in json.loads(animation_raw.decode('utf-8')).items()}
        self.animation_original=dict(self.animations)
        self.origin_path=self.root/'装备编辑器配置/武学模板来源.json'
        origin_raw=self.origin_path.read_bytes() if self.origin_path.exists() else None
        self.originals[self.origin_path]=origin_raw
        origins=json.loads(origin_raw.decode('utf-8')) if origin_raw else {}
        self.origins={n:{int(i):int(v) for i,v in origins.get(n,{}).items()} for n in ('Martial','Skill')}
        self.origin_original=copy.deepcopy(self.origins)
        retired=self.root/'装备编辑器配置/武学安全编号迁移.json'
        retired_raw=retired.read_bytes() if retired.exists() else None
        self.originals[retired]=retired_raw
        self.retired_martials=set(map(int,json.loads(retired_raw.decode('utf8')))) if retired_raw else set()
        self.icon_path=self.root/'装备编辑器配置/武学图标映射.json'
        icon_raw=self.icon_path.read_bytes() if self.icon_path.exists() else None
        self.originals[self.icon_path]=icon_raw
        self.icons=json.loads(icon_raw.decode('utf-8')) if icon_raw else {}
        self.icon_original=copy.deepcopy(self.icons);self.icon_files={};self.growth=None
        self.scope_path=self.root/'装备编辑器配置/新增作用范围.json'
        scope_raw=self.scope_path.read_bytes() if self.scope_path.exists() else None
        self.originals[self.scope_path]=scope_raw
        self.scope_groups=json.loads(scope_raw.decode('utf-8')) if scope_raw else {}
        self.scope_original=copy.deepcopy(self.scope_groups)
        self.cap_original_path=self.root/'装备编辑器配置/自建武学原上限.json'
        cap_raw=self.cap_original_path.read_bytes() if self.cap_original_path.exists() else None
        self.originals[self.cap_original_path]=cap_raw
        self.created_caps=json.loads(cap_raw.decode('utf-8')) if cap_raw else {}
        self.performance_text=self.assets.script('SkillPerformance.lua');self.performances=performance_blocks(self.performance_text)
        self.book_icons={(r['Rank'],r['Kftype']):r['SecretBookIcon'] for r in lua_rows(self.assets.script('RankSecretBookIcon.lua'),'RankSecretBookIcon',self.enums).values()}
        for item in self.tables['Item'].values():
            if item.get('MartialID') and item.get('ItemType') in (15,16):self.book_templates.setdefault(item['ItemType'],item['BaseID'])
        self.log_base_tables={n:dict(rows) for n,rows in self.tables.items()}
        # Steam can leave old JSON while removing feature-generated dependencies.
        # Keep such a martial visible but do not silently restore a broken graph.
        for mid in list(self.changes['Martial']):
            try:self.effect_audit(mid)
            except (KeyError,ValueError) as error:
                del self.changes['Martial'][mid]
                self.mod_warnings.append('旧武学编辑记录依赖不完整，未自动恢复：'+str(mid)+'（'+str(error)+'）；请先恢复对应功能或修复词条')


    def text(self,ident):return self.tables['Language'].get(ident,{}).get('Ch_Text',str(ident) if ident else '')
    def name(self,ident):return self.text(self.tables['Martial'][ident]['NameID'])
    def modified(self):return bool(getattr(self,'aoyi_runtime_requested',False)) or bool(getattr(self,'client_repairs',{})) or any(self.changes.values()) or self.animations!=self.animation_original or self.origins!=self.origin_original or self.icons!=self.icon_original or self.scope_groups!=self.scope_original or bool(self.icon_files) or bool(self.growth and self.growth.changes)
    @contextmanager
    def edit(self):
        if self._undo is not None:
            yield;return
        before=(copy.deepcopy(self.changes),copy.deepcopy(self.sources),dict(self.clause_owned),copy.deepcopy(self.skill_owned),dict(self.animations),copy.deepcopy(self.origins),copy.deepcopy(self.icons),dict(self.icon_files),copy.deepcopy(self.growth),copy.deepcopy(self.scope_groups))
        self._undo={}
        try:yield
        except Exception:
            for (name,ident),row in self._undo.items():
                if row is None:self.tables[name].pop(ident,None)
                else:self.tables[name][ident]=row
            self.changes,self.sources,self.clause_owned,self.skill_owned,self.animations,self.origins,self.icons,self.icon_files,self.growth,self.scope_groups=before
            raise
        finally:self._undo=None
    def new_id(self,name,start=1600000000):
        if name=='Martial':
            # Native battle AI stores a chosen martial parameter in 16 bits.
            # Table loading accepts larger IDs, but NPC auto casting cannot.
            for ident in range(20000,30000):
                if ident not in self.tables[name]:return ident
            raise ValueError('可用于原生战斗 AI 的武学编号已耗尽（20000～29999）')
        if name=='Language':
            from language_routing import next_id
            return next_id(self,start)
        if name=='Skill':
            # Keep authored skills in a small unused range for battle compatibility.
            occupied={(i-400000000)//1000 for i in self.tables['SkillEffect'] if 400000000<=i<500000000}
            for ident in range(30000,65536):
                if ident not in self.tables[name] and ident not in self.performances and ident not in occupied:return ident
            raise ValueError('战斗招式编号已耗尽（30000～65535）')
        used=self.tables[name];ident=max(start,max((i for i in used if i>=start),default=start-1)+1)
        if ident>2100000000:raise ValueError('可用配置编号已耗尽')
        return ident
    def set(self,name,ident,delta):
        if ident in self.overrides[name]:raise ValueError(f'{name} {ident} 被其他模组覆盖：'+', '.join(self.overrides[name][ident]))
        if self._undo is not None and (name,ident) not in self._undo:self._undo[name,ident]=copy.deepcopy(self.tables[name].get(ident))
        if ident not in self.tables[name]:self.tables[name][ident]={'BaseID':ident}
        delta=copy.deepcopy(delta);delta['BaseID']=ident
        self.tables[name][ident]={**self.tables[name][ident],**delta};self.changes[name].setdefault(ident,{}).update(delta)
    def clone(self,name,ident,new=None):
        new=self.new_id(name) if new is None else new
        if new in self.tables[name]:raise ValueError('配置编号已被占用：'+str(new))
        self.sources[name][new]=self.sources[name].get(ident,ident)
        if name=='Skill':self.origins['Skill'][new]=self.origins['Skill'].get(ident,self.animations.get(ident,ident))
        self.set(name,new,copy.deepcopy(self.tables[name][ident]));return new
    def set_text(self,ident,text):
        new=self.new_id('Language');self.set('Language',new,{'Ch_Text':text});return new

    def new_martial(self,template,name):
        if not name.strip():raise ValueError('请输入新武学名称')
        new=self.new_id('Martial',200000)
        self.sources['Martial'][new]=template
        self.origins['Martial'][new]=self.native_source(template)
        row=copy.deepcopy(self.tables['Martial'][template]);row['BaseID']=new
        row['NameID']=self.set_text(0,name.strip());row['DesID']=self.set_text(0,self.text(row.get('DesID',0)))
        # A new martial starts with no exclusive owners; the user selects them.
        row['Exclusive']=[];row['Display']=1;row['AlowEdit']=1
        from caps import cap_summary
        if cap_summary(self.root)[1]:row['LvLimit']=30
        self.set('Martial',new,row)
        for key in SECTIONS.values():
            for index in range(len(row.get(key,[]))):self.own_clause(new,key,index)
        self.sync_move_names(new)
        self.repair_bindings(new)
        return new

    def update_basic(self,ident,values):
        row=self.tables['Martial'][ident];delta=dict(values)
        if 'name' in delta:
            text=delta.pop('name').strip()
            if not text:raise ValueError('武学名称不能为空')
            if text!=self.name(ident):delta['NameID']=self.set_text(row['NameID'],text)
        if 'description' in delta:
            text=delta.pop('description')
            if text!=self.text(row.get('DesID',0)):delta['DesID']=self.set_text(row.get('DesID',0),text)
        if 'LvLimit' in delta and not 1<=delta['LvLimit']<=1000:raise ValueError('武学上限范围为 1～1000')
        if delta.get('Rank',row.get('Rank')) not in RANKS:raise ValueError('请选择有效品质')
        if delta.get('DepartEnum',row.get('DepartEnum')) not in DEPARTS:raise ValueError('请选择有效类别')
        if not 0<=delta.get('ColdTime',row.get('ColdTime',0))<=10000:raise ValueError('冷却回合范围为 0～10000')
        for rid in delta.get('Exclusive',[]):
            if rid not in {r.get('RoleID') for r in self.tables['Role'].values()}:raise ValueError('专属人物编号不存在')
        if len(delta.get('LearnCondition',row.get('LearnCondition',[])))!=len(delta.get('LearnConditionValue',row.get('LearnConditionValue',[]))):raise ValueError('学习条件与数值数量不一致')
        self.set('Martial',ident,delta)
        if 'NameID' in delta:self.sync_move_names(ident)

    def sync_move_names(self,mid):
        m=self.tables['Martial'][mid];moves=m.get('MartMovIDs',[])
        for index,cid in enumerate(moves):
            for slot in (1,2):
                sid=self.tables['MartialItem'][cid].get('SkillID'+str(slot),0)
                if sid not in self.tables['Skill']:continue
                text=self.name(mid)+(f' · 第{index+1}式' if len(moves)>1 else '')
                if self.text(self.tables['Skill'][sid].get('NameID',0))==text:continue
                sid,_=self.own_skill(mid,'MartMovIDs',index,slot)
                self.set('Skill',sid,{'NameID':self.set_text(0,text)})

    def native_source(self,mid):
        if mid in self.origins['Martial']:return self.origins['Martial'][mid]
        if mid in self.sources['Martial']:
            source=self.sources['Martial'][mid]
            if source!=mid:return self.native_source(source)
        m=self.tables['Martial'][mid]
        donors={self.origins['Skill'].get(self.tables['MartialItem'][c].get('SkillID1',0),self.animations.get(self.tables['MartialItem'][c].get('SkillID1',0),self.tables['MartialItem'][c].get('SkillID1',0))) for c in m['MartMovIDs']}
        for ident,row in self.tables['Martial'].items():
            if ident in self.origins['Martial'] or ident>=200000:continue
            if any(self.tables['MartialItem'].get(c,{}).get('SkillID1') in donors for c in row['MartMovIDs']):return ident
        return mid

    def family_skill(self,mid,sid):
        sid=self.origins['Skill'].get(sid,self.animations.get(sid,sid))
        for cid in self.tables['Martial'][mid]['MartMovIDs']:
            active=self.tables['MartialItem'][cid].get('SkillID1',0)
            if self.origins['Skill'].get(active,self.animations.get(active,active))==sid:return active
        return sid

    def repair_bindings(self,mid):
        source=self.native_source(mid);count=0
        for key in SECTIONS.values():
            for index,cid in enumerate(list(self.tables['Martial'][mid].get(key,[]))):
                clause=self.tables['MartialItem'][cid]
                for slot in (1,2):
                    fid=clause.get('MartialFilter'+str(slot),0);f=self.tables['MartialFilter'].get(fid)
                    if f and f.get('MartialID')==source and source!=mid:
                        new=self.clone('MartialFilter',fid);self.set('MartialFilter',new,{'MartialID':mid})
                        self.edit_clause(mid,key,index,{'MartialFilter'+str(slot):new});count+=1
                    sid=clause.get('SkillID'+str(slot),0)
                    if sid not in self.tables['Skill']:continue
                    graph=self.effect_graph(sid)
                    kind=self.enums.get('SkillEffectDescription.SED_SkillLogic_CommonFanJiProcess')
                    if any(r['Name']==kind and r.get('EventArg1') in ([source,0],[mid,0]) and (r['EventArg1']!=[mid,0] or self.family_skill(mid,r.get('EventArg2',[0])[0])!=r.get('EventArg2',[0])[0]) for r in graph.values()):
                        self.own_skill(mid,key,index,slot);count+=1
        return count

    def repair_presentation(self,mid):
        if mid>=20000:self.origins['Martial'].setdefault(mid,self.native_source(mid))
        self.sync_move_names(mid)
        for key in SECTIONS.values():
            for index,cid in enumerate(list(self.tables['Martial'][mid].get(key,[]))):
                row=self.tables['MartialItem'][cid]
                if row.get('DesID') and any(row.get('EffectEnum'+str(s)) in (7,8,9,10,12) for s in (1,2)):
                    desc=self.text(row['DesID']);values=row.get('Effect1Value',[])
                    if row.get('AttrEnum1')==94 and values and f'提升本武学{values[0]}次攻击上限' in desc:continue
                    self.edit_clause(mid,key,index,{'Effect1Value':list(values)})
        return self.repair_bindings(mid)

    def effect_audit(self,mid):
        m=self.tables['Martial'][mid];messages=[];kinds=set()
        for cid in m['MartMovIDs']:
            if cid not in self.tables['MartialItem']:raise ValueError('武学引用了缺失的词条：'+str(cid))
            c=self.tables['MartialItem'][cid]
            for slot in (1,2):
                sid=c.get('SkillID'+str(slot),0)
                if sid in self.tables['Skill']:kinds.update(r['Name'] for r in self.effect_graph(sid).values())
        random=self.enums.get('SkillEffectDescription.SED_SpecificSkillLogic_XiaJiBaKan') in kinds
        attrs=set()
        for key in SECTIONS.values():
            for cid in m.get(key,[]):
                if cid not in self.tables['MartialItem']:raise ValueError('武学引用了缺失的词条：'+str(cid))
                c=self.tables['MartialItem'][cid]
                for slot in (1,2):
                    fid=c.get('MartialFilter'+str(slot),0)
                    if fid and fid not in self.tables['MartialFilter']:raise ValueError('效果引用了不存在的武学限定：'+str(fid))
                    f=self.tables['MartialFilter'].get(fid,{})
                    target=f.get('MartialID',0)
                    if target and target!=mid:
                        messages.append(f'限定范围：条目 {cid} 的效果 {slot} 指向武学 {target}，不会作用于当前武学。若是跨武学加成可保留，否则请调整限定条件。')
                    if f.get('Multistage') and not m.get('Multistage'):messages.append(f'限定不匹配：条目 {cid} 要求多段类别，当前武学未设置多段。')
                    attr=c.get('AttrEnum'+str(slot),0)
                    if c.get('EffectEnum'+str(slot)) in (7,8,9,10,12):attrs.add(attr)
                    sid=c.get('SkillID'+str(slot),0)
                    if c.get('EffectEnum'+str(slot)) in (6,11):
                        if sid not in self.tables['Skill']:raise ValueError('效果引用了不存在的招式：'+str(sid))
                        self.effect_graph(sid)
        if random:
            messages.append('随机九剑模板：攻击次数 = 基础次数 + 角色/装备加成 + 本武学加成，再受剑法精通对应上限限制；提高次数加成不一定增加实际次数。')
            if attrs.intersection({321,384}):messages.append('不适用：逐次威力属性 321 / 384 未被此模板读取。可用“适配逐次威力系数”转换为属性 361；系数增量与伤害百分比含义不同。')
            if 361 in attrs:messages.append('属性 361 由此模板读取；原值 10000 表示系数 1，实际增量还乘以基础次数和攻击序号，由游戏原生算法计算。')
        else:
            if attrs.intersection({94,321,361,384}):messages.append('当前招式的多段属性适用性尚未验证；多段类别标记本身不会改变模板的攻击算法。')
        if attrs.intersection({312,313,314,315,316}):messages.append('附加增益属性不等于给自己增加状态。若要自身增益，请选中阶段使用“改为自身增益”，生成原生被动触发器并保留解锁等级。')
        if 382 in attrs:messages.append('威力百分比由武学威力计算读取，例如基础 25% + 条目 200% = 225%。最终伤害仍受目标属性和其他机制影响。')
        if 302 in attrs:messages.append('最终伤害修正 302 是最终倍率，不是通常的 +X% 增伤。随机九剑将逐次倍率 100% / 80% 与此值相加。普通增伤可改用“最终伤害附加百分比 342”，但计算位置不同。')
        messages.append('已检查阶段与招式/表达式引用。此检查不代替游戏内的命中、触发条件及伤害实测。')
        return messages

    def adapt_progressive(self,mid):
        if not any(r['Name']==self.enums.get('SkillEffectDescription.SED_SpecificSkillLogic_XiaJiBaKan') for cid in self.tables['Martial'][mid]['MartMovIDs'] for r in self.effect_graph(self.tables['MartialItem'][cid]['SkillID1']).values()):raise ValueError('此适配仅适用于已核实的随机九剑模板')
        count=0
        for key in SECTIONS.values():
            for index,cid in enumerate(list(self.tables['Martial'][mid].get(key,[]))):
                row=self.tables['MartialItem'][cid]
                for slot in (1,2):
                    if row.get('AttrEnum'+str(slot)) in (321,384) and row.get('EffectEnum'+str(slot)) in (7,8,9,10,12):
                        self.edit_clause(mid,key,index,{'AttrEnum'+str(slot):361,'DesID':0});count+=1
        return count

    def sync_icons(self,mid):
        if str(mid) in self.icons:return
        m=self.tables['Martial'][mid]
        donor=None
        for other in self.tables['Martial'].values():
            if other.get('DepartEnum')!=m['DepartEnum'] or other.get('Rank')!=m['Rank']:continue
            for item in other.get('MartMovIDs',[]):
                clause=self.tables['MartialItem'].get(item,{})
                skill=self.tables['Skill'].get(clause.get('SkillID1'),{})
                if skill.get('Icon'):donor=skill['Icon'];break
            if donor:break
        for index,cid in enumerate(m.get('MartMovIDs',[])):
            row=self.tables['MartialItem'][cid]
            for slot in (1,2):
                if row.get('SkillID'+str(slot)) not in self.tables['Skill']:continue
                sid,_=self.own_skill(mid,'MartMovIDs',index,slot)
                delta={'Rank':m['Rank']}
                if donor:delta['Icon']=donor
                self.set('Skill',sid,delta)

    def active_icons(self,mid):
        return [self.tables['Skill'][self.tables['MartialItem'][cid]['SkillID1']].get('Icon','') for cid in self.tables['Martial'][mid]['MartMovIDs']]

    def import_icon(self,mid,source):
        from martial_images import prepare_icon
        icon,relative,raw=prepare_icon(source,mid)
        record=self.icons.get(str(mid),{'originals':self.active_icons(mid)})
        self.icons={**self.icons,str(mid):{**record,'icon':icon}}
        target=self.root/relative;self.originals.setdefault(target,target.read_bytes() if target.exists() else None)
        self.icon_files={**self.icon_files,target:raw}
        for index in range(len(self.tables['Martial'][mid]['MartMovIDs'])):
            sid,_=self.own_skill(mid,'MartMovIDs',index,1);self.set('Skill',sid,{'Icon':icon})
        return icon

    def reset_icon(self,mid):
        record=self.icons.get(str(mid))
        if not record:raise ValueError('当前武学没有导入的自定义图标')
        for index in range(len(self.tables['Martial'][mid]['MartMovIDs'])):
            sid,_=self.own_skill(mid,'MartMovIDs',index,1)
            original=record['originals'][index] if index<len(record['originals']) else self.tables['Skill'].get(self.origins['Skill'].get(sid),{}).get('Icon','')
            self.set('Skill',sid,{'Icon':original})
        self.icons={i:r for i,r in self.icons.items() if i!=str(mid)}
        used={r['icon'] for r in self.icons.values()}
        from martial_images import icon_path
        if record['icon'] not in used:
            target=icon_path(self.root,record['icon']);self.icon_files={p:b for p,b in self.icon_files.items() if p!=target}

    def self_buff(self,mid,key,index,slot=1,event=313):
        """Native Skill 31 structure: self-role expression 359 + add-buff 448.

        Condition 492 restricts the passive to its owning martial and actor.
        Values are layers * 10000, as in the game's native self-buff templates.
        """
        if key!='UnlockClauses':raise ValueError('请在解锁阶段添加自身增益')
        if event not in (312,313):raise ValueError('请选择施放后或造成伤害后')
        row=self.tables['MartialItem'][self.tables['Martial'][mid][key][index]];n=str(slot)
        attr=row.get('AttrEnum'+n);value=row.get('Effect'+n+'Value',[])
        buffs={312:126,313:127,314:128,315:129,316:130}
        if row.get('EffectEnum'+n)!=10 or attr not in buffs:raise ValueError('请选择附加强壮、坚韧、疗伤、调息或轻盈属性')
        if len(value)!=2 or value[1] or not 1<=value[0]<=10000:raise ValueError('自身增益需要 1～10000 层的固定值；成长值应为 0')
        if row.get('CondID') or row.get('MartialFilter'+n):raise ValueError('转换前请先清除阶段条件和武学筛选，避免改变触发范围')
        text=('本武学施放后' if event==313 else '本武学每次造成伤害后')+'自身'+self.attr_names[str(attr)]+'+'+str(value[0])
        self.edit_clause(mid,key,index,{'EffectEnum'+n:6,'AttrEnum'+n:0,'SkillID'+n:31,'Effect'+n+'Value':[],'Grade'+n:0,'DesID':0})
        sid,mapping=self.own_skill(mid,key,index,slot)
        self.set('Skill',sid,{'NameID':self.set_text(0,text),'DescID':self.set_text(0,text),'SkillTriggers':[{**self.tables['Skill'][sid]['SkillTriggers'][0],'Event':event}]})
        self.set('SkillEffect',mapping[400031001],{'Name':492,**{'EventArg'+str(i):[] for i in range(1,14)}})
        self.set('SkillEffect',mapping[400031002],{'EventArg2':[buffs[attr],0],'EventArg3':[value[0]*10000,0]})
        return sid

    def final_damage_add(self,mid,key,index):
        row=self.tables['MartialItem'][self.tables['Martial'][mid][key][index]];delta={}
        for slot in (1,2):
            if row.get('EffectEnum'+str(slot))==10 and row.get('AttrEnum'+str(slot))==302:delta['AttrEnum'+str(slot)]=342
        if not delta:raise ValueError('请选择“本武学最终伤害修正百分比”属性阶段')
        delta['DesID']=0;self.edit_clause(mid,key,index,delta)

    def growth_profile(self,mid,key,index,slot=1):
        from martial_growth import GrowthDraft
        if self.growth is None:self.growth=GrowthDraft(self)
        return self.growth.profile(self,mid,key,index,slot)

    def own_clause(self,mid,key,index):
        token=(mid,key,index)
        if token not in self.clause_owned:
            seq=list(self.tables['Martial'][mid][key]);old=seq[index]
            if old not in self.tables['MartialItem']:raise ValueError('武学条目缺失：'+str(old))
            seq[index]=self.clone('MartialItem',old);self.set('Martial',mid,{key:seq});self.clause_owned[token]=seq[index]
        return self.clause_owned[token]
    def edit_clause(self,mid,key,index,delta):
        ident=self.own_clause(mid,key,index)
        self.set('MartialItem',ident,delta)
        # Attribute descriptions are generated by the game from real values.
        if any(k.startswith('Effect') and k.endswith('Value') for k in delta):
            row=self.tables['MartialItem'][ident]
            if any(row.get('EffectEnum'+str(s)) in (7,8,9,10,12) for s in (1,2)):
                desc=self.text(row.get('DesID',0))
                if row.get('AttrEnum1')==94 and re.search(r'提升本武学\d+次攻击上限',desc):
                    value=row.get('Effect1Value',[0])[0]
                    desc=re.sub(r'提升本武学\d+次攻击上限',f'提升本武学{value}次攻击上限',desc)
                    self.set('MartialItem',ident,{'DesID':self.set_text(0,desc)})
                elif row.get('DesID'):self.set('MartialItem',ident,{'DesID':0})
    def unlock_level(self,mid,index,level):
        if not 0<=level<=1000:raise ValueError('解锁等级范围为 0～1000')
        levels=list(self.tables['Martial'][mid]['UnlockLvls']);levels[index]=level;self.set('Martial',mid,{'UnlockLvls':levels})

    def _stage_sequence(self,mid,key,seq,levels=None):
        if key not in SECTIONS.values():raise ValueError('阶段类别不正确')
        if len(seq)>4096:raise ValueError('阶段数量不能超过 4096')
        if key=='MartMovIDs' and not seq:raise ValueError('至少保留一个主动招式阶段')
        if key=='MartMovIDs' and len(seq)>3:raise ValueError('游戏招式结构最多支持三段；等级效果请添加到解锁阶段')
        delta={key:seq}
        if key=='UnlockClauses':
            if levels is None or len(levels)!=len(seq):raise ValueError('解锁等级与效果数量不一致')
            if any(not isinstance(x,int) or not 0<=x<=1000 for x in levels):raise ValueError('解锁等级范围为 0～1000')
            delta['UnlockLvls']=levels
        owned={v for (m,k,i),v in self.clause_owned.items() if m==mid and k==key}
        self.set('Martial',mid,delta)
        self.clause_owned={t:v for t,v in self.clause_owned.items() if not (t[0]==mid and t[1]==key)}
        for index,cid in enumerate(seq):
            if cid in owned:self.clause_owned[mid,key,index]=cid

    def validate_clause(self,key,delta):
        row=copy.deepcopy(delta);row['ItemType']={'GrowProIDs':1,'MartMovIDs':3,'UnlockClauses':2}[key]
        if any(row.get('EffectEnum'+str(s)) in (7,8,9,10,12) for s in (1,2)):
            if not (row.get('AttrEnum1')==94 and re.search(r'提升本武学\d+次攻击上限',self.text(row.get('DesID',0)))):row['DesID']=0
        for slot in (1,2):
            kind=row.get('EffectEnum'+str(slot),0)
            if kind not in (0,*range(6,18)):raise ValueError('效果类型不正确')
            if kind in (6,11):
                if row.get('SkillID'+str(slot)) not in self.tables['Skill']:raise ValueError('请选择有效招式或被动技能')
            elif kind in (7,8,9,10,12):
                if str(row.get('AttrEnum'+str(slot),0)) not in self.attr_names:raise ValueError('请选择有效属性')
                vals=row.get('Effect'+str(slot)+'Value',[])
                if len(vals)!=2 and not (not vals and row.get('Grade'+str(slot),0)>0):raise ValueError('属性效果需要基础数值和成长数值，或沿用模板的等级公式')
        if key=='MartMovIDs' and not any(row.get('EffectEnum'+str(s))==11 for s in (1,2)):raise ValueError('主动招式阶段需要招式技能效果')
        return row

    def add_stage(self,mid,key,source,level=5,delta=None,after=None):
        if source not in self.tables['MartialItem']:raise ValueError('阶段模板不存在')
        row=self.validate_clause(key,{**self.tables['MartialItem'][source],**(delta or {})})
        cid=self.clone('MartialItem',source);self.set('MartialItem',cid,row)
        seq=list(self.tables['Martial'][mid].get(key,[]));pos=len(seq) if after is None else after+1
        if not 0<=pos<=len(seq):raise ValueError('插入位置不正确')
        seq.insert(pos,cid);levels=list(self.tables['Martial'][mid].get('UnlockLvls',[]))
        if key=='UnlockClauses':levels.insert(pos,level)
        self._stage_sequence(mid,key,seq,levels);self.clause_owned[mid,key,pos]=cid
        return pos

    def update_stage(self,mid,key,index,delta,level=None):
        old=self.tables['MartialItem'][self.tables['Martial'][mid][key][index]]
        row=self.validate_clause(key,{**old,**delta})
        self.edit_clause(mid,key,index,row)
        cid=self.tables['Martial'][mid][key][index]
        for slot in (1,2):
            if row.get('SkillID'+str(slot))!=old.get('SkillID'+str(slot)):self.skill_owned.pop((cid,slot),None)
        if key=='UnlockClauses' and level is not None:self.unlock_level(mid,index,level)

    def copy_stage(self,mid,key,index):
        m=self.tables['Martial'][mid]
        return self.add_stage(mid,key,m[key][index],m['UnlockLvls'][index] if key=='UnlockClauses' else 0,after=index)

    def remove_stage(self,mid,key,index):
        seq=list(self.tables['Martial'][mid][key]);seq.pop(index)
        levels=list(self.tables['Martial'][mid].get('UnlockLvls',[]))
        if key=='UnlockClauses':levels.pop(index)
        self._stage_sequence(mid,key,seq,levels)

    def move_stage(self,mid,key,index,step):
        seq=list(self.tables['Martial'][mid][key]);other=index+step
        if not 0<=other<len(seq):return index
        seq[index],seq[other]=seq[other],seq[index]
        levels=list(self.tables['Martial'][mid].get('UnlockLvls',[]))
        if key=='UnlockClauses':levels[index],levels[other]=levels[other],levels[index]
        self._stage_sequence(mid,key,seq,levels);return other

    def repair_legacy_skills(self,mid):
        count=0
        for key in SECTIONS.values():
            for index,cid in enumerate(self.tables['Martial'][mid].get(key,[])):
                for slot in (1,2):
                    sid=self.tables['MartialItem'][cid].get('SkillID'+str(slot),0)
                    if sid>65535 and sid in self.tables['Skill']:
                        self.own_skill(mid,key,index,slot);count+=1
        return count

    def repair_table_indices(self):
        """Stage positional index repair without replacing authored parameters."""
        repaired=[]
        for name in TABLES:
            path=self.root/'TableData'/(name+'.bytes')
            rows,index=indexed_rows(self.originals[path]);order=list(rows)
            bad=next((ident for pos,ident in enumerate(index) if order[pos]!=ident),None)
            if bad is not None:
                # A harmless existing-row edit routes this table through the
                # normal validated, backed-up save across both native layers.
                self.set(name,bad,{'BaseID':bad});repaired.append(name)
        return repaired

    def effect_graph(self,skill):
        return self.trigger_graph(self.tables['Skill'][skill].get('SkillTriggers',[]))

    def trigger_graph(self,triggers):
        result={};pending=[v for t in triggers for k,v in t.items() if k in ('ConditionID','EffectID') and v]
        while pending:
            ident=pending.pop()
            if ident in result:continue
            row=self.tables['SkillEffect'].get(ident)
            if not row:raise ValueError('技能表达式缺失：'+str(ident))
            result[ident]=row
            for k,v in row.items():
                if k.startswith('EventArg') and isinstance(v,list) and len(v)>1 and v[1]:pending.append(v[1])
            # This native dispatcher stores a child expression ID as a constant.
            if row.get('Name')==self.enums.get('SkillEffectDescription.SED_SkillLogic_CommonInitiativeSkill'):
                arg=row.get('EventArg1',[])
                if len(arg)==2 and not arg[1] and arg[0]:pending.append(arg[0])
            if len(result)>10000:raise ValueError('技能表达式数量异常')
        return result

    def own_skill(self,mid,key,index,slot):
        clause=self.own_clause(mid,key,index);token=(clause,slot)
        if token in self.skill_owned:return self.skill_owned[token]
        old=self.tables['MartialItem'][clause].get('SkillID'+str(slot),0)
        if old not in self.tables['Skill']:raise ValueError('该条目没有可编辑招式')
        graph=self.effect_graph(old)
        if len(graph)>999:raise ValueError('招式战斗表达式超过独立编号区间容量（999）')
        new=self.clone('Skill',old)
        # Follow the native skill expression namespace: 400000000 + skill * 1000.
        mapping={i:self.clone('SkillEffect',i,400000000+new*1000+offset) for offset,i in enumerate(graph,1)}
        for src,dst in mapping.items():
            delta={}
            for k,v in graph[src].items():
                if k.startswith('EventArg') and isinstance(v,list) and len(v)>1 and v[1]:delta[k]=[v[0],mapping[v[1]],*v[2:]]
            if graph[src].get('Name')==self.enums.get('SkillEffectDescription.SED_SkillLogic_CommonInitiativeSkill'):
                arg=graph[src].get('EventArg1',[])
                if len(arg)==2 and not arg[1] and arg[0]:delta['EventArg1']=[mapping[arg[0]],0]
            if graph[src].get('Name')==self.enums.get('SkillEffectDescription.SED_SkillLogic_CommonFanJiProcess'):
                if graph[src].get('EventArg1') in ([self.native_source(mid),0],[mid,0]):
                    delta['EventArg1']=[mid,0]
                    arg=graph[src].get('EventArg2',[])
                    if len(arg)==2 and not arg[1]:delta['EventArg2']=[self.family_skill(mid,arg[0]),0]
            if delta:self.set('SkillEffect',dst,delta)
        triggers=copy.deepcopy(self.tables['Skill'][old].get('SkillTriggers',[]))
        donor=self.animations.get(old,old)
        if donor in self.performances:self.animations[new]=donor
        for t in triggers:
            for k in ('ConditionID','EffectID'):
                if t.get(k):t[k]=mapping[t[k]]
        self.set('Skill',new,{'SkillTriggers':triggers})
        self.set('MartialItem',clause,{'SkillID'+str(slot):new})
        self.skill_owned[token]=(new,mapping);return new,mapping

    def set_animation(self,mid,index,source):
        source=self.animations.get(source,source)
        if source not in self.performances:raise ValueError('所选招式没有可用动画')
        sid,_=self.own_skill(mid,'MartMovIDs',index,1)
        self.animations[sid]=source
        # Voice and the animation show flag follow the selected native template.
        donor=self.tables['Skill'].get(source,{})
        self.set('Skill',sid,{k:donor[k] for k in ('ManAudio','WomanAudio','ShowPerformance') if k in donor})

    def replace_moves(self,mid,template):
        source=self.tables['Martial'][template].get('MartMovIDs',[])
        if not source:raise ValueError('模板没有招式')
        self.set('Martial',mid,{'MartMovIDs':list(source)})
        for token in list(self.clause_owned):
            if token[0]==mid and token[1]=='MartMovIDs':del self.clause_owned[token]
        for index in range(len(source)):self.own_clause(mid,'MartMovIDs',index);self.own_skill(mid,'MartMovIDs',index,1)
        if str(mid) in self.icons:
            record=self.icons[str(mid)];self.icons={**self.icons,str(mid):{**record,'originals':self.active_icons(mid)}}
            for index in range(len(source)):
                sid,_=self.own_skill(mid,'MartMovIDs',index,1);self.set('Skill',sid,{'Icon':record['icon']})

    def edit_skill(self,mid,key,index,slot,delta,effect_changes=None,description=None):
        skill,mapping=self.own_skill(mid,key,index,slot)
        if delta:self.set('Skill',skill,delta)
        for ident,change in (effect_changes or {}).items():
            target=mapping.get(ident,ident)
            if target not in self.effect_graph(skill):raise ValueError('表达式不属于当前招式')
            change=copy.deepcopy(change)
            for k,v in change.items():
                if not k.startswith('EventArg') or len(v)!=2 or v[1]!=self.tables['SkillEffect'][target].get(k,[0,0])[1]:raise ValueError('只能修改表达式常量，引用关系保持原值')
                current=self.tables['SkillEffect'][target]
                if k=='EventArg1' and current.get('Name')==self.enums.get('SkillEffectDescription.SED_SkillLogic_CommonInitiativeSkill') and not v[1]:
                    if mapping.get(v[0],v[0])!=current.get(k,[0,0])[0]:raise ValueError('通用主动技能的子表达式编号不能作为数值修改')
                    change[k]=[mapping.get(v[0],v[0]),0]
            self.set('SkillEffect',target,change)
        if description is not None:
            self.set('Skill',skill,{'DescID':self.set_text(0,description)})

    def books(self,mid):return [r for r in self.tables['Item'].values() if r.get('MartialID')==mid and r.get('ItemType') in (15,16) and (r.get('ItemType')!=15 or 2 in r.get('Feature',[]))]
    def configure_books(self,mid,enabled,copyable):
        self.set('Martial',mid,{'CouldCopy':int(copyable and enabled)})
        books=self.books(mid);existing=next((r for r in books if r.get('ItemType')==15),None)
        if not enabled:
            if existing:self.set('Item',existing['BaseID'],{'Feature':[x for x in existing.get('Feature',[]) if x!=2]})
            return
        # Restore an existing disabled book rather than duplicating it.
        existing=next((r for r in self.tables['Item'].values() if r.get('MartialID')==mid and r.get('ItemType')==15),None)
        for kind in (15,16):
            item=existing if kind==15 else next((r for r in books if r.get('ItemType')==kind),None)
            if item is None:
                template=self.book_templates.get(kind)
                if template is None:raise ValueError('没有可用秘籍/残章模板')
                ident=self.clone('Item',template);item=self.tables['Item'][ident]
            ident=item['BaseID'];delta={'MartialID':mid,'Rank':self.tables['Martial'][mid]['Rank'],'ItemName':'《'+self.name(mid)+'》'+('秘籍' if kind==15 else '残章')}
            if kind==15:
                m=self.tables['Martial'][mid];icon=self.book_icons.get((m['Rank'],m['DepartEnum']))
                if icon:delta['Icon']=icon
            else:
                m=self.tables['Martial'][mid]
                donor=next((r for r in self.tables['Item'].values() if r.get('ItemType')==16 and r.get('Rank')==m['Rank'] and self.tables['Martial'].get(r.get('MartialID'),{}).get('DepartEnum')==m['DepartEnum']),None)
                if donor:delta['Icon']=donor.get('Icon',item.get('Icon',''))
            if kind==15:delta['Feature']=list(dict.fromkeys(item.get('Feature',[])+[2]))
            self.set('Item',ident,delta)

    def attr_display(self,attr,value):
        if attr==361:return f'系数增量 {value/10000:g}（原值 {value}）'
        p=self.percent.get(attr,{})
        val=value/10000 if p.get('PerMyriad')==1 else value
        return f'{val*100:g}%' if p.get('ShowAsPercent')==1 else f'{val:g}'

    def effect_argument(self,effect,field):
        name=effect.get('Name',0)
        known={
            self.enums.get('SkillEffectDescription.SED_SkillLogic_SaveDataSongShanZhenQi'):{'EventArg2':('基础伤害加成',True),'EventArg3':('吸血率加成',True)},
            self.enums.get('SkillEffectDescription.SED_System_AddParameter'):{'EventArg3':('属性加成',False)},
        }
        label,percent=known.get(name,{}).get(field,('参数 '+field[8:],False))
        if name==self.enums.get('SkillEffectDescription.SED_System_AddParameter') and field=='EventArg3':
            attr=effect.get('EventArg2',[0])[0]
            label=self.attr_names.get(str(attr),label)
            p=self.percent.get(attr,{})
            percent=p.get('PerMyriad')==1 and p.get('ShowAsPercent')==1
        return label,percent

    def assign_role(self,mid,role_id,level,enabled=True):
        if role_id not in self.tables['Role']:raise ValueError('人物不存在')
        if type(level) is not int or not 1<=level<2147483648:raise ValueError('初始等级须为正整数（不超过存储范围 2147483647）')
        row=self.tables['Role'][role_id];ids=list(row.get('Kungfu',[]));levels=list(row.get('KungfuLevel',[]))
        if len(ids)!=len(levels):raise ValueError('人物初始武学与等级数量不一致')
        if mid in ids:
            idx=ids.index(mid)
            if enabled:levels[idx]=level
            else:ids.pop(idx);levels.pop(idx)
        elif enabled:ids.append(mid);levels.append(level)
        self.set('Role',role_id,{'Kungfu':ids,'KungfuLevel':levels})

    def plan(self,preserve_imported=False):
        from aoyi_editor import sync_caps
        sync_caps(self)
        from martial_ranges import sync_names,repair_bindings
        if self.modified() and not preserve_imported:
            repair_bindings(self)
            sync_names(self)
        from martial_scopes import compile_groups
        if self.modified() and not preserve_imported:compile_groups(self)
        from language_routing import stage_repairs,resource_for,strip_rows
        if self.modified():stage_repairs(self)
        from aoyi_editor import validate_recipe, report_payload
        for row in self.changes['AoYi'].values():
            validate_recipe(self,self.tables['AoYi'][row['BaseID']],row['BaseID'])
        for mid in list(self.changes['Martial']):
            if mid>=20000 and not preserve_imported:self.repair_presentation(mid)
            self.effect_audit(mid)
        from martial_collection import ensure_fragments
        ensure_fragments(self)
        from client_shards import staged
        payloads={};originals=dict(self.originals);assetdata=staged(self,originals[self.assets_path])
        for path,before in originals.items():
            current=path.read_bytes() if path.exists() else None
            if current!=before:raise ValueError('配置在读取后发生变化，请重新读取：'+str(path))
        for name in TABLES:
            directory=self.own_jsons[name].parent
            current=set(directory.glob(name+'_*.json')) if directory.exists() else set()
            expected={p for p in originals if p.parent==directory and p.name.startswith(name+'_')}
            if current!=expected:raise ValueError('模组文件列表在读取后发生变化，请重新读取')
        if not self.modified():return {},originals
        for name,changes in self.changes.items():
            if not changes:continue
            for ident in changes:
                if ident in self.overrides[name]:raise ValueError('存在其他模组覆盖，停止保存')
            for directory in ('TableData','DreamRivakes_Data/StreamingAssets'):
                path=self.root/directory/(name+'.bytes')
                if not path.exists():continue
                old=originals.get(path)
                if old is None:old=path.read_bytes();originals[path]=old
                existing=indexed_rows(old)[0]
                native_changes={i:({k:v for k,v in self.tables[name][i].items() if k in SCHEMAS[name]} if i not in existing else delta) for i,delta in changes.items()}
                payloads[path]=patch_table(old,name,native_changes,self.sources[name])
            a=Assets(assetdata)
            if name in a.scripts:
                _,q,n=a.scripts[name];blob=a.data[q+4:q+4+n]
                existing=indexed_rows(blob)[0]
                native_changes={i:({k:v for k,v in self.tables[name][i].items() if k in SCHEMAS[name]} if i not in existing else delta) for i,delta in changes.items()}
                assetdata=a.replace_blob(name,patch_table(blob,name,native_changes,self.sources[name]))
            grouped={}
            for ident in changes:
                resource=resource_for(self.assets,ident) if name=='Language' else self.locations[name].get(ident,self.resources[name][0])
                # Complete effective rows also preserve client defaults for new entries.
                from client_shards import targets
                for target in targets(self,name,ident,resource):
                    grouped.setdefault(target,{})[ident]=self.tables[name][ident]['Ch_Text'] if name=='Language' else self.tables[name][ident]
            if name=='Language':
                removals={}
                for ident in changes:
                    old_resource=self.locations[name].get(ident)
                    if old_resource and old_resource!=resource_for(self.assets,ident):removals.setdefault(old_resource,set()).add(ident)
                for resource,identifiers in removals.items():
                    a=Assets(assetdata);assetdata=a.replace_script(resource,strip_rows(a.script(resource),identifiers))
            for resource,rows in grouped.items():
                a=Assets(assetdata);text=patch_lua_rows(a.script(resource),rows,name=='Language')
                parsed={int(i):literal(v,self.enums) for _,i,v in re.findall(LANG_RE,text)} if name=='Language' else lua_rows(text,name,self.enums)
                for ident,row in rows.items():
                    if parsed.get(ident)!=row:raise ValueError('客户端配置回读不一致：'+name)
                assetdata=a.replace_script(resource,text)
            path=self.own_jsons[name];old=originals.get(path)
            originals[path]=old
            obj=json.loads(old.decode('utf-8-sig')) if old else {'Items':[]}
            existing={int(r['BaseID']):r for r in obj.get('Items',[])}
            for ident,delta in changes.items():
                from client_only_fields import without_empty_defaults
                row=copy.deepcopy(without_empty_defaults(name,delta))
                if name=='Language':row['Text']=row.pop('Ch_Text','')
                existing.setdefault(ident,{}).update(row)
            obj['Items']=list(existing.values());payloads[path]=json.dumps(obj,ensure_ascii=False,indent=2).encode('utf-8')
        if self.animations!=self.animation_original:
            a=Assets(assetdata);text=patch_performances(a.script('SkillPerformance.lua'),self.animations)
            check=performance_blocks(text)
            if not all(i in check for i in self.animations):raise ValueError('动画模板回读校验失败')
            assetdata=a.replace_script('SkillPerformance.lua',text)
            payloads[self.animation_path]=json.dumps(self.animations,ensure_ascii=False,indent=2).encode('utf-8')
        caps=dict(self.created_caps)
        for ident in self.sources['Martial']:
            if str(ident) not in caps:
                template=self.sources['Martial'][ident];value=self.tables['Martial'][ident]['LvLimit']
                if value==30:
                    from caps import baseline
                    value=self.created_caps.get(str(template),baseline()['proto']['Martial'].get(str(template),{}).get('LvLimit',value))
                caps[str(ident)]=value
        if caps!=self.created_caps:payloads[self.cap_original_path]=json.dumps(caps,ensure_ascii=False,indent=2).encode('utf-8')
        if self.origins!=self.origin_original:payloads[self.origin_path]=json.dumps(self.origins,ensure_ascii=False,indent=2).encode('utf-8')
        if self.icons!=self.icon_original:payloads[self.icon_path]=json.dumps(self.icons,ensure_ascii=False,indent=2).encode('utf-8')
        if self.scope_groups!=self.scope_original:payloads[self.scope_path]=json.dumps(self.scope_groups,ensure_ascii=False,indent=2).encode('utf-8')
        for path,raw in self.icon_files.items():
            originals.setdefault(path,path.read_bytes() if path.exists() else None);payloads[path]=raw
        from mod_compatibility import native_supported,changed_native_growth,note
        can_patch_native=native_supported(self.root)
        if not can_patch_native and changed_native_growth(self):
            from mod_compatibility import require_native
            require_native(self,'独立成长数值修改')
        if self.growth is None and can_patch_native:
            from growth_runtime import custom_values
            if any(custom_values(row,s) for row in self.changes['MartialItem'].values() for s in (1,2)):
                from martial_growth import GrowthDraft
                self.growth=GrowthDraft(self);originals.update(self.originals)
        if self.growth:assetdata=self.growth.plan(self,assetdata,payloads,originals)
        from martial_display import patch_client as patch_display
        a=Assets(assetdata)
        from mod_compatibility import attempt
        assetdata=attempt(self,'词条显示修复',lambda:a.replace_script('MartialDataManager.lua',patch_display(a.script('MartialDataManager.lua'),self)),assetdata)
        from aoyi_runtime import patch_client as patch_aoyi_caps
        a=Assets(assetdata)
        assetdata=a.replace_script('MartialDataManager.lua',patch_aoyi_caps(a.script('MartialDataManager.lua')))
        from martial_ranges import plan as plan_ranges
        assetdata=plan_ranges(self,assetdata,payloads,originals)
        from client_runtime_repair import repair
        assetdata=repair(assetdata,self.compat_notes if hasattr(self,'compat_notes') else None)
        payloads[self.assets_path]=assetdata
        from martial_preview import report_payloads
        report_payloads(self,payloads,originals)
        report_payload(self,payloads,originals)
        from compatibility import validate_native_writes
        validate_native_writes(self.root,payloads,originals)
        from shadow_compat import route_payloads
        return route_payloads(self,payloads,originals)

    def review(self):
        labels={'Martial':'武学','MartialItem':'成长/解锁条目','MartialFilter':'武学限定条件','Skill':'招式','SkillEffect':'战斗表达式','Item':'秘籍/残章','Role':'人物初始配置','Language':'名称/说明','Gift':'天赋','SuperImposed':'状态组'}
        labels['MatGrowUPAttrGrade']='成长档次'
        labels['AoYi']='秘奥义组合'
        labels['Range']='技能作用范围';labels['MartialRange']='技能范围引用'
        result='；'.join(labels[n]+' '+str(len(v))+' 条' for n,v in self.changes.items() if v)
        if self.growth and self.growth.changes:result+='；共享每级成长公式 '+str(len(self.growth.changes))+' 条（影响同类别 / 品质范围）'
        if self.icons!=self.icon_original:result+='；自定义武学图标'
        return result
