"""Use the game's existing random secret-book pools without editing rank weights."""
# Values are native Item.proto Item_ItemFeature enum values, not guessed UI flags.
CANT_DROP=16
EVOLUTION_ONLY=64

def enabled(lib,mid):
    if lib.tables['Martial'][mid].get('Drop',0):return False
    return any(r.get('ItemType')==15 and 2 in r.get('Feature',[]) and not any(f in r.get('Feature',[]) for f in (CANT_DROP,EVOLUTION_ONLY)) and not r.get('DropCondID',0) for r in lib.books(mid))

def configure(lib,mid,allow):
    if allow:
        # Match ordinary native random books. Drop=1 is reserved for non-learnable martial data.
        lib.configure_books(mid,True,lib.tables['Martial'][mid].get('CouldCopy',0))
        lib.set('Martial',mid,{'Drop':0})
    for row in list(lib.tables['Item'].values()):
        if row.get('MartialID')!=mid:continue
        if row.get('ItemType')!=15:continue
        flags=row.get('Feature',[])
        if allow:
            flags=[f for f in flags if f not in (CANT_DROP,EVOLUTION_ONLY)]
            delta={'Feature':list(dict.fromkeys(flags+[2])),'DropCondID':0}
        else:
            delta={'Feature':list(dict.fromkeys(flags+[CANT_DROP]))}
        lib.set('Item',row['BaseID'],delta)
