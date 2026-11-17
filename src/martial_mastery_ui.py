"""Mastery restoration controls exposed through the shared desktop bridge."""
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox
from martial_mastery import DEFAULT_GOLD, DEFAULT_DARK_GOLD


class MasteryPanel:
    def __init__(self,host,parent):
        self.host=host;self.prepared=None;self.signature=None
        self.gold=tk.StringVar(value=str(DEFAULT_GOLD));self.dark_gold=tk.StringVar(value=str(DEFAULT_DARK_GOLD))
        self.adjust=tk.BooleanVar(value=False)
        self.note=tk.StringVar(value='默认只补回词条，保留当前每级精通数值；预览后应用并自动备份。')
        ttk.Label(parent,text='恢复武学精通',style='Title.TLabel').pack(anchor='w',pady=10)
        ttk.Label(parent,text='为金色、暗金的八类普通武学补回缺失的精通成长，并同步逻辑表、显示表和已有 MOD 配置。\n按已学武学等级计算，对当前游戏目录的旧档、新档生效；不改变武学等级、残章和突破进度。\n轻功、阵法等不自动添加；已有独立成长数值保留。',wraplength=1100,style='Sub.TLabel').pack(anchor='w',pady=8)
        ttk.Checkbutton(parent,text='调整每级精通（不勾选时仅补回词条，保留当前每级 +1 等原数值）',variable=self.adjust,command=self.mode_changed).pack(anchor='w',pady=8)
        row=ttk.Frame(parent);row.pack(fill='x',pady=10)
        ttk.Label(row,text='金色武学：每级精通 +').pack(side='left')
        self.gold_entry=ttk.Entry(row,textvariable=self.gold,width=8,state='disabled');self.gold_entry.pack(side='left',padx=8)
        ttk.Label(row,text='暗金武学：每级精通 +').pack(side='left',padx=(20,0))
        self.dark_entry=ttk.Entry(row,textvariable=self.dark_gold,width=8,state='disabled');self.dark_entry.pack(side='left',padx=8)
        ttk.Label(parent,text='可选调整预填金色 +12、暗金 +18；只有勾选后才使用，可输入 1～1000 的整数。\n先按默认补回词条，再勾选调整、重新预览并应用，即可单独调整数值。',wraplength=1100).pack(anchor='w')
        buttons=ttk.Frame(parent);buttons.pack(fill='x',pady=10)
        ttk.Button(buttons,text='预览恢复武学精通',command=self.preview).pack(side='left')
        ttk.Button(buttons,text='恢复武学精通并备份',command=self.commit,style='Primary.TButton').pack(side='left',padx=10)
        ttk.Label(parent,textvariable=self.note,wraplength=1100).pack(anchor='w',pady=8)
        self.report=tk.Text(parent,height=14,wrap='word',state='disabled');self.report.pack(fill='both',expand=True)
        self.gold.trace_add('write',self.invalidate);self.dark_gold.trace_add('write',self.invalidate)

    def invalidate(self,*_):
        self.prepared=None;self.signature=None;self.note.set('设置已更新，请预览后再应用。')

    def refresh(self):
        if not self.host.busy:self.invalidate()

    def mode_changed(self):
        state='normal' if self.adjust.get() else 'disabled'
        self.gold_entry.configure(state=state);self.dark_entry.configure(state=state);self.invalidate()

    def selections(self):
        root=Path(self.host.game_path.get()).resolve()
        if not self.host.catalog or root!=self.host.catalog.root:raise ValueError('请先读取当前游戏目录')
        if self.host.has_changes():raise ValueError('请先保存或撤销其他草稿')
        if not self.adjust.get():return root,None,None
        try:gold=int(self.gold.get());dark_gold=int(self.dark_gold.get())
        except ValueError:raise ValueError('每级精通请输入整数') from None
        if not all(1<=v<=1000 for v in (gold,dark_gold)):raise ValueError('每级精通请输入 1～1000 的整数')
        return root,gold,dark_gold

    def show(self,text):
        self.report.configure(state='normal');self.report.delete('1.0','end');self.report.insert('1.0',text);self.report.configure(state='disabled')

    def preview(self):
        if self.host.busy:return
        try:signature=self.selections()
        except Exception as error:self.host.error(error);return
        self.prepared=None
        from martial_mastery import plan
        def finish(value):
            if self.selections()!=signature:self.invalidate();return
            self.prepared=value;self.signature=signature
            self.show('\n'.join(value.results+value.notes))
            self.note.set(f'预览完成：将修改 {len(value.payloads)} 个文件；尚未写入游戏。')
        self.host.martial_page.worker('正在检查武学精通配置…',lambda:plan(*signature),finish)

    def commit(self):
        if self.host.busy:return
        try:
            if self.prepared is None or self.selections()!=self.signature:raise ValueError('请先预览当前设置')
            if not self.prepared.payloads:raise ValueError('当前已符合目标，无需重复应用')
        except Exception as error:self.host.error(error);return
        value=self.prepared;root,gold,dark_gold=self.signature
        mode=f'金色每级 +{gold}，暗金每级 +{dark_gold}。' if gold is not None else '仅补回缺失词条，保留当前每级精通数值。'
        if not messagebox.askyesno('确认恢复武学精通',mode+f'\n将修改 {len(value.payloads)} 个配置文件，并自动备份。\n请完全退出游戏，继续应用？',parent=self.host):return
        from martial_mastery import apply
        def finish(backup):
            text='\n'.join(['恢复完成：'+mode,f'备份：{backup}']+value.results+value.notes)
            report=root/'装备编辑器配置/恢复武学精通最近报告.txt'
            try:report.parent.mkdir(exist_ok=True);report.write_text(text,encoding='utf-8')
            except OSError:pass
            self.invalidate();self.show(text);self.note.set('恢复完成，重启游戏并读取存档后生效。')
            self.host.role_page.reset();self.host.martial_page.reset();self.host.reload()
        self.host.martial_page.worker('正在备份并恢复武学精通…',lambda:apply(value),finish)


def build(host,notebook):
    host.mastery_panel=MasteryPanel(host,host.scroll_page(notebook,'恢复武学精通'))
