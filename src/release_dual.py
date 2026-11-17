"""Fail-closed dual release builder; no game files are modified."""
import argparse,hashlib,json,shutil,subprocess,sys,zipfile
from pathlib import Path
from edition import VERSION
WORK=Path(__file__).resolve().parent
BUILD=WORK.parent/'编辑器'
DEST=BUILD
DATA=['nov15_six_attrs_points_code.json','nov15_role_baseline.json','nov5_six_attrs_points_code.json','nov5_role_baseline.json','shadow_bigmap_v047d.zip','bigmap_role_baseline.json','bigmap_data_profile.json','bigmap_six_attrs_points_code.json','schemas.json','metadata.json','caps_baseline.json','clause_baseline.json','app.ico',
      'pet_mobile_data.json','six_attrs_data.json','six_attrs_schema.json','six_attrs_mobile_restore.json',
      'six_attrs_points_code.json','six_attrs_character.lua','six_attrs_character_v227.lua',
      'six_attrs_character_v2316.lua','six_attrs_character_v228.lua','six_attrs_character_v229.lua','six_attrs_mobile_layout.lua','mobile_martial_pack.json','mobile_martial_repair_baseline.json','role_breakthrough_pack.json']


def consolidate_reports(release):
    """All acceptance reports, validation notes and logs share one directory."""
    folder=release/'验收资料';folder.mkdir(exist_ok=True)
    for path in list(release.iterdir()):
        if path.is_file() and (('验收' in path.name or '验证说明' in path.name or path.name=='构建日志.txt') and path.name!='文件校验.json'):
            shutil.move(str(path),str(folder/path.name))
    evidence=release/'测试证据'
    if evidence.is_dir():
        shutil.copytree(evidence,folder/'测试证据',dirs_exist_ok=True)
        for path in sorted(evidence.rglob('*'),key=lambda p:len(p.parts),reverse=True):
            if path.is_file():path.unlink()
            elif path.is_dir():path.rmdir()
        evidence.rmdir()
    return folder

def location(mobile):
    label='手游资源版' if mobile else '标准版'
    return BUILD/('已有装备武学编辑器'+VERSION+'_'+label),label

def assets():
    for path in (WORK/'mobile_assets',WORK.parent/'mobile_assets',WORK.parent/'修复V2.3.8/mobile_assets',WORK/'investigation/mobile215/mobile_assets',Path(r'F:\mjh\编辑器\已有装备武学编辑器V2.3.1_手游资源版\mobile_assets')):
        if (path/'catalog.json').is_file():return path
    raise FileNotFoundError('请在源码同级或上级放入完整 mobile_assets')

def prepare(mobile):
    release,label=location(mobile);source=release/'源码';source.mkdir(parents=True,exist_ok=True)
    for path in source.glob('test_*.py'):path.unlink()
    for path in WORK.glob('*.py'):
        if not path.name.startswith('test_'):shutil.copy2(path,source/path.name)
    for name in DATA+['requirements.txt']:shutil.copy2(WORK/name,source/name)
    shutil.copytree(WORK/'ui_assets',source/'ui_assets',dirs_exist_ok=True)
    if not mobile:(source/'ui_assets/mobile_models.lua').unlink(missing_ok=True)
    shutil.copytree(WORK/'desktop_ui',source/'desktop_ui',ignore=shutil.ignore_patterns('node_modules'),dirs_exist_ok=True)
    edition=(WORK/'edition.py').read_text('utf8')
    import re
    edition=re.sub(r'MOBILE_ENABLED=(True|False)','MOBILE_ENABLED='+str(mobile),edition)
    (source/'edition.py').write_text(edition,'utf8')
    spec=(WORK/'desktop.spec').read_text('utf8')
    spec=re.sub(r"name='已有装备武学编辑器[^']+'",'name='+repr(release.name),spec)
    (source/'desktop.spec').write_text(spec,'utf8')
    if mobile:shutil.copytree(assets(),release/'mobile_assets',dirs_exist_ok=True)
    assert (source/'ui_assets/mobile_models.lua').exists()==mobile
    notes=f'''梦江湖 已有装备/武学/人物编辑器 {VERSION} · {label}

适配2026-11-15本机Steam build 26650481：Race aba6a72d…，Client a751183a…。
保留此前认证版本与功能；新运行库使用独立精确适配，未知代码、表头和父摘要仍拒绝覆盖。
删除编辑器抄录接管，武学抄录由当前游戏原版实现。
功能修改→空白秘籍低价购买：杭州本杰明商店1铜币/本，每游戏月20本，固定货架编号不变，已有购买记录保留。
空白秘籍沿用原生全局资产，跨周目保留；应用不赠送道具，不直接写存档。
升级会精确撤下旧自有抄录脚本；有完整旧备份可核实时，仅移除自有JSON抄录字段，保留其他配置。
退出游戏，用新版先预览并启用空白秘籍低价购买，再按已有选项重新预览应用大地图兼容，重启游戏。
仅替换EXE不会自动更新游戏补丁。不需要重新购买突破或清除学习进度。
保留V2.4.5头像修复。标准版与手游资源版各自资源边界不变。
每包附EXE、可构建源码、版本/升级说明和离线模型与立绘总表。总表仅对应本轮目录快照；游戏/MOD改变后重新导出。
验收范围详见验收资料，历史证据单列。V2.4.4首次入队保存仍未核实；V2.4.5头像修复不能视为其解决。专属武器强化继续暂缓。
'''
    (release/'版本说明.txt').write_text(notes,'utf8')
    (source/'构建说明.txt').write_text(
        f'{VERSION} {label}\n本轮使用Windows x64 Python 3.14构建，python -m pip install -r requirements.txt。\n'
        '源码运行：python desktop_app.py。前端dist已附带；改前端用npm ci、npm run build。\n'
        '构建本版：python -m PyInstaller --noconfirm --distpath .. desktop.spec。\n'
        '手游资源版从源码上级读取mobile_assets；标准版无此目录。\n'
        '双版本发布入口release_dual.py；prepare/build/review/package搭配standard/mobile/both。\n'
        'review需--game指定只读验证用的完整游戏目录，生成并验证两个版本对应总表。\n'
        '全部验收说明、报告、证据及构建日志放在发布目录的验收资料/；打包仍逐项检查，不因收纳而跳过校验。\n','utf8')
    return release,source

def build(mobile):
    release,source=prepare(mobile)
    with (release/'构建日志.txt').open('w',encoding='utf8') as log:
        subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--distpath',str(release),
                        '--workpath',str(WORK/'build250'/location(mobile)[1]),'desktop.spec'],cwd=source,stdout=log,stderr=subprocess.STDOUT,check=True)

def review(mobile,game):
    release,label=location(mobile)
    # A failed rerun must never leave an older passing receipt usable by ZIP.
    (consolidate_reports(release)/'发布验收.json').unlink(missing_ok=True)
    subprocess.run([str(release/(release.name+'.exe')),'--release-review','--game',str(Path(game).resolve())],check=True)
    (release/'发布验收失败.txt').unlink(missing_ok=True)
    reports=consolidate_reports(release)
    (reports/'发布验收失败.txt').unlink(missing_ok=True)

def package(mobile):
    release,label=location(mobile)
    reports=consolidate_reports(release)
    for name in ('空白秘籍商店冻结验收.json','空白秘籍商店界面验收.json','V250兼容调整验收.json','新版运行库冻结验收.json'):
        current=json.loads((reports/name).read_text('utf8'))
        assert current['passed'] and current['version']==VERSION and current['edition']==label,name
    for name in ('队伍头像冻结验收.json','队伍头像比例修复验收.json','门派引用导入冻结验收.json','重装原版人物导入验收.json'):
        current=json.loads((reports/name).read_text('utf8'))
        assert current['passed'] and current['version']==VERSION and current['edition']==label,name
    for name in ('同名武学导入冻结验收.json','同名武学导入修复验收.json'):
        current=json.loads((reports/name).read_text('utf8'))
        assert current['passed'] and current['version']==VERSION and current['edition']==label,name
    for name in ('人物依赖冻结验收.json','人物依赖显示修复验收.json'):
        current=json.loads((reports/name).read_text('utf8'))
        assert current['passed'] and current['version']==VERSION and current['edition']==label,name
    for name in ('人物放置导入冻结验收.json','人物放置导入修复验收.json'):
        current=json.loads((reports/name).read_text('utf8'))
        assert current['passed'] and current['version']==VERSION and current['edition']==label,name
    for name in ('十一月运行库冻结验收.json','十一月运行库兼容验收.json'):
        current=json.loads((reports/name).read_text('utf8'))
        assert current['passed'] and current['version']==VERSION and current['edition']==label,name
    for name in ('发布验收.json','版别资源验收.json','版别界面验收.json','资源总表验收.json','兼容回归验收.json',
                 '预览保存验收.json','程序与源码一致性验收.json','修复回归验收.json','宠物升级验收.json','奥义原生运行库验收.json','新增功能验收.json','递归导入验收.json','手游武学实战验收.json','武学上限强化验收.json','手游武学冻结预览验收.json','气贯苍穹恢复验收.json','天玑五转恢复验收.json','手游特效资源验收.json','状态触发编号验收.json','宝箱自动入库验收.json','功能开关验收.json','功能开关界面验收.json','暗影新功能兼容验收.json','大地图兼容验收.json','大地图原生功能验收.json','大地图界面验收.json','人物武学兼容验收.json','手游武学大地图兼容验收.json','六属性兼容修复验收.json','六属性入口冻结验收.json','攻击与观察显示修复验收.json','暗影大地图兼容验收.json','暗影大地图冻结验收.json'):
        report=json.loads((reports/name).read_text('utf8'))
        assert report['passed'] and report['version']==VERSION and report['edition']==label,name
    current=json.loads((reports/'动作与收藏修复验收.json').read_text('utf8'))
    assert current['passed'] and current['version']==VERSION and current['edition']==label
    for name in ('角色突破六属性天赋验收.json','角色突破即时修复验收.json','角色突破恢复验收.json','角色突破入口冻结验收.json','角色突破界面修复验收.json','角色突破上限验收.json','功能标签拖拽验收.json','空名称存档冻结验收.json','存档格式修复验收.json'):
        current=json.loads((reports/name).read_text('utf8'))
        assert current['passed'] and current['version']==VERSION and current['edition']==label
    extra=json.loads((reports/'无相剑诀恢复验收.json').read_text('utf8'))
    assert extra['passed'] and extra['version']==VERSION and extra['edition']==label
    required=[release.name+'.exe','源码/desktop_app.py','源码/desktop.spec','源码/requirements.txt',
              '源码/ui_assets/disguise_ui.lua','源码/mobile_martial_pack.json','模型与立绘总表.html','手游专属武学移植说明.html','版本说明.txt',
              '源码/shadow_bigmap.py','源码/shadow_bigmap_v047d.zip','源码/role_breakthrough.py','源码/role_breakthrough_client.py','源码/role_breakthrough_runtime.py',
              '源码/role_breakthrough_roster.py','源码/role_breakthrough_data.py','源码/role_breakthrough_pack.json','源码/ui_assets/role_breakthrough_gifts.lua','角色突破天赋成长说明.html','源码/save_format.py','源码/ui_assets/role_breakthrough_mobile_roster.json','源码/ui_assets/role_breakthrough_panels.lua',
              '源码/ui_assets/role_breakthrough.lua','源码/ui_assets/role_breakthrough_manager.lua','源码/ui_assets/role_breakthrough_mobile_rules.json']
    required+=['源码/blank_manual_shop.py','源码/blank_manual_shop_ui.py','源码/blank_manual_legacy.py','源码/ui_assets/legacy_blank_manual_v246.lua','空白秘籍商店使用说明.txt','源码/nov15_growth_runtime.py','源码/nov15_role_baseline.json']
    if mobile:required+=['mobile_assets/catalog.json','源码/ui_assets/mobile_models.lua']
    for name in required:assert (release/name).is_file(),name
    assert (release/'模型与立绘总表.html').stat().st_size>100000
    reference_report=json.loads((reports/'发布验收.json').read_text('utf8'))
    assert reference_report['reference_sha256']==hashlib.sha256((release/'模型与立绘总表.html').read_bytes()).hexdigest()
    assert not any(p.is_file() and ('验收' in p.name or '验证说明' in p.name) for p in release.iterdir())
    assert (release/'mobile_assets').exists()==mobile
    pack=json.loads((release/'源码/mobile_martial_pack.json').read_text('utf8'))
    receipt=json.loads((reports/'手游武学实战验收.json').read_text('utf8'))
    assert receipt['source_pack_sha256']==hashlib.sha256((release/'源码/mobile_martial_pack.json').read_bytes()).hexdigest()
    assert receipt['restored']==sum(r['available'] for r in pack['manifest']) and receipt['restored']+receipt['skipped']==42
    files=[p for p in release.rglob('*') if p.is_file() and not {'__pycache__','node_modules'}&set(p.parts) and p.name not in ('文件校验.json','构建日志.txt')]
    assert all(len(p.relative_to(release).as_posix().encode('utf8'))<240 for p in files),'ZIP路径过长，先缩短历史验收资料路径；必须通过Windows Shell打开与解压验收'
    manifest={p.relative_to(release).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    (release/'文件校验.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),'utf8');files.append(release/'文件校验.json')
    DEST.mkdir(parents=True,exist_ok=True);target=DEST/(release.name+'.zip')
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for path in files:z.write(path,path.relative_to(release))
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None
        assert set(required)<=set(z.namelist())
        assert any(n.startswith('mobile_assets/') for n in z.namelist())==mobile
    print(json.dumps({'archive':str(target),'bytes':target.stat().st_size,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()},ensure_ascii=False),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','build','review','package'])
    parser.add_argument('edition',choices=['standard','mobile','both']);parser.add_argument('--game');args=parser.parse_args()
    for mobile in ([False,True] if args.edition=='both' else [args.edition=='mobile']):
        if args.action=='review':review(mobile,args.game)
        else:globals()[args.action](mobile)
