"""Team-head controls kept independent from dialogue portrait controls."""
import io,copy
from pathlib import Path
import tkinter as tk
from tkinter import ttk,filedialog
from PIL import Image,ImageTk,ImageDraw
from role_head import prepare,compose,DIRECTORY

def build(page,notebook):
 box=page.host.scroll_page(notebook,'队伍头像')
 ttk.Label(box,text='单独设置队伍／背包人物列表的方形头像。可上传图片并调整裁剪，也可选择游戏已有头像；不改变对话立绘。',wraplength=730,style='Sub.TLabel').pack(anchor='w',pady=10)
 page.head_source=None;page.head_vars={k:tk.DoubleVar(value=1 if k=='zoom' else 0) for k in ('zoom','x','y')}
 row=ttk.Frame(box);row.pack(fill='x',pady=8)
 for label,func in [('上传队伍头像',lambda:upload(page)),('选择已有头像',lambda:choose(page)),('恢复模板头像',lambda:reset(page))]:ttk.Button(row,text=label,command=func).pack(side='left',padx=4)
 page.head_preview=ttk.Label(box,text='模板头像');page.head_preview.pack(anchor='w',pady=8)
 page.head_note=tk.StringVar();ttk.Label(box,textvariable=page.head_note,wraplength=720,style='Sub.TLabel').pack(anchor='w')
 for k,label,lo,hi in [('zoom','缩放',0.25,8),('x','横向位置',-2048,2048),('y','纵向位置',-2048,2048)]:
  row=ttk.Frame(box);row.pack(fill='x',pady=6);ttk.Label(row,text=label,width=12).pack(side='left');ttk.Scale(row,variable=page.head_vars[k],from_=lo,to=hi,length=320).pack(side='left');ttk.Entry(row,textvariable=page.head_vars[k],width=10).pack(side='left',padx=8)
  page.head_vars[k].trace_add('write',lambda *_,p=page:changed(p))
 ttk.Label(box,text='位置以512×512裁剪画布为基准；正值向右／向下移动。选择已有头像时无需调整。保存人物修改后生效。',wraplength=720,style='Sub.TLabel').pack(anchor='w',pady=8)

def changed(page):
 if page.setting or not page.library or page.current is None:return
 try:layout={k:v.get() for k,v in page.head_vars.items()}
 except tk.TclError:return
 page.settings['head_layout']=layout;page.dirty=True
 try:render(page)
 except (ValueError,OSError):page.head_preview.configure(image='',text='请调整头像构图参数')

def load(page):
 page.head_source=None
 for k,v in page.head_vars.items():v.set(page.settings.get('head_layout',{}).get(k,1 if k=='zoom' else 0))
 render(page)

def render(page):
 page._head_image=None;page.head_preview.configure(image='',text='游戏内置头像')
 ref=page.settings.get('head','');source=Path(page.head_source) if page.head_source else None;raw=None
 if source is None and ref.startswith('#role_editor/'):
  name=ref.removeprefix('#role_editor/')
  if Path(name).name!=name:raise ValueError('头像路径无效')
  source=page.library.root/DIRECTORY/name;raw=page.library.files.get(source)
 if source and (raw or source.exists()):
  with Image.open(io.BytesIO(raw) if raw else source) as im:
   im=compose(im,page.settings.get('head_layout',{})) if page.head_source else im.convert('RGBA')
   im=im.resize((180,180),Image.Resampling.LANCZOS)
   canvas=Image.new('RGBA',(180,180),'#e8e6e0');canvas.alpha_composite(im)
   ImageDraw.Draw(canvas).rectangle((0,0,179,179),outline='#222222',width=3)
   page._head_image=ImageTk.PhotoImage(canvas,master=page)
  page.head_preview.configure(image=page._head_image,text='')
 page.head_note.set(('待保存图片：'+str(source) if page.head_source else '头像资源：'+ref)+'\n上传头像保存为512×512 PNG，游戏按队伍头像框缩放显示。')

def upload(page):
 if not page.available():return
 source=filedialog.askopenfilename(title='选择队伍头像图片',filetypes=[('图片','*.png *.jpg *.jpeg *.webp *.bmp')],parent=page)
 if not source:return
 try:prepare(source,page.current)
 except Exception as e:page.host.error(e);return
 page.head_source=source;page.settings['head_layout']={'zoom':1,'x':0,'y':0};page.setting=True
 try:
  for k,v in page.head_vars.items():v.set(1 if k=='zoom' else 0)
 finally:page.setting=False
 page.dirty=True;render(page)

def choose(page):
 if not page.available():return
 owners={page.library.row(r).get('ArtID'):page.library.name(r) for r in page.library.roles}
 choices=[(i,owners.get(i,'头像')+' · '+r.get('Head','')+f' · {i}') for i,r in page.library.tables['RoleModel'].items() if r.get('Head')]
 result=page.picker('选择已有队伍头像',choices,0)
 if result:page.head_source=None;page.settings['head']=page.library.tables['RoleModel'][result['id']]['Head'];page.dirty=True;render(page)

def reset(page):
 if not page.available():return
 record=page.library.meta.get(str(page.current),{});art=record.get('base_art',page.library.row(page.current)['ArtID'])
 page.head_source=None;page.settings['head']=record.get('before',{}).get('队伍头像',page.library.tables['RoleModel'].get(art,{}).get('Head',''));page.dirty=True;render(page)
