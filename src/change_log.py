"""Plain-language audit of actual before/after data. No game writes here."""
import copy,json,re
from collections import Counter
from pathlib import Path
from datetime import datetime

def entry(category,name,action,effect):
    return {'category':category,'name':str(name),'action':action,'effect':str(effect)}

def line(row):
    return f"[{row['category']}] '{row['name']}' '{row['action']}' '{row['effect']}'"

def rows(raw,name):
    from codec import decode
    from engine import table_rows,SCHEMAS
    if not raw:return {}
    return {r['BaseID']:r for r in (decode(b,name,SCHEMAS) for b in table_rows(raw))}

def table_changes(root,payloads,originals):
    from engine import SCHEMAS
    result={}
    for path,after in payloads.items():
        path=Path(path);relative=path.relative_to(root)
        if relative.parent==Path('ModProject/GameProject/Mod_MJH/Json') and path.name.startswith('Item_') and path.suffix=='.json':
            before=originals.get(path)
            old={r['BaseID']:r for r in json.loads(before.decode('utf-8-sig')).get('Items',[])
                 if isinstance(r,dict) and isinstance(r.get('BaseID'),int)} if before else {}
            new={r['BaseID']:r for r in json.loads(after.decode('utf-8-sig')).get('Items',[])
                 if isinstance(r,dict) and isinstance(r.get('BaseID'),int)} if after else {}
            diff={i:(old.get(i),new.get(i)) for i in old.keys()|new.keys() if old.get(i)!=new.get(i)}
            if diff:
                existing=result.setdefault('Item',{})
                existing.update({i:pair for i,pair in diff.items() if i not in existing})
            continue
        if relative.parent!=Path('TableData') or path.suffix!='.bytes' or path.stem not in (set(SCHEMAS)|{'Difficult','CommonConfig'}):continue
        before=originals.get(path)
        try:
            if path.stem in ('Difficult','CommonConfig'):
                from caps import proto_profile
                old={int(i):r for i,r in proto_profile(before,path.stem).items()} if before else {}
                new={int(i):r for i,r in proto_profile(after,path.stem).items()} if after else {}
            else:old,new=rows(before,path.stem),rows(after,path.stem)
        except (ValueError,KeyError,UnicodeDecodeError,IndexError):continue
        diff={i:(old.get(i),new.get(i)) for i in old.keys()|new.keys() if old.get(i)!=new.get(i)}
        if diff:result.setdefault(path.stem,{}).update(diff)
    return result

def record_logs(catalog,r,a,b):
    logs=[]
    delta={k:b[k] for k in b if a.get(k)!=b[k]}
    item=catalog.items.get(r['type'],{});category='武器' if item.get('ItemType') in (8,9,10,11,12,13,14,18,19,27,28,29,30) else '装备'
    if 'grade' in delta:logs.append(entry(category,r['name'],'修改强化等级',f"{r['name']} +{a['grade']} → +{b['grade']}"))
    for group,title in [('white','基础属性'),('green','铸造属性'),('blue','蓝字加成')]:
        ca=Counter(json.dumps(v,sort_keys=True) for v in a[group]);cb=Counter(json.dumps(v,sort_keys=True) for v in b[group])
        for action,diff in [('删除',ca-cb),('新增',cb-ca)]:
            for encoded,count in diff.items():
                value=json.loads(encoded);text=catalog.attr(value['type'])+('+' if value['value']>=0 else '')+catalog.format_value(value['type'],value['value'])
                if group=='blue':text+='（铸造属性加成）'
                if value.get('fixed'):text+='（固定词条）'
                if count>1:text+=f' ×{count}'
                logs.append(entry(category,r['name'],action,f"{r['name']} +{b['grade']} {text} {title}"))
    return logs

def equipment_changes(root,payloads,originals,catalog=None):
    from engine import Catalog,Save
    recipes=[];logs=[]
    paths=[Path(p) for p in payloads if Path(p).name.casefold()=='save.sav']
    if not paths:return recipes,logs
    for path in paths:
        before,after=originals.get(path),payloads[path]
        if not before or not after:continue
        from save_format import validate_reader_header
        try:validate_reader_header(before);validate_reader_header(after)
        except ValueError:
            logs.append(entry('存档',path.parent.name,'修改','存档文件已更新'));continue
        catalog=catalog or Catalog(root)
        old=Save(path,catalog,before);new=Save(path,catalog,after)
        known={r['id']:r for r in old.records if r['editable']}
        for r in new.records:
            prior=known.get(r['id'])
            if not prior or not r['editable'] or prior['type']!=r['type']:continue
            a,b=old.draft(prior),new.draft(r)
            delta={k:b[k] for k in b if a.get(k)!=b[k]}
            if not delta:continue
            recipes.append({'id':r['id'],'type':r['type'],'name':r['name'],'fields':delta,
                            'source_save':str(path.relative_to(root))})
            logs.extend(record_logs(catalog,r,a,b))
    return recipes,logs

def definition_logs(oldlib,newlib):
    """Definitions are changes even before any martial art references them."""
    from martial_preview import filter_description,describe_effects,clan_names
    from martial_editor import SECTIONS
    from martial_ranges import AREA_START,AREA_END
    logs=[]
    views={}
    for lib in (oldlib,newlib):
        view=copy.copy(lib);view.tables={**lib.tables,'Martial':{**lib.tables['Martial'],0:{'DepartEnum':0}}}
        view._preview_clans=clan_names(lib);views[id(lib)]=view
    def action(a,b):return '删除' if b is None else '新增' if a is None else '修改'
    def scope_name(lib,ident):
        # Automatic type belongs to the definition's user, not an arbitrary
        # first martial in the table. Use a neutral preview subject here.
        return filter_description(views[id(lib)],0,ident)
    filters=set(oldlib.tables['MartialFilter'])|set(newlib.tables['MartialFilter'])
    for ident in sorted(filters):
        a=oldlib.tables['MartialFilter'].get(ident);b=newlib.tables['MartialFilter'].get(ident)
        oldname=scope_name(oldlib,ident) if a else None;newname=scope_name(newlib,ident) if b else None
        oldgroup=oldlib.scope_groups.get(str(ident));newgroup=newlib.scope_groups.get(str(ident))
        if a==b and oldname==newname and oldgroup==newgroup:continue
        verb=action(a,b)
        effect=verb+'作用范围词条：'+(oldname+' → '+newname if a and b else newname or oldname)
        logs.append(entry('游戏设置','作用范围词条',verb,effect))
    def range_info(lib,ident,row):
        name=lib.text(row.get('NameID',0)) or '未命名范围'
        cells=set(zip(row.get('PosXs',[]),row.get('PosYs',[])))
        return name,cells
    for ident in sorted(set(oldlib.tables['Range'])|set(newlib.tables['Range'])):
        a=oldlib.tables['Range'].get(ident);b=newlib.tables['Range'].get(ident)
        old=range_info(oldlib,ident,a) if a else None;new=range_info(newlib,ident,b) if b else None
        if a==b and old==new:continue
        verb=action(a,b);label='自定义范围' if AREA_START<=ident<AREA_END else '技能范围'
        current=new or old;name=current[0];detail='全屏范围' if len(current[1])==135 else f'{len(current[1])}格'
        if old and new and old[0]!=new[0]:name=old[0]+' → '+new[0]
        if old and new and old[1]!=new[1]:
            detail+=f'；网格已修改（新增{len(new[1]-old[1])}格，取消{len(old[1]-new[1])}格）'
        logs.append(entry('游戏设置',label,verb,f'{verb}{label}：{name}（{detail}）'))
    # An unbound clause definition has no martial-level stage comparison.
    # Bound clauses keep their existing martial/name/level log instead.
    bound={cid for lib in (oldlib,newlib) for m in lib.tables['Martial'].values() for key in SECTIONS.values() for cid in m.get(key,[])}
    for ident in sorted((set(oldlib.tables['MartialItem'])|set(newlib.tables['MartialItem']))-bound):
        a=oldlib.tables['MartialItem'].get(ident);b=newlib.tables['MartialItem'].get(ident)
        if a==b:continue
        lib=newlib if b else oldlib;row=b or a
        key={1:'GrowProIDs',2:'UnlockClauses',3:'MartMovIDs'}.get(row.get('ItemType'),'UnlockClauses')
        mid=next(iter(lib.tables['Martial']),0)
        texts=[e['name']+' '+e['value'] for e in describe_effects(lib,mid,key,row)]
        verb=action(a,b)
        logs.append(entry('游戏设置','武学词条',verb,verb+'武学词条：'+('；'.join(texts) or '无效果')+'（未绑定武学）'))
    return logs

def affected_martials(oldlib,newlib,changes):
    """Skip unchanged martial reports; new unbound definitions affect none."""
    from martial_editor import SECTIONS
    if any(a is not None for a,b in changes.get('Language',{}).values()):
        return set(oldlib.tables['Martial'])|set(newlib.tables['Martial'])
    result=set(changes.get('Martial',{}));clauses=set(changes.get('MartialItem',{}))
    filters=set(changes.get('MartialFilter',{}))
    filters.update(int(i) for i in oldlib.scope_groups.keys()|newlib.scope_groups.keys() if oldlib.scope_groups.get(i)!=newlib.scope_groups.get(i))
    skills=set(changes.get('Skill',{}));effects={i for i,(a,b) in changes.get('SkillEffect',{}).items() if a is not None}
    if effects:
        for lib in (oldlib,newlib):
            for sid in lib.tables['Skill']:
                if sid in skills:continue
                try:graph=lib.effect_graph(sid)
                except ValueError:continue
                if effects.intersection(graph):skills.add(sid)
    for lib in (oldlib,newlib):
        for mid,m in lib.tables['Martial'].items():
            if mid in result:continue
            if 'MatGrowUPAttrGrade' in changes and m.get('GrowProIDs'):result.add(mid);continue
            for key in SECTIONS.values():
                ids=m.get(key,[])
                if clauses.intersection(ids):result.add(mid);break
                if any(row.get('SkillID'+str(slot)) in skills or row.get('MartialFilter'+str(slot)) in filters
                       for cid in ids for row in [lib.tables['MartialItem'].get(cid,{})] for slot in (1,2)):
                    result.add(mid);break
    return result

def draft_views(lib):
    base=getattr(lib,'log_base_tables',None)
    if base is None:raise ValueError('请重新读取武学后查看草稿日志')
    old=copy.copy(lib);old.tables=base;old.scope_groups=lib.scope_original
    new=copy.copy(lib);new.tables=lib.tables
    for view in (old,new):
        view.originals=dict(lib.originals)
        if hasattr(view,'_preview_clans'):del view._preview_clans
    if lib.growth and lib.growth.changes:
        from martial_growth import growth_lua
        old.growth=copy.copy(lib.growth);old.growth.rows=growth_lua(lib.assets.script('KungfuBase.lua'),lib.enums)
    changes={n:{i:(base[n].get(i),lib.tables[n].get(i)) for i in rows if base[n].get(i)!=lib.tables[n].get(i)}
             for n,rows in lib.changes.items() if rows}
    return (old,new),{n:rows for n,rows in changes.items() if rows}

def pending_logs(host):
    """Preview staged changes without building assets, DLLs or export packets."""
    logs=[];catalog=host.catalog;root=catalog.root
    if host.save and host.drafts:
        for r in host.save.records:
            if r['offset'] in host.drafts and r['editable']:
                logs.extend(record_logs(catalog,r,host.save.draft(r),host.drafts[r['offset']]))
    if host.effects:
        changes={}
        for ident,draft in host.effects.items():
            a=catalog.items[ident];b={**a,'BlueGift':[v['id'] for v in draft['gifts']],
                'BlueGiftUnlockLv':[v['level'] for v in draft['gifts']],
                'BlueAttr':[v['type'] for v in draft['attrs']],'BlueAttrValue':[v['value'] for v in draft['attrs']],
                'BlueAttrUnlockLv':[v['level'] for v in draft['attrs']],'BlueMartial':[v['martial'] for v in draft['attrs']]}
            if a!=b:changes[ident]=(a,b)
        if changes:logs.extend(summarize(root,{}, {},'待保存改动',catalog=catalog,changes_override={'Item':changes})[0])
    page=host.martial_page;lib=page.library
    role=getattr(host,'role_page',None)
    if role and role.library and role.library.modified():logs.extend(role.library.logs())
    if lib and lib.modified():
        views,changes=draft_views(lib);payloads={}
        for name,original,current,path in [('动画',lib.animation_original,lib.animations,lib.animation_path),
                ('图标',lib.icon_original,lib.icons,lib.icon_path),('作用范围',lib.scope_original,lib.scope_groups,lib.scope_path)]:
            if original!=current:payloads[path]=json.dumps(current,ensure_ascii=False).encode('utf-8')
        payloads.update(lib.icon_files)
        logs.extend(summarize(root,payloads,lib.originals,'待保存改动',views=views,changes_override=changes)[0])
    return logs

def summarize(root,payloads,originals,purpose='修改配置',catalog=None,library=None,views=None,changes_override=None):
    from engine import Catalog,effect_draft,clean
    root=Path(root).resolve();logs=[]
    changes=table_changes(root,payloads,originals) if changes_override is None else changes_override
    equipment,save_logs=equipment_changes(root,payloads,originals,catalog);logs.extend(save_logs)
    lib=library
    scope_path=root/'装备编辑器配置/新增作用范围.json'
    role_path=root/'装备编辑器配置/人物编辑.json'
    if role_path in payloads:
        from role_editor import role_logs,EDIT_TABLES
        before=json.loads((originals.get(role_path) or b'{}').decode('utf-8-sig'))
        after=json.loads((payloads[role_path] or b'{}').decode('utf-8-sig'))
        logs.extend(role_logs(before,after))
    relevant=bool(set(changes)-{'Item'}) or scope_path in payloads
    if role_path in payloads and not (set(changes)-set(EDIT_TABLES)):relevant=False
    if views is None and relevant and lib is None and (root/'DreamRivakes_Data/resources.assets').is_file():
        from martial_editor import MartialLibrary
        lib=MartialLibrary(root)
    oldlib=newlib=None
    if views is not None:oldlib,newlib=views;logs.extend(definition_logs(oldlib,newlib))
    elif lib is not None:
        oldlib=copy.copy(lib);oldlib.tables={n:dict(v) for n,v in lib.tables.items()}
        newlib=copy.copy(oldlib);newlib.tables={n:dict(v) for n,v in oldlib.tables.items()}
        for name,diffs in changes.items():
            if name not in newlib.tables:continue
            for ident,(a,b) in diffs.items():
                # Apply only changed fields to the effective client/mod row.
                prior=oldlib.tables[name].get(ident,a or {})
                if b is None:newlib.tables[name].pop(ident,None);continue
                delta={k:b.get(k,[] if isinstance(a.get(k),list) else 0) for k in (a or {}).keys()|b.keys()
                       if (a or {}).get(k)!=b.get(k)} if a else b
                newlib.tables[name][ident]={**prior,**delta}
        if scope_path in payloads:
            oldlib.scope_groups=json.loads((originals.get(scope_path) or b'{}').decode('utf-8-sig'))
            newlib.scope_groups=json.loads((payloads[scope_path] or b'{}').decode('utf-8-sig'))
        logs.extend(definition_logs(oldlib,newlib))
    if 'Item' in changes:
        catalog=catalog or (Catalog(root) if (root/'DreamRivakes.exe').is_file() else None)
        for ident,(a,b) in changes['Item'].items():
            item=b or a;name=item.get('ItemName',f'装备型号 {ident}')
            if item.get('ItemType') in (15,16):
                logs.append(entry('秘籍',name,'删除' if b is None else ('新增' if a is None else '修改'),'秘籍配置已更新'));continue
            category='武器' if item.get('ItemType') in (8,9,10,11,12,13,14,18,19,27,28,29,30) else '装备'
            da,db=effect_draft(a or {}),effect_draft(b or {})
            for group in ('gifts','attrs'):
                ca=Counter(json.dumps(v,sort_keys=True) for v in da[group]);cb=Counter(json.dumps(v,sort_keys=True) for v in db[group])
                for action,diff in [('删除',ca-cb),('新增',cb-ca)]:
                    for encoded,count in diff.items():
                        value=json.loads(encoded);level=value.get('level',0)
                        if group=='gifts':
                            gift=catalog.gifts.get(value['id'],{}) if catalog else {}
                            label=catalog.text(gift.get('NameID',value['id'])) if catalog else f"天赋 {value['id']}"
                            effect=label+' 天赋效果'
                        else:
                            effect=(catalog.attr(value['type'])+('+' if value['value']>=0 else '')+catalog.format_value(value['type'],value['value'])) if catalog else f"属性 {value['type']} +{value['value']}"
                        if count>1:effect+=f' ×{count}'
                        logs.append(entry(category,name,action,f'{name} +{level} {effect}（同型号装备共用）'))
            fields=[k for k in (a or {}).keys()|(b or {}).keys() if k not in ('BaseID','BlueGift','BlueGiftUnlockLv','BlueAttr','BlueAttrValue','BlueAttrUnlockLv','BlueMartial') and (a or {}).get(k)!=(b or {}).get(k)]
            if fields:logs.append(entry(category,name,'修改装备配置','、'.join({'ItemName':'名称','Rank':'品质','ItemDesc':'说明','Icon':'图标','Feature':'装备类型'}.get(k,k) for k in fields)+'已更新'))
    if oldlib is not None:
        from martial_editor import SECTIONS
        from martial_preview import describe_effects
        def stages(lib,mid):
            out=[];m=lib.tables['Martial'].get(mid,{})
            for key in SECTIONS.values():
                for index,cid in enumerate(m.get(key,[])):
                    levels=m.get('UnlockLvls',[]);level=levels[index] if key=='UnlockClauses' and index<len(levels) else None
                    for effect in describe_effects(lib,mid,key,lib.tables['MartialItem'].get(cid,{})):
                        scope=effect['scope'];scope='本武学' if scope.startswith('本武学「') else scope
                        if scope=='按技能 / 模板逻辑执行':text=effect['value'] if effect['value']!='按战斗表达式执行' else effect['name']
                        else:text=scope+effect['name']+effect['value']
                        label=f'{level}级解锁效果' if key=='UnlockClauses' else ('每级成长' if key=='GrowProIDs' else '招式效果')
                        out.append((label,re.sub(r'\s+','',clean(text))))
            return Counter(out)
        for mid in sorted(affected_martials(oldlib,newlib,changes)):
            a=oldlib.tables['Martial'].get(mid);b=newlib.tables['Martial'].get(mid)
            name=newlib.name(mid) if b else oldlib.name(mid)
            ca=stages(oldlib,mid) if a else Counter();cb=stages(newlib,mid) if b else Counter()
            if a is None:logs.append(entry('武学',name,'新增武学','新建武学配置'))
            if b is None:logs.append(entry('武学',name,'删除武学','移除武学配置'))
            for action,diff in [('删除',ca-cb),('新增',cb-ca)]:
                for (label,text),count in diff.items():logs.append(entry('武学',name,action+label,text+(f' ×{count}' if count>1 else '')))
            for key,label in [('NameID','名称'),('DesID','说明'),('DepartEnum','类别'),('Rank','品质'),('ClanID','门派'),('LvLimit','修炼上限'),('ColdTime','冷却回合'),('Exclusive','专属人物'),('LearnCondition','学习条件'),('LearnConditionValue','学习条件数值'),('MartialTags','附加标签'),('Display','是否显示')]:
                if a and b and a.get(key)!=b.get(key):
                    before,after=a.get(key),b.get(key)
                    if key in ('NameID','DesID'):before,after=oldlib.text(before or 0),newlib.text(after or 0)
                    logs.append(entry('武学',name,'修改'+label,f'{before} → {after}'))
            if a and b:
                handled={'BaseID','NameID','DesID','DepartEnum','Rank','ClanID','LvLimit','ColdTime','Exclusive','LearnCondition','LearnConditionValue','MartialTags','Display','GrowProIDs','MartMovIDs','UnlockClauses','UnlockLvls'}
                labels={'MascCoef':'阳性系数','FemiCoef':'阴性系数','Multistage':'多段标记','Toxic':'有毒标记','AlowEdit':'游戏内可编辑','KFFeature':'奥义类别','CouldCopy':'可抄录秘籍','Drop':'禁止请教 / 观摩'}
                for k in a.keys()|b.keys():
                    if k not in handled and a.get(k)!=b.get(k):
                        before,after=a.get(k),b.get(k)
                        if k in ('MascCoef','FemiCoef'):before,after=(before or 0)/10000,(after or 0)/10000
                        logs.append(entry('武学',name,'修改'+labels.get(k,'基础设置'),f'{labels.get(k,k)}：{before} → {after}'))
                changed_skills=set(changes.get('Skill',{}));changed_effects=set(changes.get('SkillEffect',{}))
                owner_skills={row.get('SkillID'+str(s),0) for key in SECTIONS.values() for cid in b.get(key,[]) for row in [newlib.tables['MartialItem'].get(cid,{})] for s in (1,2)}
                linked=owner_skills&changed_skills
                if linked and ca==cb:logs.append(entry('武学',name,'修改技能效果','招式 / 被动技能的战斗参数已更新'))
                if changed_effects and ca==cb:
                    for sid in owner_skills:
                        skill=newlib.tables['Skill'].get(sid,{})
                        if any(any(e in changed_effects for e in v if isinstance(e,int)) for v in skill.values() if isinstance(v,list)):
                            logs.append(entry('武学',name,'修改战斗效果','攻击或触发效果的战斗参数已更新'));break
        for ident,(a,b) in changes.get('AoYi',{}).items():
            row=b or a;mid=row.get('AoYiID');name=newlib.name(mid) if mid in newlib.tables['Martial'] else oldlib.name(mid) if mid in oldlib.tables['Martial'] else '秘奥义组合'
            recipe=' + '.join((newlib.name(i) if i in newlib.tables['Martial'] else f'未知武学 {i}')+f' {level}级' for i,level in zip(row.get('MartialList',[]),row.get('LVList',[])))
            logs.append(entry('秘奥义',name,'删除' if b is None else ('新增' if a is None else '修改'),recipe+f"；第 {row.get('EffectiveRound',0)} 回合可用"))
    for name in ('Difficult','CommonConfig'):
        if name in changes:logs.append(entry('设置','武学等级上限','修改',purpose))
    for path,after in payloads.items():
        relative=Path(path).relative_to(root)
        if str(relative).startswith('装备编辑器配置') and relative.suffix=='.json' and after!=originals.get(Path(path)):
            if Path(path)==role_path:continue
            if Path(path)==scope_path and oldlib is not None:continue
            logs.append(entry('设置',relative.stem,'删除' if after is None else '修改',relative.stem+'配置已更新'))
        elif 'martial_editor' in relative.parts and relative.suffix=='.png':logs.append(entry('武学图标',relative.stem,'删除' if after is None else '新增','自定义图片'))
        elif 'role_editor' in relative.parts and relative.suffix=='.png':logs.append(entry('人物立绘',relative.stem,'删除' if after is None else '新增','上传的独立立绘图片'))
    if not logs:logs.append(entry('设置','游戏配置','修改',purpose+'；已更新 '+str(len(payloads))+' 个文件'))
    # Stable ordering and exact duplicate removal, with no technical paths in effects.
    logs=list({json.dumps(r,ensure_ascii=False,sort_keys=True):r for r in logs}.values())
    return logs,equipment

def saved_history(root):
    result=[]
    for path in sorted((Path(root)/'装备编辑器备份').glob('*/manifest.json')):
        value=json.loads(path.read_text(encoding='utf-8'))
        if value.get('complete') is True and value.get('change_log'):
            result.append({'time':value.get('time',path.parent.name),'purpose':value.get('purpose','修改'),
                           'entries':value['change_log'],'packet':path.parent/'改动效果.mjhchanges'})
    return result
