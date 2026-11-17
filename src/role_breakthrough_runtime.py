"""Bind native role breakthrough queries to the live cross-round account map."""
import struct,hashlib
MAGIC=b'MJHROLEBTBATTLE2311\0'
SUSPENDED_MAGIC=b'MJHROLEBTOFF2311\0'
SYNC_MAGIC=b'MJHROLEBTSYNC2315\0'
MOBILE_MAGIC=b'MJHROLEBTMOBILE2316\0'

def append_support(original,pe,rva,body,overwrite,enabled,legacy=False):
    if not enabled:return
    from bigmap_profile import race_parent
    # Here original can have expanded file headers; certify through the owner.
    from keystone import Ks,KS_ARCH_X86,KS_MODE_64
    ks=Ks(KS_ARCH_X86,KS_MODE_64);base=0x180000000
    if enabled not in (True,2):raise ValueError('角色突破运行库选项无效')
    body.extend(SUSPENDED_MAGIC if enabled==2 else MAGIC);body.extend(bytes((-len(body))%16));lookup=rva+len(body)
    asm='''
sub rsp,0x38
mov [rsp+0x20],edx
mov rax,gs:[0x60]
mov rax,[rax+0x18]
lea r10,[rax+0x20]
mov r11,[r10]
mov dword ptr [rsp+0x28],256
module_loop:
cmp r11,r10
je absent
dec dword ptr [rsp+0x28]
jz absent
cmp word ptr [r11+0x48],26
jne next_module
mov rcx,[r11+0x50]
'''
    for i,ch in enumerate('clientdll.dll'):
        asm+=f'movzx eax,word ptr [rcx+{i*2}]\nor eax,0x20\ncmp eax,{ord(ch)}\njne next_module\n'
    asm+='''
mov r8,[r11+0x20]
mov eax,[r8+0x3c]
lea r9,[r8+rax]
movzx ecx,word ptr [r9+6]
movzx eax,word ptr [r9+20]
lea r9,[r9+rax+24]
section_loop:
test ecx,ecx
jz absent
mov rax,0x00007462686a6d2e
cmp [r9],rax
je found
add r9,40
dec ecx
jmp section_loop
found:
mov eax,[r9+12]
add rax,r8
mov r9,0x42454c4f52484a4d
cmp [rax],r9
jne absent
mov eax,[rax+0x20]
add rax,r8
mov edx,[rsp+0x20]
call rax
add rsp,0x38
ret
next_module:
mov r11,[r11]
jmp module_loop
absent:
mov eax,-1
add rsp,0x38
ret
'''
    if enabled==2:asm='xor eax,eax\nret'
    body.extend(bytes(ks.asm(asm,addr=base+lookup)[0]));body.extend(bytes((-len(body))%16))
    trampoline=rva+len(body);hook=0x492200;off=pe.get_offset_from_rva(hook)
    prefix=bytes.fromhex('8954241048894c2408')
    if original[off:off+9]!=prefix:raise ValueError('角色突破属性查询入口已被其他补丁修改')
    body.extend(prefix+b'\xe9'+struct.pack('<i',hook+9-trampoline-14));body.extend(bytes((-len(body))%16));entry=rva+len(body)
    asm=f'''
push rbx
push rsi
sub rsp,0x38
mov rsi,rcx
mov ebx,edx
call {base+0x491f30}
test al,al
jz named
mov rcx,rsi
call {base+0x491fe0}
test eax,eax
jz named
mov ebx,eax
named:
mov edx,ebx
call {base+lookup}
cmp eax,-1
je fallback
mov [rsp+0x20],eax
mov r8d,eax
mov edx,ebx
mov rcx,rsi
call {base+0x494ff0}
add eax,[rsp+0x20]
add rsp,0x38
pop rsi
pop rbx
ret
fallback:
mov edx,ebx
mov rcx,rsi
add rsp,0x38
pop rsi
pop rbx
jmp {base+trampoline}
'''
    body.extend(bytes(ks.asm(asm,addr=base+entry)[0]));body.extend(bytes((-len(body))%16))
    overwrite(off,b'\xe9'+struct.pack('<i',entry-hook-5)+b'\x90'*4)
    if legacy is True:return
    # Before the native dirty-actor queue is drained, compare each loaded
    # role with its live account level. Only changed roles use the original
    # overlay setter and attribute rebuild, which enqueue native 759/762 data.
    hook=0x49dde0;off=pe.get_offset_from_rva(hook)
    prefix=bytes.fromhex('48894c2408')
    if original[off:off+5]!=prefix:
        raise ValueError('角色突破属性刷新入口已被其他补丁修改')
    body.extend(SYNC_MAGIC);body.extend(bytes((-len(body))%16));entry=rva+len(body)
    asm=f'''
push rbx
push rsi
push rdi
sub rsp,0x70
mov rsi,rcx
lea rcx,[rsi+0xf8]
lea rdx,[rsp+0x30]
call {base+0x240900}
loop_roles:
lea rcx,[rsi+0xf8]
lea rdx,[rsp+0x40]
call {base+0x240940}
mov rdx,rax
lea rcx,[rsp+0x30]
call {base+0x23eae0}
test al,al
jz sync_done
lea rcx,[rsp+0x30]
call {base+0x2543d0}
mov rbx,[rax+8]
test rbx,rbx
jz next_role
mov rcx,rbx
call {base+0x6f5f90}
mov edx,eax
mov rcx,rsi
call {base+0x492200}
cmp [rbx+0x194],eax
je next_role
mov edx,eax
mov rcx,rbx
call {base+0x4c3f50}
xor edx,edx
mov rcx,rbx
call {base+0x72f580}
next_role:
lea rcx,[rsp+0x30]
call {base+0x258040}
jmp loop_roles
sync_done:
mov rcx,rsi
add rsp,0x70
pop rdi
pop rsi
pop rbx
mov [rsp+8],rcx
jmp {base+hook+5}
'''
    sync_call=None
    if not legacy and enabled!=2:
        asm=asm.replace(f'call {base+0x4c3f50}\nxor edx,edx',f'call {base+0x4c3f50}\nmov rcx,rbx\ncall {base+0x1000000}\nxor edx,edx')
        # The helper is appended after the existing compatibility bytes. Resolve
        # this forward call once its final address is known.
        from capstone import Cs,CS_ARCH_X86,CS_MODE_64
        pending=bytes(ks.asm(asm,addr=base+entry)[0])
        ins=next(i for i in Cs(CS_ARCH_X86,CS_MODE_64).disasm(pending,base+entry) if i.mnemonic=='call' and i.op_str==hex(base+0x1000000))
        sync_call=len(body)+ins.address-(base+entry)
    body.extend(bytes(ks.asm(asm,addr=base+entry)[0]));body.extend(bytes((-len(body))%16))
    overwrite(off,b'\xe9'+struct.pack('<i',entry-hook-5))
    if legacy=='2315':return
    body.extend(MOBILE_MAGIC);body.extend(bytes((-len(body))%16))
    if enabled==2:return
    # Android DefaultRole.GetCardAttr scales the six untrained base attributes
    # before their native conversions. PC's retained whitelist targets HP/MP
    # and attack instead, so merely restoring its card-level getter is wrong.
    # Keep the original map/percentage machinery and change only that filter.
    hook=0x739234;off=pe.get_offset_from_rva(hook)
    prefix=bytes.fromhex('488d542458')
    if original[off:off+5]!=prefix:raise ValueError('角色突破六属性转换入口已被其他补丁修改')
    entry=rva+len(body)
    asm=f'''
lea rcx,[rsp+0x38]
call {base+0x253d40}
cmp dword ptr [rax],3
jl skip_base
cmp dword ptr [rax],8
jg skip_base
jmp {base+0x73927f}
skip_base:
jmp {base+0x7392f2}
'''
    body.extend(bytes(ks.asm(asm,addr=base+entry)[0]));body.extend(bytes((-len(body))%16))
    overwrite(off,b'\xe9'+struct.pack('<i',entry-hook-5))
    growth_sync=_append_growth(body,rva,base,ks,pe,original,overwrite)
    if sync_call is not None:struct.pack_into('<i',body,sync_call+1,growth_sync-(rva+sync_call+5))


def _append_growth(body,rva,base,ks,pe,original,overwrite):
    import json
    from engine import DATA_ROOT
    pack=json.loads((DATA_ROOT/'role_breakthrough_pack.json').read_text('utf8'))
    records=[]
    for tid,tree in pack['RoleWishTree'].items():
        for gift in tree['AllGiftIDs']:
            records.append((tree['RoleTypeID'],gift,int(tid)))
    resolver=rva+len(body)
    asm=f'''
push rbx
push rsi
push rdi
sub rsp,0x30
mov rbx,rcx
mov edi,[rbx+0x2c]
cmp dword ptr [rbx+0x30],8
jne original_type
cmp dword ptr [rbx+0x54],1
jne original_type
owned:
mov rax,[rbx+8]
mov rcx,[rax+0x18]
mov edx,[rbx+0x58]
call {base+0x49da30}
test rax,rax
jz original_type
mov esi,[rax+0x2c]
lea r9,[rip+recipes]
mov r10d,{len(records)}
scan:
test r10d,r10d
jz original_type
cmp [r9],esi
jne next_recipe
cmp [r9+4],edi
jne next_recipe
mov r8d,[r9+8]
mov rax,[rbx+8]
mov rcx,[rax+0x48]
mov edx,esi
call {base+0x51ad70}
test eax,eax
jnz done
jmp original_type
next_recipe:
add r9,12
dec r10d
jmp scan
original_type:
mov eax,edi
done:
add rsp,0x30
pop rdi
pop rsi
pop rbx
ret
recipes:
'''
    body.extend(bytes(ks.asm(asm,addr=base+resolver)[0]))
    for record in records:body.extend(struct.pack('<III',*record))
    body.extend(bytes((-len(body))%16))
    hook=0x6f5f90;off=pe.get_offset_from_rva(hook)
    if original[off:off+5]!=bytes.fromhex('48894c2408'):raise ValueError('天赋突破类型入口冲突')
    entry=rva+len(body)
    # The gift save serializer must retain the original type, not the derived
    # level-dependent view. Its UID, source, owner and learned state stay intact.
    asm=f'''
lea rax,[rip-{entry+7}]
add rax,0x7b5064
cmp [rsp],rax
je stored_type
sub rax,{0x7b5064-0x7b4d1e}
cmp [rsp],rax
je stored_type
sub rax,{0x7b4d1e-0x51765c}
cmp [rsp],rax
je stored_type
jmp {base+resolver}
stored_type:
mov eax,[rcx+0x2c]
ret
'''
    body.extend(bytes(ks.asm(asm,addr=base+entry)[0]));body.extend(bytes((-len(body))%16))
    overwrite(off,b'\xe9'+struct.pack('<i',entry-hook-5))
    hook=0x5d53e0;off=pe.get_offset_from_rva(hook)
    if original[off:off+5]!=bytes.fromhex('48894c2408'):raise ValueError('天赋突破效果入口冲突')
    entry=rva+len(body)
    asm=f'''
push rbx
sub rsp,0x30
mov rbx,rcx
call {base+resolver}
cmp eax,[rbx+0x2c]
je cached
mov edx,eax
mov [rsp+0x28],edx
mov rax,[rbx+8]
mov rcx,[rax+8]
call {base+0x40bd70}
mov rcx,rax
mov edx,[rsp+0x28]
call {base+0x89b970}
test rax,rax
jnz resolved
cached:
mov rax,[rbx+0x48]
resolved:
add rsp,0x30
pop rbx
ret
'''
    body.extend(bytes(ks.asm(asm,addr=base+entry)[0]));body.extend(bytes((-len(body))%16))
    overwrite(off,b'\xe9'+struct.pack('<i',entry-hook-5))
    sync=rva+len(body)
    asm=f'''
push rbx
push rsi
push rdi
sub rsp,0x50
mov rsi,rcx
lea rcx,[rsi+0x120]
lea rdx,[rsp+0x30]
call {base+0x240fa0}
gift_loop:
lea rcx,[rsi+0x120]
lea rdx,[rsp+0x40]
call {base+0x23e4d0}
mov rdx,rax
lea rcx,[rsp+0x30]
call {base+0x23eae0}
test al,al
jz gifts_done
lea rcx,[rsp+0x30]
call {base+0x253d20}
mov edx,[rax]
mov rax,[rsi+8]
mov rcx,[rax+0x48]
call {base+0x51b0a0}
test rax,rax
jz next_gift
mov rbx,rax
cmp dword ptr [rbx+0x54],1
je refresh_gift
cmp dword ptr [rbx+0x54],9
jne next_gift
refresh_gift:
mov rax,[rbx]
mov rcx,rbx
mov edx,2
call qword ptr [rax+0x30]
next_gift:
lea rcx,[rsp+0x30]
call {base+0x243cd0}
jmp gift_loop
gifts_done:
add rsp,0x50
pop rdi
pop rsi
pop rbx
ret
'''
    body.extend(bytes(ks.asm(asm,addr=base+sync)[0]));body.extend(bytes((-len(body))%16))
    return sync
