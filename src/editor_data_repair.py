"""Reapply retained editor overlays after game updates without using stale row IDs."""
import copy
from functools import lru_cache

@lru_cache(maxsize=3)
def role_baseline(november=False):
    import base64,hashlib,json,zlib
    from engine import DATA_ROOT,SCHEMAS
    from codec import decode
    from martial_editor import indexed_rows
    from bigmap_profile import RACE_SHA,NOV5_RACE_SHA,NOV15_RACE_SHA
    filename='nov15_role_baseline.json' if november=='nov15' else 'nov5_role_baseline.json' if november else 'bigmap_role_baseline.json'
    doc=json.loads((DATA_ROOT/filename).read_text('utf8'))
    raw=zlib.decompress(base64.b64decode(doc['data']))
    if doc['race_sha256']!=(NOV15_RACE_SHA if november=='nov15' else NOV5_RACE_SHA if november else RACE_SHA) or hashlib.sha256(raw).hexdigest()!=doc['table_sha256']:
        raise ValueError('大地图人物对应基线校验失败，未恢复旧配置')
    return {i:decode(r,'Role',SCHEMAS) for i,r in indexed_rows(raw)[0].items()}

# Fields written by RoleLibrary.update. Story, placement and generation structure
# belong to the current game build, even when an old full-row JSON survives.
ROLE_FIELDS=set(('Rank TitleID Gift NameID SurnameID GivennameID Prefix Postfix '
    'Level Clan AttributeID ArtID Kungfu KungfuLevel EvoInitCity NoRandom '
    'hurtSound helloSound dieSound BattleAudio Bag Weapon Artifacts Clothes '
    'Shoe Ornaments KungfuBook Horse').split())

def role_rows(owner,path,rows,native):
    if path.name!='Role_role_editor.json':return rows
    from bigmap_profile import race_image
    race=owner.root/'DreamRivakes_Data/Plugins/RaceLogic_Release_x64.dll'
    if not race.is_file() or not race_image(race.read_bytes()):return rows
    # V236 could already have saved the old row numbers into both game tables.
    # Recover only rows exactly explained by this editor's retained full record.
    from growth_runtime import _original
    from bigmap_profile import november_parent,november15_parent
    parent=_original(race.read_bytes())
    baseline=role_baseline('nov15' if november15_parent(parent) else november_parent(parent));native=copy.deepcopy(native);restored=set()
    identity=lambda r:(r.get('RoleID'),r.get('Index',0))
    for old in rows:
        ident=old['BaseID'];current=native.get(ident);base=baseline.get(ident)
        if current is None or base is None:continue
        if identity(current)==identity(base) and identity(old)==identity(base):continue
        if current==base:continue
        full=identity(current)==identity(old) and all(current.get(k)==v for k,v in old.items())
        writable=ROLE_FIELDS|{'Index','IndexNum'}
        partial=all(v==base.get(k) or k in writable and k in old and v==old[k] for k,v in current.items())
        if not (full or partial):
            raise ValueError('旧人物行号与外部配置冲突，未覆盖：'+str(ident))
        native[ident]=copy.deepcopy(base)
        owner.tables['Role'][ident]=copy.deepcopy(base)
        owner.changes['Role'][ident]=copy.deepcopy(base);restored.add(ident)
    by_key={}
    for ident,row in native.items():
        by_key.setdefault((row.get('RoleID'),row.get('Index',0)),[]).append(ident)
    result=[];used=set();moved=0;collapsed=0
    for old in rows:
        row=copy.deepcopy(old);ident=row['BaseID'];current=native.get(ident)
        key=(row.get('RoleID'),row.get('Index',0))
        # Independently created candidates have no native counterpart.
        if ident<1600000000 and (not current or (current.get('RoleID'),current.get('Index',0))!=key):
            targets=by_key.get(key,[])
            if len(targets)!=1:
                # V236's merge could append the new native tail to the old
                # candidates, then renumber the combined list. These are not
                # independently created candidates: the physical rows already
                # belong to this NPC in the certified game and were restored
                # above after proving the exact editor write.
                base=baseline.get(ident)
                if not targets and ident in restored and base and base['RoleID']==key[0]:
                    collapsed+=1;continue
                raise ValueError('旧人物配置无法唯一对应当前人物，请保留备份：'+str(key))
            ident=targets[0];row=copy.deepcopy(native[ident])
            row.update({k:copy.deepcopy(v) for k,v in old.items() if k in ROLE_FIELDS})
            row['BaseID']=ident;moved+=1
        if ident in used:raise ValueError('旧人物配置对应到重复行，未写入：'+str(ident))
        used.add(ident);result.append(row)
    if moved:
        owner.mod_warnings.append(f'已按人物编号及候选序号重新对应 {moved} 条旧人物配置；保存后应用，不沿用旧行号')
        owner.rebased_role_rows=result
    if restored:
        owner.restored_native_role_ids=restored-used
        owner.mod_warnings.append(f'已核实并修复旧行号曾覆盖的 {len(restored)} 条原生人物记录；保留无关人物配置')
    if collapsed:owner.mod_warnings.append(f'已合并旧版行号错位造成的 {collapsed} 条重复候选；独立新增人物候选保留')
    return result

def remember(owner,name,rows,native,client):
    """A retained JSON is not proof that the native game still has the edit."""
    if name in ('Story','Task','TaskEdge','TaskEvent','Behavior','NpcEvolute'):return
    from codec import decode
    from engine import SCHEMAS
    defaults=decode(b'',name,SCHEMAS)
    for row in rows:
        row=copy.deepcopy(row)
        if name=='Language' and 'Text' in row:row['Ch_Text']=row.pop('Text')
        ident=row['BaseID']
        def equal(other):
            return other is not None and all(other.get(k,defaults.get(k))==v for k,v in row.items())
        if equal(native.get(ident)) and equal(client.get(ident)):continue
        pending=getattr(owner,'editor_recovery',{})
        owner.editor_recovery=pending
        pending.setdefault(name,{})[ident]=row

def finish(owner):
    # All overlay paths have now been read; a later-sorting MOD must remain
    # protected just as an earlier-sorting one is.
    for name,rows in getattr(owner,'editor_recovery',{}).items():
        for ident,row in rows.items():
            if owner.overrides[name].get(ident):
                owner.mod_warnings.append('恢复编辑记录时保留外部覆盖：'+name+' '+str(ident));continue
            owner.changes[name][ident]=row

def json_rows(owner,name,old_rows):
    if name=='Role' and hasattr(owner,'rebased_role_rows'):
        return owner.rebased_role_rows
    return old_rows

def keep_owned(owner,name,ident):
    return name!='Role' or ident not in getattr(owner,'restored_native_role_ids',set())
