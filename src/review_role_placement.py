"""Read-only checks of placement repair and recursive imports in each EXE."""
from pathlib import Path
import json,sys,hashlib

def run():
    from edition import VERSION,EDITION_NAME
    from review_edition import output
    from role_editor import RoleLibrary
    from role_placement_repair import stage
    from object_bundle import Store
    from object_extras import collect
    root=Path(sys.argv[sys.argv.index('--game')+1]).resolve()
    l=RoleLibrary(root);before={p:hashlib.sha256(v).hexdigest() for p,v in l.originals.items() if v is not None}
    restored=stage(l);assert not restored,restored
    rid=1700000000;record=l.meta[str(rid)];task=record['position_task']['Task']
    assert record['settings']['location_path']==[1334,1339,1341,1349]
    assert all(task in r['StartTask'] for r in l.tables['Story'].values())
    packet,files=collect(Store(root),'Role',rid)
    assert '@Role:1700000000' in packet['role_groups'] or '1700000000' in packet['role_groups']
    assert 'Task:'+str(task) in packet['nodes']
    assert len(files)>=1
    assert all(p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==sha for p,sha in before.items())
    result=dict(passed=True,version=VERSION,edition=EDITION_NAME,frozen=bool(getattr(sys,'frozen',False)),placement_graph_verified=True,all_native_replicas_and_stories_verified=True,exported_nodes=len(packet['nodes']),exported_files=len(files),game_unchanged=True)
    (output()/'人物放置导入冻结验收.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf8')
