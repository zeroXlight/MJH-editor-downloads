from pathlib import Path
import tkinter as tk
from tkinter import ttk,messagebox

class ManagerDialog:
    def __init__(self,host,root,rows):
        self.host=host;self.root=root;self.prepared=None;self.signature=None
        self.window=tk.Toplevel(host);win=self.window;win.title('管理已启用功能');win.transient(host);win.geometry('1000x760')
        self.variables={}
        box=ttk.Frame(win,padding=18);box.pack(fill='both',expand=True)
        ttk.Label(box,text='关闭 / 重新启用功能',style='Title.TLabel').pack(anchor='w')
        ttk.Label(box,text='勾选功能后预览，再应用并备份。保留装备/物品编辑、人物和存档进度；不回收已结算资源。',wraplength=920,style='Sub.TLabel').pack(anchor='w',pady=10)
        for row in rows:
            var=tk.BooleanVar(value=False);self.variables[row['key']]=var
            label=('已启用 · ' if row['enabled'] else '已关闭 · ')+row['label']
            ttk.Checkbutton(box,text=label,variable=var,command=self.invalidate,state='normal' if row['available'] else 'disabled').pack(anchor='w',pady=3)
            if row['note'] or row['error']:ttk.Label(box,text=row['error'] or row['note'],wraplength=910,style='Sub.TLabel').pack(anchor='w',padx=22)
        if not rows:ttk.Label(box,text='未检测到可管理的已启用功能。一次性发放资源和物品编辑不属于持续开关。').pack(anchor='w',pady=15)
        buttons=ttk.Frame(box);buttons.pack(fill='x',pady=12)
        ttk.Button(buttons,text='预览关闭选中功能',command=lambda:self.preview(False)).pack(side='left')
        ttk.Button(buttons,text='预览重新启用选中功能',command=lambda:self.preview(True)).pack(side='left',padx=8)
        ttk.Button(buttons,text='应用并备份',style='Primary.TButton',command=self.commit).pack(side='left')
        ttk.Button(buttons,text='关闭窗口',command=win.destroy).pack(side='right')
        self.note=tk.StringVar(value='尚未修改。');ttk.Label(box,textvariable=self.note,wraplength=920).pack(anchor='w')
        self.report=tk.Text(box,height=10,wrap='word',state='disabled');self.report.pack(fill='both',expand=True,pady=8)
        win.grab_set();host.wait_window(win)
    def selected(self):return tuple(k for k,v in self.variables.items() if v.get())
    def invalidate(self):self.prepared=None;self.signature=None;self.note.set('选择已改变，请重新预览。')
    def show(self,text):self.report.configure(state='normal');self.report.delete('1.0','end');self.report.insert('1.0',text);self.report.configure(state='disabled')
    def preview(self,enabled):
        if self.host.busy:return
        keys=self.selected()
        if not keys:self.host.error(ValueError('请勾选至少一项功能'));return
        from feature_manager import plan
        def done(value):
            if not self.window.winfo_exists() or keys!=self.selected():return
            self.prepared=value;self.signature=(keys,enabled);self.show('\n'.join(value[2]+value[3]));self.note.set(f'预览完成：修改 {len(value[0])} 个文件，尚未写入。')
        self.host.martial_page.worker('正在核对选中功能与原值…',lambda:plan(self.root,keys,enabled),done)
    def commit(self):
        if self.host.busy:return
        if self.prepared is None or self.signature[0]!=self.selected():self.host.error(ValueError('请先预览当前选择'));return
        value=self.prepared
        if not value[0]:self.note.set('当前已符合目标。');return
        from feature_save import apply
        def done(backup):
            if self.window.winfo_exists():self.window.destroy()
            self.host.martial_page.reset();self.host.role_page.reset();self.host.reload()
            messagebox.showinfo('功能开关完成',f'已应用并备份。重启游戏后生效。\n备份：{backup}',parent=self.host)
        self.host.martial_page.worker('正在备份并切换功能…',lambda:apply(self.root,value),done)

def open_manager(host):
    if host.busy:return
    root=Path(host.game_path.get()).resolve()
    if not host.catalog or host.catalog.root!=root:raise ValueError('请先读取游戏目录')
    if host.has_changes():raise ValueError('请先保存或撤销其他草稿')
    from feature_manager import scan
    host.martial_page.worker('正在检查已启用功能…',lambda:scan(root),lambda rows:ManagerDialog(host,root,rows))
