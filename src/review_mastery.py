"""Reproducible acceptance on temporary copies; never writes to the real game."""
import copy
import gc
import hashlib
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from martial_mastery import (MASTERY, choose_changes, plan, apply, native_rows)
from client_config import Assets, lua_rows
from codec import decode
from engine import SCHEMAS
from martial_growth import growth_lua
from object_bundle import Store
from edition import VERSION, EDITION_NAME


def pure_checks():
    clauses={cid:{'EffectEnum1':7,'AttrEnum1':attr,'Effect1Value':[10]} for attr,cid in MASTERY.values()}
    formulas={49152+attr:{'AttrType':attr,'KfType':0,'IsRoleAttr':1,'IsGrowup':1,
                         'RankDatas':[0,4,6,8,10,10,1,1,1]} for attr in range(9,17)}
    martials={100+rank*10+depart:{'Rank':rank,'DepartEnum':depart,'LvLimit':30,'GrowProIDs':[]}
              for rank in (6,7) for depart in MASTERY}
    original=copy.deepcopy((martials,clauses,formulas))
    changes,_,_=choose_changes(martials,clauses,formulas,None,None)
    assert len(changes['Martial'])==16 and not changes['KungfuBase']
    for ident,delta in changes['Martial'].items():
        assert delta['GrowProIDs']==[MASTERY[martials[ident]['DepartEnum']][1]]
    assert original==(martials,clauses,formulas)
    for i,delta in changes['Martial'].items():martials[i].update(delta)
    assert not choose_changes(martials,clauses,formulas,None,None)[0]['Martial']
    changes,_,_=choose_changes(martials,clauses,formulas,12,18)
    assert len(changes['KungfuBase'])==8
    assert all(r['RankDatas']==[0,4,6,8,10,10,12,18,1] for r in changes['KungfuBase'].values())
    # Independent growth in either slot is retained; unusual/hidden arts skip.
    clauses[999]={'EffectEnum2':7,'AttrEnum2':10,'Effect2Value':[77,-123]}
    special={1:{'Rank':6,'DepartEnum':3,'GrowProIDs':[999]},
             2:{'Rank':6,'DepartEnum':6},3:{'Rank':7,'DepartEnum':13},
             4:{'Rank':7,'DepartEnum':3,'Display':0},
             5:{'Rank':7,'DepartEnum':3,'LvLimit':1},
             6:{'Rank':5,'DepartEnum':3}}
    assert not choose_changes(special,clauses,formulas,12,18)[0]['Martial']
    for values in ((0,18),(12,1001),('12',18),(None,18),(True,18)):
        try:choose_changes({},clauses,formulas,*values)
        except ValueError:pass
        else:raise AssertionError('invalid numbers accepted')
    return ['八系／两品质补回','只补回不改公式','重复执行不重复添加','独立／双效果成长保留',
            '特殊系别／隐藏／不可训练跳过','金12暗18与数值边界']


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def run(game,output):
    game=Path(game).resolve();output=Path(output);output.mkdir(parents=True,exist_ok=True)
    report={'version':VERSION,'edition':EDITION_NAME,'passed':False,'checks':pure_checks()}
    original=plan(game);report['preview']=original.results[:6]
    hashes={p:sha(p) for p in original.reads if p.exists()}
    with tempfile.TemporaryDirectory(prefix='mjh-mastery-',dir=output.resolve()) as tmp:
        root=Path(tmp).resolve()
        for path,raw in original.reads.items():
            if raw is None:continue
            target=root/path.relative_to(game);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        # The shared transaction audit loads the complete martial library.
        for folder in ('TableData','ModProject/GameProject/Mod_MJH/Json','装备编辑器配置','mod/editor_model_textures'):
            source=game/folder
            if source.exists():shutil.copytree(source,root/folder,dirs_exist_ok=True)
        runtime=game/'DreamRivakes_Data/Plugins/RaceLogic_Release_x64.dll'
        target=root/runtime.relative_to(game);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(runtime,target)
        # A save sentinel proves the feature never changes save contents.
        save=root/'Save.sav';save.write_bytes(b'unchanged save sentinel')
        first=plan(root)
        assert not any(p.name=='KungfuBase.bytes' for p in first.payloads)
        assets=Assets(first.payloads.get(root/'DreamRivakes_Data/resources.assets') or first.reads[root/'DreamRivakes_Data/resources.assets'])
        before=Assets(first.reads[root/'DreamRivakes_Data/resources.assets'])
        assert assets.script('KungfuBase.lua')==before.script('KungfuBase.lua')
        for n in ('KungfuBase','MartialItem','MartialDataManager.lua'):
            if n in before.scripts:
                _,q,k=before.scripts[n];_,q2,k2=assets.scripts[n]
                assert before.data[q+4:q+4+k]==assets.data[q2+4:q2+4+k2]
        # Ensure every native row/unknown protobuf field not targeted is exact.
        native_before=native_rows(first.reads[root/'TableData/Martial.bytes'],'Martial')
        native_after=native_rows(first.payloads.get(root/'TableData/Martial.bytes') or first.reads[root/'TableData/Martial.bytes'],'Martial')
        changed={i for i in native_before if native_before[i]!=native_after[i]}
        for ident in changed:
            old=decode(native_before[ident],'Martial',SCHEMAS);new=decode(native_after[ident],'Martial',SCHEMAS)
            assert {k:v for k,v in old.items() if k!='GrowProIDs'}=={k:v for k,v in new.items() if k!='GrowProIDs'}
            assert new['GrowProIDs'][1:]==old.get('GrowProIDs',[])
        report['native_rows_restored']=len(changed)
        with patch('engine.ensure_closed'):
            first_backup=apply(first)
        del original,first,assets,before;gc.collect()
        second=plan(root);assert not second.payloads
        del second;gc.collect()
        report['checks']+=['游戏副本实际写入／备份','只补回时成长公式和运行逻辑字节不变','原词条和其他武学字段保留','补回后再次预览无写入']
        adjust=plan(root,12,18)
        assert root/'TableData/Martial.bytes' not in adjust.payloads
        assert all(p.suffix.lower() not in ('.dll','.exe','.sav') for p in adjust.payloads)
        with patch('engine.ensure_closed'):adjust_backup=apply(adjust)
        del adjust;gc.collect()
        store=Store(root);raw=store.read(root/'TableData/KungfuBase.bytes');native=native_rows(raw,'KungfuBase')
        client=growth_lua(store.assets.script('KungfuBase.lua'),store.enums)
        _,q,k=store.assets.scripts['KungfuBase'];embedded=native_rows(store.assets.data[q+4:q+4+k],'KungfuBase')
        for i in range(49161,49169):
            expected=decode(native[i],'KungfuBase',SCHEMAS)
            assert expected==client[i]==decode(embedded[i],'KungfuBase',SCHEMAS)
            assert expected['RankDatas'][6:8]==[12,18]
        del store;gc.collect()
        assert not plan(root,12,18).payloads
        changed_plan=plan(root,13,19)
        assert root/'TableData/KungfuBase.bytes' in changed_plan.payloads
        assert root/'TableData/Martial.bytes' not in changed_plan.payloads
        # Stale previews and a newly installed MOD cannot be written.
        extra=root/'ModProject/GameProject/Mod_MJH/Json/Martial_new.json';extra.parent.mkdir(parents=True,exist_ok=True);extra.write_text('{"Items":[]}',encoding='utf-8')
        try:apply(changed_plan)
        except ValueError as error:assert '列表已变化' in str(error)
        else:raise AssertionError('new MOD accepted after preview')
        extra.unlink();del changed_plan;gc.collect()
        stale=plan(root,13,19);config=root/'TableData/MartialItem.bytes';raw=config.read_bytes();config.write_bytes(raw+b'\0')
        try:
            with patch('engine.ensure_closed'):apply(stale)
        except ValueError as error:assert '配置已变化' in str(error)
        else:raise AssertionError('stale preview accepted')
        config.write_bytes(raw);del stale;gc.collect()
        from engine import restore
        with patch('engine.ensure_closed'):
            restore(root,adjust_backup/'manifest.json')
            assert not plan(root).payloads
            restore(root,first_backup/'manifest.json')
        for path,expected in hashes.items():assert sha(root/path.relative_to(game))==expected
        assert save.read_bytes()==b'unchanged save sentinel'
        report['checks']+=['调整后逻辑表／嵌入表／Lua公式一致','调整可重复执行且不重复补词条','可再次自定义数值',
                           '预览后文件变化拒绝写入','预览后新增MOD拒绝写入','两步备份逐字节恢复','存档完全不变']
    assert all(sha(p)==value for p,value in hashes.items())
    report['checks'].append('用户真实游戏文件校验不变');report['passed']=True
    (output/'恢复武学精通验收.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report


def review_ui(window,bridge):
    def wait(fn,seconds=120):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            if fn():return
            time.sleep(.1)
        raise TimeoutError('恢复武学精通界面等待超时')
    def walk(node):
        if not node:return
        yield node
        for child in node.get('children',[]):yield from walk(child)
        if node.get('body'):yield from walk(node['body'])
    def nodes():return list(walk(bridge.state().get('feature')))
    try:
        wait(lambda:not bridge.state().get('busy') and bridge.state().get('equipment',{}).get('saveOptions'))
        bridge.command('page',{'page':'features'})
        wait(lambda:any(n.get('kind')=='tabs' for n in nodes()))
        notebook=next(n for n in nodes() if n.get('kind')=='tabs')
        tab=next(t for t in notebook['tabs'] if t['label']=='恢复武学精通')
        bridge.command('tab',{'id':notebook['id'],'key':tab['key']})
        wait(lambda:len([n for n in nodes() if n.get('kind')=='input'])==2)
        inputs=[n for n in nodes() if n.get('kind')=='input']
        assert [n['value'] for n in inputs]==['12','18'] and all(n['disabled'] for n in inputs)
        check=next(n for n in nodes() if n.get('kind')=='check')
        assert not check['value']
        bridge.command('check',{'id':check['id']})
        wait(lambda:all(not n['disabled'] for n in nodes() if n.get('kind')=='input'))
        for n,value in zip(inputs,['13','19']):bridge.command('value',{'id':n['id'],'value':value})
        bridge.command('check',{'id':check['id']})
        wait(lambda:all(n['disabled'] for n in nodes() if n.get('kind')=='input'))
        preview=next(n for n in nodes() if n.get('kind')=='button' and n.get('text')=='预览恢复武学精通')
        bridge.command('invoke',{'id':preview['id']})
        wait(lambda:any('保留当前每级精通数值（不改成长公式）' in n.get('value','') for n in nodes() if n.get('kind')=='text'))
        assert '恢复武学精通' in window.evaluate_js('document.body.innerText')
        report={'version':VERSION,'edition':EDITION_NAME,'passed':True,'default_restore_only':True,
                'optional_values':[12,18],'editable_values_verified':[13,19],'read_only_preview':True,'errors':bridge.errors}
        assert not bridge.errors,bridge.errors
        out=Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).parent.parent
        (out/'恢复武学精通界面验收.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        time.sleep(.4)
        from PIL import ImageGrab
        bounds=window.native.Bounds
        ImageGrab.grab(bbox=(bounds.X,bounds.Y,bounds.Right,bounds.Bottom)).save(out/'恢复武学精通界面.png')
    finally:
        bridge.allow_close=True;window.destroy()


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--game',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();print(json.dumps(run(args.game,args.output),ensure_ascii=False,indent=2))
