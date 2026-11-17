"""Retire only exactly proved V2.4.6 editor overlays; follow native copying."""
from pathlib import Path
import copy,json,hashlib
from engine import DATA_ROOT
OLD_STATE='装备编辑器配置/空白秘籍抄录.json'
MARKER='-- MJH_BLANK_MANUAL_V246'

def remove_script(text,name):
    if 'MJH_BLANK_MANUAL' not in text:return text
    block=(DATA_ROOT/'ui_assets/legacy_blank_manual_v246.lua').read_text('utf8').replace('CLASS',name[:-4]).rstrip()
    if text.count(MARKER)!=1 or text.count('-- MJH_BLANK_MANUAL_END')!=1 or text.count('\n'+block+'\n')!=1:
        raise ValueError('旧版抄录自有脚本段存在未知修改，未移除：'+name)
    result=text.replace('\n'+block+'\n','',1)
    if 'MJH_BLANK_MANUAL' in result:raise ValueError('旧版抄录脚本存在重复或未知标记：'+name)
    return result

def retire_fields(store,old,payloads,originals,results):
    """A backup must reproduce V246's full after-image before owning a field.

    Remove just that explicit JSON field to follow the updated native table.
    Never replay an old full row, old native table or old original Lua method.
    """
    if old is None:return 0
    ident=set(old.get('copy_martials',[]));state_sha=hashlib.sha256(json.dumps(old,ensure_ascii=False,indent=2).encode('utf8')).hexdigest()
    actual=store.read(store.root/OLD_STATE);state_sha=hashlib.sha256(actual).hexdigest()
    ownership={}
    for path in sorted((store.root/'装备编辑器备份').glob('*/manifest.json')):
        data=store.read(path)
        try:doc=json.loads(data)
        except (ValueError,TypeError):continue
        if not doc.get('complete') or not any(e.get('path','').replace('\\','/')==OLD_STATE and e.get('after_sha256')==state_sha for e in doc.get('entries',[])):continue
        for entry in doc['entries']:
            relative=entry.get('path','').replace('\\','/');p=Path(relative)
            table=p.name.split('_',1)[0]
            if table not in ('Martial','Story') or not relative.startswith('ModProject/GameProject/') or not entry.get('exists'):continue
            beforepath=(path.parent/entry['backup']).resolve()
            if not beforepath.is_relative_to(path.parent.resolve()):raise ValueError('旧抄录备份路径越界')
            raw=store.read(beforepath)
            if raw is None or hashlib.sha256(raw).hexdigest()!=entry.get('before_sha256'):raise ValueError('旧抄录备份摘要不匹配')
            before=json.loads(raw.decode('utf-8-sig'));after=copy.deepcopy(before);owned=[]
            if not isinstance(after,dict) or not isinstance(after.get('Items'),list):continue
            field='CouldCopy' if table=='Martial' else 'OpenMakeSecret'
            for row in after['Items']:
                if table=='Martial' and row.get('BaseID') not in ident:continue
                if row.get(field)!=1:owned.append((row['BaseID'],field))
                row[field]=1
            rebuilt=json.dumps(after,ensure_ascii=False,indent=2).encode('utf8')
            if hashlib.sha256(rebuilt).hexdigest()!=entry.get('after_sha256'):continue
            ownership.setdefault(relative,set()).update(owned)
    count=0
    for relative,fields in ownership.items():
        path=(store.root/relative).resolve()
        if not path.is_relative_to(store.root):raise ValueError('旧抄录配置路径越界')
        before=store.read(path)
        if before is None:continue
        doc=json.loads(before.decode('utf-8-sig'));changed=False
        for row in doc.get('Items',[]):
            for field in ('CouldCopy','OpenMakeSecret'):
                if (row.get('BaseID'),field) in fields and row.get(field)==1:
                    del row[field];changed=True;count+=1
        if changed:payloads[path]=json.dumps(doc,ensure_ascii=False,indent=2).encode('utf8');originals[path]=before
    if count:results.append(f'按旧完整备份移除 {count} 项可证明由V2.4.6添加的JSON抄录覆盖，改为读取当前游戏原生值；其他字段保留。')
    return count
