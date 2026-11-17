from pathlib import Path
import tkinter as tk
from tkinter import ttk,messagebox
from bigmap_compat import LABELS,preferences,plan
class Dialog:
    def __init__(self,host,root,prefs):
        self.host=host;self.root=root;self.prepared=None;self.selection=None
        win=self.window=tk.Toplevel(host);win.title('兼容大地图版本');win.transient(host);win.geometry('1000x780')
        box=ttk.Frame(win,padding=18);box.pack(fill='both',expand=True)
        ttk.Label(box,text='兼容大地图版本',style='Title.TLabel').pack(anchor='w')
        ttk.Label(box,text='核对大地图运行库，修复资源替换后失效的编辑器支持。勾选需要恢复的功能，预览后应用并备份。\n默认勾选有启用记录的项目；未启用的功能可保持不勾选。保留大地图配置、物品编辑及存档进度。',wraplength=920).pack(anchor='w',pady=10)
        self.vars={}
        for key,label in LABELS.items():
            var=tk.BooleanVar(value=prefs.get(key,False));self.vars[key]=var
            ttk.Checkbutton(box,text=label,variable=var,command=self.invalidate).pack(anchor='w',pady=3)
        bar=ttk.Frame(box);bar.pack(fill='x',pady=10)
        ttk.Button(bar,text='检查并预览大地图兼容',command=self.preview).pack(side='left')
        ttk.Button(bar,text='应用大地图兼容并备份',style='Primary.TButton',command=self.commit).pack(side='left',padx=10)
        ttk.Button(bar,text='关闭窗口',command=win.destroy).pack(side='right')
        self.note=tk.StringVar(value='预览不会写入游戏。未通过的项目会单独列出并跳过。')
        ttk.Label(box,textvariable=self.note,wraplength=920).pack(anchor='w')
        self.report=tk.Text(box,wrap='word',height=12,state='disabled');self.report.pack(fill='both',expand=True,pady=8)
        win.protocol('WM_DELETE_WINDOW',lambda:None if host.busy else win.destroy());win.grab_set();host.wait_window(win)
    def selected(self):return tuple(k for k,v in self.vars.items() if v.get())
    def invalidate(self):self.prepared=None;self.selection=None;self.note.set('选择已改变，请重新预览。')
    def preview(self):
        if self.host.busy:return
        selected=self.selected();self.prepared=None
        def done(value):
            if not self.window.winfo_exists() or selected!=self.selected():return
            self.prepared=value;self.selection=selected
            self.report.configure(state='normal');self.report.delete('1.0','end');self.report.insert('1.0','\n'.join(value[2]+value[3]));self.report.configure(state='disabled')
            self.note.set(f'检查完成，计划修改 {len(value[0])} 个文件，跳过 {len(value[3])} 项提示；尚未写入。')
        self.host.martial_page.worker('正在逐项核对大地图版本兼容…',lambda:plan(self.root,selected),done)
    def commit(self):
        if self.host.busy:return
        if self.prepared is None or self.selection!=self.selected():self.host.error(ValueError('请先预览当前选择'));return
        if not self.prepared[0]:self.note.set('当前已符合兼容方案。');return
        from feature_save import apply
        value=self.prepared
        def done(backup):
            if self.window.winfo_exists():self.window.destroy()
            self.host.martial_page.reset();self.host.role_page.reset();self.host.reload()
            messagebox.showinfo('大地图兼容完成','已应用并备份。请重启游戏。\n备份：'+str(backup),parent=self.host)
        self.host.martial_page.worker('正在备份并应用大地图兼容…',lambda:apply(self.root,value),done)
def show(host):
    if host.busy:return
    root=Path(host.game_path.get()).resolve()
    if not host.catalog or host.catalog.root!=root:raise ValueError('请先读取当前游戏目录')
    if host.has_changes():raise ValueError('请先保存或撤销草稿')
    host.martial_page.worker('正在读取大地图功能启用记录…',lambda:preferences(root),lambda prefs:Dialog(host,root,prefs))
