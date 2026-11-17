import tkinter as tk
from tkinter import ttk,messagebox

def show(host):
    from external_runtime import plan
    from engine import transaction,ensure_closed
    if host.has_changes():
        messagebox.showinfo('请先保存草稿','请先保存或撤销当前草稿，再准备安装外部 MOD。',parent=host);return
    dialog=tk.Toplevel(host);dialog.title('外部 MOD 安装兼容');dialog.transient(host)
    dialog.protocol('WM_DELETE_WINDOW',lambda:None if host.busy else dialog.destroy())
    frame=ttk.Frame(dialog,padding=20);frame.pack(fill='both',expand=True)
    ttk.Label(frame,text='先准备，再安装 MOD，最后恢复编辑器支持',font=('Microsoft YaHei',13)).pack(anchor='w')
    ttk.Label(frame,text='已安装暗影：退出游戏后直接重新读取目录即可检测／接入独立补丁，无需先还原所有修改。',wraplength=580).pack(anchor='w',pady=(10,0))
    ttk.Label(frame,wraplength=580,text='普通编辑使用游戏配置。额外的每级成长数值和自定义战斗范围需要计算支持。\n\n'
        '安装前准备只暂时撤下编辑器自己的支持，保留其他修改、人物、武学和存档。完成准备后，退出编辑器，运行 MOD 安装程序；安装成功后重新打开编辑器，执行安装后恢复。\n\n'
        '完成恢复前先不要进入游戏。恢复时会检查计算入口；若与 MOD 冲突，保留当前文件并说明原因。').pack(anchor='w',pady=16)
    def run(restore):
        try:ensure_closed();root=host.game_path.get()
        except Exception as error:host.error(error);return
        def review(result):
            payloads,originals,label=result
            details=('将备份当前运行库，暂时撤下编辑器计算支持。人物、武学配置和存档保持原样。\n\n准备后请安装 MOD，再回来执行恢复。'
                     if not restore else '计算入口检查和回读校验已通过。将备份 MOD 当前运行库，再恢复编辑器计算支持，保留 MOD 的其他修改。')
            if not messagebox.askyesno(label,details+'\n\n是否执行？',parent=dialog):return
            def finish(backup):
                messagebox.showinfo(label,'已完成。\n备份：'+str(backup),parent=dialog)
                host.catalog=None;host.save=None;host.current=None
                if getattr(host,'role_page',None):host.role_page.reset()
                if getattr(host,'martial_page',None):host.martial_page.reset()
                host.items.delete(*host.items.get_children());host.status.set('兼容处理完成，请重新读取目录。')
            host.martial_page.worker('正在备份并执行兼容处理…',lambda:transaction(root,payloads,originals,purpose=label),finish)
        host.martial_page.worker('正在检查计算入口并生成兼容方案…',lambda:plan(root,restore),review)
    ttk.Button(frame,text='① 安装外部 MOD 前准备',command=lambda:run(False)).pack(side='left',padx=(0,12))
    ttk.Button(frame,text='② 安装后恢复编辑器支持',command=lambda:run(True)).pack(side='left')
