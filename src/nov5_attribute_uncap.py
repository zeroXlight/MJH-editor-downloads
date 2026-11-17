# November 5 exact-build adapter. Generated offline; see native_map24.json evidence.
# Generated for the exact certified big-map native build. See native mapping evidence.
"""Opt-in native character attribute limits, with reversible owned hooks."""
import struct
from pathlib import Path

MAGIC=b'MJHATTRUNCAP218\0'
DAMAGE_MAGIC=b'MJHDAMAGEUNCAP218\0'
# Six base attributes, eight masteries, HP/MP/defense/speed, family attacks,
# numerical hit/dodge/crit/resistance/combo/counter values, common attack.
# Probability rules, movement, martial levels and skill limits remain native.
ATTRS=tuple(range(3,21))+tuple(range(22,36))+(64,65,99,100,101,116,117,118,119,120,121,122,123,145)
STORAGE_LIMIT=2_000_000_000
CALLS=(0x702695,0x7026f2,0x70277f,0x7027cd,0x70281b,0x702869,0x7028b7,0x702902,0x70294d,0x702998,0x7029e9,0x702a34,0x702a7f,0x702ac4,0x702b09,0x702b4e,0x702b93,0x702bd8,0x702c29,0x702c7a,0x702ccb,0x702d1c,0x702d6d,0x702dbb)

def _append_attrs(original,pe,rva,body,overwrite,enabled):
    if not enabled:return
    from keystone import Ks,KS_ARCH_X86,KS_MODE_64
    import hashlib
    off=pe.get_offset_from_rva(0x702570)
    if hashlib.sha256(original[off:off+0x860]).hexdigest()!='dbe6dad13e42966b7c06f47ae30ae84e79576482b36db547d0a046c4f568c8e5':
        raise ValueError('人物属性上限入口版本不一致，未修改')
    body.extend(MAGIC);body.extend(bytes(-len(body)%16));entry=rva+len(body)
    body.extend(_attribute_code(entry))
    body.extend(bytes(-len(body)%16))
    for at in CALLS:
        off=pe.get_offset_from_rva(at);expected=b'\xe8'+struct.pack('<i',0x50af20-at-5)
        if original[off:off+5]!=expected:raise ValueError('人物属性上限入口被其他 MOD 修改：'+hex(at))
        overwrite(off,b'\xe8'+struct.pack('<i',entry-at-5))

def _attribute_code(entry):
    comparisons=[b'\x41\x83\xfa'+bytes([a]) if a<128 else b'\x41\x81\xfa'+struct.pack('<I',a) for a in ATTRS]
    widths=[6]*len(ATTRS)
    while True:
        target=8+sum(len(c)+n for c,n in zip(comparisons,widths))+5
        offset=8;new=[]
        for c,n in zip(comparisons,widths):
            offset+=len(c);distance=target-offset-n
            new.append(2 if distance<=127 else 6);offset+=n
        if new==widths:break
        widths=new
    code=bytearray(bytes.fromhex('448b942420010000'))
    for c,n in zip(comparisons,widths):
        code.extend(c);distance=target-len(code)-n
        code.extend(b'\x74'+struct.pack('<b',distance) if n==2 else b'\x0f\x84'+struct.pack('<i',distance))
    code.extend(b'\xe9'+struct.pack('<i',0x50af20-entry-len(code)-5))
    code.extend(b'\x4c\x8d\x05\x05\0\0\0')
    code.extend(b'\xe9'+struct.pack('<i',0x50af20-entry-len(code)-5))
    code.extend(struct.pack('<I',STORAGE_LIMIT))
    return bytes(code)

def append_support(original,pe,rva,body,overwrite,enabled,damage_enabled=False):
    _append_attrs(original,pe,rva,body,overwrite,enabled)
    if not damage_enabled:return
    # The damage formula clamps to martial power * rank coefficient, then to
    # a second hard ceiling (10 million). Replace both maxima, retain minima.
    checks={7766944: b'\xe8\xbbz\x01\x00', 7766958: b'\x0f/\x05Gj\xac\x00', 7767029: b'\xf3\x0f\x10\x05\xffi\xac\x00'}
    for at,want in checks.items():
        off=pe.get_offset_from_rva(at)
        if original[off:off+len(want)]!=want:raise ValueError('单次伤害上限入口被其他 MOD 修改：'+hex(at))
    from keystone import Ks,KS_ARCH_X86,KS_MODE_64
    body.extend(DAMAGE_MAGIC);body.extend(bytes(-len(body)%16))
    integer=rva+len(body);body.extend(struct.pack('<i',STORAGE_LIMIT))
    floating=rva+len(body);body.extend(struct.pack('<f',STORAGE_LIMIT))
    entry=rva+len(body)
    # Fixed-width encodings avoid assembler relaxation at different layouts.
    code=b'\x4c\x8d\x05'+struct.pack('<i',integer-entry-7)
    code+=b'\xe9'+struct.pack('<i',0x77fe60-entry-12)
    body.extend(code);body.extend(bytes(-len(body)%16))
    overwrite(pe.get_offset_from_rva(0x7683a0),b'\xe8'+struct.pack('<i',entry-0x7683a0-5))
    for at,prefix,size in [(0x7683ae,b'\x0f\x2f\x05',7),(0x7683f5,b'\xf3\x0f\x10\x05',8)]:
        overwrite(pe.get_offset_from_rva(at),prefix+struct.pack('<i',floating-at-size))

def certified_transition(before,after):
    from external_runtime import detach
    try:
        a,oa=detach(before);b,ob=detach(after)
        oa.pop('attribute_uncap',None);ob.pop('attribute_uncap',None)
        oa.pop('damage_uncap',None);ob.pop('damage_uncap',None)
        return a==b and oa==ob
    except (ValueError,KeyError,struct.error):return False

def plan(root,enabled=True,damage=True,independent_damage=False):
    from nov5_growth_runtime import patch_runtime
    from compatibility import validate_native_writes
    root=Path(root).resolve();path=root/'DreamRivakes_Data/Plugins/RaceLogic_Release_x64.dll'
    damage_enabled=bool(damage and (enabled or independent_damage))
    raw=path.read_bytes();after=patch_runtime(raw,attribute_uncap=bool(enabled),damage_uncap=damage_enabled)
    payloads={path:after} if after!=raw else {};originals={path:raw} if payloads else {}
    validate_native_writes(root,payloads,originals)
    results=['移除属性上限：'+('启用' if enabled else '关闭，恢复游戏原有上限'),
        '覆盖六项属性、八类精通、生命、真气、防御、速度、攻击及数值型命中/闪避/暴击等属性。',
        '当前游戏目录的全部人物、旧档和新档生效；重启游戏并读档后重新计算。',
        '保留属性下限及概率规则；解除常规上限，保留20亿数值保护线；不会自动增加属性。',
        '单次伤害上限：'+('移除武学品质上限与全局1000万上限，保留20亿保护线' if damage_enabled else '使用游戏原有上限'),
        '关闭后恢复原生计算限制，保留存档及人物基础配置。']
    return payloads,originals,results,[],{}
