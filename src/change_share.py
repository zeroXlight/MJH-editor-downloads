"""Portable checked configuration packets and batch-isolated field merges."""
import io,json,zipfile,hashlib,copy,re
from pathlib import Path,PurePosixPath
from datetime import datetime

FORMAT='mjh-change-effects';VERSION=3
MAX_BYTES=2*1024**3

def sha(raw):return hashlib.sha256(raw).hexdigest() if raw is not None else None

def safe_path(root,name):
    if not isinstance(name,str) or '\\' in name or ':' in name:raise ValueError('改动文件路径无效')
    p=PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts or not p.parts or p.as_posix()!=name:raise ValueError('改动文件路径越界')
    from engine import SCHEMAS
    tables=set(SCHEMAS)|{'Difficult','CommonConfig','KungfuBase'}
    allowed=(len(p.parts)==2 and p.parts[0]=='TableData' and p.suffix=='.bytes' and p.stem in tables)
    allowed|=(len(p.parts)==3 and p.parts[:2]==('DreamRivakes_Data','StreamingAssets') and p.suffix=='.bytes' and p.stem in tables)
    allowed|=name in ('DreamRivakes_Data/resources.assets','DreamRivakes_Data/Plugins/RaceLogic_Release_x64.dll')
    allowed|=(p.parts[0]=='装备编辑器配置' and p.suffix in ('.json','.txt') and len(p.parts)<=3)
    allowed|=(p.parts[:4]==('ModProject','GameProject','Mod_MJH','Json') and len(p.parts)==5 and p.suffix=='.json')
    allowed|=(p.parts[:6]==('ModProject','GameProject','Mod_MJH','Source','Other','martial_editor') and len(p.parts)==7 and p.suffix=='.png')
    allowed|=(p.parts[:6]==('ModProject','GameProject','Mod_MJH','Source','Other','role_editor') and len(p.parts)==7 and p.suffix=='.png')
    allowed|=(p.parts[:2]==('mod','editor_model_textures') and len(p.parts)==3 and re.fullmatch(r'tex_[0-9a-f]{32}\.png',p.name) is not None)
    if not allowed:raise ValueError('此文件不属于可共享的编辑器配置：'+name)
    target=(Path(root)/Path(name)).resolve()
    if not target.is_relative_to(Path(root).resolve()):raise ValueError('改动目标路径越界')
    return target

def span(before,after):
    if before is None or after is None:return 0,0,after
    n=min(len(before),len(after));prefix=0;step=65536
    while prefix+step<=n and before[prefix:prefix+step]==after[prefix:prefix+step]:prefix+=step
    for a,b in zip(before[prefix:min(n,prefix+step)],after[prefix:min(n,prefix+step)]):
        if a!=b:break
        prefix+=1
    suffix=0;limit=n-prefix
    while suffix+step<=limit and before[len(before)-suffix-step:len(before)-suffix]==after[len(after)-suffix-step:len(after)-suffix]:suffix+=step
    remaining=min(step,limit-suffix)
    for a,b in zip(reversed(before[len(before)-suffix-remaining:len(before)-suffix]),reversed(after[len(after)-suffix-remaining:len(after)-suffix])):
        if a!=b:break
        suffix+=1
    return prefix,suffix,after[prefix:len(after)-suffix if suffix else len(after)]

def operation(root,payloads,originals,entries,equipment):
    root=Path(root).resolve();files=[];blobs={};warnings=[];lookup={}
    from change_log import table_changes
    from engine import effect_draft
    changes=table_changes(root,payloads,originals);models=[];equipment_ids=set();books=False
    for ident,(before,after) in changes.get('Item',{}).items():
        item=after or before
        if 1 not in item.get('Feature',[]) or item.get('ItemType') in (15,16):books=True;continue
        equipment_ids.add(ident)
        if before and after and effect_draft(before)['gifts']!=effect_draft(after)['gifts']:
            models.append({'type':ident,'name':item.get('ItemName',str(ident)),'gifts':effect_draft(after)['gifts']})
    equipment_only=bool(equipment_ids or equipment) and not books and not (set(changes)-{'Item'})
    mixed_equipment=bool(equipment_ids) and not equipment_only
    if mixed_equipment:warnings.append('混合批次仅共享可独立追溯的装备天赋；其他整体配置请分开保存后导出。')
    equipment_files={'TableData/Item.bytes','DreamRivakes_Data/StreamingAssets/Item.bytes','DreamRivakes_Data/resources.assets','ModProject/GameProject/Mod_MJH/Json/Item_warehouse_editor.json'}
    for path,after in payloads.items():
        path=Path(path);before=originals.get(path)
        if before==after:continue
        if path.name.casefold() in ('save.sav','saveai.sav'):
            warnings.append('装备仅共享同型号天赋效果；实例词条、强化等级与存档进度不共享。');continue
        name=path.relative_to(root).as_posix()
        if mixed_equipment:continue
        if equipment_only and (name in equipment_files or
                               (path.parent == root/'ModProject/GameProject/Mod_MJH/Json' and path.name.startswith('Item_'))):continue
        try:safe_path(root,name)
        except ValueError:
            warnings.append('此文件仅记录日志，未纳入共享：'+name);continue
        prefix,suffix,delta=span(before,after);blob=f'data/{len(files)}.bin' if delta is not None else None
        if blob:blobs[blob]=delta
        from change_merge import make_recipe
        recipe=make_recipe(name,before,after,root,originals,lookup)
        merge_blob=f'merge/{len(files)}.bin' if recipe is not None else None
        if merge_blob:
            import msgpack
            blobs[merge_blob]=msgpack.packb(recipe,use_bin_type=True)
        files.append({'merge_blob':merge_blob,'merge_sha256':sha(blobs[merge_blob]) if merge_blob else None,'path':name,'before_sha256':sha(before),'after_sha256':sha(after),
                      'before_length':len(before) if before is not None else None,
                      'after_length':len(after) if after is not None else None,
                      'prefix':prefix,'suffix':suffix,'blob':blob,'blob_sha256':sha(delta)})
    shared_entries=[e for e in entries if e['category'] not in ('武器','装备','存档') or '天赋效果' in e['effect']]
    op={'time':datetime.now().astimezone().isoformat(timespec='seconds'),'entries':shared_entries,'files':files,
            'required_refs':__import__('change_merge').required_refs(changes),'equipment':[],'model_gifts':models,'notes':sorted(set(warnings))}
    included={root/f['path']:payloads[root/f['path']] for f in files}
    add_texture_dependencies(root,op,blobs,included,payloads)
    return op,blobs

def add_texture_dependencies(root,op,blobs,references,available=None):
    from model_texture import texture_dependencies
    buffers=dict(available or {});buffers.update(references)
    # Scan only exported configuration; available holds pending in-memory PNGs.
    images=texture_dependencies(root,{**references,**{p:raw for p,raw in buffers.items() if Path(p).suffix=='.png'}})
    existing={f['path'] for f in op['files']}
    for path,raw in images.items():
        name=path.relative_to(root).as_posix()
        if name in existing:continue
        blob='textures/'+path.name;blobs[blob]=raw
        op['files'].append({'path':name,'before_sha256':None,'after_sha256':sha(raw),
            'before_length':None,'after_length':len(raw),'prefix':0,'suffix':0,'blob':blob,'blob_sha256':sha(raw),
            'merge_blob':None,'merge_sha256':None})
        existing.add(name)

def _write_packet(target,operations):
    manifest={'format':FORMAT,'version':VERSION,'editor_version':'V2.1.54','operations':[]}
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
        for index,(op,blobs) in enumerate(operations):
            op=copy.deepcopy(op)
            for f in op['files']:
                if f['blob']:f['blob']=f'op/{index}/'+f['blob']
                if f.get('merge_blob'):f['merge_blob']=f'op/{index}/'+f['merge_blob']
            manifest['operations'].append(op)
            for name,raw in blobs.items():z.writestr(f'op/{index}/'+name,raw)
        z.writestr('改动清单.json',json.dumps(manifest,ensure_ascii=False,indent=2))
        from change_log import line
        z.writestr('改动日志.txt','\n'.join(line(e) for op in manifest['operations'] for e in op['entries']))

def write_packet(target,operations):
    if hasattr(target,'write'):return _write_packet(target,operations)
    import tempfile,os
    target=Path(target).resolve()
    with tempfile.NamedTemporaryFile(dir=target.parent,prefix='.'+target.name+'.',suffix='.tmp',delete=False) as f:temporary=Path(f.name)
    try:
        _write_packet(temporary,operations)
        os.replace(temporary,target)
    finally:temporary.unlink(missing_ok=True)

def read_packet(source):
    with zipfile.ZipFile(source) as z:
        names=z.namelist()
        if len(names)>10000 or len(set(names))!=len(names) or sum(i.file_size for i in z.infolist())>MAX_BYTES:raise ValueError('共享文件过大或存在重复内容')
        if '改动清单.json' not in names or z.getinfo('改动清单.json').file_size>20*1024**2:raise ValueError('缺少有效改动清单')
        value=json.loads(z.read('改动清单.json'))
        if value.get('format')!=FORMAT or value.get('version') not in (2,VERSION):raise ValueError('不支持此改动文件格式')
        ops=value.get('operations')
        if not isinstance(ops,list) or not 1<=len(ops)<=1000:raise ValueError('改动批次数量无效')
        result=[]
        for op in ops:
            blobs={};paths=set()
            if not isinstance(op.get('notes',[]),list) or any(not isinstance(n,str) for n in op.get('notes',[])):raise ValueError('共享说明无效')
            if not isinstance(op.get('required_refs',{}),dict):raise ValueError('共享依赖无效')
            if not isinstance(op.get('files'),list) or op.get('equipment')!=[] or not isinstance(op.get('model_gifts'),list) or not isinstance(op.get('entries'),list):raise ValueError('不支持装备实例共享；请重新导出整体可追溯的改动')
            for f in op['files']:
                safe_path(Path.cwd(),f['path'])
                if f['path'] in paths:raise ValueError('同一批次文件路径重复')
                paths.add(f['path'])
                for k in ('prefix','suffix'):
                    if type(f.get(k)) is not int or f[k]<0:raise ValueError('改动位置无效')
                for k in ('before_length','after_length'):
                    if f.get(k) is not None and (type(f[k]) is not int or not 0<=f[k]<=MAX_BYTES):raise ValueError('改动长度无效')
                for k in ('before_sha256','after_sha256','blob_sha256','merge_sha256'):
                    if f.get(k) is not None and not re.fullmatch('[0-9a-f]{64}',str(f[k])):raise ValueError('改动校验值无效')
                if f.get('blob'):
                    if f['blob'] not in names:raise ValueError('共享文件缺少改动内容')
                    raw=z.read(f['blob'])
                    if sha(raw)!=f['blob_sha256']:raise ValueError('共享文件内容校验失败')
                    blobs[f['blob']]=raw
            for f in op['files']:
                if f.get('merge_blob'):
                    if f['merge_blob'] not in names:raise ValueError('共享文件缺少记录合并内容')
                    raw=z.read(f['merge_blob'])
                    if sha(raw)!=f.get('merge_sha256'):raise ValueError('记录合并内容校验失败')
                    blobs[f['merge_blob']]=raw
            for r in op['model_gifts']:
                if type(r.get('type')) is not int or set(r)-{'type','name','gifts'} or not isinstance(r.get('gifts'),list) or len(r['gifts'])>4096:raise ValueError('装备型号天赋改动无效')
                for gift in r['gifts']:
                    if set(gift)!={'id','level'} or type(gift['id']) is not int or type(gift['level']) is not int or not 0<=gift['level']<=20:raise ValueError('天赋效果或解锁等级无效')
            for e in op['entries']:
                if not all(isinstance(e.get(k),str) and len(e[k])<=100000 for k in ('category','name','action','effect')):raise ValueError('日志内容无效')
            result.append((op,blobs))
        return result

def apply_model_gifts(root,payloads,recipes):
    """Regenerate only gift effects against a temporary copy of current config."""
    import tempfile,shutil
    from engine import Catalog,effect_draft,effect_payloads
    matched=set();skipped=set();reads={}
    from editor_temp import workspace_temp
    with workspace_temp(root,'mjh_share_config_') as folder:
        virtual=Path(folder);(virtual/'DreamRivakes.exe').touch()
        paths=[root/'TableData'/f'{n}.bytes' for n in ('Item','Gift','Language','AttrIsPercent','Martial')]
        paths.append(root/'DreamRivakes_Data/resources.assets')
        paths.extend((root/'ModProject/GameProject/Mod_MJH/Json').glob('*.json'))
        duplicate=root/'DreamRivakes_Data/StreamingAssets/Item.bytes'
        if duplicate.exists():paths.append(duplicate)
        for p in set(paths)|set(payloads):
            physical=p.read_bytes() if p.exists() else None;reads[p]=physical
            data=payloads.get(p,physical)
            if data is None:continue
            target=virtual/p.relative_to(root);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        catalog=Catalog(virtual);drafts={}
        for r in recipes:
            ident=r['type']
            if not catalog.is_equipment(ident):skipped.add(ident);continue
            draft=copy.deepcopy(effect_draft(catalog.items[ident]));draft['gifts']=copy.deepcopy(r['gifts'])
            matched.add(ident)
            if draft!=effect_draft(catalog.items[ident]):drafts[ident]=draft
        for path,data in effect_payloads(catalog,drafts,skip_errors=True).items():payloads[root/path.relative_to(virtual)]=data
        rejected=set(catalog.last_effect_skips);matched.difference_update(rejected);skipped.update(rejected)
    return matched,skipped,reads

def signature(operations):
    simple=[{'files':[{k:v for k,v in f.items() if k not in ('blob','merge_blob')} for f in op['files']],
             'model_gifts':op.get('model_gifts',[]),'required_refs':op.get('required_refs',{})} for op,blobs in operations]
    return sha(json.dumps(simple,ensure_ascii=False,sort_keys=True).encode())

def guard_equipment_fields(before,after,client=False):
    if before is None or after is None:return
    from engine import SCHEMAS
    if client:
        from client_config import Assets,lua_rows
        from martial_editor import enum_values
        a,b=Assets(before),Assets(after)
        ta,tb=a.script('Item.lua'),b.script('Item.lua')
        if ta==tb:return
        enums=enum_values(b.script('common.lua'))|enum_values(b.script('Enum.lua'))
        old,new=lua_rows(ta,'Item',enums),lua_rows(tb,'Item',enums)
    else:
        from change_log import rows
        old,new=rows(before,'Item'),rows(after,'Item')
    for ident in old.keys()|new.keys():
        a,b=old.get(ident,{}),new.get(ident,{})
        if not (1 in a.get('Feature',[]) or 1 in b.get('Feature',[])):continue
        if (b or a).get('ItemType') in (15,16):continue
        for k in a.keys()|b.keys():
            if k in ('BlueGift','BlueGiftUnlockLv'):continue
            spec=SCHEMAS['Item'].get(k,{})
            default=[] if spec.get('label')==3 else '' if spec.get('type')==9 else 0
            if a.get(k,default)!=b.get(k,default):raise ValueError('共享文件包含不允许导入的装备属性或实例改动；装备仅支持天赋效果')

def guard_item_json(root,before,after):
    from engine import Catalog
    old={r['BaseID']:r for r in json.loads((before or b'{"Items":[]}').decode('utf-8-sig')).get('Items',[])}
    new={r['BaseID']:r for r in json.loads((after or b'{"Items":[]}').decode('utf-8-sig')).get('Items',[])}
    if old==new:return
    catalog=Catalog(root)
    for ident in old.keys()|new.keys():
        if not catalog.is_equipment(ident) or catalog.items[ident].get('ItemType') in (15,16):continue
        current=catalog.items[ident]
        for key in old.get(ident,{}).keys()|new.get(ident,{}).keys():
            if key in ('BaseID','BlueGift','BlueGiftUnlockLv'):continue
            if key in new.get(ident,{}) and new[ident][key]!=current.get(key):raise ValueError('共享文件包含不允许导入的装备属性；装备仅支持天赋效果')
            if key in old.get(ident,{}) and key not in new.get(ident,{}):raise ValueError('共享文件尝试删除装备属性配置；装备仅支持天赋效果')

def _plan_import(root,operations,save=None):
    root=Path(root).resolve();payloads={};originals={};skipped=set();matched=set()
    if any(op.get('equipment') for op,blobs in operations):raise ValueError('不支持导入装备实例改动；装备仅支持同型号天赋效果')
    final={f['path']:f['after_sha256'] for op,blobs in operations for f in op['files']}
    initial={};finished=set()
    for name,h in final.items():
        p=safe_path(root,name);raw=p.read_bytes() if p.exists() else None
        initial[p]=raw
        if sha(raw)==h:finished.add(name)
    receipt=signature(operations)
    for p in (root/'装备编辑器备份').glob('*/manifest.json'):
        try:value=json.loads(p.read_text(encoding='utf-8'))
        except (OSError,ValueError):continue
        if value.get('complete') is not True or value.get('share_signature')!=receipt:continue
        entries=value['entries'];valid=True
        for e in entries:
            if Path(e['path']).name.casefold() in ('save.sav','saveai.sav'):continue
            try:target=safe_path(root,Path(e['path']).as_posix())
            except ValueError:valid=False;break
            if sha(target.read_bytes() if target.exists() else None)!=e['after_sha256']:valid=False;break
        if valid:return {},{},0,0
    for op,blobs in operations:
        for f in op['files']:
            if f['path'] in finished:continue
            path=safe_path(root,f['path']);before=payloads.get(path,initial[path])
            if sha(before)==f['after_sha256']:continue
            recipe=None
            if f.get('merge_blob'):
                import msgpack
                recipe=msgpack.unpackb(blobs[f['merge_blob']],raw=False,strict_map_key=False)
            merging=sha(before)!=f['before_sha256'] or bool(recipe and recipe.get('inherit'))
            if merging:
                if not f.get('merge_blob'):raise ValueError('此旧版或二进制改动不支持按记录合并，目标文件存在差异：'+f['path'])
                import msgpack
                from change_merge import apply_recipe
                recipe=msgpack.unpackb(blobs[f['merge_blob']],raw=False,strict_map_key=False)
                after=apply_recipe(f['path'],before,recipe,root,payloads)
            elif f['after_sha256'] is None:after=None
            else:
                raw=blobs.get(f['blob'],b'');base=before or b''
                if f['prefix']+f['suffix']>len(base):raise ValueError('改动位置超出目标文件')
                after=base[:f['prefix']]+raw+(base[len(base)-f['suffix']:] if f['suffix'] else b'')
                if len(after)!=f['after_length'] or sha(after)!=f['after_sha256']:raise ValueError('改动回读校验失败：'+f['path'])
            if f['path'] in ('TableData/Item.bytes','DreamRivakes_Data/StreamingAssets/Item.bytes'):guard_equipment_fields(before,after)
            elif f['path']=='DreamRivakes_Data/resources.assets':guard_equipment_fields(before,after,client=True)
            elif Path(f['path']).name.startswith('Item_') and f['path'].endswith('.json'):guard_item_json(root,before,after)
            originals.setdefault(path,initial[path]);payloads[path]=after
        if op.get('model_gifts'):
            yes,no,reads=apply_model_gifts(root,payloads,op['model_gifts']);matched.update(yes);skipped.update(no)
            for p,data in reads.items():initial.setdefault(p,data);originals.setdefault(p,data)
    from change_merge import validate_refs,rebase_mod_overrides,reconcile_role_metadata
    rebase_mod_overrides(root,payloads,originals)
    reconcile_role_metadata(root,payloads,originals)
    for op,blobs in operations:validate_refs(root,op.get('required_refs',{}),payloads)
    for p,data in list(payloads.items()):
        before=initial[p] if p in initial else (p.read_bytes() if p.exists() else None)
        if before==data:payloads.pop(p);originals.pop(p,None)
        else:originals[p]=before
    from compatibility import validate_native_writes
    validate_native_writes(root,payloads,originals)
    return payloads,originals,len(matched),len(skipped-matched)

def plan_import(root,operations,save=None):
    """Stage each linked batch atomically; conflicting batches do not block others."""
    root=Path(root).resolve()
    if any(op.get('equipment') for op,blobs in operations):raise ValueError('不支持导入装备实例改动；装备仅支持同型号天赋效果')
    # A virtual tree lets later batches observe earlier staged changes without
    # writing the actual game. Copy only paths referenced by the packet.
    import tempfile
    payloads={};originals={};matched=0;skipped=0;blocked={}
    from editor_temp import workspace_temp
    with workspace_temp(root,'mjh_merge_') as folder:
        virtual=Path(folder).resolve()
        paths={safe_path(root,f['path']) for op,blobs in operations for f in op['files']}
        if any(op.get('model_gifts') for op,blobs in operations):
            paths.update(root/'TableData'/f'{n}.bytes' for n in ('Item','Gift','Language','AttrIsPercent','Martial'))
            paths.add(root/'DreamRivakes_Data/resources.assets')
            paths.update((root/'ModProject/GameProject/Mod_MJH/Json').glob('*.json'))
            duplicate=root/'DreamRivakes_Data/StreamingAssets/Item.bytes'
            if duplicate.exists():paths.add(duplicate)
        if any(op.get('required_refs') or any(f.get('merge_blob') for f in op['files']) for op,blobs in operations):
            paths.update((root/'TableData').glob('*.bytes'))
            paths.update((root/'ModProject/GameProject/Mod_MJH/Json').glob('*.json'))
            assets=root/'DreamRivakes_Data/resources.assets'
            if assets.exists():paths.add(assets)
        if any(p.suffix=='.dll' for p in paths):
            from engine import META
            paths.update(root/'DreamRivakes_Data/Plugins'/name for name in META['native_hashes'])
        for path in paths:
            try:raw=path.read_bytes() if path.exists() else None
            except OSError as error:blocked[path]=str(error);continue
            originals[path]=raw
            if raw is not None:
                dest=virtual/path.relative_to(root);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
        (virtual/'DreamRivakes.exe').touch()
        final={f['path']:f['after_sha256'] for op,blobs in operations for f in op['files']}
        finished={name for name,h in final.items() if safe_path(root,name) not in blocked and sha(originals.get(safe_path(root,name)))==h}
        for index,(op,blobs) in enumerate(operations):
            selected={**op,'files':[f for f in op['files'] if f['path'] not in finished]}
            try:
                bad=[f['path'] for f in selected['files'] if safe_path(root,f['path']) in blocked]
                if bad:raise ValueError('目标文件无法读取：'+', '.join(bad))
                new,old,yes,no=_plan_import(virtual,[(selected,blobs)],save)
            except (ValueError,KeyError,TypeError,UnicodeError,OSError,IndexError,OverflowError,RecursionError) as error:
                note=f'第 {index+1} 批已跳过，关联文件均未写入：{error}'
                notes=op.setdefault('notes',[])
                if note not in notes:notes.append(note)
                skipped+=1;continue
            matched+=yes;skipped+=no
            for path,data in new.items():
                actual=root/path.relative_to(virtual)
                if actual not in originals:originals[actual]=actual.read_bytes() if actual.exists() else None
                payloads[actual]=data;path.parent.mkdir(parents=True,exist_ok=True)
                if data is None:path.unlink(missing_ok=True)
                else:path.write_bytes(data)
    payloads={p:v for p,v in payloads.items() if originals.get(p)!=v}
    return payloads,originals,matched,skipped

def read_history_packet(root,source):
    """Upgrade locally backed-up v2 batches when before-images are available."""
    root=Path(root).resolve();source=Path(source);operations=read_packet(source)
    manifest=source.parent/'manifest.json'
    if not manifest.exists():
        for op,blobs in operations:
            references={root/f['path']:blobs.get(f.get('blob'),b'') for f in op['files']}
            add_texture_dependencies(root,op,blobs,references)
        return operations
    try:entries=json.loads(manifest.read_text(encoding='utf8'))['entries']
    except (OSError,ValueError,KeyError):return operations
    snapshots={}
    # Complete metadata/model-table images are small and reveal unchanged
    # texture references too. Assets with an existing merge recipe need no
    # extra several-hundred-MB backup copy just to find image dependencies.
    needed={f['path'] for op,blobs in operations for f in op['files']
        if not f.get('merge_blob') or f['path'].endswith('.json') or Path(f['path']).name=='RoleModel.bytes'}
    for entry in entries:
        if entry['path'] not in needed:continue
        try:
            target=safe_path(root,entry['path']);backup=(source.parent/entry['backup']).resolve()
            if not backup.is_relative_to(source.parent.resolve()):continue
            raw=backup.read_bytes() if entry['exists'] else None
            if sha(raw)==entry['before_sha256']:snapshots[target]=raw
        except (OSError,ValueError,KeyError):continue
    from change_merge import make_recipe,required_refs
    from change_log import table_changes
    import msgpack
    for index,(op,blobs) in enumerate(operations):
        afters={};befores={}
        references={root/f['path']:blobs.get(f.get('blob'),b'') for f in op['files']}
        for number,f in enumerate(op['files']):
            path=safe_path(root,f['path'])
            if f['before_sha256'] is None:before=None
            elif path in snapshots and sha(snapshots[path])==f['before_sha256']:before=snapshots[path]
            else:continue
            base=before or b''
            after=None if f['after_sha256'] is None else base[:f['prefix']]+blobs.get(f['blob'],b'')+(base[-f['suffix']:] if f['suffix'] else b'')
            if sha(after)!=f['after_sha256']:continue
            references[path]=after
            if f.get('merge_blob'):continue
            befores[path]=before;afters[path]=after
            recipe=make_recipe(f['path'],before,after,root,snapshots)
            if recipe is not None:
                name=f'upgrade/{index}/{number}.bin';raw=msgpack.packb(recipe,use_bin_type=True)
                blobs[name]=raw;f.update(merge_blob=name,merge_sha256=sha(raw))
        if afters:op['required_refs']=required_refs(table_changes(root,afters,befores))
        add_texture_dependencies(root,op,blobs,references)
    return operations

def record_transaction(root,changes,originals,purpose,backup,share_operations=None,audit_entries=None):
    from change_log import summarize,line
    if audit_entries is None:
        entries,equipment=summarize(root,changes,originals,purpose)
        op,blobs=operation(root,changes,originals,entries,equipment)
    else:
        # Native feature installation includes an ABI-specific DLL and private
        # save state. Keep its complete transaction audit and hashes/backups,
        # without exporting disconnected table edits as a portable mod.
        entries=list(audit_entries)
        op={'time':datetime.now().astimezone().isoformat(timespec='seconds'),
            'entries':entries,'files':[],'required_refs':{},'equipment':[],
            'model_gifts':[],'notes':['运行库功能与存档余额仅记录日志；请在目标游戏使用对应功能开关。']}
        blobs={}
    operations=share_operations or [(op,blobs)]
    write_packet(backup/'改动效果.mjhchanges',operations)
    (backup/'改动日志.txt').write_text('\n'.join(line(e) for e in entries),encoding='utf-8')
    return entries,op['time'],signature(operations)
