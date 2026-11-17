"""Restore the native generic task chain for editor-authored roles only."""
from role_traits import safe_wishes
from engine import clean

def equivalent(lib,ident,native):
    row=lib.tables['RoleWishQuest'].get(ident,{});original=lib.tables['RoleWishQuest'][native]
    if clean(lib.text(row.get('NameID',0)))!=clean(lib.text(original.get('NameID',0))):return False
    skip={'BaseID','NameID','DescID','Prefix'}
    return {k:v for k,v in row.items() if k not in skip}=={k:v for k,v in original.items() if k not in skip}

def backfill(lib):
    changed=[];common=None
    for rid in lib.meta:
        role=int(rid)
        if role<1700000000 or role not in lib.roles:continue
        if common is None:
            try:common=safe_wishes(lib)
            except ValueError as error:
                from mod_compatibility import note
                note(lib,'通用心愿自动补齐已跳过：'+str(error));return changed
        if any(lib.overrides['Role'].get(i) for i in lib.roles[role]):
            from mod_compatibility import note
            note(lib,'其他MOD保护的人物未自动改写心愿：'+str(role));continue
        for ident in lib.roles[role]:
            row=lib.tables['Role'][ident];wishes=list(row.get('WishQuestID',[]))
            # 203 was the editor's inert, same-name entry. Do not overwrite other quests.
            legacy=[i for i in wishes if equivalent(lib,i,203)]
            if legacy:
                save=lib.root/'Save.sav'
                from role_wish_save import present
                if save.exists() and present(save.read_bytes(),role,2147483647):lib.meta[rid]['wish_restore_needed']=True
                wishes=[195 if i in legacy else i for i in wishes]
            wishes=[190 if equivalent(lib,i,190) else i for i in wishes]
            for wish in common:
                if wish not in wishes:wishes.append(wish)
            wishes=list(dict.fromkeys(wishes))
            if set(wishes)==set(common):wishes=list(common)
            if wishes!=row.get('WishQuestID',[]):
                lib.set('Role',ident,{'WishQuestID':wishes});changed.append(ident)
    return changed
