"""Expand the native mask UI; keep native per-run timers, consumption and save model IDs."""
import copy,hashlib,io,json,re,os
from pathlib import Path
from client_config import Assets,lua_rows
from codec import decode
from engine import DATA_ROOT,SCHEMAS,transaction
from martial_editor import indexed_rows,patch_table,patch_lua_rows
from edition import MOBILE_ENABLED
FIRST,LAST=24000,32767
DURATION=300000000
ROOT_CONFIG=Path('mod/editor_disguise')

def patch_runtime(data):
    from disguise_portraits import patch_loader
    from role_roll_portrait import patch_roll
    a=Assets(data);data=a.replace_script('ResourcesMgr.lua',patch_loader(a.script('ResourcesMgr.lua')))
    a=Assets(data);data=a.replace_script('RandomRollUI.lua',patch_roll(a.script('RandomRollUI.lua')))
    a=Assets(data);text=a.script('TableDataManager.lua')
    runtime=(DATA_ROOT/'ui_assets/disguise_runtime.lua').read_text(encoding='utf8').strip()
    marker='-- MJH_DISGUISE_RUNTIME_V223';end_marker='-- MJH_DISGUISE_RUNTIME_END'
    if marker in text:
        if text.count(marker)!=1:raise ValueError('易容组合读取补丁标记异常')
        start=text.index(marker)
        if end_marker in text:
            if text.count(end_marker)!=1:raise ValueError('易容组合读取补丁结束标记异常')
            end=text.index(end_marker,start)+len(end_marker)
        else:
            match=re.search(r'^TableDataManager\s*=',text[start:],re.M)
            if not match:raise ValueError('旧版易容组合读取补丁入口不兼容')
            end=start+match.start()
            legacy=text[start:end].replace('\r\n','\n').strip()
            if not legacy.endswith('    return id\nend'):raise ValueError('旧版易容组合读取补丁边界不兼容')
        suffix=text[end:]
        text=text[:start]+runtime+('' if suffix.startswith(('\n','\r')) else '\n')+suffix
        data=a.replace_script('TableDataManager.lua',text)
    else:
        anchor='    return self.tables[tbName]'
        if text.count(anchor)!=1:raise ValueError('易容外观读取入口不兼容')
        text=text.replace(anchor,'    MJHDisguisePopulate(tbName, self.tables[tbName])\n'+anchor,1)
        text=runtime+'\n'+text
        data=a.replace_script('TableDataManager.lua',text)
    a=Assets(data);text=a.script('DisguiseUI.lua');anchor='return DisguiseUI'
    block=(DATA_ROOT/'ui_assets/disguise_ui.lua').read_text(encoding='utf8').strip()
    if text.count(anchor)!=1:raise ValueError('易容面具界面入口不兼容')
    markers=[text.index(m) for m in ('-- MJH_DISGUISE_UI_V223','-- MJH_DISGUISE_UI_V224','-- MJH_DISGUISE_UI_V2212') if m in text]
    if markers:
        if len(markers)!=1:raise ValueError('易容面具界面补丁标记异常')
        start=markers[0];end_marker='-- MJH_DISGUISE_UI_END'
        if end_marker in text:
            if text.count(end_marker)!=1:raise ValueError('易容面具界面补丁结束标记异常')
            end=text.index(end_marker,start)+len(end_marker)
        else:
            match=re.search(r'^[ \t]*return _mjh_send\(roleID,id,use\)\r?\nend',text[start:],re.M)
            if not match:raise ValueError('旧版易容面具界面补丁边界不兼容')
            end=start+match.end()
        suffix=text[end:]
        text=text[:start]+block+('' if suffix.startswith(('\n','\r')) else '\n')+suffix
    else:text=text.replace(anchor,block+'\n'+anchor,1)
    data=a.replace_script('DisguiseUI.lua',text)
    from role_model_ids import repair
    from role_battle_model import repair as repair_battle
    from team_head_runtime import repair as repair_heads
    return repair_heads(repair_battle(repair(data)))

def patch_tables(root,data,updates,payloads,originals):
    for name,rows in updates.items():
        for folder in ('TableData','DreamRivakes_Data/StreamingAssets'):
            path=root/folder/(name+'.bytes')
            if not path.exists():continue
            before=path.read_bytes();originals[path]=before;payloads[path]=patch_table(before,name,rows)
        a=Assets(data)
        if name in a.scripts:
            _,q,n=a.scripts[name];data=a.replace_blob(name,patch_table(a.data[q+4:q+4+n],name,rows))
        a=Assets(data);script=name+'.lua'
        old=a.script(script);text=patch_lua_rows(old,rows)
        data=a.replace_script(script,text)
        path=root/'ModProject/GameProject/Mod_MJH/Json'/(name+'_disguise_editor.json')
        before=path.read_bytes() if path.exists() else None;originals[path]=before
        prior={int(r['BaseID']):r for r in json.loads(before.decode('utf8')).get('Items',[])} if before else {}
        prior.update(rows)
        payloads[path]=json.dumps({'Items':list(prior.values())},ensure_ascii=False,indent=2).encode()
    return data

def plan(root):
    from disguise_assets import NativeImages
    with NativeImages(root) as images:return _plan(root,images)

def _plan(root,images):
    from role_editor import RoleLibrary
    from disguise_assets import icon_bytes
    root=Path(root).resolve();lib=RoleLibrary(root)
    data=lib.assets.data;originals=dict(lib.originals);payloads={};options=[];notes=[]
    assets_path=lib.assets_path
    prior_path=root/ROOT_CONFIG/'catalog.json';prior=json.loads(prior_path.read_text(encoding='utf8')) if prior_path.exists() else None
    if prior and (prior.get('first'),prior.get('last'))!=(FIRST,LAST):raise ValueError('易容保留编号与当前版本不一致')
    reserved=set(range(FIRST,LAST+1))
    if not prior and reserved.intersection(lib.tables['RoleModel']):raise ValueError('易容外观保留编号被其他 MOD 使用，未覆盖')
    for name in ('DisguiseItem','DisguiseConfig'):
        if name not in SCHEMAS:raise ValueError('缺少易容表结构：'+name)
    existing_masks=lua_rows(lib.assets.script('DisguiseItem.lua'),'DisguiseItem',lib.enums)
    if not prior and reserved.intersection(existing_masks):raise ValueError('易容面具编号已被其他 MOD 使用')
    # Native/mod table overrides are preserved; refuse a conflicting override rather than silently losing it.
    directory=root/'ModProject/GameProject/Mod_MJH/Json'
    from mod_rows import table_name,read_rows
    for path in sorted(directory.glob('*.json')):
        name=table_name(path)
        if path.name.endswith('_disguise_editor.json'):continue
        if name not in ('Item','DisguiseConfig','DisguiseItem','RoleModel'):continue
        before=path.read_bytes();originals[path]=before
        rows=read_rows(before,name,SCHEMAS,[],path.name)
        for row in rows:
            ident=int(row['BaseID'])
            if (name=='Item' and ident==9628) or name=='DisguiseConfig' or (name in ('DisguiseItem','RoleModel') and ident in reserved):
                raise ValueError('易容相关配置被其他 MOD 覆盖，请先处理：'+path.name)
    owners={};role_ids={}
    for rid in lib.roles:
        art=lib.row(rid).get('ArtID')
        owners.setdefault(art,set()).add(lib.name(rid));role_ids.setdefault(art,set()).add(rid)
    native_models=images.models();seen=set();drawings=set(images.portraits())
    animation=lib.assets.script('SpineAnimaitionTime.lua')
    from role_animation import animation_rows,resolved_timings,skeleton_body
    known=animation_rows(animation)
    thumbnail_cache={}
    cache=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'MengJiangHuEquipEditor/disguise_previews'
    cache.mkdir(parents=True,exist_ok=True)
    def put_icon(image):
        raw=icon_bytes(image);filename='disguise_'+hashlib.sha256(raw).hexdigest()[:24]+'.png'
        path=root/'ModProject/GameProject/Mod_MJH/Source/Other/role_editor'/filename
        originals[path]=path.read_bytes() if path.exists() else None;payloads[path]=raw
        return '#role_editor/'+filename
    native_count=0;groups={};drawing_names={};drawing_models={};drawing_heads={}
    for ident,row in sorted(lib.tables['RoleModel'].items()):
        if ident in reserved:continue
        model=row.get('Model','');drawing=row.get('Drawing','')
        if drawing:
            if drawing.startswith('#'):
                try:images.image(drawing)
                except (OSError,ValueError):drawing=''
            elif not images.has_sprite(drawing):drawing=''
        if drawing and not drawing.startswith('#'):drawings.add(drawing)
        if drawing:
            drawing_names.setdefault(drawing.lower(),set()).update(owners.get(ident,()))
            drawing_models.setdefault(drawing.lower(),[]).append(ident)
            head=row.get('Head','')
            if head and images.has_sprite(head):drawing_heads.setdefault(drawing.lower(),set()).add(head)
        if model.lower() not in native_models:continue
        signature=json.dumps({k:row.get(k) for k in ('Model','Texture','Hue','ModelScale','WeaponPos','WeaponScale','InitWeapom','ModelID')},sort_keys=True)
        if signature in groups:
            option=groups[signature];option['aliases'].append(ident)
            option['names']=sorted(set(option['names'])|owners.get(ident,set()))
            option['role_ids']=sorted(set(option['role_ids'])|role_ids.get(ident,set()))
            continue
        if ident not in known:
            try:animation=resolved_timings(lib,animation,{ident:ident});known=animation_rows(animation)
            except ValueError as error:notes.append(f'动作资源不完整，跳过 {model} / {ident}：{error}');continue
        try:
            from model_texture import template_info
            from model_texture_preview import runtime_data,render
            info=template_info(lib,ident);texture=row.get('Texture') or 'Actor/'+model+'/'+model
            preview_key=(model,texture)
            if preview_key not in thumbnail_cache:
                texture_image=images.image(texture)
                preview=cache/(hashlib.sha256(info['skel']+info['atlas']+texture.encode()+texture_image.tobytes()).hexdigest()+'.png')
                if not preview.exists():preview.write_bytes(icon_bytes(render(runtime_data(root,info),texture_image)))
                with Image.open(preview) as im:thumbnail_cache[preview_key]=put_icon(im)
            icon=thumbnail_cache[preview_key]
        except Exception as error:notes.append(f'无法生成模型默认预览，跳过 {model} / {ident}：{error}');continue
        option=dict(kind='model',source='native',query_id=f'M{ident:05d}',model=ident,icon=icon,
                    resource=model,texture=row.get('Texture',''),aliases=[ident],names=sorted(owners.get(ident,())),role_ids=sorted(role_ids.get(ident,())))
        groups[signature]=option;options.append(option);native_count+=1
        if native_count%50==0:print(f'原版模型默认预览：{native_count}',flush=True)
    print(f'原版模型选项已读取：{native_count}',flush=True)
    for index,drawing in enumerate(sorted({p.lower() for p in drawings}),1):
        if not images.has_sprite(drawing):continue
        options.append(dict(kind='portrait',source='native',query_id=f'P{100000+index}',drawing=drawing,icon=drawing,
                            resource=drawing,aliases=drawing_models.get(drawing,[]),names=sorted(drawing_names.get(drawing,())),role_ids=[]))
        heads=drawing_heads.get(drawing,set())
        if len(heads)==1:options[-1]['head']=next(iter(heads))
    native_portraits=len(options)-native_count
    print(f'原版立绘已读取：{native_portraits}',flush=True)
    updates={};mobile_count=mobile_portraits=0
    if MOBILE_ENABLED:
        from mobile_models import catalog,binding,stage,read,runtime,missing_actions,AUXILIARY_TEXTURES,PREFIX
        from model_texture_preview import render
        mobile_rows={};prior_mobile={r.get('Model'):i for i,r in lib.tables['RoleModel'].items() if r.get('Model','').startswith(PREFIX)}
        timed_ids=set(animation_rows(animation));bodies=[]
        used=set(lib.tables['RoleModel'])|timed_ids|reserved
        free=iter(i for i in range(16000,32768) if i not in used)
        for model in sorted(catalog()['models'],key=lambda m:m['id']):
            if not model['id'].startswith('role_') or missing_actions(model):continue
            for texture in sorted(model['textures'],key=lambda t:t['name']):
                if texture['name'] in AUXILIARY_TEXTURES:continue
                spec=binding(lib,model,texture);stage(lib,spec)
                name=PREFIX+spec['key'];ident=prior_mobile.get(name)
                if ident is None:
                    ident=next(free);lib.tables['RoleModel'][ident]=dict(lib.tables['RoleModel'][spec['source']],BaseID=ident,Model=name,Texture=name+'_texture',Hue='',Drawing='',PictureID=0)
                    mobile_rows[ident]={k:v for k,v in lib.tables['RoleModel'][ident].items() if v!={}}
                if ident not in timed_ids:
                    bodies.append(f'[{ident}] = {skeleton_body(runtime(spec))},\n');timed_ids.add(ident)
                key=hashlib.sha256((model['skel']['sha256']+texture['sha256']).encode()).hexdigest()
                preview=cache/(key+'.png')
                if not preview.exists():
                    with Image.open(io.BytesIO(read(texture))) as im:image=render(runtime(spec),im)
                    preview.write_bytes(icon_bytes(image))
                with Image.open(preview) as im:icon=put_icon(im)
                mobile_count+=1
                options.append(dict(kind='model',source='mobile',query_id=f'M{200000+mobile_count}',model=ident,icon=icon,
                                    resource=model['id'],texture=texture['name'],aliases=[ident],names=[],role_ids=[]))
                if mobile_count%50==0:print(f'手游模型默认预览：{mobile_count} / 420',flush=True)
        if bodies:
            match=re.search(r'\}\s*return\s+spineAnimaition\b',animation)
            animation=animation[:match.start()]+''.join(bodies)+animation[match.start():]
        for entry in sorted(catalog()['portraits'],key=lambda p:p['id']):
            from disguise_portraits import stage as stage_portrait
            filename,raw=stage_portrait(entry,read(entry))
            path=root/'ModProject/GameProject/Mod_MJH/Source/Other/role_editor'/filename
            originals[path]=path.read_bytes() if path.exists() else None;payloads[path]=raw
            drawing='#role_editor/'+filename
            with Image.open(io.BytesIO(raw)) as image:icon=put_icon(image)
            mobile_portraits+=1
            options.append(dict(kind='portrait',source='mobile',query_id=f'P{200000+mobile_portraits}',drawing=drawing,icon=icon,
                                resource=entry['id'],aliases=[],names=[],role_ids=[]))
            from disguise_portraits import head_resource
            head=head_resource(entry)
            if head:
                filename,raw=head
                path=root/'ModProject/GameProject/Mod_MJH/Source/Other/role_editor'/filename
                originals[path]=path.read_bytes() if path.exists() else None;payloads[path]=raw
                options[-1]['head']='#role_editor/'+filename
        payloads.update(lib.files);originals.update(lib.originals);updates['RoleModel']=mobile_rows
        from mobile_models import plan_loader
        data=plan_loader(lib,data)
    # The native mask command uses these hidden slots; UI choices remain separate from the transport IDs.
    updates.setdefault('RoleModel',{})
    for ident in reserved:
        slot=dict(lib.tables['RoleModel'][6],BaseID=ident,Model='',Drawing='',Head='',Texture='',ModelID=0,PictureID=0)
        updates['RoleModel'][ident]={k:v for k,v in slot.items() if v!={}}
    updates['DisguiseItem']={i:dict(BaseID=i,Model=i,DisguiseTypeList=[],Lock=0) for i in reserved}
    updates['DisguiseConfig']={1:dict(BaseID=1,Task=3632,Duration=DURATION)}
    item=dict(lib.tables['Item'][9628]);item['BuyPrice']=1;updates['Item']={9628:item}
    data=patch_tables(root,data,updates,payloads,originals)
    data=Assets(data).replace_script('SpineAnimaitionTime.lua',animation)
    data=patch_runtime(data)
    payloads[assets_path]=data
    for option in options:
        title='、'.join(option['names'][:3]) or option.get('texture') or option['resource'].rsplit('/',1)[-1]
        option['label']=title
        option['search']=' '.join([option['query_id'],option['resource'],option.get('texture',''),*option['names'],*[str(x) for x in option['aliases']+option['role_ids']]])
    config=dict(version=2,first=FIRST,last=LAST,mobile=MOBILE_ENABLED,options=options)
    originals[prior_path]=prior_path.read_bytes() if prior_path.exists() else None
    payloads[prior_path]=json.dumps(config,ensure_ascii=False,indent=2).encode()
    registry=root/ROOT_CONFIG/'registry.json';originals[registry]=registry.read_bytes() if registry.exists() else None
    if originals[registry] is None:payloads[registry]=b'{"version":1,"entries":{}}'
    results=[f'原版：{native_count} 个模型/外观选项（合并相同模型，保留全部关联编号），{native_portraits} 个立绘选项。',f'手游：{mobile_count} 个模型/皮肤选项，{mobile_portraits} 个立绘选项。' if MOBILE_ENABLED else '标准版仅加入原版资源。','删除新增的“江湖人士”，分别放入“更改模型”和“更改立绘”；原有面具分类及剧情解锁保持原样。','支持查询编号、原模型编号、关联人物编号、名称及资源名。模型页仅改变模型；立绘页同步唯一对应的头像，无匹配时保留原头像。','可导出带预览图和相同查询编号的离线资源总表。',f'易容时长：3000 → {DURATION}（原来的 100000 倍，单局超长持续，沿用原生计时）。','已有易容计时不直接改写；重新使用面具后按新时长计时。','易容面具购买基础价格设为 1。','组合外观记录保存在 mod/editor_disguise/registry.json，旧存档引用的组合不覆盖。请随游戏目录保留此文件。','预览尚未写入游戏，应用时自动备份。']
    if MOBILE_ENABLED:results.insert(2,'手游立绘保留原始透明画布、像素及位置；不生成低清 Mip 层。已有易容组合继续使用原图片路径，重新应用并重启游戏即可更新。')
    results.insert(2,f'更改立绘时同步可靠对应的头像：{sum(o.get("kind")=="portrait" and bool(o.get("head")) for o in options)} 项。没有唯一对应头像时保留原头像；仅更改模型时不改变立绘和头像。')
    payloads={p:b for p,b in payloads.items() if b!=originals.get(p)}
    return payloads,originals,results,notes,{}

from PIL import Image
