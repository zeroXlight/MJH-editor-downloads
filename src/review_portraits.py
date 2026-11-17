"""Read-only verification of the final packaged mobile canvas and head resources."""
import io,json,sys
from pathlib import Path
from PIL import Image

def run():
    from edition import VERSION,EDITION_NAME,MOBILE_ENABLED
    from engine import DATA_ROOT
    from disguise_portraits import stage,head_resource,patch_loader
    from role_roll_portrait import patch_roll,BLOCK
    root=Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent.parent
    report={'passed':True,'version':VERSION,'edition':EDITION_NAME,'frozen':getattr(sys,'frozen',False)}
    text='function GetSprite(name) return name end\nfunction GetSpriteAsync(path,component,onLoad) end\n'
    assert patch_loader(patch_loader(text))==patch_loader(text)
    assert 'row.Head = option.head' in (DATA_ROOT/'ui_assets/disguise_runtime.lua').read_text('utf8')
    assert '-- MJH_DISGUISE_UI_V2212' in (DATA_ROOT/'ui_assets/disguise_ui.lua').read_text('utf8')
    assert 'disguise_cg_' in BLOCK
    if MOBILE_ENABLED:
        from mobile_models import catalog,read
        c=catalog();assert c['portrait_canvas_version']==1 and c['portrait_head_version']==1
        names=set();heads=0
        for entry in c['portraits']:
            filename,raw=stage(entry,read(entry));names.add(filename)
            assert filename=='disguise_cg_'+entry['legacy_sha256'][:24]+'.png'
            with Image.open(io.BytesIO(raw)) as im:assert im.size==(entry['width'],entry['height'])
            if head_resource(entry):heads+=1
        assert len(names)==542 and heads==496
        report.update(portraits=len(names),paired_heads=heads,unpaired_keep_original_head=46)
    else:
        from mobile_models import catalog
        try:catalog()
        except ValueError:pass
        else:raise AssertionError('Standard edition exposed mobile assets')
        report['mobile_boundary_verified']=True
    (root/'立绘头像打包验收.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
