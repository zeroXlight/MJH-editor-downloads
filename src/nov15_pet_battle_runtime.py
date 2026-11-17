# Steam build 26650481 exact adapter; native_map250 and full parent SHA are required.
# November 5 exact-build adapter. Generated offline; see native_map24.json evidence.
# Generated for the exact certified big-map native build. See native mapping evidence.
"""Restore native assist levels from the live native account pet manager."""
import struct
MAGIC=b'MJHPETBATTLE213\0'

def append_support(original,pe,rva,body,overwrite,enabled):
    if not enabled:return
    from keystone import Ks,KS_ARCH_X86,KS_MODE_64
    body.extend(MAGIC);body.extend(bytes((-len(body))%16));entry=rva+len(body)
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
    for index,char in enumerate('clientdll.dll'):
        asm+=f'movzx eax,word ptr [rcx+{index*2}]\nor eax,0x20\ncmp eax,{ord(char)}\njne next_module\n'
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
mov rax,0x00746570686a6d2e
cmp [r9],rax
je section_found
add r9,40
dec ecx
jmp section_loop
section_found:
mov eax,[r9+12]
add rax,r8
mov r9,0x3132544550484a4d
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
xor eax,eax
add rsp,0x38
ret
'''
    code=bytes(Ks(KS_ARCH_X86,KS_MODE_64).asm(asm,addr=0x180000000+entry)[0]);body.extend(code)
    hook=0x755e46;target=0x493360;off=pe.get_offset_from_rva(hook)
    if original[off:off+5]!=b'\xe8'+struct.pack('<i',target-(hook+5)):
        raise ValueError('宠物助战等级入口被其他模组改动，未覆盖')
    overwrite(off,b'\xe8'+struct.pack('<i',entry-(hook+5)))
    body.extend(bytes((-len(body))%16))
