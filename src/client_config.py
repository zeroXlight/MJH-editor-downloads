"""Read literal Lua tables, without executing Lua, and preserve Unity assets on edits."""
import hashlib, mmap, re, struct
from pathlib import Path

EFFECT_KEYS = ('BlueGift', 'BlueGiftUnlockLv', 'BlueAttr', 'BlueAttrValue', 'BlueAttrUnlockLv', 'BlueMartial')

class Assets:
    def __init__(self, data):
        self.data = data
        meta_size, size, version, self.start = struct.unpack_from('>4I', data)
        if version != 17 or size != len(data) or data[16] != 0:
            raise ValueError('不支持此客户端资源格式，未修改文件')
        p = data.find(b'\0', 20) + 1
        if p <= 20: raise ValueError('客户端资源头无效')
        p += 4
        if data[p]: raise ValueError('客户端资源包含未支持的类型树')
        p += 1
        count = struct.unpack_from('<I', data, p)[0]; p += 4
        if count > 10000: raise ValueError('客户端资源类型表无效')
        types = []
        for _ in range(count):
            kind = struct.unpack_from('<i', data, p)[0]; types.append(kind)
            p += 7 + (16 if kind == 114 else 0) + 16
        count = struct.unpack_from('<I', data, p)[0]; p += 4
        if count > 1000000: raise ValueError('客户端资源对象表无效')
        self.objects = []; self.scripts = {}
        for _ in range(count):
            p = (p + 3) & ~3
            ident, off, length, typ = struct.unpack_from('<qIIi', data, p)
            if not 0 <= typ < len(types) or self.start + off + length > len(data):
                raise ValueError('客户端资源对象越界')
            obj = {'meta': p, 'id': ident, 'off': off, 'length': length, 'kind': types[typ]}
            self.objects.append(obj); p += 20
            if obj['kind'] == 49:
                q = self.start + off; n = struct.unpack_from('<I', data, q)[0]
                if n > length - 8: raise ValueError('客户端文本资源名称无效')
                name = data[q + 4:q + 4 + n].decode('utf-8')
                q = (q + 4 + n + 3) & ~3
                n = struct.unpack_from('<I', data, q)[0]
                if q + 4 + n > self.start + off + length: raise ValueError('客户端文本资源越界')
                if name in self.scripts and (name in ('Item.lua', 'Gift.lua', 'Enum.lua') or name.startswith('Language')):
                    raise ValueError(f'客户端配置资源重名：{name}')
                self.scripts[name] = (obj, q, n)
        if p > 20 + meta_size or p > self.start: raise ValueError('客户端资源元数据越界')

    def script(self, name):
        if name not in self.scripts: raise ValueError(f'客户端缺少 {name}')
        _, q, n = self.scripts[name]
        return self.data[q + 4:q + 4 + n].decode('utf-8-sig')

    def replace_script(self, name, text):
        return self.replace_blob(name, text.encode('utf-8'))

    def replace_blobs(self, replacements, normalize=False):
        """Replace several TextAssets with one full-file allocation."""
        blocks = {}
        for name, raw in replacements.items():
            obj, q, n = self.scripts[name]
            start = self.start + obj['off']; end = start + obj['length']
            tail = (q + 4 + n + 3) & ~3
            if tail == end and self.data[q+4:q+4+n] == raw:
                continue
            suffix = self.data[tail:end]
            if len(suffix) <= 8 and not any(suffix): suffix = b''
            block = self.data[start:q] + struct.pack('<I', len(raw)) + raw
            block += bytes((-len(block)) % 4) + suffix
            length = len(block)
            block += bytes((obj['length'] - length) % 8)
            blocks[obj['meta']] = (block, length)
        header = bytearray(self.data[:self.start]); changed = bool(blocks)
        if normalize:
            for obj, q, n in self.scripts.values():
                tail = (q+4+n+3)&~3; end = self.start+obj['off']+obj['length']
                if obj['meta'] not in blocks and 0 < end-tail <= 8 and not any(self.data[tail:end]):
                    struct.pack_into('<I', header, obj['meta']+12, tail-self.start-obj['off'])
                    changed = True
        if not changed: return self.data
        source = memoryview(self.data); chunks = [header]; cursor = self.start; delta = 0
        for obj in sorted(self.objects, key=lambda item: item['off']):
            start = self.start+obj['off']; end = start+obj['length']
            if start < cursor: raise ValueError('客户端资源对象重叠')
            struct.pack_into('<I', header, obj['meta']+8, obj['off']+delta)
            if obj['meta'] not in blocks: continue
            block, length = blocks[obj['meta']]
            chunks.extend((source[cursor:start], block)); cursor = end
            struct.pack_into('<I', header, obj['meta']+12, length)
            delta += len(block)-obj['length']
        chunks.append(source[cursor:])
        struct.pack_into('>I', header, 4, len(self.data)+delta)
        return b''.join(chunks)

    def normalize_text_lengths(self):
        # TextAsset ends after its aligned byte array. Storage gaps belong
        # between objects, not inside the serialized object byte size.
        fixes=[]
        for obj,q,n in self.scripts.values():
            tail=(q+4+n+3)&~3;end=self.start+obj['off']+obj['length']
            if 0<end-tail<=8 and not any(self.data[tail:end]):
                fixes.append((obj['meta']+12,tail-self.start-obj['off']))
        if not fixes:return self.data if isinstance(self.data,bytes) else bytes(self.data)
        out=bytearray(self.data)
        for position,length in fixes:struct.pack_into('<I',out,position,length)
        return bytes(out)

    def replace_blob(self, name, raw):
        obj, q, n = self.scripts[name]
        old_start = self.start + obj['off']; old_end = old_start + obj['length']
        tail = (q + 4 + n + 3) & ~3
        if tail==old_end and self.data[q+4:q+4+n]==raw:
            return self.data if isinstance(self.data,bytes) else bytes(self.data)
        block = self.data[old_start:q] + struct.pack('<I', len(raw)) + raw
        suffix=self.data[tail:old_end]
        if len(suffix)<=8 and not any(suffix):suffix=b''
        block += bytes((-len(block)) % 4) + suffix
        serialized_length=len(block)
        # Preserve the following object's original alignment as well as all gaps.
        block += bytes((obj['length'] - len(block)) % 8)
        delta = len(block) - obj['length']
        out = bytearray(len(self.data)+delta)
        with memoryview(self.data) as source,memoryview(out) as destination:
            destination[:old_start]=source[:old_start]
            destination[old_start:old_start+len(block)]=block
            destination[old_start+len(block):]=source[old_end:]
        struct.pack_into('>I', out, 4, len(out))
        for other in self.objects:
            if other is obj: struct.pack_into('<I', out, other['meta'] + 12, serialized_length)
            elif other['off'] >= obj['off'] + obj['length']:
                struct.pack_into('<I', out, other['meta'] + 8, other['off'] + delta)
            elif other is not obj and other['off'] + other['length'] > obj['off']:
                raise ValueError('客户端资源对象重叠')
        return bytes(out)

def enum_values(text):
    out = {}
    for name, body in re.findall(r'(?m)^\s*(\w+)\s*=\s*\{(.*?)^\s*\}', text, re.S):
        for key, value in re.findall(r'(?m)^\s*(\w+)\s*=\s*(-?\d+)\s*[;,]', body):
            out[name + '.' + key] = int(value)
    return out

def literal(text, enums):
    tokens = re.findall(r'"(?:\\.|[^"\\])*"|-?\d+(?:\.\d+)?|[A-Za-z_][\w.]*|[{}=,|]', text)
    pos = 0
    def read_atom():
        nonlocal pos
        if pos >= len(tokens): raise ValueError('客户端 Lua 表被截断')
        token = tokens[pos]; pos += 1
        if token == '{':
            rows = []; named = {}
            while pos < len(tokens) and tokens[pos] != '}':
                if pos + 1 < len(tokens) and tokens[pos + 1] == '=':
                    key = tokens[pos]; pos += 2; named[key] = read()
                else: rows.append(read())
                if pos < len(tokens) and tokens[pos] == ',': pos += 1
            if pos >= len(tokens): raise ValueError('客户端 Lua 表被截断')
            pos += 1
            if named and rows: raise ValueError('客户端 Lua 表混用字段与数组')
            return {k:v for k,v in named.items() if v is not None} if named else rows
        if token.startswith('"'):
            return re.sub(r'\\([\\"nrt])', lambda m: {'n':'\n','r':'\r','t':'\t'}.get(m[1], m[1]), token[1:-1])
        if re.fullmatch(r'-?\d+', token): return int(token)
        if re.fullmatch(r'-?\d+\.\d+', token): return float(token)
        if token in enums: return enums[token]
        if token in ('true', 'false'): return token == 'true'
        if token == 'nil': return None
        raise ValueError(f'客户端 Lua 表中有未识别的常量：{token}')
    def read():
        nonlocal pos
        value=read_atom()
        while pos<len(tokens) and tokens[pos]=='|':
            pos+=1;other=read_atom()
            if not isinstance(value,int) or not isinstance(other,int):raise ValueError('客户端 Lua 标志必须为整数')
            value|=other
        return value
    value = read()
    if pos != len(tokens): raise ValueError('客户端 Lua 表有额外内容')
    return value

def lua_rows(text, name, enums):
    default = re.search(r'(?m)^local ' + re.escape(name) + r'Default\s*=\s*(\{[^\r\n]+)', text)
    defaults = literal(default[1], enums) if default else {}
    out = {}
    for ident, body in re.findall(r'(?m)^\s*\[(\d+)\]\s*=\s*(\{[^\r\n]+)', text):
        row = literal(body.rstrip().rstrip(','), enums)
        if row.get('BaseID') != int(ident): raise ValueError(f'客户端 {name} 表记录 ID 不一致：索引 {ident}，记录 {row.get("BaseID")}')
        out[int(ident)] = {**defaults, **row}
    if not out: raise ValueError(f'未读取到客户端 {name} 表')
    return out

def patch_effects(text, effects):
    seen = set()
    def replace(match):
        ident = int(match[2])
        if ident not in effects: return match[0]
        seen.add(ident); body = match[3]
        for key in EFFECT_KEYS:
            body = re.sub(r'\b' + key + r'\s*=\s*\{[^{}]*\}\s*,?', '', body)
        addition = ''.join(key + '={' + ','.join(str(int(v)) for v in effects[ident][key]) + '},' for key in EFFECT_KEYS)
        return match[1] + body + addition + '},' + match[4]
    result = re.sub(r'(?m)^([ \t]*\[(\d+)\]\s*=\s*\{)([^\r\n]+)\},([ \t]*\r?)$', replace, text)
    if seen != set(effects): raise ValueError('客户端装备配置缺少待修改型号')
    return result

def load_client(path):
    with Path(path).open('rb') as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as data:
        assets = Assets(data)
        enums = enum_values(assets.script('common.lua'))
        enums.update(enum_values(assets.script('Enum.lua')))
        item_text = assets.script('Item.lua')
        enums.update(enum_values(item_text))
        items = lua_rows(item_text, 'Item', enums)
        gift_text = assets.script('Gift.lua'); enums.update(enum_values(gift_text))
        gifts = lua_rows(gift_text, 'Gift', enums)
        wanted = {v for g in gifts.values() for k, v in g.items() if k in ('NameID', 'DescID')}
        lang = {}
        from read_cache import language_script
        for name in assets.scripts:
            if not re.fullmatch(r'Language\d+\.lua', name): continue
            for ident, value in language_script(assets.script(name)):
                if ident in wanted: lang[ident] = {'Ch_Text': value}
        return items, gifts, lang, item_text, enums, hashlib.sha256(data).hexdigest()
