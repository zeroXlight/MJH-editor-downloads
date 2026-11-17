"""Read-only regression of the standalone feature inside the shipped executable."""
import sys,json
from pathlib import Path
def run():
    from six_attrs import plan
    from edition import VERSION,EDITION_NAME
    from review_edition import output
    root=Path(sys.argv[sys.argv.index('--game')+1]).resolve();cases=[]
    for enabled,forge,martial in ((True,True,True),(False,False,False)):
        v=plan(root,enabled,forge,martial)
        assert all((p.read_bytes() if p.exists() else None)==b for p,b in v.originals.items())
        assert all((p.read_bytes() if p.exists() else None)==b for p,b in v.reads.items())
        assert not any(p.suffix in ('.sav','.check') for p in v.payloads)
        cases.append(dict(enabled=enabled,files=len(v.payloads),results=v.results))
    report=dict(passed=True,version=VERSION,edition=EDITION_NAME,frozen=bool(getattr(sys,'frozen',False)),cases=cases,game_unchanged=True)
    (output()/'六属性入口冻结验收.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
