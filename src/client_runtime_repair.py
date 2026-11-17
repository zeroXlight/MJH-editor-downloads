"""Fix the native workshop loader and TextAsset size metadata; no save edits."""
from pathlib import Path
from client_config import Assets
OLD='default = getmetatable(akItemdata[next(akItemdata)])'
NEW=OLD+' or {} -- MJH optional table defaults V2.0.35'
def patch_workshop(text):
 if NEW in text:return text
 if text.count(OLD)!=1:raise ValueError('游戏MOD表加载入口不兼容，未写入')
 return text.replace(OLD,NEW,1)
def repair(data,notes=None):
 from mod_compatibility import attempt
 notes=[] if notes is None else notes
 from role_window_runtime import patch_weapon,patch_hud
 from role_model_ids import repair as repair_models
 from role_battle_model import repair as repair_battle
 from team_head_runtime import repair as repair_heads
 from collection_ui_runtime import repair as repair_collection
 steps=[('MOD表默认值',lambda raw:Assets(raw).replace_script('TableDataManager.lua',patch_workshop(Assets(raw).script('TableDataManager.lua')))),
        ('武器初始化',lambda raw:Assets(raw).replace_script('WeaponUI.lua',patch_weapon(Assets(raw).script('WeaponUI.lua')))),
        ('对话界面显隐',lambda raw:Assets(raw).replace_script('Functions.lua',patch_hud(Assets(raw).script('Functions.lua')))),
        ('模型传输',repair_models),('战斗模型',repair_battle),('队伍头像',repair_heads),('武学收藏初始化',repair_collection)]
 for label,fn in steps:data=attempt(notes,label,lambda:fn(data),data)
 return Assets(data).normalize_text_lengths()

def plan(root):
 from role_editor import RoleLibrary
 root=Path(root).resolve();lib=RoleLibrary(root);payloads,originals=lib.plan()
 path=root/'DreamRivakes_Data/resources.assets';before=path.read_bytes()
 originals.setdefault(path,before);payloads[path]=repair(payloads.get(path,before),lib.compat_notes)
 save=root/'Save.sav'
 if save.exists():
  from role_wish_save import plan as plan_wishes
  from mod_compatibility import attempt
  extra,old,_=attempt(lib,'存档通用心愿补齐',lambda:plan_wishes(lib,save),({},{},[]));payloads.update(extra);originals.update(old)
 payloads[path]=repair(payloads.get(path,before),lib.compat_notes)
 return payloads,originals
def open_repair(host):
 from engine import ensure_closed,transaction
 from tkinter import messagebox
 if host.busy or not host.catalog:return
 if host.has_changes():host.error(ValueError('请先保存或撤销草稿，再修复导入后的界面'));return
 try:
  ensure_closed()
  root=host.catalog.root
  if Path(host.game_path.get()).resolve()!=root:raise ValueError('游戏目录已变化，请重新读取')
 except Exception as e:host.error(e);return
 def work():
  payloads,originals=plan(root);return transaction(root,payloads,originals,'修复人物模型编号、武器骨骼初始化、对话显隐及MOD表加载')
 def finish(backup):
  host.role_page.reset();host.martial_page.reset();host.reload()
  messagebox.showinfo('修复处理完成','已应用能匹配的修复。若有不兼容项目，已跳过并记录在“装备编辑器配置/兼容性提示.txt”。请重启游戏检查。'+('\n备份：'+str(backup) if backup else '\n当前已是修复状态。'),parent=host)
 host.martial_page.worker('正在备份并修复人物模型及导入后的界面…',work,finish)
