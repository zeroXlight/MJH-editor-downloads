"""Render replacement atlases with the installed game's Spine vertex calculations."""
import hashlib, json, math, os, subprocess, tempfile
from pathlib import Path
from PIL import Image, ImageDraw

def runtime_data(root,info):
    from engine import DATA_ROOT
    helper=DATA_ROOT/'ui_assets/model_templates';reader=helper/'runtime_reader.cs'
    runtime=Path(root)/'DreamRivakes_Data/Managed/spine_runtime.dll'
    key=hashlib.sha256(info['skel']+info['atlas']+reader.read_bytes()+str(runtime.stat().st_mtime_ns).encode()).hexdigest()
    cache=Path(os.environ.get('LOCALAPPDATA',Path.home()/'AppData/Local'))/'MengJiangHuEquipEditor/model_preview'
    cache.mkdir(parents=True,exist_ok=True);target=cache/(key+'.json')
    if target.exists():
        try:
            data=json.loads(target.read_text(encoding='utf-8-sig'))
            if isinstance(data.get('draws'),list):return data
        except (OSError,ValueError):pass
    with tempfile.TemporaryDirectory(prefix='mjh_spine_') as tmp:
        tmp=Path(tmp);skel=tmp/'model.skel';atlas=tmp/'model.atlas';output=tmp/'pose.json'
        skel.write_bytes(info['skel']);atlas.write_bytes(info['atlas'])
        result=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(helper/'preview.ps1'),
            '-Runtime',str(runtime),'-Reader',str(reader),'-Skeleton',str(skel),'-Atlas',str(atlas),'-Output',str(output)],capture_output=True,timeout=45,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if result.returncode:raise ValueError('骨骼预览读取失败：'+result.stderr.decode('utf8',errors='replace')[:1000])
        data=json.loads(output.read_text(encoding='utf-8-sig'));target.write_bytes(output.read_bytes());return data

def render(data,image):
    image=image.convert('RGBA');draws=[d for d in data['draws'] if d['alpha']>0]
    if not draws:raise ValueError('模型初始姿态没有可见附件，可查看贴图布局')
    xs=[x for d in draws for x in d['xy'][::2]];ys=[y for d in draws for y in d['xy'][1::2]]
    minx,maxx,miny,maxy=min(xs),max(xs),min(ys),max(ys);scale=min(460/max(maxx-minx,1),460/max(maxy-miny,1))
    def point(x,y):return (26+(x-minx)*scale,26+(maxy-y)*scale)
    canvas=Image.new('RGBA',(512,512))
    for d in draws:
        uv=d['uv'];xy=d['xy'];triangles=d['triangles'];layer=Image.new('RGBA',canvas.size)
        for pos in range(0,len(triangles),3):
            ids=triangles[pos:pos+3];dst=[point(xy[i*2],xy[i*2+1]) for i in ids];src=[(uv[i*2]*image.width,uv[i*2+1]*image.height) for i in ids]
            x0,y0=dst[0];x1,y1=dst[1];x2,y2=dst[2];den=(x1-x0)*(y2-y0)-(x2-x0)*(y1-y0)
            if abs(den)<1e-7:continue
            coeff=[]
            for j in (0,1):
                z0,z1,z2=[p[j] for p in src];a=((z1-z0)*(y2-y0)-(z2-z0)*(y1-y0))/den;b=((x1-x0)*(z2-z0)-(x2-x0)*(z1-z0))/den;coeff.extend((a,b,z0-a*x0-b*y0))
            left=max(0,math.floor(min(p[0] for p in dst)));top=max(0,math.floor(min(p[1] for p in dst)));right=min(512,math.ceil(max(p[0] for p in dst)));bottom=min(512,math.ceil(max(p[1] for p in dst)))
            if right<=left or bottom<=top:continue
            a,b,c,e,f,g=coeff
            patch=image.transform((right-left,bottom-top),Image.Transform.AFFINE,(a,b,c+a*left+b*top,e,f,g+e*left+f*top),Image.Resampling.BILINEAR)
            mask=Image.new('L',patch.size);ImageDraw.Draw(mask).polygon([(x-left,y-top) for x,y in dst],fill=255);layer.paste(patch,(left,top),mask)
        if d['alpha']<1:layer.putalpha(layer.getchannel('A').point(lambda a:round(a*d['alpha'])))
        canvas.alpha_composite(layer)
    return canvas
