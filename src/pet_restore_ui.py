"""Pet restoration controller shared by the Tk and desktop feature views."""
from pathlib import Path
import tkinter as tk
from tkinter import ttk

class PetPanel:
    def __init__(self,host,parent):
        self.host=host;self.prepared=None;self.signature=None
        self.mode=tk.StringVar(value='启用恢复')
        self.note=tk.StringVar(value='请预览当前游戏目录，再应用并备份。')
        ttk.Label(parent,text='恢复宠物',style='Title.TLabel').pack(anchor='w',pady=10)
        ttk.Label(parent,text='在游戏“周目累计”下增加“宠物培养”，沿用原生宠物形态、助战与存档。\n解锁、培养与奇经八脉共用经脉经验；只有实际进入助战阵容的宠物提供收益。培养总览显示当前助战总值。',wraplength=1100).pack(anchor='w',pady=8)
        ttk.Label(parent,text='首次启用向现有兼容存档赠送30000经脉经验，每份存档仅领取一次。\n资源修改栏可重复使用“增加经脉点900000”，每次累加90万。',wraplength=1100).pack(anchor='w',pady=8)
        ttk.Label(parent,text='形态按品质解锁：白1000、绿2000、蓝4000、紫8000、橙16000、金32000、暗金64000。\n升级：1000×1.5^当前等级，小数向上取整；1→2为1500、2→3为2250、3→4为3375。\n基础形态达到5级后解锁进阶形态；同一家族形态共用助战位置，属性成长采用对应手游数值。',wraplength=1100,style='Sub.TLabel').pack(anchor='w',pady=8)
        ttk.Label(parent,text='当前恢复PC资源保留的10类50种形态；手游另增的形态及新特性尚未移植。\n基础形态+5后，在游戏右侧“可用造型”选择未解锁形态，解锁后继续培养。旧版已启用的请重新应用一次。',wraplength=1100,style='Sub.TLabel').pack(anchor='w',pady=8)
        row=ttk.Frame(parent);row.pack(fill='x',pady=8)
        box=ttk.Combobox(row,textvariable=self.mode,values=['启用恢复','关闭恢复'],state='readonly',width=24);box.pack(side='left')
        box.bind('<<ComboboxSelected>>',self.invalidate)
        ttk.Button(row,text='预览宠物恢复',command=self.preview).pack(side='left',padx=10)
        ttk.Button(row,text='应用并备份',command=self.commit,style='Primary.TButton').pack(side='left')
        ttk.Label(parent,textvariable=self.note,wraplength=1100).pack(anchor='w',pady=8)
        self.report=tk.Text(parent,height=14,wrap='word',state='disabled');self.report.pack(fill='both',expand=True)
    def invalidate(self,*_):
        self.prepared=None;self.signature=None;self.note.set('请重新预览当前操作。')
    def selections(self):
        root=Path(self.host.game_path.get()).resolve()
        if not self.host.catalog or root!=self.host.catalog.root:raise ValueError('请先读取当前游戏目录')
        if self.host.has_changes():raise ValueError('请先保存或撤销其他草稿')
        return root,self.mode.get()=='启用恢复'
    def show(self,text):
        self.report.configure(state='normal');self.report.delete('1.0','end');self.report.insert('1.0',text);self.report.configure(state='disabled')
    def preview(self):
        if self.host.busy:return
        try:signature=self.selections()
        except Exception as error:self.host.error(error);return
        from pet_restore import plan
        def finish(value):
            if self.selections()!=signature:return
            self.prepared=value;self.signature=signature;self.show('\n'.join(value.prepared[2]+value.prepared[3]))
            self.note.set(f'预览完成：将修改{len(value.prepared[0])}个文件；尚未写入。')
        self.host.martial_page.worker('正在核对宠物、经脉余额和存档…',lambda:plan(*signature),finish)
    def commit(self):
        if self.host.busy:return
        try:
            if self.prepared is None or self.selections()!=self.signature:raise ValueError('请先预览当前操作')
            if not self.prepared.prepared[0]:raise ValueError('当前已符合目标，无需重复应用')
        except Exception as error:self.host.error(error);return
        value=self.prepared
        from pet_restore import apply
        def finish(backup):
            self.invalidate();self.show('\n'.join(value.prepared[2]+value.prepared[3])+f'\n备份：{backup}')
            self.note.set('已完成。重启游戏后生效。');self.host.reload()
        self.host.martial_page.worker('正在备份并应用宠物恢复…',lambda:apply(value),finish)

def build(host,notebook):host.pet_panel=PetPanel(host,host.scroll_page(notebook,'恢复宠物'))
