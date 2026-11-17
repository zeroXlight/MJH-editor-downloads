"""Reuse existing validated editor planners against a temporary data overlay."""
import tempfile,copy,json
from pathlib import Path
from object_bundle import key

def finish_runtime(store,packet,mapping,rows,payloads):
    from martial_editor import MartialLibrary,TABLES
    from editor_temp import workspace_temp
    with workspace_temp(store.root,'mjh_object_runtime_') as folder:
        virtual=Path(folder).resolve()
        paths={store.root/'TableData'/f'{t}.bytes' for t in (*TABLES,'AttrIsPercent','KungfuBase')}
        paths.add(store.root/'DreamRivakes_Data/resources.assets')
        paths.add(store.root/'DreamRivakes_Data/Plugins/RaceLogic_Release_x64.dll')
        paths.add(store.root/'DreamRivakes_Data/Plugins/ClientDll.dll')
        paths.update(store.root.glob('装备编辑器配置/*.json'))
        paths.update((store.root/'ModProject/GameProject/Mod_MJH/Json').glob('*.json'))
        # Role-only planners need their read-only dependencies too.
        from role_editor import EDIT_TABLES
        if rows.get('Role'):
            from role_dependency_repair import ALLOWED
            paths.update(store.root/'TableData'/f'{t}.bytes' for t in set(EDIT_TABLES)|ALLOWED|{'City','Map','RoleWishQuest'})
        if rows.get('Role'):
            # Validation also visits existing characters; their installed custom
            # model files must be visible in the isolated planner workspace.
            for directory in ('mod/editor_mobile_models','mod/editor_model_textures'):
                paths.update(p for p in (store.root/directory).rglob('*') if p.is_file())
        for path in paths|set(payloads):
            raw=payloads.get(path,store.read(path))
            if raw is None:continue
            target=virtual/path.relative_to(store.root);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        raw=None
        if rows.get('Martial'):
            lib=MartialLibrary(virtual)
            for table,records in rows.items():
                if table in lib.changes and table not in ('Role','Item'):
                    for ident,row in records.items():lib.changes[table][ident]=copy.deepcopy(row)
            # The graph has already resolved IDs and equivalent effects.
            # Editing presentation here would clone shared clauses again.
            additional,_=lib.plan(preserve_imported=True)
            for path,raw in additional.items():
                real=store.root/path.relative_to(virtual);store.read(real);payloads[real]=raw
                path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
            del lib,additional,_
            raw=None
        if rows.get('Role'):
            from role_editor import RoleLibrary
            from role_locations import install_placement
            lib=RoleLibrary(virtual)
            before=store.read(store.root/'装备编辑器配置/人物编辑.json')
            lib.meta_before=json.loads(before.decode('utf8')) if before else {}
            for old in packet.get('role_groups',{}):
                rid=mapping[key('@Role',int(old))]
                if str(rid) not in lib.meta:continue
                rec=lib.meta[str(rid)];path=rec['settings'].get('location_path',[])
                if path:rec['position_task']=install_placement(lib,rid,path,rec)
            additional,_=lib.plan()
            # Keep the import preview aligned with legacy-role wish/model repairs.
            for ident in lib.changes['Role']:
                rows.setdefault('Role',{})[ident]=copy.deepcopy(lib.tables['Role'][ident])
            for path,raw in additional.items():
                real=store.root/path.relative_to(virtual);store.read(real);payloads[real]=raw
            del lib,additional,_
            raw=None
    from client_runtime_repair import repair
    path=store.root/'DreamRivakes_Data/resources.assets'
    warnings=packet['extras'].setdefault('compatibility_warnings',[])
    payloads[path]=repair(payloads.get(path,store.read(path)),warnings)
    return payloads
