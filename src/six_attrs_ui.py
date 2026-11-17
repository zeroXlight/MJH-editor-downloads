"""Reviewable enable/disable controls for the six-attribute profile."""
from pathlib import Path
import tkinter as tk
from tkinter import ttk

class SixAttrsPanel:
    def __init__(self,host,parent):
        self.host=host;self.prepared=None;self.signature=None;self.loaded_root=None
        self.mode=tk.StringVar(value='启用恢复')
        self.restore_forge=tk.BooleanVar(value=False);self.restore_martial=tk.BooleanVar(value=False)
        self.note=tk.StringVar(value='先预览变更，再应用；不修改存档文件。')
        ttk.Label(parent,text='恢复六项属性以及武学攻击',style='Title.TLabel').pack(anchor='w',pady=10)
        ttk.Label(parent,text='恢复力道、体质、精力、内劲、灵巧、悟性，以及八系攻击、属性加点和全部直接衍生加成。\n原 PC 转换记录与统一攻击来源保留，恢复启用期间停用对应规则；关闭后可以继续使用原规则。\n使用游戏已有存档字段，沿用剩余点数和已分配点数。重新下载覆盖补丁后，可在这里再次启用修复。',wraplength=1100,style='Sub.TLabel').pack(anchor='w',pady=8)
        ttk.Label(parent,text='游戏界面按手游原角色页重建：两列三行六属性、原生加减按钮、长按连续加减、底部剩余点数、重置与确定。\n待加点数和衍生收益绿色预览，主面板按装备武器显示对应攻击，详情页列出八系攻击；重置退回已确认的加点，保留装备、武学及丹药属性。',wraplength=1100).pack(anchor='w',pady=8)
        ttk.Checkbutton(parent,text='恢复精通、属性锻造（手游生成权重及基础/追加成长）',variable=self.restore_forge,command=self.invalidate).pack(anchor='w',pady=4)
        ttk.Checkbutton(parent,text='恢复武学精通、属性（手游原成长词条与每级数值）',variable=self.restore_martial,command=self.invalidate).pack(anchor='w',pady=4)
        row=ttk.Frame(parent);row.pack(fill='x',pady=8)
        ttk.Label(row,text='操作').pack(side='left')
        box=ttk.Combobox(row,textvariable=self.mode,values=['启用恢复','关闭恢复，使用原 PC 规则'],state='readonly',width=35)
        box.pack(side='left',padx=10);box.bind('<<ComboboxSelected>>',self.invalidate)
        ttk.Button(row,text='预览六项属性恢复',command=self.preview).pack(side='left',padx=8)
        ttk.Button(row,text='应用并备份',command=self.commit,style='Primary.TButton').pack(side='left')
        ttk.Label(parent,text='手游每点：力道→拳／刀攻击；灵巧→腿／剑攻击；内劲→内／医／奇／暗攻击，各 +10。\n体质→生命、防御、回血、反击；精力→真气、防御、回气、破招；悟性→天赋值、暴抗、抗连、暴伤。\n八系精通采用手游对应转换；不替换 PC 基础生命、真气、防御、速度及等级成长，不会补发旧档点数。',wraplength=1100).pack(anchor='w',pady=8)
        ttk.Label(parent,textvariable=self.note,wraplength=1100).pack(anchor='w',pady=8)
        self.report=tk.Text(parent,height=16,wrap='word',state='disabled');self.report.pack(fill='both',expand=True)

    def invalidate(self,*_):
        self.prepared=None;self.signature=None;self.note.set('请预览当前操作，再应用。')

    def refresh(self):
        if self.host.busy:return
        root=Path(self.host.game_path.get()).resolve()
        if self.loaded_root!=root:
            self.loaded_root=root
            import json
            try:state=json.loads((root/'装备编辑器配置/六项属性恢复状态.json').read_text('utf8'))
            except (OSError,ValueError):state={}
            self.restore_forge.set(bool(state.get('restore_forge',False)))
            self.restore_martial.set(bool(state.get('restore_martial',False)))
        self.invalidate()

    def selections(self):
        root=Path(self.host.game_path.get()).resolve()
        if not self.host.catalog or root!=self.host.catalog.root:raise ValueError('请先读取当前游戏目录')
        if self.host.has_changes():raise ValueError('请先保存或撤销其他草稿')
        return root,self.mode.get()=='启用恢复',self.restore_forge.get(),self.restore_martial.get()

    def show(self,text):
        self.report.configure(state='normal');self.report.delete('1.0','end');self.report.insert('1.0',text);self.report.configure(state='disabled')

    def preview(self):
        if self.host.busy:return
        try:signature=self.selections()
        except Exception as error:self.host.error(error);return
        self.prepared=None
        from six_attrs import plan
        def finish(value):
            if self.selections()!=signature:self.invalidate();return
            self.prepared=value;self.signature=signature;self.show('\n'.join(value.results+value.notes))
            self.note.set(f'预览完成：将修改 {len(value.payloads)} 个文件；尚未写入。')
        self.host.martial_page.worker('正在检查六属性与原有规则…',lambda:plan(*signature),finish)

    def commit(self):
        if self.host.busy:return
        try:
            if self.prepared is None or self.selections()!=self.signature:raise ValueError('请先预览当前操作')
            if not self.prepared.payloads:raise ValueError('当前已符合目标，无需重复应用')
        except Exception as error:self.host.error(error);return
        value=self.prepared
        from six_attrs import apply
        def finish(backup):
            text='\n'.join(['应用完成，备份：'+str(backup)]+value.results+value.notes)
            report=value.root/'装备编辑器配置/六项属性恢复最近报告.txt'
            try:report.parent.mkdir(exist_ok=True);report.write_text(text,encoding='utf8')
            except OSError:pass
            self.invalidate();self.show(text);self.note.set('已完成。重启游戏并读取存档后生效。')
            self.host.role_page.reset();self.host.martial_page.reset();self.host.reload()
        self.host.martial_page.worker('正在备份并应用六属性规则…',lambda:apply(value),finish)

def build(host,notebook):
    host.six_attrs_panel=SixAttrsPanel(host,host.scroll_page(notebook,'恢复六项属性以及武学攻击'))
