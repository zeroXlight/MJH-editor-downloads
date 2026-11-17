# Generated for the exact certified big-map native build. See native mapping evidence.
"""Independent recognition of the released pet account support image.

Used by the external Shadow tool. It contains no installer or editor feature.
"""
import hashlib,json,struct
MAGIC=b'MJHPET213\0'
META=b'MJHPETMETA213\0'
CODE_SHA='f4ef85233bb9f1183bb447ddeab6c8cbf0217ef89849ce196826d549f818e88c'

def original(raw):
    from shadow_bigmap import repair_legacy_client
    raw=repair_legacy_client(raw)
    from role_breakthrough_client import detach
    raw,_=detach(raw)
    import pefile
    pe=pefile.PE(data=raw,fast_load=True)
    sections=[s for s in pe.sections if s.Name.rstrip(b'\0')==b'.mjhpet']
    if not sections:return raw
    if len(sections)!=1 or sections[0]!=pe.sections[-1]:raise ValueError('宠物支持节位置异常')
    sec=sections[0];data=sec.get_data();at=data.find(META)
    if at<0 or not data.startswith(MAGIC) or hashlib.sha256(data[:at]).hexdigest()!=CODE_SHA:
        raise ValueError('宠物支持代码不是已验证版本')
    n=struct.unpack_from('<I',data,at+len(META))[0];end=at+len(META)+4+n
    if end>len(data) or any(data[end:]):raise ValueError('宠物支持节边界异常')
    doc=json.loads(data[at+len(META)+4:end]);length=doc['length']
    if type(length)is not int or length!=sec.PointerToRawData:raise ValueError('宠物运行库父文件长度异常')
    parent=bytearray(raw[:length]);offsets=[]
    for offset,value in doc['undo']:
        value=bytes.fromhex(value)
        if type(offset)is not int or offset<0 or offset+len(value)>length:raise ValueError('宠物支持恢复范围异常')
        offsets.append((offset,len(value)));parent[offset:offset+len(value)]=value
    base=pefile.PE(data=bytes(parent),fast_load=True);optional=base.OPTIONAL_HEADER.get_file_offset()
    expected=[(base.get_offset_from_rva(rva),5) for rva in (0xc446df,0xc4470b,0xba1fa0)]
    expected+=[(base.FILE_HEADER.get_file_offset()+2,2),(base.sections[-1].get_file_offset()+40,40),
               (optional+4,4),(optional+56,4),(optional+64,4)]
    if offsets!=expected or hashlib.sha256(parent).hexdigest()!=doc['parent_sha256']:
        raise ValueError('宠物支持父文件校验失败')
    return bytes(parent)
