import tkinter as tk
from tkinter import ttk
from pathlib import Path

class Panel:
    def __init__(self,host,parent):
        self.host=host;self.prepared=None;self.signature=None;self.mode=tk.StringVar(value='开启强化');self.note=tk.StringVar(value='请预览后应用，运行中的游戏需先退出。')
        ttk.Label(parent,text='开启全武学等级上限强化',style='Title.TLabel').pack(anchor='w',pady=8)
        ttk.Label(parent,text='启用后，已收藏的普通武学从10级上限起即可使用武学残文强化，每次提升1级固定消耗100。\n沿用各品质残文种类及当前最终强化上限；原有残章、收藏与已学等级保留，不赠送残文。',wraplength=1100).pack(anchor='w',pady=8)
        row=ttk.Frame(parent);row.pack(fill='x',pady=8)
        box=ttk.Combobox(row,textvariable=self.mode,values=['开启强化','关闭强化'],state='readonly',width=22);box.pack(side='left');box.bind('<<ComboboxSelected>>',self.invalidate)
        ttk.Button(row,text='预览上限强化',command=self.preview).pack(side='left',padx=8);ttk.Button(row,text='应用并备份',command=self.commit,style='Primary.TButton').pack(side='left')
        ttk.Label(parent,textvariable=self.note,wraplength=1100).pack(anchor='w',pady=8)
        self.report=tk.Text(parent,height=14,wrap='word',state='disabled');self.report.pack(fill='both',expand=True)
    def invalidate(self,*_):self.prepared=None;self.signature=None
    def selections(self):
        root=Path(self.host.game_path.get()).resolve()
        if not self.host.catalog or self.host.catalog.root!=root:raise ValueError('请先读取当前游戏目录')
        if self.host.has_changes():raise ValueError('请先保存或撤销其他草稿')
        return root,self.mode.get()=='开启强化'
    def show(self,text):self.report.configure(state='normal');self.report.delete('1.0','end');self.report.insert('1.0',text);self.report.configure(state='disabled')
    def preview(self):
        if self.host.busy:return
        try:signature=self.selections()
        except Exception as e:self.host.error(e);return
        from martial_limit_enhance import plan
        def done(value):
            if self.selections()!=signature:return
            self.prepared=value;self.signature=signature;self.show('\n'.join(value[2]+value[3]));self.note.set(f'预览完成，将修改{len(value[0])}个文件；尚未写入。')
        self.host.martial_page.worker('正在检查武学强化入口、残文费用和上限…',lambda:plan(*signature),done)
    def commit(self):
        if self.host.busy:return
        try:
            if not self.prepared or self.signature!=self.selections():raise ValueError('请先预览当前选择')
            if not self.prepared[0]:raise ValueError('当前已符合目标，无需重复应用')
        except Exception as e:self.host.error(e);return
        from feature_save import apply
        value=self.prepared;signature=self.signature
        def done(backup):self.invalidate();self.show('\n'.join(value[2])+f'\n备份：{backup}');self.note.set('已完成，重启游戏后生效。');self.host.reload()
        self.host.martial_page.worker('正在备份并修改武学上限强化…',lambda:apply(signature[0],value),done)

def build(host,notebook):host.limit_enhance_panel=Panel(host,host.scroll_page(notebook,'开启全武学等级上限强化'))
