"""Detect Shadow and call its external installer; no compatibility payload here."""
import hashlib,json,subprocess,sys,struct
from pathlib import Path

DLL='DreamRivakes_Data/Plugins/RaceLogic_Release_x64.dll'
CLIENT='DreamRivakes_Data/Plugins/ClientDll.dll'
PLUGIN='BepInEx/plugins/XiakeConsultFix.dll'
FLAGS='BepInEx/plugins/XiakeConsultFix/features.txt'
RECEIPT='暗影兼容补丁/安装状态.json'
PROFILE_SHA='d5bd0780048ef85be8f129c4db2b0ebeeadc3e4a5b6ca74d8256c0859cb4e5e3'
TOOL_DIRECTORY='暗影兼容补丁V1.0.2'
TOOL_SHA='8bd182b6e40c79593784ac26e094f5e25121c9d1d311d21268482543f06cbcb5'
_profile_cache=None
_game_hint=None
INSTALLED_PROFILE='暗影兼容补丁/兼容校验.json'

def sha(raw):return hashlib.sha256(raw).hexdigest()

def candidate_directories(root=None):
    base=Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[1]
    seen=set()
    for parent in (base,base.parent,Path(root or _game_hint).resolve() if (root or _game_hint) else None):
        if parent is None:continue
        folders=[parent/TOOL_DIRECTORY,parent/'暗影兼容补丁',parent]
        try:folders+=sorted((p for p in parent.iterdir() if p.is_dir()),key=lambda p:p.name)
        except OSError:pass
        for folder in folders:
            key=str(folder.resolve()).casefold()
            if key not in seen:seen.add(key);yield folder

def tool_directory(root=None):
    incompatible=[]
    for folder in candidate_directories(root):
        exe=folder/'暗影兼容补丁.exe';cfg=folder/'shadow_runtime_profile.json'
        if not exe.is_file():continue
        try:
            if sha(exe.read_bytes())==TOOL_SHA and cfg.is_file() and sha(cfg.read_bytes())==PROFILE_SHA:return folder
            incompatible.append(str(folder))
        except OSError:continue
    if incompatible:raise ValueError('已找到独立补丁，但程序或校验文件版本不匹配。请使用本版独立补丁；位置：'+'；'.join(incompatible))
    raise ValueError('未找到独立暗影兼容补丁。可将补丁放在编辑器目录、编辑器旁任意文件夹，或游戏目录内；请保留暗影兼容补丁.exe和shadow_runtime_profile.json')

def profile(root=None):
    global _profile_cache
    if _profile_cache is None:
        hint=root or _game_hint
        files=([Path(hint)/INSTALLED_PROFILE] if hint else [])
        files.extend(folder/'shadow_runtime_profile.json' for folder in candidate_directories(root))
        for path in files:
            try:raw=path.read_bytes()
            except OSError:continue
            if sha(raw)==PROFILE_SHA:_profile_cache=json.loads(raw);break
        if _profile_cache is None:raise ValueError('缺少经过验证的暗影兼容校验文件；请完整解压独立补丁，或用新版独立工具安装一次')
    return _profile_cache

def detected(root):
    global _game_hint
    root=Path(root)
    _game_hint=root.resolve()
    return (root/PLUGIN).is_file() and (root/FLAGS).is_file()

def known(root):
    if detected(root):
        from bigmap_profile import race_image,client_image
        from shadow_bigmap import plugin_known
        try:
            if plugin_known(root) and race_image((Path(root)/DLL).read_bytes()) and client_image((Path(root)/CLIENT).read_bytes()):return True
        except (OSError,ValueError):pass
    try:return detected(root) and sha((Path(root)/PLUGIN).read_bytes())==profile(root)['plugin_sha256']
    except (OSError,ValueError):return False

def client_supported(root,raw=None):
    from engine import META
    raw=(Path(root)/CLIENT).read_bytes() if raw is None else raw
    from bigmap_profile import client_image
    if client_image(raw):return True
    try:
        from martial_limit_enhance import normalize_client
        raw,_=normalize_client(raw)
        from pet_runtime import original as pet_original
        raw=pet_original(raw)
    except (ValueError,KeyError,TypeError,struct.error):return False
    expected=META['native_hashes']['ClientDll.dll']
    if sha(raw)==expected:return True
    if not known(root):return False
    cfg=profile()['client'];at=cfg['offset'];size=cfg['size']
    if raw[at:at+size]!=bytes.fromhex(cfg['patched_code']):return False
    for g in cfg['guards']:
        if sha(raw[g['offset']:g['offset']+g['size']])!=g['sha256']:return False
    return sha(raw[:at]+bytes.fromhex(cfg['original_code'])+raw[at+size:])==expected

def certify_features(raw,pe,six_attrs=False):
    guards=list(profile()['common_guards'])
    if six_attrs:guards+=profile()['six_guards']
    for g in guards:
        try:off=pe.get_offset_from_rva(g['rva'])
        except Exception as error:raise ValueError('运行库计算依赖位置不匹配：'+hex(g['rva'])) from error
        if sha(raw[off:off+g['size']])!=g['sha256']:
            raise ValueError('运行库计算依赖已被其他补丁修改：'+hex(g['rva'])+'，已保留现有 MOD')

def ready(root,raw=None):
    try:
        from bigmap_profile import race_image,client_image
        from shadow_bigmap import plugin_known
        if detected(root) and plugin_known(root) and race_image((Path(root)/DLL).read_bytes() if raw is None else raw) and client_image((Path(root)/CLIENT).read_bytes()):return True
        if not known(root) or not client_supported(root):return False
        from growth_runtime import supported_patch
        return supported_patch((Path(root)/DLL).read_bytes() if raw is None else raw)
    except (OSError,ValueError,KeyError):return False

def ensure(root):
    if not detected(root):return ''
    try:
        from bigmap_profile import race_image,client_image
        from shadow_bigmap import plugin_known
        if plugin_known(root) and race_image((Path(root)/DLL).read_bytes()) and client_image((Path(root)/CLIENT).read_bytes()):
            return '暗影大地图兼容：运行库通过完整还原认证，支持编辑器预览及备份应用；保留暗影现有改动，无需旧版独立补丁。'
        if ready(root):return '暗影兼容：已验证已安装补丁，保留现有暗影功能。'
        folder=tool_directory(root);exe=folder/'暗影兼容补丁.exe'
        if exe.is_file():
            if sha(exe.read_bytes())!=TOOL_SHA:raise ValueError('独立补丁程序版本不匹配，请使用暗影兼容补丁 V1.0.2')
            command=[str(exe)]
        elif not getattr(sys,'frozen',False) and (folder/'源码/patcher.py').is_file():
            command=[sys.executable,str(folder/'源码/patcher.py')]
        else:raise ValueError('独立暗影兼容补丁程序缺失，请解压完整的独立补丁包')
        result=subprocess.run(command+['--auto','--game-dir',str(Path(root).resolve()),'--json'],
                              capture_output=True,text=True,encoding='utf8',timeout=60,
                              creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:doc=json.loads(result.stdout)
        except ValueError:raise ValueError('独立补丁未返回有效结果：'+result.stderr[-500:])
        if not doc.get('ok') or not ready(root):raise ValueError(str(doc.get('message','独立补丁安装后校验未通过')))
        return str(doc['message'])
    except (OSError,ValueError,KeyError,subprocess.TimeoutExpired) as error:
        return '暗影兼容未就绪：'+str(error)+'。普通配置仍可读取。'

def require_ready(root):
    if detected(root) and not ready(root):
        raise ValueError('暗影兼容补丁尚未就绪，请退出游戏后重新读取目录；独立补丁应与编辑器文件夹放在同一目录。')
