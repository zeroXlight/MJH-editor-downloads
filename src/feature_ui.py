"""Extensible function page. Preview first; apply only the prepared save bytes."""
import tkinter as tk
from tkinter import ttk,messagebox
from pathlib import Path
from feature_save import LABELS,plan,apply

DESCRIPTIONS={
 'meridian_exp':'每次确认应用，向所选存档当前经脉经验累加 900000；再次使用继续累加。\n与奇经八脉、宠物解锁及培养共用同一余额，不改变每周获取上限或已用点数。请先退出游戏，预览后应用并备份。',
 'collection':'为新增普通武学补齐全局收藏初始记录（10级基础上限），保留已有残章和突破进度。\n不会补发残章；拾取残章至20级后，沿用原版对应品质的残文消耗继续突破。秘奥义等不可收集武学跳过。',
 'resources':'铜钱设为 1 亿；天工锤设为 999，精铁和完美粉各设为 99999。\n已持有且能唯一识别的飞马令／幸运珠／珍稀武学丹／珍稀经验丹设为 100／999／999／999。数值会设为目标值；缺少或不明确的道具跳过。',
 'fragments':'读取当前游戏可识别的可见武学，补足残章解锁值到 10，对应原版 20 级上限；同时补入当天残章日志。\n已有更多残章保持原值；不会直接学习武学，也不会修改已学等级或覆盖“武学上限 30”设置。',
 'achievements':'按当前游戏成就目标补足完成进度，并解锁当前配置中可识别的最高难度。\n保留成就奖励领取状态；不会调用 Steam 成就接口，也不切换当前周目的难度。'}

class FeaturePanel:
    def __init__(self,host,parent):
        self.host=host; self.prepared=None; self.signature=None; self.saves=[]
        self.action=tk.StringVar(value=next(iter(LABELS.values())))
        self.slot=tk.StringVar(); self.all_saves=tk.BooleanVar(value=False)
        self.description=tk.StringVar(); self.note=tk.StringVar(value='选择功能和存档，预览后确认应用。')
        ttk.Label(parent,text='存档功能',style='Title.TLabel').pack(anchor='w')
        bar=ttk.Frame(parent);bar.pack(fill='x',pady=10)
        ttk.Label(bar,text='功能').pack(side='left')
        box=ttk.Combobox(bar,textvariable=self.action,values=list(LABELS.values()),state='readonly',width=28);box.pack(side='left',padx=8)
        box.bind('<<ComboboxSelected>>',lambda _:self.invalidate())
        ttk.Button(bar,text='刷新存档',command=self.refresh).pack(side='left')
        row=ttk.Frame(parent);row.pack(fill='x',pady=5)
        self.box=ttk.Combobox(row,textvariable=self.slot,state='readonly',width=38);self.box.pack(side='left')
        self.box.bind('<<ComboboxSelected>>',lambda _:self.invalidate())
        ttk.Checkbutton(row,text='处理全部存档（不兼容的存档单独跳过）',variable=self.all_saves,command=self.invalidate).pack(side='left',padx=12)
        ttk.Label(parent,textvariable=self.description,wraplength=1100,style='Sub.TLabel').pack(anchor='w',pady=10)
        buttons=ttk.Frame(parent);buttons.pack(fill='x',pady=8)
        ttk.Button(buttons,text='预览修改',command=self.preview).pack(side='left')
        ttk.Button(buttons,text='确认应用并备份',style='Primary.TButton',command=self.commit).pack(side='left',padx=10)
        ttk.Label(parent,textvariable=self.note,wraplength=1100).pack(anchor='w',pady=8)
        frame=ttk.Frame(parent);frame.pack(fill='both',expand=True)
        self.report=tk.Text(frame,height=12,wrap='word');self.report.pack(side='left',fill='both',expand=True)
        scroll=ttk.Scrollbar(frame,command=self.report.yview);scroll.pack(side='right',fill='y');self.report.configure(yscrollcommand=scroll.set,state='disabled')
        self.invalidate()
    def action_key(self): return next(k for k,v in LABELS.items() if v==self.action.get())
    def invalidate(self):
        self.prepared=None;self.signature=None;self.description.set(DESCRIPTIONS[self.action_key()])
        self.note.set('请预览当前选择，确认后再应用。')
    def refresh(self):
        if self.host.busy:return
        self.invalidate();root=Path(self.host.game_path.get()).resolve()
        self.saves=[]
        if (root/'Save.sav').is_file():self.saves.append(('自动存档',root/'Save.sav'))
        self.saves.extend((p.parent.name,p) for p in sorted((root/'SaveFile').glob('*/Save.sav')))
        self.box.configure(values=[n for n,p in self.saves])
        if self.saves:self.box.current(next((i for i,(n,p) in enumerate(self.saves) if n=='存档1'),0))
        else:self.slot.set('');self.note.set('未找到存档，请检查上方游戏目录。')
    def selections(self):
        root=Path(self.host.game_path.get()).resolve()
        if not self.host.catalog or root!=self.host.catalog.root:raise ValueError('请先读取当前游戏目录')
        if self.host.has_changes():raise ValueError('请先保存或撤销未保存的草稿')
        if not self.saves:raise ValueError('请先刷新并选择存档')
        paths=[p for n,p in self.saves] if self.all_saves.get() else [p for n,p in self.saves if n==self.slot.get()]
        if not paths:raise ValueError('请选择存档')
        return root,paths,self.action_key()
    def show(self,text):
        self.report.configure(state='normal');self.report.delete('1.0','end');self.report.insert('1.0',text);self.report.configure(state='disabled')
    def preview(self):
        if self.host.busy:return
        try:root,paths,action=self.selections()
        except Exception as error:self.host.error(error);return
        self.prepared=None
        def finish(prepared):
            self.prepared=prepared;self.signature=(root,paths,action)
            payloads,originals,results,notes,reads=prepared
            self.note.set(f'可写入 {len(payloads)} 个存档；提醒／跳过 {len(notes)} 项。预览不会修改游戏。')
            self.show('\n'.join(results+['','处理详情：']+notes) if notes else '\n'.join(results)+'\n没有跳过项目。')
        self.host.martial_page.worker('正在检查存档和当前游戏配置…',lambda:plan(root,paths,action),finish)
    def commit(self):
        if self.host.busy:return
        try:
            if self.prepared is None or self.selections()!=self.signature:raise ValueError('请先预览当前选择')
            if not self.prepared[0]:raise ValueError('没有需要写入的存档，请查看预览详情')
        except Exception as error:self.host.error(error);return
        root,paths,action=self.signature;prepared=self.prepared
        if not messagebox.askyesno('确认功能修改',f'{LABELS[action]}\n将修改 {len(prepared[0])} 个存档并自动备份。\n请完全退出游戏后继续。',parent=self.host):return
        def finish(backup):
            report=root/'装备编辑器配置/功能修改最近报告.txt';report.parent.mkdir(exist_ok=True)
            text='\n'.join([LABELS[action],f'备份：{backup}']+prepared[2]+prepared[3])
            try:report.write_text(text,encoding='utf-8')
            except OSError:pass
            self.invalidate();self.show(text);self.note.set('已完成。请启动游戏并读取刚才选择的存档。')
            self.host.reload()
            messagebox.showinfo('功能修改完成',f'已备份并写入。\n备份：{backup}\n详细结果见本页。',parent=self.host)
        self.host.martial_page.worker('正在备份并写入功能修改…',lambda:apply(root,prepared),finish)

def build(host,parent):
    notebook=ttk.Notebook(parent);notebook.pack(fill='both',expand=True)
    caps=ttk.Frame(notebook,padding=12);notebook.add(caps,text='武学上限');host.build_caps_page(caps)
    scripts=ttk.Frame(notebook,padding=12);notebook.add(scripts,text='收藏／资源／残章／难度与成就')
    host.feature_panel=FeaturePanel(host,scripts);host.feature_notebook=notebook
    from feature_extra_ui import build as build_extras
    build_extras(host,notebook)
    from blank_manual_shop_ui import build as build_blank_manual
    build_blank_manual(host,notebook)
    from martial_mastery_ui import build as build_mastery
    build_mastery(host,notebook)
    from six_attrs_ui import build as build_six_attrs
    build_six_attrs(host,notebook)
    from role_breakthrough_ui import build as build_role_breakthrough
    build_role_breakthrough(host,notebook)
    from pet_restore_ui import build as build_pet
    build_pet(host,notebook)
    from mobile_martial_restore_ui import build as build_mobile_martials
    build_mobile_martials(host,notebook)
    from martial_limit_enhance_ui import build as build_limit_enhance
    build_limit_enhance(host,notebook)
    from attribute_uncap_ui import build as build_uncap
    build_uncap(host,notebook)
    from disguise_ui import build as build_disguise
    build_disguise(host,notebook)

def select_launcher(host):
    import sys
    if '--feature' not in sys.argv:return
    try:action=sys.argv[sys.argv.index('--feature')+1]
    except IndexError:return
    if action not in LABELS:return
    host.pages.select(1);host.feature_notebook.select(1)
    host.feature_panel.action.set(LABELS[action]);host.feature_panel.refresh()
