"""Synchronize validated runtime data registries; never rewrite foreign code."""
import hashlib,struct

def remap_pool(body,mapping):
    if len(body)!=8192:raise ValueError('残章池布局不兼容')
    code=bytearray(body[:1930]);code[0x600:0x608]=bytes(8)
    if hashlib.sha256(code).hexdigest()!='c53ca285950badf963b785b06ac26032b5a278d05baa4e1a57b1e6d02397dae7':raise ValueError('残章池代码不匹配')
    rate,count=struct.unpack_from('<II',body,0x600)
    if rate>100 or not 1<=count<=768:raise ValueError('残章池参数损坏')
    result=bytearray(body);seen=set()
    for i in range(count):
        item,mid=struct.unpack_from('<II',body,0x800+i*8)
        if not item or not mid or item in seen:raise ValueError('残章池编号不兼容')
        seen.add(item)
        if mid in mapping:struct.pack_into('<I',result,0x804+i*8,mapping[mid])
    return bytes(result)

def remap(raw,mapping,notes):
    from external_runtime import detach,reattach,certify_parent
    import pefile
    try:parent,options=detach(raw)
    except ValueError:
        pe=pefile.PE(data=raw,fast_load=True)
        if any(s.Name.rstrip(b'\0')==b'.mjhgr' for s in pe.sections):raise
        parent=raw;options=None
    pe=pefile.PE(data=parent,fast_load=True);changed=bytearray(parent)
    for section in pe.sections:
        if section.Name.rstrip(b'\0')!=b'.dyfrag':continue
        try:body=remap_pool(section.get_data(),mapping)
        except ValueError as error:
            notes.append('外部残章池已跳过同步：'+str(error));continue
        start=section.PointerToRawData;changed[start:start+len(body)]=body
    parent=bytes(changed)
    if options:
        for area in options['areas']:
            for key in ('source','target'):area[key]=mapping.get(area[key],area[key])
        certify_parent(parent);result=reattach(parent,options)
        restored,actual=detach(result)
        if restored!=parent or actual!=options:raise ValueError('运行库编号迁移回读失败')
        return result
    return parent
