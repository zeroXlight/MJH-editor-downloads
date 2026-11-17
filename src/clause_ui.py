"""Searchable clause-scope creation and delayed destructive confirmation."""
import time
import tkinter as tk
from tkinter import ttk,messagebox
from martial_editor import DEPARTS,RANKS
from martial_preview import clan_names,filter_description
from martial_scopes import criteria,matching,find,create

class ScopeDialog(tk.Toplevel):
    def __init__(self,parent,lib,mid):
        from martial_ui import SearchCombo
        super().__init__(parent);self.lib=lib;self.mid=mid;self.result=None
        self.title('新增词条 · 新增作用范围');self.geometry('790x700');self.minsize(670,570);self.transient(parent.winfo_toplevel())
        footer=ttk.Frame(self,padding=14);footer.pack(side='bottom',fill='x')
        self.action=ttk.Button(footer,text='新增作用范围（加入草稿）',style='Primary.TButton',command=self.accept);self.action.pack(side='right')
        ttk.Button(footer,text='取消',command=self.destroy).pack(side='right',padx=8)
        body=ttk.Frame(self,padding=16);body.pack(fill='both',expand=True)
        ttk.Label(body,text='新增作用范围',font=('Microsoft YaHei UI',16,'bold')).pack(anchor='w')
        ttk.Label(body,text='默认包含所有武学。已有相同条件会直接复用；保存武学修改后写入游戏。',style='Sub.TLabel',wraplength=730).pack(anchor='w',pady=8)
        self.choices=[{'所有类别 · 0':0}|{f'{n} · {i}':i for i,n in DEPARTS.items() if i!=15},
                      {'所有品质 · 0':0}|{f'{n}色 · {i}' if i<5 else f'{n}品质 · {i}':i for i,n in RANKS.items()},
                      {'所有门派 · 0':0}|{f'{n} · {i}':i for i,n in sorted(clan_names(lib).items())}]
        self.variables=[]
        for label,options in zip(('武学类别（外功 = 除内功之外全部类别）','品质','所属门派'),self.choices):
            ttk.Label(body,text=label).pack(anchor='w',pady=(8,2))
            var=tk.StringVar(value=next(iter(options)));self.variables.append(var)
            SearchCombo(body,var,options).pack(fill='x');var.trace_add('write',self.refresh)
        self.note=tk.StringVar();ttk.Label(body,textvariable=self.note,wraplength=730,style='Preview.TLabel',padding=10).pack(fill='x',pady=12)
        self.tree=ttk.Treeview(body,columns=('id','name','type','rank'),show='headings',height=6)
        for key,label,width in [('id','武学 ID',100),('name','匹配武学',280),('type','类别',95),('rank','品质',70)]:self.tree.heading(key,text=label);self.tree.column(key,width=width)
        scroll=ttk.Scrollbar(body,command=self.tree.yview);scroll.pack(side='right',fill='y');self.tree.configure(yscrollcommand=scroll.set);self.tree.pack(fill='both',expand=True)
        self.refresh();self.grab_set();self.wait_window()
    def selected(self):return tuple(options[var.get()] for options,var in zip(self.choices,self.variables))
    def refresh(self,*_):
        if not hasattr(self,'tree'):return
        row=criteria(self.lib,*self.selected());ids=matching(self.lib,row);existing=find(self.lib,row)
        self.note.set(f'匹配 {len(ids)} 门武学。'+(f'检测到相同作用范围：{existing}，将复用。' if existing is not None else '未发现相同条件，将新建独立范围。')+
                      ('\n外功属性效果保存时展开为互不重叠的具体类别；只支持固定武学属性效果（10）。' if row['MartialType']==10 else ''))
        self.action.configure(text='复用已有作用范围' if existing is not None else '新增作用范围（加入草稿）')
        self.tree.delete(*self.tree.get_children())
        for mid in ids:
            m=self.lib.tables['Martial'][mid];self.tree.insert('', 'end',values=(mid,self.lib.name(mid),DEPARTS.get(m['DepartEnum'],m['DepartEnum']),RANKS.get(m['Rank'],m['Rank'])))
    def accept(self):
        try:self.result=create(self.lib,*self.selected())[0];self.destroy()
        except Exception as e:messagebox.showerror('无法新增',str(e),parent=self)

class RestoreConfirm(tk.Toplevel):
    def __init__(self,parent,summary):
        super().__init__(parent);self.result=False;self.title('还原游戏基础词条');self.transient(parent.winfo_toplevel());self.resizable(False,False)
        ttk.Label(self,text='确认移除新增词条和作用范围？',font=('Microsoft YaHei UI',13,'bold'),padding=18).pack(anchor='w')
        ttk.Label(self,text=summary,wraplength=600,padding=(18,0,18,18)).pack(fill='x')
        bar=ttk.Frame(self,padding=18);bar.pack(fill='x')
        self.button=ttk.Button(bar,text='请等待 3 秒',state='disabled',style='Primary.TButton',command=self.accept);self.button.pack(side='right')
        ttk.Button(bar,text='取消',command=self.destroy).pack(side='right',padx=10)
        self.ready_at=time.monotonic()+3;self.timer=None;self.tick();self.grab_set();self.wait_window()
    def tick(self):
        remaining=self.ready_at-time.monotonic()
        if remaining<=0:self.button.configure(text='确认还原基础词条',state='normal');self.timer=None
        else:
            self.button.configure(text=f'请等待 {int(remaining)+1} 秒');self.timer=self.after(100,self.tick)
    def accept(self):
        if time.monotonic()<self.ready_at:return
        self.result=True;self.destroy()
    def destroy(self):
        if getattr(self,'timer',None):self.after_cancel(self.timer);self.timer=None
        super().destroy()
