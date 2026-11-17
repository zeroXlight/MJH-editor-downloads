"""Recognize the certified native layout without rewriting optional name bytes."""
import struct

STRIDES=(8832,24,32,32,32,24,56,40,128,24,32,32,104,848,32,32,72,24,24,40,72,608,288,40,96,56,624,48,56,40,64,32,40,32,32,360,136,312,56,72,48,40,40,32,32,24,40,32,32,32,32,672,384,184,48,48,40,96,48,184,800,40)

def header_kind(data):
    if len(data)<1008:raise ValueError(f'存档文件过短：{len(data)}字节，缺少完整原生头与表计数；未修改文件')
    if data[16:23]==b'Robot 2':return 'named'
    if data[:64]==bytes(64):return 'blank'
    raise ValueError('存档头无法识别：既不是Robot 2，也不是已验证的空名称头；可能为其他版本或头部损坏，未修改文件')

def table_spans(data):
    kind=header_kind(data)
    if len(data)>100*1024*1024:raise ValueError('存档超过已支持的100MiB范围，未修改文件')
    p=760;spans=[]
    for i,stride in enumerate(STRIDES):
        if p+4>len(data):raise ValueError(f'存档表{i}计数被截断（偏移0x{p:x}）；未修改文件')
        n=struct.unpack_from('<I',data,p)[0];start=p+4;end=start+n*stride
        if end>len(data):raise ValueError(f'存档表{i}越界：{n}条×{stride}字节，需要到0x{end:x}，文件仅0x{len(data):x}；可能截断或版本布局不兼容，未修改文件')
        spans.append((p,start,end,n,stride));p=end
    if p!=len(data):raise ValueError(f'存档尾部多出{len(data)-p}字节，布局尚未识别；未修改文件')
    if kind=='blank':
        # A blank string is not itself proof of a save. Certify all map bounds,
        # object prefixes and keys, including maps whose valid native key is 0.
        if not spans[0][3] or not spans[1][3]:raise ValueError('空名称存档缺少剧本或编号分配表；未修改文件')
        for i,(_,start,end,count,stride) in enumerate(spans):
            previous=-1;seen=set()
            for off in range(start,end,stride):
                key=struct.unpack_from('<I',data,off+16)[0]
                if any(data[off:off+16]) or key in seen or (not key and i not in (6,8)) or (i!=61 and key<=previous):
                    raise ValueError(f'空名称存档表{i}记录结构不兼容（偏移0x{off:x}、编号{key}）；未修改文件')
                seen.add(key);previous=key
    return kind,spans

def validate_reader_header(data):
    """Keep legacy named-layout fallbacks; blank names require complete proof."""
    kind=header_kind(data)
    if kind=='blank':table_spans(data)
    return kind
