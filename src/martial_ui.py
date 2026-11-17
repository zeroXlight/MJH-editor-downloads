"""Native Tk martial authoring page; drafts remain in memory until save."""
import copy, io, json, queue, threading
from decimal import Decimal
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
from martial_editor import MartialLibrary, DEPARTS, RANKS, SECTIONS
from martial_preview import filter_choices, describe_effects, stage_description, martial_report
from engine import ensure_closed, transaction
from engine import Save
from warehouse_books import generate_book

class SearchCombo(ttk.Frame):
    """Search separately from the chosen value, so typing cannot overwrite a selection."""
    def __init__(self,parent,variable,values):
        super().__init__(parent);self.options=list(values);self.query=tk.StringVar();self.count=tk.StringVar()
        bar=ttk.Frame(self);bar.pack(fill='x')
        ttk.Label(bar,text='搜索').pack(side='left')
        ttk.Entry(bar,textvariable=self.query,width=18).pack(side='left',fill='x',expand=True,padx=5)
        ttk.Button(bar,text='清空',width=5,command=lambda:self.query.set('')).pack(side='left')
        ttk.Label(bar,textvariable=self.count,style='Sub.TLabel').pack(side='left',padx=4)
        self.box=ttk.Combobox(self,textvariable=variable,values=self.options,state='readonly');self.box.pack(fill='x',pady=(3,0))
        self.query.trace_add('write',self.search);self.search()
    def search(self,*_):
        words=self.query.get().strip().casefold().split()
        matches=[v for v in self.options if all(q in v.casefold() for q in words)]
        self.box['values']=matches;self.count.set(f'{len(matches)} 项')
    def set_values(self,values):self.options=list(values);self.search()

class ValuesDialog(tk.Toplevel):
    def __init__(self,parent,title,items,note=''):
        super().__init__(parent);self.title(title);self.result=None;self.transient(parent.winfo_toplevel())
        self.geometry('780x600');self.minsize(650,440)
        ttk.Label(self,text=note,wraplength=730,padding=14).pack(fill='x')
        wrap=ttk.Frame(self);wrap.pack(fill='both',expand=True,padx=14)
        canvas=tk.Canvas(wrap,highlightthickness=0);canvas.pack(side='left',fill='both',expand=True)
        scroll=ttk.Scrollbar(wrap,command=canvas.yview);scroll.pack(side='right',fill='y');canvas.configure(yscrollcommand=scroll.set)
        body=ttk.Frame(canvas);win=canvas.create_window((0,0),window=body,anchor='nw')
        body.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>',lambda e:canvas.itemconfigure(win,width=e.width))
        self.variables={};self.items=items
        for key,label,value,kind in items:
            row=ttk.Frame(body);row.pack(fill='x',pady=4)
            ttk.Label(row,text=label,width=43,wraplength=400).pack(side='left')
            var=tk.StringVar(value=value);self.variables[key]=var;ttk.Entry(row,textvariable=var,width=25).pack(side='left',fill='x',expand=True)
        bar=ttk.Frame(self,padding=14);bar.pack(fill='x')
        ttk.Button(bar,text='加入草稿',style='Primary.TButton',command=self.accept).pack(side='right')
        ttk.Button(bar,text='取消',command=self.destroy).pack(side='right',padx=8)
        self.grab_set();self.wait_window()
    def accept(self):
        try:
            result={}
            for key,label,value,kind in self.items:
                text=self.variables[key].get()
                if kind=='text':result[key]=text
                elif kind=='float':result[key]=float(text)
                elif kind=='list':result[key]=[int(x.strip()) for x in text.replace('，',',').split(',') if x.strip()]
                elif kind=='percent':
                    raw=Decimal(text.rstrip('%'))*100
                    if raw!=raw.to_integral_value():raise ValueError('百分比最多支持两位小数')
                    result[key]=int(raw)
                else:result[key]=int(text)
            self.result=result;self.destroy()
        except Exception as e:messagebox.showerror('输入有误',str(e),parent=self)

class StageDialog(tk.Toplevel):
    """Edit both effects of a stage, using existing game rows as templates."""
    def __init__(self,parent,lib,mid,selected=None):
        super().__init__(parent);self.title('修改阶段与效果' if selected else '新增阶段与效果')
        self.result=None;self.lib=lib;self.mid=mid;self.transient(parent.winfo_toplevel())
        self.geometry(f'{min(1060,self.winfo_screenwidth()-80)}x{min(850,self.winfo_screenheight()-120)}');self.minsize(800,560)
        self.key=selected[0] if selected else 'UnlockClauses'
        cid=lib.tables['Martial'][mid][self.key][selected[1]] if selected else next(iter(lib.tables['MartialItem']))
        self.source=cid;self.row=copy.deepcopy(lib.tables['MartialItem'][cid]);self.slots=[]
        self.filling=True;self.filters=filter_choices(lib,mid);self.filter_boxes=[]
        bar=ttk.Frame(self,padding=12);bar.pack(side='bottom',fill='x')
        ttk.Button(bar,text='加入草稿',style='Primary.TButton',command=self.accept).pack(side='right')
        ttk.Button(bar,text='取消',command=self.destroy).pack(side='right',padx=8)
        preview=ttk.LabelFrame(self,text='修改后效果（实时预览）',padding=8);preview.pack(side='bottom',fill='x',padx=12)
        self.preview=tk.Text(preview,height=4,wrap='word',font=('Microsoft YaHei UI',10),state='disabled');self.preview.pack(fill='x')
        wrap=ttk.Frame(self);wrap.pack(fill='both',expand=True)
        canvas=tk.Canvas(wrap,highlightthickness=0);canvas.pack(side='left',fill='both',expand=True)
        scrollbar=ttk.Scrollbar(wrap,command=canvas.yview);scrollbar.pack(side='right',fill='y');canvas.configure(yscrollcommand=scrollbar.set)
        frame=ttk.Frame(canvas,padding=16);win=canvas.create_window((0,0),window=frame,anchor='nw')
        frame.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>',lambda e:canvas.itemconfigure(win,width=e.width))
        ttk.Label(frame,text='每个阶段支持两项效果；可选原版模板，也可直接选择属性或技能。重复阶段和相同解锁等级均可保留。',wraplength=950).pack(anchor='w',pady=(0,10))
        line=ttk.Frame(frame);line.pack(fill='x')
        self.section=tk.StringVar(value=next(n for n,k in SECTIONS.items() if k==self.key))
        ttk.Label(line,text='阶段类别').pack(side='left')
        box=ttk.Combobox(line,textvariable=self.section,values=list(SECTIONS),state='disabled' if selected else 'readonly',width=10);box.pack(side='left',padx=8)
        self.level=tk.StringVar(value=lib.tables['Martial'][mid]['UnlockLvls'][selected[1]] if selected and self.key=='UnlockClauses' else 5)
        ttk.Label(line,text='解锁等级（仅解锁阶段）').pack(side='left',padx=(18,8))
        ttk.Spinbox(line,from_=0,to=1000,textvariable=self.level,width=8).pack(side='left')
        self.templates={}
        for m in lib.tables['Martial'].values():
            for section,key in SECTIONS.items():
                for index,ref in enumerate(m.get(key,[])):
                    label=f'{lib.name(m["BaseID"])} · {section} {index+1} · {ref}'
                    self.templates[label]=ref
        searchline=ttk.Frame(frame);searchline.pack(fill='x',pady=(14,5))
        self.query=tk.StringVar();ttk.Label(searchline,text='搜索阶段模板').pack(side='left')
        ttk.Entry(searchline,textvariable=self.query).pack(side='left',fill='x',expand=True,padx=8)
        self.template=tk.StringVar();self.template_box=ttk.Combobox(frame,textvariable=self.template,state='readonly');self.template_box.pack(fill='x')
        self.query.trace_add('write',self.search_templates);self.search_templates()
        self.template_box.bind('<<ComboboxSelected>>',self.choose_template)
        attrs={f'{label} · {ident}':int(ident) for ident,label in lib.attr_names.items()};self.attrs=attrs
        skills={f'{lib.text(r.get("NameID",0)) or "技能"} · {sid}':sid for sid,r in lib.tables['Skill'].items()};self.skills=skills
        effects={f'{i} · {lib.labels.get(("MartialItemEffect",i),"无效果")}':i for i in (0,*range(6,18))};self.effects=effects
        columns=ttk.Frame(frame);columns.pack(fill='both',expand=True,pady=14)
        for slot in (1,2):
            group=ttk.LabelFrame(columns,text=f'第 {slot} 项效果',padding=12);group.pack(side='left',fill='both',expand=True,padx=(0,12) if slot==1 else 0)
            variables={}
            for field,label,options in [('kind','效果类型',list(effects)),('attr','属性',list(attrs)),('skill','技能 / 被动效果',list(skills)),('base','基础数值 / 参数 1',None),('growth','成长数值 / 参数 2',None),('filter','作用范围（输入名称搜索，再从列表选择）',list(self.filters)),('grade','品级 / 额外等级',None)]:
                ttk.Label(group,text=label).pack(anchor='w',pady=(6,2));var=tk.StringVar();variables[field]=var
                if field in ('attr','skill','filter'):
                    chooser=SearchCombo(group,var,options);chooser.pack(fill='x')
                    if field=='filter':
                        self.filter_boxes.append(chooser)
                        ttk.Button(group,text='新增作用范围',command=lambda s=slot:self.create_scope(s)).pack(anchor='w',pady=4)
                elif options is not None:ttk.Combobox(group,textvariable=var,values=options,state='readonly').pack(fill='x')
                else:ttk.Entry(group,textvariable=var).pack(fill='x')
            unit=tk.StringVar();variables['unit']=unit;ttk.Label(group,textvariable=unit,wraplength=400,style='Sub.TLabel').pack(anchor='w',pady=8)
            variables['attr'].trace_add('write',lambda *_,s=slot:self.units(s))
            self.slots.append(variables)
        self.condition=tk.StringVar();bottom=ttk.Frame(frame);bottom.pack(fill='x')
        ttk.Label(bottom,text='阶段条件 ID（0 为无条件）').pack(side='left');ttk.Entry(bottom,textvariable=self.condition,width=14).pack(side='left',padx=8)
        ttk.Label(frame,text='百分比属性的基础数值输入百分数（12 = 12%）。每级成长使用游戏成长公式，此处参数不会覆盖每级数值，请回主界面使用“修改每级成长”。其他效果沿用所选模板。',wraplength=950,style='Sub.TLabel').pack(anchor='w',pady=10)
        if not selected:
            default=next((label for label,ref in self.templates.items() if ref in lib.tables['Martial'][mid].get('UnlockClauses',[])),None)
            if default:self.template.set(default);self.source=self.templates[default];self.row=copy.deepcopy(lib.tables['MartialItem'][self.source])
        self.fill()
        for v in self.slots:
            for key,var in v.items():
                if key!='unit':var.trace_add('write',self.update_preview)
        for var in (self.level,self.section,self.condition):var.trace_add('write',self.update_preview)
        self.update_preview();self.grab_set();self.wait_window()
    def filter_id(self,text):
        if text in self.filters:return self.filters[text]
        try:fid=int(text)
        except ValueError:raise ValueError('请从作用范围列表选择，例如“华山外功”；也可输入有效筛选编号')
        if fid and fid not in self.lib.tables['MartialFilter']:raise ValueError(f'筛选编号 {fid} 不存在')
        return fid
    def create_scope(self,slot):
        from clause_ui import ScopeDialog
        dialog=ScopeDialog(self,self.lib,self.mid)
        if dialog.result is None:return
        self.filters=filter_choices(self.lib,self.mid)
        for box in self.filter_boxes:box.set_values(self.filters)
        self.slots[slot-1]['filter'].set(next(k for k,v in self.filters.items() if v==dialog.result))
        self.update_preview()
    def update_preview(self,*_):
        if self.filling:return
        try:
            key,level,row=self.collect()
            text=stage_description(self.lib,self.mid,key,row,level)
        except Exception as e:text='待完成输入：'+str(e)
        self.preview.configure(state='normal');self.preview.delete('1.0','end');self.preview.insert('1.0',text);self.preview.configure(state='disabled')
    def search_templates(self,*_):
        q=self.query.get().strip().casefold();self.template_box['values']=[label for label in self.templates if q in label.casefold()]
    def choose_template(self,e=None):
        self.source=self.templates[self.template.get()];self.row=copy.deepcopy(self.lib.tables['MartialItem'][self.source]);self.fill()
    def percent(self,attr):
        p=self.lib.percent.get(attr,{});return p.get('PerMyriad')==1 and p.get('ShowAsPercent')==1
    def units(self,slot):
        if slot>len(self.slots):return
        v=self.slots[slot-1];attr=self.attrs.get(v['attr'].get(),0)
        v['unit'].set('基础数值单位：%（例如 25 表示 25%）' if self.percent(attr) else '基础数值单位：游戏原值')
    def fill(self):
        self.filling=True
        self.condition.set(self.row.get('CondID',0))
        for slot,v in enumerate(self.slots,1):
            kind=self.row.get('EffectEnum'+str(slot),0);attr=self.row.get('AttrEnum'+str(slot),0);sid=self.row.get('SkillID'+str(slot),0);vals=self.row.get('Effect'+str(slot)+'Value',[])
            v['kind'].set(next((k for k,x in self.effects.items() if x==kind),''));v['attr'].set(next((k for k,x in self.attrs.items() if x==attr),''));v['skill'].set(next((k for k,x in self.skills.items() if x==sid),''))
            base=vals[0] if vals else 0;v['base'].set(str(base/100) if self.percent(attr) else str(base));v['growth'].set(vals[1] if len(vals)>1 else 0)
            fid=self.row.get('MartialFilter'+str(slot),0)
            v['filter'].set(next((label for label,i in self.filters.items() if i==fid),str(fid)));v['grade'].set(self.row.get('Grade'+str(slot),0));self.units(slot)
        self.filling=False;self.update_preview()
    def collect(self):
        key=SECTIONS[self.section.get()];row=copy.deepcopy(self.row);row.pop('BaseID',None);row['CondID']=int(self.condition.get())
        if row['CondID'] and row['CondID'] not in self.lib.tables.get('Condition',{}):
            if row['CondID']!=self.row.get('CondID',0):raise ValueError('条件编号只能沿用模板或设为 0')
        for slot,v in enumerate(self.slots,1):
            n=str(slot);kind=self.effects.get(v['kind'].get())
            if kind is None:raise ValueError('请选择效果类型')
            attr=self.attrs.get(v['attr'].get(),0);sid=self.skills.get(v['skill'].get(),0)
            row['EffectEnum'+n]=kind;row['AttrEnum'+n]=attr if kind in (7,8,9,10,12) else 0
            row['SkillID'+n]=sid if kind in (6,11) else 0
            if not kind:
                row['Effect'+n+'Value']=[];row['MartialFilter'+n]=0;row['Grade'+n]=0;continue
            value=Decimal(v['base'].get().rstrip('%'))*(100 if kind in (7,8,9,10,12) and self.percent(attr) else 1)
            if value!=value.to_integral_value():raise ValueError('数值精度超出游戏支持范围')
            if kind in (7,8,9,10,12):values=[int(value),int(v['growth'].get())]
            elif kind not in (6,11):
                values=list(self.row.get('Effect'+n+'Value',[]))
                if values:
                    values[0]=int(value)
                    if len(values)>1:values[1]=int(v['growth'].get())
                else:values=[int(value),int(v['growth'].get())]
            else:values=[]
            if kind in (7,8,9,10,12) and not self.row.get('Effect'+n+'Value',[]) and self.row.get('Grade'+n,0)>0 and int(v['grade'].get())==self.row.get('Grade'+n) and values==[0,0]:values=[]
            row['Effect'+n+'Value']=values
            row['MartialFilter'+n]=self.filter_id(v['filter'].get());row['Grade'+n]=int(v['grade'].get())
            if row['MartialFilter'+n] and kind in (7,8,9):raise ValueError('角色属性与每级成长不使用武学作用范围；请清除范围或选择“10 · 武学属性”')
            if str(row['MartialFilter'+n]) in self.lib.scope_groups and kind!=10:raise ValueError('内功以外的组合范围请使用“10 · 武学属性”效果')
        row=self.lib.validate_clause(key,row);level=int(self.level.get())
        if not 0<=level<=1000:raise ValueError('解锁等级范围为 0～1000')
        return key,level,row
    def accept(self):
        try:
            key,level,row=self.collect()
            self.result=(key,self.source,level,row);self.destroy()
        except Exception as e:messagebox.showerror('输入有误',str(e),parent=self)

class MartialPage(ttk.Frame):
    def __init__(self,parent,host):
        super().__init__(parent,padding=14);self.host=host;self.library=None;self.current=None;self.setting=False;self.dirty=False
        from cursor_list import CursorList
        self.list_cursor=CursorList();self._list_current=None;self._list_search_job=None;self._list_rendering=False
        self.query=tk.StringVar();self.note=tk.StringVar(value='读取武学配置后，可选中现有武学编辑，或以它为模板新增。')
        self.summary=tk.StringVar(value='尚未读取武学');self.fields={};self.roles_query=tk.StringVar();self.exclusive=[];self.clauses={}
        self.reference_summaries={}
        top=ttk.Frame(self);top.pack(fill='x')
        ttk.Button(top,text='读取武学（缓存优先）',command=self.load).pack(side='left')
        ttk.Button(top,text='以选中武学新增',command=self.create).pack(side='left',padx=8)
        ttk.Button(top,text='秘奥义组合',command=self.open_aoyi).pack(side='left')
        ttk.Button(top,text='保存武学修改',style='Primary.TButton',command=self.save).pack(side='right')
        ttk.Button(top,text='生成秘籍到周目仓库',command=self.generate).pack(side='right',padx=8)
        ttk.Button(top,text='导出配置副本',command=lambda:self.save(export=True)).pack(side='right',padx=8)
        from object_ui import export_selected,import_selected
        from desktop_theme import ToolShelf
        self.tools=ToolShelf(self,'配置导入导出 / 缓存 / 词条与修复工具');self.tools.pack(fill='x')
        tools=self.tools.body
        objectbar=ttk.Frame(tools);objectbar.pack(fill='x',pady=(0,6))
        ttk.Button(objectbar,text='导出所选武学完整配置',command=lambda:export_selected(self.host,'Martial',self)).pack(side='left')
        ttk.Button(objectbar,text='导入武学完整配置',command=lambda:import_selected(self.host,'Martial')).pack(side='left',padx=8)
        from martial_id_repair import open_repair as repair_attack_ids
        ttk.Button(objectbar,text='修复旧武学攻击编号',command=lambda:repair_attack_ids(self.host)).pack(side='left',padx=8)
        ttk.Button(objectbar,text='修复名称显示',command=self.repair_all_names).pack(side='left',padx=8)
        self.cache_note=tk.StringVar(value='首次读取建立本地缓存；游戏或 MOD 有外部改动时，请手动刷新。')
        cachebar=ttk.Frame(tools);cachebar.pack(fill='x',pady=(6,0))
        ttk.Button(cachebar,text='刷新武学缓存',command=lambda:self.load(True)).pack(side='left')
        ttk.Label(cachebar,textvariable=self.cache_note,style='Sub.TLabel',wraplength=1100).pack(side='left',padx=10)
        clausesbar=ttk.Frame(tools);clausesbar.pack(fill='x',pady=(8,0))
        ttk.Button(clausesbar,text='新增词条 / 作用范围',command=self.open_scope).pack(side='left')
        ttk.Button(clausesbar,text='还原游戏基础词条',command=self.restore_base_clauses).pack(side='left',padx=8)
        ttk.Button(clausesbar,text='修复游戏词条显示',command=self.repair_clause_display).pack(side='left',padx=(0,8))
        ttk.Button(clausesbar,text='修复技能实际范围',command=self.repair_actual_ranges).pack(side='left',padx=(0,8))
        ttk.Label(clausesbar,text='还原时保留自建武学、秘奥义和装备。',style='Sub.TLabel').pack(side='left',padx=8)
        ttk.Label(self,textvariable=self.summary,style='Sub.TLabel',wraplength=1250).pack(anchor='w',pady=8)
        split=ttk.Panedwindow(self,orient='horizontal');split.pack(fill='both',expand=True)
        left=ttk.Frame(split,style='Card.TFrame',padding=14);right=ttk.Frame(split,style='Card.TFrame',padding=14);split.add(left,weight=1);split.add(right,weight=3)
        ttk.Label(left,text='武学列表',font=('Microsoft YaHei UI',13,'bold')).pack(anchor='w',pady=(0,12))
        ttk.Entry(left,textvariable=self.query).pack(fill='x');ttk.Label(left,text='搜索武学名称或 ID',style='Sub.TLabel').pack(anchor='w',pady=5)
        self.list=host.make_tree(left,[('name','武学',155),('type','类别',65),('rank','品质',50)],height=14)
        self.list.bind('<<TreeviewSelect>>',self.select)
        from cursor_list import PageBar
        self.list_pages=PageBar(left,self.list_cursor,self.render_list_page);self.list_pages.pack(side='bottom',fill='x',pady=(8,0),before=self.list.master)
        ttk.Label(right,textvariable=self.note,font=('Microsoft YaHei UI',12,'bold'),wraplength=950).pack(anchor='w',pady=(0,8))
        tabs=ttk.Notebook(right);tabs.pack(fill='both',expand=True)
        basic=host.scroll_page(tabs,'基础与类别');effects=host.scroll_page(tabs,'成长 / 解锁 / 数值')
        self.preview_page=ttk.Frame(tabs,padding=12);tabs.add(self.preview_page,text='完整效果预览')
        previewbar=ttk.Frame(self.preview_page);previewbar.pack(fill='x',pady=(0,8))
        ttk.Label(previewbar,text='当前武学的作用范围、解锁等级与修改后效果',font=('Microsoft YaHei UI',11,'bold')).pack(side='left')
        ttk.Button(previewbar,text='导出效果说明',command=self.export_effect_report).pack(side='right')
        self.report_note=tk.StringVar(value='读取武学后显示完整效果。')
        ttk.Label(self.preview_page,textvariable=self.report_note,style='Sub.TLabel',wraplength=850).pack(anchor='w',pady=(0,8))
        reportwrap=ttk.Frame(self.preview_page);reportwrap.pack(fill='both',expand=True)
        self.report_text=tk.Text(reportwrap,wrap='word',font=('Microsoft YaHei UI',10),background='white',foreground='#303133',relief='flat',padx=14,pady=12,state='disabled')
        self.report_text.pack(side='left',fill='both',expand=True)
        reportscroll=ttk.Scrollbar(reportwrap,command=self.report_text.yview);reportscroll.pack(side='right',fill='y');self.report_text.configure(yscrollcommand=reportscroll.set)
        rolepage=ttk.Frame(tabs,padding=10);tabs.add(rolepage,text='秘籍与人物分配')
        animationpage=ttk.Frame(tabs,padding=12);tabs.add(animationpage,text='招式动画模板')
        ttk.Label(animationpage,text='连招模板会保留全部三段招式，可分别选择每段动画。',style='Sub.TLabel',wraplength=840).pack(anchor='w',pady=8)
        self.move_template=tk.StringVar();self.move_box=ttk.Combobox(animationpage,textvariable=self.move_template,state='readonly',width=60);self.move_box.pack(fill='x')
        ttk.Button(animationpage,text='套用招式结构（连招保留三段）',command=self.replace_moves).pack(anchor='w',pady=8)
        self.animation_boxes=[];self.animation_vars=[];self.animation_choices={};self.move_choices={}
        for index in range(3):
            row=ttk.Frame(animationpage);row.pack(fill='x',pady=8)
            ttk.Label(row,text=f'第 {index+1} 段动画',width=14).pack(side='left')
            var=tk.StringVar();box=ttk.Combobox(row,textvariable=var,state='readonly',width=55);box.pack(side='left',fill='x',expand=True)
            self.animation_vars.append(var);self.animation_boxes.append(box)
            var.trace_add('write',self.animation_changed)
        ttk.Button(animationpage,text='动画设置加入草稿',command=self.stage_animation).pack(anchor='e',pady=12)
        ttk.Label(animationpage,text='套用招式结构会替换主动招式的战斗行为；仅选择每段动画则保留当前战斗数值。\n动画、特效及音效沿用现有资源。未配置的第二、第三段保持禁用。',style='Sub.TLabel',wraplength=840).pack(anchor='w',pady=8)
        for key,label,value,kind in [('name','武学名称','','text'),('DepartEnum','武学类别',4,'depart'),('Rank','品质',5,'rank'),
                ('ClanID','所属门派（ID · 名称）',0,'clan'),('LvLimit','修炼上限（级）',30,'int'),('ColdTime','冷却时间（回合）',0,'int'),
                ('MascCoef','阳性系数（实际值）',0,'coefficient'),('FemiCoef','阴性系数（实际值）',0,'coefficient'),
                ('LearnCondition','学习条件（ID · 名称 · 数值）','','list'),('LearnConditionValue','学习条件数值','','list'),
                ('MartialTags','附加标签（ID · 名称）','','list')]:
            row=ttk.Frame(basic);row.pack(fill='x',pady=4);ttk.Label(row,text=label,width=31).pack(side='left')
            var=tk.StringVar(value=value);self.fields[key]=(var,kind)
            if key=='LearnConditionValue':row.pack_forget()
            elif kind=='clan':self.clan_combo=SearchCombo(row,var,['0 · 无所属门派']);self.clan_combo.pack(side='left',fill='x',expand=True)
            elif key in ('LearnCondition','MartialTags'):
                summary=tk.StringVar(value='尚未读取');self.reference_summaries[key]=summary
                ttk.Label(row,textvariable=summary,wraplength=480).pack(side='left',fill='x',expand=True)
                ttk.Button(row,text='选择 / 编辑',command=lambda k=key:self.edit_references(k)).pack(side='right',padx=6)
            elif kind in ('depart','rank'):
                mapping=DEPARTS if kind=='depart' else RANKS
                ttk.Combobox(row,textvariable=var,values=[f'{i} · {s}' for i,s in mapping.items()],state='readonly',width=25).pack(side='left')
            else:ttk.Entry(row,textvariable=var,width=35).pack(side='left',fill='x',expand=True)
            var.trace_add('write',self.form_changed)
        for key in ('LearnCondition','LearnConditionValue','MartialTags'):self.fields[key][0].trace_add('write',self.refresh_references)
        ttk.Label(basic,text='阴 / 阳系数直接填写游戏系数，例如 1.5；学习条件按名称选择并设置对应数值。',style='Sub.TLabel',wraplength=850).pack(anchor='w',pady=6)
        self.description=tk.Text(basic,height=3,wrap='word',font=('Microsoft YaHei UI',10));self.description.pack(fill='x',pady=8)
        self.description.bind('<<Modified>>',self.description_changed)
        iconbar=ttk.LabelFrame(basic,text='武学图标 / 样式',padding=10);iconbar.pack(fill='x',pady=8)
        self.icon_preview=ttk.Label(iconbar);self.icon_preview.pack(side='left',padx=(0,12))
        iconcontrols=ttk.Frame(iconbar);iconcontrols.pack(side='left',fill='x',expand=True)
        self.icon_note=tk.StringVar(value='使用游戏原生图标');ttk.Label(iconcontrols,textvariable=self.icon_note,wraplength=580,style='Sub.TLabel').pack(anchor='w')
        iconbuttons=ttk.Frame(iconcontrols);iconbuttons.pack(anchor='w',pady=8)
        ttk.Button(iconbuttons,text='导入图片并预览',command=self.import_icon).pack(side='left')
        ttk.Button(iconbuttons,text='还原导入前图标',command=self.reset_icon).pack(side='left',padx=8)
        ttk.Label(iconcontrols,text='支持 PNG / JPG / WebP / BMP，保留比例和透明度。保存后应用到本武学全部招式；游戏品质边框和战斗动画沿用现有设置。',wraplength=580,style='Sub.TLabel').pack(anchor='w')
        flags=ttk.Frame(basic);flags.pack(fill='x',pady=6)
        for key,label,default in [('Multistage','多段武学',False),('Toxic','有毒武学',False),('Drop','禁止请教 / 观摩',False),('Display','游戏中显示',True),('AlowEdit','允许游戏内编辑',True),('auto_icon','按品质、类型匹配原生图标',True)]:
            var=tk.BooleanVar(value=default);self.fields[key]=(var,'bool')
            ttk.Checkbutton(flags,text=label,variable=var).pack(anchor='w',pady=2);var.trace_add('write',self.form_changed)
        ttk.Label(flags,text='禁止请教 / 观摩：勾选后不列入 NPC 请教列表；取消后可列入，仍需满足学习条件。',style='Sub.TLabel',wraplength=860).pack(anchor='w',pady=(3,6))
        ttk.Label(basic,text='多段标记用于游戏的多段武学筛选加成；实际攻击次数还需在招式数值中设置。',style='Sub.TLabel',wraplength=860).pack(anchor='w',pady=8)
        ttk.Button(basic,text='当前武学上限设为 30（加入草稿）',command=self.cap_current).pack(anchor='w',pady=6)
        ttk.Button(basic,text='基础设置加入草稿',command=self.stage_basic).pack(anchor='e')
        ttk.Label(effects,text='百分比直接输入百分数；完整配置与适用性提示可在“完整效果预览”中查看。',style='Sub.TLabel',wraplength=860).pack(side='bottom',anchor='w',pady=(8,0))
        rangebar=ttk.Frame(effects);rangebar.pack(fill='x',pady=(0,6))
        ttk.Button(rangebar,text='管理范围词条（清除效果）',command=self.manage_ranges).pack(side='left')
        self.range_note=tk.StringVar();ttk.Label(rangebar,textvariable=self.range_note,style='Sub.TLabel').pack(side='left',padx=10)
        controls=ttk.Frame(effects);controls.pack(side='bottom',fill='x')
        self.clause_tree=host.make_tree(effects,[('level','阶段',75),('scope','作用范围',155),('effect','效果',185),('value','数值 / 说明',330)],height=7)
        self.clause_detail=tk.StringVar(value='选择阶段查看完整效果；全部阶段可在“完整效果预览”中查看。')
        ttk.Label(controls,textvariable=self.clause_detail,wraplength=860,style='Preview.TLabel',padding=8).pack(fill='x',pady=(6,0))
        self.clause_tree.bind('<<TreeviewSelect>>',self.show_clause_detail)
        bar=ttk.Frame(controls);bar.pack(fill='x',pady=8)
        ttk.Button(bar,text='修改条目数值',command=self.edit_clause).pack(side='left')
        ttk.Button(bar,text='修改解锁等级',command=self.edit_level).pack(side='left',padx=6)
        ttk.Button(bar,text='招式 / 战斗参数',command=self.edit_skill).pack(side='left')
        ttk.Button(bar,text='特殊状态参数',command=self.edit_state).pack(side='left',padx=6)
        ttk.Button(bar,text='修改每级成长',command=self.edit_growth).pack(side='left')
        stagebar=ttk.Frame(controls);stagebar.pack(fill='x',pady=(0,8))
        for label,command in [('新增阶段',self.add_stage),('修改阶段 / 效果',self.edit_stage),('复制阶段',self.copy_stage),('删除阶段',self.remove_stage),('上移',lambda:self.move_stage(-1)),('下移',lambda:self.move_stage(1))]:
            ttk.Button(stagebar,text=label,command=command).pack(side='left',padx=(0,5))
        checks=ttk.Frame(controls);checks.pack(anchor='w',pady=(0,4))
        ttk.Button(checks,text='修复名称 / 说明 / 引用',command=self.repair_skills).pack(side='left')
        ttk.Button(checks,text='校验效果适用性',command=self.audit_effects).pack(side='left',padx=6)
        ttk.Button(checks,text='适配逐次威力系数',command=self.adapt_effects).pack(side='left')
        conversions=ttk.Frame(controls);conversions.pack(anchor='w',pady=(2,6))
        ttk.Button(conversions,text='改为自身增益',command=self.convert_self_buff).pack(side='left')
        ttk.Button(conversions,text='改为最终伤害附加百分比',command=self.convert_final_damage).pack(side='left',padx=6)
        ttk.Button(conversions,text='新增每级成长',command=self.add_growth).pack(side='left')
        self.clause_tree.bind('<Double-1>',lambda e:self.edit_clause())
        booksbar=ttk.Frame(rolepage);booksbar.pack(fill='x')
        for key,label in [('book','有可用秘籍（同时配置残章）'),('CouldCopy','允许抄录秘籍')]:
            var=tk.BooleanVar();self.fields[key]=(var,'bool');ttk.Checkbutton(booksbar,text=label,variable=var).pack(side='left',padx=(0,15));var.trace_add('write',self.form_changed)
        randomvar=tk.BooleanVar();self.fields['random_book']=(randomvar,'bool')
        ttk.Checkbutton(rolepage,text='秘籍加入随机获取池（神秘商人 / 日常宝箱）',variable=randomvar).pack(anchor='w',pady=(8,2));randomvar.trace_add('write',self.form_changed)
        ttk.Label(rolepage,text='沿用游戏原有秘籍品质范围、难度和概率；只在含随机秘籍的商品或宝箱中有机会出现。启用时自动配置秘籍并取消“禁止请教 / 观摩”。勾选后加入草稿，再保存武学修改。',style='Sub.TLabel',wraplength=860).pack(anchor='w',pady=8)
        self.role_note=tk.StringVar(value='未设置专属人物');ttk.Label(rolepage,textvariable=self.role_note,wraplength=860).pack(anchor='w')
        rolebar=ttk.Frame(rolepage);rolebar.pack(fill='x',pady=8)
        ttk.Entry(rolebar,textvariable=self.roles_query).pack(side='left',fill='x',expand=True)
        self.role_level=tk.StringVar(value='1');ttk.Label(rolebar,text='初始等级').pack(side='left',padx=8)
        ttk.Spinbox(rolebar,from_=1,to=1000,textvariable=self.role_level,width=6).pack(side='left')
        self.role_tree=host.make_tree(rolepage,[('name','人物 / 配置 ID',200),('city','初始城市 ID',90),('owned','当前武学初始等级',140)],height=6)
        self.role_tree.configure(selectmode='extended')
        bar=ttk.Frame(rolepage);bar.pack(fill='x',pady=8)
        for label,command in [('分配给选中人物',self.assign),('移除初始分配',lambda:self.assign(False)),('设为专属人物',self.set_exclusive),('取消专属',self.clear_exclusive)]:
            ttk.Button(bar,text=label,command=command).pack(side='left',padx=(0,5))
        ttk.Label(rolepage,text='支持多选人物。专属列表与初始分配独立设置。初始配置在新周目或之后生成的人物上生效；现有存档中的人物不会自动重新初始化。',style='Sub.TLabel',wraplength=860).pack(anchor='w',pady=5)
        self.progress=ttk.Progressbar(self,mode='indeterminate');self.progress.pack(fill='x',pady=(10,0))
        self.query.trace_add('write',lambda *_:self.schedule_list_search());self.roles_query.trace_add('write',lambda *_:self.refresh_roles())

    def form_changed(self,*_):
        if not self.setting and self.current is not None:self.dirty=True
    def refresh_references(self,*_):
        if not self.library:return
        from martial_forms import parse_ids,references_text
        try:
            ids=parse_ids(self.fields['LearnCondition'][0].get());values=parse_ids(self.fields['LearnConditionValue'][0].get())
            self.reference_summaries['LearnCondition'].set(references_text(self.library,'LearnCondition',ids,values))
            self.reference_summaries['MartialTags'].set(references_text(self.library,'MartialTags',parse_ids(self.fields['MartialTags'][0].get())))
        except ValueError:pass
    def edit_references(self,key):
        if not self.available():return
        from martial_forms import ReferenceDialog,parse_ids
        ids=parse_ids(self.fields[key][0].get());values=parse_ids(self.fields['LearnConditionValue'][0].get()) if key=='LearnCondition' else None
        d=ReferenceDialog(self,self.library,key,ids,values)
        if d.result is None:return
        self.fields[key][0].set(','.join(map(str,d.result[0])))
        if key=='LearnCondition':self.fields['LearnConditionValue'][0].set(','.join(map(str,d.result[1])))
        self.refresh_references()
    def animation_changed(self,*_):
        if not self.setting and self.current is not None:self.animation_dirty=True
    def description_changed(self,e=None):
        if self.description.edit_modified():self.form_changed();self.description.edit_modified(False)
    def has_changes(self):return self.dirty or getattr(self,'animation_dirty',False) or bool(self.library and self.library.modified())
    def open_scope(self):
        if not self.available():return
        from range_ui import ClauseMenu
        d=ClauseMenu(self,self.library,self.current)
        if d.result is not None:
            if d.kind=='area':self.stage_done('UnlockClauses',d.result)
            self.host.status.set('新增范围已加入草稿，请点击“保存武学修改”应用。')
            self.refresh_list()
    def repair_actual_ranges(self):
        if not self.available():return
        if self.has_changes() or self.host.drafts or self.host.effects:
            self.host.error(ValueError('请先保存或撤销草稿，再修复技能实际范围'));return
        try:
            ensure_closed()
            if not self.host.catalog.supported:raise ValueError('游戏程序版本不同，配置写入已禁用')
        except Exception as e:self.host.error(e);return
        from martial_ranges import repair_bindings,references
        lib=self.library
        def work():
            with lib.edit():
                count=repair_bindings(lib)
                # Synchronize native/client/JSON and compile the hit-grid registry.
                for ref in references(lib):
                    sid=ref['skill'];lib.set('Skill',sid,{'SkillTriggers':lib.tables['Skill'][sid]['SkillTriggers']})
                if not references(lib):return 0,None
                payloads,originals=lib.plan();ensure_closed()
                return count,transaction(lib.root,payloads,originals,'修复技能实际范围')
        def finish(result):
            count,backup=result;self.reset();self.host.reload()
            self.host.status.set('技能实际范围已修复，请完全重启游戏。' if backup else '当前没有自定义技能范围词条。')
            messagebox.showinfo('技能范围修复',('已重新安装以人物为中心的实际命中范围，并同步预览和方向选择。\n兼容修复旧引用 '+str(count)+' 条；原有范围名称、格子、解锁等级保持不变。\n范围仅在提供词条的武学已装备且等级达标时生效；原武学施法距离保持不变。\n请完全重启游戏后重新进入战斗。\n\n备份：'+str(backup)) if backup else '当前没有自定义技能范围词条。',parent=self)
        self.worker('正在校验、备份并修复技能实际范围…',work,finish)

    def repair_clause_display(self):
        if not self.available():return
        if self.has_changes() or self.host.drafts or self.host.effects:
            self.host.error(ValueError('请先保存或撤销草稿，再修复游戏词条显示'));return
        try:
            ensure_closed()
            if not self.host.catalog.supported:raise ValueError('游戏程序版本不同，配置写入已禁用')
        except Exception as e:self.host.error(e);return
        from martial_display import patch_client
        from client_config import Assets
        lib=self.library
        def work():
            path=lib.assets_path;before=lib.originals[path];a=Assets(before)
            updated=a.replace_script('MartialDataManager.lua',patch_client(a.script('MartialDataManager.lua'),lib))
            # Recheck every config snapshot used to generate the display text.
            for p,raw in lib.originals.items():
                if (p.read_bytes() if p.exists() else None)!=raw:raise ValueError('配置已变化，请重新读取')
            return transaction(lib.root,{path:updated},{path:before},'修复游戏词条显示')
        def finish(backup):
            self.reset();self.host.reload()
            self.host.status.set('游戏词条显示修复完成，请完全重启游戏。')
            messagebox.showinfo('显示修复完成','已更新新增/修改词条的作用范围、名称和解锁颜色显示。\n等级不足或附加条件未满足时仍显示灰色。\n\n请完全退出并重启游戏。备份：'+str(backup or '当前已是最新显示配置'),parent=self)
        self.worker('正在备份并修复游戏词条名称与颜色…',work,finish)
    def restore_base_clauses(self):
        if not self.available():return
        if self.has_changes() or self.host.drafts or self.host.effects:
            self.host.error(ValueError('请先保存或撤销装备、武学草稿，再还原基础词条'));return
        try:
            ensure_closed()
            if not self.host.catalog.supported:raise ValueError('游戏程序版本不同，配置写入已禁用')
        except Exception as e:self.host.error(e);return
        from clause_restore import plan_restore,apply_restore
        lib=self.library
        def planned(result):
            payloads,originals,summary=result
            if not any(data!=originals.get(p) for p,data in payloads.items()):
                messagebox.showinfo('基础词条检查', '当前没有需要还原的词条。',parent=self);return
            from clause_ui import RestoreConfirm
            d=RestoreConfirm(self,summary)
            if not d.result:return
            def finish(backup):
                self.reset();self.host.reload();self.host.refresh_caps()
                self.host.status.set(f'游戏基础词条已还原。备份：{backup}')
                messagebox.showinfo('还原完成',summary+'\n\n备份：'+str(backup),parent=self)
            self.worker('正在备份并还原游戏基础词条…',lambda:apply_restore(lib,result),finish)
        self.worker('正在检查基础词条、模板与引用…',lambda:plan_restore(lib),planned)
    def open_aoyi(self):
        if self.host.busy:return
        if not self.library or Path(self.host.game_path.get()).resolve()!=self.library.root:
            self.host.error(ValueError('请先读取武学配置'));return
        if getattr(self,'animation_dirty',False) and not self.stage_animation():return
        if self.dirty and not self.stage_basic():return
        from aoyi_ui import AoyiDialog
        AoyiDialog(self)
    def combo_done(self,mid):
        self.query.set('');self.refresh_list();self.focus_martial(mid)
        self.host.status.set('秘奥义组合已加入草稿，请点击“保存武学修改”应用。')
    def repair_all_names(self):
        if self.host.busy:return
        if not self.library or Path(self.host.game_path.get()).resolve()!=self.library.root:
            self.host.error(ValueError('请先读取武学配置'));return
        try:
            from language_routing import stage_repairs
            count=stage_repairs(self.library)
            self.refresh_list()
            self.host.status.set(f'名称分表检查完成：{count} 条修复已加入草稿。')
            messagebox.showinfo('名称显示修复',f'已检查全部自建武学、秘奥义的名称和说明，发现 {count} 条语言分表错误。\n'+('修复已加入草稿，请点击“保存武学修改”，自动备份后应用，再重启游戏。\n原名称编号、武学等级和组合条件保持不变。' if count else '当前配置没有发现语言分表错放。若刚保存配置，请完全退出并重启游戏后再检查。'),parent=self)
        except Exception as e:self.host.error(e)
    def reset(self):
        if self._list_search_job:self.after_cancel(self._list_search_job);self._list_search_job=None
        self.list_cursor.update([]);self.list_cursor.filter();self.list_pages.sync();self._list_current=None
        self.library=None;self.current=None;self.dirty=False;self.animation_dirty=False;self.list.delete(*self.list.get_children());self.clause_tree.delete(*self.clause_tree.get_children());self.role_tree.delete(*self.role_tree.get_children());self.summary.set('目录已更新，请读取武学配置');self.note.set('尚未选择武学')
        self.clauses={};self.clause_detail.set('尚未选择武学');self.set_report('尚未选择武学')
    def available(self):
        if self.host.busy:return False
        if not self.library or self.current is None:self.host.error(ValueError('请先读取并选择武学'));return False
        if Path(self.host.game_path.get()).resolve()!=self.library.root:self.host.error(ValueError('目录已变化，请重新读取'));return False
        return True
    def worker(self,action,work,finish):
        self.host.busy=True;self.progress.start(15);self.host.status.set(action);disabled=[]
        def lock(w):
            if isinstance(w,(ttk.Button,ttk.Entry,ttk.Spinbox,ttk.Combobox,ttk.Checkbutton)):
                disabled.append((w,w.cget('state')));w.configure(state='disabled')
            for c in w.winfo_children():lock(c)
        lock(self.host);result=queue.Queue()
        def run():
            try:result.put((True,work()))
            except Exception as e:result.put((False,e))
        threading.Thread(target=run,daemon=True).start()
        def poll():
            try:ok,value=result.get_nowait()
            except queue.Empty:self.after(100,poll);return
            self.host.busy=False;self.progress.stop()
            for w,state in disabled:
                if w.winfo_exists():w.configure(state=state)
            if ok:finish(value)
            else:self.host.error(value);self.host.status.set('操作未完成：'+str(value))
        self.after(100,poll)
    def load(self,force_refresh=False):
        if self.host.busy:return
        if self.has_changes() and not messagebox.askyesno('未保存的武学修改','重新读取会丢弃武学草稿，继续？',parent=self):return
        if not self.host.catalog or Path(self.host.game_path.get()).resolve()!=self.host.catalog.root:self.host.error(ValueError('请先读取正确的游戏目录'));return
        root=self.host.catalog.root
        def finish(lib):
            self.library=lib;self.current=None;self._list_current=None;self.list_cursor.first();self.dirty=False;self.refresh_list();self.refresh_roles()
            self.focus_martial(11911)
            from library_cache import note
            self.cache_note.set(note(lib))
            self.host.status.set('武学配置读取完成；'+note(lib))
        from library_cache import load_library
        self.worker('正在刷新武学缓存…' if force_refresh else '正在读取武学本地缓存（首次读取会建立缓存）…',
                    lambda:load_library(root,'martial',force_refresh),finish)
    def animation_options(self):
        lib=self.library;self.animation_choices={};self.move_choices={}
        for mid,m in lib.tables['Martial'].items():
            if mid in getattr(lib,'retired_martials',set()):continue
            if m.get('MartMovIDs'):
                self.move_choices[f'{lib.name(mid)} · {mid} · {len(m["MartMovIDs"])}段']=mid
            for index,cid in enumerate(m.get('MartMovIDs',[])):
                sid=lib.tables['MartialItem'].get(cid,{}).get('SkillID1',0)
                source=lib.animations.get(sid,sid)
                if source in lib.performances:self.animation_choices[f'{lib.name(mid)} · 第{index+1}段 · {sid}']=sid
        self.move_box['values']=list(self.move_choices)
        for box in self.animation_boxes:box['values']=list(self.animation_choices)
    def render_animation(self):
        previous=self.setting;self.setting=True
        self.animation_options();lib=self.library;m=lib.tables['Martial'][self.current]
        for i,(var,box) in enumerate(zip(self.animation_vars,self.animation_boxes)):
            active=i<len(m.get('MartMovIDs',[]));box.configure(state='readonly' if active else 'disabled')
            if not active:var.set('未配置此段');continue
            sid=lib.tables['MartialItem'][m['MartMovIDs'][i]].get('SkillID1',0);source=lib.animations.get(sid,sid)
            label=next((k for k,v in self.animation_choices.items() if lib.animations.get(v,v)==source),'')
            var.set(label)
        self.move_template.set(next((k for k,v in self.move_choices.items() if v==self.current),''))
        self.setting=previous;self.animation_dirty=False
    def replace_moves(self):
        if not self.available():return
        template=self.move_choices.get(self.move_template.get())
        if template is None:self.host.error(ValueError('请选择招式结构模板'));return
        try:
            with self.library.edit():self.library.replace_moves(self.current,template)
            self.refresh_clauses();self.render_animation();self.refresh_list()
            return True
        except Exception as e:self.host.error(e)
    def stage_animation(self):
        if not self.available():return
        try:
            with self.library.edit():
                n=len(self.library.tables['Martial'][self.current].get('MartMovIDs',[]))
                for i in range(min(n,3)):
                    sid=self.animation_choices.get(self.animation_vars[i].get())
                    if sid is None:raise ValueError('请选择第 '+str(i+1)+' 段动画')
                    self.library.set_animation(self.current,i,sid)
            self.refresh_clauses();self.render_animation();self.refresh_list()
            return True
        except Exception as e:self.host.error(e)
    def schedule_list_search(self):
        if self._list_search_job:self.after_cancel(self._list_search_job)
        self._list_search_job=self.after(150,self.refresh_list)
    def refresh_list(self):
        if self._list_search_job:self.after_cancel(self._list_search_job);self._list_search_job=None
        if self.host.busy or not self.library:return
        from cursor_list import Entry
        entries=[]
        for ident,row in self.library.tables['Martial'].items():
            if ident in getattr(self.library,'retired_martials',set()):continue
            name=self.library.name(ident)
            entries.append(Entry(ident,(name+(' *' if ident in self.library.changes['Martial'] else ''),DEPARTS.get(row.get('DepartEnum'),'?'),RANKS.get(row.get('Rank'),'?')),(name+' '+str(ident)).casefold()))
        self.list_cursor.update(entries)
        changed=self.list_cursor.filter(self.query.get())
        if not changed and self.current!=self._list_current and self.current is not None:self.list_cursor.seek(self.current)
        self._list_current=self.current;self.render_list_page()
        self.summary.set(self.library.review() if self.library.modified() else f'已读取 {len(self.library.tables["Martial"])} 门武学；保存前可随时重新读取撤销草稿。')
    def render_list_page(self):
        self._list_rendering=True
        try:
            self.list.delete(*self.list.get_children())
            for entry in self.list_cursor.page():self.list.insert('','end',iid=str(entry.key),values=entry.value)
            self.list_pages.sync()
            if self.current is not None and self.list.exists(str(self.current)):self.list.selection_set(str(self.current));self.list.see(str(self.current))
        finally:self._list_rendering=False
    def focus_martial(self,ident):
        if self.list_cursor.seek(ident):
            self.render_list_page();self.list.selection_set(str(ident));self.list.see(str(ident));self.select()
    def select(self,e=None):
        if self._list_rendering or self.host.busy or not self.library or not self.list.selection():return
        ident=int(self.list.selection()[0])
        if ident==self.current:return
        if self.dirty or getattr(self,'animation_dirty',False):
            if not messagebox.askyesno('基础设置未加入草稿','切换会丢弃尚未加入草稿的基础设置，继续？',parent=self):
                if self.current is not None:
                    self.list_cursor.seek(self.current);self.render_list_page()
                return
        self.current=ident;self.render()
    def render(self):
        if not self.library or self.current is None:return
        lib=self.library;row=lib.tables['Martial'][self.current];self.setting=True
        from martial_forms import reference_names
        self.clan_names=reference_names(lib,'ClanID')
        if row.get('ClanID',0) not in self.clan_names:self.clan_names[row['ClanID']]='未知名称（保留原编号）'
        self.clan_combo.set_values([f'{i} · {n}' for i,n in sorted(self.clan_names.items())])
        for key,(var,kind) in self.fields.items():
            value=row.get(key,0)
            if key=='name':value=lib.name(self.current)
            elif key=='book':value=any(r['ItemType']==15 for r in lib.books(self.current))
            elif key=='random_book':
                from book_acquisition import enabled
                value=enabled(lib,self.current)
            elif key=='auto_icon':value=str(self.current) not in lib.icons
            elif kind=='list':value=','.join(map(str,row.get(key,[])))
            elif kind=='depart':value=f'{value} · {DEPARTS.get(value,"未知")}'
            elif kind=='rank':value=f'{value} · {RANKS.get(value,"未知")}'
            elif kind=='clan':value=f'{value} · {self.clan_names.get(value,"未知")}'
            elif kind=='coefficient':value=f'{value/10000:g}'
            var.set(value)
        self.description.delete('1.0','end');self.description.insert('1.0',lib.text(row.get('DesID',0)));self.description.edit_modified(False)
        self.exclusive=list(row.get('Exclusive',[]));self.role_note.set('专属人物原型 ID：'+','.join(map(str,self.exclusive)) if self.exclusive else '普通武学：未限制专属人物')
        self.setting=False;self.dirty=False;self.note.set(f'{lib.name(self.current)} · ID {self.current}');self.refresh_clauses();self.refresh_roles();self.render_animation();self.render_icon();self.refresh_list()
    def stage_basic(self):
        if not self.available():return False
        try:
            values={}
            for key,(var,kind) in self.fields.items():
                if key in ('auto_icon','book','CouldCopy','random_book'):continue
                if kind=='list':values[key]=[int(v) for v in var.get().replace('，',',').split(',') if v.strip()]
                elif kind in ('depart','rank','clan'):values[key]=int(var.get().split(' · ')[0])
                elif kind=='coefficient':
                    raw=Decimal(var.get())*10000
                    if not raw.is_finite() or raw!=raw.to_integral_value():raise ValueError('阴 / 阳系数最多支持四位小数')
                    values[key]=int(raw)
                elif kind=='bool':values[key]=int(var.get())
                elif kind=='int':values[key]=int(var.get())
                else:values[key]=var.get()
            values['description']=self.description.get('1.0','end-1c');values['Exclusive']=self.exclusive
            lib=self.library;old=lib.tables['Martial'][self.current]
            icon_changed=values['DepartEnum']!=old['DepartEnum'] or values['Rank']!=old['Rank'] or self.current in lib.sources['Martial']
            with lib.edit():
                lib.update_basic(self.current,values)
                if self.fields['auto_icon'][0].get() and icon_changed:lib.sync_icons(self.current)
                random_book=self.fields['random_book'][0].get()
                lib.configure_books(self.current,self.fields['book'][0].get() or random_book,self.fields['CouldCopy'][0].get())
                from book_acquisition import configure
                configure(lib,self.current,random_book)
            self.render();self.host.status.set('基础设置已加入武学草稿，点击“保存武学修改”后生效。');return True
        except Exception as e:self.host.error(e);return False
    def create(self):
        if not self.available():return
        if getattr(self,'animation_dirty',False) and not self.stage_animation():return
        if self.dirty and not self.stage_basic():return
        name=simpledialog.askstring('新增武学','以“'+self.library.name(self.current)+'”为模板。请输入新名称：',parent=self)
        if not name:return
        try:
            with self.library.edit():
                self.current=self.library.new_martial(self.current,name);self.library.sync_icons(self.current)
            self.query.set('');self.render();self.focus_martial(self.current);self.host.status.set('新武学已加入草稿；可设置专属人物、演化、秘籍、类别和数值。')
        except Exception as e:self.host.error(e)
    def manage_ranges(self):
        if not self.prepare_stage():return
        from range_ui import RangeManager
        def changed():
            self.refresh_clauses();self.host.status.set('范围词条清除 / 配置已加入草稿；保存武学修改并重启游戏后生效。')
        RangeManager(self,self.library,self.current,on_change=changed)

    def refresh_clauses(self):
        selection=self.clause_tree.selection()
        self.clause_tree.delete(*self.clause_tree.get_children());self.clauses={}
        lib=self.library;m=lib.tables['Martial'][self.current]
        for section,key in SECTIONS.items():
            for index,cid in enumerate(m.get(key,[])):
                row=lib.tables['MartialItem'].get(cid,{})
                level=section+(f' {m.get("UnlockLvls",[])[index]}级' if section=='解锁' else f' {index+1}')
                parts=describe_effects(lib,self.current,key,row)
                iid=f'{key}:{index}';self.clauses[iid]=(key,index)
                texts=[p['value'] for p in parts];labels=[p['name'] for p in parts]
                self.clause_tree.insert('','end',iid=iid,values=(level,' / '.join(dict.fromkeys(p['scope'] for p in parts)), ' / '.join(labels) or '武学条目',('；'.join(texts) or lib.text(row.get('DesID',0))).replace('\n',' ')))
        if selection and self.clause_tree.exists(selection[0]):self.clause_tree.selection_set(selection[0])
        from martial_ranges import references
        refs=references(lib);local=[r for r in refs if r['source']==self.current];incoming=[r for r in refs if r['target']==self.current]
        self.range_note.set(f'本武学提供 {len(local)} 条；作用于本武学 {len(incoming)} 条；全库 {len(refs)} 条')
        self.show_clause_detail();self.refresh_report()
    def show_clause_detail(self,e=None):
        selected=self.clause_tree.selection()
        if not self.library or self.current is None or not selected or selected[0] not in self.clauses:
            self.clause_detail.set('选择阶段查看完整效果；全部阶段可在“完整效果预览”中查看。');return
        key,index=self.clauses[selected[0]];m=self.library.tables['Martial'][self.current]
        row=self.library.tables['MartialItem'][m[key][index]];level=m['UnlockLvls'][index] if key=='UnlockClauses' else None
        parts=describe_effects(self.library,self.current,key,row)
        text='修改后效果：'+'；'.join(p['text'] for p in parts)
        if level is not None:text+=f'（{level}级解锁）'
        if row.get('CondID'):text+=f'；还需满足条件 {row["CondID"]}'
        # Long skill descriptions remain available in the scrollable full report.
        self.clause_detail.set(text[:260]+('…（完整说明见预览页）' if len(text)>260 else ''))
    def set_report(self,text):
        self.report_text.configure(state='normal');self.report_text.delete('1.0','end');self.report_text.insert('1.0',text);self.report_text.configure(state='disabled')
    def refresh_report(self):
        if not self.library or self.current is None:return
        self.set_report(martial_report(self.library,self.current))
        self.report_note.set('包含已加入草稿的修改；保存后同步生成说明文件：装备编辑器配置 / 武学效果说明 / '+str(self.current)+'.txt')
    def export_effect_report(self):
        if not self.available():return
        path=filedialog.asksaveasfilename(title='导出当前武学效果说明',initialfile=f'{self.library.name(self.current)}_效果说明.txt',defaultextension='.txt',filetypes=[('文本说明','*.txt')],parent=self)
        if not path:return
        try:
            Path(path).write_text(martial_report(self.library,self.current),encoding='utf-8-sig');self.host.status.set('效果说明已导出：'+path)
        except Exception as e:self.host.error(e)
    def selected_clause(self):
        if not self.available():return None
        sel=self.clause_tree.selection()
        if not sel:self.host.error(ValueError('请选择成长、招式或解锁条目'));return None
        return self.clauses[sel[0]]
    def stage_done(self,key,index):
        self.refresh_clauses();self.refresh_list();self.render_animation()
        iid=f'{key}:{index}'
        if self.clause_tree.exists(iid):self.clause_tree.selection_set(iid);self.clause_tree.see(iid)
        self.host.status.set('阶段与效果已加入草稿；保存武学修改后生效。')
    def prepare_stage(self):
        if not self.available():return False
        if getattr(self,'animation_dirty',False):return bool(self.stage_animation())
        return True
    def add_stage(self):
        if not self.prepare_stage():return
        d=StageDialog(self,self.library,self.current)
        if d.result is None:return
        key,source,level,delta=d.result
        try:
            with self.library.edit():index=self.library.add_stage(self.current,key,source,level,delta)
            self.stage_done(key,index)
        except Exception as e:self.host.error(e)
    def edit_stage(self):
        selected=self.selected_clause()
        if not selected or not self.prepare_stage():return
        if selected[0]=='UnlockClauses':
            from martial_ranges import references
            refs=[r for r in references(self.library,source=self.current) if r['index']==selected[1]]
            if refs:
                self.manage_ranges();return
        d=StageDialog(self,self.library,self.current,selected)
        if d.result is None:return
        key,source,level,delta=d.result;index=selected[1]
        try:
            with self.library.edit():self.library.update_stage(self.current,key,index,delta,level)
            self.stage_done(key,index)
        except Exception as e:self.host.error(e)
    def copy_stage(self):
        selected=self.selected_clause()
        if not selected or not self.prepare_stage():return
        key,index=selected
        try:
            with self.library.edit():index=self.library.copy_stage(self.current,key,index)
            self.stage_done(key,index)
        except Exception as e:self.host.error(e)
    def remove_stage(self):
        selected=self.selected_clause()
        if not selected or not self.prepare_stage():return
        key,index=selected
        try:
            with self.library.edit():self.library.remove_stage(self.current,key,index)
            self.stage_done(key,max(0,index-1))
        except Exception as e:self.host.error(e)
    def move_stage(self,step):
        selected=self.selected_clause()
        if not selected or not self.prepare_stage():return
        key,index=selected
        try:
            with self.library.edit():index=self.library.move_stage(self.current,key,index,step)
            self.stage_done(key,index)
        except Exception as e:self.host.error(e)
    def repair_skills(self):
        if not self.prepare_stage():return
        try:
            with self.library.edit():
                count=self.library.repair_legacy_skills(self.current)
                tables=self.library.repair_table_indices()
                bindings=self.library.repair_presentation(self.current)
                from language_routing import stage_repairs
                languages=stage_repairs(self.library)
            self.stage_done('MartMovIDs',0)
            messagebox.showinfo('武学配置修复',f'已同步当前武学的招式名称、属性说明，并检查武学限定引用。\n旧版招式 {count} 个；索引表 {len(tables)} 张；限定引用 {bindings} 处；语言分表修复 {languages} 条。\n请保存武学修改，然后重启游戏。\n\n'+'\n'.join(self.library.effect_audit(self.current)),parent=self)
        except Exception as e:self.host.error(e)
    def audit_effects(self):
        if not self.prepare_stage():return
        try:messagebox.showinfo('效果适用性校验','\n\n'.join(self.library.effect_audit(self.current)),parent=self)
        except Exception as e:self.host.error(e)
    def adapt_effects(self):
        if not self.prepare_stage():return
        try:
            with self.library.edit():count=self.library.adapt_progressive(self.current)
            self.stage_done('UnlockClauses',0)
            messagebox.showinfo('逐次威力系数适配',f'已将 {count} 条属性 321 适配为当前模板读取的属性 361，保留原数值。\n原值 10000 表示系数增量 1，作用方式与伤害百分比不同；实际增量还受基础次数和攻击序号影响。\n请检查数值、保存并在游戏内测试。',parent=self)
        except Exception as e:self.host.error(e)
    def edit_level(self):
        selected=self.selected_clause()
        if not selected:return
        key,index=selected
        if key!='UnlockClauses':self.host.error(ValueError('只有解锁条目设置解锁等级'));return
        level=simpledialog.askinteger('解锁等级','输入解锁等级：',initialvalue=self.library.tables['Martial'][self.current]['UnlockLvls'][index],minvalue=0,maxvalue=1000,parent=self)
        if level is None:return
        try:
            with self.library.edit():self.library.unlock_level(self.current,index,level)
            self.refresh_clauses();self.refresh_list()
        except Exception as e:self.host.error(e)
    def cap_current(self):
        if not self.available():return
        self.fields['LvLimit'][0].set('30')
        self.stage_basic()
    def render_icon(self):
        if not self.library or self.current is None:return
        from martial_images import icon_path
        icons=self.library.active_icons(self.current);icon=icons[0] if icons else ''
        path=icon_path(self.library.root,icon);self._icon_image=None
        self.icon_preview.configure(image='',text='原生图标' if path is None else '图片预览')
        self.icon_note.set(icon or '尚未配置主动招式图标')
        if path is not None:
            try:
                from PIL import Image,ImageTk
                raw=self.library.icon_files.get(path) or path.read_bytes()
                with Image.open(io.BytesIO(raw)) as im:
                    im=im.convert('RGBA');im.thumbnail((100,100));self._icon_image=ImageTk.PhotoImage(im,master=self)
                self.icon_preview.configure(image=self._icon_image,text='')
            except Exception as e:self.icon_note.set('图标文件无法预览：'+str(e))
    def import_icon(self):
        if not self.available():return
        path=filedialog.askopenfilename(title='选择武学图标图片',filetypes=[('图片','*.png *.jpg *.jpeg *.webp *.bmp'),('所有文件','*.*')],parent=self)
        if not path:return
        try:
            with self.library.edit():self.library.import_icon(self.current,path)
            self.setting=True;self.fields['auto_icon'][0].set(False);self.setting=False
            self.render_icon();self.refresh_list();self.host.status.set('图标已加入草稿并预览；点击“保存武学修改”后应用。')
        except Exception as e:self.host.error(e)
    def reset_icon(self):
        if not self.available():return
        try:
            with self.library.edit():self.library.reset_icon(self.current)
            self.render_icon();self.refresh_list()
        except Exception as e:self.host.error(e)
    def edit_growth(self):
        selected=self.selected_clause()
        if not selected:return
        key,index=selected;lib=self.library;row=lib.tables['MartialItem'][lib.tables['Martial'][self.current][key][index]]
        slots=[s for s in (1,2) if row.get('EffectEnum'+str(s)) in (7,9)]
        if key!='GrowProIDs' or not slots:self.host.error(ValueError('请选择“每级”成长阶段'));return
        slot=slots[0]
        if len(slots)>1:
            slot=simpledialog.askinteger('选择成长效果','修改第 1 项或第 2 项成长：',minvalue=1,maxvalue=2,parent=self)
            if slot is None:return
        try:
            if row.get('CondID') or row.get('MartialFilter'+str(slot)):raise ValueError('带条件或筛选的成长公式暂不支持直接改写，请沿用模板')
            from martial_forms import GrowthDialog
            d=GrowthDialog(self,lib,self.current,index,slot)
            if d.result is None:return
            with lib.edit():
                lib.growth.apply(lib,self.current,*d.result,selected=index,slot=slot)
            self.stage_done(key,index);self.host.status.set('每级成长已加入草稿；默认使用独立词条，原模板和其他武学的成长保持原值。')
        except Exception as e:self.host.error(e)
    def add_growth(self):
        if not self.prepare_stage():return
        if self.dirty and not self.stage_basic():return
        try:
            from martial_forms import GrowthDialog
            lib=self.library;d=GrowthDialog(self,lib,self.current)
            if d.result is None:return
            with lib.edit():index=lib.growth.apply(lib,self.current,*d.result)
            self.stage_done('GrowProIDs',index);self.host.status.set('新增每级成长已加入草稿，请保存武学修改后在游戏中读取。')
        except Exception as e:self.host.error(e)
    def convert_self_buff(self):
        selected=self.selected_clause()
        if not selected:return
        key,index=selected;lib=self.library;r=lib.tables['MartialItem'][lib.tables['Martial'][self.current][key][index]]
        slots=[s for s in (1,2) if r.get('EffectEnum'+str(s))==10 and r.get('AttrEnum'+str(s)) in (312,313,314,315,316)]
        if not slots:self.host.error(ValueError('请选择“附加强壮 / 坚韧 / 疗伤 / 调息 / 轻盈”解锁阶段'));return
        d=ValuesDialog(self,'改为自身增益',[('event','触发时机：313 施放后，312 每次造成伤害后','313','int')],'保留当前阶段的解锁等级和层数，使用原生增益状态。多段武学选择 312 时每次伤害都会触发；313 在一轮招式施放后触发。状态上限、衰减和效果沿用游戏原规则。')
        if d.result is None:return
        try:
            with lib.edit():
                for slot in slots:lib.self_buff(self.current,key,index,slot,d.result['event'])
            self.refresh_clauses();self.refresh_list()
        except Exception as e:self.host.error(e)
    def convert_final_damage(self):
        selected=self.selected_clause()
        if not selected:return
        key,index=selected
        try:
            with self.library.edit():self.library.final_damage_add(self.current,key,index)
            self.refresh_clauses();self.refresh_list();self.host.status.set('已改为最终伤害附加百分比，保留数值和解锁等级；计算位置与倍率修正不同。')
        except Exception as e:self.host.error(e)
    def edit_clause(self):
        selected=self.selected_clause()
        if not selected:return
        key,index=selected;lib=self.library;cid=lib.tables['Martial'][self.current][key][index];row=lib.tables['MartialItem'][cid];items=[];mapping={}
        if key=='UnlockClauses':
            from martial_ranges import clause_range
            if any(clause_range(lib,row,slot) for slot in (1,2)):
                self.manage_ranges();return
        if key=='GrowProIDs' and any(row.get('EffectEnum'+str(s)) in (7,9) for s in (1,2)):
            self.edit_growth();return
        for slot in (1,2):
            attr=row.get('AttrEnum'+str(slot),0);vals=row.get('Effect'+str(slot)+'Value',[])
            for j,value in enumerate(vals):
                token=f'{slot}:{j}';mapping[token]=(slot,j)
                percent= j==0 and lib.percent.get(attr,{}).get('PerMyriad')==1 and lib.percent.get(attr,{}).get('ShowAsPercent')==1
                label=(lib.attr_names.get(str(attr),'效果 '+str(slot)) if j==0 else '附加参数 '+str(j+1))
                items.append((token,label+('（%）' if percent else '（原值）'),str(value/100) if percent else str(value),'percent' if percent else 'int'))
        if not items:self.edit_skill();return
        detail='；'.join(p['text'] for p in describe_effects(lib,self.current,key,row))
        d=ValuesDialog(self,'修改武学数值',items,'当前效果：'+detail+'\n百分比输入 25 即为 25%。加入草稿后，可在阶段下方及完整效果预览查看修改结果。')
        if d.result is None:return
        delta={}
        for token,value in d.result.items():
            slot,j=mapping[token];field='Effect'+str(slot)+'Value';delta.setdefault(field,list(row[field]))[j]=value
        try:
            with lib.edit():lib.edit_clause(self.current,key,index,delta)
            self.refresh_clauses();self.refresh_list()
        except Exception as e:self.host.error(e)
    def edit_skill(self):
        selected=self.selected_clause()
        if not selected:return
        key,index=selected;lib=self.library;cid=lib.tables['Martial'][self.current][key][index];row=lib.tables['MartialItem'][cid]
        if key=='UnlockClauses':
            from martial_ranges import clause_range
            if any(clause_range(lib,row,slot) for slot in (1,2)):
                self.manage_ranges();return
        slots=[s for s in (1,2) if row.get('SkillID'+str(s)) in lib.tables['Skill']]
        if not slots:self.host.error(ValueError('该条目不引用招式；请使用“修改条目数值”'));return
        slot=slots[0]
        if len(slots)>1:
            slot=simpledialog.askinteger('选择效果','选择第 1 或第 2 个效果：',minvalue=1,maxvalue=2,parent=self)
            if slot is None:return
        sid=row['SkillID'+str(slot)];skill=lib.tables['Skill'][sid]
        try:graph=lib.effect_graph(sid)
        except Exception as e:self.host.error(e);return
        items=[];mapping={}
        for field,label in [('Cost','真气消耗'),('CostLvl','每级真气消耗'),('MascCoef','阳性系数'),('FemiCoef','阴性系数'),('MPBaseCostPercent','真气百分比消耗'),('MPCostPercentLevel','每级真气百分比消耗'),('Penetrate','穿透次数'),('Catapult','弹射次数')]:
            items.append(('skill:'+field,label,str(skill.get(field,0)),'float' if field in ('MPBaseCostPercent','MPCostPercentLevel') else 'int'))
        for ident,effect in graph.items():
            label=lib.labels.get(('SkillEffectDescription',effect.get('Name',0)),'运算 '+str(effect.get('Name',0)))
            for field,values in effect.items():
                if field.startswith('EventArg') and isinstance(values,list) and len(values)==2 and values[1]==0:
                    if field=='EventArg1' and effect.get('Name')==lib.enums.get('SkillEffectDescription.SED_SkillLogic_CommonInitiativeSkill'):continue
                    token=f'{ident}:{field}';mapping[token]=(ident,field)
                    arglabel,percent=lib.effect_argument(effect,field)
                    items.append((token,label+' · '+arglabel+('（%）' if percent else '（原值）'),str(values[0]/100) if percent else str(values[0]),'percent' if percent else 'int'))
        items.append(('description','游戏内效果说明',lib.text(skill.get('DescID',0)),'text'))
        shared=skill.get('SurperType',0)
        note='修改当前武学的招式副本。战斗参数按游戏原始单位输入，百分比常见单位为万分比（5000 = 50%）；参数可能包含属性或状态编号，请按运算含义修改。修改数值后同步调整下方效果说明。'
        if shared:note+=' 此招式引用特殊状态组 '+str(shared)+'，状态内部参数可在“特殊状态参数”窗口编辑。'
        d=ValuesDialog(self,'招式 / 战斗参数',items,note)
        if d.result is None:return
        delta={};effects={}
        for token,value in d.result.items():
            if token=='description':continue
            if token.startswith('skill:'):delta[token[6:]]=value
            else:
                ident,field=mapping[token];effects.setdefault(ident,{})[field]=[value,0]
        try:
            with lib.edit():lib.edit_skill(self.current,key,index,slot,delta,effects,d.result['description'])
            self.refresh_clauses();self.refresh_list()
        except Exception as e:self.host.error(e)
    def edit_state(self):
        selected=self.selected_clause()
        if not selected:return
        key,index=selected;lib=self.library;cid=lib.tables['Martial'][self.current][key][index];clause=lib.tables['MartialItem'][cid]
        skills=[lib.tables['Skill'].get(clause.get('SkillID'+str(s)),{}) for s in (1,2)]
        skills=[s for s in skills if s.get('SurperType')]
        if not skills:self.host.error(ValueError('此条目没有特殊状态组；请使用“招式 / 战斗参数”'));return
        group=lib.tables['SuperImposed'].get(skills[0]['SurperType'],{});items=[];mapping={}
        try:
            for gid in group.get('BuffList',[]):
                gift=lib.tables['Gift'].get(gid,{})
                name=lib.text(gift.get('NameID',0)) or str(gid)
                for j,value in enumerate(gift.get('AttrValue',[])):
                    attr=gift.get('AttrType',[])[j];token=f'gift:{gid}:{j}';mapping[token]=('gift',gid,j)
                    percent=lib.percent.get(attr,{}).get('PerMyriad')==1 and lib.percent.get(attr,{}).get('ShowAsPercent')==1
                    items.append((token,name+' · '+lib.attr_names.get(str(attr),str(attr))+('（%）' if percent else '（原值）'),str(value/100) if percent else str(value),'percent' if percent else 'int'))
                for eid,effect in lib.trigger_graph(gift.get('SkillTriggers',[])).items():
                    opname=lib.labels.get(('SkillEffectDescription',effect.get('Name',0)),'运算 '+str(effect.get('Name',0)))
                    for field,values in effect.items():
                        if field.startswith('EventArg') and isinstance(values,list) and len(values)==2 and values[1]==0:
                            token=f'effect:{eid}:{field}'
                            if token in mapping:continue
                            mapping[token]=('effect',eid,field)
                            arglabel,percent=lib.effect_argument(effect,field)
                            items.append((token,name+' · '+opname+' · '+arglabel+('（%）' if percent else '（原值）'),str(values[0]/100) if percent else str(values[0]),'percent' if percent else 'int'))
                token=f'desc:{gid}';mapping[token]=('description',gid,None);items.append((token,name+' · 效果说明',lib.text(gift.get('DescID',0)),'text'))
            if not items:raise ValueError('状态组没有可读取参数')
        except Exception as e:self.host.error(e);return
        d=ValuesDialog(self,'特殊状态参数（共享配置）',items,'这些参数属于游戏共用的特殊状态组，修改会影响所有引用同一状态的武学和装备天赋。参数按原值输入，5000 常表示 50%；修改后同步编辑效果说明。')
        if d.result is None:return
        try:
            with lib.edit():
                gifts={}
                for token,value in d.result.items():
                    kind,ident,field=mapping[token]
                    if kind=='gift':gifts.setdefault(ident,list(lib.tables['Gift'][ident]['AttrValue']))[field]=value
                    elif kind=='effect':
                        if value!=lib.tables['SkillEffect'][ident][field][0]:lib.set('SkillEffect',ident,{field:[value,0]})
                    elif value!=lib.text(lib.tables['Gift'][ident].get('DescID',0)):
                        lib.set('Gift',ident,{'DescID':lib.set_text(0,value)})
                for ident,values in gifts.items():
                    if values!=lib.tables['Gift'][ident]['AttrValue']:lib.set('Gift',ident,{'AttrValue':values})
            self.refresh_clauses();self.refresh_list()
        except Exception as e:self.host.error(e)
    def refresh_roles(self):
        if self.host.busy or not self.library:return
        self.role_tree.delete(*self.role_tree.get_children());q=self.roles_query.get().strip().casefold()
        count=0
        for ident,row in self.library.tables['Role'].items():
            name=self.library.text(row.get('NameID',0)) or self.library.text(row.get('GivennameID',0)) or '未命名人物'
            if q not in (name+' '+str(ident)+' '+str(row.get('RoleID',0))).casefold():continue
            ids=row.get('Kungfu',[]);lv=row.get('KungfuLevel',[]);owned=lv[ids.index(self.current)] if self.current in ids and len(ids)==len(lv) else '—'
            self.role_tree.insert('','end',iid=str(ident),values=(name+f' · {ident}',row.get('EvoInitCity',0),owned));count+=1
            if count>=250:break
    def assign(self,enabled=True):
        if not self.available():return
        selected=self.role_tree.selection()
        if not selected:self.host.error(ValueError('请选择人物，可按名称或 ID 搜索'));return
        try:
            with self.library.edit():
                for rid in selected:self.library.assign_role(self.current,int(rid),int(self.role_level.get()),enabled)
            self.refresh_roles();self.refresh_list()
        except Exception as e:self.host.error(e)
    def set_exclusive(self):
        if not self.available():return
        if not self.role_tree.selection():self.host.error(ValueError('请选择专属人物'));return
        self.exclusive=list(dict.fromkeys(self.library.tables['Role'][int(i)]['RoleID'] for i in self.role_tree.selection()))
        self.role_note.set('专属人物原型 ID：'+','.join(map(str,self.exclusive))+'（待加入基础草稿）');self.dirty=True
    def clear_exclusive(self):
        if not self.available():return
        self.exclusive=[];self.role_note.set('普通武学：未限制专属人物（待加入基础草稿）');self.dirty=True
    def save(self,export=False):
        if not self.available():return
        if getattr(self.host,'role_page',None) and self.host.role_page.has_changes():self.host.error(ValueError('请先保存或撤销人物草稿，再保存武学配置'));return
        if getattr(self,'animation_dirty',False) and not self.stage_animation():return
        if self.dirty and not self.stage_basic():return
        lib=self.library
        if not lib.modified():self.host.error(ValueError('没有待保存的武学修改'));return
        if self.host.drafts or self.host.effects:self.host.error(ValueError('请先保存或撤销装备草稿，再保存武学配置'));return
        try:
            if not export:ensure_closed()
        except Exception as e:self.host.error(e);return
        folder=None
        if export:
            selected=filedialog.askdirectory(title='选择游戏目录之外的导出目录',parent=self)
            if not selected:return
            folder=Path(selected).resolve()
            if folder.is_relative_to(lib.root):self.host.error(ValueError('请选择游戏目录之外的目录'));return
        try:audit='\n\n效果校验：\n'+'\n'.join(lib.effect_audit(self.current))
        except Exception as e:self.host.error(e);return
        review=lib.review()+audit
        def work():
            payloads,originals=lib.plan()
            if export:
                from datetime import datetime
                target=folder/('武学配置副本_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'));target.mkdir()
                for path,data in payloads.items():
                    dest=target/path.relative_to(lib.root);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
                (target/'导出说明.txt').write_text('这是待安装的配置副本；游戏原文件未修改。建议在编辑器中保存以自动备份。\n'+review,encoding='utf-8')
                return target
            from martial_collection import augment
            augment(lib.root,payloads,originals,lib.compat_notes)
            ensure_closed();return transaction(lib.root,payloads,originals,'新增/编辑武学')
        def finish(target):
            if export:self.host.status.set(f'武学配置副本已导出：{target}');messagebox.showinfo('导出完成',str(target),parent=self);return
            mid=self.current;self.reset();self.host.role_page.reset();self.host.reload();self.host.refresh_caps()
            self.host.status.set(f'武学配置已保存并完成配置校验；效果适用性见提示。备份：{target}')
            from mod_compatibility import summary
            messagebox.showinfo('武学保存完成',review+summary(lib)+'\n\n修改后效果说明：'+str(lib.root/'装备编辑器配置/武学效果说明')+'\n\n重启游戏后读取配置。人物初始分配在新周目或后续创建人物时生效。\n\n备份：'+str(target),parent=self)
        self.worker('正在验证、'+('导出' if export else '备份并保存')+'武学配置…',work,finish)

    def generate(self):
        if not self.available():return
        if getattr(self.host,'role_page',None) and self.host.role_page.has_changes():self.host.error(ValueError('请先保存或撤销人物草稿'));return
        if getattr(self,'animation_dirty',False) and not self.stage_animation():return
        if self.dirty and not self.stage_basic():return
        if not self.host.save:self.host.error(ValueError('请先在装备页选择目标存档'));return
        if self.host.drafts or self.host.effects:self.host.error(ValueError('请先保存或撤销装备草稿'));return
        try:
            ensure_closed()
        except Exception as e:self.host.error(e);return
        quantity=simpledialog.askinteger('生成测试秘籍','写入目标：'+self.host.save_var.get()+'\n数量（先保存武学配置，并自动备份）：',initialvalue=1,minvalue=1,maxvalue=99,parent=self)
        if quantity is None:return
        lib=self.library;mid=self.current
        try:
            with lib.edit():lib.configure_books(mid,True,lib.tables['Martial'][mid].get('CouldCopy',0))
            book=next(r for r in lib.books(mid) if r['ItemType']==15)
        except Exception as e:self.host.error(e);return
        catalog=copy.copy(self.host.catalog);catalog.items=lib.tables['Item']
        source=Save(self.host.save.path,catalog,self.host.save.data)
        def work():
            ensure_closed();payloads,originals=lib.plan();new,ident=generate_book(source,book['BaseID'],quantity)
            payloads[source.path]=new;originals[source.path]=source.data
            from martial_collection import augment
            augment(lib.root,payloads,originals,lib.compat_notes)
            return transaction(lib.root,payloads,originals,'保存武学并生成仓库测试秘籍'),ident
        def finish(result):
            backup,ident=result;self.reset();self.host.role_page.reset();self.host.reload();self.host.refresh_caps()
            self.host.status.set(f'已生成秘籍 {quantity} 本到所选存档的周目仓库。备份：{backup}')
            messagebox.showinfo('生成完成',f'已保存武学配置，并生成秘籍 {quantity} 本到周目仓库。\n秘籍实例 ID：{ident}\n\n重启游戏并读取所选存档后测试。\n备份：{backup}',parent=self)
        self.worker('正在保存武学配置并生成周目仓库测试秘籍…',work,finish)
