from pathlib import Path
from datetime import datetime
import ctypes, hashlib, json, os, shutil, struct, uuid
from codec import fields, values, decode, patch, encoded, numeric_list
from client_config import Assets, load_client, lua_rows, patch_effects, EFFECT_KEYS

APP_ROOT = Path(__file__).resolve().parent
DATA_ROOT = Path(getattr(__import__('sys'), '_MEIPASS', APP_ROOT))
SCHEMAS = json.loads((DATA_ROOT / 'schemas.json').read_text(encoding='utf-8'))
META = json.loads((DATA_ROOT / 'metadata.json').read_text(encoding='utf-8'))
MAX_VALUE = 0x1fffff

def digest(data): return hashlib.sha256(data).hexdigest()
def u32(data, pos): return struct.unpack_from('<I', data, pos)[0]
def clean(text):
    import re
    return re.sub(r'<[^>]*>', '', str(text)).replace('\\n', '\n').replace('\\r', '').strip()

def inventory_precedes(data, end):
    """Prove a 96-byte map boundary using the preceding 40-byte item map.

    Needed when semantic checks cannot identify every equipment record:
    other save maps can resemble equipment when their unused fields are zero.
    """
    # A 40-byte map ending here can start at only one residue modulo 40.
    # Avoid rescanning the other nine alignments for every rejected candidate.
    start = 19036 + (end - 4 - 19036) % 40
    for p in range(start, end, 40):
        count = u32(data, p)
        if count < 1 or p + 4 + count * 40 != end: continue
        previous = 0
        for index in range(count):
            off = p + 4 + index * 40
            ident = u32(data, off + 16); owner = u32(data, off + 20)
            typ = u32(data, off + 24); num = u32(data, off + 28)
            owner_type = data[off + 36]
            if data[off:off + 16] != bytes(16) or ident <= previous or not typ or not 0 < num <= 0x7fffffff: break
            if owner_type not in (0, 1, 2, 3, 9) or data[off + 37] > 100 or (owner_type == 0) != (owner == 0): break
            previous = ident
        else: return True
    return False

def skipped_records_note(save):
    """Describe excluded records without treating missing templates as unowned."""
    parts = []
    unowned = getattr(save, 'unowned_count', save.ignored_count)
    missing = getattr(save, 'unknown_count', 0)
    incompatible = getattr(save, 'incompatible_count', 0)
    if unowned: parts.append(f'{unowned} 条无归属记录')
    if missing: parts.append(f'{missing} 条缺失型号配置记录')
    if incompatible: parts.append(f'{incompatible} 条不兼容装备记录')
    return '已跳过 ' + '、'.join(parts) if parts else ''

def game_running():
    """Windows Toolhelp snapshot; checks the game across user sessions."""
    from ctypes import wintypes
    class Entry(ctypes.Structure):
        _fields_ = [('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD),
                    ('th32ProcessID', wintypes.DWORD), ('th32DefaultHeapID', ctypes.c_size_t),
                    ('th32ModuleID', wintypes.DWORD), ('cntThreads', wintypes.DWORD),
                    ('th32ParentProcessID', wintypes.DWORD), ('pcPriClassBase', wintypes.LONG),
                    ('dwFlags', wintypes.DWORD), ('szExeFile', wintypes.WCHAR * 260)]
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
    kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateToolhelp32Snapshot(2, 0)
    if handle == ctypes.c_void_p(-1).value: raise OSError('无法检查游戏进程，请重试')
    entry = Entry(); entry.dwSize = ctypes.sizeof(entry)
    try:
        ok = kernel.Process32FirstW(handle, ctypes.byref(entry))
        while ok:
            if entry.szExeFile.casefold() == 'dreamrivakes.exe': return True
            ok = kernel.Process32NextW(handle, ctypes.byref(entry))
        return False
    finally: kernel.CloseHandle(handle)

def ensure_closed():
    if game_running(): raise ValueError('请先完全退出梦江湖，再保存或恢复。游戏运行期间可以读取和编辑草稿。')

def table_rows(data):
    return [f.value for f in fields(data) if f.number == 2 and f.wire == 2]

class Catalog:
    def __init__(self, root):
        self.root = Path(root).resolve()
        if not (self.root / 'DreamRivakes.exe').is_file(): raise ValueError('请选择包含 DreamRivakes.exe 的游戏目录')
        from shadow_runtime import ensure
        self.shadow_status = ensure(self.root)
        self.snapshots = {}
        self.rows = {}; self.items = {}; self.gifts = {}; self.lang = {}; self.percent = {}; self.martials = {}
        for name, target in [('Item', self.items), ('Gift', self.gifts), ('Language', self.lang),
                             ('AttrIsPercent', self.percent), ('Martial', self.martials)]:
            path = self.root / 'TableData' / (name + '.bytes')
            data = path.read_bytes(); self.snapshots[path] = data
            if name=='Language':
                from read_cache import native_language
                target.update((i,dict(row)) for i,row in native_language(data));continue
            for row in table_rows(data):
                obj = decode(row, name, SCHEMAS); target[obj['BaseID']] = obj
                if name == 'Item': self.rows[obj['BaseID']] = row
        # The UI reads embedded Lua, not the server's protobuf table. A regenerated
        # GameProject can remove an override while leaving Item.bytes modified.
        self.client_path = self.root / 'DreamRivakes_Data/resources.assets'
        self.client_hash = None; self.client_text = None; self.client_enums = {}
        self.effect_source = '逻辑配置（无客户端资源）'
        if self.client_path.is_file():
            items, gifts, lang, self.client_text, self.client_enums, self.client_hash = load_client(self.client_path)
            for ident, row in items.items():
                native = self.items.get(ident, {})
                self.items[ident] = {**native, **{k: [] for k, spec in SCHEMAS['Item'].items() if spec['label'] == 3}, **row}
            for ident, row in gifts.items(): self.gifts.setdefault(ident, {}).update(row)
            self.lang.update(lang)
            self.effect_source = '游戏客户端配置'
        # The UI also loads external client configuration. Overlay the user's active mod.
        self.json_dir = self.root / 'ModProject/GameProject/Mod_MJH/Json'
        self.own_json = self.json_dir / 'Item_warehouse_editor.json'
        self.other_item_overrides = set()
        self.item_sources = {}
        self.mod_warnings = []
        from mod_rows import table_name
        mod_targets = {'Item': self.items, 'Gift': self.gifts, 'Language': self.lang,
                       'AttrIsPercent': self.percent, 'Martial': self.martials}
        if self.json_dir.is_dir():
            for path in sorted(self.json_dir.glob('*.json')):
                kind = table_name(path)
                if kind not in mod_targets: continue
                data = path.read_bytes(); self.snapshots[path] = data
                from mod_rows import read_rows
                for row in read_rows(data,kind,SCHEMAS,self.mod_warnings,path.name):
                    ident = int(row['BaseID'])
                    if kind == 'Item':
                        if path != self.own_json: self.other_item_overrides.add(ident)
                        if ident <= 0 or not isinstance(row.get('Feature', []), list):
                            self.mod_warnings.append(f'{path.name}：型号 {ident} 格式无效，已跳过')
                            continue
                        self.item_sources.setdefault(ident, []).append(path)
                        defaults = {k: [] if s['label'] == 3 else '' if s['type'] == 9 else 0
                                    for k, s in SCHEMAS['Item'].items()}
                        self.items.setdefault(ident, defaults).update(row)
                    elif kind == 'Gift':
                        self.gifts.setdefault(ident, {}).update(row)
                    elif kind == 'Language':
                        self.lang[ident] = {'Ch_Text': row.get('Text', row.get('Ch_Text', ''))}
                    else:
                        mod_targets[kind].setdefault(ident, {}).update(row)
        self.own_original = self.own_json.read_bytes() if self.own_json.exists() else None
        self.own_rows = {}
        if self.own_original:
            from mod_rows import read_rows
            self.own_rows = {int(x['BaseID']): x for x in read_rows(self.own_original,'Item',SCHEMAS,self.mod_warnings,self.own_json.name)}
        self.validate_runtime()

    def validate_runtime(self):
        """Certification can change independently of the resource snapshot."""
        self.supported = True
        self.runtime_notes = []
        for filename, expected in META['native_hashes'].items():
            path = self.root / 'DreamRivakes_Data/Plugins' / filename
            if not path.exists():
                self.supported=False;self.runtime_notes.append(filename+' 缺失');continue
            raw=path.read_bytes()
            if filename=='RaceLogic_Release_x64.dll':
                from bigmap_profile import race_parent
                if race_parent(raw):continue
            if filename=='ClientDll.dll':
                from shadow_runtime import client_supported
                if client_supported(self.root,raw):continue
            if digest(raw)!=expected:
                from growth_runtime import supported_patch
                if filename!='RaceLogic_Release_x64.dll' or not supported_patch(raw):
                    self.supported=False;self.runtime_notes.append(filename+' 与已认证运行库不同')

    def text(self, ident): return clean(self.lang.get(int(ident), {}).get('Ch_Text', ident))
    def attr(self, ident): return META['attributes'].get(str(ident), f'属性 {ident}')
    def gift_label(self, ident):
        gift = self.gifts.get(ident, {})
        return f"{ident} · {self.text(gift.get('NameID', ident))}"
    def gift_desc(self, ident):
        return self.text(self.gifts.get(ident, {}).get('DescID', ident))
    def is_equipment(self, ident): return 1 in self.items.get(ident, {}).get('Feature', [])
    def saves(self):
        out = []
        path = self.root / 'Save.sav'
        if path.is_file(): out.append(('自动存档', path))
        base = self.root / 'SaveFile'
        if base.is_dir():
            for folder in sorted(base.iterdir()):
                path = folder / 'Save.sav'
                if path.is_file(): out.append((folder.name, path))
        return out
    def format_value(self, ident, value):
        data = self.percent.get(ident, {})
        v = value / 10000 if data.get('PerMyriad') == 1 else value
        if data.get('ShowAsPercent') == 1: return f'{v * 100:g}%'
        return f'{v:g}'

class Save:
    def __init__(self, path, catalog, data=None):
        self.path = Path(path); self.catalog = catalog
        self.data = self.path.read_bytes() if data is None else bytes(data)
        self.records = []; self.tables = []
        b = self.data
        from save_format import validate_reader_header
        self.header_kind=validate_reader_header(b)
        if len(b)<19036:raise ValueError('存档不包含支持的装备数据范围，未修改文件')
        self.main_role = u32(b, 9616)
        native_boundary = None
        try:
            # A complete native ABI proves the map boundary without guessing
            # whether another manager's owner enum is a supported equipment enum.
            # Shadow saves can retain owner=0/type=29 inventory entries; those
            # unrelated bytes must not prevent reading the equipment manager.
            from feature_save import NativeSave, STRIDES
            native = NativeSave(b)
            native.indexed(23); native.indexed(24)
            native_boundary = 760 + sum(4+len(rows)*STRIDES[i] for i,rows in enumerate(native.tables[:24]))
            self.main_role = u32(native.script(),20)
        except ValueError:
            pass  # Retain the old independent boundary proof for other layouts.
        # Locate complete count-prefixed maps, not isolated occurrences of item IDs.
        next_end = 0
        positions=(native_boundary,) if native_boundary is not None else range(19036,len(b)-100,4)
        for p in positions:
            if p < next_end: continue
            count = u32(b, p)
            if count < 1 or count > 100000 or p + 4 + count * 96 > len(b): continue
            q = p + 4
            first_unowned = u32(b, q + 20) == 0 and b[q + 34] == 0
            if b[q:q + 16] != bytes(16) or not u32(b, q + 16): continue
            first_supported = catalog.is_equipment(u32(b, q + 24)) or first_unowned
            records = []; previous = 0
            for index in range(count):
                off = q + index * 96
                ident = u32(b, off + 16); typ = u32(b, off + 24)
                if b[off:off + 16] != bytes(16) or ident <= previous: break
                owner = u32(b, off + 20); owner_type = b[off + 34]
                # Retained unowned records may contain stale script, equip,
                # item or attribute values. Keep their structural position and
                # raw bytes, but exclude them from editing and semantic checks.
                unowned = owner == 0 and owner_type == 0
                missing = typ not in catalog.items
                errors = []; warnings = []
                if not unowned:
                    if missing: errors.append('缺失型号配置')
                    elif not catalog.is_equipment(typ): errors.append('型号不是装备')
                    if owner == 0 or owner_type not in (1, 2, 3, 9): errors.append('归属标记不兼容')
                    if b[off + 32] > 20: errors.append('强化等级超出支持范围')
                    if b[off + 35] > 20 or b[off + 36] > 100: errors.append('穿戴或剧本标记不兼容')
                    for start in range(40, 84, 4):
                        value = u32(b, off + start)
                        attr = (value >> 21) & 1023 if 48 <= start <= 72 else value >> 21
                        if value and str(attr) not in META['attributes']:
                            warnings.append(f'属性 {attr} 未识别，所在属性组原样保留')
                reason = 'unowned' if unowned else ('unknown_item' if missing else ('incompatible' if errors else ''))
                record = {'offset': off, 'id': ident, 'type': typ, 'owner': u32(b, off + 20),
                          'owner_type': b[off + 34], 'script': b[off + 36], 'grade': b[off + 32],
                          'equipped': b[off + 35], 'name': catalog.items.get(typ, {}).get('ItemName', '未归属装备'),
                          'ignored': bool(reason), 'skip_reason': reason, 'validation_errors': errors,
                          'editable': not reason, 'compatibility_warnings': warnings}
                records.append(record); previous = ident
            if len(records) != count: continue
            # Semantic failures exclude just that row, after its fixed map
            # boundary is proven independently. Never infer an address from
            # an isolated item ID or delete/renumber excluded records.
            needs_boundary = (not first_supported or not any(r['editable'] for r in records) or
                              any(r['skip_reason'] in ('unknown_item', 'incompatible') or
                                  r['compatibility_warnings'] for r in records) or
                              not getattr(catalog, 'supported', True))
            boundary = (p==native_boundary if native_boundary is not None else inventory_precedes(b,p)) if needs_boundary else False
            if needs_boundary and not boundary: continue
            if any(catalog.is_equipment(r['type']) for r in records) or (
                boundary and any(r['skip_reason'] == 'unknown_item' for r in records)
            ):
                self.tables.append((p, count)); self.records.extend(records)
                next_end = p + 4 + count * 96
        if not self.tables: raise ValueError('未找到完整装备表，存档记录可能不兼容。未修改文件。')
        self.ignored_count = sum(r['ignored'] for r in self.records)
        self.unowned_count = sum(r['skip_reason'] == 'unowned' for r in self.records)
        self.unknown_count = sum(r['skip_reason'] == 'unknown_item' for r in self.records)
        self.incompatible_count = sum(r['skip_reason'] == 'incompatible' for r in self.records)
        offsets = [r['offset'] for r in self.records]
        if len(set(offsets)) != len(offsets): raise ValueError('装备表存在重叠，停止读取')

    def location(self, record):
        if record['owner'] == 0 and record['owner_type'] == 0: return '未归属'
        # Ending a run clears the script ID but retains former role/equip IDs.
        # Those IDs are provenance, not the item's current warehouse location.
        if record['script'] == 0 and record['owner_type'] == 2: return '周目仓库'
        if record['owner'] == self.main_role: return '主角背包/穿戴'
        return f"其他角色 {record['owner']}"

    def draft(self, record):
        off = record['offset']; groups = {'white': [], 'green': [], 'blue': []}
        for key, start, count in [('white', 40, 2), ('green', 48, 7), ('blue', 76, 2)]:
            for index in range(count):
                packed = u32(self.data, off + start + index * 4)
                if packed:
                    groups[key].append({'type': packed >> 21 if key != 'green' else (packed >> 21) & 1023,
                                        'value': packed & MAX_VALUE,
                                        'fixed': bool(packed & 0x80000000) if key == 'green' else False})
        return {'grade': record['grade'], **groups}

    def patched(self, drafts, skip_errors=False):
        out = bytearray(self.data); known = {r['offset']: r for r in self.records}; allowed = set()
        self.last_record_skips = {}; accepted = {}
        for off, draft in drafts.items():
            try:
                if off not in known: raise ValueError('装备记录已失效')
                if not known[off]['editable']: raise ValueError('此记录不是可编辑装备')
                grade = int(draft['grade'])
                if not 0 <= grade <= 20: raise ValueError('当前版本支持强化等级 0～20')
                original = self.draft(known[off])
                if grade != original['grade']:
                    out[off + 32] = grade; allowed.add(off + 32)
                for key, start, count in [('white', 40, 2), ('green', 48, 7), ('blue', 76, 2)]:
                    rows = draft[key]
                    if rows == original[key]: continue
                    if any(str(r['type']) not in META['attributes'] for r in original[key]):
                        raise ValueError('此属性组包含 MOD 未知属性，请保留原值；仍可修改强化等级及其他已识别属性组')
                    if len(rows) > count: raise ValueError(f'{key} 属性槽位超限')
                    allowed.update(range(off + start, off + start + count * 4))
                    for index in range(count):
                        packed = 0
                        if index < len(rows):
                            row = rows[index]; typ = int(row['type']); value = int(row['value'])
                            if not 1 <= typ <= 396 or str(typ) not in META['attributes']: raise ValueError(f'属性 ID 无效：{typ}')
                            if not 0 <= value <= MAX_VALUE: raise ValueError(f'存档原始数值范围为 0～{MAX_VALUE}')
                            packed = (typ << 21) | value
                            if key == 'green' and row.get('fixed'): packed |= 0x80000000
                        struct.pack_into('<I', out, off + start + index * 4, packed)
                accepted[off] = draft
            except (ValueError,KeyError,TypeError,OverflowError) as error:
                if not skip_errors: raise
                self.last_record_skips[off] = str(error)
                if off in known:
                    out[off:off+96] = self.data[off:off+96]
                    allowed.difference_update(range(off,off+96))
        if len(out) != len(self.data) or any(a != b and i not in allowed for i, (a, b) in enumerate(zip(self.data, out))):
            raise ValueError('写入超出本次修改字段范围，停止保存')
        check = Save(self.path, self.catalog, out)
        if self.tables != check.tables: raise ValueError('写入结果的装备表结构验证失败')
        if [(r['offset'], r['id'], r['type'], r['owner']) for r in check.records] != [(r['offset'], r['id'], r['type'], r['owner']) for r in self.records]:
            raise ValueError('写入结果的装备身份验证失败')
        for off, draft in accepted.items():
            record = next(x for x in check.records if x['offset'] == off)
            if check.draft(record) != draft: raise ValueError('写入结果的词条回读验证失败')
        return bytes(out)

def effect_draft(item):
    gift_ids = item.get('BlueGift', []); gift_lv = item.get('BlueGiftUnlockLv', [])
    attrs = item.get('BlueAttr', []); vals = item.get('BlueAttrValue', [])
    levels = item.get('BlueAttrUnlockLv', []); martials = item.get('BlueMartial', [])
    return {'gifts': [{'id': ident, 'level': gift_lv[i] if i < len(gift_lv) else 0} for i, ident in enumerate(gift_ids)],
            'attrs': [{'type': ident, 'value': vals[i] if i < len(vals) else 0,
                       'level': levels[i] if i < len(levels) else 0,
                       'martial': martials[i] if i < len(martials) else 0} for i, ident in enumerate(attrs)]}

def effect_payloads(catalog, drafts, skip_errors=False):
    catalog.last_effect_skips = {}
    if not drafts: return {}
    rows = {}; client = dict(catalog.own_rows); lua_effects = {}; mod_documents = {}; result = {}
    expected = {p for p in catalog.snapshots if p.parent == catalog.json_dir}
    from mod_rows import table_name
    from collections import Counter
    current = {p for p in catalog.json_dir.glob('*.json') if table_name(p) in ('Item', 'Gift', 'Language', 'AttrIsPercent', 'Martial')}
    for ident, draft in drafts.items():
        edited_mod_row = None
        try:
            if current != expected: raise ValueError('模组文件列表在读取后发生变化，请重新读取；单件存档修改仍可保存')
            if not catalog.is_equipment(ident): raise ValueError(f'型号 {ident} 不是已识别装备')
            sources = getattr(catalog, 'item_sources', {}).get(ident, [])
            external = [p for p in sources if p != catalog.own_json]
            if ident in catalog.other_item_overrides and (len(sources) != 1 or len(external) != 1):
                names = '、'.join(p.name for p in sources)
                raise ValueError(f'装备 {ident} 存在多个 MOD 配置来源，无法确认加载优先级：{names}；仍可保存单件强化等级和数值')
            if len(draft['gifts']) + len(draft['attrs']) > 4096: raise ValueError('单件装备最多编辑 4096 条强化效果')
            baseline = effect_draft(catalog.items[ident])
            old_gifts = Counter((r['id'], r['level']) for r in baseline['gifts'])
            old_attrs = Counter((r['type'], r['value'], r['level'], r['martial']) for r in baseline['attrs'])
            for row in draft['gifts']:
                if row['id'] not in catalog.gifts:
                    key = (row['id'], row['level'])
                    if old_gifts[key] <= 0: raise ValueError(f"找不到天赋 ID：{row['id']}；现有未知效果可以原样保留")
                    old_gifts[key] -= 1
                    continue
                if not 0 <= row['level'] <= 20: raise ValueError('解锁等级范围为 0～20')
            for row in draft['attrs']:
                if str(row['type']) not in META['attributes'] or row['martial'] and row['martial'] not in catalog.martials:
                    key = (row['type'], row['value'], row['level'], row['martial'])
                    if old_attrs[key] <= 0: raise ValueError('强化属性或武学尚未识别；现有未知效果可以原样保留')
                    old_attrs[key] -= 1
                    continue
                if not -2147483648 <= row['value'] <= 2147483647: raise ValueError('强化属性值超出 32 位整数范围')
                if not 0 <= row['level'] <= 20: raise ValueError('解锁等级范围为 0～20')
                if row['martial'] and row['martial'] not in catalog.martials: raise ValueError('武学 ID 无效')
            obj = {**catalog.items[ident], 'BlueGift': [r['id'] for r in draft['gifts']],
                   'BlueGiftUnlockLv': [r['level'] for r in draft['gifts']], 'BlueAttr': [r['type'] for r in draft['attrs']],
                   'BlueAttrValue': [r['value'] for r in draft['attrs']], 'BlueAttrUnlockLv': [r['level'] for r in draft['attrs']],
                   'BlueMartial': [r['martial'] for r in draft['attrs']]}
            if external:
                source = external[0]; raw = catalog.snapshots[source]
                if source.read_bytes() != raw: raise ValueError('MOD 配置在读取后发生变化，请重新读取：'+str(source))
                document = mod_documents.setdefault(source, json.loads(raw.decode('utf-8-sig')))
                matches = [r for r in document['Items'] if isinstance(r,dict) and r.get('BaseID') == ident]
                if len(matches) != 1: raise ValueError(f'MOD 配置中型号 {ident} 重复，停止保存')
                edited_mod_row = (matches[0], dict(matches[0]))
                matches[0].update({key: obj[key] for key in EFFECT_KEYS})
                if effect_draft(matches[0]) != draft: raise ValueError('MOD 强化效果回读验证失败')
                continue
            if ident not in catalog.rows:
                raise ValueError(f'装备 {ident} 缺少原生记录或唯一 MOD 来源，暂只支持单件存档数值编辑')
            if catalog.own_original:
                try:
                    own_doc=json.loads(catalog.own_original.decode('utf-8-sig'))
                    if not isinstance(own_doc,dict) or not isinstance(own_doc.get('Items'),list) or len(own_doc['Items'])!=len(catalog.own_rows):
                        raise ValueError('已有记录不完整')
                except (ValueError,UnicodeError):raise ValueError('编辑器已有 JSON 异常，保留原文件并跳过型号效果')
            client[ident] = obj
            lua_effects[ident] = {key: obj[key] for key in EFFECT_KEYS}
            replacements = {SCHEMAS['Item'][key]['number']: numeric_list(SCHEMAS['Item'][key]['number'], obj[key])
                            for key in ('BlueGift', 'BlueGiftUnlockLv', 'BlueAttr', 'BlueAttrValue', 'BlueAttrUnlockLv', 'BlueMartial')}
            rows[ident] = patch(catalog.rows[ident], replacements)
            if effect_draft(decode(rows[ident], 'Item', SCHEMAS)) != draft: raise ValueError('强化效果回读验证失败')
        except (ValueError,KeyError,TypeError,OverflowError) as error:
            if not skip_errors: raise
            catalog.last_effect_skips[ident] = str(error)
            rows.pop(ident, None); lua_effects.pop(ident, None)
            if ident in catalog.own_rows:client[ident] = catalog.own_rows[ident]
            else:client.pop(ident, None)
            if edited_mod_row:
                target, before_row = edited_mod_row; target.clear(); target.update(before_row)
    item_path = catalog.root / 'TableData/Item.bytes'
    data = catalog.snapshots[item_path]; out = bytearray()
    for field in fields(data):
        if field.number == 2 and field.wire == 2:
            ident = values(field.value, 1)[0]
            out.extend(encoded(2, rows[ident], 2) if ident in rows else field.raw)
        else: out.extend(field.raw)
    if rows:
        result.update({item_path: bytes(out), catalog.own_json: json.dumps({'Keys': [str(i) for i in sorted(client)],
                       'Items': [client[i] for i in sorted(client)]}, ensure_ascii=False, indent=2).encode('utf-8')})
    for source, document in mod_documents.items():
        raw = json.dumps(document, ensure_ascii=False, indent=2).encode('utf-8')
        if json.loads(raw) != document: raise ValueError('MOD JSON 回读验证失败')
        result[source] = raw
    if catalog.client_hash and lua_effects:
        original = catalog.client_path.read_bytes()
        if digest(original) != catalog.client_hash: raise ValueError('客户端配置在读取后发生变化，请重新读取')
        updated = patch_effects(catalog.client_text, lua_effects)
        result[catalog.client_path] = Assets(original).replace_script('Item.lua', updated)
        check = Assets(result[catalog.client_path]).script('Item.lua')
        check_items = lua_rows(check, 'Item', catalog.client_enums)
        for ident in lua_effects:
            draft = drafts[ident]
            if effect_draft(check_items[ident]) != draft: raise ValueError('客户端强化效果回读验证失败')
        catalog.snapshots[catalog.client_path] = original
    # If the build also has this table in StreamingAssets, update that copy consistently.
    duplicate = catalog.root / 'DreamRivakes_Data/StreamingAssets/Item.bytes'
    if rows and duplicate.is_file():
        original = duplicate.read_bytes()
        if original != data: raise ValueError('Item.bytes 的两个副本不一致，停止写入')
        catalog.snapshots[duplicate] = original; result[duplicate] = bytes(out)
    return result

def write_locked(path, before, after):
    """Exclusive Windows handle; compare and write while holding the same handle."""
    import msvcrt
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                                  wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    handle = kernel.CreateFileW(str(path), 0xC0000000, 0, None, 3, 0x80, None)
    if handle == ctypes.c_void_p(-1).value: raise OSError(ctypes.get_last_error(), f'文件被占用：{path}')
    fd = msvcrt.open_osfhandle(handle, os.O_RDWR | os.O_BINARY)
    with os.fdopen(fd, 'r+b', buffering=0) as stream:
        current = stream.read()
        if current != before: raise ValueError(f'文件在读取后发生变化，请重新读取：{path}')
        try:
            stream.seek(0); stream.write(after); stream.truncate(); os.fsync(stream.fileno())
            stream.seek(0)
            if stream.read() != after: raise OSError('文件写入校验失败')
        except Exception:
            stream.seek(0); stream.write(before); stream.truncate(); os.fsync(stream.fileno())
            raise

def transaction(root, payloads, originals, purpose='编辑装备', share_operations=None, audit_entries=None):
    root = Path(root).resolve(); ensure_closed()
    changes = {Path(p).resolve(): data for p, data in payloads.items() if data != originals.get(Path(p))}
    if not changes: return None
    for path in changes:
        if not path.is_relative_to(root): raise ValueError('目标文件不在游戏目录内')
        expected = originals.get(path)
        current = path.read_bytes() if path.exists() else None
        if current != expected: raise ValueError(f'文件已变化，请重新读取：{path}')
    backup = root / '装备编辑器备份' / (datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '_' + uuid.uuid4().hex[:6])
    backup.mkdir(parents=True)
    # Prepare the audit and portable patch before any game write. Failed
    # transactions remain incomplete and are never shown as saved history.
    from change_share import record_transaction
    log_entries,log_time,share_signature=record_transaction(root,changes,originals,purpose,backup,share_operations,audit_entries)
    entries = []
    for index, (path, data) in enumerate(changes.items()):
        before = originals.get(path); entry = {'path': str(path.relative_to(root)), 'exists': before is not None,
                                              'before_sha256': digest(before) if before is not None else None,
                                              'after_sha256': digest(data) if data is not None else None, 'backup': f'{index:02d}.bin'}
        if before is not None: (backup / entry['backup']).write_bytes(before)
        entries.append(entry)
    manifest = {'root': str(root), 'purpose': purpose, 'entries': entries, 'complete': False,
                'change_log': log_entries, 'time': log_time, 'log_version': 1, 'share_signature':share_signature}
    manifest_path = backup / 'manifest.json'
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    written = []
    try:
        for path, data in changes.items():
            ensure_closed(); path.parent.mkdir(parents=True, exist_ok=True)
            before = originals.get(path)
            if data is None:
                if path.read_bytes() != before: raise ValueError('删除配置前文件发生变化')
                path.unlink(); written.append(path)
            elif before is None:
                with path.open('xb') as stream:
                    written.append(path); stream.write(data); stream.flush(); os.fsync(stream.fileno())
                if path.read_bytes() != data: raise OSError('新文件写入校验失败')
            else:
                write_locked(path, before, data); written.append(path)
        ensure_closed()
        manifest['complete'] = True
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception as error:
        failures = []
        for path in reversed(written):
            try:
                before = originals.get(path)
                if before is None:
                    path.unlink()
                elif changes[path] is None:
                    with path.open('xb') as stream: stream.write(before); stream.flush(); os.fsync(stream.fileno())
                else: write_locked(path, changes[path], before)
            except Exception as rollback: failures.append(f'{path}: {rollback}')
        if failures: raise OSError(f'保存失败，部分文件恢复失败。备份：{backup}\n' + '\n'.join(failures)) from error
        raise OSError(f'保存失败，已撤销本次写入。备份：{backup}\n{error}') from error
    try:
        from library_cache import invalidate
        invalidate(root,changes)
    except (ImportError,OSError):pass
    return backup

def restore(root, manifest_path):
    root = Path(root).resolve(); backup = Path(manifest_path).parent
    manifest = json.loads(Path(manifest_path).read_text(encoding='utf-8'))
    if Path(manifest['root']).resolve() != root: raise ValueError('备份属于另一个游戏目录')
    ensure_closed(); payloads = {}; originals = {}; removals = []
    for entry in manifest['entries']:
        path = (root / entry['path']).resolve()
        if not path.is_relative_to(root): raise ValueError('备份路径超出游戏目录')
        current = path.read_bytes() if path.exists() else None
        originals[path] = current
        if entry['exists']:
            is_save=path.name.lower() in ('save.sav','saveai.sav')
            if not is_save and current is not None and digest(current) not in (entry['before_sha256'],entry['after_sha256']):
                raise ValueError('文件已被后装 MOD 修改，保留最后安装版本，其他编辑功能仍可使用：'+str(path))
            if current is None and entry['after_sha256'] is not None:
                raise ValueError('文件已被其他程序移除，不自动恢复旧版本：'+str(path))
            source = (backup / entry['backup']).resolve()
            if not source.is_relative_to(backup.resolve()): raise ValueError('备份文件路径无效')
            before = source.read_bytes()
            if digest(before) != entry['before_sha256']: raise ValueError('备份文件校验失败')
            payloads[path] = before
        elif current is not None:
            if digest(current) != entry['after_sha256']: raise ValueError(f'恢复需移除的配置已被其他工具修改：{path}')
            removals.append(path)
    # Record newly created files too, so the restore itself can be undone.
    for path in removals: payloads[path] = None
    restored_backup = transaction(root, payloads, originals, '恢复备份')
    return restored_backup
