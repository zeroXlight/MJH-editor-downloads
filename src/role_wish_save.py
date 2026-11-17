"""Backfill real native wish-instance records, preserving existing progress and all suffix bytes."""
import struct
from pathlib import Path
from dataclasses import dataclass
ZERO=bytes(16)
RECORD_BYTES=40
COUNTER_BYTES=24

def u32(raw,p):return struct.unpack_from('<I',raw,p)[0]

@dataclass
class Layout:
 counter:int
 maximum:int
 offset:int
 count:int
 script:int
 seed:bytes
 records:list
 role_max:int

def inspect(raw,lib):
 counters=[]
 for p in range(128,len(raw)-120,4):
  n=u32(raw,p)
  if not 5<=n<=64 or p+4+n*COUNTER_BYTES>len(raw):continue
  entries={};keys=[]
  for k in range(n):
   q=p+4+k*COUNTER_BYTES;key=u32(raw,q+16)
   if raw[q:q+16]!=ZERO or not 1<=key<=64:break
   keys.append(key);entries[key]=(q+20,u32(raw,q+20))
  else:
   if keys==sorted(set(keys)) and all(i in entries for i in [6,9,10,12,20]):counters.append((p+4+n*COUNTER_BYTES,entries))
 if len(counters)!=1:raise ValueError('无法验证唯一的存档编号分配表，未修改心愿')
 start,entries=counters[0];counter,maximum=entries[12];candidates=[]
 for p in range(start,len(raw)-RECORD_BYTES,4):
  n=u32(raw,p)
  if not 1<=n<=maximum or p+4+n*RECORD_BYTES>len(raw):continue
  if raw[p+4:p+20]!=ZERO:continue
  end=p+4+(n-1)*RECORD_BYTES
  if raw[end:end+16]!=ZERO or u32(raw,end+16)>maximum:continue
  records=[];prior=0;scripts=set();seed=None
  for k in range(n):
   q=p+4+k*RECORD_BYTES;record=raw[q:q+RECORD_BYTES]
   uid,role,wish,reward,flags,plat=struct.unpack_from('<6I',record,16)
   script=(flags>>8)&255;state=flags&255
   if record[:16]!=ZERO or not prior<uid<=maximum or wish not in lib.tables['RoleWishQuest'] or role not in lib.roles or state not in [1,2,3] or flags>>16 or plat!=0:break
   records.append((uid,role,wish,flags,record));prior=uid
   if script:scripts.add(script)
  else:
   if len(scripts)!=1:continue
   script=next(iter(scripts))
   # Copy the complete real current-story pristine generic wish; do not fabricate packed flags.
   for uid,role,wish,flags,record in records:
    if wish==190 and flags==(script<<8|1) and u32(record,28)==0:seed=record;break
   if seed is not None:candidates.append(Layout(counter,maximum,p,n,script,seed,records,entries[6][1]))
 if len(candidates)!=1:raise ValueError('无法验证唯一的原生心愿实例表及未完成通用心愿，未修改存档')
 return candidates[0]

def present(raw,rid,maximum):
 # Native role records have a zero 16-byte serialization header, UID and role type.
 needle=struct.pack('<I',rid);p=0
 while True:
  p=raw.find(needle,p)
  if p<0:return False
  if p>=20 and raw[p-20:p-4]==ZERO and 0<u32(raw,p-4)<=maximum:return True
  p+=1

def fill(raw,lib,selected=None):
 chosen=set(selected) if selected is not None else {int(i) for i in lib.meta if int(i)>=1700000000}
 chosen={rid for rid in chosen if rid in lib.roles and rid>=1700000000 and str(rid) in lib.meta}
 if not any(present(raw,rid,2147483647) for rid in chosen):return raw,[]
 layout=inspect(raw,lib)
 new=[];maximum=layout.maximum;report=[];migrations=[];aliases=[]
 for rid in sorted(chosen):
  if rid not in lib.roles or rid<1700000000 or str(rid) not in lib.meta:continue
  if not present(raw,rid,layout.role_max):continue
  existing={wish for uid,role,wish,flags,record in layout.records if role==rid and (flags>>8)&255==layout.script}
  from role_common_wishes import equivalent
  if 190 not in existing:
   for index,(uid,role,wish,flags,record) in enumerate(layout.records):
    if role==rid and wish!=190 and (flags>>8)&255==layout.script and equivalent(lib,wish,190):
     aliases.append((index,uid,rid,190));existing.add(190)
     report.append({'role':rid,'wish':190,'instance':uid,'action':'normalize'})
     break
  # Preserve the existing UID and unfinished state while repairing the inert legacy entry.
  if 195 not in existing and 195 in lib.row(rid).get('WishQuestID',[]):
   for index,(uid,role,wish,flags,record) in enumerate(layout.records):
    if role==rid and equivalent(lib,wish,203) and flags==(layout.script<<8|1) and u32(record,28)==0:
     migrations.append((index,uid,rid));existing.add(195)
     report.append({'role':rid,'wish':195,'instance':uid,'action':'repair'})
     break
  for wish in [195,190]:
   if wish in existing:continue
   if wish not in lib.row(rid).get('WishQuestID',[]):raise ValueError('请先保存人物通用心愿配置')
   maximum+=1
   if maximum>=2147483000:raise ValueError('心愿实例编号已用完，未修改')
   record=bytearray(layout.seed)
   for off,value in [(16,maximum),(20,rid),(24,wish)]:struct.pack_into('<I',record,off,value)
   new.append(bytes(record));report.append({'role':rid,'wish':wish,'instance':maximum})
 if not new and not migrations and not aliases:return raw,[]
 out=bytearray(raw);struct.pack_into('<I',out,layout.counter,maximum);struct.pack_into('<I',out,layout.offset,layout.count+len(new))
 insertion=layout.offset+4+layout.count*RECORD_BYTES
 for index,uid,rid in migrations:struct.pack_into('<I',out,layout.offset+4+index*RECORD_BYTES+24,195)
 for index,uid,rid,wish in aliases:struct.pack_into('<I',out,layout.offset+4+index*RECORD_BYTES+24,wish)
 out[insertion:insertion]=b''.join(new);out=bytes(out)
 check=inspect(out,lib)
 assert check.maximum==maximum and check.count==layout.count+len(new)
 assert out[insertion+len(new)*RECORD_BYTES:]==raw[insertion:]
 expected=[bytearray(r[4]) for r in layout.records]
 for index,uid,rid in migrations:struct.pack_into('<I',expected[index],24,195)
 for index,uid,rid,wish in aliases:struct.pack_into('<I',expected[index],24,wish)
 assert [r[4] for r in check.records[:layout.count]]==[bytes(r) for r in expected]
 return out,report

def plan(lib,path,selected=None):
 path=Path(path).resolve();raw=path.read_bytes();data=raw;report=[]
 try:
  with lib.edit():
   from role_traits import safe_wishes
   safe_wishes(lib)
   data,report=fill(raw,lib,selected)
   from role_wish_tasks import fill as fill_tasks
   data,tasks=fill_tasks(data,lib,selected)
   for record in tasks:report.append({**record,'wish':195,'action':'initialize'})
 except (ValueError,KeyError) as error:
  from mod_compatibility import note
  note(lib,'所选存档的自动心愿修复已跳过：'+str(error));data=raw;report=[]
 payloads,originals=lib.plan();originals[path]=raw
 if report:payloads[path]=data
 return payloads,originals,report
