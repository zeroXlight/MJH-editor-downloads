"""Only mobile card characters and player-created roles enter the visible list."""
import base64,hashlib,json,zlib
from pathlib import Path
def roster(store):
 from engine import DATA_ROOT
 from martial_editor import indexed_rows
 from codec import fields
 doc=json.loads((DATA_ROOT/'ui_assets/role_breakthrough_mobile_roster.json').read_text('utf8'))
 pack=json.loads((DATA_ROOT/'role_breakthrough_pack.json').read_text('utf8'))
 mobile=set(pack['visible_role_ids'])
 baseline=json.loads((DATA_ROOT/'bigmap_role_baseline.json').read_text('utf8'))
 raw=zlib.decompress(base64.b64decode(baseline['data']))
 if hashlib.sha256(raw).hexdigest()!=baseline['table_sha256']:raise ValueError('人物原版基线校验失败')
 native={next(f.value for f in fields(row) if f.number==2 and f.wire==0) for row in indexed_rows(raw)[0].values()}
 # This is the editor's existing allocation range, also used on future saves.
 if any(rid>=1700000000 for rid in native):raise ValueError('人物自建编号范围与认证原版冲突')
 rows=store.table('Role');present={row.get('RoleID',0) for row in rows.values()}
 saved=store.read(store.root/'装备编辑器配置/人物编辑.json')
 meta=json.loads(saved) if saved else {}
 custom={int(k) for k in meta if str(k).isdigit() and int(k) not in native and int(k) in present}
 custom|={row['RoleID'] for row in rows.values() if row.get('RoleID',0)>=1700000000 and row.get('BaseID',0)>=1600000000}
 lua='local mjhMobileRoster={'+','.join('['+str(i)+']=true' for i in sorted(mobile))+'}\n'
 lua+='local mjhSavedCustom={'+','.join('['+str(i)+']=true' for i in sorted(custom))+'}\n'
 return lua,dict(mobile_source_count=len(doc['role_ids']),mobile_present=len(mobile&present),custom_present=len(custom),custom_ids=sorted(custom))
