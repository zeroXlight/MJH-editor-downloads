"""Preview and apply the installation-wide mask configuration."""
from pathlib import Path
import tkinter as tk
from tkinter import ttk,filedialog
class DisguisePanel:
    def __init__(self,host,parent):
        self.host=host;self.prepared=None;self.signature=None
        self.note=tk.StringVar(value='预览检查当前游戏资源后应用，自动备份。')
        ttk.Label(parent,text='易容面具 · 全部模型与立绘',style='Title.TLabel').pack(anchor='w',pady=10)
        ttk.Label(parent,text='新增选项分别放入游戏内“更改模型”和“更改立绘”，可查询编号、人物名及资源名；模型与立绘分开修改；更改立绘时同步唯一对应的头像，无匹配时保留原头像。\n原有面具保留分类及位置。易容时长加长为原来的 100000 倍，仅作用于当前局；面具购买基础价格设为 1。\n预览后可导出带缩略图的离线查询总表；游戏中每页 60 项。手游资源版额外加入手游模型、皮肤和立绘。',wraplength=1100,style='Sub.TLabel').pack(anchor='w',pady=8)
        row=ttk.Frame(parent);row.pack(fill='x',pady=10)
        ttk.Button(row,text='预览易容面具修改',command=self.preview).pack(side='left')
        ttk.Button(row,text='应用易容面具修改并备份',command=self.commit,style='Primary.TButton').pack(side='left',padx=10)
        ttk.Button(row,text='导出模型与立绘总表',command=self.export_reference).pack(side='left',padx=10)
        ttk.Label(parent,textvariable=self.note,wraplength=1100).pack(anchor='w',pady=8)
        self.report=tk.Text(parent,height=15,wrap='word',state='disabled');self.report.pack(fill='both',expand=True)
    def selections(self):
        root=Path(self.host.game_path.get()).resolve()
        if not self.host.catalog or root!=self.host.catalog.root:raise ValueError('请先读取当前游戏目录')
        if self.host.has_changes():raise ValueError('请先保存或撤销其他草稿')
        return root
    def show(self,text):
        self.report.configure(state='normal');self.report.delete('1.0','end');self.report.insert('1.0',text);self.report.configure(state='disabled')
    def preview(self):
        if self.host.busy:return
        try:root=self.selections()
        except Exception as error:self.host.error(error);return
        self.prepared=None
        from disguise_editor import plan
        def finish(value):
            self.prepared=value;self.signature=root;self.show('\n'.join(value[2]+value[3]));self.note.set(f'预览完成，将修改 {len(value[0])} 个文件。尚未写入游戏。')
        self.host.martial_page.worker('正在读取全部易容资源并生成模型预览，请稍候…',lambda:plan(root),finish)
    def commit(self):
        if self.host.busy:return
        try:
            if self.prepared is None or self.selections()!=self.signature:raise ValueError('请先预览当前游戏目录')
            if not self.prepared[0]:raise ValueError('已符合本版设置，无需重复应用')
        except Exception as error:self.host.error(error);return
        from feature_save import apply
        value=self.prepared;root=self.signature
        def finish(backup):
            self.show('\n'.join(value[2])+f'\n备份：{backup}');self.note.set('应用完成，重启游戏后使用易容面具。')
            self.prepared=None;self.host.role_page.reset();self.host.martial_page.reset();self.host.reload()
        self.host.martial_page.worker('正在备份并应用易容面具修改…',lambda:apply(root,value),finish)
    def export_reference(self):
        if self.host.busy:return
        try:
            if self.prepared is None or self.selections()!=self.signature:raise ValueError('请先预览当前游戏目录')
        except Exception as error:self.host.error(error);return
        from edition import VERSION,EDITION_NAME
        path=filedialog.asksaveasfilename(title='导出模型与立绘总表',initialfile=f'模型与立绘总表_{VERSION}_{EDITION_NAME}.html',defaultextension='.html',filetypes=[('离线查询总表','*.html')])
        if not path:return
        from disguise_reference import export
        self.host.martial_page.worker('正在生成资源总表和缩略图…',lambda:export(self.signature,self.prepared,path),lambda p:self.note.set('总表已导出，双击可离线查询：'+str(p)))

def build(host,notebook):host.disguise_panel=DisguisePanel(host,host.scroll_page(notebook,'易容面具'))
