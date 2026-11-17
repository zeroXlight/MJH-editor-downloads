"""Move editor-authored martial IDs into native AI's unsigned 16-bit domain."""
import copy,json
from pathlib import Path
from feature_save import NativeSave,u32,put

def remap_save(raw,mapping):
    save=NativeSave(raw)
    for table,offset in ((2,24),(25,32),(46,24)):
        save.indexed(table)
        for row in save.tables[table]:
            if table==2 and u32(row,28)!=6:continue
            old=u32(row,offset)
            if old in mapping:put(row,offset,mapping[old])
    return save.bytes()

def remap_row(table,row,mapping,enums):
    from object_bundle import references
    out=copy.deepcopy(row)
    for path,target,old in references(table,row,enums):
        if target!='Martial' or old not in mapping:continue
        obj=out
        for part in path[:-1]:obj=obj[part]
        obj[path[-1]]=str(mapping[old]) if isinstance(obj[path[-1]],str) else mapping[old]
    return out

def plan(root):
    from martial_editor import MartialLibrary
    from caps import baseline
    from object_bundle import constant_links
    lib=MartialLibrary(root);native={int(i) for i in baseline()['proto']['Martial']}
    # Require editor provenance; external mods may provide their own widened AI.
    provenance=set(lib.origins['Martial'])
    own=lib.own_jsons['Martial']
    if own.exists():provenance.update(r['BaseID'] for r in json.loads(own.read_text(encoding='utf-8-sig')).get('Items',[]) if isinstance(r,dict) and type(r.get('BaseID')) is int)
    history_path=lib.root/'装备编辑器配置/武学安全编号迁移.json'
    history_raw=history_path.read_bytes() if history_path.exists() else None
    history=json.loads(history_raw.decode('utf8')) if history_raw else {}
    candidates=sorted(i for i in provenance if i>65535 and i not in native and i in lib.tables['Martial'] and str(i) not in history)
    mapping={};used=set(lib.tables['Martial']);notes=[]
    for old in candidates:
        if old in lib.overrides['Martial']:
            notes.append(f'武学 {old} 有多个活动来源，已跳过编号迁移');continue
        new=next((i for i in range(20000,30000) if i not in used),None)
        if new is None:raise ValueError('原生 AI 安全编号不足，未准备写入')
        used.add(new);mapping[old]=new
    if not mapping:return {},dict(lib.originals),mapping,notes
    lib.retired_martials=set(map(int,history))|set(mapping)
    for old,new in mapping.items():
        row=copy.deepcopy(lib.tables['Martial'][old]);row['BaseID']=new
        lib.sources['Martial'][new]=old;lib.origins['Martial'][new]=lib.native_source(old)
        lib.set('Martial',new,row)
        # Retain a hidden compatibility record rather than deleting unknown
        # external references. No character/collection references stay here.
        lib.set('Martial',old,{'Display':0})
        if str(old) in lib.icons:lib.icons[str(new)]=copy.deepcopy(lib.icons[str(old)])
    for table,rows in lib.tables.items():
        if table=='Language':continue
        for ident,row in list(rows.items()):
            updated=remap_row(table,row,mapping,lib.enums)
            if updated!=row:
                if ident in lib.overrides[table]:raise ValueError(f'{table}:{ident} 的引用来源不唯一，不能安全迁移')
                lib.set(table,ident,updated)
    # Constant-expression indirection must follow the same remap as exports.
    for row in list(lib.tables['SkillEffect'].values()):
        for child,target,old in constant_links(row,lambda i:lib.tables['SkillEffect'].get(i,{})):
            if target=='Martial' and old in mapping:lib.set('SkillEffect',child,{'EventArg1':[mapping[old],0]})
    payloads,originals=lib.plan(preserve_imported=True)
    dll=lib.root/'DreamRivakes_Data/Plugins/RaceLogic_Release_x64.dll'
    if dll.exists():
        from martial_id_runtime import remap
        before=dll.read_bytes();after=remap(payloads.get(dll,before),mapping,notes)
        if after!=before:originals.setdefault(dll,before);payloads[dll]=after
    from client_config import Assets
    from martial_ranges import patch_client
    asset=Assets(payloads.get(lib.assets_path,lib.originals[lib.assets_path]))
    payloads[lib.assets_path]=asset.replace_script('Unit.lua',patch_client(asset.script('Unit.lua'),lib))
    notes.extend(n for n in lib.compat_notes if '自定义范围运行库同步已跳过' not in n)
    originals[history_path]=history_raw
    history.update({str(old):new for old,new in mapping.items()})
    payloads[history_path]=json.dumps(history,ensure_ascii=False,indent=2).encode('utf8')
    receipt=lib.root/'装备编辑器配置/外部MOD安装兼容.json'
    if receipt.is_file():
        before=receipt.read_bytes();obj=json.loads(before.decode('utf8'))
        for area in obj.get('options',{}).get('areas',[]):
            for field in ('source','target'):area[field]=mapping.get(area.get(field),area.get(field))
        originals[receipt]=before;payloads[receipt]=json.dumps(obj,ensure_ascii=False,indent=2).encode('utf8')
    path=lib.root/'装备编辑器配置/人物编辑.json'
    before=path.read_bytes() if path.exists() else None
    if before:
        meta=json.loads(before.decode('utf8'));changed=False
        for rec in meta.values():
            for pair in rec.get('settings',{}).get('kungfu',[]):
                if pair[0] in mapping:pair[0]=mapping[pair[0]];changed=True
        if changed:originals[path]=before;payloads[path]=json.dumps(meta,ensure_ascii=False,indent=2).encode('utf8')
    for path in [lib.root/'Save.sav',*sorted((lib.root/'SaveFile').glob('*/Save.sav'))]:
        if not path.is_file():continue
        raw=path.read_bytes()
        try:after=remap_save(raw,mapping)
        except ValueError as error:notes.append(f'{path.parent.name} 已跳过：{error}');continue
        if after!=raw:originals[path]=raw;payloads[path]=after
    from martial_collection import augment
    augment(lib.root,payloads,originals,notes)
    report=lib.root/'装备编辑器配置/武学攻击编号迁移.txt'
    originals[report]=report.read_bytes() if report.exists() else None
    payloads[report]=('\n'.join([f'{old} → {new}：{lib.name(new)}' for old,new in mapping.items()]+notes)+'\n旧编号保留隐藏兼容记录；人物配置、已学等级、经验和收藏进度同步迁移。').encode('utf8')
    return payloads,originals,mapping,notes

def open_repair(host):
    from engine import ensure_closed,transaction
    from tkinter import messagebox
    if host.busy or not host.catalog:return
    if host.has_changes():host.error(ValueError('请先保存或撤销草稿'));return
    try:ensure_closed()
    except Exception as error:host.error(error);return
    root=host.catalog.root
    def work():
        payloads,originals,mapping,notes=plan(root)
        return transaction(root,payloads,originals,'修复旧新增武学的原生 AI 编号'),len(mapping),notes
    def finish(result):
        backup,count,notes=result;host.martial_page.reset();host.role_page.reset();host.reload()
        messagebox.showinfo('武学编号修复',f'已迁移 {count} 个武学编号，保留等级、经验和收藏进度。\n'+ '\n'.join(notes)+f'\n备份：{backup}\n请重启游戏验证切磋。',parent=host)
    host.martial_page.worker('正在检查旧武学编号并准备备份迁移…',work,finish)
