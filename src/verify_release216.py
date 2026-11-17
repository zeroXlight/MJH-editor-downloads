"""Compare released executable code/data with the delivered buildable source."""
import hashlib,json,marshal,types
from pathlib import Path
from PyInstaller.archive.readers import CArchiveReader
from release_dual import location,DATA,VERSION

def norm(code):
    return code.replace(co_filename='',co_consts=tuple(norm(c) if isinstance(c,types.CodeType) else c for c in code.co_consts))

for mobile in (False,True):
    folder,label=location(mobile);source=folder/'源码';exe=folder/(folder.name+'.exe')
    archive=CArchiveReader(str(exe));pyz=archive.open_embedded_archive('PYZ.pyz');checked=[]
    names=['desktop_app','review_release217','edition','external_runtime','growth_runtime','mobile_models',
           'role_ui','mobile_models_ui','disguise_editor','disguise_reference','disguise_assets','engine',
           'equipment_copy','pet_runtime','pet_restore','pet_battle_runtime','aoyi_editor','aoyi_runtime','aoyi_ui','martial_editor','pet_config','attribute_uncap','attribute_uncap_ui','object_bundle','object_service','object_reuse','object_identity_reuse','object_growth_import','object_extras','object_ui','object_runtime',
           'six_attrs_runtime','shadow_runtime','shadow_compat','mobile_martial_restore','mobile_martial_repair','mobile_martial_graph','mobile_martial_identity','mobile_martial_acquisition','mobile_martial_restore_ui','martial_limit_enhance','martial_limit_enhance_ui','feature_ui','compatibility']
    for name in names:
        actual=marshal.loads(archive.extract('desktop_app')) if name=='desktop_app' else pyz.extract(name)
        expected=compile((source/(name+'.py')).read_bytes(),str(source/(name+'.py')),'exec')
        assert norm(actual)==norm(expected),name
        checked.append(name)
    table={k.replace('\\','/'):k for k in archive.toc}
    for path in (source/'ui_assets').rglob('*'):
        if path.is_file():
            member='ui_assets/'+path.relative_to(source/'ui_assets').as_posix()
            assert archive.extract(table[member])==path.read_bytes(),member
    for path in (source/'desktop_ui/dist').rglob('*'):
        if path.is_file():
            member='desktop_ui/dist/'+path.relative_to(source/'desktop_ui/dist').as_posix()
            assert archive.extract(table[member])==path.read_bytes(),member
    for name in DATA:assert archive.extract(table[name])==(source/name).read_bytes(),name
    assert ('ui_assets/mobile_models.lua' in table)==mobile
    assert any(k.endswith('keystone.dll') for k in table)
    assert any('lupa/' in k and 'lua53' in k for k in table)
    assert not any('mobile_assets/' in k or k.endswith('shadow_runtime_profile.json') or k.endswith('暗影兼容补丁.exe') for k in table)
    report=dict(version=VERSION,edition=label,passed=True,compiled_modules_match_source=checked,
                frontend_and_lua_match_source=True,keystone_and_lua53_bundled=True,
                mobile_loader_bundled=mobile,independent_shadow_tool_not_embedded=True,
                executable_sha256=hashlib.sha256(exe.read_bytes()).hexdigest())
    (folder/'程序与源码一致性验收.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps(report,ensure_ascii=False),flush=True)
