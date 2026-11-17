"""Read/write checks for the supplied blank-name save, without a real game write."""
from pathlib import Path
import sys,json,hashlib,struct,copy

def checks(raw,catalog,path):
 from engine import Save
 from feature_save import NativeSave,patch_save
 from save_format import table_spans,validate_reader_header
 from meridian_resource import balance
 assert raw[:64]==bytes(64)
 n=NativeSave(raw);assert n.header_kind=='blank' and n.bytes()==raw
 save=Save(path,catalog,raw);assert save.header_kind=='blank' and len(save.records)==583 and all(r['editable'] for r in save.records)
 assert save.patched({})==raw
 row=next(r for r in save.records if r['owner']==save.main_role and r['grade']<20)
 draft=copy.deepcopy(save.draft(row));draft['grade']+=1
 edited=save.patched({row['offset']:draft});changed=[i for i,(a,b) in enumerate(zip(raw,edited)) if a!=b]
 assert changed==[row['offset']+32] and edited[:760]==raw[:760]
 reread=Save(path,catalog,edited);assert reread.draft(next(r for r in reread.records if r['id']==row['id']))==draft
 incremented=patch_save(raw,'meridian_exp',{},[])
 assert incremented[:760]==raw[:760] and balance(NativeSave(incremented))==balance(n)+900000
 named=bytearray(raw);named[16:23]=b'Robot 2';assert NativeSave(named).bytes()==named
 named_save=Save(path,catalog,named);assert named_save.records==save.records
 assert named_save.patched({row['offset']:draft})[760:]==edited[760:]
 _,spans=table_spans(raw);bad_count=bytearray(raw);struct.pack_into('<I',bad_count,760,0xffffffff)
 bad_prefix=bytearray(raw);bad_prefix[spans[24][1]]=1
 duplicate=bytearray(raw);struct.pack_into('<I',duplicate,spans[24][1]+96+16,struct.unpack_from('<I',raw,spans[24][1]+16)[0])
 unknown=bytearray(raw);unknown[16:23]=b'Unknown'
 corrupt=[('截断',raw[:-1]),('表越界',bad_count),('异常记录前缀',bad_prefix),('重复装备编号',duplicate),('未知文件头',unknown),('额外尾部',raw+b'\0'),('伪全零文件',bytes(len(raw)))]
 rejected=[]
 for name,data in corrupt:
  try:validate_reader_header(data)
  except ValueError as e:rejected.append(dict(case=name,error=str(e)))
  else:raise AssertionError('Bad save accepted: '+name)
 from change_log import equipment_changes
 catalog.root=path.parent
 recipes,logs=equipment_changes(path.parent,{path:edited},{path:raw},catalog)
 assert len(recipes)==1 and recipes[0]['fields']['grade']==draft['grade']
 return dict(passed=True,original_sha256=hashlib.sha256(raw).hexdigest(),header_kind='blank',tables=62,equipment_count=len(save.records),no_op_exact=True,
  equipment_change_offsets=changed,equipment_id=row['id'],equipment_grade=draft['grade'],header_all_760_bytes_preserved=True,other_bytes_preserved=True,
  meridian_delta=900000,named_save_same_behavior=True,change_log_recipe_preserved=True,corrupt_rejected=rejected),edited,incremented

def run():
 from edition import VERSION,EDITION_NAME
 from review_edition import output
 from object_bundle import Store
 from types import SimpleNamespace
 root=Path(sys.argv[sys.argv.index('--game')+1]).resolve()
 path=root/'SaveFile/blank_header/Save.sav';raw=path.read_bytes()
 store=Store(root);items=store.table('Item');catalog=SimpleNamespace(items=items,is_equipment=lambda i:1 in items.get(i,{}).get('Feature',[]),supported=True)
 report,_,_=checks(raw,catalog,path)
 report.update(version=VERSION,edition=EDITION_NAME,frozen=bool(getattr(sys,'frozen',False)),game_unchanged=path.read_bytes()==raw)
 (output()/'空名称存档冻结验收.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
