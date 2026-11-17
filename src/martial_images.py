"""Independent PNG icons using the game's existing # local sprite loader."""
import hashlib, io
from pathlib import Path
from PIL import Image, ImageOps

ICON_DIR = Path('ModProject/GameProject/Mod_MJH/Source/Other/martial_editor')

def prepare_icon(source, mid):
    source=Path(source)
    if source.stat().st_size>20*1024*1024:raise ValueError('图片不能超过 20 MB')
    with Image.open(source) as im:
        if im.width*im.height>20000000:raise ValueError('图片分辨率过大，请使用 2000 万像素以内的图片')
        im=ImageOps.exif_transpose(im).convert('RGBA')
        im.thumbnail((256,256),Image.Resampling.LANCZOS)
        result=Image.new('RGBA',(256,256));result.alpha_composite(im,((256-im.width)//2,(256-im.height)//2))
        out=io.BytesIO();result.save(out,format='PNG');raw=out.getvalue()
    filename=f'{int(mid)}_{hashlib.sha256(raw).hexdigest()[:16]}.png'
    return '#martial_editor/'+filename,ICON_DIR/filename,raw

def icon_path(root, icon):
    if not icon.startswith('#martial_editor/'):return None
    name=icon[len('#martial_editor/'):]
    if Path(name).name!=name or not name.endswith('.png'):raise ValueError('自定义图标路径无效')
    target=(Path(root)/ICON_DIR/name).resolve()
    if not target.is_relative_to((Path(root)/ICON_DIR).resolve()):raise ValueError('自定义图标路径越界')
    return target
