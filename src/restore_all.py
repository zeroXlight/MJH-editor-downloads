"""Review and restore every file recorded by this editor's completed backups."""
from dataclasses import dataclass
from pathlib import Path
import json
from engine import digest, ensure_closed, transaction

@dataclass
class RestoreAllPlan:
    root: Path
    payloads: dict
    originals: dict
    files: list
    history: dict
    skipped_incomplete: int

    @property
    def changed(self):
        return sum(self.payloads[p] != self.originals[p] for p in self.payloads)

    @property
    def preserved(self):
        return [row for row in self.files if row.get('preserved')]

def history_files(root):
    directory=root/'装备编辑器备份'
    if not directory.exists():return []
    return sorted(directory.glob('*/manifest.json'),key=lambda p:p.parent.name)

def target_path(root, name):
    relative=Path(name)
    if relative.is_absolute() or '..' in relative.parts:raise ValueError('备份目标路径无效：'+str(name))
    target=(root/relative).resolve()
    if not target.is_relative_to(root) or target==root or target.is_relative_to(root/'装备编辑器备份'):
        raise ValueError('备份目标路径越界：'+str(name))
    return target

def plan_restore_all(root):
    """Read-only. Preserve MOD epochs and restore compatible editor changes."""
    root=Path(root).resolve();first={};known_hashes={};history={};incomplete=0
    for manifest_path in history_files(root):
        if not manifest_path.resolve().is_relative_to((root/'装备编辑器备份').resolve()):
            raise ValueError('备份目录路径越界')
        raw=manifest_path.read_bytes();history[manifest_path]=digest(raw)
        try:manifest=json.loads(raw.decode('utf-8'))
        except Exception as error:raise ValueError('备份清单损坏：'+str(manifest_path)) from error
        if Path(manifest.get('root','')).resolve()!=root:raise ValueError('备份属于另一个游戏目录：'+str(manifest_path))
        if manifest.get('complete') is not True:
            incomplete+=1;continue
        entries=manifest.get('entries')
        if not isinstance(entries,list):raise ValueError('备份清单没有有效文件列表：'+str(manifest_path))
        seen=set()
        for entry in entries:
            path=target_path(root,entry['path'])
            if path in seen:raise ValueError('备份清单存在重复文件：'+str(path))
            if type(entry.get('exists')) is not bool:raise ValueError('备份存在标记无效：'+str(path))
            seen.add(path)
            hashes=known_hashes.setdefault(path,set())
            is_save=path.name.lower() in ('save.sav','saveai.sav')
            # A new pre-edit image begins a MOD epoch. Do not restore a file
            # from before that external installation on subsequent operations.
            before_hash=entry.get('before_sha256')
            if not is_save and path in first and before_hash and before_hash not in hashes:
                first[path]=(manifest_path,entry);hashes.clear()
            first.setdefault(path,(manifest_path,entry))
            hashes.update(h for h in (before_hash,entry.get('after_sha256')) if h)
    payloads={};originals={};files=[]
    for path,(manifest_path,entry) in first.items():
        current=path.read_bytes() if path.exists() else None
        if entry['exists']:
            folder=manifest_path.parent.resolve();source=(folder/entry['backup']).resolve()
            if not source.is_relative_to(folder) or source==manifest_path.resolve():raise ValueError('备份文件路径无效：'+str(source))
            before=source.read_bytes()
            if digest(before)!=entry.get('before_sha256'):raise ValueError('备份文件校验失败：'+str(source))
        else:
            before=None
        is_save=path.name.lower() in ('save.sav','saveai.sav')
        preserved=not is_save and current!=before and (current is None or digest(current) not in known_hashes[path])
        action='移除新增文件' if before is None else '恢复修改前文件'
        relative=path.relative_to(root).as_posix()
        if relative in ('DreamRivakes_Data/Plugins/RaceLogic_Release_x64.dll','DreamRivakes_Data/Plugins/ClientDll.dll'):
            from shadow_runtime import detected,known
            if detected(root):
                try:
                    if not known(root):raise ValueError('未验证的暗影版本')
                    if relative.endswith('/ClientDll.dll'):
                        from pet_runtime import original
                        from martial_limit_enhance import normalize_client
                        from shadow_runtime import client_supported
                        if not client_supported(root,current):raise ValueError('未知客户端运行库')
                        before=original(normalize_client(current)[0])
                    else:
                        from external_runtime import detach
                        from growth_runtime import _build_runtime,supported_patch
                        if not supported_patch(current):raise ValueError('运行库需要先恢复编辑器支持')
                        parent,_=detach(current)
                        before=_build_runtime(parent)
                    preserved=False;action='撤销编辑器功能，保留暗影支持'
                except (ValueError,KeyError,OSError,TypeError):preserved=True
        if preserved:
            originals[path]=current
            files.append({'path':relative,'action':'保留外部MOD文件','backup':manifest_path.parent.name,
                          'changed':False,'save':False,'preserved':True})
            continue
        payloads[path]=before;originals[path]=current
        files.append({'path':relative, 'action':action,
                      'backup':manifest_path.parent.name,'changed':current!=before,
                      'save':path.name.lower() in ('save.sav','saveai.sav')})
    # Keep native hooks, Lua and their tables together if an unknown MOD owns
    # either half. Restoring only one side could leave a working MOD broken.
    critical={'DreamRivakes_Data/resources.assets','DreamRivakes_Data/Plugins/RaceLogic_Release_x64.dll','DreamRivakes_Data/Plugins/ClientDll.dll'}
    if any(row.get('preserved') and row['path'] in critical for row in files):
        for row in files:
            name=row['path']
            if name in critical or name.startswith(('TableData/','装备编辑器配置/','DreamRivakes_Data/StreamingAssets/')):
                payloads.pop(root/name,None)
                row.update(action='保留MOD关联配置',changed=False,preserved=True)
    return RestoreAllPlan(root,payloads,originals,files,history,incomplete)

def apply_restore_all(plan):
    ensure_closed()
    current={p:digest(p.read_bytes()) for p in history_files(plan.root)}
    if current!=plan.history:raise ValueError('备份历史在预览后发生变化，请重新点击还原所有修改')
    for path,expected in plan.originals.items():
        actual=path.read_bytes() if path.exists() else None
        if actual!=expected:raise ValueError('文件已变化，请重新生成还原清单：'+str(path))
    from change_log import entry
    audit=[entry('还原','全部修改',row['action'],row['path']) for row in plan.files if row['changed'] or row.get('preserved')]
    return transaction(plan.root,plan.payloads,plan.originals,'还原所有修改（保留外部MOD）',audit_entries=audit)

class RestoreAllDialog:
    """Factory-like wrapper: result is set only by the explicit restore button."""
    def __init__(self,master,plan,has_drafts=False):
        import tkinter as tk
        from tkinter import ttk
        from desktop_theme import DataTree
        self.result=False;self.plan=plan
        win=self.window=tk.Toplevel(master);win.title('还原所有修改 · 确认恢复清单');win.transient(master)
        width=min(1000,win.winfo_screenwidth()-80);height=min(720,win.winfo_screenheight()-120)
        master.update_idletasks()
        x=max(0,min(master.winfo_rootx()+(master.winfo_width()-width)//2,win.winfo_screenwidth()-width))
        y=max(0,min(master.winfo_rooty()+(master.winfo_height()-height)//2,win.winfo_screenheight()-height))
        win.geometry(f'{width}x{height}+{x}+{y}');win.minsize(min(width,760),min(height,540))
        main=ttk.Frame(win,padding=20);main.pack(fill='both',expand=True)
        footer=ttk.Frame(main);footer.pack(side='bottom',fill='x',pady=(8,0))
        ttk.Button(footer,text='取消',command=win.destroy).pack(side='right')
        def accept():self.result=True;win.destroy()
        ttk.Button(footer,text='确认还原所有修改',style='Primary.TButton',command=accept).pack(side='right',padx=8)
        ttk.Label(main,text='还原所有装备 / 武学修改',style='Title.TLabel').pack(anchor='w')
        saves=sum(x['changed'] and x['save'] for x in plan.files)
        removed=sum(x['changed'] and x['action']=='移除新增文件' for x in plan.files)
        ttk.Label(main,text=f'需要还原 {plan.changed} 个文件 · 含 {saves} 个存档 · 移除 {removed} 个新增文件 · 保留 {len(plan.preserved)} 个外部MOD文件',style='Sub.TLabel').pack(anchor='w',pady=(8,12))
        ttk.Label(main,text='装备、武学等配置恢复到首次修改前；有后装MOD记录时采用MOD更新后的基线。暗影运行库保留兼容支持。',wraplength=width-70).pack(anchor='w')
        if saves:
            ttk.Label(main,text='包含存档整文件恢复：装备会还原，存档内之后的游戏进度也会回退。',foreground='#b45309',wraplength=width-70).pack(anchor='w',pady=8)
        if has_drafts:ttk.Label(main,text='未保存的装备与武学草稿也将撤销。',wraplength=width-70).pack(anchor='w',pady=5)
        ttk.Label(main,text='外部MOD改过的文件按清单保留，不会中止其他可还原文件；已验证的暗影运行库仅撤销编辑器功能、保留暗影支持。还原前自动备份当前状态。',style='Sub.TLabel',wraplength=width-70).pack(anchor='w',pady=8)
        self.query=tk.StringVar();ttk.Entry(main,textvariable=self.query).pack(fill='x',pady=(4,8))
        ttk.Label(main,text='搜索文件路径或来源备份',style='Sub.TLabel').pack(anchor='w')
        if plan.skipped_incomplete:ttk.Label(main,text=f'已忽略 {plan.skipped_incomplete} 次未完成操作的备份。',style='Sub.TLabel').pack(anchor='w')
        wrap=ttk.Frame(main);wrap.pack(fill='both',expand=True,pady=8)
        self.tree=DataTree(wrap,columns=('action','path','source'),show='headings')
        for key,label,size in [('action','还原操作',145),('path','文件路径',420),('source','首次备份',270)]:
            self.tree.heading(key,text=label);self.tree.column(key,width=size,minwidth=80)
        self.tree.grid(row=0,column=0,sticky='nsew');wrap.rowconfigure(0,weight=1);wrap.columnconfigure(0,weight=1)
        v=ttk.Scrollbar(wrap,command=self.tree.yview);v.grid(row=0,column=1,sticky='ns')
        h=ttk.Scrollbar(wrap,orient='horizontal',command=self.tree.xview);h.grid(row=1,column=0,sticky='ew')
        self.tree.configure(yscrollcommand=v.set,xscrollcommand=h.set)
        def filter_rows(*_):
            self.tree.delete(*self.tree.get_children());query=self.query.get().strip().casefold()
            for row in plan.files:
                if query and query not in (row['path']+' '+row['backup']).casefold():continue
                self.tree.insert('','end',values=(row['action'] if row['changed'] or row.get('preserved') else '已是修改前状态',row['path'],row['backup']))
        self.query.trace_add('write',filter_rows);filter_rows()
        win.protocol('WM_DELETE_WINDOW',win.destroy);win.grab_set();master.wait_window(win)
