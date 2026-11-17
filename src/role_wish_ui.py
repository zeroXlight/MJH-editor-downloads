from pathlib import Path
from tkinter import filedialog,messagebox
from engine import ensure_closed,transaction
from role_wish_save import plan

def open_sync(page):
 if not page.available():return
 lib=page.library
 if page.dirty or lib.modified():page.host.error(ValueError('请先保存人物配置，再补齐存档中的心愿实例'));return
 path=filedialog.askopenfilename(title='选择要补齐通用心愿的存档',initialdir=str(lib.root),initialfile='Save.sav',filetypes=[('游戏存档','*.sav')],parent=page)
 if not path:return
 try:
  target=Path(path).resolve()
  if target not in {p.resolve() for _,p in page.host.catalog.saves()}:raise ValueError('请选择当前游戏目录中的存档')
  payloads,originals,records=plan(lib,target)
  if not records:
   from mod_compatibility import summary
   messagebox.showinfo('未新增心愿','所选存档未新增心愿；已有进度保持不变。'+summary(lib),parent=page);return
  details='\n'.join(lib.name(r['role'])+' → '+('海内存知己' if r['wish']==190 else '寻物探宝') for r in records)
  if not messagebox.askokcancel('补齐真实心愿实例',str(target)+'\n\n'+details+'\n\n修复旧版未完成心愿的任务绑定并补齐缺失项，保留已完成进度；备份后写入。',parent=page):return
  ensure_closed()
 except Exception as e:page.host.error(e);return
 def work():
  ensure_closed();return transaction(lib.root,payloads,originals,'补齐所选存档新增人物的通用心愿实例')
 def finish(backup):
  messagebox.showinfo('补齐完成','已写入所选存档的真实心愿实例。请重新读档；旧角色已补原生情缘初始化任务，不需要通过退队触发。\n备份：'+str(backup),parent=page)
 page.host.martial_page.worker('正在备份并补齐存档心愿实例…',work,finish)
