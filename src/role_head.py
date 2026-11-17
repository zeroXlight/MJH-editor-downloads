"""Independent square team portraits, preserving PNG alpha and original source."""
import io,hashlib,math
from pathlib import Path
from PIL import Image,ImageOps
DIRECTORY=Path('ModProject/GameProject/Mod_MJH/Source/Other/role_editor')
def validate(layout):
 if not isinstance(layout,dict):raise ValueError('头像构图参数无效')
 for k,lo,hi in [('zoom',0.25,8),('x',-2048,2048),('y',-2048,2048)]:
  v=layout.get(k,1 if k=='zoom' else 0)
  if type(v) not in (int,float) or not math.isfinite(v) or not lo<=v<=hi:raise ValueError('头像构图超出范围：'+k)
def compose(image,layout=None):
 layout=layout or {};validate(layout);image=ImageOps.exif_transpose(image).convert('RGBA')
 scale=max(512/image.width,512/image.height)*layout.get('zoom',1)
 # Crop in source coordinates rather than creating an oversized intermediate.
 cx=image.width/2-layout.get('x',0)/scale;cy=image.height/2-layout.get('y',0)/scale;half=256/scale
 return image.transform((512,512),Image.Transform.EXTENT,(cx-half,cy-half,cx+half,cy+half),Image.Resampling.BICUBIC)
def prepare(source,rid,layout=None):
 source=Path(source)
 if source.stat().st_size>20*1024*1024:raise ValueError('头像图片不能超过20MB')
 with Image.open(source) as im:
  if im.width*im.height>20000000:raise ValueError('头像图片不能超过2000万像素')
  result=compose(im,layout)
  if result.getbbox() is None:raise ValueError('头像裁剪区域为空，请调整位置')
  buffer=io.BytesIO();result.save(buffer,format='PNG');raw=buffer.getvalue()
 name=f'head_{rid}_{hashlib.sha256(raw).hexdigest()[:16]}.png'
 return '#role_editor/'+name,DIRECTORY/name,raw
