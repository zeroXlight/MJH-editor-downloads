"""Feature-scoped compatibility: keep MOD runtime, preserve failed optional steps."""
from pathlib import Path

def note(owner,message):
    values=owner if isinstance(owner,list) else getattr(owner,'compat_notes',None)
    if values is None:values=[];owner.compat_notes=values
    if message not in values:values.append(message)

def attempt(owner,label,action,original):
    try:return action()
    except (ValueError,KeyError) as error:
        note(owner,label+'已跳过：'+str(error));return original

def native_supported(root,raw=None):
    from growth_runtime import _original
    from engine import META,digest
    root=Path(root)
    try:
        data=raw if raw is not None else (root/'DreamRivakes_Data/Plugins/RaceLogic_Release_x64.dll').read_bytes()
        from growth_runtime import supported_patch
        bridge=b'"external_parent_sha256"' in data and supported_patch(data)
        from shadow_runtime import ready,client_supported
        bridge=bridge or ready(root,data)
        flags=root/'BepInEx/plugins/XiakeConsultFix/features.txt'
        if flags.exists():
            native_keys={'optimize.exclusive','optimize.countrule','optimize.chuangwang','optimize.dynrank','optimize.wishfill','balance.exp','fix.chetmartialexp','optimize.equipnolimit','optimize.learnnolimit','optimize.staticmax','optimize.recast','optimize.dualartifact','optimize.aoyi','optimize.fragment','optimize.uncollectiblecap','optimize.mazesweep','optimize.randomequip','optimize.wishtalents','optimize.clantalents','optimize.giftmastery','fix.harvest'}
            for line in flags.read_text(encoding='utf-8-sig').splitlines():
                key,sep,value=line.partition('=')
                if sep and key.strip() in native_keys and value.strip().lower() in ('1','true','on') and not bridge:return False
        _original(data)
        client=(root/'DreamRivakes_Data/Plugins/ClientDll.dll').read_bytes()
        return client_supported(root,client)
    except (OSError,ValueError):return False

def require_native(lib,label):
    if not native_supported(lib.root):raise ValueError(label+'需要匹配的游戏运行库；当前已跳过该功能，其他配置仍可编辑，暗影运行库保持原样')

def stage(lib,payloads,originals):
    messages=list(getattr(lib,'compat_notes',[]))+list(getattr(lib,'mod_warnings',[]))
    if not messages:return payloads,originals
    path=lib.root/'装备编辑器配置/兼容性提示.txt'
    originals.setdefault(path,path.read_bytes() if path.exists() else None)
    payloads[path]=('本次操作的兼容性提示\n\n'+'\n'.join(dict.fromkeys(messages))+'\n').encode('utf8')
    return payloads,originals

def summary(lib):
    return '\n\n兼容提示：\n'+'\n'.join(getattr(lib,'compat_notes',[])) if getattr(lib,'compat_notes',[]) else ''

def changed_native_growth(lib):
    from growth_runtime import custom_values
    keys=['EffectEnum1','EffectEnum2','AttrEnum1','AttrEnum2','Effect1Value','Effect2Value']
    for ident,row in lib.changes['MartialItem'].items():
        effective=lib.tables['MartialItem'][ident]
        if not any(custom_values(effective,slot) for slot in (1,2)):continue
        source=lib.sources['MartialItem'].get(ident,ident)
        original=getattr(lib,'native_clause_original',{}).get(source)
        if original is None or any(effective.get(k)!=original.get(k) for k in keys):return True
    return False
