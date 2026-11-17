# Generated for the exact certified big-map native build. See native mapping evidence.
"""Chest-only native drop settlement; never scans or collects map loot."""
from pathlib import Path
import struct,json
MAGIC=b'MJHCHEST235\0'
HOOK=0x58728e
TARGET=0x5cad10
STATE='装备编辑器配置/宝箱自动入库.json'

def append_support(original,pe,rva,body,overwrite,enabled):
    if not enabled:return
    expected=b'\xe8'+struct.pack('<i',TARGET-HOOK-5)
    off=pe.get_offset_from_rva(HOOK)
    if original[off:off+5]!=expected:raise ValueError('宝箱奖励入口被其他MOD修改，未覆盖')
    from keystone import Ks,KS_ARCH_X86,KS_MODE_64
    body.extend(MAGIC);body.extend(bytes(-len(body)%16));entry=rva+len(body)
    # The original chest branch generates its drop list without awarding it,
    # then creates floor loot. Award the exact same native drop directly.
    asm=f'''
sub rsp,0x78
mov [rsp+0x30],rcx
mov [rsp+0x38],edx
lea rcx,[rsp+0x48]
call {0x180000000+0x4bcf50}
mov rcx,[rsp+0x30]
mov rcx,[rcx+8]
mov rcx,[rcx+0x88]
mov edx,[rsp+0x38]
lea r8,[rsp+0x48]
xor r9d,r9d
mov byte ptr [rsp+0x20],1
mov byte ptr [rsp+0x28],1
call {0x180000000+0x524b60}
lea rcx,[rsp+0x48]
call {0x180000000+0xa26520}
add rsp,0x78
ret
'''
    body.extend(bytes(Ks(KS_ARCH_X86,KS_MODE_64).asm(asm,0x180000000+entry)[0]))
    body.extend(bytes(-len(body)%16));overwrite(off,b'\xe8'+struct.pack('<i',entry-HOOK-5))

def certified_transition(before,after):
    from external_runtime import detach
    try:
        a,x=detach(before);b,y=detach(after);x.pop('chest_autoloot',None);y.pop('chest_autoloot',None)
        return a==b and x==y
    except (ValueError,KeyError,struct.error):return False

def plan(root,enabled=True):
    from bigmap_growth_runtime import patch_runtime
    from compatibility import validate_native_writes
    root=Path(root).resolve()
    from shadow_runtime import detected
    detected(root)
    p=root/'DreamRivakes_Data/Plugins/RaceLogic_Release_x64.dll';before=p.read_bytes()
    after=patch_runtime(before,chest_autoloot=enabled);payloads={p:after} if before!=after else {};originals={p:before}
    state=root/STATE;old=state.read_bytes() if state.exists() else None
    raw=json.dumps(dict(version=1,enabled=enabled),ensure_ascii=False,indent=2).encode('utf8')
    originals[state]=old
    if old!=raw:payloads[state]=raw
    validate_native_writes(root,payloads,originals)
    return payloads,originals,['宝箱物品自动入库：'+('启用' if enabled else '关闭'),
        '开箱奖励按游戏原有掉落方案直接结算至背包；不扫描或拾取地图已有散落物品。'],[],{}
