"""Route known Shadow generated rows to their authoritative source files.

No native patching, imports with UI side effects or disk writes. Plans join the
editor's existing backup/compare/write/rollback transaction. Later explicit
writes replace conflicting fields; no automatic whole-file restore is used.
"""
import copy
import json
import re
from pathlib import Path


def _document(raw, label, partial=False):
    doc = json.loads(raw.decode('utf-8-sig'))
    if not isinstance(doc, dict) or not isinstance(doc.get('Items'), list):
        raise ValueError('外部配置结构无效：' + label)
    if partial: return doc  # Unrelated unsupported rows remain unchanged.
    ids = [r.get('BaseID') for r in doc['Items'] if isinstance(r, dict)]
    if len(ids) != len(doc['Items']) or any(type(i) is not int or i <= 0 for i in ids) or len(set(ids)) != len(ids):
        raise ValueError('暗影配置记录编号无效或重复：' + label)
    return doc


def prepare_routes(lib):
    routes = {}
    documents = {}
    from collections import Counter
    def inspect(path, raw, partial=False):
        key = (path, partial)
        if key not in documents:
            doc = _document(raw, str(path), partial=partial)
            counts = Counter(row['BaseID'] for row in doc['Items']
                             if isinstance(row,dict) and type(row.get('BaseID')) is int)
            documents[key] = (doc, counts)
        return documents[key]
    from mod_compatibility import note
    for kind, overrides in lib.overrides.items():
        for ident, names in list(overrides.items()):
            if len(names) != 1:
                continue  # Other sources and ambiguous ownership stay protected.
            filename = names[0]
            match = re.fullmatch(r'([A-Za-z]+)_(ShadowMartial|ShadowCustom)_([A-Za-z0-9_-]+)\.json', filename)
            if not match or match[1] != kind:
                target = lib.own_jsons[kind].parent/filename
                try:
                    doc, counts = inspect(target, lib.originals[target], partial=True)
                except (ValueError, UnicodeError, KeyError) as error:
                    note(lib,'外部配置保持保护：'+filename+'（'+str(error)+'）');continue
                if counts[ident] != 1:
                    continue
                # The unique active JSON is the write target. No MOD name or
                # presumed source directory is required for ordinary overlays.
                routes[kind, ident] = (target, target)
                del overrides[ident]
                continue
            if match[2] == 'ShadowMartial' and kind not in ('Martial','MartialItem','Language'):
                continue
            if match[2] == 'ShadowCustom' and kind not in ('Role','RoleAttr','RoleModel','Language'):
                continue
            folder = '自定义武学' if match[2] == 'ShadowMartial' else '自定义角色'
            source = (lib.root/'mod'/'暗影mod'/folder/(kind+'_'+match[3]+'.json')).resolve()
            if not source.is_relative_to(lib.root.resolve()) or not source.is_file():
                continue
            target = lib.own_jsons[kind].parent/filename
            raw = lib.originals[source] if source in lib.originals else source.read_bytes()
            try:
                doc, counts = inspect(source, raw)
                generated, _ = inspect(target, lib.originals[target])
            except (ValueError,UnicodeError) as error:
                note(lib,'暗影来源保持保护：'+filename+'（'+str(error)+'）');continue
            if doc != generated:
                note(lib,'暗影源文件与生成文件不同，已跳过自动同步：'+filename)
                continue  # Never guess which of diverging source/target is current.
            if counts[ident] != 1:
                continue
            lib.originals[source] = raw
            routes[kind, ident] = (source, target)
            del overrides[ident]
    lib.shadow_routes = routes


def _encode(doc):
    return json.dumps(doc, ensure_ascii=False, indent=2).encode('utf-8')


def route_payloads(lib, payloads, originals):
    # Official Martial overlays replace whole rows: retain name/icon/defaults.
    own_martial = lib.own_jsons.get('Martial')
    if own_martial in payloads and hasattr(lib, 'tables'):
        doc = _document(payloads[own_martial], str(own_martial))
        for row in doc['Items']:
            effective = lib.tables.get('Martial', {}).get(row['BaseID'])
            if effective is not None:
                full = copy.deepcopy(effective); full.update(row)
                row.clear(); row.update(full)
        payloads[own_martial] = _encode(doc)
    docs = {}
    routed = {}
    for (kind, ident), (source, target) in getattr(lib, 'shadow_routes', {}).items():
        if ident not in lib.changes.get(kind, {}):
            continue
        delta = copy.deepcopy(lib.changes[kind][ident])
        if kind == 'Language' and 'Ch_Text' in delta:
            delta['Text'] = delta.pop('Ch_Text')
        for path in dict.fromkeys((source, target)):
            before = originals[path]
            if path.read_bytes() != before:
                raise ValueError('外部配置在读取后发生变化，请重新读取：' + str(path))
            if path not in docs: docs[path] = _document(before, str(path), partial=source == target)
            doc = docs[path]
            row = next(r for r in doc['Items'] if isinstance(r,dict) and type(r.get('BaseID')) is int and r['BaseID'] == ident)
            row.update(delta)  # Preserve all unknown fields and unrelated rows.
        routed.setdefault(kind, set()).add(ident)
    for path, doc in docs.items():
        payloads[path] = _encode(doc)
    for kind, ids in routed.items():
        own = lib.own_jsons[kind]
        raw = payloads.get(own)
        if raw is None:
            continue
        doc = _document(raw, str(own))
        keep = [row for row in doc['Items'] if row['BaseID'] not in ids]
        doc['Items'] = keep
        if 'Keys' in doc:
            old = doc['Keys']
            as_string = bool(old) and isinstance(old[0], str)
            doc['Keys'] = [str(r['BaseID']) if as_string else r['BaseID'] for r in keep]
        if not keep and originals.get(own) is None:
            payloads.pop(own, None)  # Avoid creating a second same-ID overlay.
        else:
            payloads[own] = _encode(doc)
    from mod_compatibility import stage
    return stage(lib,payloads,originals)
