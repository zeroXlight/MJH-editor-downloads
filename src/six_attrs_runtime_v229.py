"""Reversible native selectors and full attribute notifications; save ABI unchanged."""
import struct

MAGIC=b'MJHSIXATTR227\0'
ATTACKS={1:27,2:23,3:22,4:29,5:26,7:24,8:25,9:28}

def relative(op,target,origin):return op+struct.pack('<i',target-origin-5)

def selector(martial):
    # Called in place of MOV EDX,145. Preserve RAX and RCX; no nested calls.
    # The caller's original argument remains in its home slot.
    code=bytearray(b'\x50')
    if martial:
        code=bytearray(bytes.fromhex('50 48 8b 84 24 c8 00 00 00 48 85 c0'))
        jumps=[]
        def nulljump():
            code.extend(b'\x0f\x84');jumps.append(len(code));code.extend(bytes(4))
        nulljump();code.extend(bytes.fromhex('48 8b 80 80 00 00 00 48 85 c0'));nulljump()
        code.extend(bytes.fromhex('8b 80 a4 00 00 00'))
    else:
        code.extend(bytes.fromhex('8b 44 24 48')) # home EDX, including CALL+PUSH
        jumps=[]
    destinations=[]
    for depart,attr in ATTACKS.items():
        code.extend(b'\x83\xf8'+bytes([depart])+b'\x75\x07\xba'+struct.pack('<I',attr)+b'\xeb')
        destinations.append(len(code));code.append(0)
    fallback=len(code);code.extend(b'\xba'+struct.pack('<I',99))
    end=len(code);code.extend(b'\x58\xc3')
    for pos in jumps:struct.pack_into('<i',code,pos,fallback-pos-4)
    for pos in destinations:code[pos]=end-pos-1
    return bytes(code)

def sum_attack(rva):
    # RCX=unit, EDX=selected attack. 99 is the original general base attack.
    c=bytearray(bytes.fromhex('48 83 ec 38 48 89 4c 24 20 89 54 24 2c'))
    c.extend(relative(b'\xe8',0x6f0820,rva+len(c)))
    c.extend(bytes.fromhex('83 7c 24 2c 63 74 1c 89 44 24 28 48 8b 4c 24 20 ba 63 00 00 00'))
    c.extend(relative(b'\xe8',0x6f0820,rva+len(c)))
    c.extend(bytes.fromhex('03 44 24 28 48 83 c4 38 c3'))
    # JE returns directly when fallback selected base 99 (do not add twice).
    c[24]=len(c)-5-25
    return bytes(c)

def append_support(original,pe,rva,body,overwrite,enabled):
    if not enabled:return
    body.extend(MAGIC);body.extend(bytes(-len(body)%16))
    def hook(at,expected,build):
        off=pe.get_offset_from_rva(at)
        if original[off:off+len(expected)]!=expected:raise ValueError('六属性入口被其他 MOD 修改：'+hex(at))
        entry=rva+len(body);body.extend(build(entry));body.extend(bytes(-len(body)%16))
        overwrite(off,relative(b'\xe8',entry,at))
    hook(0x6f09ac,bytes.fromhex('ba 91 00 00 00'),lambda entry:selector(True))
    hook(0x6fc36d,bytes.fromhex('ba 91 00 00 00'),lambda entry:selector(False))
    for at in (0x6f09b9,0x6fc377):hook(at,relative(b'\xe8',0x6f0820,at),sum_attack)
    def notification(entry):
        c=bytearray(bytes.fromhex('48 83 ec 38 48 89 4c 24 20'))
        c.extend(relative(b'\xe8',0x4ced90,entry+len(c)))
        for attr in (4,5,6,8,22,23,24,25,26,27,28,29,93,99):
            c.extend(bytes.fromhex('48 8b 4c 24 20 c7 44 24 28')+struct.pack('<I',attr)+bytes.fromhex('48 8d 54 24 28'))
            c.extend(relative(b'\xe8',0x4ced90,entry+len(c)))
        c.extend(bytes.fromhex('48 83 c4 38 c3'));return bytes(c)
    hook(0x48577d,relative(b'\xe8',0x4ced90,0x48577d),notification)

def certified_transition(before,after):
    from external_runtime import detach
    try:
        a,oa=detach(before);b,ob=detach(after)
        oa.pop('six_attrs',None);ob.pop('six_attrs',None)
        return a==b and oa==ob
    except (ValueError,KeyError,struct.error):return False
