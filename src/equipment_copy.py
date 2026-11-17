"""Copy selected equipment instances into the native cross-run warehouse."""
from dataclasses import dataclass
from engine import Save,transaction,ensure_closed
from feature_save import NativeSave,u32,put
from change_log import entry

@dataclass
class CopyPlan:
    save:Save
    payload:bytes
    ids:tuple
    source_id:int
    name:str

def plan(save,source_id,count):
    if type(count)is not int or not 1<=count<=9999:raise ValueError('复制数量范围为1～9999')
    if type(source_id)is not int:raise ValueError('请选择有效装备实例')
    source=next((r for r in save.records if r['id']==source_id and r['editable']),None)
    if source is None:raise ValueError('所选装备不可复制，未知归属或不兼容记录已跳过')
    before=NativeSave(save.data);native=NativeSave(save.data)
    rows=native.indexed(24);counter=native.counter(10,24)
    if source_id not in rows:raise ValueError('所选装备已失效')
    last=u32(counter,20)
    if last+count>=0x7fffffff or len(rows)+count>100000:raise ValueError('装备编号或记录数量超出支持范围')
    original=rows[source_id];ids=tuple(range(last+1,last+count+1))
    for ident in ids:
        row=bytearray(original)
        put(row,16,ident);put(row,20,save.main_role)
        row[34]=2;row[35]=0;row[36]=0
        rows[ident]=row
    put(counter,20,ids[-1]);native.tables[24]=[rows[k] for k in sorted(rows)]
    result=native.bytes();check=Save(save.path,save.catalog,result)
    checked={r['id']:r for r in check.records}
    for ident in ids:
        r=checked.get(ident)
        if not r or not r['editable'] or check.location(r)!='周目仓库':raise ValueError('复制装备的仓库归属验证失败')
        if check.draft(r)!=save.draft(source):raise ValueError('复制装备的强化或词条验证失败')
    # Adding instances must preserve every preexisting record, including unknown MOD records.
    native.tables[24]=before.tables[24];native.tables[1]=before.tables[1]
    if native.bytes()!=save.data:raise ValueError('复制装备影响了其他存档数据')
    return CopyPlan(save,result,ids,source_id,source['name'])

def apply(value):
    ensure_closed();save=value.save
    if save.path.read_bytes()!=save.data:raise ValueError('存档已发生变化，请重新读取并预览')
    for path,raw in save.catalog.snapshots.items():
        if path.read_bytes()!=raw:raise ValueError('配置已发生变化，请重新读取并预览：'+str(path))
    logs=[entry('装备',value.name,'复制到周目仓库',f'来源实例{value.source_id}；数量{len(value.ids)}；新实例{value.ids[0]}～{value.ids[-1]}')]
    return transaction(save.catalog.root,{save.path:value.payload},{save.path:save.data},'复制装备到周目仓库',audit_entries=logs)

def show(host):
    import tkinter as tk
    from tkinter import ttk,messagebox
    from pathlib import Path
    if host.busy:return
    try:
        if not host.save or not host.current:raise ValueError('请先选择要复制的装备')
        if Path(host.game_path.get()).resolve()!=host.catalog.root:raise ValueError('目录已变化，请先重新读取')
        if host.has_changes():raise ValueError('请先保存或撤销当前草稿，再复制装备')
        source=host.current
        if not source['editable']:raise ValueError('此装备记录不可复制')
    except Exception as error:host.error(error);return
    dialog=tk.Toplevel(host);dialog.title('复制装备到周目仓库');dialog.transient(host)
    box=ttk.Frame(dialog,padding=20);box.pack(fill='both',expand=True)
    ttk.Label(box,text=f"{source['name']} +{source['grade']} · 实例 {source['id']}",style='Title.TLabel').pack(anchor='w')
    ttk.Label(box,text='副本保留强化、基础属性、铸造属性和蓝字加成；每件分配独立实例编号。\n同型号的强化效果继续使用现有配置，副本统一放入当前存档的周目仓库。',wraplength=650).pack(anchor='w',pady=12)
    quantity=tk.StringVar(value='1');row=ttk.Frame(box);row.pack(fill='x')
    ttk.Label(row,text='复制数量').pack(side='left');ttk.Spinbox(row,from_=1,to=9999,textvariable=quantity,width=12).pack(side='left',padx=10)
    state={'prepared':None};report=tk.StringVar(value='请输入数量并预览。')
    ttk.Label(box,textvariable=report,wraplength=650).pack(anchor='w',pady=14)
    buttons=ttk.Frame(box);buttons.pack(fill='x');commit=ttk.Button(buttons,text='复制并备份',state='disabled')
    def invalidate(*_):state['prepared']=None;commit.configure(state='disabled');report.set('数量已变化，请重新预览。')
    quantity.trace_add('write',invalidate)
    def preview():
        if host.busy:return
        try:count=int(quantity.get())
        except ValueError:host.error(ValueError('复制数量必须是整数'));return
        save=host.save
        def ready(value):
            if not dialog.winfo_exists() or quantity.get()!=str(count):return
            state['prepared']=value;commit.configure(state='normal')
            report.set(f'目标存档：{save.path}\n复制{len(value.ids)}件到周目仓库，新实例{value.ids[0]}～{value.ids[-1]}。\n预览尚未写入；点击“复制并备份”执行。')
        host.martial_page.worker('正在验证装备副本与编号…',lambda:plan(save,source['id'],count),ready)
    def commit_copy():
        if host.busy:return
        value=state['prepared']
        if value is None:return
        def finish(backup):
            if dialog.winfo_exists():dialog.destroy()
            host.reload();host.status.set(f'已复制{len(value.ids)}件装备到周目仓库；备份：{backup}')
            messagebox.showinfo('复制完成',f'已复制{len(value.ids)}件“{value.name}”到目标存档的周目仓库。\n备份：{backup}',parent=host)
        host.martial_page.worker('正在备份并复制装备…',lambda:apply(value),finish)
    ttk.Button(buttons,text='预览复制',command=preview).pack(side='left')
    commit.configure(command=commit_copy);commit.pack(side='left',padx=8)
    ttk.Button(buttons,text='取消',command=dialog.destroy).pack(side='right')
    dialog.protocol('WM_DELETE_WINDOW',dialog.destroy);dialog.bind('<<DesktopCancel>>',lambda _:dialog.destroy())
    dialog.grab_set();host.wait_window(dialog)
