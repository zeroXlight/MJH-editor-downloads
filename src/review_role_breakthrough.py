"""Read-only acceptance of the new feature inside each delivered executable."""
import json,sys,hashlib
from pathlib import Path
def run():
    from edition import VERSION,EDITION_NAME
    from review_edition import output
    from role_breakthrough import plan,BEGIN
    from role_breakthrough_client import detach,COSTS
    from client_config import Assets
    from engine import DATA_ROOT
    from external_runtime import detach as race_detach
    from role_breakthrough_roster import roster
    from object_bundle import Store
    root=Path(sys.argv[sys.argv.index('--game')+1]).resolve();cases=[]
    for enabled in (True,False):
        value=plan(root,enabled)
        assert all((p.read_bytes() if p.exists() else None)==b for p,b in value[1].items())
        assert all((p.read_bytes() if p.exists() else None)==b for p,b in value[4].items())
        assert not any(p.suffix in ('.sav','.check','.checksave') for p in value[0])
        asset=root/'DreamRivakes_Data/resources.assets';a=Assets(value[0].get(asset,asset.read_bytes()))
        assert (BEGIN in a.script('LoginUI.lua'))==enabled
        assert (BEGIN in a.script('RoleCardsUpgradeUI.lua'))==enabled
        assert BEGIN in a.script('CardsUpgradeDataManager.lua')
        client=root/'DreamRivakes_Data/Plugins/ClientDll.dll';assert detach(value[0].get(client,client.read_bytes()))[1]==enabled
        race=root/'DreamRivakes_Data/Plugins/RaceLogic_Release_x64.dll';mode=race_detach(value[0].get(race,race.read_bytes()))[1]['role_breakthrough'];assert mode==(True if enabled else 2)
        from role_breakthrough_runtime import SYNC_MAGIC
        assert SYNC_MAGIC in value[0].get(race,race.read_bytes())
        cases.append(dict(enabled=enabled,files=len(value[0]),mode=mode,save_free=True))
    mobile=json.loads((DATA_ROOT/'ui_assets/role_breakthrough_mobile_rules.json').read_text('utf8'))
    assert [mobile['role_piece'][str(i)]['Piece']*500 for i in range(1,11)]==list(COSTS)
    prefix,roster_info=roster(Store(root))
    pack=json.loads((DATA_ROOT/'role_breakthrough_pack.json').read_text('utf8'))
    assert roster_info['mobile_source_count']==276 and roster_info['mobile_present']==len(pack['visible_role_ids'])
    assert not pack['Item'] and not any(r['EffectEnum']==2 for r in pack['RoleCard'].values())
    assert 1700000000 in roster_info['custom_ids'] and roster_info['custom_present']>=1
    a=Assets((root/'DreamRivakes_Data/resources.assets').read_bytes())
    assert prefix in a.script('CardsUpgradeDataManager.lua')
    assert (DATA_ROOT/'ui_assets/role_breakthrough_panels.lua').read_text('utf8') in a.script('RoleCardsUpgradeUI.lua')
    assert (DATA_ROOT/'ui_assets/role_breakthrough.lua').read_text('utf8') in a.script('RoleCardsUpgradeUI.lua')
    assert 'if kind==2 then return 10 end' in a.script('CardsUpgradeDataManager.lua')
    client=root/'DreamRivakes_Data/Plugins/ClientDll.dll'
    from role_breakthrough_client import _build
    parent,enabled=detach(client.read_bytes());assert enabled and _build(parent,2)==client.read_bytes()
    report=dict(version=VERSION,edition=EDITION_NAME,passed=True,frozen=bool(getattr(sys,'frozen',False)),cases=cases,mobile_curve_verified=True,roster=roster_info,real_custom_role_preserved=True,game_unchanged=True)
    (output()/'角色突破入口冻结验收.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
