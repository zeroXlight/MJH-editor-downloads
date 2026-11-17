"""Named reference lists and searchable native growth authoring dialogs."""
import re
import tkinter as tk
from tkinter import ttk, messagebox
from client_config import lua_rows
from martial_preview import clan_names


def clean(text):return re.sub(r'<[^>]+>','',text)


def reference_names(lib,kind):
    if kind=='ClanID':return {0:'无所属门派',**clan_names(lib)}
    if kind=='LearnCondition':
        return {i:label for (category,i),label in lib.labels.items() if category=='ClanMartialConfig' and i}
    if kind=='MartialTags':
        return {i:clean(lib.text(r['NameID'])) for i,r in lua_rows(lib.assets.script('MartialTags.lua'),'MartialTags',lib.enums).items()}
    return {}


def parse_ids(text):return [int(x.strip()) for x in text.replace('，',',').split(',') if x.strip()]


def references_text(lib,kind,ids,values=None):
    names=reference_names(lib,kind)
    parts=[]
    for index,ident in enumerate(ids):
        text=f'{ident} · {names.get(ident,"未知名称（保留原编号）")}'
        if values is not None:
            value=values[index] if index<len(values) else '?'
            op='≤' if ident==2 and isinstance(value,int) and value<0 else '≥'
            text+=f' {op} {value}'
        parts.append(text)
    return '；'.join(parts) or ('无学习条件' if kind=='LearnCondition' else '无附加标签')


class ReferenceDialog(tk.Toplevel):
    def __init__(self,parent,lib,kind,ids,values=None):
        from martial_ui import SearchCombo
        super().__init__(parent);self.title('学习条件选择' if values is not None else '附加标签选择')
        self.transient(parent.winfo_toplevel());self.result=None;self.lib=lib;self.kind=kind
        self.geometry('800x590');self.minsize(680,480)
        self.rows=[[i,values[n] if values is not None and n<len(values) else 0] for n,i in enumerate(ids)];self.with_values=values is not None
        self.names=reference_names(lib,kind);self.names.update({i:self.names.get(i,'未知名称（保留原编号）') for i in ids})
        self.choices={f'{i} · {name}':i for i,name in sorted(self.names.items())}
        body=ttk.Frame(self,padding=14);body.pack(fill='both',expand=True)
        ttk.Label(body,text='按名称或编号搜索，选择后添加 / 更新。学习条件保持原有顺序并与数值一一对应。' if self.with_values else '按名称或编号搜索，选择现有标签后添加；标签说明沿用游戏配置。',wraplength=730,style='Sub.TLabel').pack(anchor='w',pady=(0,8))
        self.choice=tk.StringVar(value=next(iter(self.choices),''));self.search=SearchCombo(body,self.choice,list(self.choices));self.search.pack(fill='x')
        line=ttk.Frame(body);line.pack(fill='x',pady=10)
        self.value=tk.StringVar(value='0')
        if self.with_values:
            ttk.Label(line,text='条件数值').pack(side='left');ttk.Entry(line,textvariable=self.value,width=14).pack(side='left',padx=8)
        ttk.Button(line,text='添加',command=self.add).pack(side='left')
        ttk.Button(line,text='更新选中',command=self.update_row).pack(side='left',padx=6)
        ttk.Button(line,text='删除选中',command=self.remove).pack(side='left')
        columns=('id','name','value') if self.with_values else ('id','name')
        self.tree=ttk.Treeview(body,columns=columns,show='headings',selectmode='browse',height=10)
        self.tree.heading('id',text='ID');self.tree.column('id',width=80,stretch=False)
        self.tree.heading('name',text='名称');self.tree.column('name',width=400)
        if self.with_values:self.tree.heading('value',text='条件数值');self.tree.column('value',width=120)
        scroll=ttk.Scrollbar(body,command=self.tree.yview);scroll.pack(side='right',fill='y');self.tree.pack(fill='both',expand=True);self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind('<<TreeviewSelect>>',self.select)
        bar=ttk.Frame(self,padding=14);bar.pack(fill='x');ttk.Button(bar,text='使用此列表',style='Primary.TButton',command=self.accept).pack(side='right');ttk.Button(bar,text='取消',command=self.destroy).pack(side='right',padx=8)
        self.render();self.grab_set();self.wait_window()
    def render(self):
        self.tree.delete(*self.tree.get_children())
        for index,(ident,value) in enumerate(self.rows):self.tree.insert('','end',iid=str(index),values=(ident,self.names.get(ident,'未知名称'),value) if self.with_values else (ident,self.names.get(ident,'未知名称')))
    def input_row(self):
        if self.choice.get() not in self.choices:raise ValueError('请从列表选择名称')
        return [self.choices[self.choice.get()],int(self.value.get()) if self.with_values else 0]
    def add(self):
        try:
            row=self.input_row()
            if not self.with_values and any(r[0]==row[0] for r in self.rows):raise ValueError('这个标签已经在列表中')
            self.rows.append(row);self.render()
        except Exception as e:messagebox.showerror('输入有误',str(e),parent=self)
    def select(self,e=None):
        selection=self.tree.selection()
        if not selection:return
        ident,value=self.rows[int(selection[0])];self.choice.set(next((s for s,i in self.choices.items() if i==ident),''));self.value.set(str(value))
    def update_row(self):
        if not self.tree.selection():return
        try:self.rows[int(self.tree.selection()[0])]=self.input_row();self.render()
        except Exception as e:messagebox.showerror('输入有误',str(e),parent=self)
    def remove(self):
        if self.tree.selection():self.rows.pop(int(self.tree.selection()[0]));self.render()
    def accept(self):self.result=([r[0] for r in self.rows],[r[1] for r in self.rows]);self.destroy()


class GrowthDialog(tk.Toplevel):
    def __init__(self,parent,lib,mid,index=None,slot=1):
        from martial_growth import GrowthDraft
        from martial_editor import DEPARTS,RANKS
        super().__init__(parent);self.title('新增每级成长' if index is None else '修改每级成长')
        self.transient(parent.winfo_toplevel());self.geometry('940x670');self.minsize(780,550)
        self.result=None;self.lib=lib;self.mid=mid;self.index=index;self.slot=slot;self.grade=2
        if lib.growth is None:lib.growth=GrowthDraft(lib)
        self.growth=lib.growth;self.options=self.growth.available(lib,mid)
        if not self.options:self.destroy();raise ValueError('当前武学没有可用的原生成长表')
        current=None;current_profile=None
        if index is not None:
            current_profile=lib.growth_profile(mid,'GrowProIDs',index,slot);current=current_profile['id'];self.grade=current_profile['grade']
            if current not in self.options:self.destroy();raise ValueError('此成长尚未校验直接数值编辑，请保留原模板；当前支持原生精通、角色属性、威力系数和召唤等级成长')
        bar=ttk.Frame(self,padding=16);bar.pack(side='bottom',fill='x')
        ttk.Button(bar,text='加入草稿',style='Primary.TButton',command=self.accept).pack(side='right');ttk.Button(bar,text='取消',command=self.destroy).pack(side='right',padx=8)
        body=ttk.Frame(self,padding=16);body.pack(fill='both',expand=True)
        controls=ttk.Frame(body);controls.pack(side='bottom',fill='x')
        ttk.Label(body,text='选择成长模板并填写每级增加值。默认复制为当前武学独立词条；按名称或编号搜索。',wraplength=860,style='Sub.TLabel').pack(anchor='w',pady=(0,10))
        mode_line=ttk.Frame(body);mode_line.pack(fill='x',pady=(0,8))
        self.reuse=tk.BooleanVar(value=False)
        ttk.Radiobutton(mode_line,text='新建独立成长（默认，不修改模板）',variable=self.reuse,value=False,command=self.mode_changed).pack(side='left')
        ttk.Radiobutton(mode_line,text='引用现有成长（沿用模板数值）',variable=self.reuse,value=True,command=self.mode_changed).pack(side='left',padx=16)
        line=ttk.Frame(body);line.pack(fill='x');ttk.Label(line,text='搜索成长表').pack(side='left')
        self.query=tk.StringVar();ttk.Entry(line,textvariable=self.query).pack(side='left',fill='x',expand=True,padx=8);ttk.Button(line,text='清空',command=lambda:self.query.set('')).pack(side='left')
        wrap=ttk.Frame(body);wrap.pack(fill='both',expand=True,pady=10)
        self.tree=ttk.Treeview(wrap,columns=('id','name','value','scope'),show='headings',selectmode='browse',height=10)
        for key,title,width in [('id','模板 ID',100),('name','每级成长效果',200),('value','模板每级加成',170),('scope','模板适用范围',260)]:self.tree.heading(key,text=title);self.tree.column(key,width=width)
        self.tree.pack(side='left',fill='both',expand=True);scroll=ttk.Scrollbar(wrap,command=self.tree.yview);scroll.pack(side='right',fill='y');self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind('<<TreeviewSelect>>',self.select)
        self.value=tk.StringVar();self.selected=None
        entryline=ttk.Frame(controls);entryline.pack(fill='x',pady=8)
        ttk.Label(entryline,text='每级增加（游戏显示值）').pack(side='left');self.value_entry=ttk.Entry(entryline,textvariable=self.value,width=16);self.value_entry.pack(side='left',padx=8)
        self.preview=tk.StringVar();ttk.Label(controls,textvariable=self.preview,style='Preview.TLabel',padding=10,wraplength=850).pack(fill='x')
        self.warning=tk.StringVar();ttk.Label(controls,textvariable=self.warning,wraplength=850,style='Sub.TLabel').pack(anchor='w',pady=10)
        self.value.trace_add('write',self.preview_value);self.query.trace_add('write',self.search)
        self.rows={}
        m=lib.tables['Martial'][mid]
        for ident,row in self.options.items():
            profile=self.growth.option_profile(lib,mid,ident,self.grade);name=lib.attr_names.get(str(row['AttrType']),'属性 '+str(row['AttrType']))
            scope=(DEPARTS.get(row['KfType'],'未知') if row['KfType'] else '全部类别')+' · '+RANKS.get(m['Rank'],'未知')+'品质'
            self.rows[ident]=(ident,f'{name} · 属性 ID {row["AttrType"]}',self.growth.display(lib,profile),scope)
        self.search()
        initial=current if current in self.options else next(iter(self.options));self.tree.selection_set(str(initial));self.tree.see(str(initial));self.select()
        if current_profile is not None:self.value.set(str(self.growth.actual(lib,current_profile)))
        self.grab_set();self.wait_window()
    def search(self,*_):
        words=self.query.get().strip().casefold().split();self.tree.delete(*self.tree.get_children())
        for ident,row in self.rows.items():
            if all(q in ' '.join(map(str,row)).casefold() for q in words):self.tree.insert('','end',iid=str(ident),values=row)
        if self.selected is not None and self.tree.exists(str(self.selected)):self.tree.selection_set(str(self.selected))
    def select(self,e=None):
        sel=self.tree.selection()
        if not sel:return
        ident=int(sel[0])
        if ident==self.selected:return
        self.selected=ident;p=self.growth.option_profile(self.lib,self.mid,ident,self.grade)
        self.value.set(str(self.growth.actual(self.lib,p)))
        self.mode_changed(reset=False)
    def mode_changed(self,reset=True):
        if self.selected is None:return
        p=self.growth.option_profile(self.lib,self.mid,self.selected,self.grade)
        self.value_entry.configure(state='disabled' if self.reuse.get() else 'normal')
        if self.reuse.get():self.value.set(str(self.growth.actual(self.lib,p)))
        self.warning.set('引用所选成长表的原始数值，不修改游戏共用表。' if self.reuse.get() else '仅当前武学使用新词条。原模板及其他武学保持原值；保存时安装并备份独立成长支持，未校验的游戏版本会停止保存。')
        self.preview_value()
    def preview_value(self,*_):
        if self.selected is None:return
        try:
            p=self.growth.option_profile(self.lib,self.mid,self.selected,self.grade)
            if not self.reuse.get():p={**p,'factor':10000}
            raw=self.growth.encode_actual(self.lib,p,self.value.get())
            self.preview.set('修改后效果：每级 '+self.lib.attr_names[str(p['attr'])]+self.growth.display(self.lib,{**p,'raw':raw}))
        except Exception as e:self.preview.set('待完成输入：'+str(e))
    def accept(self):
        try:
            if self.selected is None:raise ValueError('请选择成长表')
            p=self.growth.option_profile(self.lib,self.mid,self.selected,self.grade)
            if not self.reuse.get():p={**p,'factor':10000}
            self.growth.encode_actual(self.lib,p,self.value.get())
            self.result=(self.selected,self.value.get(),self.reuse.get());self.destroy()
        except Exception as e:messagebox.showerror('输入有误',str(e),parent=self)
