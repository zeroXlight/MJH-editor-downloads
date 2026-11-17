"""Live ink-wash UI: scalable brush elements and a decorative artwork header."""
import tkinter as tk
from tkinter import ttk,font
from PIL import Image,ImageDraw,ImageTk
PAPER='#f2efe9';FIELD='#fcfaf6';INK='#282b2c';RED='#a33f35';BLUE='#287ba3';LINE='#ded8ce'

def brush(color,rough=False):
    # Nine-slice assets give native ttk controls antialiased rounded corners.
    scale=3;im=Image.new('RGBA',(90*scale,36*scale));d=ImageDraw.Draw(im)
    d.rounded_rectangle((2,2,268,106),radius=19,fill=color,outline=LINE if not rough else color,width=3)
    d.line((23,5,246,5),fill='#ffffff40',width=2)
    return im.resize((90,36),Image.Resampling.LANCZOS)


def icon(app,kind,color):
    key=(kind,color)
    if key in app._ink_icons:return app._ink_icons[key]
    im=Image.new('RGBA',(40,40));d=ImageDraw.Draw(im);w=3
    if kind=='folder':d.line([(5,13),(5,8),(17,8),(22,13),(34,13),(34,31),(5,31),(5,18),(34,18)],fill=color,width=w)
    elif kind=='refresh':d.arc((7,7,33,33),40,320,fill=color,width=w);d.line([(33,8),(33,17),(24,17)],fill=color,width=w)
    elif kind=='undo':d.arc((6,11,34,34),195,445,fill=color,width=w);d.line([(6,8),(6,18),(16,18)],fill=color,width=w)
    elif kind=='save':
        d.line([(6,5),(30,5),(35,10),(35,35),(6,35),(6,5)],fill=color,width=w)
        d.rectangle((13,5,27,15),outline=color,width=w);d.rectangle((12,23,28,35),outline=color,width=w)
    elif kind=='export':d.rectangle((7,4,28,35),outline=color,width=w);d.line([(15,21),(35,21),(28,15),(35,21),(28,27)],fill=color,width=w)
    elif kind=='plus':d.line((20,6,20,34),fill=color,width=w);d.line((6,20,34,20),fill=color,width=w)
    elif kind=='copy':d.rectangle((5,5,25,27),outline=color,width=w);d.rectangle((14,13,34,35),outline=color,width=w)
    elif kind=='trash':d.line((7,10,33,10),fill=color,width=w);d.rectangle((16,5,24,10),outline=color,width=w);d.rectangle((11,10,29,35),outline=color,width=w)
    elif kind=='edit':d.line([(7,31),(28,9),(33,14),(11,35),(7,31)],fill=color,width=w)
    result=ImageTk.PhotoImage(im.resize((18,18),Image.Resampling.LANCZOS),master=app);app._ink_icons[key]=result;return result

def apply_theme(app):
    style=ttk.Style(app);style.theme_use('clam');app._ink_images=[];app._ink_icons={}
    fonts=set(font.families(app));app.ink_font='Microsoft YaHei UI'
    app.ink_title_font=next((n for n in ('STKaiti','KaiTi','楷体',app.ink_font) if n in fonts),app.ink_font)
    def photo(im):
        p=ImageTk.PhotoImage(im,master=app);app._ink_images.append(p);return p
    def button(name,colors,rough=False):
        pics=[photo(brush(c,rough)) for c in colors]
        style.element_create(name,'image',pics[0],('disabled',pics[3]),('pressed',pics[2]),('active',pics[1]),border=(12,7,12,7),padding=0,sticky='nsew')
        return [(name,{'sticky':'nswe','children':[('Button.padding',{'sticky':'nswe','children':[('Button.focus',{'sticky':'nswe','children':[('Button.label',{'sticky':'nswe'})]})]})]})]
    for name,colors,rough in [('TButton',(FIELD,'#f0e8db','#e4d8c4','#e9e4da'),False),('Primary.TButton',(BLUE,'#4987b1','#2b5e84','#a8b3b6'),True),('Ink.TButton',(FIELD,'#f0ebe3','#e8e1d7','#efebe5'),False),('Danger.TButton',(RED,'#a3463a','#6d2722','#b5a197'),True)]:
        style.layout(name,button('Ink.'+name,colors,rough))
    tabs=[photo(brush(c,True)) for c in ('#eeeae2',RED,'#e6dfd4')]
    style.element_create('Ink.tab','image',tabs[0],('selected',tabs[1]),('active',tabs[2]),border=(12,7,12,7),padding=0,sticky='nsew')
    style.layout('TNotebook.Tab',[('Ink.tab',{'sticky':'nswe','children':[('Notebook.padding',{'sticky':'nswe','children':[('Notebook.focus',{'sticky':'nswe','children':[('Notebook.label',{'sticky':'nswe'})]})]})]})])
    panel=Image.new('RGBA',(90,36));d=ImageDraw.Draw(panel)
    d.rounded_rectangle((1,1,88,34),radius=9,fill=FIELD,outline=LINE)
    style.element_create('Ink.panel','image',photo(panel),border=(12,12,12,12),padding=0,sticky='nsew')
    for name in ('TNotebook','Paper.TFrame','Card.TFrame'):
        style.layout(name,[('Ink.panel',{'sticky':'nswe'})])
    app.configure(background=PAPER)
    style.configure('.',font=(app.ink_font,10),background=FIELD,foreground=INK)
    for name in ('TFrame','TLabel'):style.configure(name,background=FIELD,foreground=INK)
    style.configure('Shell.TFrame',background=PAPER)
    style.configure('Shell.TLabel',background=PAPER,foreground='#8a857c',font=(app.ink_font,9))
    style.configure('Toolbar.TFrame',background=FIELD)
    style.configure('Title.TLabel',font=(app.ink_font,17,'bold'),foreground=INK)
    style.configure('Sub.TLabel',foreground='#807c74',font=(app.ink_font,9));style.configure('Badge.TLabel',foreground=RED,font=('Microsoft YaHei UI',10,'bold'))
    style.configure('Preview.TLabel',background='#eee6d7',foreground='#5c5141',borderwidth=0)
    for name in ('Card.TFrame','Card.TLabel'):style.configure(name,background=FIELD,foreground=INK)
    style.configure('CardTitle.TLabel',background=FIELD,foreground=RED,font=(app.ink_font,14,'bold'))
    style.configure('TNotebook',background=PAPER,borderwidth=0,tabmargins=(0,0,0,0))
    style.map('TNotebook.Tab',expand=[('selected',(0,0,0,0))],padding=[('selected',(18,9))])
    style.configure('TNotebook.Tab',padding=(18,9),font=(app.ink_font,10,'bold'))
    style.map('TNotebook.Tab',foreground=[('selected',FIELD),('disabled','#aaa69b'),('active',RED)])
    style.configure('Workspace.TNotebook.Tab',padding=(28,12),font=(app.ink_font,12,'bold'))
    style.map('Workspace.TNotebook.Tab',padding=[('selected',(28,12))])
    style.configure('Workspace.TNotebook',background=PAPER,tabmargins=(0,0,0,4))
    style.configure('TButton',padding=(12,7),foreground=INK,font=(app.ink_font,10));style.map('TButton',foreground=[('disabled','#99958b'),('active',RED)])
    for name in ('Primary.TButton','Danger.TButton'):
        style.configure(name,foreground=FIELD,padding=(13,6));style.map(name,foreground=[('disabled','#eee9df'),('active',FIELD)])
    style.configure('Ink.TButton',foreground=INK,padding=(12,7))
    style.map('Ink.TButton',foreground=[('disabled','#aaa49a'),('active',RED)])
    for name in ('TEntry','TCombobox','TSpinbox'):
        style.configure(name,padding=(7,5),fieldbackground=FIELD,background='#f3efe8',foreground=INK,bordercolor=LINE,lightcolor=FIELD,darkcolor=LINE,arrowcolor=INK,borderwidth=1,relief='flat')
        style.map(name,fieldbackground=[('disabled','#ece7de'),('readonly',FIELD)],foreground=[('disabled','#979287'),('readonly',INK)],bordercolor=[('focus',RED)])
    style.configure('TLabelframe',background=FIELD,bordercolor=LINE,lightcolor=LINE,darkcolor=LINE,relief='solid',borderwidth=1)
    style.configure('TLabelframe.Label',background=FIELD,foreground=INK,font=(app.ink_font,11,'bold'))
    style.configure('TCheckbutton',background=FIELD,foreground=INK);style.map('TCheckbutton',background=[('active',FIELD)],foreground=[('disabled','#979287')])
    # Explicit check mark instead of clam's ambiguous cross; retain ttk state/keyboard behavior.
    size=max(18,round(18*float(app.tk.call('tk','scaling'))/(4/3)))
    def check_image(selected,disabled=False):
        im=Image.new('RGBA',(80,80));d=ImageDraw.Draw(im)
        color='#aaa69b' if disabled else BLUE
        d.rounded_rectangle((9,9,69,69),radius=7,fill='#ece7de' if disabled else FIELD,outline=color if selected else LINE,width=5)
        if selected:d.line([(23,40),(35,52),(57,27)],fill=color,width=9,joint='curve')
        return photo(im.resize((size,size),Image.Resampling.LANCZOS))
    empty,checked,disabled,disabled_checked=[check_image(s,d) for s,d in [(False,False),(True,False),(False,True),(True,True)]]
    style.element_create('Ink.checkindicator','image',empty,('disabled','selected',disabled_checked),('disabled',disabled),('selected',checked),sticky='w')
    def check_layout(nodes):
        result=[]
        for name,options in nodes:
            options=dict(options)
            if 'children' in options:options['children']=check_layout(options['children'])
            result.append(('Ink.checkindicator' if name=='Checkbutton.indicator' else name,options))
        return result
    style.layout('TCheckbutton',check_layout(style.layout('TCheckbutton')))
    style.configure('Treeview',rowheight=34,background=FIELD,fieldbackground=FIELD,foreground=INK,borderwidth=0,bordercolor=LINE,lightcolor=FIELD,darkcolor=FIELD,relief='flat',font=('Microsoft YaHei UI',10))
    style.configure('Treeview.Heading',background='#f0ece4',foreground=INK,font=(app.ink_font,10,'bold'),padding=(8,8),relief='flat',borderwidth=0)
    style.map('Treeview.Heading',background=[('active','#e8e1d6')]);style.map('Treeview',background=[('selected','#f3ded7')],foreground=[('selected','#963b30')])
    for name in ('Vertical.TScrollbar','Horizontal.TScrollbar'):
        style.configure(name,background='#b9b5ad',troughcolor='#f1ede6',bordercolor=PAPER,lightcolor=PAPER,darkcolor=PAPER,arrowcolor='#535c56',borderwidth=0,arrowsize=11)
        style.map(name,background=[('active','#5f6d64')])
    style.configure('TProgressbar',background=RED,troughcolor='#e4dece',borderwidth=0)
    app.option_add('*TCombobox*Listbox.font',('Microsoft YaHei UI',10));app.option_add('*TCombobox*Listbox.background',FIELD)
    app.option_add('*TCombobox*Listbox.selectBackground','#f3ded7');app.option_add('*TCombobox*Listbox.selectForeground','#963b30')
    def mapped(event):
        widget=event.widget
        if isinstance(widget,ttk.Button) and not widget.cget('image'):
            labels={'选择目录':'folder','读取目录':'refresh','重新读取':'refresh','还原所有修改':'undo','保存装备修改':'save','保存武学修改':'save','保存人物修改':'save','导出修改副本':'export','添加':'plus','修改':'edit','复制':'copy','删除':'trash'}
            kind=labels.get(widget.cget('text'))
            if kind:widget.configure(image=icon(app,kind,FIELD if widget.cget('style') in ('Primary.TButton','Danger.TButton') else INK),compound='left')
        elif isinstance(widget,(tk.Text,tk.Listbox)):
            widget.configure(background=FIELD,foreground=INK,selectbackground='#f3ded7',selectforeground=RED,relief='flat',highlightthickness=1,highlightbackground=LINE,highlightcolor=BLUE,font=(app.ink_font,10))
            if isinstance(widget,tk.Text):widget.configure(insertbackground=BLUE,padx=12,pady=10)
        elif isinstance(widget,tk.Canvas) and not isinstance(widget,InkHeader):widget.configure(background=FIELD)
        elif isinstance(widget,tk.Toplevel):widget.configure(background=FIELD)
    app.bind_all('<Map>',mapped,add='+')

class InkHeader(tk.Canvas):
    def __init__(self,parent,version):
        from engine import DATA_ROOT
        self.app=parent.winfo_toplevel();self.version=version;self.photos=[];self.job=None
        super().__init__(parent,height=132,background=PAPER,highlightthickness=0)
        with Image.open(DATA_ROOT/'ui_assets/ink_landscape.png') as source:self.art=source.convert('RGB')
        self.bind('<Configure>',self.schedule);self.bind('<Destroy>',self.cleanup,add='+')
        self.app.bind('<Configure>',self.resize_height,add='+')
    def resize_height(self,event):
        if event.widget is self.app:
            height=110 if event.height<850 else 132
            if int(self.cget('height'))!=height:self.configure(height=height)
    def cleanup(self,event):
        if event.widget is self and self.job:self.after_cancel(self.job);self.job=None
    def schedule(self,event):
        if self.job:self.after_cancel(self.job)
        self.job=self.after(45,self.draw)
    def draw(self):
        self.job=None;w=max(1,self.winfo_width());h=self.winfo_height();self.delete('all');self.photos=[]
        # Keep the detailed scenery on the right; the title has a quiet paper field.
        art=self.art.resize((w,round(w*self.art.height/self.art.width)),Image.Resampling.LANCZOS)
        top=max(0,art.height//3-20);art=art.crop((0,top,w,top+h))
        veil=Image.new('L',(w,h));d=ImageDraw.Draw(veil)
        for x in range(w):
            opacity=int(240-170*max(0,min(1,(x-w*.42)/(w*.58))))
            d.line((x,0,x,h),fill=opacity)
        paper=Image.new('RGB',(w,h),PAPER);art=Image.composite(paper,art,veil)
        pic=ImageTk.PhotoImage(art,master=self);self.photos.append(pic);self.create_image(0,0,anchor='nw',image=pic)
        seal=Image.new('RGBA',(48*3,82*3));sd=ImageDraw.Draw(seal)
        sd.rounded_rectangle((2,2,141,243),radius=24,fill=RED)
        stamp=ImageTk.PhotoImage(seal.resize((48,82),Image.Resampling.LANCZOS),master=self);self.photos.append(stamp)
        self.create_image(14,23,anchor='nw',image=stamp)
        self.create_text(38,64,text='梦\n江\n湖',font=(self.app.ink_title_font,15,'bold'),fill=FIELD)
        title=self.create_text(86,51,anchor='w',text='已有装备/武学/人物编辑器',font=(self.app.ink_title_font,29,'bold'),fill='#1e2423')
        end=self.bbox(title)[2]
        self.create_text(end+18,53,anchor='w',text=self.version,font=(self.app.ink_font,10),fill='#927b69')
        self.create_text(88,94,anchor='w',text='装备属性   |   武学创作   |   人物编辑   |   功能修改',font=(self.app.ink_font,10),fill='#706e66')
        if w>1200:self.create_text(w-28,102,anchor='e',text='江湖路远 · 自在由心',font=(self.app.ink_title_font,12),fill='#555c56')


class DataTree(ttk.Treeview):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self.tag_configure('stripe',background='#f6f2ec');self._stripe_count=0
        self.empty_art=tk.Canvas(self,background=FIELD,highlightthickness=0);self.empty_photo=None
        self.bind('<Configure>',self.paint_empty,add='+')
    def paint_empty(self,event=None):
        if self.get_children():self.empty_art.place_forget();return
        self.empty_art.place(relx=.03,rely=.30,relwidth=.94,relheight=.45)
        w=max(1,int(self.winfo_width()*.94));h=max(1,int(self.winfo_height()*.45))
        self.empty_art.delete('all')
        self.empty_art.create_text(w/2,h/2,text='暂无数据',font=('Microsoft YaHei UI',12),fill='#969086')
        self.empty_art.create_text(w/2,h/2+30,text='读取配置或选择条目后在此编辑',font=('Microsoft YaHei UI',9),fill='#aaa398')
    def insert(self,parent,index,**kwargs):
        self.empty_art.place_forget()
        if self._stripe_count%2:kwargs['tags']=tuple(kwargs.get('tags',()))+('stripe',)
        result=super().insert(parent,index,**kwargs);self._stripe_count+=1;return result
    def delete(self,*items):
        super().delete(*items)
        if not self.get_children():self._stripe_count=0;self.paint_empty()
