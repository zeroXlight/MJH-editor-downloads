"""Transactional exact-image fix for HarmonyX 2.9 callback initialization."""
from pathlib import Path
import hashlib,json,zlib,base64
DLL='BepInEx/core/0Harmony.dll'
STATE='装备编辑器配置/暗影加载修复.json'

def sha(raw):return hashlib.sha256(raw).hexdigest()

def plan(root,enabled=True):
    from engine import DATA_ROOT
    from shadow_bigmap import plugin_known
    root=Path(root).resolve();path=root/DLL;state=root/STATE
    prior=state.read_bytes() if state.is_file() else None
    if not path.is_file() or (not prior and (not enabled or not plugin_known(root))):return {},{},[],[],{}
    cfg=json.loads((DATA_ROOT/'ui_assets/shadow_harmony_init.json').read_text('utf8'))
    images={k:zlib.decompress(base64.b64decode(cfg[k]['zlib_base64'])) for k in ('before','after')}
    if any(sha(images[k])!=cfg[k]['sha256'] for k in images):raise ValueError('暗影加载修复资源摘要不匹配，未覆盖')
    raw=path.read_bytes();reads={path:raw,state:prior}
    if raw not in images.values():
        if prior:raise ValueError('暗影加载组件在本编辑器修复后又被修改，保留现有文件')
        return {},{},[],['暗影加载组件不是本版核对的HarmonyX 2.9，保留现有组件。'],reads
    for name,want in cfg['dependencies'].items():
        p=root/'BepInEx/core'/name;b=p.read_bytes() if p.is_file() else None;reads[p]=b
        if b is None or sha(b)!=want:raise ValueError('暗影加载修复依赖已变化，未覆盖：'+name)
    if prior:
        doc=json.loads(prior)
        if doc.get('original_sha256')!=cfg['before']['sha256'] or doc.get('fixed_sha256')!=cfg['after']['sha256']:raise ValueError('暗影加载修复记录未认证，未覆盖')
    after=images['after' if enabled else 'before'];payloads={};originals={}
    if after!=raw:payloads[path]=after;originals[path]=raw
    doc=dict(version=1,enabled=enabled,original_sha256=cfg['before']['sha256'],fixed_sha256=cfg['after']['sha256'])
    value=json.dumps(doc,ensure_ascii=False,indent=2).encode('utf8')
    if value!=prior:payloads[state]=value;originals[state]=prior
    return payloads,originals,['暗影加载：'+('修复回调初始化顺序，保留原挂钩和业务脚本。' if enabled else '暂时还原本编辑器拥有的初始化修复，便于安装或卸载MOD。')],[],reads
