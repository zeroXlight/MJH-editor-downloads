import tkinter as tk
from tkinter import ttk
from martial_limit_enhance_ui import Panel as BasePanel
class Panel(BasePanel):
    def __init__(self,host,parent):
        self.host=host;self.prepared=None;self.signature=None;self.mode=tk.StringVar(value='启用角色突破');self.note=tk.StringVar(value='预览后应用，重启游戏生效。')
        ttk.Label(parent,text='恢复角色突破',style='Title.TLabel').pack(anchor='w',pady=8)
        ttk.Label(parent,text='在游戏主菜单“周目累计”新增“角色突破”。按手游角色卡名单匹配当前PC人物，另外保留玩家自建角色，支持名称和编号查询。\n界面采用手游式三列卡片与水墨标签，可按等级、品质、主角排序或筛选自建角色。可查看基础属性、天赋、默认装备和武学，资料只读。',wraplength=1100).pack(anchor='w',pady=8)
        ttk.Label(parent,text='每张角色卡改为500经脉点，最高+10；解除手游开服时间和剧本阶段导致的+5限制，保留逐级费用和余额检查。\n只对对应人物跨周目生效，沿用原生基础属性范围，不增加其他人物的属性。\n关闭时停用入口和加成，保留进度；重新开启继续使用。不修改其他功能或存档。',wraplength=1100).pack(anchor='w',pady=8)
        row=ttk.Frame(parent);row.pack(fill='x',pady=8)
        box=ttk.Combobox(row,textvariable=self.mode,values=['启用角色突破','关闭角色突破'],state='readonly',width=22);box.pack(side='left');box.bind('<<ComboboxSelected>>',self.invalidate)
        ttk.Button(row,text='预览角色突破',command=self.preview).pack(side='left',padx=8);ttk.Button(row,text='应用并备份',command=self.commit,style='Primary.TButton').pack(side='left')
        ttk.Label(parent,textvariable=self.note,wraplength=1100).pack(anchor='w',pady=8)
        self.report=tk.Text(parent,height=14,wrap='word',state='disabled');self.report.pack(fill='both',expand=True)
    def selections(self):
        root,_=super().selections();return root,self.mode.get()=='启用角色突破'
    def preview(self):
        if self.host.busy:return
        try:signature=self.selections()
        except Exception as e:self.host.error(e);return
        from role_breakthrough import plan
        def done(value):
            if self.selections()!=signature:return
            self.prepared=value;self.signature=signature;self.show('\n'.join(value[2]+value[3]));self.note.set(f'预览完成，将修改{len(value[0])}个文件；尚未写入。')
        self.host.martial_page.worker('正在核对角色突破、经脉扣费和功能隔离…',lambda:plan(*signature),done)
    def commit(self):
        if self.host.busy:return
        try:
            if not self.prepared or self.signature!=self.selections():raise ValueError('请先预览当前选择')
            if not self.prepared[0]:raise ValueError('当前已符合目标，无需重复应用')
        except Exception as e:self.host.error(e);return
        from feature_save import apply
        value=self.prepared;signature=self.signature
        def done(backup):
            self.invalidate();self.show('\n'.join(value[2])+f'\n备份：{backup}');self.note.set('已完成，重启游戏后生效。');self.host.reload()
        self.host.martial_page.worker('正在备份并应用角色突破…',lambda:apply(signature[0],value),done)
def build(host,notebook):host.role_breakthrough_panel=Panel(host,host.scroll_page(notebook,'恢复角色突破'))
