"""Only the native blank-manual merchant offer; copying is game-owned."""
from pathlib import Path
import json,re
from object_bundle import Store
from client_config import Assets,lua_rows
from engine import SCHEMAS
from martial_editor import indexed_rows,patch_lua_rows
from codec import decode
from blank_manual_legacy import OLD_STATE,remove_script,retire_fields
STATE='装备编辑器配置/空白秘籍商店.json'
SHOP_ID=2000002460
SHOP=dict(BaseID=SHOP_ID,BusinessManID=19,ItemClass='功能物品',ItemID=9682,MaxCount=20,DiscountID=0,IsReplenish=1,BuyPrice=1,ShowCondition=0,BuyCity=0,BuyInt=0,Difficulty=0,ShowMoney=0,ItemSortID=0)
def inventory(root):
    return tuple(sorted(str(p.resolve()) for t in ('Shop','Item','Businessman','Martial','Story') for p in (Path(root)/'ModProject/GameProject').rglob(t+'_*.json')))
class Reads(dict):pass
def plan(root):
    from feature_fields import sync
    from mod_rows import read_rows
    root=Path(root).resolve();store=Store(root);watched=inventory(root);results=[]
    oldpath=root/OLD_STATE;oldraw=store.read(oldpath);old=json.loads(oldraw) if oldraw is not None else None
    if old is not None:
        expected=dict(version=1,shop=SHOP,asset=45,item=9682)
        if not isinstance(old,dict) or any(old.get(k)!=v for k,v in expected.items()) or set(old)-set(expected)-{'copy_martials'}:raise ValueError('旧版抄录记录存在未知修改，未接管')
        ids=old.get('copy_martials',[])
        if not isinstance(ids,list) or any(type(v)is not int or not 0<v<2147483647 for v in ids) or ids!=sorted(set(ids)):raise ValueError('旧版抄录编号记录无效')
    statepath=root/STATE;raw=store.read(statepath);state=json.loads(raw) if raw is not None else None
    if state is not None and (state.get('version')!=1 or state.get('shop')!=SHOP or state.get('asset')!=45 or state.get('item')!=9682 or set(state)-{'version','shop','asset','item','legacy_retired'}):raise ValueError('空白秘籍商店记录存在未知修改')
    contracts={'Item':(9682,dict(ItemType=43,EffectType=4,GameData=32,Value1='1',Feature=[4,8,16,128])),'Businessman':(19,dict(RoleID=1050114002,BusinessManType=0,UseMoney=0))}
    for table,(i,expected) in contracts.items():
        effective=store.table(table).get(i);copies=[store.read(root/'TableData'/(table+'.bytes'))]
        stream=store.read(root/'DreamRivakes_Data/StreamingAssets'/(table+'.bytes'))
        if stream is not None:copies.append(stream)
        if table in store.assets.scripts:
            _,q,n=store.assets.scripts[table];copies.append(store.assets.data[q+4:q+4+n])
        if effective is None or any(effective.get(k)!=v for k,v in expected.items()):raise ValueError('空白秘籍或本杰明身份不兼容：'+table)
        for data in copies:
            native=indexed_rows(data)[0];row=decode(native[i],table,SCHEMAS) if i in native else {}
            if any(row.get(k)!=v for k,v in expected.items()):raise ValueError('原生空白秘籍或本杰明副本不兼容：'+table)
    for filename in watched:
        path=Path(filename);table=path.name.split('_',1)[0];warnings=[];rows=read_rows(store.read(path),table,SCHEMAS,warnings,path.name)
        if warnings:raise ValueError('无法完整核对商店配置：'+'；'.join(warnings[:3]))
        for row in rows:
            if table=='Shop' and row['BaseID']==SHOP_ID:
                if old is None and state is None:raise ValueError('货架缺少自有安装记录，未接管')
                if any(k not in SHOP or SHOP[k]!=v for k,v in row.items()):raise ValueError('空白秘籍货架已被其他MOD改动')
            if table in contracts and row['BaseID']==contracts[table][0] and any(k in row and row[k]!=v for k,v in contracts[table][1].items()):raise ValueError('MOD空白秘籍或本杰明身份冲突')
    current=store.table('Shop').get(SHOP_ID)
    if current is not None and (current!=SHOP or old is None and state is None):raise ValueError('空白秘籍货架编号已被其他配置占用')
    for directory in ('TableData','DreamRivakes_Data/StreamingAssets'):
        data=store.read(root/directory/'Shop.bytes')
        if data is not None:
            row=indexed_rows(data)[0].get(SHOP_ID)
            if row is not None and decode(row,'Shop',SCHEMAS)!=SHOP:raise ValueError('空白秘籍原生货架冲突')
    if 'Shop' in store.assets.scripts:
        _,q,n=store.assets.scripts['Shop'];row=indexed_rows(store.assets.data[q+4:q+4+n])[0].get(SHOP_ID)
        if row is not None and decode(row,'Shop',SCHEMAS)!=SHOP:raise ValueError('空白秘籍内嵌货架冲突')
    payloads,originals=sync(store,{'Shop':{SHOP_ID:SHOP}})
    p=root/'DreamRivakes_Data/resources.assets';a=Assets(payloads.get(p,store.assets.data));script=a.script('Shop.lua');rows=lua_rows(script,'Shop',store.enums)
    if SHOP_ID in rows and rows[SHOP_ID]!=SHOP:raise ValueError('客户端空白秘籍货架冲突')
    a=Assets(a.replace_script('Shop.lua',patch_lua_rows(script,{SHOP_ID:SHOP})))
    for name in ('MartialUI.lua','MartialUIS.lua'):
        before=a.script(name);after=remove_script(before,name)
        if after!=before:a=Assets(a.replace_script(name,after));results.append('撤下V2.4.6旧抄录自有段：'+name+'；保留原生方法。')
    payloads[p]=a.normalize_text_lengths();originals[p]=store.assets.data
    retired=retire_fields(store,old,payloads,originals,results)
    if old is not None and not retired:
        results.append('未找到可完整证明旧JSON字段来源的备份，保留这些字段；不会猜测或回放旧原生表。旧自有抄录脚本仍按精确字节撤下。')
    cfg=root/'ModProject/GameProject/Mod_MJH/Json/Shop_blank_manual_editor.json';before=store.read(cfg);expected={'Items':[SHOP]}
    if before is not None and json.loads(before)!=expected:raise ValueError('空白秘籍自有货架JSON已被改动')
    payloads[cfg]=json.dumps(expected,ensure_ascii=False,indent=2).encode('utf8');originals[cfg]=before
    new=dict(version=1,shop=SHOP,asset=45,item=9682)
    if old is not None:
        new['legacy_retired']=dict(state_sha256=__import__('hashlib').sha256(oldraw).hexdigest(),json_fields_removed=retired)
        payloads[oldpath]=None;originals[oldpath]=oldraw
    elif state and 'legacy_retired' in state:new['legacy_retired']=state['legacy_retired']
    payloads[statepath]=json.dumps(new,ensure_ascii=False,indent=2).encode('utf8');originals[statepath]=raw
    for path,before in store.reads.items():originals.setdefault(path,before)
    payloads={path:b for path,b in payloads.items() if b!=originals[path]}
    reads=Reads(store.reads);reads.inventory=watched
    results[:0]=['杭州本杰明商店：空白秘籍1铜币/本，每个游戏月20本，沿用原生补货和购买记录。','抄录规则由游戏原版提供；此入口只启用低价货架，保留武学/剧情原生开关和学习条件。','空白秘籍沿用原生全局资产跨周目保留；应用不赠送道具，不写存档。']
    return payloads,originals,results,[],reads
def apply(root,prepared):
    if inventory(root)!=prepared[4].inventory:raise ValueError('配置文件列表已变化，请重新预览')
    from feature_save import apply as commit
    return commit(root,prepared)
