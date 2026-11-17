"""Configuration-wide interaction unlock controls."""
from pathlib import Path
import tkinter as tk
from tkinter import ttk,messagebox
class ExtraPanel:
    def __init__(self,host,parent):
        self.host=host;self.prepared=None;self.signature=None
        self.note=tk.StringVar(value='预览后确认应用；应用时自动备份。')
        ttk.Label(parent,text='盘查／号召／决斗／乞讨永久解锁',style='Title.TLabel').pack(anchor='w',pady=10)
        ttk.Label(parent,text='一次应用，对当前游戏目录的全部旧档、新档和后续周目生效，无需选择存档。\n解锁四项功能入口；交互对象、剧情、次数及战斗条件继续按游戏规则处理。',wraplength=1100,style='Sub.TLabel').pack(anchor='w',pady=8)
        row=ttk.Frame(parent);row.pack(fill='x',pady=10)
        ttk.Button(row,text='预览永久解锁',command=self.preview).pack(side='left')
        ttk.Button(row,text='永久解锁四项并备份',command=self.commit,style='Primary.TButton').pack(side='left',padx=10)
        ttk.Label(parent,textvariable=self.note,wraplength=1100).pack(anchor='w',pady=8)
        self.report=tk.Text(parent,height=7,wrap='word',state='disabled');self.report.pack(fill='x')
    def invalidate(self):self.prepared=None;self.signature=None;self.note.set('选择已更新，请预览后再应用。')
    def refresh(self):
        if not self.host.busy:self.invalidate()
    def selections(self):
        root=Path(self.host.game_path.get()).resolve()
        if not self.host.catalog or root!=self.host.catalog.root:raise ValueError('请先读取当前游戏目录')
        if self.host.has_changes():raise ValueError('请先保存或撤销其他草稿')
        return (root,)
    def preview(self):
        if self.host.busy:return
        try:signature=self.selections()
        except Exception as error:self.host.error(error);return
        self.prepared=None
        from interaction_unlock import plan
        def finish(value):
            self.prepared=value;self.signature=signature;self.show('\n'.join(value[2]));self.note.set(f'预览完成：将修改 {len(value[0])} 个文件。尚未写入游戏。')
        self.host.martial_page.worker('正在检查永久解锁…',lambda:plan(*signature),finish)
    def show(self,text):
        self.report.configure(state='normal');self.report.delete('1.0','end');self.report.insert('1.0',text);self.report.configure(state='disabled')
    def commit(self):
        if self.host.busy:return
        try:
            if self.prepared is None or self.selections()!=self.signature:raise ValueError('请先预览当前选择')
            if not self.prepared[0]:raise ValueError('当前已符合目标，无需重复应用')
        except Exception as error:self.host.error(error);return
        value=self.prepared;root=self.signature[0]
        if not messagebox.askyesno('确认功能修改','\n'.join(value[2])+'\n\n请退出游戏；继续将自动备份并应用。',parent=self.host):return
        from feature_save import apply
        def finish(backup):
            self.invalidate();self.show('\n'.join(value[2])+f'\n备份：{backup}');self.note.set('应用完成，重启游戏后生效。')
            self.host.role_page.reset();self.host.martial_page.reset();self.host.reload()
        self.host.martial_page.worker('正在备份并应用…',lambda:apply(root,value),finish)
class ChestPanel(ExtraPanel):
    def __init__(self,host,parent):
        self.host=host;self.prepared=None;self.signature=None;self.enabled=tk.BooleanVar(value=True)
        self.note=tk.StringVar(value='仅处理宝箱，不自动拾取地图散落物品。')
        ttk.Label(parent,text='宝箱物品自动入库',style='Title.TLabel').pack(anchor='w',pady=(18,8))
        ttk.Label(parent,text='打开宝箱时，按原有掉落规则直接结算到背包，不再生成宝箱物品的散落动画。\n地图本来存在的散落物品保留，不改变开箱条件、钥匙消耗和原有奖励数量。',wraplength=1100,style='Sub.TLabel').pack(anchor='w')
        ttk.Checkbutton(parent,text='启用宝箱物品自动入库',variable=self.enabled,command=self.invalidate).pack(anchor='w',pady=8)
        bar=ttk.Frame(parent);bar.pack(fill='x',pady=8)
        ttk.Button(bar,text='预览宝箱自动入库',command=self.preview).pack(side='left')
        ttk.Button(bar,text='应用宝箱设置并备份',style='Primary.TButton',command=self.commit).pack(side='left',padx=10)
        ttk.Label(parent,textvariable=self.note,wraplength=1100).pack(anchor='w')
        self.report=tk.Text(parent,height=5,wrap='word',state='disabled');self.report.pack(fill='x',pady=8)
    def selections(self):return super().selections()+(self.enabled.get(),)
    def preview(self):
        if self.host.busy:return
        try:signature=self.selections()
        except Exception as e:self.host.error(e);return
        from chest_autoloot import plan
        def done(value):
            self.prepared=value;self.signature=signature;self.show('\n'.join(value[2]));self.note.set(f'预览完成：修改 {len(value[0])} 个文件，尚未写入。')
        self.host.martial_page.worker('正在核对宝箱奖励入口…',lambda:plan(*signature),done)

def build(host,notebook):
    page=host.scroll_page(notebook,'交互永久解锁')
    host.interaction_panel=ExtraPanel(host,page)
    host.chest_panel=ChestPanel(host,page)
