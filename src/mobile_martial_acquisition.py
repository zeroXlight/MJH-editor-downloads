"""Native acquisition pools, copying, collection and manuals for restored arts."""
import json
from client_config import Assets
from martial_editor import patch_table,patch_lua_rows

def reconnect(store,payloads,originals,installed):
    from feature_fields import sync
    from codec import decode
    from engine import SCHEMAS
    updates={};clans=store.table('Clan');martials=store.table('Martial')
    for rec in installed.values():
        m=martials[rec['id']];cid=m['ClanID'];current=clans[cid]
        native=decode(store.native['Clan'][cid],'Clan',SCHEMAS)
        field={1:'Dart',2:'Knife',3:'Sword',4:'Magic',5:'Stick',7:'Fist',8:'Leg'}.get(m['DepartEnum'])
        for name in (field,'BestMartial' if m['Rank']>=6 else 'HighMartial'):
            if name is None:continue
            delta=updates.setdefault('Clan',{}).setdefault(cid,{})
            wanted=list(delta.get(name,native.get(name,[])))
            for value in [*current.get(name,[]),rec['id']]:
                if value not in wanted:wanted.append(value)
            if wanted!=native.get(name,[]) or wanted!=current.get(name,[]):delta[name]=wanted
    if 'OpenMakeSecret' in SCHEMAS['Story']:
        for ident,row in store.table('Story').items():
            raw=store.native['Story'].get(ident)
            native=decode(raw,'Story',SCHEMAS) if raw else {}
            if row.get('OpenMakeSecret')!=1 or native.get('OpenMakeSecret')!=1:
                updates.setdefault('Story',{})[ident]={'OpenMakeSecret':1}
    updates={t:{i:d for i,d in rows.items() if d} for t,rows in updates.items()}
    updates={t:r for t,r in updates.items() if r}
    if updates:
        more,old=sync(store,updates);payloads.update(more)
        for p,b in old.items():originals.setdefault(p,p.read_bytes() if p.exists() else None)
    for p,b in store.reads.items():originals.setdefault(p,p.read_bytes() if p.exists() else None)

def stage(store,payloads,installed):
    clans={};martials=store.table('Martial');source_items=list(store.table('Item').values())
    # Read the staged martial records, which already carry their new IDs.
    from codec import decode
    from engine import SCHEMAS
    from martial_editor import indexed_rows
    current={i:decode(v,'Martial',SCHEMAS) for i,v in indexed_rows(payloads[store.root/'TableData/Martial.bytes'])[0].items()}
    items={i:decode(v,'Item',SCHEMAS) for i,v in indexed_rows(payloads[store.root/'TableData/Item.bytes'])[0].items()}
    changed_items={}
    for rec in installed.values():
        mid=rec['id'];m=current[mid];cid=m['ClanID'];row=clans.setdefault(cid,dict(store.table('Clan')[cid]))
        row={k:list(v) if isinstance(v,list) else v for k,v in row.items()};clans[cid]=row
        field={1:'Dart',2:'Knife',3:'Sword',4:'Magic',5:'Stick',7:'Fist',8:'Leg'}.get(m['DepartEnum'])
        for name in [field,'BestMartial' if m['Rank']>=6 else 'HighMartial']:
            if name and mid not in row.get(name,[]):row[name]=row.get(name,[])+[mid]
        donors=[r for r in source_items if r.get('ItemType')==15 and r.get('Rank')==m['Rank'] and 2 in r.get('Feature',[])]
        exact=[r for r in donors if martials.get(r.get('MartialID'),{}).get('DepartEnum')==m['DepartEnum']];donors=exact or donors
        if not donors:raise ValueError('缺少同品质原生秘籍价格模板：'+rec['name'])
        donor=sorted(donors,key=lambda r:r['BaseID'])[0]
        book=dict(items[rec['book']]);book.update({k:donor[k] for k in ('BuyPrice','SellPrice','Present','LimitNum','MaxNum')})
        book.update(CommonUseCondition=[],levelCond=0,clanCond=0,attrCond=0,attrValueCond=0,PersonalTreasure=0,ClanTreasure=0,NoneTreasure=0,DropCondID=0)
        changed_items[book['BaseID']]=book
    def update(table,changes):
        for directory in ('TableData','DreamRivakes_Data/StreamingAssets'):
            path=store.root/directory/(table+'.bytes');raw=payloads.get(path,store.read(path))
            if raw is not None:payloads[path]=patch_table(raw,table,changes)
        path=store.root/'DreamRivakes_Data/resources.assets';a=Assets(payloads.get(path,store.assets.data))
        if table in a.scripts:
            _,q,n=a.scripts[table];a=Assets(a.replace_blob(table,patch_table(a.data[q+4:q+4+n],table,changes)))
        a=Assets(a.replace_script(table+'.lua',patch_lua_rows(a.script(table+'.lua'),changes)))
        payloads[path]=a.data
        path=store.root/'ModProject/GameProject/Mod_MJH/Json'/f'{table}_martial_editor.json';raw=payloads.get(path,store.read(path));obj=json.loads(raw) if raw else {'Items':[]}
        existing={r['BaseID']:r for r in obj['Items']}
        for i,r in changes.items():existing.setdefault(i,{}).update(r)
        obj['Items']=list(existing.values());payloads[path]=json.dumps(obj,ensure_ascii=False,indent=2).encode('utf8')
        # Existing editor/MOD rows can override native tables on the next read.
        # Keep overlapping rows consistent, preserving their JSON containers,
        # unknown fields and all unrelated records.
        directory=path.parent
        candidates=set(directory.glob(table+'_*.json'))|{p for p in payloads if p.parent==directory and p.name.startswith(table+'_')}
        for other in candidates-{path}:
            original=payloads.get(other,store.read(other))
            if not original:continue
            try:document=json.loads(original)
            except (ValueError,UnicodeError):continue
            records=document.get('Items',[]) if isinstance(document,dict) and 'Items' in document else document if isinstance(document,list) else [document] if isinstance(document,dict) and 'BaseID' in document else list(document.values()) if isinstance(document,dict) else []
            changed=False
            for record in records:
                if not isinstance(record,dict) or record.get('BaseID') not in changes:continue
                desired=changes[record['BaseID']]
                if any(record.get(k)!=v for k,v in desired.items()):record.update(desired);changed=True
            if changed:payloads[other]=json.dumps(document,ensure_ascii=False,indent=2).encode('utf8')
    update('Clan',clans);update('Item',changed_items)
    # The PC has the complete native copying protocol. Enabling its story flag
    # opens that existing feature; each art still uses its own CouldCopy value.
    if 'OpenMakeSecret' in SCHEMAS['Story']:
        stories={i:{**r,'OpenMakeSecret':1} for i,r in store.table('Story').items() if r.get('OpenMakeSecret')!=1}
        if stories:update('Story',stories)
