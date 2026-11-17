"""Searchable secret martial formula editor; all changes go to shared drafts."""
import tkinter as tk
from tkinter import ttk, messagebox
from aoyi_editor import result_choices, ingredient_choices, recipe_text, save_recipe

class FormulaDialog(tk.Toplevel):
    def __init__(self,parent,lib,host,*,editing=None,source=None):
        from martial_ui import SearchCombo
        super().__init__(parent);self.title('编辑秘奥义组合' if editing is not None else '新增秘奥义组合')
        self.transient(parent);self.lib=lib;self.editing=editing;self.result=None
        self.geometry(f'{min(1020,self.winfo_screenwidth()-80)}x{min(850,self.winfo_screenheight()-100)}');self.minsize(820,650)
        row=lib.tables['AoYi'].get(editing if editing is not None else source,{})
        self.ingredients=list(zip(row.get('MartialList',[]),row.get('LVList',[])))
        self.results={f'{i} · {name}':i for i,name in result_choices(lib).items()}
        self.choices={f'{i} · {name}':i for i,name in ingredient_choices(lib).items()}
        self.target=tk.StringVar(value=next((s for s,i in self.results.items() if i==row.get('AoYiID')),next(iter(self.results),'')))
        self.new=tk.BooleanVar(value=editing is None);self.name=tk.StringVar();self.turn=tk.StringVar(value=row.get('EffectiveRound',1))
        self.ingredient=tk.StringVar();self.level=tk.StringVar(value=20)
        bottom=ttk.Frame(self,padding=12);bottom.pack(side='bottom',fill='x')
        ttk.Button(bottom,text='加入草稿',style='Primary.TButton',command=self.accept).pack(side='right')
        ttk.Button(bottom,text='取消',command=self.destroy).pack(side='right',padx=8)
        preview=ttk.LabelFrame(self,text='组合效果预览',padding=8);preview.pack(side='bottom',fill='x',padx=12,pady=(0,6))
        self.preview=tk.Text(preview,height=6,wrap='word',font=('Microsoft YaHei UI',10),state='disabled',relief='flat');self.preview.pack(side='left',fill='x',expand=True)
        scroll=ttk.Scrollbar(preview,command=self.preview.yview);scroll.pack(side='right',fill='y');self.preview.configure(yscrollcommand=scroll.set)
        body=ttk.Frame(self,padding=12);body.pack(fill='both',expand=True)
        ttk.Label(body,text='公式只设置组合条件；奥义的伤害、招式和动画沿用结果功法。可用回合是“仅第几回合”，不是持续时间。',wraplength=950,style='Sub.TLabel').pack(anchor='w',pady=(0,8))
        columns=ttk.Frame(body);columns.pack(fill='x')
        resultbox=ttk.LabelFrame(columns,text='结果武学 / 新功法的招式模板（ID · 名称）',padding=8);resultbox.pack(side='left',fill='both',expand=True,padx=(0,10))
        SearchCombo(resultbox,self.target,list(self.results)).pack(fill='x')
        mode=ttk.Checkbutton(resultbox,text='复制所选秘奥义，创建独立新功法',variable=self.new,command=self.mode_changed)
        mode.pack(anchor='w',pady=6)
        if editing is not None:mode.configure(state='disabled')
        self.name_entry=ttk.Entry(resultbox,textvariable=self.name);self.name_entry.pack(fill='x')
        ttk.Label(resultbox,text='新功法名称（复制时必填）',style='Sub.TLabel').pack(anchor='w')
        config=ttk.LabelFrame(columns,text='回合设置',padding=10);config.pack(side='left',fill='y')
        ttk.Label(config,text='仅第几回合可用').pack(anchor='w')
        ttk.Spinbox(config,textvariable=self.turn,from_=1,to=1000,width=14).pack(anchor='w',pady=6)
        ttk.Label(config,text='原版公式通常为\n第 1、2 或 3 回合。',style='Sub.TLabel').pack(anchor='w')
        chooser=ttk.LabelFrame(body,text='组成武学（按名称或 ID 搜索）',padding=8);chooser.pack(fill='x',pady=10)
        SearchCombo(chooser,self.ingredient,list(self.choices)).pack(side='left',fill='x',expand=True)
        ttk.Label(chooser,text='所需等级').pack(side='left',padx=(12,6))
        ttk.Spinbox(chooser,textvariable=self.level,from_=1,to=1000,width=7).pack(side='left')
        ttk.Button(chooser,text='添加',command=self.add).pack(side='left',padx=6)
        ttk.Label(body,text='全部组成武学都需满足等级；条件等级不受修炼上限限制；不重复加入相同武学。暂不支持用另一个秘奥义作为组成材料。',wraplength=950,style='Sub.TLabel').pack(side='bottom',anchor='w')
        actions=ttk.Frame(body);actions.pack(side='bottom',fill='x',pady=6)
        for label,command in [('替换选中项 / 修改等级',self.replace),('移除',self.remove),('上移',lambda:self.move(-1)),('下移',lambda:self.move(1))]:
            ttk.Button(actions,text=label,command=command).pack(side='left',padx=(0,6))
        self.tree=host.make_tree(body,[('martial','组成武学（ID · 名称）',460),('level','所需等级',100)],height=5)
        self.tree.bind('<<TreeviewSelect>>',self.selected)
        for var in (self.target,self.name,self.turn,self.new):var.trace_add('write',self.update_preview)
        self.refresh();self.mode_changed();self.grab_set();self.wait_window()
    def mode_changed(self):
        self.name_entry.configure(state='normal' if self.new.get() else 'disabled');self.update_preview()
    def refresh(self,selected=None):
        self.tree.delete(*self.tree.get_children())
        for index,(mid,level) in enumerate(self.ingredients):
            self.tree.insert('','end',iid=str(index),values=(f'{mid} · {self.lib.name(mid)}',f'{level} 级'))
        if selected is not None and str(selected) in self.tree.get_children():self.tree.selection_set(str(selected));self.tree.see(str(selected))
        self.update_preview()
    def selected(self,_=None):
        if not self.tree.selection():return
        mid,level=self.ingredients[int(self.tree.selection()[0])]
        self.ingredient.set(next((s for s,i in self.choices.items() if i==mid),''));self.level.set(level)
    def pair(self):
        if self.ingredient.get() not in self.choices:raise ValueError('请搜索并从列表选择组成武学')
        mid=self.choices[self.ingredient.get()];level=int(self.level.get())
        if not 1<=level<=1000:raise ValueError('所需等级须为 1～1000 的整数')
        return mid,level
    def change(self,work):
        try:work()
        except Exception as e:messagebox.showerror('无法修改组合',str(e),parent=self)
    def add(self):
        def work():
            pair=self.pair()
            if any(i==pair[0] for i,_ in self.ingredients):raise ValueError('该武学已在组合中，请选中后修改等级')
            if len(self.ingredients)>=64:raise ValueError('编辑器每条公式最多支持 64 门武学')
            self.ingredients.append(pair);self.refresh(len(self.ingredients)-1)
        self.change(work)
    def index(self):
        if not self.tree.selection():raise ValueError('请先在组合表中选中一门武学')
        return int(self.tree.selection()[0])
    def replace(self):
        def work():
            index=self.index();pair=self.pair()
            if any(i==pair[0] for n,(i,_) in enumerate(self.ingredients) if n!=index):raise ValueError('该武学已在组合中')
            self.ingredients[index]=pair;self.refresh(index)
        self.change(work)
    def remove(self):
        def work():
            index=self.index();self.ingredients.pop(index);self.refresh(min(index,len(self.ingredients)-1))
        self.change(work)
    def move(self,direction):
        def work():
            index=self.index();other=index+direction
            if not 0<=other<len(self.ingredients):return
            self.ingredients[index],self.ingredients[other]=self.ingredients[other],self.ingredients[index];self.refresh(other)
        self.change(work)
    def update_preview(self,*_):
        try:
            mid=self.results[self.target.get()]
            row={'AoYiID':mid,'MartialList':[i for i,_ in self.ingredients],'LVList':[lv for _,lv in self.ingredients],'EffectiveRound':int(self.turn.get())}
            text=recipe_text(self.lib,row)
            if self.new.get():
                name=self.name.get().strip() or '待填写名称'
                text='新功法：《'+name+'》（新 ID 自动生成）\n招式模板：《'+self.lib.name(mid)+'》\n'+'\n'.join(text.splitlines()[1:])
        except (KeyError,ValueError):text='请完成结果武学和可用回合设置。'
        self.preview.configure(state='normal');self.preview.delete('1.0','end');self.preview.insert('1.0',text);self.preview.configure(state='disabled')
    def accept(self):
        try:
            if self.target.get() not in self.results:raise ValueError('请从列表选择秘奥义结果 / 模板')
            self.result=save_recipe(self.lib,self.results[self.target.get()],self.ingredients,int(self.turn.get()),editing=self.editing,new_name=self.name.get() if self.new.get() else None)
            self.destroy()
        except Exception as e:messagebox.showerror('无法加入草稿',str(e),parent=self)

class AoyiDialog(tk.Toplevel):
    def __init__(self,page):
        super().__init__(page);self.title('秘奥义组合');self.transient(page.winfo_toplevel());self.page=page;self.lib=page.library
        self.geometry(f'{min(1080,self.winfo_screenwidth()-80)}x{min(780,self.winfo_screenheight()-100)}');self.minsize(850,580)
        footer=ttk.Frame(self,padding=12);footer.pack(side='bottom',fill='x')
        ttk.Label(footer,text='修改先加入武学草稿；返回后点击“保存武学修改”，自动备份。',style='Sub.TLabel').pack(side='left')
        ttk.Button(footer,text='返回武学编辑',style='Primary.TButton',command=self.destroy).pack(side='right')
        top=ttk.Frame(self,padding=12);top.pack(fill='x')
        for text,cmd in [('新增组合',lambda:self.open_formula()),('编辑选中公式',lambda:self.open_formula(edit=True)),('以选中公式新增',lambda:self.open_formula(copy=True)),('编辑结果功法',self.edit_result),('修复组合等级上限',self.repair_caps),('修复旧版名称显示',self.repair_names)]:
            ttk.Button(top,text=text,command=cmd).pack(side='left',padx=(0,8))
        self.query=tk.StringVar();self.count=tk.StringVar();search=ttk.Frame(self,padding=(12,0,12,8));search.pack(fill='x')
        ttk.Label(search,text='搜索结果 / 组成武学名称或 ID').pack(side='left')
        ttk.Entry(search,textvariable=self.query).pack(side='left',fill='x',expand=True,padx=8)
        ttk.Label(search,textvariable=self.count,style='Sub.TLabel').pack(side='right')
        detail=ttk.LabelFrame(self,text='公式与游戏内效果',padding=8);detail.pack(side='bottom',fill='x',padx=12,pady=8)
        self.detail=tk.Text(detail,height=8,wrap='word',font=('Microsoft YaHei UI',10),relief='flat',state='disabled');self.detail.pack(side='left',fill='x',expand=True)
        scroll=ttk.Scrollbar(detail,command=self.detail.yview);scroll.pack(side='right',fill='y');self.detail.configure(yscrollcommand=scroll.set)
        wrap=ttk.Frame(self,padding=(12,0));wrap.pack(fill='both',expand=True)
        self.tree=page.host.make_tree(wrap,[('id','公式 ID',90),('result','结果武学（ID · 名称）',290),('ingredients','组成武学与等级',420),('round','可用回合',90)],height=10)
        self.tree.bind('<<TreeviewSelect>>',self.show_detail);self.tree.bind('<Double-1>',lambda _:self.open_formula(edit=True))
        self.query.trace_add('write',self.refresh);self.refresh();self.grab_set();self.wait_window()
    def refresh(self,*_):
        selected=self.tree.selection();self.tree.delete(*self.tree.get_children());words=self.query.get().strip().casefold().split()
        for ident,row in sorted(self.lib.tables['AoYi'].items()):
            text=recipe_text(self.lib,row)
            if not all(w in text.casefold() for w in words):continue
            name=f'{row["AoYiID"]} · {self.lib.name(row["AoYiID"])}'
            materials=' + '.join(f'{self.lib.name(i)} ({i}) {lv}级' for i,lv in zip(row['MartialList'],row['LVList']))
            self.tree.insert('','end',iid=str(ident),values=(str(ident)+(' *' if ident in self.lib.changes['AoYi'] else ''),name,materials,f'第 {row["EffectiveRound"]} 回合'))
        children=self.tree.get_children();self.count.set(f'{len(children)} / {len(self.lib.tables["AoYi"])} 条')
        if children:self.tree.selection_set(selected[0] if selected and selected[0] in children else children[0])
        self.show_detail()
    def repair_caps(self):
        try:
            from aoyi_editor import sync_caps
            with self.lib.edit():count=sync_caps(self.lib)
            self.lib.aoyi_runtime_requested=True
            self.refresh();self.page.refresh_list()
            messagebox.showinfo('组合等级上限',f'已将 {count} 个奥义的基础上限修正及动态上限读取修复加入草稿。\n游戏中取该角色各组成武学实际修炼上限的最低值，保留原生额外等级加成。\n请返回并保存武学修改，重启游戏后生效。',parent=self)
        except Exception as error:messagebox.showerror('修复未完成',str(error),parent=self)
    def show_detail(self,_=None):
        selected=self.tree.selection();text=recipe_text(self.lib,self.lib.tables['AoYi'][int(selected[0])]) if selected else '无匹配公式。'
        self.detail.configure(state='normal');self.detail.delete('1.0','end');self.detail.insert('1.0',text);self.detail.configure(state='disabled')
    def open_formula(self,edit=False,copy=False):
        selected=self.tree.selection()
        if (edit or copy) and not selected:messagebox.showerror('未选择公式','请先选中一条公式',parent=self);return
        ident=int(selected[0]) if selected else None
        d=FormulaDialog(self,self.lib,self.page.host,editing=ident if edit else None,source=ident if copy else None)
        self.grab_set()
        if d.result:
            self.page.combo_done(d.result[1]);self.query.set('');self.refresh();self.tree.selection_set(str(d.result[0]));self.tree.see(str(d.result[0]));self.show_detail()
    def edit_result(self):
        selected=self.tree.selection()
        if not selected:return
        mid=self.lib.tables['AoYi'][int(selected[0])]['AoYiID'];self.page.combo_done(mid);self.destroy()
    def repair_names(self):
        try:
            from language_routing import stage_repairs
            count=stage_repairs(self.lib)
            if count:
                selected=self.tree.selection()
                if selected:self.page.combo_done(self.lib.tables['AoYi'][int(selected[0])]['AoYiID'])
                self.page.refresh_list()
            messagebox.showinfo('名称分表修复',f'已将 {count} 条错放的名称 / 说明加入修复草稿。\n原编号和文本保持不变，普通自建武学也一并检查。\n请返回并保存武学修改，然后重启游戏。',parent=self)
        except Exception as e:messagebox.showerror('修复未完成',str(e),parent=self)
