"""Atomic pet transactions in the retained native account dispatcher.

The two pet RPC calls are replaced. Pet records and the native meridians
balance change together inside one handler, then follow ordinary game saves.
No Lua-side balance or synthetic inventory token is involved.
"""
import hashlib,json,struct
from pathlib import Path

SECTION=b'.mjhpet'
MAGIC=b'MJHPET213\0'
META_MAGIC=b'MJHPETMETA213\0'
ORIGINAL_SHA='e5409f50da068a1ca6c7b57556b2946710606fe5474510043d8fd1b992222a82'
HOOKS=((0xc42a4f,0xca7860),(0xc42a7b,0xca66d0))

def _sha(raw):return hashlib.sha256(raw).hexdigest()

def _rules():
    from engine import DATA_ROOT
    pets=json.loads((DATA_ROOT/'pet_mobile_data.json').read_text('utf8'))
    return [(int(k),v['cardItem1'] or int(k),v['Rank'],5 if v.get('Chain') else 10)
            for k,v in sorted(pets.items(),key=lambda item:int(item[0]))]

def _helper(rva):
    from keystone import Ks,KS_ARCH_X86,KS_MODE_64
    from pet_rules import upgrade_cost
    base=0x180000000
    asm=f'''
push rbx
push rbp
push rsi
push rdi
push r12
push r13
push r14
push r15
sub rsp,0x58
mov r12,rcx
mov [rsp+0x44],r9d
mov edi,edx
mov r13,[r12]
mov r14,[r12+0x10]
test r13,r13
jz fail
test r14,r14
jz fail
lea r15,[rip+rules]
mov ecx,{len(_rules())}
search:
cmp edi,[r15]
je found
add r15,16
dec ecx
jnz search
jmp fail
found:
mov rcx,r14
mov edx,edi
xor r8d,r8d
call {base+0xca6cd0}
mov rsi,rax
xor ebx,ebx
test rsi,rsi
jz unlock
mov rcx,rsi
call {base+0x175be0}
mov ebx,eax
test ebx,ebx
jz unlock
cmp dword ptr [rsp+0x44],0
jne fail
cmp ebx,[r15+12]
jae fail
lea rax,[rip+costs]
mov ebp,[rax+rbx*4]
mov eax,ebx
inc eax
mov [rsp+0x40],eax
jmp check_balance
unlock:
mov ebp,1000
mov ecx,[r15+8]
dec ecx
shl ebp,cl
mov dword ptr [rsp+0x40],1
cmp edi,[r15+4]
je check_balance
mov rcx,r14
mov edx,[r15+4]
xor r8d,r8d
call {base+0xca6cd0}
test rax,rax
jz fail
mov rcx,rax
call {base+0x175be0}
cmp eax,5
jb fail
mov dword ptr [rsp+0x40],5
check_balance:
mov rax,[r13+0xb68]
cmp rax,rbp
jb fail
test rsi,rsi
jnz change
mov rcx,r14
mov edx,edi
mov r8d,edi
call {base+0xca58a0}
mov rsi,rax
test rsi,rsi
jz fail
change:
mov rcx,r13
mov edx,ebp
neg edx
xor r8d,r8d
xor r9d,r9d
call {base+0xb90fa0}
test al,al
jz fail
mov rcx,rsi
mov edx,[rsp+0x40]
call {base+0x175bf0}
test ebx,ebx
jnz success
mov rcx,r12
mov edx,[r15+4]
mov r8d,edi
call {base+0xca8b10}
success:
lea rcx,[r13+0x12e8]
mov edx,edi
mov r8d,[rsp+0x40]
xor r9d,r9d
mov byte ptr [rsp+0x20],0
call {base+0xd05fe0}
mov eax,1
jmp finish
fail:
xor eax,eax
finish:
add rsp,0x58
pop r15
pop r14
pop r13
pop r12
pop rdi
pop rsi
pop rbp
pop rbx
ret
costs:
.long 0,{','.join(str(upgrade_cost(i)) for i in range(1,10))}
rules:
.byte {','.join(str(b) for row in _rules() for b in struct.pack('<4I',*row))}
'''
    return bytes(Ks(KS_ARCH_X86,KS_MODE_64).asm(asm,addr=base+rva)[0])

def original(raw):
    from bigmap_profile import client_image
    if client_image(raw):
        from bigmap_pet_runtime import original as big_original
        return big_original(raw)
    import pefile
    pe=pefile.PE(data=raw,fast_load=True)
    sections=[s for s in pe.sections if s.Name.rstrip(b'\0')==SECTION]
    if not sections:return raw
    if len(sections)!=1 or sections[0]!=pe.sections[-1]:raise ValueError('宠物运行库节布局不兼容')
    sec=sections[0];data=sec.get_data();at=data.find(META_MAGIC)
    if not data.startswith(MAGIC) or at<0:raise ValueError('宠物运行库元数据缺失')
    size=struct.unpack_from('<I',data,at+len(META_MAGIC))[0]
    doc=json.loads(data[at+len(META_MAGIC)+4:at+len(META_MAGIC)+4+size])
    result=bytearray(raw[:doc['length']])
    for off,value in doc['undo']:
        val=bytes.fromhex(value)
        if off<0 or off+len(val)>len(result):raise ValueError('宠物运行库恢复范围无效')
        result[off:off+len(val)]=val
    result=bytes(result)
    if _sha(result)!=doc['parent_sha256']:raise ValueError('宠物运行库父文件已变化')
    if _build(result)!=raw:raise ValueError('宠物运行库支持被其他修改覆盖')
    return result

def _build(parent):
    from bigmap_profile import client_parent
    if client_parent(parent):
        from bigmap_pet_runtime import _build as big_build
        return big_build(parent)
    import pefile
    pe=pefile.PE(data=parent,fast_load=True)
    header=pe.sections[-1].get_file_offset()+40
    if header+40>pe.OPTIONAL_HEADER.SizeOfHeaders or any(parent[header:header+40]):
        raise ValueError('宠物运行库没有可用节表空间')
    align=lambda n,a:(n+a-1)//a*a
    rva=align(max(s.VirtualAddress+max(s.Misc_VirtualSize,s.SizeOfRawData) for s in pe.sections),pe.OPTIONAL_HEADER.SectionAlignment)
    raw_offset=align(len(parent),pe.OPTIONAL_HEADER.FileAlignment)
    body=bytearray(MAGIC+bytes(0x100-len(MAGIC)))
    entry=rva+len(body);body.extend(_helper(entry));body.extend(bytes((-len(body))%16))
    upgrade=rva+len(body)
    body.extend(bytes.fromhex('45 31 c9 e9')+struct.pack('<i',entry-(upgrade+8)))
    evolve=rva+len(body)
    # The evolution RPC passes root, form. Normal form validation below checks
    # ownership through the authoritative root and requires its level five.
    body.extend(bytes.fromhex('44 89 c2 41 b9 01 00 00 00 e9')+struct.pack('<i',entry-(evolve+14)))
    
    from keystone import Ks,KS_ARCH_X86,KS_MODE_64
    ks=Ks(KS_ARCH_X86,KS_MODE_64);base=0x180000000
    body.extend(bytes((-len(body))%16));lookup=rva+len(body)
    asm=f"""
sub rsp,0x38
mov [rsp+0x20],edx
mov rcx,[rip+player]
test rcx,rcx
jz nolevel
add rcx,0xd40
mov rcx,[rcx+0x10]
test rcx,rcx
jz nolevel
mov edx,[rsp+0x20]
xor r8d,r8d
call {base+0xca6cd0}
test rax,rax
jz nolevel
mov rcx,rax
call {base+0x175be0}
add rsp,0x38
ret
nolevel:
xor eax,eax
add rsp,0x38
ret
player:
"""
    code=bytes(ks.asm(asm,addr=base+lookup)[0])
    # Relocate the sole RIP-relative player slot from the label after the code
    # to the fixed writable slot in our section header.
    at=code.index(bytes.fromhex('48 8b 0d'));code=bytearray(code)
    struct.pack_into('<i',code,at+3,(rva+0x18)-(lookup+at+7));body.extend(code)
    struct.pack_into('<I',body,0x20,lookup)
    body.extend(bytes((-len(body))%16));capture=rva+len(body)
    asm=f"""
mov [rip+player],rcx
mov [rsp+8],rcx
jmp {base+0xb9fb95}
player:
"""
    code=bytearray(ks.asm(asm,addr=base+capture)[0]);struct.pack_into('<i',code,3,(rva+0x18)-(capture+7));body.extend(code)

    output=bytearray(parent);undo=[]
    def overwrite(off,value):undo.append((off,parent[off:off+len(value)].hex()));output[off:off+len(value)]=value
    for (hook,target),dest in zip(HOOKS,(upgrade,evolve)):
        off=pe.get_offset_from_rva(hook)
        expected=b'\xe8'+struct.pack('<i',target-(hook+5))
        if parent[off:off+5]!=expected:raise ValueError('宠物账户入口被其他模组修改，已保留原文件')
        overwrite(off,b'\xe8'+struct.pack('<i',dest-(hook+5)))
    off=pe.get_offset_from_rva(0xb9fb90)
    if parent[off:off+5]!=bytes.fromhex('48 89 4c 24 08'):raise ValueError('宠物账户查询入口不兼容')
    overwrite(off,b'\xe9'+struct.pack('<i',capture-(0xb9fb90+5)))
    optional=pe.OPTIONAL_HEADER.get_file_offset()
    overwrite(pe.FILE_HEADER.get_file_offset()+2,struct.pack('<H',pe.FILE_HEADER.NumberOfSections+1))
    for off,width in ((header,40),(optional+4,4),(optional+56,4),(optional+64,4)):
        undo.append((off,parent[off:off+width].hex()))
    doc=json.dumps({'length':len(parent),'parent_sha256':_sha(parent),'undo':undo},separators=(',',':')).encode('ascii')
    body.extend(META_MAGIC+struct.pack('<I',len(doc))+doc)
    raw_size=align(len(body),pe.OPTIONAL_HEADER.FileAlignment)
    output[header:header+40]=struct.pack('<8sIIIIIIHHI',SECTION,len(body),rva,raw_size,raw_offset,0,0,0,0,0xe0000020)
    struct.pack_into('<I',output,optional+4,pe.OPTIONAL_HEADER.SizeOfCode+raw_size)
    struct.pack_into('<I',output,optional+56,align(rva+len(body),pe.OPTIONAL_HEADER.SectionAlignment))
    struct.pack_into('<I',output,optional+64,0)
    output.extend(bytes(raw_offset-len(output))+body+bytes(raw_size-len(body)))
    return bytes(output)

def patch(raw,enabled=True,certify=None):
    from martial_limit_enhance import normalize_client,patch_client
    from role_breakthrough_client import detach,_build as build_breakthrough
    raw,breakthrough=detach(raw)
    raw,limit_enabled=normalize_client(raw)
    parent=original(raw)
    if _sha(parent)!=ORIGINAL_SHA and (certify is None or not certify(parent)):
        raise ValueError('宠物账户运行库版本尚未识别，未修改')
    result=_build(parent) if enabled else parent
    result=patch_client(result,True) if limit_enabled else result
    return build_breakthrough(result) if breakthrough else result
