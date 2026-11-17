"""Portable, offline visual index using the same identifiers as the in-game mask UI."""
import base64,hashlib,json,os,io
from pathlib import Path
from disguise_assets import NativeImages,icon_bytes
from edition import VERSION,EDITION_NAME
from contextlib import ExitStack

def html_bytes(root,prepared):
    with ExitStack() as resources:return _html_bytes(root,prepared,resources)

def _html_bytes(root,prepared,resources):
    root=Path(root);payloads,originals,*_=prepared
    config_path=root/'mod/editor_disguise/catalog.json'
    raw=payloads.get(config_path) or originals.get(config_path) or config_path.read_bytes()
    config=json.loads(raw);rows=[];images=None;icons={}
    cache=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'MengJiangHuEquipEditor/reference_thumbnails'
    cache.mkdir(parents=True,exist_ok=True)
    stamp=str(root.resolve())+str((root/'DreamRivakes_Data/resources.assets').stat().st_mtime_ns)
    for index,option in enumerate(config['options'],1):
        icon=option['icon']
        if icon not in icons:
            if icon.startswith('#'):
                path=root/'ModProject/GameProject/Mod_MJH/Source/Other'/icon[1:]
                raw=payloads.get(path) or path.read_bytes()
                from PIL import Image
                with Image.open(io.BytesIO(raw)) as im:raw=icon_bytes(im)
            else:
                target=cache/(hashlib.sha256((stamp+icon).encode()).hexdigest()+'.png')
                if not target.exists():
                    if images is None:images=resources.enter_context(NativeImages(root))
                    target.write_bytes(icon_bytes(images.image(icon)))
                raw=target.read_bytes()
            from PIL import Image
            with Image.open(io.BytesIO(raw)) as im:
                compressed=io.BytesIO();im.save(compressed,format='WEBP',quality=82,method=4)
            icons[icon]='data:image/webp;base64,'+base64.b64encode(compressed.getvalue()).decode()
        row={k:v for k,v in option.items() if k not in ('drawing','icon')}
        row['preview']=icons[icon];rows.append(row)
        if index%200==0:print(f'资源总表缩略图：{index} / {len(config["options"])}',flush=True)
    from engine import DATA_ROOT
    template=(DATA_ROOT/'ui_assets/disguise_reference.html').read_text(encoding='utf8')
    data=json.dumps(rows,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c')
    return template.replace('__VERSION__',VERSION+' '+EDITION_NAME).replace('__ROWS__',data).encode('utf8')

def export(root,prepared,path):
    path=Path(path);path.write_bytes(html_bytes(root,prepared));return path
