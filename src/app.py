from edition import DISPLAY_VERSION
import copy, json, os, sys, traceback, threading, queue
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from engine import Catalog, Save, effect_draft, effect_payloads, transaction, restore, ensure_closed, META, clean, skipped_records_note
from external_runtime_ui import show as external_mod_dialog
from caps import plan_caps, cap_summary
from martial_ui import MartialPage
from role_ui import RolePage
from restore_all import plan_restore_all, apply_restore_all, RestoreAllDialog
from cursor_list import CursorList,Entry,PageBar

DEFAULT_GAME = r'D:\game\steam\steamapps\common\xiake'
PREFS = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'MengJiangHuEquipEditor/settings.json'
GROUPS = {'white': ('基础属性', 2), 'green': ('铸造属性', 7), 'blue': ('蓝字铸造百分比加成', 2)}

class Picker(tk.Toplevel):
    def __init__(self, master, title, choices, initial, fields, description=None, allow_repeat=False):
        super().__init__(master); self.title(title); self.result = None
        self.transient(master); self.resizable(True, True)
        master.update_idletasks()
        width, height = min(760, self.winfo_screenwidth() - 40), min(620, self.winfo_screenheight() - 80)
        x = max(0, min(master.winfo_rootx() + (master.winfo_width() - width) // 2, self.winfo_screenwidth() - width))
        y = max(0, min(master.winfo_rooty() + (master.winfo_height() - height) // 2, self.winfo_screenheight() - height))
        self.geometry(f'{width}x{height}+{x}+{y}')
        self.choices = choices; self.filtered = []; self.description = description
        self.query = tk.StringVar(); self.query.trace_add('write', lambda *_: self.filter())
        top = ttk.Frame(self, padding=16); top.pack(fill='both', expand=True)
        ttk.Label(top, text='搜索名称或 ID').pack(anchor='w')
        ttk.Entry(top, textvariable=self.query).pack(fill='x', pady=(6, 8))
        wrap = ttk.Frame(top); wrap.pack(fill='both', expand=True)
        self.list = tk.Listbox(wrap, font=('Microsoft YaHei UI', 11), exportselection=False, activestyle='none')
        self.list.pack(side='left', fill='both', expand=True)
        scroll = ttk.Scrollbar(wrap, command=self.list.yview); scroll.pack(side='right', fill='y')
        self.list.configure(yscrollcommand=scroll.set)
        self.list.bind('<<ListboxSelect>>', self.show_desc)
        self.note = tk.StringVar()
        ttk.Label(top, textvariable=self.note, wraplength=710, foreground='#456079').pack(fill='x', pady=8)
        self.vars = {}
        for key, label, default in fields:
            row = ttk.Frame(top); row.pack(fill='x', pady=4)
            ttk.Label(row, text=label, width=24).pack(side='left')
            var = tk.StringVar(value=str(initial.get(key, default))); self.vars[key] = var
            ttk.Entry(row, textvariable=var, width=22).pack(side='left')
        if 'fixed' in initial:
            self.fixed = tk.BooleanVar(value=initial['fixed'])
            ttk.Checkbutton(top, text='固定铸造词条（保留存档的固定类型标记）', variable=self.fixed).pack(anchor='w', pady=5)
        else: self.fixed = None
        self.repeat = tk.StringVar(value='1')
        if allow_repeat:
            row = ttk.Frame(top); row.pack(fill='x', pady=5)
            ttk.Label(row, text='添加相同词条数量', width=24).pack(side='left')
            ttk.Spinbox(row, from_=1, to=4096, textvariable=self.repeat, width=20).pack(side='left')
        footer = ttk.Frame(top); footer.pack(fill='x', pady=(10, 0))
        ttk.Button(footer, text='确定', command=self.accept).pack(side='right')
        ttk.Button(footer, text='取消', command=self.destroy).pack(side='right', padx=8)
        self.filter(initial.get('id', initial.get('type')))
        self.protocol('WM_DELETE_WINDOW', self.destroy); self.grab_set(); self.wait_visibility(); self.focus_set()
        self.wait_window()

    def filter(self, selected=None):
        query = self.query.get().casefold().strip()
        self.filtered = [(ident, text) for ident, text in self.choices if query in text.casefold()]
        self.list.delete(0, 'end')
        for ident, text in self.filtered: self.list.insert('end', text)
        if self.filtered:
            index = next((i for i, x in enumerate(self.filtered) if x[0] == selected), 0)
            self.list.selection_set(index); self.list.see(index); self.show_desc()

    def show_desc(self, event=None):
        selected = self.list.curselection()
        if selected and self.description: self.note.set(self.description(self.filtered[selected[0]][0]))

    def accept(self):
        try:
            if not self.list.curselection(): raise ValueError('请选择一条属性或天赋')
            ident = self.filtered[self.list.curselection()[0]][0]
            out = {key: int(var.get()) for key, var in self.vars.items()}
            out['id'] = ident
            if self.fixed is not None: out['fixed'] = self.fixed.get()
            repeats = int(self.repeat.get())
            if not 1 <= repeats <= 4096: raise ValueError('添加数量范围为 1～4096')
            self.result = (out, repeats); self.destroy()
        except Exception as error: messagebox.showerror('输入有误', str(error), parent=self)

class Application(tk.Tk):
    def __init__(self):
        super().__init__(); self.title('梦江湖 · 已有装备/武学/人物编辑器 '+DISPLAY_VERSION+' --mode by 零光-6.1Sol')
        width = min(1600, self.winfo_screenwidth()-60); height = min(900, self.winfo_screenheight()-80)
        self.geometry(f'{width}x{height}'); self.minsize(1280, 800)
        try:
            from engine import DATA_ROOT
            self.iconbitmap(str(DATA_ROOT / 'app.ico'))
        except Exception: pass
        self.catalog = None; self.save = None; self.current = None
        self.drafts = {}; self.effects = {}; self.visible_records = {}; self.saves = []; self.active_save_index = None
        self.item_cursor=CursorList();self._equipment_source=None;self._item_search_job=None
        self.attr_trees = {}; self.loading = False; self.busy = False
        self.game_path = tk.StringVar(value=DEFAULT_GAME); self.save_var = tk.StringVar()
        self.search = tk.StringVar(); self.scope = tk.StringVar(value='周目仓库')
        self.status = tk.StringVar(value='选择游戏目录后，读取自动存档或手动存档。')
        self.detail = tk.StringVar(value='选择左侧装备开始编辑'); self.grade = tk.StringVar(value='0')
        self.effect_note = tk.StringVar(value='强化效果来自装备配置；修改会影响此型号的全部装备及所有存档。')
        self.cap_status = tk.StringVar(value='读取游戏目录后查看当前武学上限')
        try:
            prefs = json.loads(PREFS.read_text(encoding='utf-8')); self.game_path.set(prefs.get('game_path', DEFAULT_GAME))
        except Exception: pass
        self.style(); self.build()
        self.search.trace_add('write', lambda *_: self.schedule_item_search())
        self.scope.trace_add('write', lambda *_: self.refresh_items())
        self.grade.trace_add('write', self.grade_changed)
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.after(200, self.load_game)

    def style(self):
        from desktop_theme import apply_theme
        apply_theme(self)

    def build(self):
        outer = ttk.Frame(self, style='Shell.TFrame', padding=(20,8,20,12)); outer.pack(fill='both', expand=True)
        from desktop_theme import InkHeader
        self.ink_header=InkHeader(outer,DISPLAY_VERSION);self.ink_header.pack(fill='x')
        workspace = ttk.Frame(outer,style='Card.TFrame',padding=(16,12));workspace.pack(fill='x',pady=(8,10))
        bar = ttk.Frame(workspace); bar.pack(fill='x', pady=(0, 8))
        ttk.Label(bar, text='游戏目录').pack(side='left', padx=(0, 8))
        ttk.Entry(bar, textvariable=self.game_path).pack(side='left', fill='x', expand=True)
        ttk.Button(bar, text='选择目录', style='Ink.TButton', command=self.browse).pack(side='left', padx=6)
        ttk.Button(bar, text='读取目录', style='Ink.TButton', command=self.load_game).pack(side='left')
        ttk.Button(bar, text='还原所有修改', style='Ink.TButton', command=self.restore_all_dialog).pack(side='left',padx=(10,0))
        ttk.Button(bar,text='外部 MOD 安装兼容',command=lambda:external_mod_dialog(self)).pack(side='left',padx=6)
        sharebar=ttk.Frame(workspace);sharebar.pack(fill='x',pady=(2,0))
        ttk.Button(sharebar,text='查看改动日志',command=self.show_change_logs).pack(side='left')
        ttk.Button(sharebar,text='读取改动效果',command=self.read_change_effects).pack(side='left',padx=8)
        ttk.Button(sharebar,text='导出改动效果',command=self.export_change_effects).pack(side='left')
        ttk.Label(sharebar,text='日志区分待保存与已保存 · 共享文件读取后预览并备份',style='Sub.TLabel').pack(side='left',padx=12)
        bottom = ttk.Frame(outer,style='Shell.TFrame'); bottom.pack(side='bottom',fill='x',pady=(8,0))
        ttk.Label(bottom, textvariable=self.status, wraplength=1260,style='Shell.TLabel').pack(side='left')
        ttk.Label(bottom,text='梦江湖 · MOD 编辑工作台',style='Shell.TLabel').pack(side='right')
        self.pages = ttk.Notebook(outer,style='Workspace.TNotebook'); self.pages.pack(fill='both', expand=True, pady=(8,0))
        equipment = ttk.Frame(self.pages, padding=14); self.pages.add(equipment,text='装备编辑')
        caps_page = ttk.Frame(self.pages, padding=20); self.pages.add(caps_page,text='功能修改')
        from feature_ui import build
        build(self,caps_page)
        self.martial_page = MartialPage(self.pages,self); self.pages.add(self.martial_page,text='武学编辑 · Beta')
        self.role_page=RolePage(self.pages,self);self.pages.add(self.role_page,text='人物编辑 · Beta')
        paned = ttk.Panedwindow(equipment, orient='horizontal'); paned.pack(fill='both', expand=True)
        left = ttk.Frame(paned,style='Card.TFrame',padding=14); paned.add(left, weight=2)
        right = ttk.Frame(paned,style='Card.TFrame',padding=14); paned.add(right, weight=5)
        ttk.Label(left,text='装备列表',font=('Microsoft YaHei UI',13,'bold')).pack(anchor='w',pady=(0,12))
        bar = ttk.Frame(right); bar.pack(fill='x', pady=(0,12))
        selection = ttk.Frame(bar);selection.grid(row=0,column=0,sticky='w')
        actions = ttk.Frame(bar);actions.grid(row=0,column=1,sticky='e')
        bar.columnconfigure(0,weight=1)
        ttk.Label(selection, text='目标存档').pack(side='left', padx=(0, 8))
        self.save_box = ttk.Combobox(selection, textvariable=self.save_var, state='readonly', width=23)
        self.save_box.pack(side='left'); self.save_box.bind('<<ComboboxSelected>>', lambda _: self.load_save())
        ttk.Button(selection, text='重新读取', command=self.reload).pack(side='left', padx=6)
        ttk.Button(actions, text='保存装备修改', style='Primary.TButton', command=self.write).pack(side='left',padx=6)
        ttk.Button(actions, text='备份恢复', command=self.restore_dialog).pack(side='left',padx=6)
        ttk.Button(actions, text='导出修改副本', command=self.export).pack(side='left')
        def fit_actions(event):
            compact=event.width<900
            actions.grid_configure(row=1 if compact else 0,column=0 if compact else 1,pady=(8,0) if compact else 0)
        bar.bind('<Configure>',fit_actions)
        from object_ui import export_selected,import_selected
        from desktop_theme import ToolShelf
        self.equipment_tools=ToolShelf(right,'装备完整配置导入 / 导出');self.equipment_tools.pack(fill='x',pady=(0,8))
        self.equipment_tools.toggle.pack_configure(side='right')
        ttk.Label(self.equipment_tools.heading, textvariable=self.detail, font=('Microsoft YaHei UI', 13, 'bold'), wraplength=570).pack(side='left',anchor='w')
        objectbar=ttk.Frame(self.equipment_tools.body);objectbar.pack(fill='x')
        ttk.Button(objectbar,text='导出所选装备完整配置',command=lambda:export_selected(self,'Item')).pack(side='left')
        ttk.Button(objectbar,text='导入装备完整配置',command=lambda:import_selected(self,'Item')).pack(side='left',padx=8)
        filters = ttk.Frame(left); filters.pack(fill='x')
        ttk.Combobox(filters, textvariable=self.scope, values=['周目仓库', '主角背包/穿戴', '全部装备'], state='readonly', width=13).pack(side='left')
        ttk.Entry(filters, textvariable=self.search).pack(side='left', fill='x', expand=True, padx=(8, 0))
        ttk.Button(filters, text='清空', width=4, command=lambda:self.search.set('')).pack(side='right',padx=(4,0))
        ttk.Label(left, text='搜索装备名、实例 ID 或型号 ID', style='Sub.TLabel').pack(anchor='w', pady=(6, 8))
        self.items = self.make_tree(left, [('name', '装备', 195), ('grade', '强化', 55), ('location', '位置', 115)])
        self.items.bind('<<TreeviewSelect>>', self.select_item)
        self.item_pages=PageBar(left,self.item_cursor,self.render_item_page);self.item_pages.pack(side='bottom',fill='x',pady=(8,0),before=self.items.master)
        self.count_label = ttk.Label(left, text='尚未读取', style='Sub.TLabel'); self.count_label.pack(side='bottom',anchor='w', pady=4,before=self.items.master)
        grade_bar = ttk.Frame(right); grade_bar.pack(fill='x', pady=10)
        ttk.Label(grade_bar, text='强化等级').pack(side='left')
        ttk.Spinbox(grade_bar, from_=0, to=20, textvariable=self.grade, width=5).pack(side='left', padx=8)
        ttk.Label(grade_bar, text='0～20；效果达到其解锁等级后启用', style='Sub.TLabel').pack(side='left')
        ttk.Button(grade_bar, text='撤销这件装备的存档修改', command=self.revert_item).pack(side='right')
        from equipment_copy import show as copy_equipment
        ttk.Button(grade_bar,text='复制装备',command=lambda:copy_equipment(self)).pack(side='right',padx=8)
        notebook = ttk.Notebook(right); notebook.pack(fill='both', expand=True)
        dynamic = ttk.Frame(notebook,padding=10);notebook.add(dynamic,text='装备词条（此存档、此装备）')
        group_pages = ttk.Notebook(dynamic); group_pages.pack(fill='both',expand=True,pady=(0,12))
        for key, (label, count) in GROUPS.items():
            box = ttk.Frame(group_pages,padding=10); group_pages.add(box,text=label.replace('蓝字铸造百分比加成','蓝字加成'))
            title = ttk.Frame(box); title.pack(fill='x')
            ttk.Label(title, text=f'{label}  ·  {count} 个槽位', font=('Microsoft YaHei UI', 10, 'bold')).pack(side='left')
            for text, command in [('删除', lambda k=key: self.delete_attr(k)), ('复制', lambda k=key: self.edit_attr(k, 'copy')),
                                  ('修改', lambda k=key: self.edit_attr(k, 'edit')), ('添加', lambda k=key: self.edit_attr(k, 'add'))]:
                ttk.Button(title, text=text, command=command, width=5).pack(side='right', padx=2)
            tree = self.make_tree(box, [('type', '属性', 180), ('raw', '原始值', 100), ('shown', '换算值', 120), ('flag', '标记', 100)], height=count)
            tree.bind('<Double-1>', lambda _, k=key: self.edit_attr(k, 'edit')); self.attr_trees[key] = tree
        ttk.Label(self.equipment_tools.body, text='百分比按游戏原始单位存储，换算值供核对。蓝字加成作用于本装备的同名铸造属性。\n铸造属性可重复；达到 7 条时需替换或删除已有词条。\n直接设置强化等级不自动重算词条数值；请在上方单独编辑数值。', style='Sub.TLabel',wraplength=760).pack(anchor='w',pady=(8,4))
        static = self.scroll_page(notebook, '强化效果（同型号装备共同使用）')
        ttk.Label(static, textvariable=self.effect_note, foreground='#a65c16', wraplength=830).pack(anchor='w', pady=(0, 8))
        ttk.Label(static, text='数值效果 · 支持重复添加及按等级解锁', font=('Microsoft YaHei UI', 11, 'bold')).pack(anchor='w')
        self.effect_attrs = self.make_tree(static, [('level', '解锁 +', 65), ('type', '属性', 165), ('value', '原始值 / 换算值', 190), ('martial', '指定武学 ID', 115)], height=3)
        self.effect_attrs.bind('<Double-1>', lambda _: self.edit_effect('attrs', 'edit'))
        self.effect_buttons(static, 'attrs')
        ttk.Label(static, text='天赋效果 · 可重复保存相同天赋 ID', font=('Microsoft YaHei UI', 11, 'bold')).pack(anchor='w', pady=(12, 0))
        self.effect_gifts = self.make_tree(static, [('level', '解锁 +', 65), ('name', '天赋', 220), ('desc', '效果说明', 380)], height=5)
        self.effect_gifts.bind('<Double-1>', lambda _: self.edit_effect('gifts', 'edit'))
        self.effect_buttons(static, 'gifts')
        ttk.Label(static, text='强化效果列表可以重复添加（工具每型号上限 4096 条）。\n保存会同步逻辑表和客户端配置，并备份客户端资源文件（约 391 MB）。\n天赋重复条目能保存和显示；战斗中是否叠加取决于游戏对该天赋的处理，尚未实测。', style='Sub.TLabel', wraplength=830).pack(anchor='w', pady=10)
        ttk.Button(static, text='撤销此型号的强化效果修改', command=self.revert_effects).pack(anchor='e')

    def build_caps_page(self, parent):
        ttk.Label(parent,text='武学等级上限',style='Title.TLabel').pack(anchor='w')
        ttk.Label(parent,text='全难度统一设置，包含已保存的自建武学，适用于现有存档、新开档及后续周目。启用后新建武学自动继承上限 30。',style='Sub.TLabel').pack(anchor='w',pady=(5,16))
        card = ttk.Frame(parent,style='Card.TFrame',padding=20); card.pack(fill='x')
        ttk.Label(card,textvariable=self.cap_status,style='CardTitle.TLabel',wraplength=1120).pack(anchor='w')
        ttk.Label(card,text='仅调整可修炼的等级上限，已学武学的等级和经验保持原值。',style='Card.TLabel').pack(anchor='w',pady=(8,16))
        buttons = ttk.Frame(card,style='Card.TFrame'); buttons.pack(fill='x')
        ttk.Button(buttons,text='一键全难度武学上限 30',style='Primary.TButton',command=lambda:self.run_caps(True)).pack(side='left')
        ttk.Button(buttons,text='还原原等级上限',command=lambda:self.run_caps(False)).pack(side='left',padx=12)
        ttk.Button(buttons,text='刷新状态',command=self.refresh_caps).pack(side='right')
        ttk.Label(parent,text='当前配置',font=('Microsoft YaHei UI',12,'bold')).pack(anchor='w',pady=(22,8))
        self.cap_tree = self.make_tree(parent,[('scope','范围',180),('kind','上限项目',240),('count','配置数量',100),('value','当前等级上限',240)],height=5)
        ttk.Label(parent,text='点击按钮后直接应用，并自动备份。请先完全退出游戏。\n还原只恢复上限配置，保留其他装备修改；如需撤销一次操作，可使用装备页的“备份恢复”。',style='Sub.TLabel',wraplength=1150).pack(anchor='w',pady=(16,4))
        self.cap_progress = ttk.Progressbar(parent,mode='indeterminate'); self.cap_progress.pack(fill='x',pady=(8,0))

    def refresh_caps(self):
        if not self.catalog: return
        if Path(self.game_path.get()).resolve()!=self.catalog.root:
            self.cap_status.set('目录已变化，请先读取目录'); return
        try:
            rows, unified = cap_summary(self.catalog.root)
            labels={'Difficult':'全部难度','CommonConfig':'通用设置','Martial':'全部武学'}
            names={'MartialLvMax':'武学最终上限','DefaultMartialLVMax':'默认修炼上限',
                   'DefaultMartialMaxLevel':'默认修炼上限','MartialMaxLevelFinal':'武学最终上限','LvLimit':'武学自身上限'}
            self.cap_tree.delete(*self.cap_tree.get_children())
            for table,key,count,value in rows:self.cap_tree.insert('','end',values=(labels[table],names[key],count,value))
            self.cap_status.set('当前逻辑配置：全难度武学上限 30' if unified else '当前逻辑配置：保留各项等级上限')
        except Exception as error:self.cap_status.set('无法读取武学上限：'+str(error))

    def run_caps(self, enable):
        if self.busy:return
        try:
            if not self.catalog:raise ValueError('请先读取游戏目录')
            if Path(self.game_path.get()).resolve()!=self.catalog.root:raise ValueError('目录已变化，请先读取目录')
            if self.has_changes():raise ValueError('请先保存或撤销装备草稿，再修改武学上限')
            ensure_closed()
        except Exception as error:self.error(error);return
        action='设置全难度武学上限 30' if enable else '还原原等级上限'
        self.busy=True; self.status.set('正在'+action+'，验证配置并准备备份…');self.cap_progress.start(15)
        disabled=[]
        def lock(widget):
            if isinstance(widget,(ttk.Button,ttk.Entry,ttk.Combobox,ttk.Spinbox)):
                disabled.append((widget,widget.cget('state')));widget.configure(state='disabled')
            for child in widget.winfo_children():lock(child)
        lock(self)
        result=queue.Queue();root=self.catalog.root
        def worker():
            try:
                ensure_closed();notes=[];payloads,originals=plan_caps(root,enable,notes)
                backup=transaction(root,payloads,originals,action)
                result.put((True,(backup,notes)))
            except Exception as error:result.put((False,error))
        threading.Thread(target=worker,daemon=True).start()
        def poll():
            try:ok,value=result.get_nowait()
            except queue.Empty:self.after(100,poll);return
            self.busy=False;self.cap_progress.stop()
            for widget,state in disabled:widget.configure(state=state)
            if ok:
                value,notes=value
                # Reload config snapshots so later equipment saves do not use
                # resource offsets or hashes from before this operation.
                self.martial_page.reset();self.role_page.reset();self.reload();self.refresh_caps()
                text=action+'完成。重启游戏并读取存档后生效。' if value else '当前配置已符合目标，无需重复修改。'
                self.status.set(text+(f' 备份：{value}' if value else ''))
                if notes:
                    report=root/'装备编辑器配置/武学上限跳过报告.txt'
                    report.parent.mkdir(exist_ok=True)
                    try: report.write_text('\n'.join(dict.fromkeys(notes)),encoding='utf-8')
                    except OSError: pass
                    text+=f'\n已跳过 {len(set(notes))} 项，保持原值。\n报告：{report}'
                messagebox.showinfo('武学上限',text+(f'\n\n备份：{value}' if value else ''),parent=self)
            else:self.error(value);self.status.set('操作未完成：'+str(value))
        self.after(100,poll)

    def make_tree(self, parent, columns, height=None):
        frame = ttk.Frame(parent,style='Paper.TFrame',padding=5); frame.pack(fill='both', expand=True, pady=(5, 0))
        args = {'height': height if height is not None else 6}
        from desktop_theme import DataTree
        tree = DataTree(frame, columns=[x[0] for x in columns], show='headings', selectmode='browse', **args)
        for key, label, width in columns: tree.heading(key, text=label); tree.column(key, width=width, minwidth=45)
        frame.rowconfigure(0,weight=1);frame.columnconfigure(0,weight=1)
        tree.grid(row=0,column=0,sticky='nsew')
        scroll = ttk.Scrollbar(frame, orient='vertical', command=tree.yview);scroll.grid(row=0,column=1,sticky='ns')
        horizontal=ttk.Scrollbar(frame,orient='horizontal',command=tree.xview);horizontal.grid(row=1,column=0,sticky='ew')
        tree.configure(yscrollcommand=scroll.set,xscrollcommand=horizontal.set)
        return tree

    def scroll_page(self, notebook, label):
        page = ttk.Frame(notebook); notebook.add(page, text=label)
        canvas = tk.Canvas(page, highlightthickness=0, background='#fcfaf6')
        canvas.pack(side='left', fill='both', expand=True)
        scrollbar = ttk.Scrollbar(page, orient='vertical', command=canvas.yview); scrollbar.pack(side='right', fill='y')
        canvas.configure(yscrollcommand=scrollbar.set)
        interior = ttk.Frame(canvas, padding=12)
        item = canvas.create_window((0, 0), window=interior, anchor='nw')
        interior.bind('<Configure>', lambda _: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda event: canvas.itemconfigure(item, width=event.width))
        def wheel(event):
            widget = event.widget
            if isinstance(widget,(ttk.Treeview,ttk.Combobox,ttk.Spinbox)):return
            while widget is not None:
                if widget is interior:
                    canvas.yview_scroll(-int(event.delta/120),'units');return
                widget=getattr(widget,'master',None)
        self.bind_all('<MouseWheel>',wheel,add='+')
        return interior

    def effect_buttons(self, parent, key):
        bar = ttk.Frame(parent); bar.pack(fill='x', pady=(5, 0))
        for label, mode in [('添加', 'add'), ('修改', 'edit'), ('复制', 'copy')]:
            ttk.Button(bar, text=label, command=lambda k=key, m=mode: self.edit_effect(k, m)).pack(side='left', padx=(0, 6))
        ttk.Button(bar, text='删除', command=lambda k=key: self.delete_effect(k)).pack(side='left')

    def error(self, error): messagebox.showerror('操作未完成', str(error), parent=self)
    def has_changes(self): return bool(self.drafts or self.effects or (getattr(self,'martial_page',None) and self.martial_page.has_changes()) or (getattr(self,'role_page',None) and self.role_page.has_changes()))
    def discard_ok(self):
        return not self.has_changes() or messagebox.askyesno('未保存的修改', '将丢弃当前草稿，继续读取？', parent=self)
    def browse(self):
        selected = filedialog.askdirectory(title='选择游戏目录', initialdir=self.game_path.get(), parent=self)
        if selected:
            self.game_path.set(selected); self.load_game()
    def load_game(self):
        if self.busy:return
        if not self.discard_ok(): return
        root=self.game_path.get()
        def finish(catalog):
            self.catalog = catalog
            if getattr(self,'martial_page',None):self.martial_page.reset()
            if getattr(self,'role_page',None):self.role_page.reset()
            self.refresh_caps()
            self.save = None; self.items.delete(*self.items.get_children()); self.visible_records.clear()
            self.item_cursor.update([]);self.item_cursor.filter();self.item_pages.sync();self._equipment_source=None
            self.active_save_index = None
            self.saves = catalog.saves()
            labels = [f'{name}  ·  {__import__("datetime").datetime.fromtimestamp(path.stat().st_mtime):%m-%d %H:%M}' for name, path in self.saves]
            self.save_box['values'] = labels; self.drafts.clear(); self.effects.clear(); self.current = None
            if not labels:
                self.status.set('游戏配置已读取，目录中没有发现 Save.sav 存档。');return
            self.save_box.current(0); self.load_save(confirmed=True)
            PREFS.parent.mkdir(parents=True, exist_ok=True); PREFS.write_text(json.dumps({'game_path': str(catalog.root)}, ensure_ascii=False), encoding='utf-8')
        from library_cache import load_catalog
        self.martial_page.worker('正在读取游戏配置与存档列表…',lambda:load_catalog(root),finish)
    def load_save(self, confirmed=False):
        if not self.catalog: return
        if not confirmed and not self.discard_ok():
            if self.active_save_index is not None: self.save_box.current(self.active_save_index)
            return
        try:
            index = self.save_box.current()
            if index < 0: return
            self.status.set('正在验证并读取完整装备表…'); self.update_idletasks()
            save = Save(self.saves[index][1], self.catalog)
            if getattr(self,'martial_page',None) and self.martial_page.has_changes():self.martial_page.reset()
            if getattr(self,'role_page',None) and self.role_page.has_changes():self.role_page.reset()
            self.active_save_index = index
            self.save = save; self.current = None; self.drafts.clear(); self.effects.clear(); self.refresh_items()
            skipped = f'（{skipped_records_note(save)}）' if save.ignored_count else ''
            self.status.set(f'已读取 {self.saves[index][0]}：{sum(r["editable"] for r in save.records)} 件装备{skipped}；请从左侧选择装备。' +
                            __import__('compatibility').status(self.catalog))
        except Exception as error:
            if self.active_save_index is not None: self.save_box.current(self.active_save_index)
            self.error(error); self.status.set(str(error))
    def reload(self):
        if not self.discard_ok(): return
        index = self.save_box.current()
        try:
            from library_cache import load_catalog
            self.catalog = load_catalog(self.game_path.get()); self.saves = self.catalog.saves()
            self.save_box.current(min(max(index, 0), len(self.saves) - 1)); self.load_save(confirmed=True)
        except Exception as error: self.error(error)
    def schedule_item_search(self):
        if self._item_search_job:self.after_cancel(self._item_search_job)
        self._item_search_job=self.after(150,self.refresh_items)
    def refresh_items(self):
        if self._item_search_job:self.after_cancel(self._item_search_job);self._item_search_job=None
        if not self.save:return
        if self._equipment_source is not self.save:
            self.item_cursor.update(Entry(r['offset'],r,f"{r['name']} {r['id']} {r['type']}".casefold(),self.save.location(r)) for r in self.save.records if r['editable'])
            self._equipment_source=self.save;self.item_cursor.first()
        self.item_cursor.filter(self.search.get(),'' if self.scope.get()=='全部装备' else self.scope.get())
        self.render_item_page()
    def render_item_page(self):
        if not self.save:return
        old = self.current['offset'] if self.current else None
        self.loading = True; self.items.delete(*self.items.get_children()); self.visible_records = {}
        for entry in self.item_cursor.page():
            record=entry.value;location=entry.scope
            off = record['offset']; iid = str(off); self.visible_records[iid] = record
            draft = self.drafts.get(off); grade = draft['grade'] if draft else record['grade']
            marker = ' *' if draft or record['type'] in self.effects else ''
            self.items.insert('', 'end', iid=iid, values=(record['name'] + marker, f'+{grade}', location))
        self.loading = False
        self.item_pages.sync()
        skipped = f' · {skipped_records_note(self.save)}' if self.save.ignored_count else ''
        self.count_label.configure(text=f'本页 {len(self.visible_records)} 件{skipped} · * 表示有待保存修改')
        if old is not None and str(old) in self.visible_records: self.items.selection_set(str(old)); self.items.see(str(old))
        elif self.visible_records: self.items.selection_set(next(iter(self.visible_records)))
        else:
            self.current = None; self.detail.set('此范围没有装备；可切换存档或查看全部装备')
            self.effect_note.set('选择左侧装备后显示该型号的强化效果。')
            self.loading = True; self.grade.set('0'); self.loading = False
            for tree in list(self.attr_trees.values()) + [self.effect_attrs, self.effect_gifts]: tree.delete(*tree.get_children())
    def select_item(self, event=None):
        if self.loading or not self.items.selection(): return
        record=self.visible_records.get(self.items.selection()[0])
        if record is None:return
        self.current = record; self.render_details()
    def current_draft(self):
        return copy.deepcopy(self.drafts.get(self.current['offset'], self.save.draft(self.current)))
    def current_effect(self):
        return copy.deepcopy(self.effects.get(self.current['type'], effect_draft(self.catalog.items[self.current['type']])))
    def render_details(self):
        if not self.current: return
        record = self.current; self.loading = True
        draft = self.current_draft(); self.grade.set(str(draft['grade']))
        self.detail.set(f"{record['name']} · 实例 {record['id']} · 型号 {record['type']}\n{self.save.location(record)} · 脚本编号 {record['script']}")
        for key, tree in self.attr_trees.items():
            tree.delete(*tree.get_children())
            for index, row in enumerate(draft[key]):
                converted = f"{row['value']}%" if key == 'blue' else self.catalog.format_value(row['type'], row['value'])
                tree.insert('', 'end', iid=str(index), values=(f"{self.catalog.attr(row['type'])} ({row['type']})", row['value'], converted,
                                                             '固定' if row['fixed'] else '可重铸' if key == 'green' else ''))
        effects = self.current_effect(); self.effect_attrs.delete(*self.effect_attrs.get_children()); self.effect_gifts.delete(*self.effect_gifts.get_children())
        for index, row in enumerate(effects['attrs']):
            self.effect_attrs.insert('', 'end', iid=str(index), values=(row['level'], self.catalog.attr(row['type']),
                                    f"{row['value']} / {self.catalog.format_value(row['type'], row['value'])}", row['martial'] or '全部/无指定'))
        for index, row in enumerate(effects['gifts']):
            self.effect_gifts.insert('', 'end', iid=str(index), values=(row['level'], self.catalog.gift_label(row['id']), self.catalog.gift_desc(row['id']).replace('\n', ' ')))
        same = sum(x['type'] == record['type'] for x in self.save.records)
        sources = getattr(self.catalog, 'item_sources', {}).get(record['type'], [])
        source = '、'.join(p.name for p in sources) if sources else self.catalog.effect_source
        notes = '；'.join(record.get('compatibility_warnings', []))
        self.effect_note.set(f'型号 {record["type"]} · 来源：{source} · 当前存档有 {same} 件。修改影响全部存档中同型号装备。'
                             + (' MOD 效果保存将备份并更新来源 JSON。' if record['type'] in self.catalog.other_item_overrides else '')
                             + ('\n'+notes if notes else ''))
        self.loading = False
    def stage_item(self, draft):
        off = self.current['offset']
        if draft == self.save.draft(self.current): self.drafts.pop(off, None)
        else: self.drafts[off] = draft
        self.mark_status(); self.render_details(); self.refresh_items()
    def stage_effect(self, draft):
        ident = self.current['type']
        if draft == effect_draft(self.catalog.items[ident]): self.effects.pop(ident, None)
        else: self.effects[ident] = draft
        self.mark_status(); self.render_details(); self.refresh_items()
    def mark_status(self): self.status.set(f'待保存：{len(self.drafts)} 件装备的存档修改，{len(self.effects)} 种型号的强化效果修改。原文件尚未写入。')
    def grade_changed(self, *_):
        if self.loading or not self.current: return
        try:
            value = int(self.grade.get())
            if not 0 <= value <= 20: return
            draft = self.current_draft(); draft['grade'] = value
            off = self.current['offset']
            if draft == self.save.draft(self.current): self.drafts.pop(off, None)
            else: self.drafts[off] = draft
            self.mark_status()
            iid = str(off); vals = list(self.items.item(iid, 'values'))
            vals[1] = f'+{value}'; vals[0] = self.current['name'] + (' *' if off in self.drafts or self.current['type'] in self.effects else '')
            self.items.item(iid, values=vals)
        except ValueError: pass
    def attr_choices(self): return [(int(i), f'{i} · {name}') for i, name in META['attributes'].items()]
    def selected_index(self, tree): return int(tree.selection()[0]) if tree.selection() else None
    def edit_attr(self, key, mode):
        if self.busy or not self.current: return
        draft = self.current_draft(); rows = draft[key]; index = self.selected_index(self.attr_trees[key])
        if mode in ('edit', 'copy') and index is None: return
        if mode != 'edit' and len(rows) >= GROUPS[key][1]: self.error(ValueError('该组槽位已满，请修改或删除现有词条')); return
        if mode == 'copy': rows.append(copy.deepcopy(rows[index])); self.stage_item(draft); return
        initial = rows[index] if mode == 'edit' else {'type': 145, 'value': 1000, 'fixed': False}
        if key != 'green': initial = {k: v for k, v in initial.items() if k != 'fixed'}
        dialog = Picker(self, GROUPS[key][0], self.attr_choices(), initial, [('value', '原始数值（0～2097151）', 1000)],
                        description=lambda ident: f"{self.catalog.attr(ident)}；10000 的换算显示：{self.catalog.format_value(ident, 10000)}")
        if not dialog.result: return
        row, _ = dialog.result; row['type'] = row.pop('id'); row.setdefault('fixed', False)
        if not 0 <= row['value'] <= 0x1fffff: self.error(ValueError('数值范围为 0～2097151')); return
        if mode == 'edit': rows[index] = row
        else: rows.append(row)
        self.stage_item(draft)
    def delete_attr(self, key):
        if not self.current: return
        index = self.selected_index(self.attr_trees[key])
        if index is None: return
        draft = self.current_draft(); draft[key].pop(index); self.stage_item(draft)
    def edit_effect(self, key, mode):
        if self.busy or not self.current: return
        draft = self.current_effect(); rows = draft[key]
        tree = self.effect_attrs if key == 'attrs' else self.effect_gifts; index = self.selected_index(tree)
        if mode in ('edit', 'copy') and index is None: return
        if mode == 'copy': rows.append(copy.deepcopy(rows[index])); self.stage_effect(draft); return
        initial = rows[index] if mode == 'edit' else {'id': 1497, 'type': 18, 'value': 18000, 'level': 5, 'martial': 0}
        if key == 'attrs':
            initial = {k: v for k, v in initial.items() if k != 'id'}
            choices = self.attr_choices(); fields = [('value', '原始数值（32 位整数）', 18000), ('level', '解锁等级（0～20）', 5), ('martial', '武学 ID（0 表示不指定）', 0)]
            description = lambda ident: f"{self.catalog.attr(ident)}；10000 的换算显示：{self.catalog.format_value(ident, 10000)}"
        else:
            choices = [(ident, self.catalog.gift_label(ident)) for ident in sorted(self.catalog.gifts)]
            fields = [('level', '解锁等级（0～20）', 10)]; description = self.catalog.gift_desc
        dialog = Picker(self, '修改强化效果' if mode == 'edit' else '添加强化效果', choices, initial, fields, description, allow_repeat=mode != 'edit')
        if not dialog.result: return
        row, repeats = dialog.result
        if not 0 <= row['level'] <= 20: self.error(ValueError('解锁等级范围为 0～20')); return
        if key == 'attrs':
            row['type'] = row.pop('id')
            if not -2147483648 <= row['value'] <= 2147483647: self.error(ValueError('原始值超出 32 位整数范围')); return
            if row['martial'] and row['martial'] not in self.catalog.martials: self.error(ValueError('找不到该武学 ID')); return
        if mode == 'edit': rows[index] = row
        else: rows.extend(copy.deepcopy(row) for _ in range(repeats))
        if len(draft['gifts']) + len(draft['attrs']) > 4096: self.error(ValueError('单型号强化效果超过工具上限 4096 条')); return
        self.stage_effect(draft)
    def delete_effect(self, key):
        if not self.current: return
        tree = self.effect_attrs if key == 'attrs' else self.effect_gifts; index = self.selected_index(tree)
        if index is None: return
        draft = self.current_effect(); draft[key].pop(index); self.stage_effect(draft)
    def revert_item(self):
        if self.current: self.drafts.pop(self.current['offset'], None); self.mark_status(); self.render_details(); self.refresh_items()
    def revert_effects(self):
        if self.current: self.effects.pop(self.current['type'], None); self.mark_status(); self.render_details(); self.refresh_items()
    def validate_grade(self):
        if self.current:
            value = int(self.grade.get())
            if not 0 <= value <= 20: raise ValueError('强化等级范围为 0～20')
    def prepare(self):
        if not self.save or not self.catalog: raise ValueError('请先读取游戏与存档')
        if Path(self.game_path.get()).resolve() != self.catalog.root: raise ValueError('游戏目录输入已变化，请先点击读取目录')
        if getattr(self,'martial_page',None) and self.martial_page.has_changes(): raise ValueError('请先在武学页保存或撤销武学草稿，再保存装备修改')
        if getattr(self,'role_page',None) and self.role_page.has_changes(): raise ValueError('请先在人物页保存或撤销人物草稿，再保存装备修改')
        self.validate_grade()
        result = effect_payloads(self.catalog, self.effects, skip_errors=True)
        self.save.last_record_skips = {}
        if self.drafts: result[self.save.path] = self.save.patched(self.drafts, skip_errors=True)
        self._last_save_skips = {'effects': dict(self.catalog.last_effect_skips),
                                 'records': dict(getattr(self.save, 'last_record_skips', {}))}
        originals = dict(self.catalog.snapshots); originals[self.save.path] = self.save.data
        originals[self.catalog.own_json] = self.catalog.own_original
        return result, originals
    def write(self):
        if self.busy:return
        if not self.has_changes(): messagebox.showinfo('没有待保存修改', '当前没有修改草稿。', parent=self); return
        try:
            ensure_closed();self.validate_grade()
        except Exception as error:self.error(error);return
        def work():
            result, originals = self.prepare()
            # Recheck every table/mod source used to build the reviewable draft.
            for path, data in self.catalog.snapshots.items():
                if path.read_bytes() != data: raise ValueError(f'配置在读取后发生变化，请重新读取：{path}')
            return transaction(self.catalog.root, result, originals)
        def finish(backup):
            skips = getattr(self, '_last_save_skips', {'effects': {}, 'records': {}})
            retained_effects = {i:d for i,d in self.effects.items() if i in skips['effects']}
            retained_records = {i:d for i,d in self.drafts.items() if i in skips['records']}
            details = '\n'.join([f'型号 {i}：{e}' for i,e in skips['effects'].items()] +
                                [f'装备记录 {i}：{e}' for i,e in skips['records'].items()])
            if backup is None:
                self.status.set('没有可写入的改动；异常项保留草稿。'+details)
                messagebox.showinfo('已跳过异常项', self.status.get(), parent=self); return
            self.drafts.clear(); self.effects.clear(); self.martial_page.reset(); self.role_page.reset(); self.reload()
            self.drafts.update(retained_records); self.effects.update(retained_effects); self.refresh_items()
            self.status.set(f'保存完成。原文件备份：{backup}')
            if details:self.status.set(f'兼容项已保存，跳过 {len(retained_effects)+len(retained_records)} 项（草稿保留）。备份：{backup}')
            messagebox.showinfo('保存完成', f'兼容项已写入并验证。\n\n原文件备份：\n{backup}' +
                                ('\n\n以下异常项已跳过，草稿保留：\n'+details if details else '') +
                                '\n\n请启动游戏并读取刚才选择的存档。', parent=self)
        self.martial_page.worker('正在回读验证、记录日志、备份并保存…',work,finish)
    def export(self):
        if not self.has_changes(): messagebox.showinfo('没有待导出修改', '请先编辑至少一条词条或效果。', parent=self); return
        try:
            result, originals = self.prepare()
            folder = filedialog.askdirectory(title='选择空目录，导出副本（不会修改游戏文件）', parent=self)
            if not folder: return
            folder = Path(folder).resolve()
            if folder.is_relative_to(self.catalog.root): raise ValueError('请选择游戏目录之外的导出目录')
            target = folder / ('装备修改副本_' + __import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
            target.mkdir(); entries = []
            for path, data in result.items():
                relative = path.relative_to(self.catalog.root); dest = target / relative
                dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes(data); entries.append(str(relative))
            (target / '导出说明.txt').write_text('这些文件是修改副本，尚未安装。请通过编辑器的保存按钮写入并自动备份。\n文件：\n' + '\n'.join(entries), encoding='utf-8')
            self.status.set(f'已导出副本：{target}。游戏原文件未修改。'); os.startfile(target)
        except Exception as error: self.error(error)
    def restore_all_dialog(self):
        if self.busy:return
        try:
            if not self.catalog:raise ValueError('请先读取游戏目录')
            if Path(self.game_path.get()).resolve()!=self.catalog.root:raise ValueError('目录已变化，请先读取目录')
            ensure_closed()
        except Exception as error:self.error(error);return
        root=self.catalog.root
        def reviewed(plan):
            drafts=self.has_changes()
            if not plan.files and not drafts:
                messagebox.showinfo('没有可还原的修改','未发现可用的已完成备份，也没有未保存的草稿。',parent=self);return
            dialog=RestoreAllDialog(self,plan,drafts)
            if not dialog.result:self.status.set('已取消还原，当前文件与草稿保持原样。');return
            def finished(backup):
                self.drafts.clear();self.effects.clear();self.current=None
                self.martial_page.reset()
                if getattr(self,'role_page',None):self.role_page.reset()
                index=self.active_save_index
                self.save=None;self.items.delete(*self.items.get_children());self.visible_records.clear()
                self.active_save_index=None;self.save_box.configure(values=[])
                # Refresh all configuration snapshots, even if no save is loaded.
                try:
                    self.catalog=Catalog(root);self.saves=self.catalog.saves()
                    labels=[f'{name} · {__import__("datetime").datetime.fromtimestamp(path.stat().st_mtime):%m-%d %H:%M}' for name,path in self.saves]
                    self.save_box.configure(values=labels)
                    self.refresh_caps()
                    if labels:
                        self.save_box.current(min(index or 0,len(labels)-1));self.load_save(confirmed=True)
                    else:self.detail.set('还原完成，请重新读取游戏目录与存档')
                except Exception as error:
                    self.catalog=None;self.save=None;self.error(ValueError('还原已完成，重新读取配置失败：'+str(error)))
                    self.status.set('还原已完成，重新读取失败；请重新读取游戏目录。');return
                kept=f'已按清单保留 {len(plan.preserved)} 个外部MOD文件。' if plan.preserved else ''
                self.status.set('所有可还原修改已恢复。'+kept+(f'还原前备份：{backup}' if backup else '已撤销未保存草稿；文件无需重复还原。'))
                messagebox.showinfo('还原完成','已还原可安全恢复的装备、武学及其他修改。'+kept+(f'\n\n还原前备份：\n{backup}\n\n可用“备份恢复”撤销本次还原。' if backup else '\n文件无需写入，草稿已撤销。'),parent=self)
            self.martial_page.worker('正在备份当前状态并还原所有修改…',lambda:apply_restore_all(plan),finished)
        self.martial_page.worker('正在校验备份并生成全部还原清单…',lambda:plan_restore_all(root),reviewed)

    def show_change_logs(self):
        from change_ui import show_logs
        show_logs(self)

    def read_change_effects(self):
        from change_ui import import_changes
        import_changes(self)

    def export_change_effects(self):
        from change_ui import export_changes
        export_changes(self)

    def restore_dialog(self):
        if not self.catalog: return
        if not self.discard_ok(): return
        selected = filedialog.askopenfilename(title='选择备份的 manifest.json', initialdir=str(self.catalog.root / '装备编辑器备份'), filetypes=[('备份清单', 'manifest.json')], parent=self)
        if not selected: return
        try:
            manifest = json.loads(Path(selected).read_text(encoding='utf-8'))
            paths = '\n'.join(entry['path'] for entry in manifest['entries'])
            if not messagebox.askyesno('恢复指定备份', f'将恢复以下文件到这次编辑之前，当前版本也会备份：\n\n{paths}\n\n继续恢复？', parent=self): return
            backup = restore(self.catalog.root, selected)
            self.drafts.clear(); self.effects.clear(); self.martial_page.reset(); self.role_page.reset(); self.reload(); self.refresh_caps(); self.status.set(f'恢复完成。恢复前备份：{backup}')
            messagebox.showinfo('恢复完成', f'所选备份已恢复。\n恢复前版本：{backup}', parent=self)
        except Exception as error: self.error(error)
    def close(self):
        if self.busy:
            messagebox.showinfo('正在保存','请等待配置保存或回滚完成后再关闭。',parent=self);return
        if self.has_changes() and not messagebox.askyesno('未保存的修改', '关闭应用会丢弃当前草稿，继续关闭？', parent=self): return
        self.destroy()

if __name__ == '__main__':
    try:
        ctypes = __import__('ctypes'); ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception: pass
    app = Application()
    from feature_ui import select_launcher
    app.after(400,lambda:select_launcher(app))
    app.mainloop()
