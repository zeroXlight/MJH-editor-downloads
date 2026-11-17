"""Ordinary data writes use their parsers; native code writes keep certification."""
from pathlib import Path
from engine import digest, META

def validate_native_writes(root, payloads, originals):
    root = Path(root).resolve()
    plugins = root / 'DreamRivakes_Data/Plugins'
    native_changes = [Path(p) for p, data in payloads.items()
                      if Path(p).suffix.lower() in ('.dll', '.exe') and data != originals.get(Path(p))]
    if not native_changes: return
    client=plugins/'ClientDll.dll'
    from martial_limit_enhance import certified_transition as limit_transition
    from shadow_runtime import client_supported
    if native_changes==[client] and client_supported(root,originals.get(client,b'')) and limit_transition(originals.get(client,b''),payloads[client]):return
    from external_runtime import certified_transition,DLL
    race=root/DLL
    if native_changes==[race] and certified_transition(originals.get(race,b''),payloads[race]):return
    from recruitment_runtime import certified_transition as recruitment_transition
    if native_changes==[race] and recruitment_transition(originals.get(race,b''),payloads[race]):return
    from chest_autoloot import certified_transition as chest_transition
    if native_changes==[race] and chest_transition(originals.get(race,b''),payloads[race]):return
    from interaction_unlock import certified_transition as interaction_transition
    if native_changes==[race] and interaction_transition(originals.get(race,b''),payloads[race]):return
    from six_attrs_runtime import certified_transition as six_transition
    if native_changes==[race] and six_transition(originals.get(race,b''),payloads[race]):return
    from attribute_uncap import certified_transition as uncap_transition
    if native_changes==[race] and uncap_transition(originals.get(race,b''),payloads[race]):return
    from growth_runtime import supported_patch
    for filename, expected in META['native_hashes'].items():
        path = plugins / filename
        raw = path.read_bytes() if path.is_file() else None
        if filename=='ClientDll.dll' and raw is not None and client_supported(root,raw):continue
        if raw is None or (digest(raw) != expected and
                           (filename != 'RaceLogic_Release_x64.dll' or not supported_patch(raw))):
            raise ValueError('普通存档与配置编辑可用，但本次涉及原生运行库补丁；当前运行库未认证，不能安装独立成长或技能范围支持：'+filename)
    for path in native_changes:
        if path != plugins / 'RaceLogic_Release_x64.dll' or not supported_patch(payloads[path]):
            raise ValueError('本次原生运行库写入未通过补丁校验：'+str(path))

def status(catalog):
    count=len(getattr(catalog,'mod_warnings',[]))
    note=f' 已隔离 {count} 项异常 MOD 配置（不影响其他记录读取）。' if count else ''
    shadow=getattr(catalog,'shadow_status','')
    if shadow:note+=' '+shadow
    if catalog.supported: return note
    return ' MOD 兼容：普通存档与配置按结构校验；原生补丁需单独认证。'+note
