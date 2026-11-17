"""Transactional native card progression tables; retained PC effects stay native."""
from pathlib import Path
import copy,json
from codec import fields,encoded,numeric_list
from martial_editor import indexed_rows,patch_table,lua_value
OWNED_TREE=('RoleTypeID','GiftIDs','AllGiftIDs')

def _check_first(name,ident,row,pack):
 if name=='RoleCard':
  if row is not None:raise ValueError('角色突破成长编号已被占用：'+str(ident))
  return
 expected=pack['tree_baseline'].get(str(ident))
 if expected is None:
  if row is not None:raise ValueError('角色突破天赋树编号已被占用：'+str(ident))
 elif row is None or any(row.get(k,[])!=expected.get(k,[]) for k in OWNED_TREE):
  raise ValueError('角色突破天赋树与已认证PC基线不同：'+str(ident))

def _remove(raw,ids):
 rows,index=indexed_rows(raw);keep={i:r for i,r in rows.items() if i not in ids};wanted=[i for i in index if i not in ids]
 out=bytearray();written=False
 for f in fields(raw):
  if f.number in (1,2):
   if not written:
    out.extend(numeric_list(1,wanted))
    for i in wanted+[i for i in keep if i not in wanted]:out.extend(encoded(2,keep[i],2))
    written=True
  else:out.extend(f.raw)
 return bytes(out)

def prepare(store,enabled,prior,payloads):
 from engine import DATA_ROOT
 pack=json.loads((DATA_ROOT/'role_breakthrough_pack.json').read_text('utf8'))
 prior=prior or {};installed=bool(prior)
 if not enabled and not installed:return {},{},pack,{}
 rows={name:{int(i):r for i,r in pack[name].items()} for name in ('RoleCard','RoleWishTree')}
 if any(r.get('EffectEnum')==2 for r in rows['RoleCard'].values()) or pack.get('Item'):
  raise ValueError('本轮专属武器恢复已暂缓，资源包不应含装备升级')
 receipt=copy.deepcopy(prior);receipt.setdefault('files',{})
 from codec import decode
 from engine import SCHEMAS
 if enabled:
  gifts=store.table('Gift')
  for ident,expected in pack['gift_identity'].items():
   actual=gifts.get(int(ident))
   if actual is None or any(actual.get(k)!=v for k,v in expected.items()):raise ValueError('角色突破天赋身份冲突：'+ident)
 blobs={}
 for name in rows:
  active=enabled
  sources=[]
  for folder in ('TableData','DreamRivakes_Data/StreamingAssets'):
   path=store.root/folder/(name+'.bytes');raw=store.read(path)
   if raw is not None:sources.append((path.relative_to(store.root).as_posix(),raw,path))
  if name in store.assets.scripts:
   _,at,size=store.assets.scripts[name]
   sources.append(('@resources/'+name,store.assets.data[at+4:at+4+size],None))
  for key,raw,path in sources:
   entry=receipt['files'].setdefault(key,{})
   current=indexed_rows(raw)[0];wanted=rows[name] if active else {}
   for ident,data in entry.items():
    actual=current.get(int(ident));expected=data.get('after')
    if actual!=(bytes.fromhex(expected) if expected is not None else None):
     # Steam can replace an embedded table while preserving both the separate
     # table and the editor's receipt. Accept only an exact recorded preimage
     # AND a postimage reproduced from the immutable shipped progression pack.
     before=bytes.fromhex(data['before']) if data.get('before') is not None else None
     recipe=rows[name].get(int(ident))
     from martial_editor import encode_field
     from codec import patch
     replacements={SCHEMAS[name][k]['number']:encode_field(k,v,name) for k,v in (recipe or {}).items() if k in SCHEMAS[name]}
     replacements[1]=encoded(1,int(ident))
     known_after=patch(before or b'',replacements) if recipe else None
     if actual!=before or expected is None or known_after!=bytes.fromhex(expected):
      raise ValueError('角色突破成长配置被外部修改：'+name+' '+ident)
   remove={int(i) for i,e in entry.items() if int(i) not in wanted and e.get('before') is None}
   staged=_remove(raw,remove) if remove else raw
   restore={int(i):bytes.fromhex(e['before']) for i,e in entry.items() if int(i) not in wanted and e.get('before') is not None}
   if restore:
    kept,idx=indexed_rows(staged);kept.update(restore);out=bytearray();done=False
    for f in fields(staged):
     if f.number in (1,2):
      if not done:
       out.extend(numeric_list(1,idx))
       for i in idx+[i for i in kept if i not in idx]:out.extend(encoded(2,kept[i],2))
       done=True
     else:out.extend(f.raw)
    staged=bytes(out)
   for ident in wanted:
    token=str(ident)
    if token not in entry:
     _check_first(name,ident,decode(current[ident],name,SCHEMAS) if ident in current else None,pack)
     entry[token]={'before':current[ident].hex() if ident in current else None}
   if wanted:staged=patch_table(staged,name,wanted)
   after=indexed_rows(staged)[0]
   for ident,e in entry.items():e['after']=after[int(ident)].hex() if int(ident) in after else None
   if staged!=raw:
    if path is None:blobs[name]=staged
    else:payloads[path]=staged
 # A later MOD JSON load can otherwise silently undo the native/Lua update.
 # Preserve all other fields; restore only the fields owned by this feature.
 directory=store.root/'ModProject/GameProject/Mod_MJH/Json'
 receipt.setdefault('mod_files',{})
 for name,desired in rows.items():
  for path in sorted(directory.glob(name+'_*.json')):
   raw=store.read(path)
   try:doc=json.loads(raw.decode('utf-8-sig'))
   except (ValueError,UnicodeError):raise ValueError('无法核对角色突破相关MOD文件：'+path.name)
   if not isinstance(doc,dict) or not isinstance(doc.get('Items'),list):raise ValueError('角色突破相关MOD格式无效：'+path.name)
   key=path.relative_to(store.root).as_posix();old=receipt['mod_files'].get(key,{})
   entries={};changed=False
   for row in doc['Items']:
    if not isinstance(row,dict):raise ValueError('角色突破相关MOD记录无效：'+path.name)
    ident=row.get('BaseID');token=str(ident)
    if ident not in desired and token not in old:continue
    if token in entries:raise ValueError('角色突破相关MOD编号重复：'+path.name+' '+token)
    fields_owned=tuple(desired[ident]) if name=='RoleCard' and ident in desired else OWNED_TREE
    before={k:copy.deepcopy(row[k]) for k in fields_owned if k in row}
    if token in old:
     e=old[token]
     if before!=e['after']:raise ValueError('角色突破相关MOD被外部修改：'+path.name+' '+token)
    else:
     _check_first(name,ident,row,pack);e={'before':before}
    target={k:copy.deepcopy(desired[ident][k]) for k in fields_owned if k in desired[ident]} if enabled else e['before']
    for k in fields_owned:row.pop(k,None)
    row.update(target);changed|=before!=target;e['after']=target;entries[token]=e
   if entries:receipt['mod_files'][key]=entries
   if changed:payloads[path]=(json.dumps(doc,ensure_ascii=False,indent=2)+'\n').encode('utf8')
 # Validate the original Lua rows independently, before appending our override.
 if enabled and not installed:
  from client_config import lua_rows
  current=lua_rows(store.assets.script('RoleWishTree.lua'),'RoleWishTree',store.enums)
  for ident in rows['RoleWishTree']:_check_first('RoleWishTree',ident,current.get(ident),pack)
  from role_breakthrough import BEGIN
  text=store.assets.script('RoleCard.lua')
  if BEGIN not in text and __import__('re').search(r'\[\d+\]\s*=',text):
   current=lua_rows(text,'RoleCard',store.enums)
   for ident in rows['RoleCard']:_check_first('RoleCard',ident,current.get(ident),pack)
 bodies={}
 for name,wanted in rows.items():
  if not enabled:continue
  text='local mjhProgressionRows={\n'+''.join('  ['+str(i)+']='+lua_value(r)+',\n' for i,r in sorted(wanted.items()))+'}\n'
  text+='for id,row in pairs(mjhProgressionRows) do '+name+'[id]=row end\n'
  bodies[name+'.lua']=text
 receipt['enabled']=bool(enabled)
 receipt['source_apk_sha256']=pack['source_apk_sha256']
 return bodies,receipt,pack,blobs
