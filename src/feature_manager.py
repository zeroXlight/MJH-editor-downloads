"""Compose selected feature toggles, never a whole-save rollback."""
from pathlib import Path
import json,shutil,copy
HISTORY='装备编辑器配置/功能开关管理.json'
LABELS={'caps':'武学上限30','interactions':'交互永久解锁','chest':'宝箱物品自动入库',
        'mastery':'恢复武学精通','six':'恢复六项属性及武学攻击（含锻造/武学附加选项）',
        'breakthrough':'恢复角色突破','pets':'恢复宠物','mobile':'恢复手游专属武学（保留学习及秘籍）',
        'limit':'全武学等级上限强化','uncap':'移除人物属性上限','damage':'移除单次伤害上限',
        'disguise':'易容面具扩展界面（保留物品与已有外观）'}

def _doc(root,name,default=None):
    p=Path(root)/name
    return json.loads(p.read_text('utf8')) if p.exists() else (default or {})

def scan(root):
    from client_config import Assets
    from feature_fields import state
    from interaction_unlock import LUA_MARKER
    from external_runtime import detach
    from caps import cap_summary
    from object_bundle import Store
    store=Store(root);root=store.root;assets=store.assets;history=_doc(root,HISTORY);fields=state(root)['features'];flags={};native_error=''
    from shadow_runtime import detected
    detected(root)
    raw=(root/'DreamRivakes_Data/Plugins/RaceLogic_Release_x64.dll').read_bytes()
    from growth_runtime import _original
    try:
        if _original(raw)!=raw:_,flags=detach(raw)
    except ValueError as e:native_error=str(e)
    _,caps=cap_summary(root)
    remembered=_doc(root,'装备编辑器配置/武学上限原值.json').get('files',{})
    if remembered:
        from caps import CAPS,proto_profile
        for table in CAPS:
            current=proto_profile((root/'TableData'/(table+'.bytes')).read_bytes(),table)
            old=remembered.get('TableData/'+table+'.bytes',{})
            caps |= any(value.get(field)==30 and before.get(field)!=30 for ident,before in old.items() for field in before for value in [current.get(ident,{})])
    mobile=bool(_doc(root,'装备编辑器配置/手游专属武学恢复.json').get('installed'))
    active={'caps':caps,'interactions':bool(flags.get('interactions') or LUA_MARKER in assets.script('RoleDataManager.lua')),
            'chest':bool(flags.get('chest_autoloot')),'six':bool(flags.get('six_attrs')),
            'pets':bool(_doc(root,'装备编辑器配置/宠物恢复状态.json').get('enabled')),
            'breakthrough':bool(_doc(root,'装备编辑器配置/角色突破恢复.json').get('enabled')),'mobile':mobile,'limit':bool(_doc(root,'装备编辑器配置/全武学等级上限强化.json').get('enabled')),
            'uncap':bool(flags.get('attribute_uncap')),'damage':bool(flags.get('damage_uncap')),
            'disguise':'-- MJH_DISGUISE_UI_END' in assets.script('DisguiseUI.lua')}
    receipt=_doc(root,'装备编辑器配置/武学精通恢复记录.json');active['mastery']=bool(receipt.get('entries'))
    legacy_mastery=False
    if not active['mastery'] and any((root/'装备编辑器备份').glob('*/manifest.json')):
        from feature_fields import mastery_entries
        legacy_mastery=bool(mastery_entries(store)[0]);active['mastery']=legacy_mastery
    rows=[]
    for key,label in LABELS.items():
        paused=fields.get(key,{}).get('suspended',False)
        enabled=active.get(key,False) and not paused
        seen=enabled or paused or key in history.get('features',{})
        if not seen:continue
        note=''
        if key=='mastery' and legacy_mastery:note='旧版记录：预览时从备份核实原值，无法核实的条目不回退。'
        if key=='mobile':note='停用新增武学的成长/招式/被动效果；保留编号、学习等级、秘籍和收藏。'
        if key=='disguise':note='关闭扩展界面，保留人物模型/立绘加载支持及已有物品编辑结果。'
        unavailable=native_error if key in ('interactions','chest','six','pets','uncap','damage') else ''
        rows.append(dict(key=key,label=label,enabled=enabled,note=note,available=not unavailable,error=unavailable))
    return rows

def _tuple(value):
    p=getattr(value,'prepared',None)
    return p() if callable(p) else p if p is not None else value

def _step(root,key,enabled):
    if key=='caps':
        from caps import plan_caps
        notes=[];p,o=plan_caps(root,enabled,notes);return p,o,['武学上限30：'+('启用' if enabled else '关闭')],notes,{}
    if key=='interactions':
        from interaction_unlock import plan
        return plan(root,enabled)
    if key=='chest':
        from chest_autoloot import plan
        return plan(root,enabled)
    if key=='six':
        from six_attrs import plan
        prefs=_doc(root,'装备编辑器配置/功能开关管理.json').get('features',{}).get('six',{})
        return _tuple(plan(root,enabled,prefs.get('restore_forge',False),prefs.get('restore_martial',False)))
    if key=='breakthrough':
        from role_breakthrough import plan
        return plan(root,enabled)
    if key=='pets':
        from pet_restore import plan
        return _tuple(plan(root,enabled))
    if key=='limit':
        from martial_limit_enhance import plan
        return plan(root,enabled)
    if key in ('uncap','damage'):
        from external_runtime import detach
        from attribute_uncap import plan
        _,flags=detach((Path(root)/'DreamRivakes_Data/Plugins/RaceLogic_Release_x64.dll').read_bytes())
        return plan(root,enabled if key=='uncap' else bool(flags.get('attribute_uncap')),
                    enabled if key=='damage' else bool(flags.get('damage_uncap')),independent_damage=True)
    from feature_fields import switch,mobile_entries,mastery_entries,disguise_entries
    return switch(root,key,enabled,{'mobile':mobile_entries,'mastery':mastery_entries,'disguise':disguise_entries}[key])

def plan(root,keys,enabled=False):
    from editor_temp import workspace_temp
    root=Path(root).resolve();keys=list(dict.fromkeys(keys))
    if not keys or any(k not in LABELS for k in keys):raise ValueError('请选择要处理的功能')
    keys=sorted(keys,key=list(LABELS).index,reverse=enabled)
    status={r['key']:r for r in scan(root)}
    for k in keys:
        if k not in status:raise ValueError('未检测到本功能的启用或关闭记录：'+LABELS[k])
        if not status[k]['available']:raise ValueError(status[k]['error'])
    originals={};results=[];notes=[];selected={};history=_doc(root,HISTORY,{'version':1,'features':{}})
    with workspace_temp(root,'mjh_feature_switch_') as folder:
        virtual=Path(folder).resolve()
        # Only configuration and owned state. Never copy or write any save.
        files=set((root/'TableData').glob('*.bytes'))|set((root/'DreamRivakes_Data/Plugins').glob('*.dll'))
        files|={root/'DreamRivakes_Data/resources.assets',root/'DreamRivakes_Data/globalgamemanagers',root/'DreamRivakes.exe'}
        for directory in ('装备编辑器配置','ModProject','mod','BepInEx'):
            files.update(p for p in (root/directory).rglob('*') if p.is_file() and p.suffix.lower() not in ('.sav','.check','.checksave'))
        # Verified backup preimages are needed only for older mastery restores.
        if 'mastery' in keys and not enabled:
            files.update(p for p in (root/'装备编辑器备份').rglob('*') if p.is_file() and p.name!='Save.sav')
        for p in files:
            if not p.is_file():continue
            q=virtual/p.relative_to(root);q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q)
        if 'mastery' in keys and not enabled:
            for p in (virtual/'装备编辑器备份').glob('*/manifest.json'):
                doc=json.loads(p.read_text('utf8'))
                if Path(doc.get('root','')).resolve()==root:doc['root']=str(virtual);p.write_text(json.dumps(doc,ensure_ascii=False),'utf8')
        def stage_step(result):
            payloads,previous,report,warnings,_=result
            for p,data in payloads.items():
                relative=p.relative_to(virtual)
                if p.suffix.lower()=='.sav' or 'SaveFile' in relative.parts:raise ValueError('功能开关不允许回写存档')
                real=root/relative;originals.setdefault(real,real.read_bytes() if real.exists() else None);selected[real]=data
                if data is None:
                    if p.exists():p.unlink()
                else:p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
            return report,warnings
        six_changed=False
        for key in keys:
            if status[key]['enabled']==enabled:results.append(LABELS[key]+'：已是目标状态。');continue
            entry=history['features'].setdefault(key,{})
            if key=='six' and not enabled:
                prefs=_doc(virtual,'装备编辑器配置/六项属性恢复状态.json');entry.update({k:prefs.get(k,False) for k in ('restore_forge','restore_martial')})
            hp=virtual/HISTORY;hp.parent.mkdir(exist_ok=True);hp.write_text(json.dumps(history,ensure_ascii=False),'utf8')
            from feature_fields import state as fields_state,rebase_mastery
            temporary_mastery=key=='six' and status.get('mastery',{}).get('enabled') and not fields_state(virtual)['features'].get('mastery',{}).get('suspended')
            if temporary_mastery:stage_step(_step(virtual,'mastery',False))
            if key=='mastery' and enabled and six_changed:rebase_mastery(virtual)
            report,warnings=stage_step(_step(virtual,key,enabled))
            if key=='six':six_changed=True
            if temporary_mastery:
                rebase_mastery(virtual);stage_step(_step(virtual,'mastery',True))
            entry['enabled']=enabled;results.append(LABELS[key]+'：'+('启用' if enabled else '关闭'));results.extend(report);notes.extend(warnings)
        p=root/HISTORY;originals[p]=p.read_bytes() if p.exists() else None;selected[p]=json.dumps(history,ensure_ascii=False,indent=2).encode('utf8')
    payloads={p:b for p,b in selected.items() if b!=originals[p]}
    # Independent safety invariant: this control never edits item definitions,
    # including their embedded client copies inside the shared assets file.
    from client_config import Assets
    import re
    for p,data in payloads.items():
        if p.name=='Item.bytes' or p.name.startswith('Item_') and p.suffix=='.json':raise ValueError('所选功能涉及物品定义，未应用')
        if p==root/'DreamRivakes_Data/resources.assets':
            a=Assets(originals[p]);b=Assets(data)
            for name in a.scripts:
                if name!='Item' and not re.fullmatch(r'Item\d*\.lua',name):continue
                _,x,n=a.scripts[name];_,y,m=b.scripts[name]
                if a.data[x+4:x+4+n]!=b.data[y+4:y+4+m]:raise ValueError('所选功能改变了物品配置，未应用')
    results+=['不回退存档，不回收已领取资源；装备、物品与人物编辑结果保留。']
    return payloads,originals,results,notes,{}
