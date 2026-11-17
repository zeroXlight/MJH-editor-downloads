# Steam build 26650481 exact adapter; native_map250 and full parent SHA are required.
# November 5 exact-build adapter. Generated offline; see native_map24.json evidence.
# Generated for the exact certified big-map native build. See native mapping evidence.
"""Scoped recruitment support, installed through the existing reversible PE section.

NPC evolution and teammate construction use different initial martial rules.
Only explicitly edited fields take precedence during the first conversion.
Unedited roles, later training, equipment and plot state retain native behavior.
"""
import json, re, struct

MAGIC=b'MJHJOIN256\0'
# hook, native callee, instance-pointer stack offset, flag, result kind
HOOKS=((0x702e41,0x4682f0,0x110,1,'level'),
       (0x47c25a,0x5aa2e0,0x260,1,'empty'),
       (0x5aad28,0x2ab970,0x470,3,'evolution'))

def validate(rows):
    result=[]
    for rid,mask in rows:
        if type(rid) is not int or not 0<rid<2147483648 or type(mask) is not int or mask not in (1,2,3):
            raise ValueError('入队同步人物配置无效')
        result.append([rid,mask])
    if len({r[0] for r in result})!=len(result):raise ValueError('入队同步人物编号重复')
    return sorted(result)

def installed(raw,original):
    pos=raw.find(MAGIC,len(original))
    if pos<0:return []
    start=pos+len(MAGIC);size=struct.unpack_from('<I',raw,start)[0]
    return validate(json.loads(raw[start+4:start+4+size].decode('ascii')))

def desired(lib):
    result=[]
    for key,record in lib.meta.items():
        rid=int(key)
        if rid not in lib.roles:continue
        mask=record.get('recruitment_fields',0)
        # Upgrade previously saved edits using their before/after semantic data.
        before=record.get('before',{});after=lib.snapshot(rid,record['settings'])
        if before.get('武学')!=after['武学']:mask|=1
        if before.get('属性')!=after['属性']:mask|=2
        if record.get('template') is not None:mask|=3
        if mask:result.append([rid,mask])
    return validate(result)

def helper(rva,hook,target,stack,flag,kind,rows):
    code=bytearray();fixes=[];labels={}
    def emit(b):code.extend(b)
    def rel(op,dest):emit(op);emit(struct.pack('<i',dest-(rva+len(code)+4)))
    def branch(op,label):emit(op);fixes.append((len(code),label));emit(bytes(4))
    if kind=='evolution':
        # This getter is shared with other evolution-copy callers. Validate the
        # return address before accessing the outer recruitment frame.
        rel(b'\xe8',target)
        emit(b'\x41\x52') # preserve R10; RAX carries the native enum result
        emit(bytes.fromhex('4c 8b 94 24 10 02 00 00'))
        emit(b'\x41\x53')
        rel(bytes.fromhex('4c 8d 1d'),0x47c9c3)
        emit(bytes.fromhex('4d 39 da 41 5b'))
        branch(b'\x0f\x85','return_type')
        emit(b'\x83\xf8\x02');branch(b'\x0f\x84','attrs')
        emit(b'\x83\xf8\x0c');branch(b'\x0f\x85','return_type')
        labels['martials']=len(code)
        # Separate paths ensure editing attributes cannot discard martial gains.
        for label,bit in [('martials_check',1),('attrs',2)]:
            if label=='attrs':labels[label]=len(code)
            emit(b'\x4c\x8b\x94\x24'+struct.pack('<I',stack+8))
            emit(bytes.fromhex('45 8b 52 2c'))
            for rid,mask in rows:
                if mask&bit:
                    emit(b'\x41\x81\xfa'+struct.pack('<I',rid));branch(b'\x0f\x84','exclude')
            branch(b'\xe9','return_type')
        labels['exclude']=len(code)
        emit(b'\xb8\x04\x00\x00\x00') # NET_FRAGMENT is already excluded natively
        labels['return_type']=len(code);emit(bytes.fromhex('41 5a'))
        rel(b'\xe9',hook+5)
    else:
        emit(b'\x50')
        emit(b'\x48\x8b\x84\x24'+struct.pack('<I',stack+8))
        emit(bytes.fromhex('8b 40 2c'))
        for rid,mask in rows:
            if mask&flag:
                emit(b'\x3d'+struct.pack('<I',rid));branch(b'\x0f\x84','selected')
        emit(b'\x58');rel(b'\xe8',target);rel(b'\xe9',hook+5)
        labels['selected']=len(code);emit(b'\x58')
        emit(bytes.fromhex('48 89 c8') if kind=='level' else b'\x31\xc0')
        rel(b'\xe9',hook+5)
    for off,label in fixes:struct.pack_into('<i',code,off,labels[label]-off-4)
    return bytes(code)

def append_support(original,pe,rva,body,overwrite,rows):
    rows=validate(rows)
    if not rows:return
    data=json.dumps(rows,separators=(',',':')).encode('ascii')
    body.extend(MAGIC+struct.pack('<I',len(data))+data);body.extend(bytes(-len(body)%16))
    for hook,target,stack,flag,kind in HOOKS:
        offset=pe.get_offset_from_rva(hook)
        expected=b'\xe8'+struct.pack('<i',target-hook-5)
        if original[offset:offset+5]!=expected:
            raise ValueError('人物入队逻辑已被其他版本或 MOD 改写，未安装：'+hex(hook))
        entry=rva+len(body)
        body.extend(helper(entry,hook,target,stack,flag,kind,rows));body.extend(bytes(-len(body)%16))
        overwrite(offset,b'\xe9'+struct.pack('<i',entry-hook-5))

def plan(lib,payloads,originals):
    rows=desired(lib)
    if rows:
        # This resource's comments use GBK in some builds; enum tokens are ASCII.
        _,q,n=lib.assets.scripts['SePtlCommDefine.lua']
        definitions=lib.assets.data[q+4:q+4+n].decode('ascii',errors='ignore')
        for name,value in [('NET_ATTR',2),('NET_MARTIAL_TYPEID',12),('NET_GIFT_TYPEID',13),('NET_FRAGMENT',4)]:
            if not re.search(r'(?m)^'+name+r'\s*=\s*'+str(value)+r'\b',definitions):
                raise ValueError('人物演化类型定义不匹配，未安装入队同步：'+name)
    path=lib.root/'DreamRivakes_Data/Plugins/RaceLogic_Release_x64.dll'
    if not rows and not path.exists():return
    raw=payloads.get(path)
    if raw is None:raw=path.read_bytes()
    from nov15_growth_runtime import _original,patch_runtime
    if not rows and MAGIC not in raw:return
    originals.setdefault(path,raw)
    result=patch_runtime(raw,recruitment=rows)
    if result!=raw:payloads[path]=result

def pending(lib):
    rows=desired(lib)
    if not rows:return False
    path=lib.root/'DreamRivakes_Data/Plugins/RaceLogic_Release_x64.dll'
    if path not in lib.originals:lib.originals[path]=path.read_bytes()
    try:return installed(lib.originals[path],b'')!=rows
    except (ValueError,struct.error,UnicodeError):return True

def certified_transition(before,after):
    """Changing only this scope does not require a vanilla client-side DLL.

    Both full support sections, all hook bytes and the identical foreign parent
    are proved by detach; existing growth/range options must stay identical.
    """
    from external_runtime import detach
    try:
        parent_a,options_a=detach(before);parent_b,options_b=detach(after)
        options_a.pop('recruitment',None);options_b.pop('recruitment',None)
        return parent_a==parent_b and options_a==options_b
    except (ValueError,KeyError,struct.error):return False
