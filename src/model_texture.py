"""Import immutable PNG atlases, validate native templates and stage per-role bindings."""
import hashlib, io, json, re, struct, zipfile
from pathlib import Path, PurePosixPath
from PIL import Image

PREFIX='#model_editor/'
TEXTURE_DIR=Path('mod/editor_model_textures')
MAX_IMAGE=20*1024*1024

def binding_runtime_pending(lib):
    if not any(row.get('Texture','').startswith(PREFIX) for row in lib.tables['RoleModel'].values()):return False
    from role_model_ids import BOUND_MARKER as role_marker
    from role_battle_model import BOUND_MARKER as battle_marker
    return role_marker not in lib.assets.script('RoleDataManager.lua') or battle_marker not in lib.assets.script('Unit.lua')

def texture_dependencies(root,payloads):
    """Freeze referenced immutable textures for exports, including saved PNGs."""
    root=Path(root);names=set()
    for path,raw in payloads.items():
        if raw is None:continue
        path=Path(path)
        if path.suffix not in ('.bytes','.json','.assets'):continue
        names.update(n.decode('ascii') for n in re.findall(rb'#model_editor/(tex_[0-9a-f]{32}\.png)',raw))
        if path.name=='人物编辑.json':
            names.update(n.decode('ascii') for n in re.findall(rb'"filename"\s*:\s*"(tex_[0-9a-f]{32}\.png)"',raw))
    result={}
    for name in sorted(names):
        path=root/TEXTURE_DIR/name
        raw=payloads.get(path)
        if raw is None and path.exists():raw=path.read_bytes()
        if raw is None:raise ValueError('自定义模型贴图缺失，不能完整导出：'+name)
        if len(raw)>MAX_IMAGE or name!='tex_'+hashlib.sha256(raw).hexdigest()[:32]+'.png':raise ValueError('自定义模型贴图内容或校验值不一致，请重新导入：'+name)
        with Image.open(io.BytesIO(raw)) as im:
            if im.format!='PNG' or getattr(im,'is_animated',False) or im.width*im.height>16777216:raise ValueError('自定义模型贴图格式无效：'+name)
            im.verify()
        result[path]=raw
    return result

def template_info(lib,source_id):
    row=lib.tables['RoleModel'].get(source_id)
    if not row:raise ValueError('请选择有效的人物模型模板')
    model=row.get('Model','');name=model.split('/')[-1]+'_SkeletonData'
    a=lib.assets
    objects=getattr(lib,'_model_texture_objects',None)
    if objects is None:objects={o['id']:o for o in a.objects};lib._model_texture_objects=objects
    found=[]
    for obj in a.objects:
        if obj['kind']!=114:continue
        start=a.start+obj['off'];size=obj['length']
        if size<32:continue
        n=struct.unpack_from('<I',a.data,start+28)[0]
        if n!=len(name.encode('utf8')) or 32+n>size:continue
        if a.data[start+32:start+32+n]!=name.encode('utf8'):continue
        q=start+((32+n+3)&~3);count=struct.unpack_from('<I',a.data,q)[0]
        if count!=1:raise ValueError('当前版本只支持单页模型贴图，所选模型包含多页 atlas')
        if q+32>start+size:raise ValueError('模型资源引用越界')
        afile,atlas_id=struct.unpack_from('<iq',a.data,q+4)
        sfile,skel_id=struct.unpack_from('<iq',a.data,q+20)
        if afile or sfile:raise ValueError('该模板引用外部资源，暂不支持')
        atlas_obj=objects.get(atlas_id);skel_obj=objects.get(skel_id)
        if not atlas_obj or atlas_obj['kind']!=114 or not skel_obj or skel_obj['kind']!=49:raise ValueError('骨骼/atlas 引用不完整')
        at=a.start+atlas_obj['off'];an=struct.unpack_from('<I',a.data,at+28)[0];aq=at+((32+an+3)&~3)
        tf,tid=struct.unpack_from('<iq',a.data,aq)
        text_obj=objects.get(tid)
        if tf or not text_obj or text_obj['kind']!=49:raise ValueError('atlas 文本引用不完整')
        def blob(obj):
            p=a.start+obj['off'];n=struct.unpack_from('<I',a.data,p)[0];p=(p+4+n+3)&~3;length=struct.unpack_from('<I',a.data,p)[0]
            if p+4+length>a.start+obj['off']+obj['length']:raise ValueError('文本资源越界')
            return bytes(a.data[p+4:p+4+length])
        skel=blob(skel_obj);atlas=blob(text_obj)
        pages=re.findall(r'(?m)^([^\r\n]+\.(?:png|jpg|jpeg))\r?\nsize:\s*(\d+),\s*(\d+)',atlas.decode('utf8'))
        if len(pages)!=1:raise ValueError('只支持带明确尺寸的单页 atlas')
        page,w,h=pages[0];found.append(dict(model=model,page=page,width=int(w),height=int(h),skel=skel,atlas=atlas,
            skeleton_sha=hashlib.sha256(skel).hexdigest(),atlas_sha=hashlib.sha256(atlas).hexdigest(),source_id=source_id))
    if len(found)!=1:raise ValueError('无法唯一定位所选模型的骨骼和贴图布局，请选择其他模板')
    return found[0]

def png_bytes(raw,info,*,allow_resize=False,normalization=None,max_bytes=MAX_IMAGE):
    if not raw or len(raw)>max_bytes:raise ValueError(f'贴图须为不超过 {max_bytes//(1024*1024)} MB 的 PNG')
    with Image.open(io.BytesIO(raw)) as im:
        if im.format!='PNG':raise ValueError('模型贴图只接受 PNG 文件')
        if getattr(im,'is_animated',False):raise ValueError('模型贴图需要单帧 PNG，不能将动画 PNG 丢帧后导入')
        if im.width*im.height>16777216:raise ValueError('贴图尺寸超过 4096×4096 像素上限')
        target=(info['width'],info['height']);original=im.size
        if original!=target:
            if not allow_resize:raise ValueError(f"贴图尺寸不匹配：模板需要 {target[0]}×{target[1]}，图片为 {im.width}×{im.height}。请导入对应模板的拆件贴图。")
            if im.width*target[1]!=im.height*target[0]:raise ValueError(f"贴图比例不匹配：模板为 {target[0]}×{target[1]}，图片为 {im.width}×{im.height}。请使用相同比例的拆件贴图；不会拉伸或裁切。")
        im.load();image=im.convert('RGBA')
        if original!=target:
            # Pillow resamples RGBA through premultiplied alpha, avoiding
            # dark/colored fringes from transparent texels around cutouts.
            image=image.resize(target,Image.Resampling.LANCZOS)
        if normalization is not None:
            normalization.update(source_width=original[0],source_height=original[1],resized=original!=target)
        out=io.BytesIO();image.save(out,format='PNG');return out.getvalue()

def _safe_member(name):
    p=PurePosixPath(name)
    if '\\' in name or p.is_absolute() or any(v in ('..','') for v in p.parts) or ':' in name:raise ValueError('模板包含非法路径')
    return name

def import_texture(lib,path,source_id):
    """Return a validated binding and frozen bytes; do not mutate library or disk."""
    path=Path(path);manifest={};raw=None;zip_skel=zip_atlas=None
    if path.suffix.lower()=='.zip':
        if path.stat().st_size>64*1024*1024:raise ValueError('模板包不能超过 64 MB')
        with zipfile.ZipFile(path) as z:
            entries=z.infolist();names=[_safe_member(e.filename.rstrip('/')) for e in entries if not e.is_dir()]
            if len(entries)>400 or sum(e.file_size for e in entries)>128*1024*1024 or len(names)!=len(set(names)):raise ValueError('模板包文件数量、大小或重名记录无效')
            key=next((n for n in ('模板配置.json','selected_template.json') if n in names),None)
            if not key:raise ValueError('模板包缺少 模板配置.json 或 selected_template.json')
            if z.getinfo(key).file_size>2*1024*1024:raise ValueError('模板清单过大')
            manifest=json.loads(z.read(key).decode('utf-8-sig'))
            texture=manifest.get('texture') or (manifest.get('textures') or [None])[0]
            if not texture:raise ValueError('模板包未指定贴图')
            texture=_safe_member(texture)
            if z.getinfo(texture).file_size>MAX_IMAGE:raise ValueError('贴图不能超过 20 MB')
            raw=z.read(texture)
            for field,alternate in [('skel','skeleton'),('atlas','atlas')]:
                member=manifest.get(field) or manifest.get(alternate)
                if member:
                    member=_safe_member(member)
                    if z.getinfo(member).file_size>MAX_IMAGE:raise ValueError('骨骼或布局文件过大')
                    if field=='skel':zip_skel=z.read(member)
                    else:zip_atlas=z.read(member)
    else:
        if path.suffix.lower()!='.png':raise ValueError('请选择 PNG 贴图或本工具导出的 ZIP 模板包')
        if path.stat().st_size>MAX_IMAGE:raise ValueError('贴图不能超过 20 MB')
        raw=path.read_bytes()
        sidecar=path.parent/'模板配置.json'
        if sidecar.exists() and sidecar.stat().st_size<2*1024*1024:
            manifest=json.loads(sidecar.read_text(encoding='utf-8-sig'))
    if not isinstance(manifest,dict):raise ValueError('模板清单须为 JSON 对象')
    declared=manifest.get('sourceTemplate') or manifest.get('model')
    source=manifest.get('sourceRoleModelId',manifest.get('roleModelId'))
    if declared:
        selected=lib.tables['RoleModel'].get(source_id,{})
        if selected.get('Model')!=declared:
            raise ValueError('模板不匹配：已选 '+str(selected.get('Model',''))+'，导入文件要求 '+str(declared)+'。请先选择对应骨骼/贴图模板，再导入。')
    info=template_info(lib,source_id)
    declared_sha=manifest.get('skelSha256')
    if declared_sha and declared_sha!=info['skeleton_sha']:raise ValueError('模板包的骨骼版本与当前游戏不一致，请重新生成')
    if zip_skel is not None and hashlib.sha256(zip_skel).hexdigest()!=info['skeleton_sha']:raise ValueError('模板包的骨骼与游戏模板不一致')
    if zip_atlas is not None and hashlib.sha256(zip_atlas).hexdigest()!=info['atlas_sha']:raise ValueError('模板包的拆件布局与游戏模板不一致')
    scale=manifest.get('textureScale',1)
    if type(scale) is not int or scale not in (1,2,4,8):raise ValueError('高清贴图倍率须为 1、2、4 或 8')
    image_info=dict(info,width=info['width']*scale,height=info['height']*scale)
    if max(image_info['width'],image_info['height'])>4096:raise ValueError('高清贴图单边不能超过 4096 像素')
    normalization={};raw=png_bytes(raw,image_info,allow_resize=scale==1,normalization=normalization)
    digest=hashlib.sha256(raw).hexdigest();filename='tex_'+digest[:32]+'.png'
    spec=dict(filename=filename,sha256=digest,width=image_info['width'],height=image_info['height'],model=info['model'],source_id=source_id,
              skeleton_sha=info['skeleton_sha'],atlas_sha=info['atlas_sha'],label=str(manifest.get('characterName') or path.stem)[:100],
              original_source_id=source_id,original_texture=lib.tables['RoleModel'][source_id].get('Texture',''))
    if scale>1:spec.update(texture_scale=scale,atlas_width=info['width'],atlas_height=info['height'])
    if normalization['resized']:
        spec.update(source_width=normalization['source_width'],source_height=normalization['source_height'],resize_filter='LANCZOS')
    return spec,raw,info

def template_choices(lib):
    """Every bindable model, distinct from its many appearance configuration rows."""
    groups={}
    for i,row in lib.tables['RoleModel'].items():
        if not row.get('Model') or row.get('Texture','').startswith(PREFIX):continue
        groups.setdefault(row['Model'],[]).append(i)
    result=[]
    for model,ids in sorted(groups.items()):
        ident=min(ids)
        try:info=template_info(lib,ident)
        except ValueError:continue
        def varint(raw,pos):
            value=0;shift=0
            while True:
                b=raw[pos];pos+=1;value|=(b&127)<<shift
                if b<128:return value,pos
                shift+=7
                if shift>28:raise ValueError('骨骼数据无效')
        raw=info['skel'];pos=0
        for _ in range(2):n,pos=varint(raw,pos);pos+=max(0,n-1)
        pos+=8;extra=raw[pos];pos+=1
        if extra:
            pos+=4
            for _ in range(2):n,pos=varint(raw,pos);pos+=max(0,n-1)
        bones,_=varint(raw,pos)
        result.append((ident,f"{model} · {bones} 骨骼 · {info['width']}×{info['height']} · 源配置 {ident}"))
    return result

def validate_binding(lib,settings):
    spec=settings.get('texture_binding')
    if spec is None:return
    if not isinstance(spec,dict) or not re.fullmatch(r'tex_[0-9a-f]{32}\.png',str(spec.get('filename',''))):raise ValueError('自定义贴图绑定记录无效')
    if not re.fullmatch(r'[0-9a-f]{64}',str(spec.get('sha256',''))) or spec['filename']!='tex_'+spec['sha256'][:32]+'.png':raise ValueError('自定义贴图校验值无效')
    source=lib.tables['RoleModel'].get(settings.get('model_source'),{})
    if source.get('Model')!=spec.get('model'):raise ValueError('已切换模型模板，请重新导入匹配的贴图')
    if spec.get('source_id')!=settings.get('model_source'):raise ValueError('贴图模板绑定编号不一致，请重新导入')
    if type(spec.get('width')) is not int or type(spec.get('height')) is not int or not 0<spec['width']<=4096 or not 0<spec['height']<=4096:raise ValueError('贴图尺寸记录无效')

def stage_file(lib,spec,raw=None):
    path=lib.root/TEXTURE_DIR/spec['filename']
    before=path.read_bytes() if path.exists() else None
    lib.originals.setdefault(path,before)
    if raw is None:raw=lib.files.get(path,before)
    if raw is None or hashlib.sha256(raw).hexdigest()!=spec['sha256']:raise ValueError('已绑定的模型贴图丢失或被修改，请重新导入')
    if png_bytes(raw,spec)!=raw:raise ValueError('已绑定的贴图格式不规范，请重新导入')
    lib.files[path]=raw

LOADER='''-- MJH_CUSTOM_MODEL_TEXTURE_V252
local function _mjh_model_texture(path)
    local file = string.match(path, "^#model_editor/(tex_[0-9a-f]+%.png)$")
    if not file then return nil end
    if _loadedPerfabs[path] then return _loadedPerfabs[path] end
    local localPath = "mod/editor_model_textures/" .. file
    local ok, texture = pcall(function()
        if not DRCSRef.File.Exists(localPath) then return nil end
        local bytes = DRCSRef.File.ReadAllBytes(localPath)
        local tex = CS.UnityEngine.Texture2D(2, 2, CS.UnityEngine.TextureFormat.RGBA32, false)
        if not CS.UnityEngine.ImageConversion.LoadImage(tex, bytes) then
            CS.UnityEngine.Object.Destroy(tex)
            return nil
        end
        tex.name = path
        tex.filterMode = CS.UnityEngine.FilterMode.Bilinear
        tex.wrapMode = CS.UnityEngine.TextureWrapMode.Clamp
        return tex
    end)
    if not ok or not texture then
        DRCSRef.LogError("Custom model texture failed: " .. localPath)
        return nil
    end
    _loadedPerfabs[path] = texture
    _lastUsePerfabsTimes[path] = os.clock()
    return texture
end
'''

def patch_loader(text):
    marker='-- MJH_CUSTOM_MODEL_TEXTURE_V252'
    entry='function LoadPrefab(sPath,iType, mod)'
    branch='    if type(sPath) == "string" and string.sub(sPath, 1, 14) == "#model_editor/" then return _mjh_model_texture(sPath) end'
    if marker in text:
        if branch not in text:raise ValueError('自定义贴图加载补丁不完整，请刷新配置')
        return text
    if text.count(entry)!=1:raise ValueError('游戏贴图读取入口不兼容，未写入')
    return text.replace(entry,LOADER+'\n'+entry+'\n'+branch,1)

def plan_loader(data):
    from client_config import Assets
    a=Assets(data);old=a.script('ResourcesMgr.lua');new=patch_loader(old)
    data=a.replace_script('ResourcesMgr.lua',new) if old!=new else data
    from role_model_ids import repair as repair_models
    from role_battle_model import repair as repair_battle
    return repair_battle(repair_models(data))
