"""Searchable character templates and explicit in-memory character drafts."""
import copy, io
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from PIL import Image, ImageTk
from role_editor import RoleLibrary,SLOTS,RANKS,ATTR_LABELS
from role_locations import AUTO
from martial_ui import SearchCombo
from cursor_list import CursorList,Entry,PageBar
from engine import ensure_closed,transaction,clean
from edition import MOBILE_ENABLED

class RolePage(ttk.Frame):
    def __init__(self,parent,host):
        super().__init__(parent,padding=14);self.host=host;self.library=None;self.current=None;self.dirty=False;self.setting=False;self.portrait_source=None
        self.title_var=tk.StringVar();self.rank_var=tk.StringVar();self.battle_gifts=[];self.query=tk.StringVar();self.name_var=tk.StringVar();self.level=tk.StringVar();self.city_var=tk.StringVar();self.clan_var=tk.StringVar();self.location_var=tk.StringVar(value=AUTO);self.location_note=tk.StringVar();self.mute=tk.BooleanVar(value=True);self.empty_bag=tk.BooleanVar(value=True)
        self.summary=tk.StringVar(value='读取人物配置后，选择现有人物作为模板。');self.note=tk.StringVar(value='尚未选择人物')
        self.portrait_note=tk.StringVar();self.kungfu=[];self.equipment={};self.attrs={};self.cursor=CursorList(100)
        bar=ttk.Frame(self);bar.pack(fill='x',pady=(0,10))
        ttk.Button(bar,text='读取人物（缓存优先）',command=self.load).pack(side='left')
        ttk.Button(bar,text='以所选人物为模板新增',command=self.create).pack(side='left',padx=8)
        ttk.Button(bar,text='加入人物草稿',command=self.stage).pack(side='left')
        ttk.Button(bar,text='撤销人物草稿',command=self.discard).pack(side='left',padx=8)
        ttk.Button(bar,text='导出人物副本',command=lambda:self.save(True)).pack(side='right')
        ttk.Button(bar,text='保存人物修改',style='Primary.TButton',command=self.save).pack(side='right',padx=8)
        from object_ui import export_selected,import_selected
        from desktop_theme import ToolShelf
        self.tools=ToolShelf(self,'配置导入导出 / 缓存 / 存档同步与修复');self.tools.pack(fill='x')
        tools=self.tools.body
        objectbar=ttk.Frame(tools);objectbar.pack(fill='x',pady=(0,6))
        ttk.Button(objectbar,text='导出所选人物完整配置',command=lambda:export_selected(self.host,'Role',self)).pack(side='left')
        ttk.Button(objectbar,text='导入人物完整配置',command=lambda:import_selected(self.host,'Role')).pack(side='left',padx=8)
        from client_runtime_repair import open_repair
        ttk.Button(objectbar,text='修复导入后人物界面',command=lambda:open_repair(self.host)).pack(side='left',padx=8)
        self.cache_note=tk.StringVar(value='首次读取建立本地缓存；游戏或 MOD 有外部改动时，请手动刷新。')
        cachebar=ttk.Frame(tools);cachebar.pack(fill='x',pady=(0,6))
        from role_save_ui import open_sync
        ttk.Button(cachebar,text='补齐人物到指定存档',command=lambda:open_sync(self)).pack(side='right',padx=8)
        from role_wish_ui import open_sync as open_wish_sync
        ttk.Button(cachebar,text='补齐存档心愿实例',command=lambda:open_wish_sync(self)).pack(side='right',padx=8)
        ttk.Button(cachebar,text='刷新人物缓存',command=lambda:self.load(True)).pack(side='left')
        ttk.Label(cachebar,textvariable=self.cache_note,style='Sub.TLabel',wraplength=1100).pack(side='left',padx=10)
        ttk.Label(self,textvariable=self.summary,style='Sub.TLabel',wraplength=1200).pack(anchor='w',pady=(0,8))
        paned=ttk.Panedwindow(self,orient='horizontal');paned.pack(fill='both',expand=True)
        left=ttk.Frame(paned,style='Card.TFrame',padding=14);right=ttk.Frame(paned,style='Card.TFrame',padding=14);paned.add(left,weight=2);paned.add(right,weight=5)
        ttk.Label(left,text='人物列表',font=('Microsoft YaHei UI',13,'bold')).pack(anchor='w',pady=(0,12))
        search=ttk.Frame(left);search.pack(fill='x');ttk.Entry(search,textvariable=self.query).pack(side='left',fill='x',expand=True)
        ttk.Button(search,text='清空',width=5,command=lambda:self.query.set('')).pack(side='right')
        ttk.Label(left,text='搜索人物名字、原型 ID、城市（覆盖全库）',style='Sub.TLabel').pack(anchor='w',pady=7)
        self.list=host.make_tree(left,[('name','人物',180),('city','城市',90),('draft','草稿',45)],height=6)
        self.list.bind('<<TreeviewSelect>>',self.select);self.pages=PageBar(left,self.cursor,self.render_page);self.pages.pack(side='bottom',fill='x',pady=8,before=self.list.master)
        ttk.Label(right,textvariable=self.note,style='Title.TLabel').pack(anchor='w',pady=(0,8))
        notebook=ttk.Notebook(right);notebook.pack(fill='both',expand=True)
        basic=host.scroll_page(notebook,'名字 / 位置 / 立绘')
        for label,var in [('人物名字（允许同名，按编号区分）',self.name_var),('人物等级',self.level)]:
            row=ttk.Frame(basic);row.pack(fill='x',pady=6);ttk.Label(row,text=label,width=24).pack(side='left');ttk.Entry(row,textvariable=var).pack(side='left',fill='x',expand=True)
        from role_traits import ROLE_RANKS
        row=ttk.Frame(basic);row.pack(fill='x',pady=5);ttk.Label(row,text='称号（留空清除）',width=24).pack(side='left');ttk.Entry(row,textvariable=self.title_var).pack(side='left',fill='x',expand=True)
        ttk.Button(row,text='选择已有称号',command=self.choose_title).pack(side='left',padx=5)
        row=ttk.Frame(basic);row.pack(fill='x',pady=5);ttk.Label(row,text='人物品质',width=24).pack(side='left');ttk.Combobox(row,textvariable=self.rank_var,values=list(ROLE_RANKS.values()),state='readonly',width=15).pack(side='left')
        ttk.Label(basic,text='所属门派（名称 / ID 可搜索）').pack(anchor='w',pady=(8,3));self.clan_box=SearchCombo(basic,self.clan_var,[]);self.clan_box.pack(fill='x')
        ttk.Label(basic,text='所在城市').pack(anchor='w',pady=(8,3));self.city_box=SearchCombo(basic,self.city_var,[]);self.city_box.pack(fill='x')
        ttk.Label(basic,text='具体位置（完整路径；可搜索建筑名 / 地图 ID）').pack(anchor='w',pady=(8,3))
        self.location_box=SearchCombo(basic,self.location_var,[]);self.location_box.pack(fill='x')
        ttk.Label(basic,textvariable=self.location_note,wraplength=740,style='Sub.TLabel').pack(anchor='w',pady=(5,3))
        ttk.Checkbutton(basic,text='去掉人物与模型语音（默认）',variable=self.mute).pack(anchor='w',pady=(12,5))
        ttk.Checkbutton(basic,text='清空人物背包（默认；穿戴装备单独设置）',variable=self.empty_bag).pack(anchor='w',pady=5)
        ttk.Label(basic,text='模板新增人物自动带通用心愿：海内存知己、寻物探宝。旧人物在保存或修复时补齐；好感突破仍遵循游戏入队、99 好感等条件。',style='Sub.TLabel',wraplength=740).pack(anchor='w',pady=5)
        portrait=ttk.Frame(basic);portrait.pack(fill='x',pady=12)
        self.image_label=ttk.Label(portrait,text='模板立绘');self.image_label.pack(side='left',padx=(0,15))
        actions=ttk.Frame(portrait);actions.pack(side='left',fill='x',expand=True)
        ttk.Button(actions,text='三场景立绘预览 / 调整构图',command=self.preview_portrait).pack(anchor='w',pady=(0,8))
        ttk.Button(actions,text='上传立绘图片',command=self.import_portrait).pack(anchor='w')
        ttk.Button(actions,text='使用模板立绘',command=self.reset_portrait).pack(anchor='w',pady=8)
        modelbar=ttk.Frame(actions);modelbar.pack(anchor='w',pady=(0,8))
        ttk.Button(modelbar,text='模型动作绑定检查',command=self.check_model_animation).pack(side='left',padx=8)
        ttk.Button(modelbar,text='选择模型',command=self.choose_model).pack(side='left')
        if MOBILE_ENABLED:
            from mobile_models_ui import choose_model as choose_mobile,choose_portrait as choose_mobile_portrait
            ttk.Button(actions,text='选择手游模型与皮肤',command=lambda:choose_mobile(self)).pack(anchor='w',pady=6)
            ttk.Button(actions,text='选择手游人物立绘',command=lambda:choose_mobile_portrait(self)).pack(anchor='w',pady=6)
        ttk.Button(modelbar,text='使用模板模型',command=self.reset_model).pack(side='left',padx=8)
        from model_texture_ui import choose_template as choose_texture_template,import_file as import_model_texture
        ttk.Button(actions,text='1. 选择骨骼/贴图模板',command=lambda:choose_texture_template(self)).pack(anchor='w',pady=(0,8))
        self.texture_import_basic_button=ttk.Button(actions,text='2. 导入自定义贴图并绑定人物',command=lambda:import_model_texture(self),state='disabled')
        self.texture_import_basic_button.pack(anchor='w',pady=(0,8))
        ttk.Label(actions,textvariable=self.portrait_note,wraplength=480,style='Sub.TLabel').pack(anchor='w')
        ttk.Label(basic,text='模型默认沿用模板，也可选择已有模型。新增人物清除亲属、情缘线和专属心愿，只留海内存知己、寻物探宝。\n这里编辑人物初始配置；武学与装备在新周目或人物后续生成时生效。具体位置在新周目首次进入所选根场景时生效；已有周目不自动添加位置任务或搬迁人物。',wraplength=740,style='Sub.TLabel').pack(anchor='w',pady=10)
        if MOBILE_ENABLED:
            from mobile_models_ui import build as build_mobile
            build_mobile(self,notebook)
        from role_head_ui import build as build_head
        build_head(self,notebook)
        from model_texture_ui import build as build_model_texture
        build_model_texture(self,notebook)
        chatpage=host.scroll_page(notebook,'闲聊对话')
        ttk.Label(chatpage,text='按下“闲聊”后的独立人物台词；每行一段，按顺序播放。留空使用游戏原有闲聊。\n保留剧情选项；已出现的“闲聊”按钮使用这里的台词。保存后重启游戏生效。',wraplength=730,style='Sub.TLabel').pack(anchor='w',pady=10)
        self.chat_text=tk.Text(chatpage,height=16,wrap='word',undo=True,font=('Microsoft YaHei UI',12));self.chat_text.pack(fill='both',expand=True)
        self.chat_text.bind('<<Modified>>',self.chat_changed)
        ttk.Button(chatpage,text='恢复游戏原有闲聊',command=self.clear_chat).pack(anchor='w',pady=8)
        martial=host.scroll_page(notebook,'拥有的武学')
        row=ttk.Frame(martial);row.pack(fill='x',pady=5)
        for text,cmd in [('添加武学',self.add_kungfu),('修改等级',self.edit_kungfu),('移除所选',self.remove_kungfu)]:ttk.Button(row,text=text,command=cmd).pack(side='left',padx=(0,8))
        self.kungfu_tree=host.make_tree(martial,[('name','武学',300),('level','初始等级',100)],height=15)
        self.kungfu_tree.bind('<Double-1>',lambda _:self.edit_kungfu())
        gifts_page=host.scroll_page(notebook,'战斗天赋')
        ttk.Label(gifts_page,text='为人物添加、替换或移除现有战斗天赋；支持名称和描述搜索。其他类型天赋保留，天赋效果定义不被修改。',wraplength=730,style='Sub.TLabel').pack(anchor='w',pady=8)
        row=ttk.Frame(gifts_page);row.pack(fill='x')
        for text,cmd in [('添加战斗天赋',self.add_gift),('替换所选天赋',self.replace_gift),('移除所选天赋',self.remove_gift)]:ttk.Button(row,text=text,command=cmd).pack(side='left',padx=5)
        self.gift_tree=host.make_tree(gifts_page,[('name','天赋名称',200),('desc','效果描述',500)],height=15);self.gift_tree.bind('<Double-1>',lambda _:self.replace_gift())
        equip=host.scroll_page(notebook,'各部位装备')
        ttk.Label(equip,text='每个部位可选择具体装备、不佩戴或按品质随机。\n随机模式使用原生人物变体；人物生成时由游戏选择变体并自动穿戴。无候选的品质不能保存。',style='Sub.TLabel',wraplength=730).pack(anchor='w',pady=(0,12))
        for slot,(label,kinds) in SLOTS.items():
            box=ttk.LabelFrame(equip,text=label,padding=10);box.pack(fill='x',pady=5)
            mode=tk.StringVar(value='指定装备');rank=tk.StringVar(value='暗金');item=tk.StringVar(value='不佩戴');self.equipment[slot]=(mode,rank,item)
            row=ttk.Frame(box);row.pack(fill='x')
            modebox=ttk.Combobox(row,textvariable=mode,values=['指定装备','按品质随机'],state='readonly',width=14);modebox.pack(side='left')
            rankbox=ttk.Combobox(row,textvariable=rank,values=list(RANKS.values()),state='readonly',width=8);rankbox.pack(side='left',padx=8)
            ttk.Button(row,text='选择装备',command=lambda k=slot:self.choose_equipment(k)).pack(side='left')
            ttk.Button(row,text='不佩戴',command=lambda k=slot:self.clear_equipment(k)).pack(side='left',padx=8)
            ttk.Label(box,textvariable=item,wraplength=710,style='Sub.TLabel').pack(anchor='w',pady=(8,0))
            mode.trace_add('write',lambda *_,k=slot:self.slot_changed(k));rank.trace_add('write',lambda *_,k=slot:self.slot_changed(k))
        attributes=host.scroll_page(notebook,'自定义属性')
        ttk.Label(attributes,text='属性复制为人物独立配置，不影响模板。数值按游戏原值输入：百分率 10000 = 100%。\n这些是初始属性；游戏中的等级换算、武学与装备加成仍按原规则计算。',style='Sub.TLabel',wraplength=730).pack(anchor='w',pady=(0,12))
        grid=ttk.Frame(attributes);grid.pack(fill='x')
        for index,(key,label) in enumerate(ATTR_LABELS.items()):
            var=tk.StringVar(value='0');self.attrs[key]=var
            row,col=divmod(index,2);ttk.Label(grid,text=label,width=16).grid(row=row,column=col*2,sticky='w',padx=5,pady=4)
            ttk.Entry(grid,textvariable=var,width=16).grid(row=row,column=col*2+1,sticky='ew',padx=(0,16),pady=4);var.trace_add('write',self.mark_dirty)
        grid.columnconfigure(1,weight=1);grid.columnconfigure(3,weight=1)
        self.query.trace_add('write',lambda *_:self.refresh_list())
        for var in (self.title_var,self.rank_var,self.name_var,self.level,self.city_var,self.clan_var,self.mute,self.empty_bag):var.trace_add('write',self.mark_dirty)
        self.city_var.trace_add('write',self.city_changed);self.location_var.trace_add('write',self.location_changed)
    def city_changed(self,*_):
        if not self.library:return
        if not self.setting:self.position_changed=True
        city=self.city_choices.get(self.city_var.get());self.location_choices=self.library.places.by_city.get(city,{AUTO:()})
        self.location_box.set_values(list(self.location_choices))
        self.location_var.set(AUTO)
    def location_changed(self,*_):
        if not self.setting:self.position_changed=True
        self.mark_dirty()
        if not self.library:return
        city=self.city_choices.get(self.city_var.get());path=getattr(self,'location_choices',{}).get(self.location_var.get(),())
        self.location_note.set(self.library.places.note(city,path) if city in self.library.tables['City'] else '请先选择城市。')
    def mark_dirty(self,*_):
        if not self.setting and self.current is not None:self.dirty=True
    def slot_changed(self,slot):
        self.mark_dirty()
        if not self.library or self.current is None:return
        mode,rank,item=self.equipment[slot]
        if mode.get()=='按品质随机':
            grade=next((i for i,label in RANKS.items() if label==rank.get()),7)
            count=len(self.library.candidates(slot,grade));item.set(f'人物生成时自动佩戴 {rank.get()} 品质装备 · {count} 个可选型号')
        elif hasattr(self,'item_ids'):
            item.set(clean(self.library.tables['Item'].get(self.item_ids.get(slot,0),{}).get('ItemName','')) or '不佩戴')
    def has_changes(self):return self.dirty or bool(self.library and self.library.modified())
    def reset(self):
        self.library=None;self.current=None;self.dirty=False;self.portrait_source=None;self.cursor.update([]);self.cursor.filter();self.render_page();self.summary.set('目录已更新，请读取人物配置');self.note.set('尚未选择人物')
    def available(self):
        if self.host.busy:return False
        if not self.library or self.current is None:self.host.error(ValueError('请先读取并选择人物'));return False
        if Path(self.host.game_path.get()).resolve()!=self.library.root:self.host.error(ValueError('目录已变化，请重新读取'));return False
        return True
    def load(self,force_refresh=False):
        if self.host.busy:return
        if self.has_changes() and not messagebox.askyesno('未保存的人物草稿','重新读取会丢弃人物草稿，继续？',parent=self):return
        if not self.host.catalog or Path(self.host.game_path.get()).resolve()!=self.host.catalog.root:self.host.error(ValueError('请先读取正确的游戏目录'));return
        def finish(lib):
            self.library=lib;self.current=None;self.dirty=False;self.city_choices={lib.text(r.get('NameID'))+f' · {i}':i for i,r in lib.tables['City'].items()}
            self.clan_choices={name+f' · {i}':i for i,name in lib.clans.items()};self.clan_box.set_values(list(self.clan_choices))
            self.city_box.set_values(list(self.city_choices));self.refresh_list();self.summary.set(f'已读取 {len(lib.roles)} 个人物原型；多个生成变体合并显示。编辑后加入草稿，再保存。')
            from library_cache import note
            self.cache_note.set(note(lib))
            self.host.status.set('人物配置读取完成；'+note(lib))
            from model_texture import binding_runtime_pending
            from recruitment_runtime import pending
            from role_animation import pending as animation_pending
            from mobile_models import runtime_pending
            if runtime_pending(lib):
                self.summary.set(self.summary.get()+' 手游模型加载修复待保存。')
                self.host.status.set('已保存的手游模型需要更新加载和贴图绑定；退出游戏后保存人物修改即可修复。')
            if animation_pending(lib):
                self.summary.set(self.summary.get()+' 模型动作绑定补齐待保存。')
                self.host.status.set('存在缺失的模型动作绑定；退出游戏后保存人物修改，可从对应骨骼补齐。')
            if pending(lib):
                self.summary.set(self.summary.get()+' 已保存人物的入队同步修复待保存。')
                self.host.status.set('退出游戏后点击“保存人物修改”安装入队同步，再重启游戏邀请人物。')
            if binding_runtime_pending(lib):
                self.summary.set(self.summary.get()+' 自定义贴图的旧档外观同步修复待保存。')
                self.host.status.set('已有贴图绑定需要更新旧档外观同步；退出游戏后点击“保存人物修改”，再重新进入游戏。')
        from library_cache import load_library
        self.host.martial_page.worker('正在刷新人物缓存…' if force_refresh else '正在读取人物本地缓存（首次读取会建立缓存）…',
                                     lambda:load_library(self.host.catalog.root,'role',force_refresh),finish)
    def refresh_list(self):
        if not self.library or self.host.busy:return
        l=self.library;entries=[]
        for rid in l.roles:
            name=l.name(rid);city=l.text(l.tables['City'].get(l.city(rid),{}).get('NameID',0));draft=any(i in l.changes['Role'] for i in l.roles[rid])
            entries.append(Entry(rid,(f'{name} · {rid}',city,'●' if draft else ''),f'{name} {rid} {city}'))
        self.cursor.update(entries);self.cursor.filter(self.query.get());self.render_page()
    def render_page(self):
        selected=str(self.current) if self.current is not None else None;self.list.delete(*self.list.get_children())
        for entry in self.cursor.page():self.list.insert('','end',iid=str(entry.key),values=entry.value)
        if selected and self.list.exists(selected):self.list.selection_set(selected);self.list.see(selected)
        self.pages.sync()
    def select(self,event=None):
        if self.host.busy or not self.library or not self.list.selection():return
        rid=int(self.list.selection()[0])
        if rid==self.current:return
        if self.dirty:
            if not messagebox.askyesno('人物设置未加入草稿','先将当前人物设置加入草稿，再切换人物？',parent=self):
                self.cursor.seek(self.current);self.render_page();return
            if not self.stage():self.cursor.seek(self.current);self.render_page();return
        self.current=rid;self.render()
    def render(self):
        if not self.library or self.current is None:return
        s=self.library.options(self.current);self.settings=copy.deepcopy(s);self.setting=True
        self.texture_template_confirmed=bool(s.get('texture_binding'))
        try:
            self.chat_text.delete('1.0','end');self.chat_text.insert('1.0',s.get('chat',''));self.chat_text.edit_modified(False)
            from role_traits import ROLE_RANKS
            self.title_var.set(s.get('title',''));self.rank_var.set(ROLE_RANKS.get(s.get('rank',4),'紫'));self.battle_gifts=list(s.get('battle_gifts',[]));self.render_gifts()
            self.name_var.set(s['name']);self.level.set(str(s['level']));self.city_var.set(next((label for label,i in self.city_choices.items() if i==s['city']),''))
            self.clan_var.set(next((label for label,i in self.clan_choices.items() if i==s['clan']),''))
            self.location_var.set(next((label for label,path in self.location_choices.items() if tuple(s.get('location_path',[]))==path),AUTO))
            self.mute.set(s['mute']);self.empty_bag.set(s['empty_bag']);self.kungfu=copy.deepcopy(s['kungfu']);self.item_ids={}
            for slot,(mode,rank,item) in self.equipment.items():
                spec=s['equipment'][slot];mode.set('按品质随机' if spec['mode']=='random' else '指定装备');rank.set(RANKS.get(spec.get('rank',7),'暗金'))
                ident=spec.get('id',0);self.item_ids[slot]=ident;self.slot_changed(slot)
            for key,var in self.attrs.items():var.set(str(s['attrs'].get(key,0)))
            from role_head_ui import load as load_head
            load_head(self)
            self.portrait_source=None;self.render_portrait();self.render_kungfu();self.note.set(self.library.name(self.current)+f' · 原型 {self.current}')
            from model_texture_ui import load as load_model_texture
            load_model_texture(self)
            if MOBILE_ENABLED:
                from mobile_models_ui import refresh as refresh_mobile
                refresh_mobile(self)
        finally:self.setting=False;self.dirty=False;self.position_changed=False
    def collect(self):
        if self.clan_var.get() not in self.clan_choices:raise ValueError('请选择有效的所属门派')
        s=copy.deepcopy(self.settings);s.update(name=self.name_var.get(),level=int(self.level.get()),
                kungfu=list(self.kungfu),mute=self.mute.get(),empty_bag=self.empty_bag.get(),attrs={k:int(v.get()) for k,v in self.attrs.items()})
        s['preserve_location']=not getattr(self,'position_changed',False)
        if not s['preserve_location']:
            s['city']=self.city_choices.get(self.city_var.get(),s.get('city',0))
            s['location_path']=list(self.location_choices.get(self.location_var.get(),s.get('location_path',[])))
        from role_traits import ROLE_RANKS
        s['rank']={v:k for k,v in ROLE_RANKS.items()}[self.rank_var.get()];s['title']=self.title_var.get();s['battle_gifts']=list(self.battle_gifts)
        s['head_layout']={k:v.get() for k,v in self.head_vars.items()}
        s['chat']=self.chat_text.get('1.0','end-1c')
        s['clan']=self.clan_choices[self.clan_var.get()]
        ranks={v:k for k,v in RANKS.items()};s['equipment']={k:({'mode':'random','rank':ranks[rank.get()]} if mode.get()=='按品质随机' else {'mode':'item','id':self.item_ids[k]}) for k,(mode,rank,item) in self.equipment.items()}
        return s
    def stage(self):
        if not self.available():return False
        try:
            with self.library.edit():self.library.update(self.current,self.collect(),self.portrait_source,head_source=self.head_source,texture_source=self.texture_payload)
            self.render();self.refresh_list();self.host.status.set(f'人物修改已加入草稿；{len(self.library.logs())} 条待保存人物日志。');return True
        except Exception as error:self.host.error(error);return False
    def create(self):
        if not self.available():return
        if self.dirty and not self.stage():return
        name=simpledialog.askstring('新增人物','新人物名字：',parent=self)
        if name is None:return
        try:
            s=self.library.options(self.current);s['name']=name;s['mute']=True;s['empty_bag']=True
            if s['city'] not in self.library.tables['City']:
                s['city']=self.city_choices.get(self.city_var.get(),next(iter(self.library.tables['City'])));s['location_path']=[]
            with self.library.edit():rid=self.library.create(self.current,s)
            self.current=rid;self.query.set('');self.refresh_list();self.cursor.seek(rid);self.render_page();self.render()
            self.host.status.set('新人物已加入草稿；请编辑武学、装备、城市、立绘和属性后保存。')
        except Exception as error:self.host.error(error)
    def discard(self):
        if self.host.busy:return
        if self.has_changes() and not messagebox.askyesno('撤销人物草稿','撤销本页全部未保存人物修改？',parent=self):return
        self.reset();self.load()
    def picker(self,title,choices,initial=0,fields=()):
        from app import Picker
        d=Picker(self,title,choices,{'id':initial},fields)
        return d.result[0] if d.result else None
    def add_kungfu(self):
        if not self.available():return
        l=self.library;choices=[(i,l.text(r.get('NameID'))+f' · {i}') for i,r in l.tables['Martial'].items() if i not in getattr(l,'retired_martials',set())]
        result=self.picker('选择人物拥有的武学',choices,fields=[('level','初始等级',1)])
        if not result:return
        mid=result['id'];level=result['level']
        if any(i==mid for i,v in self.kungfu):self.host.error(ValueError('人物已经拥有此武学'));return
        if not 1<=level<2147483648:self.host.error(ValueError('武学等级须为正整数（不超过存储范围 2147483647）'));return
        self.kungfu.append((mid,level));self.dirty=True;self.render_kungfu()
    def choose_title(self):
        if not self.available():return
        from role_traits import title_name
        result=self.picker('选择已有称号',[(0,'无称号')]+[(i,title_name(self.library,i)+f' · {i}') for i in self.library.tables['RoleTitle']])
        if result is not None:self.title_var.set(title_name(self.library,result['id']));self.dirty=True
    def gift_picker(self):
        from role_traits import battle_choices
        win=tk.Toplevel(self);win.title('搜索战斗天赋 · 名称 / 描述 / ID');win.geometry('1000x660');win.transient(self.winfo_toplevel())
        query=tk.StringVar();ttk.Entry(win,textvariable=query).pack(fill='x',padx=12,pady=10)
        ttk.Label(win,text='多个关键词以空格分隔；同时搜索名称与效果描述。').pack(anchor='w',padx=12)
        tree=self.host.make_tree(win,[('name','天赋名称',210),('id','ID',90),('desc','效果描述',620)],height=16)
        detail=tk.Text(win,height=5,wrap='word',font=('Microsoft YaHei UI',10));detail.pack(fill='x',padx=12,pady=8)
        result=[];rows={}
        def refresh(*_):
            tree.delete(*tree.get_children());rows.clear()
            for ident,name,desc in battle_choices(self.library,query.get()):rows[ident]=(name,desc);tree.insert('','end',iid=str(ident),values=(name,ident,desc))
        def selected(*_):
            if not tree.selection():return
            ident=int(tree.selection()[0]);name,desc=rows[ident];detail.configure(state='normal');detail.delete('1.0','end');detail.insert('1.0',name+f' · {ident}\n'+desc);detail.configure(state='disabled')
        def accept(*_):
            if tree.selection():result.append(int(tree.selection()[0]));win.destroy()
        tree.bind('<<TreeviewSelect>>',selected);tree.bind('<Double-1>',accept);query.trace_add('write',refresh)
        ttk.Button(win,text='使用所选战斗天赋',command=accept).pack(pady=8);refresh();win.grab_set();self.wait_window(win)
        return result[0] if result else None
    def render_gifts(self):
        self.gift_tree.delete(*self.gift_tree.get_children())
        for index,ident in enumerate(self.battle_gifts):
            row=self.library.tables['Gift'].get(ident,{})
            self.gift_tree.insert('','end',iid=str(index),values=(clean(self.library.text(row.get('NameID',0)))+f' · {ident}',clean(self.library.text(row.get('DescID',0)))))
    def add_gift(self):
        if not self.available():return
        ident=self.gift_picker()
        if ident is None:return
        if ident in self.battle_gifts:self.host.error(ValueError('人物已拥有该战斗天赋'));return
        self.battle_gifts.append(ident);self.dirty=True;self.render_gifts()
    def replace_gift(self):
        if not self.available() or not self.gift_tree.selection():return
        index=int(self.gift_tree.selection()[0]);ident=self.gift_picker()
        if ident is None:return
        if ident in self.battle_gifts and self.battle_gifts[index]!=ident:self.host.error(ValueError('人物已拥有该战斗天赋'));return
        self.battle_gifts[index]=ident;self.dirty=True;self.render_gifts()
    def remove_gift(self):
        if not self.available() or not self.gift_tree.selection():return
        self.battle_gifts.pop(int(self.gift_tree.selection()[0]));self.dirty=True;self.render_gifts()
    def render_kungfu(self):
        self.kungfu_tree.delete(*self.kungfu_tree.get_children())
        for index,(mid,level) in enumerate(self.kungfu):self.kungfu_tree.insert('','end',iid=str(index),values=(self.library.text(self.library.tables['Martial'][mid].get('NameID'))+f' · {mid}',level))
    def edit_kungfu(self):
        if not self.available() or not self.kungfu_tree.selection():return
        index=int(self.kungfu_tree.selection()[0]);mid,level=self.kungfu[index]
        value=simpledialog.askinteger('武学初始等级','输入初始等级',initialvalue=level,minvalue=1,maxvalue=2147483647,parent=self)
        if value is not None:self.kungfu[index]=(mid,value);self.dirty=True;self.render_kungfu()
    def remove_kungfu(self):
        if not self.available() or not self.kungfu_tree.selection():return
        self.kungfu.pop(int(self.kungfu_tree.selection()[0]));self.dirty=True;self.render_kungfu()
    def choose_equipment(self,slot):
        if not self.available():return
        choices=[(0,'不佩戴')]+[(i,clean(r.get('ItemName'))+' · '+RANKS.get(r.get('Rank'),'未知品质')+f' · {i}') for i,r in self.library.tables['Item'].items() if r.get('ItemType') in SLOTS[slot][1]]
        result=self.picker('选择'+SLOTS[slot][0],choices,self.item_ids[slot])
        if result is None:return
        ident=result['id'];mode,rank,item=self.equipment[slot];mode.set('指定装备');self.item_ids[slot]=ident;item.set(clean(self.library.tables['Item'].get(ident,{}).get('ItemName','')) or '不佩戴');self.dirty=True
    def clear_equipment(self,slot):
        if not self.available():return
        self.item_ids[slot]=0;mode,rank,item=self.equipment[slot];mode.set('指定装备');item.set('不佩戴');self.dirty=True
    def chat_changed(self,event=None):
        if self.chat_text.edit_modified():
            self.mark_dirty();self.chat_text.edit_modified(False)
    def clear_chat(self):
        if not self.available():return
        self.chat_text.delete('1.0','end');self.dirty=True
    def portrait_image(self):
        from role_editor import prepare_portrait, PORTRAIT_DIR
        if self.portrait_source:
            _,_,raw=prepare_portrait(self.portrait_source,self.current,self.settings.get('portrait_layout',{}))
            return Image.open(io.BytesIO(raw)).convert('RGBA')
        portrait=self.settings.get('portrait','')
        if portrait.startswith('#role_editor/'):
            filename=portrait.removeprefix('#role_editor/')
            if Path(filename).name!=filename:raise ValueError('立绘路径无效')
            path=self.library.root/PORTRAIT_DIR/filename
            raw=self.library.files.get(path)
            with Image.open(io.BytesIO(raw) if raw else path) as im:return im.convert('RGBA')
        raise ValueError('请选择上传的立绘图片后预览。模板内置立绘暂不提供资源读取。')
    def preview_portrait(self):
        if not self.available():return
        try:self.portrait_image()
        except Exception as error:messagebox.showinfo('立绘预览',str(error),parent=self);return
        from role_portrait import preview
        win=tk.Toplevel(self);win.title('普通对话 / 属性面板 / 互动转盘 · 游戏立绘预览');win.geometry('1040x780');win.minsize(720,580)
        ttk.Label(win,text='按游戏 1280×720 布局预览：保留透明留白、镜像和属性面板遮挡；背景与属性文字为模拟。',wraplength=990).pack(anchor='w',padx=12,pady=8)
        mode=tk.StringVar(value='普通对话');bar=ttk.Frame(win);bar.pack(fill='x',padx=12)
        imagebox=ttk.Label(win);imagebox.pack(fill='both',expand=True,padx=12,pady=8)
        pending=[None]
        def redraw():
            pending[0]=None
            try:
                width,height=win.winfo_width(),win.winfo_height()
                if width<=1 or height<=1:width,height=1040,780
                w=int(max(400,min(1000,width-30,(height-325)*16/9))); im=preview(self.portrait_image(),{'普通对话':'dialogue','人物属性面板':'observe','互动转盘':'roll'}[mode.get()],self.name_var.get(),self.chat_text.get('1.0','end-1c'),(w,round(w*9/16)))
                imagebox._image=ImageTk.PhotoImage(im,master=win);imagebox.configure(image=imagebox._image)
            except Exception as error:imagebox.configure(image='',text=str(error))
        def schedule(*_):
            if pending[0] is not None:win.after_cancel(pending[0])
            pending[0]=win.after(100,redraw)
        for label in ['普通对话','人物属性面板','互动转盘']:ttk.Radiobutton(bar,text=label,variable=mode,value=label,command=schedule).pack(side='left',padx=8)
        controls=ttk.Frame(win);controls.pack(fill='x',padx=12)
        if self.portrait_source:
            values={};readouts={}
            for key,label,lo,hi in [('zoom','缩放',0.1,3),('x','横向偏移',-1024,1024),('y','纵向偏移',-1024,1024)]:
                row=ttk.Frame(controls);row.pack(fill='x');ttk.Label(row,text=label,width=12).pack(side='left')
                var=tk.DoubleVar(value=self.settings.get('portrait_layout',{}).get(key,1 if key=='zoom' else 0));values[key]=var
                readout=tk.StringVar(value=f'{var.get():.2f}');readouts[key]=readout;ttk.Label(row,textvariable=readout,width=9).pack(side='right')
                def changed(value,k=key,label=readout):
                    self.settings.setdefault('portrait_layout',{})[k]=float(value);label.set(f'{float(value):.2f}');self.dirty=True;schedule()
                ttk.Scale(row,from_=lo,to=hi,variable=var,command=changed).pack(side='left',fill='x',expand=True)
            flip=tk.BooleanVar(value=self.settings.get('portrait_layout',{}).get('flip',False))
            def flipped():self.settings.setdefault('portrait_layout',{})['flip']=flip.get();self.dirty=True;schedule()
            ttk.Checkbutton(controls,text='上传图水平翻转（游戏本身会镜像，预览已计入）',variable=flip,command=flipped).pack(anchor='w')
            def reset_layout():
                for k,var in values.items():
                    var.set(1 if k=='zoom' else 0);readouts[k].set(f'{var.get():.2f}')
                flip.set(False);self.settings['portrait_layout']={'zoom':1,'x':0,'y':0,'flip':False};self.dirty=True;schedule()
            ttk.Button(controls,text='恢复原图构图',command=reset_layout).pack(anchor='e')
            ttk.Label(controls,text='构图按原图保留细节，画布 2048～4096 像素；调整后加入人物草稿并保存。').pack(anchor='w')
        else:ttk.Label(controls,text='已保存图片预览；如需重新调整构图，请重新上传原图。').pack(anchor='w')
        def close():
            if pending[0] is not None:win.after_cancel(pending[0])
            self.render_portrait();win.destroy()
        ttk.Button(win,text='完成',command=close).pack(pady=8);win.protocol('WM_DELETE_WINDOW',close)
        win.bind('<Configure>',lambda event:schedule() if event.widget==win else None);win.transient(self.winfo_toplevel());win.grab_set();schedule()
    def import_portrait(self):
        if not self.available():return
        path=filedialog.askopenfilename(title='选择立绘图片',filetypes=[('图片','*.png *.jpg *.jpeg *.webp *.bmp'),('所有文件','*.*')],parent=self)
        if not path:return
        try:
            from role_editor import prepare_portrait
            prepare_portrait(path,self.current);self.portrait_source=path;self.settings['portrait_layout']={'zoom':1,'x':0,'y':0,'flip':False};self.dirty=True;self.render_portrait();self.preview_portrait()
        except Exception as error:self.host.error(error)
    def reset_portrait(self):
        if not self.available():return
        self.portrait_source=None
        rec=self.library.meta.get(str(self.current),{});self.settings['portrait']=rec.get('before',{}).get('立绘',self.library.options(self.current)['portrait'])
        self.dirty=True;self.render_portrait()
    def render_portrait(self):
        self._image=None;self.image_label.configure(image='',text='模板立绘')
        portrait=self.settings.get('portrait','');path=Path(self.portrait_source) if self.portrait_source else None
        raw=None
        if path is None and portrait.startswith('#role_editor/'):
            filename=portrait.removeprefix('#role_editor/')
            if Path(filename).name!=filename:raise ValueError('立绘路径无效')
            path=self.library.root/'ModProject/GameProject/Mod_MJH/Source/Other/role_editor'/filename;raw=self.library.files.get(path)
        if path and (raw or path.exists()):
            with Image.open(io.BytesIO(raw) if raw else path) as im:
                im=im.convert('RGBA')
                if self.portrait_source:
                    from role_portrait import compose
                    im=compose(im,self.settings.get('portrait_layout',{}))
                im.thumbnail((150,200));self._image=ImageTk.PhotoImage(im,master=self)
            self.image_label.configure(image=self._image,text='')
        art=self.library.tables['RoleModel'].get(self.settings.get('model_source'),{})
        model_note=art.get('Model','')
        if self.settings.get('mobile_binding'):
            spec=self.settings['mobile_binding'];model_note='手游 '+spec['id']+' / '+spec['texture']
        self.portrait_note.set(('已选择：'+str(path) if path else portrait)+'\n模型：'+model_note)
    def check_model_animation(self):
        if not self.available():return
        if self.settings.get('mobile_binding'):
            from mobile_models import runtime
            try:
                data=runtime(self.settings['mobile_binding'])
                messagebox.showinfo('手游模型动作绑定','\n'.join(a['Name']+' · '+str(a['Milliseconds'])+' ms · '+str(len(a.get('Events',[])))+' 事件' for a in data['animations']),parent=self)
            except Exception as error:self.host.error(error)
            return
        from role_animation import animation_rows,resolved_timings,model_bindings
        try:
            source=self.settings['model_source']
            text=self.library.assets.script('SpineAnimaitionTime.lua')
            bindings=model_bindings(self.library)
            bindings[source]=bindings.get(source,source)
            rows=animation_rows(resolved_timings(self.library,text,bindings))
            if source not in rows:raise ValueError('该模型缺少动作时间与事件数据；保存会拒绝无效绑定。')
            body=rows[source][2]
            import re
            names=re.findall(r'\["([^"\n]+)"\]\s*=\s*\{',body)
            messagebox.showinfo('模型动作绑定',f'模型配置编号：{source}\n资源编号：{self.library.tables["RoleModel"][source].get("ModelID",0)}\n动作及事件键：'+', '.join(dict.fromkeys(names))+'\n\n保存时复制完整动作时长及命中／切换等事件帧到独立模型编号。此处校验动作表，未运行骨骼动画。',parent=self)
        except Exception as error:self.host.error(error)
    def choose_model(self):
        if not self.available():return
        owners={self.library.row(rid).get('ArtID'):self.library.name(rid) for rid in self.library.roles}
        choices=[(i,owners.get(i,'模型')+' · '+r.get('Model','')+f' · {i}') for i,r in self.library.tables['RoleModel'].items() if r.get('Model') and not r.get('Model','').startswith('mjh_mobile_')]
        result=self.picker('选择人物模型',choices,self.settings.get('model_source',0))
        if result:
            self.settings['model_source']=result['id'];self.settings.pop('texture_binding',None);self.settings.pop('mobile_binding',None);self.dirty=True;self.render_portrait()
            self.texture_template_confirmed=True
            from model_texture_ui import load as load_model_texture
            load_model_texture(self)
    def reset_model(self):
        if not self.available():return
        source=self.library.meta.get(str(self.current),{}).get('base_art',self.library.row(self.current)['ArtID'])
        if self.library.tables['RoleModel'].get(source,{}).get('Model','').startswith('mjh_mobile_'):
            self.host.error(ValueError('此人物模板本身为手游模型，请通过“选择手游模型与皮肤”重选模板，或通过“选择模型”切换原版。'));return
        self.settings['model_source']=source
        self.settings.pop('texture_binding',None);self.settings.pop('mobile_binding',None)
        self.texture_template_confirmed=True
        from model_texture_ui import load as load_model_texture
        load_model_texture(self)
        self.dirty=True;self.render_portrait()
    def save(self,export=False):
        if not self.available():return
        if self.dirty and not self.stage():return
        l=self.library
        if not l.modified():self.host.error(ValueError('没有待保存人物草稿'));return
        if self.host.drafts or self.host.effects or self.host.martial_page.has_changes():self.host.error(ValueError('请先保存或撤销装备、武学草稿，再保存人物配置'));return
        try:
            if not export:ensure_closed()
        except Exception as error:self.host.error(error);return
        folder=None
        if export:
            value=filedialog.askdirectory(title='选择游戏目录之外的导出目录',parent=self)
            if not value:return
            folder=Path(value).resolve()
            if folder.is_relative_to(l.root):self.host.error(ValueError('请选择游戏目录之外的导出目录'));return
        def work():
            payloads,originals=l.plan()
            if export:
                from model_texture import texture_dependencies
                payloads.update(texture_dependencies(l.root,payloads))
                from mobile_models import dependencies
                payloads.update(dependencies(l.root,payloads))
                from datetime import datetime
                target=folder/('人物配置副本_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'));target.mkdir()
                for path,data in payloads.items():
                    dest=target/path.relative_to(l.root);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
                from change_log import line
                (target/'人物改动日志.txt').write_text('\n'.join(line(r) for r in l.logs()),encoding='utf8')
                return target
            ensure_closed();return transaction(l.root,payloads,originals,'新增/修改人物')
        def finish(target):
            from mod_compatibility import summary
            compat=summary(l)
            if export:self.host.status.set('人物配置副本已导出（包含自定义模型贴图）：'+str(target));messagebox.showinfo('导出完成','已导出人物配置及其引用的自定义模型 PNG。\n'+str(target),parent=self);return
            self.reset();self.host.martial_page.reset();self.host.reload();self.host.refresh_caps()
            self.host.status.set('人物配置已保存并记录日志。备份：'+str(target))
            messagebox.showinfo('人物保存完成','人物配置与立绘已保存，日志已按批次记录。\n重启游戏，新周目或人物后续生成时使用初始配置。具体位置在新周目首次进入所选根场景时生效；已有周目不自动添加位置任务或搬迁人物。\n\n备份：'+str(target)+compat,parent=self)
        self.host.martial_page.worker('正在校验、'+('导出' if export else '备份并保存')+'人物配置…',work,finish)
