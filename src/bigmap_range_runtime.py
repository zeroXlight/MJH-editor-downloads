# Generated for the exact certified big-map native build. See native mapping evidence.
"""Named areas at the native hit-grid lookup boundary (verified game build).

The helper returns positions to the existing target/damage pipeline. It never
changes cast vectors, target allegiance, damage formulas or martial state.
"""
import struct

HIT_GRID_RVA = 0x7050f0
HIT_GRID_PREFIX = bytes.fromhex('44 88 4c 24 20')
LEGACY_AREA_MAGIC = b'MJHAREA211\0'
AREA_MAGIC = b'MJHAREA212\0'

def validate_areas(areas):
    result=[];targets={}
    for entry in areas:
        source,target,level=(entry[k] for k in ('source','target','level'))
        if any(type(v) is not int or not 0<v<2**31 for v in (source,target)) or type(level) is not int or not 1<=level<=255:
            raise ValueError('技能范围战斗注册参数不正确')
        cells=entry['positions']
        if not cells or len(cells)>135 or any(len(p)!=2 or any(type(v) is not int for v in p) or not -7<=p[0]<=7 or not -4<=p[1]<=4 for p in cells):
            raise ValueError('技能范围战斗格子不正确')
        cells=[list(p) for p in cells]
        if len({tuple(p) for p in cells})!=len(cells):raise ValueError('技能范围战斗格子重复')
        if target in targets and targets[target]!=cells:raise ValueError('同一武学的战斗范围冲突')
        targets[target]=cells
        result.append({'source':source,'target':target,'level':level,'positions':cells})
    return sorted(result,key=lambda e:(e['target'],e['source'],e['level']))

def legacy_hit_grid_helper(rva,trampoline,areas):
    areas=validate_areas(areas);code=bytearray();fixups=[];labels={}
    def emit(hexcode):code.extend(bytes.fromhex(hexcode))
    def call(target):
        code.append(0xe8);code.extend(struct.pack('<i',target-(rva+len(code)+4)))
    def jump(op,label):
        code.extend(bytes.fromhex(op));fixups.append((len(code),label));code.extend(bytes(4))
    def label(name):labels[name]=len(code)
    def imm(value):code.extend(struct.pack('<i',value))
    # Five saved registers plus a 0x60 frame keep Windows x64 call alignment.
    # Original seventh argument (output vector) is now at rsp+0xc0.
    emit('53 56 57 41 54 41 55 48 83 ec 60')
    emit('48 8b d9 48 8b f2 45 8b e0 45 8b e9 48 8b bc 24 c0 00 00 00')
    emit('48 85 f6');jump('0f 84','fallback')
    for n,entry in enumerate(areas):
        next_rule=f'rule{n+1}'
        emit('81 be 90 01 00 00');imm(entry['target']);jump('0f 85',next_rule)
        emit('48 8b cb ba');imm(entry['source']);call(0x6fd9d0)
        emit('48 85 c0');jump('0f 84',next_rule)
        # +0x1a4 is embattle; +0x198 is the native current martial level.
        emit('80 b8 a4 01 00 00 00');jump('0f 84',next_rule)
        emit('80 b8 98 01 00 00');code.append(entry['level']);jump('0f 82',next_rule)
        emit('48 8b cf');call(0x4cd5b0) # clear output positions
        emit('48 8b cb');call(0x724210) # actual actor facing, +0xa8
        emit('89 44 24 40')
        for k,(x,y) in enumerate(entry['positions']):
            skip=f'cell{n}_{k}'
            emit('b8');imm(x);emit('0f af 44 24 40 44 01 e0 83 f8 07');jump('0f 87',skip)
            emit('ba');imm(y);emit('44 01 ea 83 fa 04');jump('0f 87',skip)
            emit('89 44 24 20 89 54 24 24 48 8d 54 24 20 48 8b cf');call(0x729710)
            label(skip)
        jump('e9','done');label(next_rule)
    label('fallback')
    emit('48 8b cb 48 8b d6 45 8b c4 45 8b cd')
    emit('48 83 c4 60 41 5d 41 5c 5f 5e 5b')
    code.append(0xe9);code.extend(struct.pack('<i',trampoline-(rva+len(code)+4)))
    label('done');emit('48 83 c4 60 41 5d 41 5c 5f 5e 5b c3')
    for pos,name in fixups:struct.pack_into('<i',code,pos,labels[name]-pos-4)
    return bytes(code)

def hit_grid_helper(rva,trampoline,areas):
    """Actor-centred cardinal rotation; cast coordinates only select direction.

    Stack args 5/6 are the actual actor position (including proposed movement).
    All original cast vectors and native cast-distance checks remain untouched.
    """
    areas=validate_areas(areas);code=bytearray();fixups=[];labels={}
    def emit(h):code.extend(bytes.fromhex(h))
    def imm(v):code.extend(struct.pack('<i',v))
    def call(v):code.append(0xe8);imm(v-(rva+len(code)+4))
    def jump(op,name):emit(op);fixups.append((len(code),name));imm(0)
    def label(name):labels[name]=len(code)
    emit('53 56 57 41 54 41 55 48 83 ec 60')
    emit('48 8b d9 48 8b f2 45 0f b6 e0 45 0f b6 e9 48 8b bc 24 c0 00 00 00')
    emit('0f b6 84 24 b0 00 00 00 89 44 24 44')
    emit('0f b6 84 24 b8 00 00 00 89 44 24 48')
    emit('48 85 f6');jump('0f 84','fallback')
    for n,e in enumerate(areas):
        nxt=f'rule{n+1}';oriented=f'orient{n}';horizontal=f'horizontal{n}';vertical=f'vertical{n}'
        emit('81 be 90 01 00 00');imm(e['target']);jump('0f 85',nxt)
        emit('48 8b cb ba');imm(e['source']);call(0x6fd9d0)
        emit('48 85 c0');jump('0f 84',nxt)
        emit('80 b8 a4 01 00 00 00');jump('0f 84',nxt)
        emit('80 b8 98 01 00 00');code.append(e['level']);jump('0f 82',nxt)
        emit('48 8b cf');call(0x4cd5b0)
        emit('48 8b cb');call(0x724210)
        emit('89 44 24 40 c7 44 24 4c 00 00 00 00') # forward basis fx,fy
        if len(e['positions'])==135:
            # Full-screen is absolute battlefield coverage, never a rotated rectangle.
            emit('c7 44 24 40 01 00 00 00')
        else:
            emit('44 89 e0 2b 44 24 44 44 89 ea 2b 54 24 48') # cast minus actor
            emit('41 89 c0 41 f7 d8 85 c0 44 0f 49 c0') # abs dx
            emit('41 89 d1 41 f7 d9 85 d2 44 0f 49 ca') # abs dy
            emit('45 39 c8');jump('0f 8d',horizontal)
            emit('85 d2');jump('0f 8c',vertical)
            emit('c7 44 24 4c 01 00 00 00');jump('e9',oriented)
            label(vertical);emit('c7 44 24 4c ff ff ff ff');jump('e9',oriented)
            label(horizontal);emit('85 c0');jump('0f 84',oriented)
            emit('b9 01 00 00 00 41 b8 ff ff ff ff 41 0f 48 c8 89 4c 24 40')
            jump('e9',oriented)
            label(oriented)
            # Vertical basis has zero horizontal component.
            emit('83 7c 24 4c 00');jump('0f 84',f'basis{n}')
            emit('c7 44 24 40 00 00 00 00');label(f'basis{n}')
        for k,(x,y) in enumerate(e['positions']):
            skip=f'cell{n}_{k}'
            emit('b8');imm(x);emit('0f af 44 24 40 ba');imm(y)
            emit('0f af 54 24 4c 29 d0 03 44 24 44 83 f8 07');jump('0f 87',skip)
            emit('ba');imm(x);emit('0f af 54 24 4c b9');imm(y)
            emit('0f af 4c 24 40 01 ca 03 54 24 48 83 fa 04');jump('0f 87',skip)
            emit('89 44 24 20 89 54 24 24 48 8d 54 24 20 48 8b cf');call(0x729710)
            label(skip)
        jump('e9','done');label(nxt)
    label('fallback');emit('48 8b cb 48 8b d6 45 8b c4 45 8b cd')
    emit('48 83 c4 60 41 5d 41 5c 5f 5e 5b')
    code.append(0xe9);imm(trampoline-(rva+len(code)+4))
    label('done');emit('48 83 c4 60 41 5d 41 5c 5f 5e 5b c3')
    for pos,name in fixups:struct.pack_into('<i',code,pos,labels[name]-pos-4)
    return bytes(code)
