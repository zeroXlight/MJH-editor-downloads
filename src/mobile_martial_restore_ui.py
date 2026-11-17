"""Review first, then back up and apply verified mobile martial restoration."""
from pathlib import Path
import tkinter as tk
from tkinter import ttk

class Panel:
    def __init__(self,host,parent):
        self.host=host;self.prepared=None;self.signature=None
        self.test=tk.BooleanVar(value=False);self.slot=tk.StringVar();self.note=tk.StringVar(value='请预览当前游戏目录，核对成功与跳过清单后应用。')
        ttk.Label(parent,text='恢复手游专属武学',style='Title.TLabel').pack(anchor='w',pady=8)
        ttk.Label(parent,text='核对42门手游人物专属武学；仅恢复依赖完整且已通过PC兼容检查的项目。\n解除人物专属限制，新增版本名称以“新·”开头，保留已有同名武学。不存在的门派统一归为散武学。',wraplength=1100).pack(anchor='w',pady=8)
        ttk.Label(parent,text='成功恢复的武学支持演化、抄录、秘籍与残章原生获取、神秘商店及江湖收藏，沿用普通武学的升级上限规则。\n天玑五转按手游主表恢复飞剑次数、随机敌方范围与单目标上限；已移植专用特效，材质适配PC着色器，部分动态视觉细节可能与手游不同。\n无法完整恢复的项目整门跳过，具体原因见下方预览。',wraplength=1100,style='Sub.TLabel').pack(anchor='w',pady=8)
        ttk.Checkbutton(parent,text='向所选存档当前周目仓库各添加1本测试秘籍（每次应用都会添加）',variable=self.test,command=self.invalidate).pack(anchor='w',pady=6)
        row=ttk.Frame(parent);row.pack(fill='x',pady=6)
        ttk.Label(row,text='测试存档').pack(side='left')
        self.box=ttk.Combobox(row,textvariable=self.slot,state='readonly',width=35);self.box.pack(side='left',padx=8);self.box.bind('<<ComboboxSelected>>',self.invalidate)
        ttk.Button(row,text='刷新存档',command=self.refresh).pack(side='left')
        row=ttk.Frame(parent);row.pack(fill='x',pady=8)
        ttk.Button(row,text='预览手游武学恢复',command=self.preview).pack(side='left')
        ttk.Button(row,text='应用恢复并备份',command=self.commit,style='Primary.TButton').pack(side='left',padx=10)
        ttk.Label(parent,textvariable=self.note,wraplength=1100).pack(anchor='w',pady=8)
        self.report=tk.Text(parent,height=15,wrap='word',state='disabled');self.report.pack(fill='both',expand=True)
        self.saves=[]
    def invalidate(self,*_):self.prepared=None;self.signature=None;self.note.set('请重新预览当前选择。')
    def refresh(self):
        root=Path(self.host.game_path.get()).resolve();self.saves=[]
        if (root/'Save.sav').is_file():self.saves.append(('自动存档（当前周目）',root/'Save.sav'))
        self.saves.extend((p.parent.name,p) for p in sorted((root/'SaveFile').glob('*/Save.sav')))
        self.box.configure(values=[n for n,p in self.saves]);self.slot.set(self.saves[0][0] if self.saves else '');self.invalidate()
    def selections(self):
        root=Path(self.host.game_path.get()).resolve()
        if not self.host.catalog or self.host.catalog.root!=root:raise ValueError('请先读取当前游戏目录')
        if self.host.has_changes():raise ValueError('请先保存或撤销其他草稿')
        save=next((p for n,p in self.saves if n==self.slot.get()),None)
        if self.test.get() and save is None:raise ValueError('请刷新并选择测试存档')
        return root,self.test.get(),save if self.test.get() else None
    def show(self,text):self.report.configure(state='normal');self.report.delete('1.0','end');self.report.insert('1.0',text);self.report.configure(state='disabled')
    def preview(self):
        if self.host.busy:return
        try:signature=self.selections()
        except Exception as e:self.host.error(e);return
        from mobile_martial_restore import plan
        def done(value):
            if self.selections()!=signature:return
            self.prepared=value;self.signature=signature;self.show('\n'.join(value.prepared[2]+['','跳过项目与原因：']+value.prepared[3]));self.note.set(f'预览完成：恢复 {len(value.installed)} 门，将修改 {len(value.prepared[0])} 个文件；尚未写入。')
        self.host.martial_page.worker('正在核对手游武学依赖、获取途径和测试存档…',lambda:plan(*signature),done)
    def commit(self):
        if self.host.busy:return
        try:
            if not self.prepared or self.signature!=self.selections():raise ValueError('请先预览当前选择')
            if not self.prepared.prepared[0]:raise ValueError('当前已符合目标，无需重复应用')
        except Exception as e:self.host.error(e);return
        from mobile_martial_restore import apply
        value=self.prepared
        def done(backup):
            self.invalidate();self.show('\n'.join(value.prepared[2]+value.prepared[3])+f'\n备份：{backup}');self.note.set('恢复完成。重启游戏后查看江湖收藏或测试仓库。');self.host.reload()
        self.host.martial_page.worker('正在备份并恢复手游专属武学…',lambda:apply(value),done)

def build(host,notebook):host.mobile_martial_panel=Panel(host,host.scroll_page(notebook,'恢复手游专属武学'))
