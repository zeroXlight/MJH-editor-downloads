"""Explicit save and character selection, preview, then backed-up transaction."""
import copy
import tkinter as tk
from tkinter import ttk,messagebox
from pathlib import Path
from engine import ensure_closed,transaction
from role_save_sync import eligible,preview,plan

def open_sync(page):
    if not page.available():return
    lib=page.library
    if page.dirty or lib.modified():page.host.error(ValueError('请先保存人物修改，再补齐旧档'));return
    if page.host.drafts or page.host.effects or page.host.martial_page.has_changes():
        page.host.error(ValueError('请先保存或撤销装备、武学草稿，再补齐旧档'));return
    characters=eligible(lib)
    if not characters:page.host.error(ValueError('没有已保存的编辑／新增人物，请先保存人物配置'));return
    saves=page.host.catalog.saves()
    if not saves:page.host.error(ValueError('当前游戏目录未找到存档'));return
    win=tk.Toplevel(page);win.title('补齐人物到指定存档 · 保留已有角色进度');win.geometry('1080x740');win.minsize(850,600);win.transient(page.winfo_toplevel())
    ttk.Label(win,text='只补齐缺失人物；已有角色、队伍、装备、养成与剧情记录保留。先预览，确认后备份并写入所选存档。\n读档后进入人物设定的城市／根场景，由游戏原生任务创建人物；不会直接把角色塞进队伍。',wraplength=1020).pack(anchor='w',padx=15,pady=12)
    labels={label+' · '+path.relative_to(lib.root).as_posix():path for label,path in saves};slot=tk.StringVar(value=next(iter(labels)))
    row=ttk.Frame(win);row.pack(fill='x',padx=15);ttk.Label(row,text='目标存档：').pack(side='left');ttk.Combobox(row,textvariable=slot,values=list(labels),state='readonly',width=70).pack(side='left',fill='x',expand=True)
    ttk.Label(win,text='选择要补齐的人物（Ctrl / Shift 多选，默认全选）：').pack(anchor='w',padx=15,pady=8)
    footer=ttk.Frame(win);footer.pack(side='bottom',fill='x')
    tree=page.host.make_tree(win,[('name','已保存的人物',230),('status','检测结果',250),('location','生成位置',500)],height=15)
    for rid,name in characters:tree.insert('','end',iid=str(rid),values=(name,'尚未检查',''))
    tree.selection_set(tree.get_children())
    detail=tk.StringVar(value='请选择存档及人物，然后点击预览。');ttk.Label(footer,textvariable=detail,wraplength=1010).pack(fill='x',padx=15,pady=10)
    buttons=ttk.Frame(footer);buttons.pack(fill='x',padx=15,pady=10);proposal=[None];rendering=[False]
    def invalidate(*_):
        if rendering[0]:return
        proposal[0]=None;apply.configure(state='disabled');detail.set('选择已变化，请重新预览。')
    def check():
        if page.host.busy:return
        ids=[int(x) for x in tree.selection()]
        if not ids:page.host.error(ValueError('请至少选择一个人物'));return
        try:
            value=preview(lib,labels[slot.get()],ids)
            rendering[0]=True
            try:
                for r in value['rows']:tree.item(str(r['rid']),values=(r['name'],r['status'],r['location']))
            finally:rendering[0]=False
            proposal[0]=value;n=sum(r['status']=='补齐缺失人物' for r in value['rows'])
            detail.set(f'所选 {len(ids)} 人；需要补齐 {n} 人，其余跳过。保存退出游戏后再写入；读档后进入对应城市，若已在该城市则离开并重新进入。')
            apply.configure(state='normal' if n else 'disabled')
        except Exception as e:proposal[0]=None;apply.configure(state='disabled');page.host.error(e)
    def commit():
        value=proposal[0]
        if not value or page.host.busy:return
        if ids_changed(value):invalidate();return
        try:ensure_closed()
        except Exception as e:page.host.error(e);return
        targets=[r for r in value['rows'] if r['status']=='补齐缺失人物']
        message='目标：'+str(value['path'])+'\n\n'+ '\n'.join(r['name']+' → '+r['location'] for r in targets)+'\n\n将备份存档及本次新增任务配置。只添加一次性补齐任务，保留已有角色记录。继续？'
        if not messagebox.askokcancel('确认补齐旧档人物',message,parent=win):return
        worklib=copy.deepcopy(lib)
        win.destroy()
        def work():
            ensure_closed()
            payloads,originals,n=plan(worklib,value)
            ensure_closed()
            backup=transaction(lib.root,payloads,originals,'补齐所选旧档缺失人物')
            return backup,n
        def finish(result):
            backup,n=result;page.reset();page.host.martial_page.reset();page.host.reload()
            page.host.status.set(f'已为所选存档安排 {n} 个补齐任务。备份：{backup}')
            messagebox.showinfo('已写入所选存档',f'已添加 {n} 个一次性补齐任务。\n启动游戏读取刚才选的存档，再进入对应城市／根场景；如果当前已在该城，离开后重新进入。\n任务执行后请在游戏内保存。其他存档及已有角色进度保留。\n\n备份：{backup}',parent=page)
        page.host.martial_page.worker('正在校验、备份并补齐指定存档…',work,finish)
    def ids_changed(value):
        return value['path']!=labels[slot.get()] or {r['rid'] for r in value['rows']}!={int(i) for i in tree.selection()}
    ttk.Button(buttons,text='预览所选存档',command=check).pack(side='left');apply=ttk.Button(buttons,text='备份并补齐缺失人物',command=commit,state='disabled');apply.pack(side='right')
    slot.trace_add('write',invalidate);tree.bind('<<TreeviewSelect>>',invalidate)
    win.grab_set()
