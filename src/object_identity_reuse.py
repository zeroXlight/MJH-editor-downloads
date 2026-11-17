"""Prove identity reuse before allocating recursive import dependencies.

This runs before portable growth materialization. A shared native growth clause
and its exported independent value are compared in the owning martial context.
Character imports can also match same-name martials, ignoring only role
attribute/mastery grants. Power, casts and recursive effects remain compared.
Existing rows are never changed. Failure to prove equality means cloning.
"""
import base64,copy,json
from fractions import Fraction
from codec import fields
from engine import SCHEMAS
from object_bundle import key

LABELS={'BaseID','NameID','DescID','DesID'}

class Different(Exception):pass

def reuse_identities(packet,store,mapping,candidate_tables=('Martial','Gift'),martial_names=False):
    from object_reuse import EFFECT_TABLES
    reusable=EFFECT_TABLES|{'Martial','Skill','AoYi'}
    reused={};growth_cache=None;performance_cache=None
    role_attrs={v for k,v in store.enums.items() if k.startswith('AttrType.')}

    def target(table,ident):
        row=store.table(table).get(ident)
        if row is None:raise Different()
        return row

    def growth(row,context,source,ident,skip_core=False):
        nonlocal growth_cache
        result=copy.deepcopy(row)
        from growth_runtime import custom_values,MARKER
        for slot in (1,2):
            if skip_core and core_slot(row,slot):continue
            if row.get('EffectEnum'+str(slot)) not in (7,9):continue
            value=(packet['extras'].get('independent_growth_by_martial',{}).get(str(context[2]),{}).get(f'{ident}:{slot}') if context else None) if source else None
            if source and value is None:value=packet['extras'].get('independent_growth',{}).get(f'{ident}:{slot}')
            if value is None and custom_values(row,slot):value=row.get('Effect'+str(slot)+'Value')
            if value is None:
                # An old/MOD packet without a captured shared growth value
                # cannot prove that another game's global formula is equal.
                if source or context is None:raise Different()
                if growth_cache is None:
                    from martial_growth import growth_lua
                    growth_cache=growth_lua(store.assets.script('KungfuBase.lua'),store.enums)
                rank,depart=context[:2];kind=row['EffectEnum'+str(slot)];attr=row.get('AttrEnum'+str(slot),0)
                options=[r for r in growth_cache.values() if r['AttrType']==attr and r['IsRoleAttr']==int(kind==7) and r['IsGrowup']==1 and r['KfType'] in (0,depart)]
                options=[r for r in options if r['KfType']==depart] or options
                if len(options)!=1:raise Different()
                grade=row.get('Grade'+str(slot),0) or 2
                factor=next((r['GrowFactor'] for r in store.table('MatGrowUPAttrGrade').values() if r['Grade']==grade),10000) if kind==9 else 10000
                amount=Fraction(options[0]['RankDatas'][rank]*factor,10000)
                if amount.denominator!=1:raise Different()
                value=[int(amount),MARKER]
            result['Effect'+str(slot)+'Value']=value
            result['Grade'+str(slot)]=0
        return result

    def at(row,path):
        for part in path:row=row[part]
        return row

    def defaults(table,row):
        from client_only_fields import without_empty_defaults
        row=without_empty_defaults(table,row)
        if set(row)-set(SCHEMAS[table]):raise Different()
        return {k:row.get(k,[] if s['label']==3 else '' if s['type']==9 else {} if s['type']==11 else 0)
                for k,s in SCHEMAS[table].items() if k not in LABELS}

    def unknown_wire(table,raw):
        known={s['number'] for s in SCHEMAS[table].values()}
        return [f.raw for f in fields(raw) if f.number not in known]

    def name(row,source):
        from engine import clean
        import unicodedata
        ident=row.get('NameID',0)
        value=(packet['nodes'].get(key('Language',ident),{}).get('row',{}) if source else store.table('Language').get(ident,{})).get('Ch_Text','')
        return ' '.join(unicodedata.normalize('NFKC',clean(value)).split()).casefold()

    def core_slot(row,slot):
        # Character attribute/mastery grants, with a known attribute enum.
        # The native effect kind distinguishes role stats from martial stats.
        # In particular,
        # martial power (kind 9 / attribute 359) remains a strict combat check.
        attr=row.get('AttrEnum'+str(slot),0)
        return row.get('EffectEnum'+str(slot)) in (7,8) and attr>0 and attr in role_attrs

    def canonical(table,row,source,ident):
        row=copy.deepcopy(row)
        if table=='MartialItem':
            keys=('EffectEnum{n}','AttrEnum{n}','SkillID{n}','MartialFilter{n}','Effect{n}Value','Grade{n}')
            kept=[]
            for slot in (1,2):
                if core_slot(row,slot) and not row.get('SkillID'+str(slot)):continue
                if row.get('EffectEnum'+str(slot)) or row.get('SkillID'+str(slot)):
                    kept.append({k:row.get(k.format(n=slot),[] if 'Value' in k else 0) for k in keys})
            for slot in (1,2):
                for k in keys:row[k.format(n=slot)]=kept[slot-1][k] if slot<=len(kept) else ([] if 'Value' in k else 0)
        elif table=='Martial':
            # Reuse keeps the target's learning cap and acquisition settings.
            # These are not combat clauses and must never be copied over it.
            for field in ('LvLimit','CouldCopy','Display','Drop','AlowEdit'):row.pop(field,None)
            for field in ('GrowProIDs','UnlockClauses','MartMovIDs'):
                keep=[]
                for index,cid in enumerate(row.get(field,[])):
                    node=packet['nodes'].get(key('MartialItem',cid)) if source else None
                    clause=node.get('row') if node else (store.table('MartialItem').get(cid) if not source else None)
                    raw=base64.b64decode(node.get('wire',''),validate=True) if node else getattr(store,'native',{}).get('MartialItem',{}).get(cid,b'')
                    pure=clause is not None and not (set(clause)-set(SCHEMAS['MartialItem'])) and not unknown_wire('MartialItem',raw)
                    pure=pure and any(core_slot(clause,s) for s in (1,2)) and all(not clause.get('EffectEnum'+str(s)) or core_slot(clause,s) for s in (1,2)) and all(not clause.get('SkillID'+str(s)) for s in (1,2))
                    if not pure:keep.append(index)
                row[field]=[row[field][i] for i in keep]
                if field=='UnlockClauses' and 'UnlockLvls' in row:
                    if len(row['UnlockLvls'])!=len((packet['nodes'][key('Martial',ident)]['row'] if source else target('Martial',ident)).get(field,[])):raise Different()
                    row['UnlockLvls']=[row['UnlockLvls'][i] for i in keep]
        return row

    def equivalent(start,candidate=None,relaxed=False):
        nonlocal performance_cache
        queue=[(start,candidate if candidate is not None else packet['nodes'][start]['id'],None,None)];seen=set();proposed={}
        while queue:
            token,ident,source_context,target_context=queue.pop()
            stamp=(token,ident,source_context,target_context)
            if stamp in seen:continue
            seen.add(stamp)
            if len(seen)>30000:raise Different()
            node=packet['nodes'][token];table=node['table'];source=node['row'];other=target(table,ident)
            if token!=start and table=='Martial' and reused.get(token)==ident:continue
            # Martial/gift identities are never substituted by an unrelated ID.
            if table in ('Martial','Gift') and ident!=node['id']:
                if not (relaxed and table=='Martial' and name(source,True) and name(source,True)==name(other,False)):raise Different()
            if table in reusable:
                if token in reused and reused[token]!=ident:raise Different()
                if token in proposed and proposed[token]!=ident:raise Different()
                proposed[token]=ident
            if table=='Martial':
                source_context=(source.get('Rank'),source.get('DepartEnum'),node['id'])
                target_context=(other.get('Rank'),other.get('DepartEnum'),ident)
                # Recipes are reverse links, absent from the martial row.
                source_recipes={n['id']:t for t,n in packet['nodes'].items() if n['table']=='AoYi' and n['row'].get('AoYiID')==node['id']}
                target_recipes={i for i,r in store.table('AoYi').items() if r.get('AoYiID')==ident}
                if relaxed:
                    if len(source_recipes)!=len(target_recipes):raise Different()
                    queue.extend((t,i,None,None) for t,i in zip((source_recipes[j] for j in sorted(source_recipes)),sorted(target_recipes)))
                else:
                    if set(source_recipes)!=target_recipes:raise Different()
                    queue.extend((t,i,None,None) for i,t in source_recipes.items())
            if table=='Skill' or (table=='SkillEffect' and source.get('Name') in (451,537)):
                if performance_cache is None:
                    from martial_editor import performance_blocks
                    from lua_data import parse
                    performance_cache={i:parse(v[2]) for i,v in performance_blocks(store.assets.script('SkillPerformance.lua')).items()}
                a=copy.deepcopy(packet['extras'].get('skill_performance' if table=='Skill' else 'effect_performance',{}).get(str(node['id'])))
                b=copy.deepcopy(performance_cache.get(ident))
                if isinstance(a,dict):a.pop('id',None)
                if isinstance(b,dict):b.pop('id',None)
                if a!=b:raise Different()
            raw=base64.b64decode(node.get('wire',''),validate=True)
            native=getattr(store,'native',{}).get(table,{}).get(ident,b'')
            if unknown_wire(table,raw)!=unknown_wire(table,native):raise Different()
            a=growth(source,source_context,True,node['id'],relaxed) if table=='MartialItem' else copy.deepcopy(source)
            b=growth(other,target_context,False,ident,relaxed) if table=='MartialItem' else copy.deepcopy(other)
            if relaxed:a=canonical(table,a,True,node['id']);b=canonical(table,b,False,ident)
            if relaxed and table in ('Martial','MartialItem'):
                from object_bundle import references
                edges=[dict(path=p,target=key(t,i),string=isinstance(a.get(p[0]),str)) for p,t,i in references(table,a,store.enums)]
            else:edges=packet['edges'][token]
            for edge in edges:
                child=edge['target'];child_table,old=child.split(':');old=int(old)
                if edge['path'][0] in LABELS:
                    if child in packet['nodes'] and other.get(edge['path'][0],0) not in store.table('Language'):raise Different()
                    continue
                value=at(b,edge['path'])
                if edge.get('string'):
                    if not isinstance(value,str) or not value.isdecimal():raise Different()
                    value=int(value)
                if type(value) is not int or value<=0:raise Different()
                if child in packet['nodes']:
                    if child_table not in reusable|{'Language'}:raise Different()
                    queue.append((child,value,source_context,target_context))
                else:
                    # World and character references have identity semantics.
                    if value!=old or (child_table=='@Role' and str(old) in packet.get('role_groups',{})):raise Different()
                    if child_table!='@Role' and packet.get('anchors',{}).get(child)!={'missing':True}:
                        from object_bundle import anchor_compatible
                        if not anchor_compatible(child_table,packet.get('anchors',{}).get(child),store.table(child_table).get(old)):raise Different()
                marker='@'+child_table
                for row in (a,b):
                    parent=row
                    for part in edge['path'][:-1]:parent=parent[part]
                    parent[edge['path'][-1]]=marker
            if defaults(table,a)!=defaults(table,b):raise Different()
        return proposed

    root=key(packet['kind'],packet['root'])
    for token,node in packet['nodes'].items():
        if token==root or token in reused or node['table'] not in candidate_tables:continue
        if node['id'] not in store.table(node['table']):continue
        try:proposal=equivalent(token)
        except (Different,KeyError,IndexError,TypeError,ValueError):continue
        reused.update(proposal);mapping.update(proposal)
    if martial_names and 'Martial' in candidate_tables:
        names={}
        for ident,row in sorted(store.table('Martial').items()):
            label=name(row,False)
            if label:names.setdefault(label,[]).append(ident)
        for token,node in packet['nodes'].items():
            if token==root or token in reused or node['table']!='Martial':continue
            label=name(node['row'],True)
            if not label:continue
            options=list(names.get(label,[]))
            if node['id'] in options:options.remove(node['id']);options.insert(0,node['id'])
            for ident in options:
                try:equivalent(token,ident,relaxed=True)
                except (Different,KeyError,IndexError,TypeError,ValueError):continue
                # The exemption belongs to this whole martial, never a shared
                # clause that may also be used by a newly imported martial.
                reused[token]=ident;mapping[token]=ident
                break
        # Same-ID gifts may refer to a martial whose source ID was remapped.
        # Resolve that already-proven identity while keeping the gift itself
        # under its full original-ID/function comparison.
        for token,node in packet['nodes'].items():
            if token==root or token in reused or node['table']!='Gift' or 'Gift' not in candidate_tables:continue
            if node['id'] not in store.table('Gift'):continue
            try:proposal=equivalent(token)
            except (Different,KeyError,IndexError,TypeError,ValueError):continue
            reused.update(proposal);mapping.update(proposal)
        packet['extras']['import_martial_matches']=[dict(source_id=n['id'],target_id=reused.get(t),name=name(n['row'],True),same_name_candidates=len(names.get(name(n['row'],True),[]))) for t,n in packet['nodes'].items() if n['table']=='Martial' and t!=root]
    return reused
