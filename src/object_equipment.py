"""Create one imported equipment instance in the selected save's warehouse."""
import copy,struct
from engine import Save,u32

def generate(save,item_id,item,draft):
    if len(save.tables)!=1:raise ValueError('此存档存在多个装备表，不能确认插入位置')
    templates=[r for r in save.records if r['editable'] and r['owner_type']==2 and r['script']==0]
    if not templates:raise ValueError('所选存档没有可验证的周目仓库装备记录，未写入')
    raw=save.data;slots=set()
    for p in range(0,len(raw)-28,4):
        n=u32(raw,p)
        if not 8<=n<=100 or p+4+n*24>len(raw):continue
        previous=-1;counter=None
        for i in range(n):
            o=p+4+i*24;k=u32(raw,o+16)
            if raw[o:o+16]!=bytes(16) or not previous<k<100:break
            if k==10:counter=o+20
            previous=k
        else:
            if counter is not None:slots.add(counter)
    if len(slots)!=1:raise ValueError('装备实例编号分配表无法唯一验证')
    counter=next(iter(slots));ident=max(u32(raw,counter),max(r['id'] for r in save.records))+1
    if ident>=2147483647:raise ValueError('装备实例编号超限')
    template=templates[0];record=bytearray(raw[template['offset']:template['offset']+96])
    struct.pack_into('<I',record,16,ident);struct.pack_into('<I',record,24,item_id);record[32]=0;record[35]=0;record[36]=0
    record[40:84]=bytes(44)
    out=bytearray(raw);p,n=save.tables[0];struct.pack_into('<I',out,p,n+1);struct.pack_into('<I',out,counter,ident)
    end=p+4+n*96;out[end:end]=record
    catalog=copy.copy(save.catalog);catalog.items=dict(catalog.items);catalog.items[item_id]=item
    staged=Save(save.path,catalog,bytes(out));added=next(r for r in staged.records if r['id']==ident)
    result=staged.patched({added['offset']:draft})
    check=Save(save.path,catalog,result)
    if check.draft(next(r for r in check.records if r['id']==ident))!=draft:raise ValueError('导入装备词条回读失败')
    if result[end+96:]!=raw[end:]:raise ValueError('存档后续记录发生非预期变化')
    return result,ident
