"""Preserve mobile sprite canvases and the resource names used by existing disguises."""
import io,re
from pathlib import Path
from PIL import Image

def stage(entry,raw):
    meta=entry.get('sprite_canvas',{})
    if meta.get('version')!=1:
        raise ValueError('手游立绘资源缺少原始画布信息，请完整解压 V2.2.12 或更新版本的手游资源版')
    key=entry.get('legacy_sha256',entry['sha256'])
    if not re.fullmatch('[0-9a-f]{64}',key):raise ValueError('手游立绘资源编号无效')
    with Image.open(io.BytesIO(raw)) as image:
        if image.size!=(entry['width'],entry['height']):raise ValueError('手游立绘画布尺寸校验失败：'+entry['id'])
    # Keep the old filename: saved composite RoleModel rows refer to this path.
    return 'disguise_cg_'+key[:24]+'.png',raw

def head_resource(entry):
    head=entry.get('head')
    if not head:return None
    from mobile_models import read
    raw=read(head)
    with Image.open(io.BytesIO(raw)) as image:
        if image.size!=(head['width'],head['height']) or image.getbbox() is None:
            raise ValueError('手游头像资源无效：'+entry['id'])
    return 'head_mobile_'+head['sha256'][:24]+'.png',raw

def stage_head(lib,entry):
    result=head_resource(entry)
    if result is None:return None
    filename,raw=result
    path=lib.root/Path('ModProject/GameProject/Mod_MJH/Source/Other/role_editor')/filename
    lib.originals.setdefault(path,path.read_bytes() if path.exists() else None)
    lib.files[path]=raw
    return '#role_editor/'+filename

BEGIN='-- MJH_DISGUISE_PORTRAIT_LOADER_BEGIN'
END='-- MJH_DISGUISE_PORTRAIT_LOADER_END'

def patch_loader(text):
    from engine import DATA_ROOT
    block=(DATA_ROOT/'ui_assets/disguise_portraits.lua').read_text('utf8').strip()
    if BEGIN in text:
        if text.count(BEGIN)!=1 or text.count(END)!=1:raise ValueError('易容立绘加载补丁标记异常')
        start=text.index(BEGIN);end=text.index(END,start)+len(END)
        return text[:start]+block+text[end:]
    if text.count('function GetSprite(')!=1 or text.count('function GetSpriteAsync(')!=1:
        raise ValueError('易容立绘加载入口不兼容')
    return text.rstrip()+'\n\n'+block+'\n'
