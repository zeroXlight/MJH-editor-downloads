"""Portable editor metadata and PNGs; native resource paths stay game anchors."""
import copy,json,re
from pathlib import Path
from object_bundle import key,export_graph,sha,normalize_owned_roles

def json_read(store,name,default):
    raw=store.read(store.root/'装备编辑器配置'/name)
    return json.loads(raw.decode('utf8')) if raw else default

def collect(store,kind,ident):
    packet=export_graph(store,kind,ident);files={};images={}
    rolemeta=json_read(store,'人物编辑.json',{})
    if kind=='Role' and str(ident) not in rolemeta:
        from role_editor import RoleLibrary
        lib=RoleLibrary(store.root)
        rolemeta[str(ident)]={'settings':lib.options(ident),'template':None,'position_task':None}
    # Placement tasks are owned configuration, separate from per-save progress.
    if kind=='Role' and str(ident) in rolemeta:
        rec=copy.deepcopy(rolemeta[str(ident)]);rec.pop('save_restore_tasks',None)
        packet['extras']['role_metadata']={str(ident):rec}
        if rec.get('position_task'):
            extra=export_graph(store,'Task',rec['position_task']['Task'])
            for section in ('nodes','edges','anchors','role_groups'):packet[section].update(extra[section])
    normalize_owned_roles(packet)
    origins=json_read(store,'武学模板来源.json',{})
    packet['extras']['origins']={t:{i:v for i,v in origins.get(t,{}).items() if key(t,int(i)) in packet['nodes']} for t in ('Martial','Skill')}
    scopes=json_read(store,'新增作用范围.json',{})
    packet['extras']['scope_groups']={i:v for i,v in scopes.items() if key('MartialFilter',int(i)) in packet['nodes']}
    # Built-in icon strings refer to game resources. Uploaded files are portable.
    for token,node in packet['nodes'].items():
        for field in ('Drawing','Icon','Head','Texture'):
            value=node['row'].get(field,'')
            if field=='Texture' and isinstance(value,str) and value.startswith('#model_editor/'):
                from model_texture import TEXTURE_DIR,PREFIX
                filename=value[len(PREFIX):]
                if node['table']!='RoleModel' or not re.fullmatch(r'tex_[0-9a-f]{32}\.png',filename):raise ValueError('模型贴图路径无效')
                raw=store.read(store.root/TEXTURE_DIR/filename)
                if not raw:raise ValueError('缺少自定义模型贴图：'+value)
                from model_texture import template_info,png_bytes
                from types import SimpleNamespace
                info=template_info(SimpleNamespace(assets=store.assets,tables={'RoleModel':{1:node['row']}}),1)
                png_bytes(raw,info)
                name='images/'+sha(raw)+'.png';files[name]=raw;images[token+':'+field]={'member':name,'directory':'model_editor'}
                continue
            if field=='Texture':continue
            match=re.fullmatch(r'#(role_editor|martial_editor)/([^/\\]+\.png)',value) if isinstance(value,str) else None
            if not match:continue
            path=store.root/'ModProject/GameProject/Mod_MJH/Source/Other'/match[1]/match[2]
            raw=store.read(path)
            if not raw:raise ValueError('缺少上传图片：'+value)
            from PIL import Image
            import io
            with Image.open(io.BytesIO(raw)) as im:
                if im.format!='PNG' or im.width*im.height>20000000:raise ValueError('上传图片不是支持的 PNG')
                im.verify()
            name='images/'+sha(raw)+'.png';files[name]=raw
            images[token+':'+field]={'member':name,'directory':match[1]}
    from mobile_models import collect_object
    collect_object(store,packet,files)
    packet['extras']['images']=images
    # Materialize shared per-level formulas for just the exported clauses.
    # This carries source-side edits without modifying a target's shared table.
    from martial_growth import growth_lua
    from growth_runtime import custom_values,MARKER
    from fractions import Fraction
    from mod_compatibility import native_supported
    if not native_supported(store.root):
        packet['extras'].setdefault('compatibility_warnings',[]).append('目标为MOD运行库，已跳过原生成长转为独立数值；保留现有词条配置')
        packet['extras']['independent_growth']={}
        return packet,files
    growth=growth_lua(store.assets.script('KungfuBase.lua'),store.enums)
    factors=store.table('MatGrowUPAttrGrade')
    independent={};by_martial={}
    for node in list(packet['nodes'].values()):
        if node['table']!='Martial':continue
        m=node['row']
        for cid in m.get('GrowProIDs',[]):
            c=packet['nodes'][key('MartialItem',cid)]['row']
            for slot in (1,2):
                kind=c.get('EffectEnum'+str(slot));attr=c.get('AttrEnum'+str(slot),0)
                if kind not in (7,9) or custom_values(c,slot):continue
                options=[r for r in growth.values() if r['AttrType']==attr and r['IsRoleAttr']==int(kind==7) and r['IsGrowup']==1 and r['KfType'] in (0,m['DepartEnum'])]
                exact=[r for r in options if r['KfType']==m['DepartEnum']];options=exact or options
                if len(options)!=1:raise ValueError('每级成长来源不唯一，不能打包为独立配置')
                grade=c.get('Grade'+str(slot),0) or 2
                factor=next((r['GrowFactor'] for r in factors.values() if r['Grade']==grade),10000) if kind==9 else 10000
                value=Fraction(options[0]['RankDatas'][m['Rank']]*factor,10000)
                if value.denominator!=1:raise ValueError('每级成长无法无损转换为独立整数，请先在编辑器设置独立成长')
                independent[f'{cid}:{slot}']=[int(value),MARKER]
                by_martial.setdefault(str(m['BaseID']),{})[f'{cid}:{slot}']=[int(value),MARKER]
    packet['extras']['independent_growth']=independent
    packet['extras']['independent_growth_by_martial']=by_martial
    return packet,files

def import_extras(store,packet,mapping,rows,payloads,files):
    from object_bundle import sha
    from client_config import Assets
    extra=packet['extras']
    from mobile_models import import_object
    import_object(store,packet,rows,payloads,files)
    for tokenfield,entry in extra.get('images',{}).items():
        table,old,field=tokenfield.split(':');token=key(table,int(old));directory=entry['directory'];name=entry['member']
        if mapping[token] not in rows.get(table,{}):continue # Reused/pruned assets retain their target files.
        if directory=='model_editor':
            if table!='RoleModel' or field!='Texture' or name not in files:raise ValueError('模型贴图配置无效')
            from model_texture import TEXTURE_DIR,PREFIX,template_info,png_bytes
            from types import SimpleNamespace
            raw=files[name];row=rows[table][mapping[token]]
            info=template_info(SimpleNamespace(assets=store.assets,tables={'RoleModel':{1:row}}),1);raw=png_bytes(raw,info)
            filename='tex_'+sha(raw)[:32]+'.png';path=store.root/TEXTURE_DIR/filename;prior=store.read(path)
            if prior is not None and prior!=raw:raise ValueError('目标模型贴图名称冲突')
            payloads[path]=raw;row.update(Texture=PREFIX+filename,Hue='')
            from model_texture import plan_loader
            asset_path=store.root/'DreamRivakes_Data/resources.assets'
            payloads[asset_path]=plan_loader(payloads.get(asset_path,store.assets.data))
            continue
        if directory not in ('role_editor','martial_editor') or field not in ('Drawing','Icon','Head') or name not in files:raise ValueError('图片配置无效')
        raw=files[name];filename=sha(raw)+'.png';path=store.root/'ModProject/GameProject/Mod_MJH/Source/Other'/directory/filename
        prior=store.read(path)
        if prior is not None and prior!=raw:raise ValueError('目标图片名称冲突')
        payloads[path]=raw
        # Main writer reads these rows after image references are rewritten.
        rows[table][mapping[token]][field]='#'+directory+'/'+filename
    meta=json_read(store,'人物编辑.json',{})
    for old,rec in extra.get('role_metadata',{}).items():
        rid=mapping[key('@Role',int(old))];rec=copy.deepcopy(rec)
        first=rows['Role'][mapping[key('Role',packet['role_groups'][old][0])]]
        settings=rec['settings'];settings['model_source']=first['ArtID'];settings['portrait']=rows['RoleModel'][first['ArtID']].get('Drawing','');settings['head']=rows['RoleModel'][first['ArtID']].get('Head','')
        if settings.get('mobile_binding'):
            from mobile_models import carrier,selected
            from types import SimpleNamespace
            spec=settings['mobile_binding'];model,_=selected(spec)
            source=carrier(SimpleNamespace(tables={'RoleModel':store.table('RoleModel')}),model)
            spec['source']=source;settings['model_source']=source
        if settings.get('texture_binding'):
            from model_texture import PREFIX
            spec=settings['texture_binding'];spec['source_id']=first['ArtID']
            spec['filename']=rows['RoleModel'][first['ArtID']]['Texture'].removeprefix(PREFIX)
        settings['kungfu']=[(mapping.get(key('Martial',int(i)),int(i)),lv) for i,lv in settings['kungfu']]
        settings['battle_gifts']=[mapping.get(key('Gift',int(i)),int(i)) for i in settings.get('battle_gifts',[])]
        for spec in settings['equipment'].values():
            if spec.get('id'):spec['id']=mapping.get(key('Item',spec['id']),spec['id'])
        rec['art_id']=first['ArtID'];rec['base_art']=first['ArtID'];rec['animation_source']=first['ArtID'];rec['owned_art']=False;rec['owned_attr']=False
        rec['template']=None;rec.pop('before',None);rec.pop('snapshot',None)
        rec.pop('wish_restore_task',None);rec.pop('wish_restore_needed',None)
        rec.pop('wish_friend_restore_task',None);rec.pop('wish_treasure_restore_task',None)
        if rec.get('position_task'):
            rec['position_task']={k:mapping[key('Behavior' if k in ('move','unique') else k,v)] for k,v in rec['position_task'].items()}
        meta[str(rid)]=rec
    if extra.get('role_metadata'):
        path=store.root/'装备编辑器配置/人物编辑.json';payloads[path]=json.dumps(meta,ensure_ascii=False,indent=2).encode()
    for filename,name,table in [('武学模板来源.json','origins',None),('新增作用范围.json','scope_groups','MartialFilter')]:
        source=extra.get(name,{})
        if not source or not any(source.values()):continue
        target=json_read(store,filename,{})
        before_target=copy.deepcopy(target)
        if name=='origins':
            for t,values in source.items():
                for old,origin in values.items():
                    ident=mapping[key(t,int(old))]
                    if ident in rows.get(t,{}):target.setdefault(t,{})[str(ident)]=origin
        else:
            for old,value in source.items():
                if key(table,int(old)) in extra.get('import_reused',{}):continue
                ident=mapping[key(table,int(old))]
                if ident in rows.get(table,{}):target[str(ident)]=value
        if target!=before_target:payloads[store.root/'装备编辑器配置'/filename]=json.dumps(target,ensure_ascii=False,indent=2).encode()
