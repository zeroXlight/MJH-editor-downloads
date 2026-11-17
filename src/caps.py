"""Martial caps: field-only restoration preserves equipment and unrelated mods."""
import json, re
from pathlib import Path
from codec import fields, values, patch, encoded
from client_config import Assets
from engine import DATA_ROOT, digest

CAPS = {'Difficult': {9:'MartialLvMax',20:'DefaultMartialLVMax'},
        'CommonConfig': {2:'DefaultMartialMaxLevel',4:'MartialMaxLevelFinal'},
        'Martial': {15:'LvLimit'}}
ROW_PATTERN = r'(?m)^([ \t]*\[(\d+)\]\s*=\s*\{)([^\r\n]*)\},'

def proto_profile(data, name, notes=None):
    out = {}; seen = set(); parts = fields(data); keys = values(data, 1)
    for f in parts:
        if f.number != 2: continue
        if f.wire != 2: raise ValueError('配置记录编码异常：'+name)
        ids = values(f.value, 1)
        if len(ids) != 1 or not isinstance(ids[0], int) or ids[0] in seen:
            raise ValueError('配置记录编号异常：'+name)
        seen.add(ids[0]); row = {}; valid = True
        for number, key in CAPS[name].items():
            vals = values(f.value, number)
            if len(vals) > 1 or any(not isinstance(v,int) or not 0 <= v <= 1000 for v in vals):
                valid = False
                if notes is not None: notes.append(f'{name}:{ids[0]} 上限字段无法识别，已跳过')
                break
            row[key] = vals[0] if vals else None
        if valid: out[str(ids[0])] = row
    if seen != set(keys): raise ValueError('配置索引与记录不匹配：'+name)
    return out

def lua_profile(text, name, notes=None):
    out = {}
    for match in re.finditer(ROW_PATTERN, text):
        ident = match[2]
        if ident in out: raise ValueError('客户端记录编号重复：'+name)
        row = {}; valid = True
        for key in CAPS[name].values():
            vals = re.findall(r'\b'+key+r'\s*=\s*(-?\d+)\s*,', match[3])
            if len(vals)>1 or (not vals and re.search(r'\b'+key+r'\s*=',match[3])) or any(not 0 <= int(v) <= 1000 for v in vals):
                valid = False
                if notes is not None: notes.append(f'{name}:{ident} 客户端上限字段无法识别，已跳过')
                break
            row[key] = int(vals[0]) if vals else None
        if valid: out[ident] = row
    if not out and not re.search(ROW_PATTERN,text): raise ValueError('未找到客户端配置记录：'+name)
    return out

def patch_proto(data, name, desired):
    original = proto_profile(data,name); out = bytearray()
    for f in fields(data):
        if f.number != 2: out.extend(f.raw); continue
        ident = str(values(f.value,1)[0])
        if ident not in desired: out.extend(f.raw); continue
        row = desired[ident]
        replacements = {n: b'' if row[k] is None else encoded(n,row[k]) for n,k in CAPS[name].items()}
        new = patch(f.value,replacements)
        out.extend(f.raw if new == f.value else encoded(2,new,2))
    result = bytes(out)
    if proto_profile(result,name) != original | desired: raise ValueError('等级上限回读校验失败')
    return result

def patch_lua(text, name, desired):
    def change(m):
        if m[2] not in desired: return m[0]
        body = m[3]; row = desired[m[2]]
        for key in CAPS[name].values():
            body = re.sub(r'\b'+key+r'\s*=\s*-?\d+\s*,?', '', body)
        return m[1]+body+''.join(k+'='+str(v)+',' for k,v in row.items() if v is not None)+'},'
    result = re.sub(ROW_PATTERN,change,text)
    if lua_profile(result,name) != (lua_profile(text,name) | desired): raise ValueError('客户端上限回读校验失败')
    return result

def original_profile(current, standard, saved=None, notes=None):
    out = {}
    for ident, row in current.items():
        old = saved.get(ident) if saved else None
        result = {}
        for key,value in row.items():
            if old is not None and key in old: result[key] = old[key]
            elif value == 30:
                if ident not in standard or key not in standard[ident]:
                    if notes is not None: notes.append(f'记录 {ident} 缺少原等级上限，保持当前值，已跳过')
                    break
                result[key] = standard[ident][key]
            else: result[key] = value
        else: out[ident] = result
    return out

def baseline():
    return json.loads((DATA_ROOT/'caps_baseline.json').read_text(encoding='utf-8'))

def plan_caps(root, enable, notes=None):
    notes = notes if notes is not None else []
    root = Path(root).resolve()
    if not (root/'DreamRivakes.exe').is_file(): raise ValueError('游戏目录无效')
    standard = baseline(); payloads = {}; originals = {}; state = {}
    created_path=root/'装备编辑器配置/自建武学原上限.json'
    if created_path.exists():
        created_raw=created_path.read_bytes();originals[created_path]=created_raw
        created=json.loads(created_raw.decode('utf-8'))
        for ident,level in created.items():
            if not str(ident).isdigit() or type(level) is not int or not 1<=level<=1000:
                notes.append(f'自建武学 {ident} 原上限记录无效，已跳过'); continue
            for section in ('proto','embedded','lua'):
                standard[section]['Martial'].setdefault(str(ident),{'LvLimit':level})
    state_path = root/'装备编辑器配置/武学上限原值.json'
    state_before = state_path.read_bytes() if state_path.exists() else None
    if state_before:
        obj = json.loads(state_before.decode('utf-8'))
        if obj.get('version') != 1: raise ValueError('武学上限原值记录版本不支持')
        state = obj['files']
    next_state = dict(state)
    def desired(profile, fallback, source):
        remembered = original_profile(profile,fallback,state.get(source),notes)
        next_state[source] = dict(state.get(source,{})) | remembered
        return {i:{k:30 for k in row} for i,row in remembered.items()} if enable else remembered
    for directory in ('TableData','DreamRivakes_Data/StreamingAssets'):
        for name in CAPS:
            path = root/directory/(name+'.bytes')
            if not path.is_file():
                if directory == 'TableData': raise ValueError('缺少配置文件：'+str(path))
                continue
            old = path.read_bytes(); source = path.relative_to(root).as_posix()
            profile = proto_profile(old,name,notes)
            new = patch_proto(old,name,desired(profile,standard['proto'][name],source))
            originals[path] = old
            if new != old: payloads[path] = new
    path = root/'DreamRivakes_Data/resources.assets'; old = path.read_bytes(); updated = old
    for name in CAPS:
        for resource in (name,name+'.lua'):
            a = Assets(updated)
            if resource not in a.scripts:
                notes.append('缺少客户端配置，已跳过：'+resource); continue
            _,q,n = a.scripts[resource]; raw = a.data[q+4:q+4+n]
            source = 'resources.assets/'+resource
            if resource.endswith('.lua'):
                text = raw.decode('utf-8-sig'); profile = lua_profile(text,name,notes)
                target = desired(profile,standard['lua'][name],source)
                new = patch_lua(text,name,target).encode('utf-8')
            else:
                profile = proto_profile(raw,name,notes)
                new = patch_proto(raw,name,desired(profile,standard['embedded'][name],source))
            if new != raw: updated = a.replace_blob(resource,new)
    originals[path] = old
    if updated != old: payloads[path] = updated
    mod_root = root/'ModProject'
    if mod_root.is_dir():
        for path in sorted(mod_root.rglob('*.json')):
            name = path.stem.split('_')[0]
            if name not in CAPS: continue
            if not path.resolve().is_relative_to(root): raise ValueError('模组路径超出游戏目录')
            old = path.read_bytes(); obj = json.loads(old.decode('utf-8-sig')); rows = obj.get('Items',[])
            profile = {}; duplicates=set(); seen_ids=set()
            if not isinstance(rows,list): notes.append(path.name+' Items格式不兼容，已跳过'); continue
            for row in rows:
                if not isinstance(row,dict): notes.append(f'{path.name} 非对象记录已跳过'); continue
                ident = str(row.get('BaseID',row.get('ID','')))
                if not ident.isdigit() or int(ident)<=0:
                    notes.append(f'{path.name} 模组编号无效，已跳过'); continue
                if ident in seen_ids:
                    duplicates.add(ident); notes.append(f'{path.name}:{ident} 编号重复，相关记录已跳过'); continue
                seen_ids.add(ident)
                profile[ident] = {k:row.get(k) for k in CAPS[name].values()}
                if any(v is not None and (type(v) is not int or not 0 <= v <= 1000) for v in profile[ident].values()):
                    notes.append(f'{path.name}:{ident} 模组上限字段无效，已跳过'); del profile[ident]
            for ident in duplicates: profile.pop(ident,None)
            source = path.relative_to(root).as_posix()
            target = desired(profile,standard['proto'][name],source)
            for row in rows:
                if not isinstance(row,dict): continue
                ident = str(row.get('BaseID',row.get('ID','')))
                if ident not in target: continue
                for key,value in target[ident].items():
                    if value is None: row.pop(key,None)
                    else: row[key] = value
            originals[path] = old
            if any(profile[i] != row for i,row in target.items()): payloads[path] = (json.dumps(obj,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    # A stable field baseline allows restoration without rolling back later
    # changes to equipment, skills, or the rest of a mod file.
    if enable and payloads:
        state_new = json.dumps({'version':1,'files':next_state},ensure_ascii=False,indent=2).encode('utf-8')
        if state_new != state_before: payloads[state_path] = state_new; originals[state_path] = state_before
    return payloads, originals

def cap_summary(root):
    root = Path(root); standard = baseline(); rows = []; unified = True
    for name in CAPS:
        profile = proto_profile((root/'TableData'/(name+'.bytes')).read_bytes(),name)
        for key in CAPS[name].values():
            vals = [r[key] for r in profile.values()]; unified &= all(v==30 for v in vals)
            numbers = sorted(set(v for v in vals if v is not None))
            rows.append((name,key,len(profile),' / '.join(map(str,numbers)) or '使用默认值'))
    return rows, unified
