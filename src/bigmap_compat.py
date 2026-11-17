"""A previewable, save-free migration for the certified big-map build."""
from pathlib import Path
import json,shutil,gc
STATE='装备编辑器配置/大地图兼容.json'
LABELS={'caps':'武学上限30','interactions':'交互永久解锁','chest':'宝箱物品自动入库','six':'六属性、八系攻击及附加成长/锻造','mastery':'武学精通','breakthrough':'角色突破','pets':'宠物培养与助战','mobile':'手游专属武学及特效','limit':'全武学上限强化','uncap':'属性及伤害上限','disguise':'易容面具、模型及立绘'}
def read(root,name):
    p=Path(root)/name
    return json.loads(p.read_text('utf8')) if p.is_file() else {}
def preferences(root):
    from client_config import Assets
    a=Assets((Path(root)/'DreamRivakes_Data/resources.assets').read_bytes())
    return dict(caps=bool(read(root,'装备编辑器配置/武学上限原值.json')),
        interactions='-- MJH_INTERACTION_UNLOCK_V257' in a.script('RoleDataManager.lua'),
        chest=bool(read(root,'装备编辑器配置/宝箱自动入库.json').get('enabled')),
        six=bool(read(root,'装备编辑器配置/六项属性恢复状态.json').get('enabled')),
        mastery=bool(read(root,'装备编辑器配置/武学精通恢复记录.json').get('entries')),
        breakthrough=bool(read(root,'装备编辑器配置/角色突破恢复.json').get('enabled')),
        pets=bool(read(root,'装备编辑器配置/宠物恢复状态.json').get('enabled')),
        mobile=bool(read(root,'装备编辑器配置/手游专属武学恢复.json').get('installed')),
        limit=bool(read(root,'装备编辑器配置/全武学等级上限强化.json').get('enabled')),
        uncap=bool(read(root,STATE).get('options',{}).get('uncap')),
        disguise=bool(read(root,'mod/editor_disguise/registry.json')))
def plan(root,keys=()):
    from bigmap_profile import race_image,client_image,RACE_SHA,CLIENT_SHA
    from editor_temp import workspace_temp
    from client_config import Assets
    from growth_runtime import patch_runtime
    root=Path(root).resolve();keys=list(dict.fromkeys(keys))
    if any(k not in LABELS for k in keys):raise ValueError('大地图兼容功能选择无效')
    race=root/'DreamRivakes_Data/Plugins/RaceLogic_Release_x64.dll';client=root/'DreamRivakes_Data/Plugins/ClientDll.dll'
    if not race_image(race.read_bytes()) or not client_image(client.read_bytes()):raise ValueError('当前运行库不是本版已核对的大地图版本，保留原文件；请提供新的运行库供适配。')
    originals={};selected={};results=['大地图运行库版本匹配。基础成长支持将按大地图入口安装。'];notes=[];statuses={};reads={}
    protected={p:p.read_bytes() for p in (root/'TableData').glob('*.bytes') if p.stem in ('Map','City','Scene','Maze','Plot') or p.stem.startswith(('Maze','Map','City','Plot'))}
    initial_assets=Assets((root/'DreamRivakes_Data/resources.assets').read_bytes())
    protected_scripts={n:initial_assets.data[q+4:q+4+size] for n,(_,q,size) in initial_assets.scripts.items() if n.startswith(('Map','City','Maze','Plot'))}
    with workspace_temp(root,'mjh_bigmap_') as folder:
        virtual=Path(folder).resolve();files=set((root/'TableData').glob('*.bytes'))|set((root/'DreamRivakes_Data/Plugins').glob('*.dll'))
        files|={root/'DreamRivakes.exe',root/'DreamRivakes_Data/resources.assets',root/'DreamRivakes_Data/globalgamemanagers'}
        for directory in ('装备编辑器配置','ModProject','mod','DreamRivakes_Data/StreamingAssets','DreamRivakes_Data/Managed'):
            files.update(p for p in (root/directory).rglob('*') if p.is_file() and p.suffix.lower() not in ('.sav','.check','.checksave'))
        files.update((root/'DreamRivakes_Data').glob('mjh_tianji_*.assets'))
        files.update((root/'DreamRivakes_Data').glob('mjh_wuxiang_*.assets'))
        for name in ('BepInEx/core/0Harmony.dll','BepInEx/core/MonoMod.RuntimeDetour.dll','BepInEx/core/MonoMod.Utils.dll','BepInEx/plugins/XiakeConsultFix.dll','BepInEx/plugins/XiakeConsultFix/consult_hook.lua','BepInEx/plugins/XiakeConsultFix/features.txt'):
            if (root/name).is_file():files.add(root/name)
        # Unity image readers may need external resource streams for disguise.
        if 'disguise' in keys:files.update(p for p in (root/'DreamRivakes_Data').glob('*') if p.is_file() and p.suffix in ('.resS','.resource'))
        for p in files:
            if not p.is_file():continue
            q=virtual/p.relative_to(root);q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q)
        def stage(value):
            if hasattr(value,'prepared'):value=value.prepared() if callable(value.prepared) else value.prepared
            payloads,previous,report,warnings,*more=value
            for path,data in payloads.items():
                relative=path.relative_to(virtual)
                if path.suffix.lower() in ('.sav','.check','.checksave') or 'SaveFile' in relative.parts:raise ValueError('大地图兼容禁止写入存档')
                real=root/relative;originals.setdefault(real,real.read_bytes() if real.is_file() else None);selected[real]=data
                if data is None:path.unlink(missing_ok=True)
                else:path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
            if more and isinstance(more[0],dict):
                for p,b in more[0].items():
                    if not isinstance(p,Path) or not p.is_relative_to(virtual):continue
                    r=root/p.relative_to(virtual)
                    if r not in reads:reads[r]=originals.get(r,r.read_bytes() if r.is_file() else None)
            return report,warnings
        from feature_fields import state as field_state,switch,mastery_entries,rebase_mastery
        from shadow_loader_repair import plan as loader_plan
        report,warnings=stage(loader_plan(virtual,True));results+=report;notes+=warnings
        from shadow_bigmap import repair_legacy_client
        cp=virtual/client.relative_to(root);cb=cp.read_bytes();cf=repair_legacy_client(cb)
        if cf!=cb:stage(({cp:cf},{cp:cb},[],[],{}));results.append('核对并重建暗影安装后保留的宠物支持父文件记录；保留暗影客户端修复及强化选项。')
        mastery_active=bool(read(virtual,'装备编辑器配置/武学精通恢复记录.json').get('entries')) and not field_state(virtual)['features'].get('mastery',{}).get('suspended')
        if mastery_active:stage(switch(virtual,'mastery',False,mastery_entries))
        from bigmap_data_repair import stage as repair
        report,warnings=stage(repair(virtual));results+=report;notes+=warnings
        p=virtual/race.relative_to(root);before=p.read_bytes();stage(({p:patch_runtime(before)},{p:before},[],[],{}))
        # Restore runtime registrations from existing configuration; never invent
        # missing characters, positions or skill IDs.
        from martial_editor import MartialLibrary
        lib=MartialLibrary(virtual);old=dict(lib.originals);payloads={}
        from martial_ranges import plan as range_plan
        path=virtual/'DreamRivakes_Data/resources.assets'
        payloads[path]=range_plan(lib,lib.assets.data,payloads,old)
        stage((payloads,old,[],[],old))
        # Old martial overlays also survive Steam verification. Synchronize
        # their complete dependency graph before reconnecting recruitment.
        del lib;gc.collect()
        lib=MartialLibrary(virtual)
        martial_payloads,martial_originals=lib.plan()
        stage((martial_payloads,martial_originals,[],[],martial_originals))
        notes+=lib.mod_warnings
        del lib;gc.collect()
        # Reapply surviving character JSON to both native and client tables.
        # RoleLibrary also reconnects legacy recruitment scopes semantically.
        from role_editor import RoleLibrary
        roles=RoleLibrary(virtual)
        role_payloads,role_originals=roles.plan()
        count=sum(len(rows) for rows in roles.changes.values())
        stage((role_payloads,role_originals,[],[],role_originals))
        if count:results.append(f'重新对应并同步 {count} 条已有的人物编辑配置。')
        notes+=roles.mod_warnings
        del roles;gc.collect()
        # Restored martial graphs must exist before caps and growth overlays
        # are applied. Installing mobile last otherwise undoes their first pass.
        for key in ['mobile',*(k for k in LABELS if k!='mobile')]:
            if key not in keys:continue
            if __import__('os').environ.get('MJH_BIGMAP_TEST'):print('CHECKING',key,flush=True)
            try:
                if key=='six':
                    from six_attrs import plan as action
                    pref=read(virtual,'装备编辑器配置/六项属性恢复状态.json');value=action(virtual,True,pref.get('restore_forge',False),pref.get('restore_martial',False))
                elif key=='mastery':
                    from martial_mastery import plan as action
                    # Reconnect missing clauses without changing the user's growth.
                    value=action(virtual)
                elif key=='pets':
                    from pet_restore import plan as action
                    value=action(virtual,True)
                elif key=='mobile':
                    from mobile_martial_restore import plan as action
                    value=action(virtual,False)
                elif key=='disguise':
                    from edition import MOBILE_ENABLED
                    catalog=read(virtual,'mod/editor_disguise/catalog.json')
                    if read(virtual,STATE).get('options',{}).get('disguise') and catalog.get('mobile')==MOBILE_ENABLED:
                        from disguise_editor import patch_runtime
                        p=virtual/'DreamRivakes_Data/resources.assets';b=p.read_bytes();updated=patch_runtime(b)
                        value={p:updated} if updated!=b else {},{p:b},[],[],{}
                    else:
                        from disguise_editor import plan as action
                        value=action(virtual)
                elif key=='caps':
                    from caps import plan_caps
                    more=[];p,o=plan_caps(virtual,True,more);value=p,o,[],more,{}
                elif key=='uncap':
                    from attribute_uncap import plan as action
                    value=action(virtual,True,True)
                else:
                    from feature_manager import _step
                    value=_step(virtual,key,True)
                report,warnings=stage(value);statuses[key]='已通过';results.append(LABELS[key]+'：兼容恢复通过。');notes+=warnings
                del value;gc.collect()
            except (ValueError,KeyError,FileNotFoundError) as error:
                if __import__('os').environ.get('MJH_BIGMAP_TEST'):
                    __import__('traceback').print_exc()
                statuses[key]='跳过：'+str(error);notes.append(LABELS[key]+' 已跳过：'+str(error))
        if mastery_active and field_state(virtual)['features'].get('mastery',{}).get('suspended'):
            rebase_mastery(virtual);stage(switch(virtual,'mastery',True,mastery_entries))
        # Initialize newly enabled mastery bookkeeping now, rather than on the
        # next preview's suspend/reapply pass.
        doc=field_state(virtual);entries=read(virtual,'装备编辑器配置/武学精通恢复记录.json').get('entries',[])
        if entries and not doc['features'].get('mastery'):
            import copy
            entries=copy.deepcopy(entries)
            for e in entries:
                if e['field']=='GrowProIDs':
                    e['intent_add']=[v for v in e['on'] if v not in e['off']]
                    e['intent_remove']=[v for v in e['off'] if v not in e['on']]
            doc['features']['mastery']=dict(suspended=False,entries=entries,scripts=[])
            from feature_fields import STATE as FIELD_STATE
            p=virtual/FIELD_STATE;old=p.read_bytes() if p.exists() else None
            stage(({p:json.dumps(doc,ensure_ascii=False,indent=2).encode('utf8')},{p:old},[],[],{}))
        # Features can supply dependencies absent at the initial read. Resolve
        # the final graph and refresh the current warning file in the same plan.
        lib=MartialLibrary(virtual);p,o=lib.plan();stage((p,o,[],[],o))
        from mod_compatibility import stage as warning_plan
        p,o=warning_plan(lib,{},{});stage((p,o,[],[],o))
        del lib;gc.collect()
        path=root/STATE;originals[path]=path.read_bytes() if path.exists() else None
        prior=read(virtual,STATE);options=dict(prior.get('options',{}));recorded=dict(prior.get('results',{}))
        for key in keys:options[key]=statuses.get(key)=='已通过'
        recorded.update(statuses)
        import hashlib
        from growth_runtime import _original
        actual_race_sha=hashlib.sha256(_original(race.read_bytes())).hexdigest()
        selected[path]=json.dumps(dict(version=1,race_sha256=actual_race_sha,client_sha256=CLIENT_SHA,options=options,results=recorded),ensure_ascii=False,indent=2).encode('utf8')
    for p,raw in protected.items():
        if selected.get(p,raw)!=raw:raise ValueError('兼容方案试图修改大地图配置，已停止：'+p.name)
    a=Assets(selected.get(root/'DreamRivakes_Data/resources.assets',initial_assets.data))
    for n,raw in protected_scripts.items():
        _,q,size=a.scripts[n]
        if a.data[q+4:q+4+size]!=raw:raise ValueError('兼容方案改变大地图脚本，已停止：'+n)
    # A composed pause/reapply can alter only trailing Lua whitespace. Avoid
    # backing up and rewriting the large asset for this cosmetic difference.
    asset_path=root/'DreamRivakes_Data/resources.assets'
    if asset_path in selected and selected[asset_path]!=initial_assets.data:
        old_objects={o['id']:o for o in initial_assets.objects};same=len(old_objects)==len(a.objects)
        by_object={o['id']:name for name,(o,q,size) in a.scripts.items()}
        for obj in a.objects:
            old=old_objects.get(obj['id'])
            if old is None:same=False;break
            name=by_object.get(obj['id'])
            if name and name.endswith('.lua') and name in initial_assets.scripts:
                _,p,n=initial_assets.scripts[name];_,q,m=a.scripts[name]
                x=initial_assets.data[p+4:p+4+n].strip(b' \t\r\n');y=a.data[q+4:q+4+m].strip(b' \t\r\n')
                if x!=y:
                    from lua_whitespace import equivalent,equivalent_table
                    if equivalent(x,y):continue
                    from client_config import enum_values
                    enums=enum_values(initial_assets.script('common.lua'))|enum_values(initial_assets.script('Enum.lua'))
                    if equivalent_table(x,y,name,enums):continue
            else:
                x=initial_assets.data[initial_assets.start+old['off']:initial_assets.start+old['off']+old['length']]
                y=a.data[a.start+obj['off']:a.start+obj['off']+obj['length']]
            if x!=y:
                same=False
                if __import__('os').environ.get('MJH_BIGMAP_TEST'):print('ASSET CONTENT CHANGE',name or obj['id'],len(x),len(y),flush=True)
                break
        if same:selected[asset_path]=initial_assets.data
    payloads={p:b for p,b in selected.items() if b!=originals[p]}
    results+=['大地图城市、场景和剧情配置保持原样；不写入存档，不补发资源，不重复赠送经脉或测试秘籍。',f'计划修改 {len(payloads)} 个文件。应用前请退出游戏，应用后重启。']
    return payloads,originals,results,notes,reads
