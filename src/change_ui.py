"""Audit browsing and reviewed sharing in the desktop editor."""
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
from pathlib import Path
from change_log import saved_history,summarize,line,pending_logs
from change_share import operation,write_packet,read_packet,plan_import,read_history_packet

def pending_plan(host):
    role=getattr(host,'role_page',None)
    if role and role.has_changes():
        if host.martial_page.has_changes() or host.drafts or host.effects:raise ValueError('人物与其他页面都有草稿，请先保存其中一组，再导出另一组。')
        if role.dirty:raise ValueError('请先在人物页点击“加入人物草稿”，再导出。')
        return role.library.plan()
    page=host.martial_page
    martial=page.has_changes()
    if martial and (host.drafts or host.effects):raise ValueError('装备和武学都有草稿，请先保存其中一组，再导出另一组，以免同一配置相互覆盖。')
    if martial:
        if getattr(page,'animation_dirty',False) or page.dirty:raise ValueError('请先在武学页将基础设置 / 动画设置加入草稿，再查看或导出待保存改动。')
        return page.library.plan()
    if host.drafts or host.effects:return host.prepare()
    return {},{}

class LogDialog(tk.Toplevel):
    def __init__(self,host,batches,pending=None):
        super().__init__(host);self.title('改动日志');self.transient(host);self.geometry('1120x680');self.minsize(780,460)
        self.host=host;self.records=[]
        for batch in batches:
            for row in batch['entries']:self.records.append(('已保存',batch['time'],row))
        for row in pending or []:self.records.append(('待保存','当前草稿',row))
        main=ttk.Frame(self,padding=16);main.pack(fill='both',expand=True)
        top=ttk.Frame(main);top.pack(fill='x')
        ttk.Label(top,text='搜索名称、操作或效果').pack(side='left')
        self.query=tk.StringVar();ttk.Entry(top,textvariable=self.query).pack(side='left',fill='x',expand=True,padx=8)
        ttk.Button(top,text='导出改动效果',command=lambda:export_changes(host)).pack(side='right')
        self.count=tk.StringVar();ttk.Label(main,textvariable=self.count,style='Sub.TLabel').pack(anchor='w',pady=8)
        self.tree=host.make_tree(main,[('state','状态',65),('category','类别',65),('name','名称',170),('action','操作',170),('effect','实际改动效果',460)],height=12)
        self.detail=tk.Text(main,height=4,wrap='word',font=('Microsoft YaHei UI',10));self.detail.pack(fill='x',pady=8)
        self.tree.bind('<<TreeviewSelect>>',self.select);self.query.trace_add('write',self.render)
        self.render()
    def render(self,*_):
        q=self.query.get().casefold();self.tree.delete(*self.tree.get_children())
        visible=0
        for index,(state,time,row) in enumerate(self.records):
            if q and q not in (state+' '+time+' '+line(row)).casefold():continue
            self.tree.insert('','end',iid=str(index),values=(state,row['category'],row['name'],row['action'],row['effect']));visible+=1
        self.count.set(f'{visible} 条 / 共 {len(self.records)} 条；日志从 V2.0.18 开始记录，待保存不代表已生效。')
    def select(self,*_):
        if not self.tree.selection():return
        state,time,row=self.records[int(self.tree.selection()[0])]
        self.detail.configure(state='normal');self.detail.delete('1.0','end');self.detail.insert('1.0',state+' · '+time+'\n'+line(row));self.detail.configure(state='disabled')

def require_host(host):
    if host.busy:return False
    if not host.catalog:raise ValueError('请先读取游戏目录')
    if Path(host.game_path.get()).resolve()!=host.catalog.root:raise ValueError('目录已变化，请先读取目录')
    return True

def show_logs(host):
    try:
        if not require_host(host):return
    except Exception as e:host.error(e);return
    def work():
        return saved_history(host.catalog.root),pending_logs(host)
    def finish(value):
        batches,pending=value
        host.status.set(f'改动日志已读取：已保存 {sum(len(b["entries"]) for b in batches)} 条，待保存 {len(pending)} 条。')
        LogDialog(host,batches,pending)
    host.martial_page.worker('正在读取改动日志及当前草稿…',work,finish)

class ExportChoice(tk.Toplevel):
    def __init__(self,host,has_pending,history):
        super().__init__(host);self.title('导出改动效果');self.transient(host);self.result=None;self.resizable(False,False)
        main=ttk.Frame(self,padding=20);main.pack(fill='both',expand=True)
        ttk.Label(main,text='选择需要共享的改动',font=('Microsoft YaHei UI',12,'bold')).pack(anchor='w')
        self.choice=tk.StringVar(value='pending' if has_pending else 'latest')
        for key,label,enabled in [('pending','当前待保存改动（原文件尚未写入）',has_pending),('latest','最近一次已保存改动',bool(history)),('all','全部已保存改动（按原顺序读取）',bool(history))]:
            ttk.Radiobutton(main,text=label,value=key,variable=self.choice,state='normal' if enabled else 'disabled').pack(anchor='w',pady=8)
        ttk.Label(main,text='人物自定义模型 PNG 与绑定配置会一起导出，包含复用的已保存贴图。\n装备仅共享同型号共用的天赋效果，不共享实例词条和强化等级。\n武学等整体配置需匹配游戏版本及前置改动。\n所有装备改动仍会记日志；共享文件不包含个人存档。',wraplength=520,style='Sub.TLabel').pack(anchor='w',pady=10)
        bar=ttk.Frame(main);bar.pack(fill='x')
        ttk.Button(bar,text='取消',command=self.destroy).pack(side='right')
        ttk.Button(bar,text='选择导出文件',style='Primary.TButton',command=self.accept).pack(side='right',padx=8)
        self.grab_set();self.wait_visibility();self.wait_window()
    def accept(self):self.result=self.choice.get();self.destroy()

def export_changes(host):
    try:
        if not require_host(host):return
        history=saved_history(host.catalog.root)
        if not history and not host.has_changes():raise ValueError('暂无可导出的改动；先编辑草稿或保存一项改动。')
        choice=ExportChoice(host,host.has_changes(),history).result
        if not choice:return
        target=filedialog.asksaveasfilename(title='导出改动效果',defaultextension='.mjhchanges',initialfile='梦江湖改动效果.mjhchanges',filetypes=[('改动效果共享文件','*.mjhchanges')],parent=host)
        if not target:return
        target=Path(target).resolve()
        if target.is_relative_to(host.catalog.root):raise ValueError('请导出到游戏目录之外，以便分享')
    except Exception as e:host.error(e);return
    def work():
        ops=[]
        if choice=='pending':
            payloads,originals=pending_plan(host)
            if not payloads:raise ValueError('当前没有已加入草稿的改动')
            entries,equipment=summarize(host.catalog.root,payloads,originals,'待保存改动')
            ops.append(operation(host.catalog.root,payloads,originals,entries,equipment))
        else:
            for batch in (history[-1:] if choice=='latest' else history):ops.extend(read_history_packet(host.catalog.root,batch['packet']))
        ops=[(op,blobs) for op,blobs in ops if op['files'] or op.get('model_gifts')]
        if not ops:raise ValueError('没有整体可追溯的共享改动；装备仅支持导出同型号天赋效果，实例词条和强化等级仅记录日志。')
        write_packet(target,ops)
        return sum(len(op['entries']) for op,blobs in ops)
    def done(count):
        host.status.set(f'已导出 {count} 条改动日志及效果：{target}')
        messagebox.showinfo('导出完成',f'已导出 {count} 条改动日志及效果。\n\n{target}\n\n另一台设备通过“读取改动效果”查看并应用。',parent=host)
    host.martial_page.worker('正在校验并导出改动效果…',work,done)

class ImportReview(tk.Toplevel):
    def __init__(self,host,ops,payloads,matched,skipped):
        super().__init__(host);self.title('读取改动效果 · 确认应用');self.transient(host);self.result=False;self.geometry('1040x650')
        main=ttk.Frame(self,padding=16);main.pack(fill='both',expand=True)
        ttk.Label(main,text=f'可更新 {len(payloads)} 个配置文件；匹配 {matched} 个装备型号，跳过 {skipped} 个冲突批次或缺失 / 不支持的型号。',wraplength=990).pack(anchor='w',pady=6)
        ttk.Label(main,text='按记录合并配置，保留目标设备未改动的字段与 MOD。关联批次存在冲突或缺少依赖时整批跳过，原因列在下方；装备仍仅共享型号天赋。',style='Sub.TLabel').pack(anchor='w',pady=6)
        footer=ttk.Frame(main);footer.pack(side='bottom',fill='x',pady=(10,0))
        ttk.Button(footer,text='取消',command=self.destroy).pack(side='right')
        ttk.Button(footer,text='应用改动并备份',style='Primary.TButton',command=self.accept,state='normal' if payloads else 'disabled').pack(side='right',padx=8)
        tree=host.make_tree(main,[('category','类别',80),('name','名称',170),('action','操作',170),('effect','源文件改动效果',520)],height=12)
        for op,blobs in ops:
            for e in op['entries']:tree.insert('','end',values=(e['category'],e['name'],e['action'],e['effect']))
        notes=sorted({n for op,blobs in ops for n in op.get('notes',[])})
        ttk.Label(footer,text='\n'.join(notes),wraplength=600,style='Sub.TLabel').pack(side='left')
        self.grab_set();self.wait_visibility();self.wait_window()
    def accept(self):self.result=True;self.destroy()

def import_changes(host):
    try:
        if not require_host(host):return
        if host.has_changes():raise ValueError('请先保存或撤销当前草稿，再读取共享改动')
        source=filedialog.askopenfilename(title='读取改动效果',filetypes=[('改动效果共享文件','*.mjhchanges')],parent=host)
        if not source:return
        root=host.catalog.root;save=host.save
    except Exception as e:host.error(e);return
    def work():
        ops=read_packet(source);payloads,originals,matched,skipped=plan_import(root,ops,save)
        return ops,payloads,originals,matched,skipped
    def reviewed(value):
        ops,payloads,originals,matched,skipped=value
        if not payloads:
            notes='\n'.join(n for op,blobs in ops for n in op.get('notes',[]) if '已跳过' in n)
            messagebox.showinfo('无需写入',f'配置已应用或没有可应用改动。\n匹配 {matched} 个装备型号，跳过 {skipped} 项。\n'+notes,parent=host);return
        if not ImportReview(host,ops,payloads,matched,skipped).result:return
        def apply():
            from engine import transaction
            for path,before in originals.items():
                if (path.read_bytes() if path.exists() else None)!=before:raise ValueError('配置在预览后发生变化，请重新读取共享文件：'+path.name)
            return transaction(root,payloads,originals,'读取共享改动效果',share_operations=ops)
        def done(backup):
            host.martial_page.reset();host.role_page.reset();host.reload();host.refresh_caps()
            host.status.set(f'共享改动已应用；匹配 {matched} 个装备型号，跳过 {skipped} 个冲突批次或不支持型号。备份：{backup}')
            messagebox.showinfo('读取完成',host.status.get(),parent=host)
        host.martial_page.worker('正在验证、备份并应用共享改动…',apply,done)
    host.martial_page.worker('正在读取并校验共享改动…',work,reviewed)
