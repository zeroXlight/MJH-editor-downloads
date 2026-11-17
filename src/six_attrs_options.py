"""Selective, reversible APK growth restoration in logic/client/MOD copies."""
import copy,json,re
from pathlib import Path
from engine import DATA_ROOT,SCHEMAS
from codec import fields,encoded,numeric_list,decode
from client_config import Assets,lua_rows
from martial_editor import indexed_rows,patch_table,patch_lua_rows,ROW_RE
from martial_growth import growth_native,growth_lua
from martial_mastery import patch_native
from object_bundle import Store

SCHEMAS.update(json.loads((DATA_ROOT/'six_attrs_schema.json').read_text('utf8')))
NAMES=('ItemRecastAttrGen','ItemBaseRecast','Martial','MartialItem','KungfuBase')
STATE='装备编辑器配置/六属性附加恢复记录.json'

def inventory(root):
    return tuple(sorted(p for p in (Path(root)/'ModProject/GameProject').rglob('*.json')
                        if any(p.name.startswith(n+'_') for n in NAMES)))

def remove_native(raw,removed):
    rows,index=indexed_rows(raw)
    return (numeric_list(1,[i for i in index if i not in removed])+
            b''.join(f.raw for f in fields(raw) if f.number not in (1,2) or
                     f.number==2 and next(x.value for x in fields(f.value) if x.number==1) not in removed))

def prepare(root,enabled,forge,martial,payloads,originals,reads):
    store=Store(root,payloads);state_path=Path(root)/STATE
    old=store.read(state_path);state=json.loads(old.decode('utf8')) if old else {'format':'mjh-six-options-2210','changes':{}}
    if state.get('format')!='mjh-six-options-2210':raise ValueError('六属性附加恢复记录不兼容')
    data=json.loads((DATA_ROOT/'six_attrs_mobile_restore.json').read_text('utf8'))
    rows={};deltas={};removed={};actions={};report=[]
    from feature_fields import state as switch_state,mobile_growth,STATE as SWITCH_STATE
    switches=switch_state(root);dormant=mobile_growth(switches)
    def table(name):
        if name not in rows:
            if name=='KungfuBase':
                raw=store.read(Path(root)/'TableData/KungfuBase.bytes')
                store.native[name]=growth_native(raw)
                rows[name]=growth_lua(store.assets.script('KungfuBase.lua'),store.enums)
                for i,r in store.native[name].items():
                    if decode(r,name,SCHEMAS)!=rows[name][i]:raise ValueError('成长逻辑与客户端不同步')
            else:
                rows[name]=copy.deepcopy(store.table(name))
                if name=='Martial':
                    for ident,e in dormant.items():
                        if ident in rows[name]:rows[name][ident]['GrowProIDs']=copy.deepcopy(e['on'])
        return rows[name]
    def put(name,ident,delta):
        table(name).setdefault(ident,{}).update(copy.deepcopy(delta))
        if name=='Martial' and ident in dormant and 'GrowProIDs' in delta:
            dormant[ident]['on']=copy.deepcopy(delta['GrowProIDs']);delta={k:v for k,v in delta.items() if k!='GrowProIDs'}
        if delta:deltas.setdefault(name,{}).setdefault(ident,{}).update(copy.deepcopy(delta))
        removed.setdefault(name,set()).discard(ident)
    # Restore the last known baseline first. Validate only fields owned here;
    # unrelated edits and unknown protobuf fields remain untouched.
    for group,tables in state.get('changes',{}).items():
        for name,changes in tables.items():
            current=table(name)
            for key,record in changes.items():
                ident=int(key);row=current.get(ident)
                if row is None or any(row.get(k)!=v for k,v in record['after'].items()):
                    raise ValueError(f'附加恢复配置被外部修改：{name} {ident}，请先处理冲突')
                if record['before'] is None:
                    current.pop(ident);removed.setdefault(name,set()).add(ident)
                else:put(name,ident,record['before'])
    def change(group,name,ident,delta):
        current=table(name);before={k:copy.deepcopy(current[ident].get(k)) for k in delta} if ident in current else None
        if before==delta:return
        actions.setdefault(group,{}).setdefault(name,{})[str(ident)]={'before':before,'after':copy.deepcopy(delta)}
        put(name,ident,delta)
    if enabled and forge:
        config=table('ItemRecastAttrGen')
        mobile={v['Attr']:v['Value'] for v in data['forge_weights']}
        relevant=set(range(3,17))|set(range(22,30))
        for ident,row in config.items():
            weights=copy.deepcopy(row['RoleAttrWeightList'])
            existing={x['Attr'] for x in weights}
            for x in weights:
                if x['Attr'] in relevant:x['Value']=mobile[x['Attr']]
                elif x['Attr']==145:x['Value']=0 # retained old entry, inactive.
            weights += [{'Attr':i,'Value':mobile[i]} for i in sorted(relevant-existing)]
            change('forge','ItemRecastAttrGen',ident,{'RoleAttrWeightList':weights,**data['forge_generation']})
        base=table('ItemBaseRecast');by_attr={r.get('AttrType'):(i,r) for i,r in base.items() if r.get('AttrType')}
        for record in data['forge_rows'].values():
            if record['AttrType'] in by_attr:
                ident,_=by_attr[record['AttrType']]
                delta={k:record[k] for k in ('RandomBase','RandomSize')}
            else:
                ident=1
                while ident in base:ident+=1
                delta={**record,'BaseID':ident}
            change('forge','ItemBaseRecast',ident,delta)
        report.append('恢复精通、属性锻造：按 APK 补回六属性、八项精通和八系攻击权重及对应基础/追加成长档；恢复被清零的手游词条数量和生成概率，保留 PC 其他条目及消耗。')
    if enabled and martial:
        clauses=table('MartialItem');ms=table('Martial');restored=0;skipped=[]
        def is_core(c):
            return any(c.get('EffectEnum'+str(i))==7 and 3<=c.get('AttrEnum'+str(i),0)<=16
                       and len(c.get('Effect'+str(i)+'Value',[]))!=2 for i in (1,2))
        for key,ref in data['martial_growth'].items():
            ident=int(key)
            if ident not in ms:continue
            row=ms[ident]
            if row.get('DepartEnum')!=ref['DepartEnum']:skipped.append(ident);continue
            links=[]
            for cid in row.get('GrowProIDs',[]):
                if cid not in clauses:raise ValueError('武学成长依赖缺失：'+str(cid))
                if not is_core(clauses[cid]):links.append(cid)
            for cid in ref['GrowProIDs']:
                target=1795000000+cid
                desired={**data['clauses'][str(cid)],'BaseID':target}
                # Native independent clauses are left in place; restored APK
                # clauses use their own IDs and never overwrite custom clauses.
                if target in clauses and target not in removed.get('MartialItem',set()):
                    if any(clauses[target].get(k)!=v for k,v in desired.items()):raise ValueError('手游成长预留词条冲突：'+str(target))
                change('martial','MartialItem',target,desired);links.append(target)
            if links!=row.get('GrowProIDs',[]):
                change('martial','Martial',ident,{'GrowProIDs':links});restored+=1
        for key,record in data['formulas'].items():
            ident=int(key)
            if ident not in table('KungfuBase'):raise ValueError('缺少原生成长公式：'+key)
            change('martial','KungfuBase',ident,{'RankDatas':record['RankDatas']})
        report.append(f'恢复武学精通、属性：同步 {restored} 门武学的原手游成长词条及六属性/精通成长公式；保留现有等级、上限和非目标词条。')
        if skipped:report.append(f'{len(skipped)} 门武学系别与 APK 不一致，保留现有配置。')
    def save(path,after):
        before=store.read(path)
        if before!=after:payloads[path]=after;originals.setdefault(path,before)
    assets=store.assets
    for name in set(deltas)|set(removed):
        changes=deltas.get(name,{})
        deleted=removed.get(name,set())
        def rewrite(raw):
            if deleted:raw=remove_native(raw,deleted)
            return patch_native(raw,name,changes) if name=='KungfuBase' else patch_table(raw,name,changes)
        for path in [Path(root)/'TableData'/f'{name}.bytes',Path(root)/'DreamRivakes_Data/StreamingAssets'/f'{name}.bytes']:
            raw=store.read(path)
            if raw is not None:save(path,rewrite(raw))
        if name in assets.scripts:
            _,q,n=assets.scripts[name];assets=Assets(assets.replace_blob(name,rewrite(assets.data[q+4:q+4+n])))
        remaining=set(changes)
        resources=[n for n in assets.scripts if re.fullmatch(re.escape(name)+r'\d*\.lua',n)]
        for resource in resources:
            text=assets.script(resource)
            if deleted:text=re.sub(ROW_RE,lambda m:'' if int(m[2]) in deleted else m[0],text)
            current=growth_lua(text,store.enums) if name=='KungfuBase' else lua_rows(text,name,store.enums)
            matched=remaining&set(current)
            update={i:{**current[i],**changes[i]} for i in matched if any(current[i].get(k)!=v for k,v in changes[i].items())}
            remaining-=matched
            if update:text=patch_lua_rows(text,update);remaining-=set(update)
            assets=Assets(assets.replace_script(resource,text))
        if remaining:
            if not resources:raise ValueError('没有可同步客户端表：'+name)
            resource=resources[-1];text=assets.script(resource)
            # A native-only martial can be absent from all client shards in the
            # big-map resources. Materialize its complete row, not a delta.
            complete={i:{**table(name)[i],**changes[i]} for i in remaining}
            assets=Assets(assets.replace_script(resource,patch_lua_rows(text,complete)))
        for path in inventory(root):
            if not path.name.startswith(name+'_'):continue
            raw=store.read(path);obj=json.loads(raw.decode('utf-8-sig'));lst=obj.get('Items') if isinstance(obj,dict) else obj
            if not isinstance(lst,list):raise ValueError('MOD 表格式不兼容：'+path.name)
            output=[];changed=False
            for row in lst:
                ident=row.get('BaseID')
                if ident in deleted:changed=True;continue
                delta=changes.get(ident)
                if delta and any(row.get(k)!=v for k,v in delta.items()):row.update(copy.deepcopy(delta));changed=True
                output.append(row)
            if changed:
                if isinstance(obj,dict):obj['Items']=output
                else:obj=output
                save(path,json.dumps(obj,ensure_ascii=False,indent=2).encode('utf8'))
    save(Path(root)/'DreamRivakes_Data/resources.assets',assets.normalize_text_lengths())
    document={'format':'mjh-six-options-2210','forge':bool(enabled and forge),'martial':bool(enabled and martial),'changes':actions}
    save(state_path,json.dumps(document,ensure_ascii=False,indent=2).encode('utf8'))
    if dormant:save(Path(root)/SWITCH_STATE,json.dumps(switches,ensure_ascii=False,indent=2).encode('utf8'))
    reads.update(store.reads)
    return report
