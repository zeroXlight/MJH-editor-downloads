"""Insert a test manual into the ordinary-item map, preserving all other records."""
import struct
from engine import Save, u32

def inventory(save):
    b=save.data
    if len(save.tables)!=1:raise ValueError('存在多个装备表，无法确认普通物品表的位置')
    end=save.tables[0][0];valid=[]
    for p in range(19036,end,4):
        n=u32(b,p)
        if n<1 or p+4+n*40!=end:continue
        previous=0;records=[]
        for i in range(n):
            off=p+4+i*40;ident=u32(b,off+16);owner=u32(b,off+20);typ=u32(b,off+24);num=u32(b,off+28)
            if b[off:off+16]!=bytes(16) or ident<=previous or not typ or not 0<num<=0x7fffffff:break
            ot=b[off+36];script=b[off+37]
            if ot not in (0,1,2,3,9) or script>100 or (ot==0)!=(owner==0):break
            records.append({'offset':off,'id':ident,'owner':owner,'type':typ,'num':num,'owner_type':ot,'script':script});previous=ident
        if len(records)==n:valid.append((p,records))
    if not valid:raise ValueError('未识别完整普通物品表，未修改存档')
    # Reject interior count-like values in item flags: the real map contains
    # all validated suffix candidates and therefore has the earliest start.
    return min(valid,key=lambda pair:pair[0])

def counter_offset(save,maxid):
    b=save.data;candidates=set()
    # Counter maps precede the variable-length save maps. The supplied save
    # has its complete counter table at 18428, below the old scan threshold.
    # Identify the whole sorted 24-byte map, never an isolated key/value pair.
    for p in range(0,len(b)-28,4):
        n=u32(b,p);q=p+4
        if not 8<=n<=100 or q+n*24>len(b):continue
        prev=-1;item=None
        for i in range(n):
            off=q+i*24;key=u32(b,off+16)
            if b[off:off+16]!=bytes(16) or not prev<key<100:break
            if key==7:item=off+20
            prev=key
        else:
            # A stale counter is recoverable once its structural identity is
            # proven. Its value is not evidence for choosing a table.
            # Nested suffix candidates pointing at the same slot are one slot.
            if item is not None:candidates.add(item)
    if len(candidates)!=1:raise ValueError('无法唯一确认物品编号计数器，未修改存档')
    return next(iter(candidates))

def next_item_id(counter,used):
    """Append above both the counter and all retained item/equipment IDs."""
    ident=max(counter,max(used,default=0))+1
    while ident in used:ident+=1
    if not 0<ident<=0x7fffffff:raise ValueError('物品实例编号已超出支持范围，未修改存档')
    return ident

def generate_book(save,book_id,quantity=1):
    catalog=save.catalog;item=catalog.items.get(book_id)
    if not item or item.get('ItemType')!=15 or 2 not in item.get('Feature',[]):raise ValueError('此武学没有可用秘籍，请先启用秘籍')
    if not 1<=quantity<=min(99,item.get('MaxNum',99) or 99):raise ValueError('测试秘籍数量超出范围')
    p,records=inventory(save);b=save.data
    warehouse=[r for r in records if r['owner_type']==2 and r['script']==0]
    equipment=[r for r in save.records if save.location(r)=='周目仓库']
    # Stack only a matching warehouse item; never touch a role's book stack.
    stack=next((r for r in warehouse if r['type']==book_id and r['num']+quantity<=(item.get('MaxNum',99) or 99)),None)
    used={r['id'] for r in records}|{r['id'] for r in save.records}
    counter=None
    if stack:
        out=bytearray(b);struct.pack_into('<I',out,stack['offset']+28,stack['num']+quantity);ident=stack['id']
    else:
        if len(warehouse)+len(equipment)>=5000:raise ValueError('周目仓库已满')
        counter=counter_offset(save,max(used,default=0))
        ident=next_item_id(u32(b,counter),used)
        # End-of-run saves may have no current protagonist. Warehouse owners
        # are provenance in that state; reuse an existing valid warehouse owner.
        owner=save.main_role or next((r['owner'] for r in warehouse+equipment if r['owner']>0),0)
        if not owner:raise ValueError('存档无当前主角或可复用的仓库归属，无法生成有效秘籍；未修改存档')
        record=bytearray(40)
        struct.pack_into('<4I',record,16,ident,owner,book_id,quantity)
        record[36]=2;record[37]=0
        out=bytearray(b);struct.pack_into('<I',out,counter,ident);struct.pack_into('<I',out,p,len(records)+1)
        end=p+4+len(records)*40;out[end:end]=record
    result=bytes(out);check=Save(save.path,catalog,result);_,after=inventory(check)
    matches=[r for r in after if r['id']==ident]
    if len(matches)!=1 or (not stack and (ident in used or any(r['id']==ident for r in check.records))):
        raise ValueError('新秘籍实例编号重复，未修改存档')
    generated=matches[0]
    if generated['type']!=book_id or generated['owner_type']!=2 or generated['script']!=0 or generated['num']!=(stack['num']+quantity if stack else quantity):raise ValueError('秘籍写入回读验证失败')
    if [(r['id'],result[r['offset']:r['offset']+96]) for r in check.records]!=[(r['id'],b[r['offset']:r['offset']+96]) for r in save.records]:raise ValueError('秘籍生成影响了装备记录')
    for record in records:
        if stack and record['id']==stack['id']:continue
        original=b[record['offset']:record['offset']+40]
        new=next(r for r in after if r['id']==record['id'])
        if result[new['offset']:new['offset']+40]!=original:raise ValueError('秘籍生成影响了其他物品')
    if not stack:
        end=p+4+len(records)*40
        # The counter may lie on either side of the inserted item map.
        # Compare against the exact expected counter/count edits and insertion.
        expected=bytearray(b);struct.pack_into('<I',expected,counter,ident);struct.pack_into('<I',expected,p,len(records)+1)
        if result[:end]!=expected[:end] or result[end+40:]!=expected[end:]:raise ValueError('存档其他数据发生变化')
        moved_counter=counter+40 if counter>=end else counter
        if u32(result,moved_counter)!=ident:raise ValueError('物品计数器回读验证失败')
    return result,ident
