"""One shared panel for the native merchant discount only."""
import tkinter as tk
from tkinter import ttk,messagebox
from feature_extra_ui import ExtraPanel
class Panel(ExtraPanel):
    def __init__(self,host,parent):
        self.host=host;self.prepared=None;self.signature=None;self.note=tk.StringVar(value='预览后启用，自动备份。')
        ttk.Label(parent,text='空白秘籍低价购买',style='Title.TLabel').pack(anchor='w',pady=10)
        ttk.Label(parent,text='启用后，杭州本杰明商店可用1铜币购买1本空白秘籍，每个游戏月限20本。\n空白秘籍作为原生全局资产跨周目保留。抄录由游戏原版提供。\n升级时会撤下可核实的旧编辑器抄录接管；购买数量和已有余额保留。',wraplength=1100,style='Sub.TLabel').pack(anchor='w',pady=8)
        row=ttk.Frame(parent);row.pack(fill='x',pady=10)
        ttk.Button(row,text='预览空白秘籍商店',command=self.preview).pack(side='left')
        ttk.Button(row,text='启用低价购买并备份',command=self.commit,style='Primary.TButton').pack(side='left',padx=10)
        ttk.Label(parent,textvariable=self.note,wraplength=1100).pack(anchor='w',pady=8)
        self.report=tk.Text(parent,height=10,wrap='word',state='disabled');self.report.pack(fill='x')
    def preview(self):
        if self.host.busy:return
        try:signature=self.selections()
        except Exception as e:self.host.error(e);return
        self.prepared=None
        from blank_manual_shop import plan
        def done(value):
            self.prepared=value;self.signature=signature;self.show('\n'.join(value[2]));self.note.set(f'预览完成：修改 {len(value[0])} 个文件，尚未写入。')
        self.host.martial_page.worker('正在核对空白秘籍货架…',lambda:plan(*signature),done)
    def commit(self):
        if self.host.busy:return
        try:
            if self.prepared is None or self.selections()!=self.signature:raise ValueError('请先预览当前目录')
            if not self.prepared[0]:raise ValueError('当前已符合目标，无需重复应用')
        except Exception as e:self.host.error(e);return
        root=self.signature[0];value=self.prepared
        if not messagebox.askyesno('启用空白秘籍低价购买','\n'.join(value[2])+'\n\n退出游戏后继续，将自动备份。',parent=self.host):return
        from blank_manual_shop import apply
        def done(backup):
            self.invalidate();self.show('\n'.join(value[2])+f'\n备份：{backup}');self.note.set('已完成，重启游戏后生效。');self.host.reload()
        self.host.martial_page.worker('正在备份并启用低价货架…',lambda:apply(root,value),done)
def build(host,notebook):host.blank_manual_shop_panel=Panel(host,host.scroll_page(notebook,'空白秘籍低价购买'))
