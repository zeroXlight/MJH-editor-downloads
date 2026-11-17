"""Installation-wide attribute cap switch using the existing preview workflow."""
from pathlib import Path
import tkinter as tk
from tkinter import ttk,messagebox

class UncapPanel:
    def __init__(self,host,parent):
        self.host=host;self.prepared=None;self.signature=None
        self.enabled=tk.BooleanVar(value=True);self.damage=tk.BooleanVar(value=True)
        self.note=tk.StringVar(value='读取目录后预览，确认后应用并自动备份。')
        ttk.Label(parent,text='移除属性上限',style='Title.TLabel').pack(anchor='w',pady=10)
        ttk.Label(parent,text='移除六项属性、精通、生命、真气、攻击、防御、速度及数值型命中/闪避/暴击等属性的游戏上限。\n对当前目录全部人物和存档生效，重启游戏后重新计算；不会直接增加属性。保留20亿数值保护线。',
                  wraplength=1100,style='Sub.TLabel').pack(anchor='w',pady=8)
        ttk.Checkbutton(parent,text='启用移除属性上限（取消勾选可恢复原上限）',variable=self.enabled,command=self.invalidate).pack(anchor='w',pady=8)
        ttk.Checkbutton(parent,text='同时移除武学单次伤害上限（保留20亿保护线）',variable=self.damage,command=self.invalidate).pack(anchor='w',pady=6)
        row=ttk.Frame(parent);row.pack(fill='x',pady=10)
        ttk.Button(row,text='预览属性上限修改',command=self.preview).pack(side='left')
        ttk.Button(row,text='应用属性上限修改并备份',command=self.commit,style='Primary.TButton').pack(side='left',padx=10)
        ttk.Label(parent,textvariable=self.note,wraplength=1100).pack(anchor='w',pady=8)
        self.report=tk.Text(parent,height=10,wrap='word',state='disabled');self.report.pack(fill='both',expand=True)
    def invalidate(self,*_):self.prepared=None;self.signature=None;self.note.set('请预览当前设置后应用。')
    def refresh(self):
        if not self.host.busy:self.invalidate()
    def selections(self):
        root=Path(self.host.game_path.get()).resolve()
        if not self.host.catalog or root!=self.host.catalog.root:raise ValueError('请先读取当前游戏目录')
        if self.host.has_changes():raise ValueError('请先保存或撤销其他草稿')
        return root,bool(self.enabled.get()),bool(self.damage.get())
    def show(self,text):
        self.report.configure(state='normal');self.report.delete('1.0','end');self.report.insert('1.0',text);self.report.configure(state='disabled')
    def preview(self):
        if self.host.busy:return
        try:signature=self.selections()
        except Exception as error:self.host.error(error);return
        self.prepared=None
        from attribute_uncap import plan
        def finish(value):
            if self.selections()!=signature:self.invalidate();return
            self.prepared=value;self.signature=signature
            self.show('\n'.join(value[2]));self.note.set(f'预览完成：将修改 {len(value[0])} 个文件，尚未写入游戏。')
        self.host.martial_page.worker('正在检查人物属性上限…',lambda:plan(*signature),finish)
    def commit(self):
        if self.host.busy:return
        try:
            if self.prepared is None or self.selections()!=self.signature:raise ValueError('请先预览当前设置')
            if not self.prepared[0]:raise ValueError('当前已符合目标，无需重复应用')
        except Exception as error:self.host.error(error);return
        value=self.prepared;root=self.signature[0]
        if not messagebox.askyesno('确认修改属性上限','\n'.join(value[2])+'\n\n请退出游戏；继续将自动备份并应用。',parent=self.host):return
        from feature_save import apply
        def finish(backup):
            self.invalidate();self.show('\n'.join(value[2])+f'\n备份：{backup}');self.note.set('应用完成，重启游戏并读取存档后生效。')
            self.host.role_page.reset();self.host.martial_page.reset();self.host.reload()
        self.host.martial_page.worker('正在备份并修改人物属性上限…',lambda:apply(root,value),finish)

def build(host,notebook):
    host.attribute_uncap_panel=UncapPanel(host,host.scroll_page(notebook,'移除属性上限'))
