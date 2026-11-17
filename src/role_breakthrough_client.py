"""Independent account role-card transaction; native save and meridian balance."""
import hashlib,json,struct
SECTION=b'.mjhbt'
MAGIC=b'MJHROLEBT2311\0'
META=b'MJHROLEBTMETA2311\0'
BASE=0x180000000
COSTS=(500,1000,2000,3000,4000,6000,8000,12000,16000,25000)
def sha(raw):return hashlib.sha256(raw).hexdigest()

def detach(raw):
    import pefile
    pe=pefile.PE(data=raw,fast_load=True)
    sections=[s for s in pe.sections if s.Name.rstrip(b'\0')==SECTION]
    if not sections:return raw,False
    if len(sections)!=1 or sections[0]!=pe.sections[-1]:raise ValueError('角色突破支持段位置异常，未覆盖')
    s=sections[0];body=s.get_data();at=body.find(META)
    if not body.startswith(MAGIC) or at<0:raise ValueError('角色突破支持记录缺失')
    size=struct.unpack_from('<I',body,at+len(META))[0];end=at+len(META)+4+size
    if end!=s.Misc_VirtualSize or end>len(body) or any(body[end:]):raise ValueError('角色突破支持边界异常')
    doc=json.loads(body[at+len(META)+4:end])
    from growth_runtime import _restore_parent
    parent=_restore_parent(raw,doc)
    revision=doc.get('revision',1)
    if revision not in (1,2):raise ValueError('角色突破支持版本未认证，未覆盖')
    if sha(parent)!=doc['parent_sha256'] or _build(parent,revision)!=raw:raise ValueError('角色突破支持或父运行库被外部修改，未覆盖')
    return parent,True

def _helper(rva,revision=2):
    from keystone import Ks,KS_ARCH_X86,KS_MODE_64
    asm=f'''
push rbx
push rbp
push rsi
push rdi
push r12
push r13
push r14
sub rsp,0x40
mov r12,rcx
mov edi,edx
mov r13,[r12]
mov r14,[r12+0x18]
test r13,r13
jz fail
test r14,r14
jz fail
mov rcx,[r12+8]
test rcx,rcx
jz fail
mov edx,edi
xor r8d,r8d
call {BASE+0x3cc6d0}
test rax,rax
jz fail
mov rcx,rax
call {BASE+0x2755f0}
test eax,eax
jz fail
cmp eax,8
ja fail
mov [rsp+0x30],eax
mov rcx,r14
mov edx,edi
xor r8d,r8d
call {BASE+0xc9dd30}
mov rsi,rax
xor ebx,ebx
test rsi,rsi
jz level_ready
mov rcx,rsi
call {BASE+0x175be0}
mov ebx,eax
level_ready:
cmp ebx,10
jae fail
mov dword ptr [rsp+0x20],0
lea r9d,[rbx+1]
mov r8d,edi
mov edx,2
mov rcx,r12
call {BASE+0xca82d0}
test al,al
jz fail
lea rax,[rip+costs]
mov ebp,[rax+rbx*4]
cmp [r13+0xb68],rbp
jb fail
test rsi,rsi
jnz charge
mov rcx,r14
mov edx,edi
mov r8d,edi
call {BASE+0xca7900}
mov rsi,rax
test rsi,rsi
jz fail
charge:
mov rcx,r13
mov edx,ebp
neg edx
xor r8d,r8d
xor r9d,r9d
call {BASE+0xb933b0}
test al,al
jz fail
lea edx,[rbx+1]
mov rcx,rsi
call {BASE+0x175bf0}
mov rcx,r12
mov edx,edi
call {BASE+0xcaa4b0}
lea rcx,[r13+0x12e8]
mov edx,edi
lea r8d,[rbx+1]
mov r9d,[rsp+0x30]
mov byte ptr [rsp+0x20],1
call {BASE+0xd06830}
mov eax,1
jmp finish
fail:
xor eax,eax
finish:
add rsp,0x40
pop r14
pop r13
pop r12
pop rdi
pop rsi
pop rbp
pop rbx
ret
costs:
.long {','.join(map(str,COSTS))}
'''
    if revision==2:
        # ca82d0 only applies mobile server-age/story stage maxima. The role,
        # rank, native record, currency and ten-step bounds above/below stay.
        asm=asm.replace(f'''mov dword ptr [rsp+0x20],0
lea r9d,[rbx+1]
mov r8d,edi
mov edx,2
mov rcx,r12
call {BASE+0xca82d0}
test al,al
jz fail
''','')
    return bytes(Ks(KS_ARCH_X86,KS_MODE_64).asm(asm,addr=BASE+rva)[0])

def _build(parent,revision=2):
    if revision not in (1,2):raise ValueError('角色突破支持版本未认证')
    import pefile
    from bigmap_profile import client_image
    if not client_image(parent):raise ValueError('角色突破目前仅支持已认证的大地图电脑版运行库')
    from growth_runtime import _expand_headers
    original=parent;parent,shift=_expand_headers(parent);pe=pefile.PE(data=parent,fast_load=True)
    align=lambda n,a:(n+a-1)//a*a
    header=pe.sections[-1].get_file_offset()+40
    rva=align(max(s.VirtualAddress+max(s.Misc_VirtualSize,s.SizeOfRawData) for s in pe.sections),pe.OPTIONAL_HEADER.SectionAlignment)
    offset=align(len(parent),pe.OPTIONAL_HEADER.FileAlignment)
    body=bytearray(MAGIC+bytes(0x100-len(MAGIC)))
    entry=rva+len(body);body.extend(_helper(entry,revision));body.extend(bytes((-len(body))%16))
    from keystone import Ks,KS_ARCH_X86,KS_MODE_64
    ks=Ks(KS_ARCH_X86,KS_MODE_64)
    lookup=rva+len(body)
    code=bytearray(ks.asm(f'''
sub rsp,0x38
mov [rsp+0x20],edx
mov rcx,[rip+player]
test rcx,rcx
jz absent
mov rcx,[rcx+0xd58]
test rcx,rcx
jz absent
mov edx,[rsp+0x20]
xor r8d,r8d
call {BASE+0xc9dd30}
test rax,rax
jz absent
mov rcx,rax
call {BASE+0x175be0}
cmp eax,10
jbe done
absent:
xor eax,eax
done:
add rsp,0x38
ret
player:
''',addr=BASE+lookup)[0])
    at=code.index(bytes.fromhex('488b0d'));struct.pack_into('<i',code,at+3,(rva+0x18)-(lookup+at+7));body.extend(code)
    struct.pack_into('<I',body,0x20,lookup)
    body.extend(bytes((-len(body))%16));capture=rva+len(body)
    site=0xba1fa0;off=pe.get_offset_from_rva(site);before=parent[off:off+5]
    if before==bytes.fromhex('48894c2408'):
        tail=f'mov [rsp+8],rcx\njmp {BASE+site+5}'
    elif before[0]==0xe9 and any(s.Name.rstrip(b'\0')==b'.mjhpet' for s in pe.sections):
        # The complete inner image was certified before header expansion.
        tail=f'jmp {BASE+site+5+struct.unpack_from("<i",before,1)[0]}'
    else:raise ValueError('角色突破账户入口已被其他补丁修改')
    code=bytearray(ks.asm(f'mov [rip+player],rcx\n{tail}\nplayer:',addr=BASE+capture)[0]);struct.pack_into('<i',code,3,(rva+0x18)-(capture+7));body.extend(code)
    out=bytearray(parent);undo=[]
    def put(off,data):undo.append((off,parent[off:off+len(data)].hex()));out[off:off+len(data)]=data
    hook=0xc44675;off=pe.get_offset_from_rva(hook)
    if parent[off:off+5]!=b'\xe8'+struct.pack('<i',0xca9d40-hook-5):raise ValueError('角色突破操作入口已被其他补丁修改')
    put(off,b'\xe8'+struct.pack('<i',entry-hook-5));put(pe.get_offset_from_rva(site),b'\xe9'+struct.pack('<i',capture-site-5))
    opt=pe.OPTIONAL_HEADER.get_file_offset()
    put(pe.FILE_HEADER.get_file_offset()+2,struct.pack('<H',pe.FILE_HEADER.NumberOfSections+1))
    for off,n in ((header,40),(opt+4,4),(opt+56,4),(opt+64,4)):undo.append((off,parent[off:off+n].hex()))
    doc=dict(length=len(parent),parent_sha256=sha(original),undo=undo)
    if shift:doc['header_shift']=shift
    if revision==2:doc['revision']=2
    data=json.dumps(doc,separators=(',',':')).encode('ascii');body.extend(META+struct.pack('<I',len(data))+data)
    size=align(len(body),pe.OPTIONAL_HEADER.FileAlignment)
    out[header:header+40]=struct.pack('<8sIIIIIIHHI',SECTION,len(body),rva,size,offset,0,0,0,0,0xe0000020)
    struct.pack_into('<I',out,opt+4,pe.OPTIONAL_HEADER.SizeOfCode+size);struct.pack_into('<I',out,opt+56,align(rva+len(body),pe.OPTIONAL_HEADER.SectionAlignment));struct.pack_into('<I',out,opt+64,0)
    out.extend(bytes(offset-len(out))+body+bytes(size-len(body)));return bytes(out)

def patch(raw,enabled=True):
    parent,_=detach(raw)
    return _build(parent) if enabled else parent
