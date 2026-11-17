"""Bundled mobile assets and per-character portable runtime bindings."""
import hashlib, io, json, re
from pathlib import Path
from edition import MOBILE_ASSETS,MOBILE_ENABLED,require_mobile

PREFIX='mjh_mobile_'
INSTALL=Path('mod/editor_mobile_models')
REQUIRED_ACTIONS={'idle','move','injured','spell','prepare','prepare_f','prepare_l','prepare_r','prepare_s'}|{'attack_'+d+'_'+n for d in 'flrs' for n in ('001','002','101')}
AUXILIARY_TEXTURES={'role_baiyimojun_kuang_mask','role_huangguniang_mohua_glow'}

def missing_actions(model):
    data=json.loads(read(model['runtime']).decode('utf-8-sig'))
    return sorted(REQUIRED_ACTIONS-{a['Name'] for a in data['animations']})

def assert_bindable(model):
    missing=missing_actions(model)
    if missing:raise ValueError('该手游模型缺少人物必需动作，不能用于人物替换：'+model['id']+'。缺少：'+', '.join(missing)+'。仍可在独立预览器查看。')

def asset_root():
    require_mobile()
    return MOBILE_ASSETS

def catalog():return json.loads((asset_root()/'catalog.json').read_text(encoding='utf8'))

def read(entry):
    root=asset_root().resolve();path=(root/entry['file']).resolve()
    if not path.is_relative_to(root):raise ValueError('手游资源路径无效')
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=entry['sha256']:raise ValueError('手游资源已损坏：'+entry['file'])
    return raw

def selected(spec):
    if not isinstance(spec,dict):raise ValueError('手游模型绑定无效')
    model=next((m for m in catalog()['models'] if m['id']==spec.get('id')),None)
    if not model:raise ValueError('手游模型不存在，请重新选择')
    texture=next((t for t in model['textures'] if t['name']==spec.get('texture')),None)
    if not texture:raise ValueError('手游模型贴图不存在，请重新选择')
    if not model.get('compatible'):raise ValueError('该手游骨骼尚未通过电脑版动作校验')
    return model,texture

def carrier(lib,model):
    candidates=[i for i,r in lib.tables['RoleModel'].items() if r.get('Model')==model['id'] and not r.get('Texture','').startswith('#')]
    if candidates:return min(candidates)
    candidates=[i for i,r in lib.tables['RoleModel'].items() if r.get('Model')=='role_zhouguniang' and not r.get('Texture','').startswith('#')]
    if not candidates:raise ValueError('游戏缺少手游骨骼加载所需的原版人物组件')
    return min(candidates)

def binding(lib,model,texture,custom=None):
    assert_bindable(model)
    if texture['name'] in AUXILIARY_TEXTURES:raise ValueError('该文件是遮罩或发光辅助贴图，不能作为人物皮肤绑定')
    source=carrier(lib,model);base=lib.tables['RoleModel'][source]['Model']
    if custom:
        required={'sha256','width','height','label'};resize_fields={'source_width','source_height','resize_filter'}
        if not required<=set(custom) or set(custom)-required not in (set(),resize_fields) or not isinstance(custom['sha256'],str) or not re.fullmatch('[0-9a-f]{64}',custom['sha256']):raise ValueError('自定义手游贴图记录无效')
        if type(custom['width']) is not int or type(custom['height']) is not int or (custom['width'],custom['height'])!=(texture['width'],texture['height']):raise ValueError('自定义手游贴图尺寸与模板不一致')
        if not isinstance(custom['label'],str) or not 1<=len(custom['label'])<=160:raise ValueError('自定义手游贴图名称无效')
        if 'resize_filter' in custom:
            w,h=custom['source_width'],custom['source_height']
            if type(w) is not int or type(h) is not int or w<=0 or h<=0 or w*h>16777216 or w*texture['height']!=h*texture['width'] or custom['resize_filter']!='LANCZOS':raise ValueError('手游贴图自动适配记录无效')
    key=resource_key(model,custom['sha256'] if custom else texture['sha256'],base)
    result=dict(id=model['id'],texture=texture['name'],key=key,source=source,base=base)
    if custom:result['custom_texture']=dict(custom)
    return result

def resource_key(model,texture_sha,base):
    return hashlib.sha256((model['skel']['sha256']+model['atlas']['sha256']+texture_sha+base+str(model.get('spine_scale',0.01))).encode()).hexdigest()[:32]

def check_png(raw,texture):
    from PIL import Image
    if not raw or len(raw)>32*1024*1024:raise ValueError('手游贴图不能超过 32 MB')
    try:
        with Image.open(io.BytesIO(raw)) as im:
            if im.format!='PNG':raise ValueError('手游贴图须为 PNG 图片')
            if getattr(im,'is_animated',False):raise ValueError('手游贴图需要单帧 PNG')
            if im.size!=(texture['width'],texture['height']):raise ValueError(f"贴图尺寸不匹配：模板需要 {texture['width']}×{texture['height']}，当前为 {im.width}×{im.height}。请使用此模型模板的贴图布局。")
            if im.width*im.height>16777216:raise ValueError('手游贴图不能超过 4096×4096 像素总量')
            im.verify()
        with Image.open(io.BytesIO(raw)) as im:im.load()
    except (OSError,SyntaxError) as error:raise ValueError('手游 PNG 贴图损坏或无法读取') from error

def custom_texture(lib,spec,source):
    """Keep uncommitted uploads in memory; only selected bindings become game files."""
    require_mobile();model,texture=selected(spec)
    source=Path(source)
    if source.stat().st_size>32*1024*1024:raise ValueError('手游贴图不能超过 32 MB')
    from model_texture import png_bytes
    normalization={}
    raw=png_bytes(source.read_bytes(),texture,allow_resize=True,normalization=normalization,max_bytes=32*1024*1024)
    check_png(raw,texture)
    custom=dict(sha256=hashlib.sha256(raw).hexdigest(),width=texture['width'],height=texture['height'],label=source.name[:160])
    if normalization['resized']:
        custom.update(source_width=normalization['source_width'],source_height=normalization['source_height'],resize_filter='LANCZOS')
    result=binding(lib,model,texture,custom)
    if not hasattr(lib,'_mobile_texture_uploads'):lib._mobile_texture_uploads={}
    lib._mobile_texture_uploads[custom['sha256']]=raw
    return result

def texture_bytes(lib,spec):
    _,texture=selected(spec);custom=spec.get('custom_texture')
    if not custom:return read(texture)
    path=lib.root/INSTALL/spec['key']/'texture.png'
    raw=getattr(lib,'_mobile_texture_uploads',{}).get(custom['sha256'])
    if raw is None:raw=lib.files.get(path)
    if raw is None and path.exists():raw=path.read_bytes()
    if raw is None:raise ValueError('自定义手游贴图缺失，请重新上传贴图或恢复模板贴图')
    check_custom(raw,texture,custom)
    return raw

def check_custom(raw,texture,custom):
    check_png(raw,texture)
    if hashlib.sha256(raw).hexdigest()!=custom['sha256']:raise ValueError('自定义手游贴图校验失败，文件可能已被修改')

def validate(lib,settings):
    spec=settings.get('mobile_binding')
    if not MOBILE_ENABLED and (spec or lib.tables['RoleModel'].get(settings.get('model_source'),{}).get('Model','').startswith(PREFIX)):
        require_mobile()
    if not spec:return
    require_mobile()
    model,texture=selected(spec);expected=binding(lib,model,texture,spec.get('custom_texture'))
    if spec!=expected or settings['model_source']!=spec['source']:raise ValueError('手游模型绑定与当前模板不一致，请重新选择手游模型')
    if settings.get('texture_binding'):raise ValueError('手游模型与原版自定义贴图不能同时绑定')
    if spec.get('custom_texture'):texture_bytes(lib,spec)

def runtime(spec):
    model,_=selected(spec)
    return json.loads(read(model['runtime']).decode('utf-8-sig'))

def stage(lib,spec):
    model,texture=selected(spec)
    files={'model.skel':read(model['skel']),'model.atlas':read(model['atlas']),'texture.png':texture_bytes(lib,spec)}
    # Generated from validated catalog names, never arbitrary Lua entered in UI.
    files['binding.lua']=('return {base='+json.dumps(spec['base'])+',page='+json.dumps(model['page'])+',scale='+str(model.get('spine_scale',0.01))+'}\n').encode()
    for name,raw in files.items():
        path=lib.root/INSTALL/spec['key']/name;before=path.read_bytes() if path.exists() else None
        if before is not None and before!=raw:raise ValueError('已安装的手游模型资源被修改：'+str(path))
        lib.originals.setdefault(path,before);lib.files[path]=raw

def animation_patch(lib,text):
    from role_animation import animation_rows,skeleton_body
    for rid,record in lib.meta.items():
        spec=record.get('settings',{}).get('mobile_binding')
        if not spec:continue
        target=lib.row(int(rid))['ArtID'];body=skeleton_body(runtime(spec));rows=animation_rows(text)
        if target in rows:
            start,end,_=rows[target];text=text[:start]+body+text[end:]
        else:
            match=re.search(r'\}\s*return\s+spineAnimaition\b',text)
            if not match:raise ValueError('模型动作表结构不兼容')
            text=text[:match.start()]+f'[{target}] = {body},\n'+text[match.start():]
    return text

def dependencies(root,payloads):
    keys=set()
    for raw in payloads.values():
        if raw:keys.update(v.decode() for v in re.findall(rb'mjh_mobile_([0-9a-f]{32})',raw))
    result={}
    if keys:require_mobile()
    for key in keys:
        for name in ('binding.lua','model.skel','model.atlas','texture.png'):
            path=Path(root)/INSTALL/key/name
            raw=payloads.get(path)
            if raw is None and path.exists():raw=path.read_bytes()
            if raw is None:raise ValueError('导出缺少手游模型资源：'+str(path))
            result[path]=raw
    return result

def patch_loader(text):
    if not MOBILE_ENABLED:return text
    marker='-- MJH_MOBILE_MODELS_V261'
    if marker in text:return patch_dynamic_texture(text)
    from engine import DATA_ROOT
    resource=DATA_ROOT/'ui_assets/mobile_models.lua'
    if not resource.is_file():
        raise ValueError('手游模型运行文件缺失，请完整解压本版手游资源版；不要混用旧版程序或资源文件。缺少：ui_assets/mobile_models.lua')
    loader=resource.read_text(encoding='utf8')
    if marker not in loader:raise ValueError('手游模型运行文件版本不匹配，请重新完整解压本版手游资源版')
    entry='function LoadPrefab(sPath,iType, mod)'
    if text.count(entry)!=1:raise ValueError('手游模型加载入口不兼容')
    if '-- MJH_MOBILE_MODELS_V260' in text:
        start=text.index('-- MJH_MOBILE_MODELS_V260');end=text.index(entry,start)
        text=text[:start]+loader+'\n'+text[end:]
        return patch_dynamic_texture(text)
    text=text.replace(entry,loader+'\n'+entry+'\n    if _mjh_mobile_key(sPath) then return _mjh_mobile_load(sPath,iType) end',1)
    entry='function LoadPrefabAsync(sPath,iType,loadCallback)'
    if text.count(entry)!=1:raise ValueError('手游模型异步入口不兼容')
    text=text.replace(entry,entry+'\n    if _mjh_mobile_key(sPath) then local p = _mjh_mobile_load(sPath,iType); if loadCallback then loadCallback(p,sPath) end; return end',1)
    entry='function ObjectInitFormPool(kPath,kParent)'
    if text.count(entry)!=1:raise ValueError('手游模型对象池入口不兼容')
    text=text.replace(entry,entry+'\n    if _mjh_mobile_key(kPath) then return DRCSRef.ObjInit(_mjh_mobile_load(kPath,_ClassTypeof.GameObject), kParent and kParent.transform or nil) end',1)
    entry='function ReturnObjectToPool(obj,bActive)'
    if text.count(entry)!=1:raise ValueError('手游模型回收入口不兼容')
    text=text.replace(entry,entry+'\n    if obj and obj.gameObject and _mjh_mobile_key(obj.gameObject.name) then CS.UnityEngine.Object.Destroy(obj.gameObject); return end',1)
    return patch_dynamic_texture(text)

def patch_dynamic_texture(text):
    marker='-- MJH_MOBILE_SWITCH_V261'
    if marker in text:return text
    start=text.index('function DynamicChangeSpineFullPath(')
    anchor='\t\tskeletonCom.skeletonDataAsset = loadSpine'
    pos=text.find(anchor,start)
    if pos<0:raise ValueError('手游模型切换入口不兼容')
    prepare='''        -- MJH_MOBILE_SWITCH_V261
        if _mjh_mobile_key(newSkeletonDataFullPath) then _mjh_mobile_prepare(skeletonCom) end
'''
    text=text[:pos]+prepare+text[pos:]
    start=text.index('function DynamicChangeSpineFullPath(')
    anchor='\t\tskeletonCom:Initialize(true)';pos=text.index(anchor,start)+len(anchor)
    apply='''
        if _mjh_mobile_key(newSkeletonDataFullPath) then
            local texture = _mjh_mobile_load(newSkeletonDataFullPath, _ClassTypeof.Texture)
            if skeletonGrap then skeletonGrap.OverrideTexture = texture end
            if objSpine:GetComponent("Renderer") then ReplaceTextureForSkinNew(objSpine, texture) end
        elseif skeletonGrap then skeletonGrap.OverrideTexture = nil end
'''
    return text[:pos]+apply+text[pos:]

def runtime_pending(lib):
    if not MOBILE_ENABLED:return False
    rows=[r for r in lib.tables['RoleModel'].values() if r.get('Model','').startswith(PREFIX)]
    if not rows:return False
    text=lib.assets.script('ResourcesMgr.lua')
    if '-- MJH_MOBILE_MODELS_V261' not in text or '-- MJH_MOBILE_SWITCH_V261' not in text:return True
    return any(r.get('Texture')!=r['Model']+'_texture' for r in rows)

def repair_saved_bindings(lib):
    if not MOBILE_ENABLED:return
    for rid,record in lib.meta.items():
        settings=record.get('settings',{})
        if int(rid) in lib.roles and settings.get('mobile_binding'):
            validate(lib,settings);stage(lib,settings['mobile_binding'])
    for ident,row in list(lib.tables['RoleModel'].items()):
        if row.get('Model','').startswith(PREFIX) and row.get('Texture')!=row['Model']+'_texture':
            lib.set('RoleModel',ident,dict(Texture=row['Model']+'_texture',Hue=''))

def collect_object(store,packet,files):
    """Carry the four immutable runtime files in an existing character package."""
    mobile={}
    for token,node in packet['nodes'].items():
        value=node['row'].get('Model','')
        if node['table']!='RoleModel' or not value.startswith(PREFIX):continue
        require_mobile()
        key=value[len(PREFIX):]
        if not re.fullmatch('[0-9a-f]{32}',key):raise ValueError('手游模型编号无效')
        entries={}
        for name in ('binding.lua','model.skel','model.atlas','texture.png'):
            raw=store.read(store.root/INSTALL/key/name)
            if raw is None:raise ValueError('手游模型资源缺失：'+name)
            member='mobile/'+key+'/'+name;files[member]=raw;entries[name]=member
        mobile[key]=entries
    packet['extras']['mobile_models']=mobile

def import_object(store,packet,rows,payloads,files):
    mobile=packet['extras'].get('mobile_models',{})
    if mobile:require_mobile()
    for key,entries in mobile.items():
        if not re.fullmatch('[0-9a-f]{32}',key) or set(entries)!= {'binding.lua','model.skel','model.atlas','texture.png'}:raise ValueError('手游资源清单无效')
        records=[r['settings']['mobile_binding'] for r in packet['extras'].get('role_metadata',{}).values() if r.get('settings',{}).get('mobile_binding',{}).get('key')==key]
        if not records:raise ValueError('缺少手游模型人物绑定信息')
        for spec in records:
            model,texture=selected(spec)
            assert_bindable(model)
            if texture['name'] in AUXILIARY_TEXTURES:raise ValueError('配置包含辅助贴图，不能作为人物模型导入')
            custom=spec.get('custom_texture');png=read(texture)
            if custom:
                # Validate metadata and bytes before accepting files from a portable package.
                store.table('RoleModel');binding(store,model,texture,custom)
                png=files.get(entries['texture.png'])
                if png is None:raise ValueError('人物配置包缺少自定义手游贴图')
                check_custom(png,texture,custom)
            expected={'model.skel':read(model['skel']),'model.atlas':read(model['atlas']),'texture.png':png,'binding.lua':('return {base='+json.dumps(spec['base'])+',page='+json.dumps(model['page'])+',scale='+str(model.get('spine_scale',0.01))+'}\n').encode()}
            expected_key=resource_key(model,custom['sha256'] if custom else texture['sha256'],spec['base'])
            if key!=expected_key:raise ValueError('手游模型资源校验失败')
            for name,member in entries.items():
                if member!='mobile/'+key+'/'+name or files.get(member)!=expected[name]:raise ValueError('手游模型资源与目录不一致：'+name)
                path=store.root/INSTALL/key/name;prior=store.read(path)
                if prior is not None and prior!=files[member]:raise ValueError('目标手游模型资源冲突')
                payloads[path]=files[member]
    for row in rows.get('RoleModel',{}).values():
        if row.get('Model','').startswith(PREFIX) and row['Model'][len(PREFIX):] not in mobile:raise ValueError('人物配置包缺少手游模型资源')

def plan_loader(lib,data):
    if not MOBILE_ENABLED:return data
    if not any(r.get('Model','').startswith(PREFIX) for r in lib.tables['RoleModel'].values()):return data
    from client_config import Assets
    from role_model_ids import repair
    from role_battle_model import repair as repair_battle
    a=Assets(data);old=a.script('ResourcesMgr.lua');new=patch_loader(old)
    return repair_battle(repair(a.replace_script('ResourcesMgr.lua',new) if old!=new else data))
