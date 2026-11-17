"""Three-way field merges; unrelated target records, wire fields and assets survive."""
import copy,json,re
from codec import fields,encoded,numeric_list,patch
from martial_editor import indexed_rows,ROW_RE,LANG_RE,patch_lua_rows
from client_config import Assets,literal,enum_values

MISSING=object()
class MergeConflict(ValueError):pass

def merge(old,new,current,path='记录'):
    if old==new or current==new:return copy.deepcopy(current) if current is not MISSING else MISSING
    if current==old:return copy.deepcopy(new) if new is not MISSING else MISSING
    if all(isinstance(v,dict) for v in (old,new,current)):
        result=copy.deepcopy(current)
        for key in old.keys()|new.keys():
            value=merge(old.get(key,MISSING),new.get(key,MISSING),current.get(key,MISSING),f'{path}/{key}')
            if value is MISSING:result.pop(key,None)
            else:result[key]=value
        return result
    raise MergeConflict('目标已修改同一字段或新增编号冲突：'+path)

def changed(old,new):return {key:(old.get(key,MISSING),new.get(key,MISSING)) for key in old.keys()|new.keys() if old.get(key,MISSING)!=new.get(key,MISSING)}

def row_changes(old,new):
    return [{'id':key,'old':a if a is not MISSING else None,'new':b if b is not MISSING else None} for key,(a,b) in changed(old,new).items()]

def apply_rows(current,changes):
    result=copy.deepcopy(current)
    for record in changes:
        ident=record['id'];old=record['old'];new=record['new']
        value=merge(MISSING if old is None else old,MISSING if new is None else new,result.get(ident,MISSING),str(ident))
        if value is MISSING:result.pop(ident,None)
        else:result[ident]=value
    return result

def wire_row(raw):
    result={}
    for field in fields(raw):result[field.number]=result.get(field.number,b'')+field.raw
    return result

def proto_recipe(before,after):
    a,ai=indexed_rows(before);b,bi=indexed_rows(after)
    # Non-record table fields must not be silently dropped from the packet.
    extra=lambda raw:b''.join(f.raw for f in fields(raw) if f.number not in (1,2))
    if extra(before)!=extra(after):raise ValueError('配置表头变化不支持按记录合并')
    if [i for i in ai if i in b]!=[i for i in bi if i in a]:raise ValueError('配置索引重新排序')
    return {'kind':'proto','rows':row_changes({i:wire_row(r) for i,r in a.items()},{i:wire_row(r) for i,r in b.items()})}

def apply_proto(raw,recipe):
    rows,index=indexed_rows(raw);old={i:wire_row(r) for i,r in rows.items()};new=apply_rows(old,recipe['rows'])
    if new==old:return raw
    updated={i:patch(rows.get(i,b''),{k:new[i].get(k,b'') for k in old.get(i,{}).keys()|new[i].keys() if old.get(i,{}).get(k)!=new[i].get(k)}) for i in new}
    wanted=[i for i in index if i in new]+sorted(set(new)-set(rows));ordered=wanted+[i for i in rows if i in new and i not in wanted]
    out=bytearray();written=False
    for field in fields(raw):
        if field.number in (1,2):
            if not written:
                out.extend(numeric_list(1,wanted))
                for ident in ordered:out.extend(encoded(2,updated[ident],2))
                written=True
        else:out.extend(field.raw)
    if not written:raise ValueError('缺少配置记录区')
    result=bytes(out);check,ids=indexed_rows(result)
    if {i:wire_row(r) for i,r in check.items()}!=new or list(check)[:len(ids)]!=ids:raise ValueError('记录合并回读失败')
    return result

def lua_records(text,enums,language=False):
    result={};pattern=LANG_RE if language else ROW_RE
    for match in re.finditer(pattern,text):
        ident=int(match[2])
        if ident in result:raise ValueError('客户端记录编号重复')
        result[ident]=literal(match[3],enums)
    if not result:raise ValueError('没有可合并的客户端记录')
    return result

def script_recipe(name,a,b,enums):
    if name.endswith('.lua'):
        ta,tb=a.decode('utf-8-sig'),b.decode('utf-8-sig');language=name.startswith('Language')
        pattern=LANG_RE if language else ROW_RE
        skeleton=lambda text:re.sub(r'\s+','',re.sub(pattern,'',text))
        if skeleton(ta)==skeleton(tb):
            old,new=lua_records(ta,enums,language),lua_records(tb,enums,language)
            if set(old)-set(new):raise ValueError('暂不按行删除客户端记录')
            return {'kind':'lua','language':language,'rows':row_changes(old,new)}
    else:
        try:return proto_recipe(a,b)
        except (ValueError,UnicodeError,TypeError):pass
    return {'kind':'raw','old':a,'new':b}

def json_rows(obj):
    result={}
    for row in obj['Items']:
        if not isinstance(row,dict) or type(row.get('BaseID')) is not int or row['BaseID'] in result:raise ValueError('JSON 记录编号异常')
        result[row['BaseID']]=row
    return result

def make_recipe(name,before,after,root=None,originals=None,lookup=None):
    lookup={} if lookup is None else lookup
    if after is None:return None
    try:
        if name.endswith('.bytes') and before is not None:return proto_recipe(before,after)
        if name.endswith('.json'):
            old=json.loads(before.decode('utf-8-sig')) if before else {};new=json.loads(after.decode('utf-8-sig'))
            if isinstance(new,dict) and isinstance(new.get('Items'),list):
                if before is None:old={'Items':[]}
                if not isinstance(old,dict) or not isinstance(old.get('Items'),list):return None
                if {k:v for k,v in old.items() if k!='Items'}!={k:v for k,v in new.items() if k!='Items'}:return None
                recipe={'kind':'json_rows','rows':row_changes(json_rows(old),json_rows(new))}
                table=name.rsplit('/',1)[-1].split('_')[0]
                if root is not None and name.startswith('ModProject/'):
                    inheritance={}
                    for record in recipe['rows']:
                        if record['old'] is None and record['new'] is not None:
                            base=effective_row(root,table,record['id'],originals or {},lookup)
                            if base is not None:inheritance[record['id']]={k:base[k] for k in record['new'] if k in base}
                    if inheritance:recipe.update(inherit=inheritance,table=table)
                return recipe
            return {'kind':'json','old':old,'new':new}
        if name=='DreamRivakes_Data/resources.assets' and before is not None:
            a,b=Assets(before),Assets(after)
            if a.scripts.keys()!=b.scripts.keys():return None
            enums=enum_values(a.script('common.lua'))|enum_values(a.script('Enum.lua'))
            recipes={};rebuilt=before
            for script in a.scripts:
                _,q,n=a.scripts[script];old=before[q+4:q+4+n]
                _,q,n=b.scripts[script];new=after[q+4:q+4+n]
                if old==new:continue
                try:recipe=script_recipe(script,old,new,enums|enum_values(new.decode('utf8')))
                except (ValueError,UnicodeError,TypeError):recipe={'kind':'raw','old':old,'new':new}
                recipes[script]=recipe;rebuilt=Assets(rebuilt).replace_blob(script,new)
            if rebuilt!=after:return None
            return {'kind':'assets','scripts':recipes}
    except (ValueError,KeyError,UnicodeError,TypeError,IndexError):return None
    return None

def apply_recipe(name,current,recipe,root=None,overlay=None):
    lookup={}
    kind=recipe['kind']
    if kind=='proto':return apply_proto(current,recipe)
    if kind in ('json','json_rows'):
        obj=json.loads(current.decode('utf-8-sig')) if current else ({'Items':[]} if kind=='json_rows' else {})
        if kind=='json_rows':
            rows=json_rows(obj);records=copy.deepcopy(recipe['rows'])
            for record in records:
                baseline=recipe.get('inherit',{}).get(record['id'])
                if baseline is None:continue
                effective=effective_row(root,recipe['table'],record['id'],overlay or {},lookup)
                if effective is None:raise MergeConflict('目标缺少原人物/武学配置：'+str(record['id']))
                # Baseline fields omitted from an override are inherited, not deleted.
                rows.setdefault(record['id'],{})
                for key in baseline.keys()|record['new'].keys():
                    if key in effective:rows[record['id']].setdefault(key,effective[key])
                desired=dict(baseline);desired.update(record['new'])
                record['old']=baseline;record['new']=desired
            new=apply_rows(rows,records);order=[r['BaseID'] for r in obj['Items'] if r['BaseID'] in new]
            order+=sorted(set(new)-set(order));obj={**obj,'Items':[new[i] for i in order]}
        else:obj=merge(recipe['old'],recipe['new'],obj,name)
        return json.dumps(obj,ensure_ascii=False,indent=2).encode('utf8')
    if kind=='assets':
        result=current;assets=Assets(current)
        enums=enum_values(assets.script('common.lua'))|enum_values(assets.script('Enum.lua'))
        for script,sub in recipe['scripts'].items():
            assets=Assets(result)
            if script not in assets.scripts:raise MergeConflict('目标客户端缺少配置：'+script)
            _,q,n=assets.scripts[script];raw=result[q+4:q+4+n]
            if sub['kind']=='lua':
                text=raw.decode('utf-8-sig');local_enums=enums|enum_values(text)
                old=lua_records(text,local_enums,sub['language']);new=apply_rows(old,sub['rows'])
                replacements={i:v for i,v in new.items() if old.get(i,MISSING)!=v}
                patched=patch_lua_rows(text,replacements,sub['language']) if replacements else text
                if lua_records(patched,local_enums,sub['language'])!=new:raise ValueError('客户端合并回读失败')
                after=patched.encode('utf8')
            elif sub['kind']=='proto':after=apply_proto(raw,sub)
            elif sub['kind']=='raw':after=merge(sub['old'],sub['new'],raw,script)
            else:raise ValueError('未知客户端合并类型')
            if after!=raw:result=assets.replace_blob(script,after)
        return result
    raise ValueError('未知记录合并类型')


def effective_row(root,table,ident,overlay,memo=None):
    from pathlib import Path
    from engine import SCHEMAS
    from codec import decode
    root=Path(root);memo={} if memo is None else memo
    if table not in set(SCHEMAS)|{'Clan'}:raise ValueError('不支持的关联配置表')
    def read(path):return overlay[path] if path in overlay else (path.read_bytes() if path.exists() else None)
    row=None;path=root/'TableData'/f'{table}.bytes';key=('native',table)
    if key not in memo:
        raw=read(path);memo[key]=indexed_rows(raw)[0] if raw and table in SCHEMAS else {}
    if ident in memo[key]:row=decode(memo[key][ident],table,SCHEMAS)
    if 'assets' not in memo:
        raw=read(root/'DreamRivakes_Data/resources.assets');assets=Assets(raw) if raw else None
        memo['assets']=assets;memo['enums']=enum_values(assets.script('common.lua'))|enum_values(assets.script('Enum.lua')) if assets else {}
    assets=memo['assets'];enums=memo['enums']
    if assets:
        pattern=(r'Language\d*\.lua' if table=='Language' else re.escape(table)+r'\d*\.lua')
        for script in assets.scripts:
            if not re.fullmatch(pattern,script):continue
            text=assets.script(script)
            if not re.search(r'(?m)^\s*\['+str(ident)+r'\]\s*=',text):continue
            key=('script',script)
            if key not in memo:
                if table=='Clan':
                    memo[key]={int(m[2]):{'BaseID':int(m[2]),'NameID':int(n[1])} for m in re.finditer(ROW_RE,text) if (n:=re.search(r'\bNameID\s*=\s*(\d+)',m[3]))}
                else:memo[key]=lua_records(text,enums|enum_values(text),table=='Language')
            parsed=memo[key]
            if ident in parsed:
                value={'BaseID':ident,'Text':parsed[ident],'Ch_Text':parsed[ident]} if table=='Language' else parsed[ident]
                row={**(row or {}),**value}
    directory=root/'ModProject/GameProject/Mod_MJH/Json';key=('mods',table)
    if key not in memo:
        paths=set(directory.glob(table+'_*.json'))|{p for p in overlay if p.parent==directory and p.name.startswith(table+'_')}
        records={}
        for path in sorted(paths):
            raw=read(path)
            if not raw:continue
            try:
                for value in json.loads(raw.decode('utf-8-sig')).get('Items',[]):
                    if isinstance(value,dict) and type(value.get('BaseID')) is int:
                        records.setdefault(value['BaseID'],{}).update(value)
            except (ValueError,UnicodeError,AttributeError):continue
        memo[key]=records
    if ident in memo[key]:row={**(row or {}),**memo[key][ident]}
    return row

REFS={
 'Role':{'NameID':'Language','SurnameID':'Language','GivennameID':'Language','Clan':'Clan','Kungfu':'Martial','Gift':'Gift','AttributeID':'RoleAttr','ArtID':'RoleModel','EvoInitCity':'City',**{k:'Item' for k in ('Weapon','Artifacts','Clothes','Shoe','Ornaments','KungfuBook','Horse')}},
 'Martial':{'NameID':'Language','DesID':'Language','GrowProIDs':'MatGrowUPAttrGrade','MartMovIDs':'MartialItem','UnlockClauses':'MartialItem'},
 'MartialItem':{'SkillID1':'Skill','SkillID2':'Skill','MartialFilter1':'MartialFilter','MartialFilter2':'MartialFilter'},
 'Skill':{'NameID':'Language','DescID':'Language','MartialItemID':'MartialItem','SkillTriggers':'SkillEffect'},
 'Gift':{'NameID':'Language','DescID':'Language','SkillTriggers':'SkillEffect'},
 'NpcEvolute':{'CityID':'City'},
}

def required_refs(changes):
    refs={}
    for table,rows in changes.items():
        for old,new in rows.values():
            if new is None:continue
            for key,target in REFS.get(table,{}).items():
                if old and old.get(key)==new.get(key):continue
                values=new.get(key,0);values=values if isinstance(values,list) else [values]
                refs.setdefault(target,set()).update(v for v in values if type(v) is int and v>0)
    return {name:sorted(ids) for name,ids in refs.items() if ids}

def validate_refs(root,refs,overlay):
    from pathlib import Path
    from engine import SCHEMAS
    root=Path(root)
    lookup={}
    for table,ids in refs.items():
        if table not in set(SCHEMAS)|{'Clan'}:raise ValueError('不支持的依赖配置表')
        if not isinstance(ids,list) or any(type(i) is not int or i<=0 for i in ids):raise ValueError('依赖编号格式无效')
        path=root/'TableData'/f'{table}.bytes'
        raw=overlay.get(path,path.read_bytes() if path.exists() else None)
        available=set(indexed_rows(raw)[0]) if raw and table in SCHEMAS else set()
        for ident in ids:
            if ident not in available and effective_row(root,table,ident,overlay,lookup) is None:
                raise MergeConflict(f'目标缺少依赖 {table} {ident}；需要对应 MOD 或一起导出关联配置')


def rebase_mod_overrides(root,payloads,originals):
    """Synchronize only touched fields in target MOD overrides, not whole rows."""
    from pathlib import Path
    from change_log import table_changes
    root=Path(root);changes=table_changes(root,payloads,originals)
    directory=root/'ModProject/GameProject/Mod_MJH/Json'
    for table,rows in changes.items():
        if table=='Item':continue  # Equipment gifts have their dedicated importer.
        for path in sorted(directory.glob(table+'_*.json')):
            if path in payloads:continue
            raw=path.read_bytes()
            try:obj=json.loads(raw.decode('utf-8-sig'))
            except (ValueError,UnicodeError):continue
            if not isinstance(obj,dict) or not isinstance(obj.get('Items'),list):continue
            edited=False
            for row in obj['Items']:
                if not isinstance(row,dict) or type(row.get('BaseID')) is not int:continue
                pair=rows.get(row['BaseID'])
                if pair is None:continue
                old,new=pair
                if old is None:raise MergeConflict(f'新增 {table} {row["BaseID"]} 已被目标 MOD {path.name} 使用')
                if new is None:raise MergeConflict(f'删除 {table} {row["BaseID"]} 仍被目标 MOD {path.name} 覆盖')
                for key,(a,b) in changed(old,new).items():
                    key='Text' if table=='Language' and key=='Ch_Text' else key
                    if key not in row:continue
                    value=merge(a,b,row[key],f'{path.name}/{row["BaseID"]}/{key}')
                    if value!=row[key]:row[key]=value;edited=True
            if edited:
                originals[path]=raw;payloads[path]=json.dumps(obj,ensure_ascii=False,indent=2).encode('utf8')


def reconcile_role_metadata(root,payloads,originals):
    """Keep the editor's displayed settings aligned with merged game records."""
    from pathlib import Path
    from change_log import table_changes
    from role_editor import ATTR_LABELS,SLOTS
    from engine import clean
    root=Path(root);path=root/'装备编辑器配置/人物编辑.json'
    if path not in payloads or payloads[path] is None:return
    changes=table_changes(root,payloads,originals).get('Role',{})
    if not changes:return
    metadata=json.loads(payloads[path].decode('utf-8-sig'));after_cache={};before_cache={}
    def snapshot_values(row,overlay,memo):
        if row is None:return {},{}
        settings={'level':row.get('Level',1),'clan':row.get('Clan',0),
                  'kungfu':list(zip(row.get('Kungfu',[]),row.get('KungfuLevel',[])))}
        attrs=effective_row(root,'RoleAttr',row.get('AttributeID',0),overlay,memo)
        if attrs:settings['attrs']={k:v for k,v in attrs.items() if k!='BaseID'}
        model=effective_row(root,'RoleModel',row.get('ArtID',0),overlay,memo)
        if model:settings['portrait']=model.get('Drawing','')
        def text(ident):
            value=effective_row(root,'Language',ident,overlay,memo) if ident else None
            return clean((value or {}).get('Text',(value or {}).get('Ch_Text','')))
        name=text(row.get('NameID')) or text(row.get('SurnameID'))+text(row.get('GivennameID'))
        if name:settings['name']=name
        clan=effective_row(root,'Clan',settings['clan'],overlay,memo) if settings['clan'] else None
        label=text(clan.get('NameID',0)) if clan else ('无所属门派' if not settings['clan'] else f'未知门派 {settings["clan"]}')
        snap={'等级':settings['level'],'门派':label+f' · {settings["clan"]}'}
        if name:snap['名字']=name
        if attrs:snap['属性']={ATTR_LABELS.get(k,k):v for k,v in settings['attrs'].items()}
        snap['武学']=[text((effective_row(root,'Martial',ident,overlay,memo) or {}).get('NameID',0))+f' {level}级' for ident,level in settings['kungfu']]
        snap['装备']={}
        equipment={}
        for slot,(label,types) in SLOTS.items():
            ident=row.get(slot,0);equipment[slot]={'mode':'item','id':ident}
            value=effective_row(root,'Item',ident,overlay,memo) if ident else None
            snap['装备'][label]=clean((value or {}).get('ItemName','')) or '不佩戴'
        settings['equipment']=equipment
        return settings,snap
    seen=set()
    for ident,(old,new) in changes.items():
        if new is None:continue
        rid=str(new.get('RoleID'));record=metadata.get(rid)
        if rid in seen or not record or record.get('template') is not None:continue
        seen.add(rid)
        actual=effective_row(root,'Role',ident,payloads,after_cache)
        prior=effective_row(root,'Role',ident,originals,before_cache)
        settings,snap=snapshot_values(actual,payloads,after_cache);unused,before=snapshot_values(prior,originals,before_cache)
        # A random equipment recipe remains a generation rule in editor metadata.
        for slot,spec in record.get('settings',{}).get('equipment',{}).items():
            if spec.get('mode')=='random':settings['equipment'][slot]=spec;snap['装备'].pop(SLOTS[slot][0],None)
        record.setdefault('settings',{}).update(settings)
        record.setdefault('snapshot',{}).update(snap)
        if rid not in json.loads((originals.get(path) or b'{}').decode('utf-8-sig')):
            record.setdefault('before',{}).update(before)
    payloads[path]=json.dumps(metadata,ensure_ascii=False,indent=2).encode('utf8')
