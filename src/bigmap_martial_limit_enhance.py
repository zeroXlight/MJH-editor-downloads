# Generated for the exact certified big-map native build. See native mapping evidence.
"""Native collection reinforcement from level ten; fixed 100 remains per level."""
from pathlib import Path
import hashlib,json,re

RVA=0xbaad1e
START=0xbaaad0
LENGTH=0x6c3
FUNCTION_SHA='65242c1598d7a709312854180174d78742b8d5c3948609ab4e77947418a9933c'
CLIENT='DreamRivakes_Data/Plugins/ClientDll.dll'
STATE='装备编辑器配置/全武学等级上限强化.json'
MARK='-- MJH_LIMIT_ENHANCE_230'

def normalize_client(raw):
    from role_breakthrough_client import detach,_build
    raw,breakthrough=detach(raw)
    import pefile
    pe=pefile.PE(data=raw,fast_load=True);off=pe.get_offset_from_rva(RVA)
    code=raw[off:off+5]
    if code not in (bytes.fromhex('837c24680a'),bytes.fromhex('837c246800')):raise ValueError('武学上限强化入口已被其他补丁修改')
    out=bytearray(raw);out[off+4]=10
    at=pe.get_offset_from_rva(START)
    if hashlib.sha256(out[at:at+LENGTH]).hexdigest()!=FUNCTION_SHA:raise ValueError('武学上限强化完整计算入口不匹配，未修改')
    result=bytes(out)
    return (_build(result) if breakthrough else result),code[-1]==0

def patch_client(raw,enabled):
    import pefile
    result,_=normalize_client(raw)
    if not enabled:return result
    from role_breakthrough_client import detach,_build
    result,breakthrough=detach(result)
    off=pefile.PE(data=result,fast_load=True).get_offset_from_rva(RVA)
    out=bytearray(result);out[off+4]=0;return _build(bytes(out)) if breakthrough else bytes(out)

def certified_transition(before,after):
    try:
        a,_=normalize_client(before);b,_=normalize_client(after)
        return a==b
    except Exception:return False

def _patch_limit_ui(text,enabled):
    if enabled:
        if MARK in text:return text
        old='local GrowUpLevelLimitUp = 10;'
        if text.count(old)!=1:raise ValueError('武学收藏强化入口不兼容')
        text=text.replace(old,'local GrowUpLevelLimitUp = 0; '+MARK)
        old='self:CanLevelUp(rank, level + GrowUpLevelLimitUp)'
        if text.count(old)!=1:raise ValueError('武学收藏上限判定入口不兼容')
        return text.replace(old,'self:CanLevelUp(rank, level + BaseLevelLimitUp) --[[MJH_LIMIT_MAX_230]]')
    return text.replace('local GrowUpLevelLimitUp = 0; '+MARK,'local GrowUpLevelLimitUp = 10;').replace('self:CanLevelUp(rank, level + BaseLevelLimitUp) --[[MJH_LIMIT_MAX_230]]','self:CanLevelUp(rank, level + GrowUpLevelLimitUp)')

def patch_ui(text,enabled):
    from collection_ui_runtime import patch
    return patch(_patch_limit_ui(text,enabled))

def plan(root,enabled=True):
    from object_bundle import Store
    from martial_editor import patch_table,patch_lua_rows
    from client_config import Assets
    root=Path(root).resolve();s=Store(root);payloads={};results=[]
    raw=s.read(root/STATE);prior=json.loads(raw) if raw else {}
    rows=s.table('MartialBreakRemainsConfig');remembered=prior.get('original',{})
    if enabled:
        if not remembered:remembered={str(i):dict(r) for i,r in rows.items()}
        desired={}
        for i,r in rows.items():
            if r['MartialRank'] not in range(1,8) or not r['MartialLevel']:raise ValueError('武学残文品质／等级配置不明确')
            maximum=max(r['MartialLevel'])
            if not 20<=maximum<=250:raise ValueError('当前MOD强化范围未校验，未覆盖')
            levels=list(range(11,maximum+1));desired[i]={**r,'MartialLevel':levels,'ConsumeNum':[100]*len(levels)}
        results.append('启用：已收藏普通武学从10级上限起可强化，每次提升1级，固定消耗100武学残文。')
        results.append('沿用各品质当前残文种类及最终强化上限；不赠送残文，不修改已学等级和已有收藏进度。')
    else:
        if not remembered:raise ValueError('没有本编辑器记录的强化原配置，未修改')
        desired={int(i):r for i,r in remembered.items()}
        if set(desired)!=set(rows):raise ValueError('强化表记录已变化，请先处理外部MOD，未覆盖')
        results.append('关闭：恢复原强化入口与消耗表；已经获得的等级上限和收藏进度保留。')
    for directory in ('TableData','DreamRivakes_Data/StreamingAssets'):
        p=root/directory/'MartialBreakRemainsConfig.bytes';before=s.read(p)
        if before is not None:payloads[p]=patch_table(before,'MartialBreakRemainsConfig',desired)
    p=root/'DreamRivakes_Data/resources.assets';a=Assets(s.assets.data)
    if 'MartialBreakRemainsConfig' in a.scripts:
        _,q,n=a.scripts['MartialBreakRemainsConfig'];a=Assets(a.replace_blob('MartialBreakRemainsConfig',patch_table(a.data[q+4:q+4+n],'MartialBreakRemainsConfig',desired)))
    a=Assets(a.replace_script('MartialBreakRemainsConfig.lua',patch_lua_rows(a.script('MartialBreakRemainsConfig.lua'),desired)))
    from collection_ui_runtime import repair
    payloads[p]=repair(a.replace_script('CollectionMartialUI.lua',patch_ui(a.script('CollectionMartialUI.lua'),enabled)))
    p=root/CLIENT;before=s.read(p)
    from shadow_runtime import client_supported
    if not client_supported(root,before):raise ValueError('当前客户端运行库尚未认证，未安装强化功能')
    payloads[p]=patch_client(before,enabled)
    payloads[root/STATE]=json.dumps({'version':1,'enabled':enabled,'original':remembered},ensure_ascii=False,indent=2).encode('utf8')
    payloads={p:v for p,v in payloads.items() if s.read(p)!=v}
    return payloads,dict(s.reads),results,[],dict(s.reads)
