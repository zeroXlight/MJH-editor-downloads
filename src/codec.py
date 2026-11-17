"""Lossless protobuf wire editing. Unknown fields and table hashes stay intact."""
from dataclasses import dataclass
import struct

def read_varint(data, pos):
    value = 0
    for shift in range(0, 70, 7):
        if pos >= len(data): raise ValueError('配置数据被截断')
        byte = data[pos]; pos += 1
        value |= (byte & 127) << shift
        if byte < 128: return value, pos
    raise ValueError('配置数据的整数编码无效')

def varint(value):
    value = int(value)
    if value < 0: value += 1 << 64
    result = bytearray()
    while value >= 128:
        result.append((value & 127) | 128); value >>= 7
    result.append(value)
    return bytes(result)

@dataclass
class Field:
    number: int
    wire: int
    value: object
    raw: bytes

def fields(data):
    result = []; pos = 0
    while pos < len(data):
        start = pos; tag, pos = read_varint(data, pos)
        number, wire = tag >> 3, tag & 7
        if not number: raise ValueError('配置数据字段号无效')
        if wire == 0: value, pos = read_varint(data, pos)
        elif wire == 2:
            length, pos = read_varint(data, pos)
            if length > len(data) - pos: raise ValueError('配置数据长度无效')
            value = data[pos:pos + length]; pos += length
        elif wire in (1, 5):
            length = 8 if wire == 1 else 4
            if pos + length > len(data): raise ValueError('配置数据长度无效')
            value = data[pos:pos + length]; pos += length
        else: raise ValueError(f'不支持的配置编码 {wire}')
        result.append(Field(number, wire, value, data[start:pos]))
    return result

def encoded(number, value, wire=0):
    if wire == 2: return varint((number << 3) | 2) + varint(len(value)) + value
    return varint(number << 3) + varint(value)

def values(data, number):
    return [f.value for f in fields(data) if f.number == number]

def patch(data, replacements):
    result = bytearray(); seen = set()
    for field in fields(data):
        if field.number not in replacements: result.extend(field.raw)
        elif field.number not in seen:
            result.extend(replacements[field.number]); seen.add(field.number)
    for number, replacement in replacements.items():
        if number not in seen: result.extend(replacement)
    return bytes(result)

def decode(data, name, schemas):
    schema = schemas[name]; by_number = {v['number']: (k, v) for k, v in schema.items()}
    out = {key: [] if spec['label'] == 3 else '' if spec['type'] == 9 else {} if spec['type'] == 11 else 0
           for key, spec in schema.items()}
    for field in fields(data):
        if field.number not in by_number: continue
        key, spec = by_number[field.number]; typ = spec['type']
        parts = [field.value]
        if field.wire == 2 and spec['label'] == 3 and typ not in (9, 11, 12):
            parts = []; pos = 0
            while pos < len(field.value):
                value, pos = read_varint(field.value, pos); parts.append(value)
        for value in parts:
            if typ == 9: value = value.decode('utf-8')
            elif typ == 11: value = decode(value, spec['type_name'].split('.')[-1], schemas)
            elif typ == 5 and value >= 1 << 31: value = (value & 0xffffffff) - (1 << 32)
            elif typ == 3 and value >= 1 << 63: value -= 1 << 64
            elif typ in (1, 2): value = struct.unpack('<d' if typ == 1 else '<f', value)[0] if isinstance(value, bytes) else value
            if spec['label'] == 3: out[key].append(value)
            else: out[key] = value
    return out

def numeric_list(number, seq):
    return b''.join(encoded(number, value) for value in seq)
