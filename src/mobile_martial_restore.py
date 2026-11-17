"""Restore the verified subset of mobile martial graphs, without overwriting PC arts."""
from pathlib import Path
from dataclasses import dataclass
import json,copy,hashlib,re

STATE='装备编辑器配置/手游专属武学恢复.json'

@dataclass
class RestorePlan:
    root:Path
    prepared:tuple
    installed:dict

def source_pack():
    from engine import DATA_ROOT
    return json.loads((DATA_ROOT/'mobile_martial_pack.json').read_text('utf8'))

def compare_existing(store,pack):
    """Explain same-name differences without treating a name as equivalence."""
    out=[];languages=store.table('Language')
    for spec in pack['manifest']:
        if not spec['available']:continue
        graph=pack['graphs'][str(spec['mobile_id'])];source=graph['nodes']['Martial:'+str(spec['mobile_id'])]['row']
        candidates=[r for r in store.table('Martial').values() if languages.get(r['NameID'],{}).get('Ch_Text')==spec['name']]
        for row in candidates:
            differences={}
            for field in ('Rank','DepartEnum','KFFeature'):
                if source[field]!=row[field]:differences[field]={'mobile':source[field],'pc':row[field]}
            for field in ('GrowProIDs','UnlockClauses','MartMovIDs'):
                if len(source[field])!=len(row[field]):differences[field+'数量']={'mobile':len(source[field]),'pc':len(row[field])}
            # IDs alone cannot demonstrate equivalence. When the structural
            # counts agree, retaining both is the safe choice until the full
            # graphs can be proven identical; the PC record is never replaced.
            out.append({'name':spec['name'],'mobile_id':spec['mobile_id'],'pc_id':row['BaseID'],'differences':differences,'decision':'保留PC配置，另建新·版本；未以同名或相同编号认定效果相同'})
    return out

def _materialize_growth(packet,pack):
    from growth_runtime import MARKER
    from fractions import Fraction
    # Copy shared formulas per owner before remapping. Source clauses already
    # encode their attribute kind; take the source owner's rank and department.
    pending={};nextid=1_680_000_000
    for node in list(packet['nodes'].values()):
        if node['table']!='Martial':continue
        m=node['row']
        for idx,cid in enumerate(list(m['GrowProIDs'])):
            token='MartialItem:'+str(cid);c=copy.deepcopy(packet['nodes'][token]['row']);changed=False
            for slot in (1,2):
                kind=c.get('EffectEnum'+str(slot),0);attr=c.get('AttrEnum'+str(slot),0)
                if kind not in (7,9):continue
                opts=[v for v in pack['growth'].values() if v.get('AttrType')==attr and v.get('IsRoleAttr')==int(kind==7) and v.get('IsGrowup')==1 and v.get('KfType') in (0,m['DepartEnum'])]
                exact=[v for v in opts if v.get('KfType')==m['DepartEnum']];opts=exact or opts
                if len(opts)!=1:raise ValueError('手游成长来源不唯一：'+token)
                grade=c.get('Grade'+str(slot),0) or 2
                factor=next((v['GrowFactor'] for v in pack['growth_grades'].values() if v['Grade']==grade),10000) if kind==9 else 10000
                values=opts[0]['RankDatas'];base=values.get(str(m['Rank']),0) if isinstance(values,dict) else values[m['Rank']-1]
                value=Fraction(base*factor,10000)
                if value.denominator!=1:raise ValueError('手游成长不是可无损表达的整数：'+token)
                c['Effect'+str(slot)+'Value']=[int(value),MARKER];c['Grade'+str(slot)]=0;changed=True
            if not changed:continue
            signature=json.dumps(c,sort_keys=True)
            cache=pending.get((cid,signature))
            if cache is None:
                while 'MartialItem:'+str(nextid) in packet['nodes']:nextid+=1
                cache=nextid;nextid+=1;c['BaseID']=cache
                newtoken='MartialItem:'+str(cache)
                packet['nodes'][newtoken]={'table':'MartialItem','id':cache,'row':c,'wire':''}
                packet['edges'][newtoken]=copy.deepcopy(packet['edges'].get(token,[]));pending[(cid,signature)]=cache
            m['GrowProIDs'][idx]=cache
            for e in packet['edges'][f"Martial:{node['id']}"]:
                if e['path']==['GrowProIDs',idx]:e['target']='MartialItem:'+str(cache)

def _subset(pack,ids):
    result=dict(pack);ids=set(map(str,ids))
    result['manifest']=[s for s in pack['manifest'] if str(s['mobile_id']) in ids]
    result['graphs']={k:v for k,v in pack['graphs'].items() if k in ids}
    return result

def _append_missing(store,pack,prior,payloads,originals,results):
    """Import new roots over staged files, preserving every existing batch's IDs."""
    from editor_temp import workspace_temp
    missing={str(s['mobile_id']) for s in pack['manifest'] if s['available']}-set(prior['installed'])
    if not missing:return prior
    with workspace_temp(store.root,'mjh_mobile_upgrade_') as folder:
        virtual=Path(folder).resolve()
        paths=set((store.root/'TableData').glob('*.bytes'))
        paths.update((store.root/'DreamRivakes_Data/StreamingAssets').glob('*.bytes'))
        paths.update(store.root.glob('装备编辑器配置/*.json'))
        paths.update((store.root/'ModProject/GameProject/Mod_MJH/Json').glob('*.json'))
        paths.update((store.root/'DreamRivakes_Data').glob('mjh_tianji_*.assets'))
        paths.update((store.root/'DreamRivakes_Data').glob('mjh_wuxiang_*.assets'))
        paths.update(store.root/p for p in ('DreamRivakes.exe','DreamRivakes_Data/resources.assets','DreamRivakes_Data/globalgamemanagers',
            'DreamRivakes_Data/Plugins/RaceLogic_Release_x64.dll','DreamRivakes_Data/Plugins/ClientDll.dll'))
        for path in paths|set(payloads):
            raw=payloads.get(path,store.read(path))
            if raw is None:continue
            target=virtual/path.relative_to(store.root);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        added=plan(virtual,_pack=_subset(pack,missing),_fresh=True)
        batch=json.loads(added.prepared[0][virtual/STATE])
        for path,raw in added.prepared[0].items():
            if path==virtual/STATE:continue
            real=store.root/path.relative_to(virtual);originals.setdefault(real,store.read(real));payloads[real]=raw
        results.extend(added.prepared[2])
    state=copy.deepcopy(prior);state.setdefault('additional_batches',[]).append(batch)
    state['installed'].update(added.installed);state['source_manifest']=pack['manifest']
    state['effect_revision']=pack.get('revision',1)
    results.append('增量补入 '+str(len(missing))+' 门武学；保留已恢复武学的编号、学习等级和秘籍。')
    return state

def plan(root,add_test_books=False,save_path=None,*,_pack=None,_fresh=False):
    from object_bundle import Store,allocate,plan_import,key
    from object_runtime import finish_runtime
    from martial_editor import MartialLibrary,performance_blocks
    from editor_temp import workspace_temp
    from client_config import Assets
    from lua_data import dump
    from engine import digest
    root=Path(root).resolve();store=Store(root);pack=_pack if _pack is not None else source_pack();payloads={};results=[];notes=[]
    before=store.read(root/STATE);prior=json.loads(before) if before and not _fresh else {}
    if prior.get('installed'):
        installed=prior['installed']
        for mid,rec in installed.items():
            actual=store.table('Martial').get(rec['id'])
            if not actual:raise ValueError('已恢复的武学记录缺失，请先恢复备份：'+mid)
        originals=dict(store.reads)
        if prior.get('effect_revision',1)<pack.get('revision',1):
            from mobile_martial_repair import stage
            # Batches have independent source-to-target maps; never let a later
            # import overwrite an earlier map for shared source expression IDs.
            batches=prior.get('additional_batches',[])
            extra_ids={mid for batch in batches for mid in batch['installed']}
            mainpack=_subset(pack,set(prior['installed'])-extra_ids)
            payloads,more,prior,changed=stage(store,mainpack,prior);originals.update(more)
            for i,batch in enumerate(batches):
                if batch.get('effect_revision',1)>=pack.get('revision',1):continue
                more_store=Store(root,overlay=payloads)
                more_payloads,more,updated,extra=stage(more_store,_subset(pack,batch['installed']),batch)
                payloads.update(more_payloads);originals.update(more);changed.extend(extra)
                prior['additional_batches'][i]=updated
            payloads[root/STATE]=json.dumps(prior,ensure_ascii=False,indent=2).encode('utf8')
            results.append('核对并更新手游效果依赖 '+str(len(changed))+' 条；保留武学编号、学习等级和秘籍。')
        else:results.append('本目录已恢复手游专属武学，保留现有配置，不重复新增。')
        prior=_append_missing(store,pack,prior,payloads,originals,results)
        installed=prior['installed']
        state_raw=json.dumps(prior,ensure_ascii=False,indent=2).encode('utf8')
        if state_raw!=before:payloads[root/STATE]=state_raw
    else:
        comparisons=compare_existing(store,pack)
        for rec in comparisons:results.append('同名核对：'+rec['name']+'（PC '+str(rec['pc_id'])+'），成长/解锁等配置不能证明完全相同，保留PC记录，另建手游版本。')
        nodes={};edges={};anchors={};performances={};names={}
        for spec in pack['manifest']:
            if not spec['available']:continue
            graph=pack['graphs'][str(spec['mobile_id'])]
            nodes.update(copy.deepcopy(graph['nodes']));edges.update(copy.deepcopy(graph['edges']));anchors.update(copy.deepcopy(graph['anchors']));performances.update(copy.deepcopy(graph['performances']));names[spec['mobile_id']]=spec['name']
        if not nodes:raise ValueError('此资源包没有通过完整性检查的手游武学')
        for n in nodes.values():n['wire']=''
        # Anchors remain native. Only a same-ID, same-named clan is accepted.
        for token,row in list(anchors.items()):
            name,ident=token.split(':');target=store.table(name).get(int(ident))
            if name=='Clan' and row.get('pc_id')==93:
                target=store.table('Clan').get(93)
                if not target or target.get('ClanName')!='散武学':raise ValueError('PC缺少原生散武学分类')
                replacement='Clan:93';anchors[replacement]=copy.deepcopy(target);del anchors[token]
                for source,ee in edges.items():
                    for e in ee:
                        if e['target']!=token:continue
                        e['target']=replacement;obj=nodes[source]['row']
                        for part in e['path'][:-1]:obj=obj[part]
                        obj[e['path'][-1]]=93
                notes.append('手游门派「'+row['mobile_name']+'」统一归为散武学。')
                continue
            if not target or (name=='Clan' and target.get('ClanName')!=row.get('ClanName')):raise ValueError('目标游戏门派与手游来源不同：'+token)
            anchors[token]=copy.deepcopy(target)
        packet={'format':'mjh-selected-object','version':2,'kind':'Martial','root':next(iter(names)),'nodes':nodes,'edges':edges,'anchors':anchors,'role_groups':{},'extras':{},'enums':{k:v for k,v in pack['enums'].items() if k in ('SkillEffectDescription.SED_SkillLogic_CommonInitiativeSkill','SkillEffectDescription.SED_SkillLogic_CommonFanJiProcess')}}
        from mobile_martial_identity import prepare as prepare_identity,ALIASES
        performances,reference_rules,bindings=prepare_identity(packet,set(names),store,performances)
        _materialize_growth(packet,pack)
        mapping=allocate(packet,store)
        # Shared native statuses (bleeding, burning, etc.) must interoperate
        # with PC arts. Reuse only a same-ID, entire-behavior match; changed
        # mobile statuses keep their own graph and never replace PC records.
        from object_identity_reuse import reuse_identities
        class NativeAnchors:
            enums=store.enums
            native=store.native
            assets=store.assets
            def table(self,name):return store.table(ALIASES.get(name,name))
        reused=reuse_identities(packet,NativeAnchors(),mapping,candidate_tables=('Buff',))
        active=set();queue=[key('Martial',i) for i in names]
        while queue:
            token=queue.pop()
            if token in active or token in reused or token not in packet['nodes']:continue
            active.add(token);queue.extend(e['target'] for e in packet['edges'][token])
        performances={t:p for t,p in performances.items() if t in active}
        occupied=set(performance_blocks(store.assets.script('SkillPerformance.lua')))
        for token in performances:
            ident=mapping[token]
            if ident in occupied:
                table=token.split(':')[0]
                used=set(store.table(table))|set(mapping.values())|occupied
                ident=next(i for i in range(30000,65536) if i not in used) if table=='Skill' else next(i for i in range(1_650_000_000,1_660_000_000) if i not in used)
                mapping[token]=ident
            occupied.add(ident)
        for mid,name in names.items():
            row=packet['nodes'][key('Martial',mid)]['row']
            row.update(Exclusive=[],CouldCopy=1,Display=1,Drop=0,LvLimit=10,AlowEdit=1)
            lang=packet['nodes'][key('Language',row['NameID'])]['row'];lang['Ch_Text']='新·'+name
        # Dedicated records make source/target ID clashes harmless.
        payloads,originals,rows=plan_import(store,packet,mapping,active=active,reference_rules=reference_rules,native_aliases=ALIASES)
        # SkillEffect presentation uses the effect ID, not a Skill row's ID.
        path=root/'DreamRivakes_Data/resources.assets';assets=Assets(payloads[path]);text=assets.script('SkillPerformance.lua');existing=performance_blocks(text);entries=[]
        for token,presentation in performances.items():
            ident=mapping[token]
            if ident in existing:raise ValueError('手游招式动画编号被占用：'+str(ident))
            presentation=copy.deepcopy(presentation)
            if 'id' in presentation:presentation['id']=ident
            entries.append(f'[{ident}] = '+dump(presentation)+',\n')
        match=re.search(r'\}\s*return\s+t\s*$',text)
        if not match:raise ValueError('目标招式动画表结构不兼容')
        payloads[path]=assets.replace_script('SkillPerformance.lua',text[:match.start()]+''.join(entries)+text[match.start():])
        finish_runtime(store,packet,mapping,rows,payloads)
        # Reuse the native book/fragment writer on the complete staged tables.
        with workspace_temp(root,'mjh_mobile_books_') as folder:
            virtual=Path(folder).resolve()
            needed={root/'TableData'/f'{t}.bytes' for t in __import__('martial_editor').TABLES}
            needed|={root/'TableData'/f'{t}.bytes' for t in ('AttrIsPercent','KungfuBase')}
            needed|={root/'DreamRivakes_Data/resources.assets',root/'DreamRivakes_Data/Plugins/RaceLogic_Release_x64.dll',root/'DreamRivakes_Data/Plugins/ClientDll.dll'}
            needed.update(root.glob('装备编辑器配置/*.json'));needed.update((root/'ModProject/GameProject/Mod_MJH/Json').glob('*.json'))
            for p in needed|set(payloads):
                raw=payloads.get(p,store.read(p))
                if raw is None:continue
                v=virtual/p.relative_to(root);v.parent.mkdir(parents=True,exist_ok=True);v.write_bytes(raw)
            lib=MartialLibrary(virtual);installed={}
            from book_acquisition import configure
            for mid,name in names.items():
                target=mapping[key('Martial',mid)]
                lib.configure_books(target,True,True);configure(lib,target,True)
                lib.set('Martial',target,{'Exclusive':[],'CouldCopy':1,'Display':1,'Drop':0})
                books=[r['BaseID'] for r in lib.books(target) if r['ItemType']==15]
                if len(books)!=1:raise ValueError('手游秘籍配置不唯一：'+name)
                installed[str(mid)]={'id':target,'name':'新·'+name,'book':books[0]}
                # Full target graphs are deliberately left intact; no PC record
                # is replaced merely because its display name is the same.
                results.append(f'恢复 {name} → 新·{name}（武学 {target}，秘籍 {books[0]}），解除专属，允许抄录及原生获取。')
            more,_=lib.plan(preserve_imported=True)
            for p,raw in more.items():payloads[root/p.relative_to(virtual)]=raw
        from martial_collection import augment
        from mobile_martial_acquisition import stage as stage_acquisition
        stage_acquisition(store,payloads,installed)
        augment(root,payloads,originals,notes)
        state={'version':1,'effect_revision':pack.get('revision',1),'source_apk_sha256':pack['source_apk_sha256'],'installed':installed,'nodes':mapping,'reused_native_status_graphs':reused,'native_identity_bindings':bindings,'same_name_comparisons':comparisons,'source_manifest':pack['manifest']}
        payloads[root/STATE]=json.dumps(state,ensure_ascii=False,indent=2).encode('utf8')
        originals.update(store.reads)
    if before and prior.get('installed'):
        from mobile_martial_resync import stage as resync
        resync(root,prior,pack,payloads,originals,results)
        from martial_collection import augment
        augment(root,payloads,originals,notes)
    if add_test_books:
        if save_path is None:raise ValueError('请选择测试秘籍要放入的当前周目存档')
        save_path=Path(save_path).resolve()
        if not save_path.is_relative_to(root) or save_path.name!='Save.sav':raise ValueError('测试秘籍存档路径无效')
        from engine import Catalog,Save
        from warehouse_books import generate_book
        # Catalog consumes the staged item tables without committing to the game.
        with workspace_temp(root,'mjh_mobile_test_books_') as folder:
            virtual=Path(folder).resolve()
            required={p for p in root.glob('TableData/*.bytes')}|{root/'DreamRivakes_Data/resources.assets',root/'DreamRivakes.exe'}
            for p in required:
                raw=payloads.get(p,store.read(p))
                if raw is None:continue
                v=virtual/p.relative_to(root);v.parent.mkdir(parents=True,exist_ok=True);v.write_bytes(raw)
            catalog=Catalog(virtual);raw=payloads.get(save_path,store.read(save_path))
            if not raw:raise ValueError('测试存档不存在')
            for rec in installed.values():raw,_=generate_book(Save(save_path,catalog,raw),rec['book'],1)
            originals.setdefault(save_path,store.read(save_path));payloads[save_path]=raw
        results.append(f'所选存档当前周目仓库各添加 1 本测试秘籍，共 {len(installed)} 本；不改其他存档。')
    for spec in pack['manifest']:
        if not spec['available']:notes.append('跳过 '+spec['name']+'：'+'；'.join(spec['skip_reasons']))
    from mobile_effect_resources import stage as stage_effect_resources
    stage_effect_resources(store,payloads,installed,results)
    from mobile_martial_presentation import stage as stage_presentation
    stage_presentation(store,payloads,installed,results)
    from collection_ui_runtime import repair as repair_collection
    path=root/'DreamRivakes_Data/resources.assets';raw=payloads.get(path,store.read(path));updated=repair_collection(raw)
    if raw!=updated:payloads[path]=updated;results.append('修复江湖收藏首次打开和列表初始化顺序，保留已有收藏进度。')
    originals.update(store.reads)
    for path in payloads:originals.setdefault(path,store.read(path))
    payloads={p:raw for p,raw in payloads.items() if originals.get(p)!=raw}
    return RestorePlan(root,(payloads,originals,results,notes,dict(store.reads)),installed)

def apply(value):
    from feature_save import apply as commit
    return commit(value.root,value.prepared)
