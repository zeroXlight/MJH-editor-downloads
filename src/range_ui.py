"""Named 5 by 8 area picker: individual clicks and rectangular drag painting."""
import tkinter as tk
from tkinter import ttk,messagebox
from martial_ranges import CELLS,AREA_START,AREA_END,create_range,range_name,apply_clause,update_range,references,display_name,clear_clause,clear_target

class AreaGrid(ttk.Frame):
    def __init__(self,parent,on_change=lambda:None):
        super().__init__(parent);self.cells={(0,0)};self.fullscreen=False;self.on_change=on_change;self.drag=None
        self.canvas=tk.Canvas(self,width=600,height=210,background='#f3efe5',highlightthickness=0);self.canvas.pack(fill='both',expand=True)
        self.canvas.bind('<Configure>',lambda e:self.draw())
        self.canvas.bind('<ButtonPress-1>',self.press);self.canvas.bind('<B1-Motion>',self.motion);self.canvas.bind('<ButtonRelease-1>',self.release)
        bar=ttk.Frame(self);bar.pack(fill='x',pady=8)
        for label,command in [('全选',lambda:self.set_cells(CELLS)),('全屏范围',lambda:self.set_cells(CELLS,True)),('全部取消',lambda:self.set_cells(set()))]:ttk.Button(bar,text=label,command=command).pack(side='left',padx=(0,8))
        self.status=tk.StringVar();ttk.Label(bar,textvariable=self.status,style='Sub.TLabel').pack(side='right');self.draw()
    def set_cells(self,cells,fullscreen=False):
        self.cells=set(cells);self.fullscreen=fullscreen;self.drag=None;self.draw();self.on_change()
    def point(self,event):
        w=max(self.canvas.winfo_width(),8)/8;h=max(self.canvas.winfo_height(),5)/5
        col=int(event.x//w);row=int(event.y//h)
        return (col-3,row-2) if 0<=col<8 and 0<=row<5 else None
    def press(self,event):
        p=self.point(event)
        if p is None:return
        self.drag=(p,set(self.cells),p not in self.cells);self.fullscreen=False;self.paint(p)
    def motion(self,event):
        p=self.point(event)
        if p is not None and self.drag:self.paint(p)
    def release(self,event):
        self.motion(event);self.drag=None
    def paint(self,end):
        start,before,adding=self.drag
        rect={(x,y) for x,y in CELLS if min(start[0],end[0])<=x<=max(start[0],end[0]) and min(start[1],end[1])<=y<=max(start[1],end[1])}
        self.cells=before|rect if adding else before-rect
        self.draw();self.on_change()
    def draw(self):
        c=self.canvas;c.delete('all');w=max(c.winfo_width(),600 if c.winfo_width()<=1 else 8)/8;h=max(c.winfo_height(),210 if c.winfo_height()<=1 else 5)/5
        for x,y in sorted(CELLS):
            left=(x+3)*w;top=(y+2)*h;chosen=(x,y) in self.cells
            c.create_rectangle(left+2,top+2,left+w-2,top+h-2,fill='#409eff' if chosen else '#fbf8f1',outline='#b7ad9b')
            c.create_text(left+w/2,top+h/2,text='人物中心' if (x,y)==(0,0) else f'{x:+d}, {y:+d}',fill='white' if chosen else '#506580',font=('Microsoft YaHei UI',10))
        self.status.set('全屏范围（整个战场）' if self.fullscreen else f'已选 {len(self.cells)} / 40 格')

class RangeDialog(tk.Toplevel):
    def __init__(self,parent,lib,mid,ref=None):
        from martial_ui import SearchCombo
        super().__init__(parent);self.lib=lib;self.mid=mid;self.result=None
        self.title('新增 / 编辑技能作用范围');self.geometry('820x910');self.minsize(700,860);self.transient(parent.winfo_toplevel())
        footer=ttk.Frame(self,padding=12);footer.pack(side='bottom',fill='x')
        ttk.Button(footer,text='应用到当前武学（新增 / 更新词条）',style='Primary.TButton',command=self.accept).pack(side='right')
        self.edit_button=ttk.Button(footer,text='仅修改所选范围',command=self.edit_selected,state='disabled');self.edit_button.pack(side='right',padx=8)
        ttk.Button(footer,text='取消',command=self.destroy).pack(side='right',padx=8)
        body=ttk.Frame(self,padding=16);body.pack(fill='both',expand=True)
        ttk.Label(body,text='改变技能作用范围',font=('Microsoft YaHei UI',16,'bold')).pack(anchor='w')
        ttk.Label(body,text='词条加入当前武学，装备并达到解锁等级后改变指定武学的作用范围；施放距离保持原值。',wraplength=760,style='Sub.TLabel').pack(fill='x',pady=8)
        self.targets={f'{lib.name(i)} · {i}':i for i,m in lib.tables['Martial'].items() if m.get('MartMovIDs') and m.get('DepartEnum') not in (1,6)}
        default=next((n for n,i in self.targets.items() if i==mid),next(iter(self.targets),''));self.target=tk.StringVar(value=default)
        ttk.Label(body,text='指定武学（名称 / ID 搜索；暗器 / 轻功暂不支持网格范围）').pack(anchor='w');SearchCombo(body,self.target,self.targets).pack(fill='x')
        row=ttk.Frame(body);row.pack(fill='x',pady=10);ttk.Label(row,text='当前武学：'+lib.name(mid)+'    解锁等级').pack(side='left');self.level=tk.StringVar(value='5');ttk.Spinbox(row,from_=1,to=255,textvariable=self.level,width=7).pack(side='left',padx=8)
        self.existing={'新建独立范围':None}|{f'{range_name(lib,i)} · {i}':i for i in lib.tables['Range'] if AREA_START<=i<AREA_END and (set(zip(lib.tables['Range'][i]['PosXs'],lib.tables['Range'][i]['PosYs']))<=CELLS or len(lib.tables['Range'][i]['PosXs'])==135)}
        self.choice=tk.StringVar(value='新建独立范围')
        rangebar=ttk.Frame(body);rangebar.pack(fill='x');ttk.Label(rangebar,text='已有命名范围（修改将同步所有引用）').pack(side='left')
        ttk.Button(rangebar,text='以所选范围新建副本',command=lambda:self.choice.set('新建独立范围')).pack(side='right')
        SearchCombo(body,self.choice,self.existing).pack(fill='x');self.choice.trace_add('write',self.load)
        self.name=tk.StringVar(value='自定义范围');ttk.Label(body,text='范围名称').pack(anchor='w',pady=(8,2));ttk.Entry(body,textvariable=self.name).pack(fill='x');self.name.trace_add('write',self.preview)
        ttk.Label(body,text='以“人物中心”为原点，右方为默认攻击方向。点选 / 拖选添加或取消；战斗中按选点方向旋转为上、下、左、右，施放距离保持原值。',style='Sub.TLabel',wraplength=760).pack(fill='x',pady=8)
        self.loading=False;self.grid=AreaGrid(body,self.changed);self.grid.pack(fill='both',expand=True)
        self.note=tk.StringVar();ttk.Label(body,textvariable=self.note,style='Preview.TLabel',padding=10,wraplength=740).pack(fill='x',pady=8);self.target.trace_add('write',self.target_changed);self.target_changed()
        if ref:
            self.target.set(next(k for k,v in self.targets.items() if v==ref['target']))
            self.choice.set(next(k for k,v in self.existing.items() if v==ref['range']))
            self.level.set(str(lib.tables['Martial'][mid]['UnlockLvls'][ref['index']]))
        self.grab_set();self.wait_window()
    def preview(self,*_):
        if not hasattr(self,'note'):return
        target=self.targets.get(self.target.get());self.note.set('修改后效果：改变《'+(self.lib.name(target) if target is not None else '请选择武学')+'》技能范围为'+display_name(self.name.get())+'\n'+self.usage_note()+'保存并重启游戏后生效。')
    def usage_note(self):
        rid=self.existing.get(self.choice.get());uses=references(self.lib,rid=rid) if rid is not None else []
        local=references(self.lib,source=self.mid,target=self.targets.get(self.target.get()))
        dormant='当前词条已停用；修改名称和格子不会自动启用。' if len(local)==1 and not local[0]['enabled'] else ''
        return dormant+('将同步 '+str(len(uses))+' 条引用：'+ '、'.join(dict.fromkeys(self.lib.name(r['source']) for r in uses))+'。' if uses else '新建独立范围。')
    def target_changed(self,*_):
        if self.loading:self.preview();return
        refs=references(self.lib,source=self.mid,target=self.targets.get(self.target.get()))
        if len(refs)==1:
            ref=refs[0];key=next((k for k,v in self.existing.items() if v==ref['range']),None)
            if key:self.choice.set(key);self.level.set(str(self.lib.tables['Martial'][self.mid]['UnlockLvls'][ref['index']]))
        self.preview()
    def changed(self):
        self.preview()
    def load(self,*_):
        rid=self.existing.get(self.choice.get())
        self.edit_button.configure(state='normal' if rid is not None else 'disabled')
        if rid is None:self.preview();return
        r=self.lib.tables['Range'][rid];positions=set(zip(r['PosXs'],r['PosYs']))
        self.loading=True;self.name.set(range_name(self.lib,rid));self.grid.set_cells(CELLS if not positions<=CELLS else positions,not positions<=CELLS)
        refs=references(self.lib,rid=rid,source=self.mid) or references(self.lib,rid=rid)
        targets={r['target'] for r in refs}
        if len(targets)==1:
            target=next(iter(targets));key=next((k for k,v in self.targets.items() if v==target),None)
            if key and self.target.get()!=key:self.target.set(key)
        local=[r for r in refs if r['source']==self.mid]
        if len(local)==1:self.level.set(str(self.lib.tables['Martial'][self.mid]['UnlockLvls'][local[0]['index']]))
        self.loading=False;self.preview()
    def accept(self):
        try:
            target=self.targets.get(self.target.get())
            if target is None:raise ValueError('请选择指定武学')
            with self.lib.edit():
                rid=self.existing.get(self.choice.get())
                if rid is None:rid=create_range(self.lib,self.name.get(),self.grid.cells,self.grid.fullscreen)
                else:update_range(self.lib,rid,self.name.get(),self.grid.cells,self.grid.fullscreen)
                if not self.grid.cells:raise ValueError('范围不能为空')
                self.result=apply_clause(self.lib,self.mid,target,rid,int(self.level.get()))
            self.destroy()
        except Exception as e:self.result=None;messagebox.showerror('无法新增范围词条',str(e),parent=self)

    def edit_selected(self):
        try:
            rid=self.existing.get(self.choice.get())
            if rid is None:raise ValueError('请先从列表选择已有命名范围')
            with self.lib.edit():update_range(self.lib,rid,self.name.get(),self.grid.cells,self.grid.fullscreen)
            local=references(self.lib,rid=rid,source=self.mid)
            self.result=local[0]['index'] if local else -1
            self.destroy()
        except Exception as e:self.result=None;messagebox.showerror('无法修改范围',str(e),parent=self)

class RangeManager(tk.Toplevel):
    """Show all providers, including clauses on other martial arts and dormant rows."""
    def __init__(self,parent,lib,mid,on_change=lambda:None):
        super().__init__(parent);self.lib=lib;self.mid=mid;self.on_change=on_change
        self.title('管理技能范围词条');self.geometry('1080x560');self.minsize(820,460);self.transient(parent.winfo_toplevel())
        footer=ttk.Frame(self,padding=(16,0,16,12));footer.pack(side='bottom',fill='x')
        body=ttk.Frame(self,padding=16);body.pack(fill='both',expand=True)
        ttk.Label(body,text='技能范围词条 · 清除效果',font=('Microsoft YaHei UI',16,'bold')).pack(anchor='w')
        ttk.Label(body,text='列出所有武学提供的范围词条，与当前武学相关的排在前面。清除会移除提供功法上的范围词条；命名网格保留供以后复用。点击主界面的“保存武学修改”后生效。',wraplength=1000,style='Sub.TLabel').pack(fill='x',pady=8)
        self.query=tk.StringVar();search=ttk.Frame(body);search.pack(fill='x',pady=6)
        ttk.Label(search,text='搜索名称 / ID').pack(side='left');ttk.Entry(search,textvariable=self.query).pack(side='left',fill='x',expand=True,padx=8)
        ttk.Button(search,text='清空',command=lambda:self.query.set('')).pack(side='left')
        columns=('status','source','target','name','level');frame=ttk.Frame(body);frame.pack(fill='both',expand=True)
        self.tree=ttk.Treeview(frame,columns=columns,show='headings',selectmode='browse',height=6)
        for key,title,width in zip(columns,('状态','提供词条的武学','被改变范围的武学','范围名称 / ID','解锁等级'),(85,240,230,220,80)):
            self.tree.heading(key,text=title);self.tree.column(key,width=width,minwidth=60)
        scroll=ttk.Scrollbar(frame,orient='vertical',command=self.tree.yview);self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y');self.tree.pack(fill='both',expand=True)
        self.tree.tag_configure('enabled',foreground='#17633c');self.tree.tag_configure('disabled',foreground='#65758b')
        self.note=tk.StringVar();ttk.Label(footer,textvariable=self.note,wraplength=1000,style='Preview.TLabel',padding=10).pack(fill='x',pady=8)
        bar=ttk.Frame(footer);bar.pack(fill='x')
        self.clear_button=ttk.Button(bar,text='清除所选范围词条',command=self.clear_selected);self.clear_button.pack(side='left')
        self.clear_all_button=ttk.Button(bar,text='清除此目标全部范围词条',command=self.clear_all_target);self.clear_all_button.pack(side='left',padx=8)
        ttk.Button(bar,text='修改名称 / 格子 / 等级',command=self.edit_selected).pack(side='left',padx=8)
        ttk.Button(bar,text='关闭',command=self.destroy).pack(side='right')
        self.tree.bind('<<TreeviewSelect>>',self.selection_changed);self.tree.bind('<Double-1>',lambda e:self.edit_selected())
        self.query.trace_add('write',lambda *_:self.refresh());self.refresh();self.grab_set();self.wait_window()
    def refresh(self,focus=None):
        selection=self.tree.selection();focus=focus or (selection[0] if selection else None)
        self.tree.delete(*self.tree.get_children());self.refs={};query=self.query.get().strip().casefold()
        refs=references(self.lib)
        for ref in sorted(refs,key=lambda r:(not (r['source']==self.mid or r['target']==self.mid),r['source'],r['index'],r['slot'])):
            values=('已启用' if ref['enabled'] else '旧版停用记录',self.lib.name(ref['source'])+' · '+str(ref['source']),self.lib.name(ref['target'])+' · '+str(ref['target']),range_name(self.lib,ref['range'])+' · '+str(ref['range']),str(self.lib.tables['Martial'][ref['source']]['UnlockLvls'][ref['index']])+'级')
            if query and query not in ' '.join(values).casefold():continue
            iid=f"{ref['source']}:{ref['index']}:{ref['slot']}";self.refs[iid]=ref
            self.tree.insert('','end',iid=iid,values=values,tags=('enabled' if ref['enabled'] else 'disabled',))
        if focus in self.refs:self.tree.selection_set(focus);self.tree.see(focus)
        elif self.refs:self.tree.selection_set(next(iter(self.refs)))
        self.selection_changed()
    def selected(self):
        selection=self.tree.selection();return self.refs.get(selection[0]) if selection else None
    def selection_changed(self,*_):
        ref=self.selected()
        for button in (self.clear_button,self.clear_all_button):button.configure(state='normal' if ref else 'disabled')
        if not ref:self.note.set('暂无匹配的范围词条；可在“新增词条 / 作用范围”中创建。');return
        others=[r for r in references(self.lib,target=ref['target']) if (r['source'],r['index'],r['slot'])!=(ref['source'],ref['index'],ref['slot'])]
        self.note.set('清除所选词条：移除“'+self.lib.name(ref['source'])+'”上改变“'+self.lib.name(ref['target'])+'”范围的效果。'+('此目标另有 '+str(len(others))+' 条记录；完全恢复请用“清除此目标全部范围词条”。' if others else '')+'旧版停用记录也可清除；保存后重启游戏。')
    def clear_selected(self):
        ref=self.selected()
        if not ref:return
        try:
            with self.lib.edit():clear_clause(self.lib,ref['source'],ref['index'],ref['slot'])
            self.refresh();self.on_change()
        except Exception as e:messagebox.showerror('无法清除范围词条',str(e),parent=self)
    def clear_all_target(self):
        ref=self.selected()
        if not ref:return
        try:
            with self.lib.edit():clear_target(self.lib,ref['target'])
            self.refresh();self.on_change()
        except Exception as e:messagebox.showerror('无法清除目标范围词条',str(e),parent=self)
    def edit_selected(self):
        ref=self.selected()
        if not ref:return
        dialog=RangeDialog(self,self.lib,ref['source'],ref=ref)
        self.grab_set()
        if dialog.result is not None:self.refresh();self.on_change()


class ClauseMenu(tk.Toplevel):
    def __init__(self,parent,lib,mid):
        super().__init__(parent);self.result=None;self.kind=None;self.title('新增词条');self.transient(parent.winfo_toplevel());self.resizable(False,False)
        ttk.Label(self,text='请选择新增内容',font=('Microsoft YaHei UI',14,'bold'),padding=18).pack(anchor='w')
        def choose(kind):self.kind=kind;self.destroy()
        ttk.Button(self,text='新增武学筛选范围（类别 / 品质 / 门派）',command=lambda:choose('scope'),padding=12).pack(fill='x',padx=18,pady=6)
        ttk.Button(self,text='新增 / 编辑技能作用范围（命名 / 5×8 网格）',command=lambda:choose('area'),padding=12).pack(fill='x',padx=18,pady=6)
        ttk.Label(self,text='筛选范围决定词条加成哪些武学；技能作用范围决定一次施放影响哪些格子。',wraplength=470,style='Sub.TLabel',padding=18).pack(fill='x')
        self.grab_set();self.wait_window()
        if self.kind=='scope':
            from clause_ui import ScopeDialog
            self.result=ScopeDialog(parent,lib,mid).result
        elif self.kind=='area':self.result=RangeDialog(parent,lib,mid).result
