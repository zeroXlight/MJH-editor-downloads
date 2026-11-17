"""Recover known replaced editor overlays; keep the big-map configuration."""
from pathlib import Path
import json,copy
from engine import DATA_ROOT
def stage(root):
    from object_bundle import Store
    from feature_fields import table_rows,sync
    from martial_mastery import native_rows
    from codec import decode
    from engine import SCHEMAS
    import six_attrs_options
    from bigmap_profile import race_image
    root=Path(root);race=(root/'DreamRivakes_Data/Plugins/RaceLogic_Release_x64.dll').read_bytes()
    if not race_image(race):raise ValueError('当前运行库不是已核对的大地图版本，未修改')
    profile=json.loads((DATA_ROOT/'bigmap_data_profile.json').read_text('utf8'));s=Store(root);p=root/six_attrs_options.STATE;before=s.read(p);payloads={};originals={};notes=[]
    if before:
        doc=json.loads(before);removed=0
        for group,tables in doc.get('changes',{}).items():
            for table,entries in tables.items():
                current=table_rows(s,table)
                for key,e in list(entries.items()):
                    row=current.get(int(key));v={k:row.get(k) for k in e['after']} if row else None
                    if v==e['after']:continue
                    known=profile['stale_current'].get(table,{}).get(key,'unrecognized')
                    if v!=e['before'] and v!=known:raise ValueError('大地图兼容保留外部改动，请处理冲突：'+table+' '+key)
                    del entries[key];removed+=1
        if removed:
            payloads[p]=json.dumps(doc,ensure_ascii=False,indent=2).encode('utf8');originals[p]=before
            notes.append('已核实资源替换造成的 '+str(removed)+' 条旧恢复记录失效，以现有大地图数据为基线重建。')
    native=native_rows(s.read(root/'TableData/KungfuBase.bytes'),'KungfuBase');client=table_rows(s,'KungfuBase');changes={}
    for key,e in profile['growth'].items():
        i=int(key);actual=decode(native[i],'KungfuBase',SCHEMAS);display=client[i]
        if actual==display:continue
        if actual!=e['native'] or display!=e['client']:raise ValueError('大地图成长表存在额外改动，未覆盖：'+key)
        changes[i]=copy.deepcopy(actual)
    if changes:
        more,old=sync(s,{'KungfuBase':changes});payloads.update(more);originals.update(old);notes.append('同步 '+str(len(changes))+' 条已核实的成长显示到大地图原生逻辑数值。')
    return payloads,originals,notes,[],dict(s.reads)
