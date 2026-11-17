"""Register custom ordinary martial arts without granting fragment progress."""
from pathlib import Path
from feature_save import load_config,patch_save

def ensure_fragments(lib):
    from caps import baseline
    native={int(i) for i in baseline()['proto']['Martial']}
    # Create only the fragment counterpart. The secret-book toggle continues
    # to control books independently, and existing item flags are preserved.
    for mid in list(lib.changes['Martial']):
        row=lib.tables['Martial'][mid]
        if mid in native or row.get('Display')!=1 or row.get('Drop',0)!=0:continue
        if any(r.get('ItemType')==16 and r.get('MartialID')==mid for r in lib.tables['Item'].values()):continue
        template=lib.book_templates.get(16)
        if template is None:
            lib.compat_notes=getattr(lib,'compat_notes',[])+[f'武学 {mid} 缺少原生残章模板，已跳过残章配置'];continue
        ident=lib.clone('Item',template)
        lib.set('Item',ident,{'MartialID':mid,'Rank':row['Rank'],'ItemName':'《'+lib.name(mid)+'》残章'})

def augment(root,payloads,originals,notes=None):
    """Actual save/import only. Portable configuration exports never call this.

    Reads the staged table data so ID remapping from portable imports is used.
    Existing save rows and all fragment counts remain byte-for-byte unchanged.
    """
    root=Path(root).resolve();notes=notes if notes is not None else []
    config,reads=load_config(root,'collection',notes,payloads)
    if not config['collection']:return
    paths=([root/'Save.sav'] if (root/'Save.sav').is_file() else [])+sorted((root/'SaveFile').glob('*/Save.sav'))
    count=0
    for path in paths:
        try:
            raw=payloads.get(path,path.read_bytes());after=patch_save(raw,'collection',config,[])
            if after!=raw:
                originals.setdefault(path,path.read_bytes());payloads[path]=after
                count+=1
        except (ValueError,OSError) as error:notes.append(f'{path.parent.name} 收藏初始化已跳过：{error}')
    # Store records original on-disk bytes even when reading staged overlays.
    for path,raw in reads.items():originals.setdefault(path,raw)
    if count:notes.append(f'已为 {count} 个存档补齐新增武学收藏初始记录；已有残章和突破进度保持原值')
