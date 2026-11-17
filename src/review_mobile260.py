"""Frozen app resource acceptance; never writes game or saves."""
import json,sys
from pathlib import Path
def review():
    from mobile_models import catalog,read
    from role_animation import skeleton_body
    c=catalog();actions=events=0
    for model in c['models']:
        assert model['compatible']
        read(model['skel']);read(model['atlas'])
        data=json.loads(read(model['runtime']).decode('utf-8-sig'));skeleton_body(data)
        actions+=len(data['animations']);events+=sum(len(a.get('Events',[])) for a in data['animations'])
        for texture in model['textures']:read(texture)
    for portrait in c['portraits']:read(portrait)
    result=dict(passed=True,version='V2.1.61',models=len(c['models']),textures=sum(len(m['textures']) for m in c['models']),portraits=len(c['portraits']),actions=actions,events=events,no_game_write=True)
    out=Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).parent
    (out/'手游资源验收.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
