# November 5 exact-build adapter. Generated offline; see native_map24.json evidence.
# Generated for the exact certified big-map native build. See native mapping evidence.
"""Installation-wide interaction unlock; no save iteration or platform purchase."""
import struct
from pathlib import Path

MAGIC=b'MJHINTERACT257\0'
TYPES=(1,2,11,13)
NAMES=('PBT_QiTao','PBT_JueDou','PBT_CallUp','PBT_INQUIRY')
ENTRY=0x476470
EXPECTED=bytes.fromhex('44 89 44 24 18')
LUA_MARKER='-- MJH_INTERACTION_UNLOCK_V257'

def helper(rva):
    code=bytearray()
    for value in TYPES:code.extend(b'\x83\xfa'+bytes([value])+b'\x74'+bytes([5*(len(TYPES)-TYPES.index(value)-1)+10]))
    code.extend(EXPECTED)
    code.extend(b'\xe9'+struct.pack('<i',ENTRY+5-(rva+len(code)+5)))
    code.extend(b'\xb0\x01\xc3')
    return bytes(code)

def append_support(original,pe,rva,body,overwrite,enabled):
    if not enabled:return
    off=pe.get_offset_from_rva(ENTRY)
    if original[off:off+5]!=EXPECTED:raise ValueError('交互解锁入口已被其他 MOD 修改，未安装')
    body.extend(MAGIC);body.extend(bytes(-len(body)%16));entry=rva+len(body)
    body.extend(helper(entry));body.extend(bytes(-len(body)%16))
    overwrite(off,b'\xe9'+struct.pack('<i',entry-ENTRY-5))

def patch_lua(text,enabled=True):
    if not enabled:
        import re
        pattern=r'\r?\n    '+re.escape(LUA_MARKER)+r'\r?\n    if [^\r\n]+ then return true end\r?\n'
        if LUA_MARKER in text:
            text,count=re.subn(pattern,'\n',text)
            if count!=1:raise ValueError('交互解锁脚本标记异常，未关闭')
        return text
    if LUA_MARKER in text:return text
    anchor='function RoleDataManager:IsInteractUnlock(playerBehavior)'
    if text.count(anchor)!=1:raise ValueError('界面交互解锁入口不兼容')
    condition=' or '.join('playerBehavior == PlayerBehaviorType.'+n for n in NAMES)
    return text.replace(anchor,anchor+'\n    '+LUA_MARKER+'\n    if '+condition+' then return true end\n',1)

def certified_transition(before,after):
    from external_runtime import detach
    try:
        a,oa=detach(before);b,ob=detach(after)
        oa.pop('interactions',None);ob.pop('interactions',None)
        return a==b and oa==ob
    except (ValueError,KeyError,struct.error):return False

def plan(root,enabled=True):
    from client_config import Assets
    from nov5_growth_runtime import patch_runtime
    root=Path(root).resolve();dll=root/'DreamRivakes_Data/Plugins/RaceLogic_Release_x64.dll'
    path=root/'DreamRivakes_Data/resources.assets';raw=path.read_bytes();native=dll.read_bytes()
    assets=Assets(raw)
    from client_config import enum_values
    enums=enum_values(assets.script('common.lua'))
    for name,value in zip(NAMES,TYPES):
        if enums.get('PlayerBehaviorType.'+name)!=value:raise ValueError('交互类型定义不匹配：'+name)
    after=Assets(assets.replace_script('RoleDataManager.lua',patch_lua(assets.script('RoleDataManager.lua'),enabled))).normalize_text_lengths()
    patched=patch_runtime(native,interactions=enabled)
    originals={path:raw,dll:native};payloads={p:b for p,b in ((path,after),(dll,patched)) if b!=originals[p]}
    from compatibility import validate_native_writes
    validate_native_writes(root,payloads,originals)
    return payloads,originals,['盘查、号召、决斗、乞讨：'+('永久解锁（当前游戏目录全部旧档、新档及后续周目）。' if enabled else '关闭永久解锁，按原游戏条件使用。'),'不修改存档，不支付解锁费用；保留交互对象、剧情、次数和战斗规则。'],[],{}
