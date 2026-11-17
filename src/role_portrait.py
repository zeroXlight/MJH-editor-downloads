"""Upload composition and previews using measured 1280x720 Unity prefab rectangles."""
import io
from PIL import Image, ImageOps, ImageDraw, ImageFont

def validate_layout(layout):
    if not isinstance(layout,dict):raise ValueError('立绘构图无效')
    for key,lo,hi in [('zoom',0.1,3),('x',-1024,1024),('y',-1024,1024)]:
        value=layout.get(key,1 if key=='zoom' else 0)
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not lo<=value<=hi:raise ValueError('立绘构图参数超出范围：'+key)
    if not isinstance(layout.get('flip',False),bool):raise ValueError('立绘翻转参数无效')

def compose(image,layout):
    validate_layout(layout)
    image=ImageOps.exif_transpose(image).convert('RGBA')
    if layout.get('flip'):image=ImageOps.mirror(image)
    # Keep full source detail up to 4096px; layout coordinates remain in 1024 units.
    side=min(4096,max(2048,max(image.size)))
    factor=side/max(image.size)*layout.get('zoom',1)
    left=(side-image.width*factor)/2+layout.get('x',0)*side/1024
    top=(side-image.height*factor)/2+layout.get('y',0)*side/1024
    # Render only the visible canvas, avoiding huge temporary images at 3x zoom.
    canvas=image.transform((side,side),Image.Transform.AFFINE,
        (1/factor,0,-left/factor,0,1/factor,-top/factor),Image.Resampling.BICUBIC)
    return canvas

def font(size):
    try:return ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',size)
    except OSError:return ImageFont.load_default()

def preview(image,mode,name,chat='',size=(960,540)):
    out=Image.new('RGBA',(1280,720),'#575044');d=ImageDraw.Draw(out)
    # A neutral scene keeps the source alpha visible without including another character.
    for x in range(0,1280,128):d.line((x,0,x,720),fill='#655d50',width=3)
    if mode=='roll':rect=(280,0,720,720);clip=(0,0,1280,720)
    elif mode=='dialogue':rect=(-138,-15.09,759.24,759.24);clip=(0,0,1280,720)
    else:
        d.rectangle((41,34,1239,699),fill='#d3d0c9',outline='#282522',width=9)
        rect=(-150.65,-174.51,870.4,870.4);clip=(63,75,386,663)
    # Unity Image.preserveAspect centers the complete texture, including transparent margins.
    x,y,w,h=rect;im=ImageOps.contain(image.convert('RGBA'),(round(w),round(h)),Image.Resampling.LANCZOS)
    im=ImageOps.mirror(im)
    layer=Image.new('RGBA',out.size);layer.alpha_composite(im,(round(x+(w-im.width)/2),round(y+(h-im.height)/2)))
    mask=Image.new('L',out.size);ImageDraw.Draw(mask).rectangle(clip,fill=255)
    layer.putalpha(__import__('PIL.ImageChops',fromlist=['multiply']).multiply(layer.getchannel('A'),mask));out.alpha_composite(layer)
    d=ImageDraw.Draw(out)
    if mode=='dialogue':
        d.rectangle((344,546,1125,592),fill='#111111');d.text((350,548),name,fill='white',font=font(27))
        d.polygon([(340,593),(1125,593),(1280,720),(340,720)],fill='#eeece7')
        line=next((v for v in chat.splitlines() if v.strip()),'……')
        for i in range(0,min(len(line),110),36):d.text((356,610+i//36*29),line[i:i+36],fill='#222222',font=font(22))
        d.text((975,25),'自动对话    对话记录',fill='white',font=font(22))
    elif mode=='roll':
        d.rectangle((264,536,1016,635),fill='#252830')
        for i,label in enumerate(['罪','疑','空','罪','疑','罪','疑','罪','疑']):
            x=400+i*60;d.polygon([(x,559),(x+32,591),(x,623),(x-32,591)],fill='#777777',outline='#dddddd');d.text((x-15,568),label,fill='#ffcb30',font=font(30))
        d.text((535,665),'点击任意位置继续',fill='#dddddd',font=font(24))
    else:
        d.rectangle((310,72,839,115),fill='#403b37');d.text((320,77),name,fill='#ffc35a',font=font(26))
        for box,title in [((310,117,839,291),'人物属性'),((310,300,839,405),'装备'),((310,415,564,653),'天赋'),((573,415,839,653),'武学'),((849,73,1200,291),'关系'),((849,300,1200,653),'包裹')]:
            d.rectangle(box,fill='#d3d0c9',outline='#b9b5ac',width=3);d.text((box[0]+10,box[1]+10),title,fill='#37312b',font=font(22))
        d.polygon([(88,599),(102,587),(118,599),(132,587),(146,599),(118,634)],fill='#ae342e');d.text((160,590),'50',fill='#292624',font=font(42))
        d.text((598,40),'观察',fill='#292624',font=font(22))
    return out.convert('RGB').resize(size,Image.Resampling.LANCZOS)
