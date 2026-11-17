"""Local data-only library snapshots. Cache hits never read game sources.

Original file bytes remain in the snapshot so existing save planners still
compare real files before writing. Cache snapshots never contain drafts.
"""
import hashlib, os, tempfile, zlib
from datetime import datetime
from pathlib import Path
import msgpack

MAGIC=b'MJHC024\0'
from edition import EDITION_NAME
REVISION='V2.4.5-dependencies-1-'+EDITION_NAME
MAX_BYTES=1024**3
KINDS=('martial','role','catalog')

def cache_directory(root):
    base=Path(os.environ.get('LOCALAPPDATA',Path.home()/'AppData/Local'))
    key=hashlib.sha256(os.path.normcase(str(Path(root).resolve())).encode('utf8')).hexdigest()[:32]
    return base/'梦江湖装备编辑器/配置缓存'/REVISION/key

def cache_path(root,kind):
    if kind not in KINDS:raise ValueError('缓存类别无效')
    return cache_directory(root)/(kind+'.cache')

def _default(value,root=None):
    if isinstance(value,Path):
        if root is not None and (not value.is_absolute() or not value.is_relative_to(root)):raise ValueError('缓存配置路径越界')
        return msgpack.ExtType(1,str(value).encode('utf8'))
    if isinstance(value,tuple):return msgpack.ExtType(2,_pack(list(value),root))
    if isinstance(value,set):return msgpack.ExtType(3,_pack(list(value),root))
    raise TypeError('不能缓存此对象：'+type(value).__name__)

def _pack(value,root=None):return msgpack.packb(value,default=lambda v:_default(v,root),use_bin_type=True,strict_types=True)

def _extension(code,data,root=None,paths=None):
    if code==1:
        text=data.decode('utf8')
        if paths is not None and text in paths:return paths[text]
        value=Path(text)
        if root is not None and (not value.is_absolute() or not value.is_relative_to(root)):raise ValueError('缓存配置路径越界')
        if paths is not None:paths[text]=value
        return value
    if code==2:return tuple(_unpack(data,root,paths))
    if code==3:return set(_unpack(data,root,paths))
    raise ValueError('缓存包含未知数据类型')

def _unpack(data,root=None,paths=None):
    if paths is None:paths={}
    return msgpack.unpackb(data,raw=False,strict_map_key=False,ext_hook=lambda c,d:_extension(c,d,root,paths))

def _check_paths(value,root):
    if isinstance(value,Path):
        if not value.is_absolute() or not value.is_relative_to(root):raise ValueError('缓存配置路径越界')
    elif isinstance(value,dict):
        for k,v in value.items():_check_paths(k,root);_check_paths(v,root)
    elif isinstance(value,(list,tuple,set)):
        for v in value:_check_paths(v,root)

def _class(kind):
    if kind=='catalog':
        from engine import Catalog
        return Catalog
    if kind=='martial':
        from martial_editor import MartialLibrary
        return MartialLibrary
    from role_editor import RoleLibrary
    return RoleLibrary

def write_snapshot(lib,kind):
    if kind!='catalog' and lib.modified():raise ValueError('不缓存未保存草稿')
    state={k:v for k,v in vars(lib).items() if k not in ('assets','places','_mobile_texture_uploads') and not k.startswith('cache_')}
    root=lib.root.resolve()
    created=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    packed=_pack({'revision':REVISION,'kind':kind,'root':str(root),'created':created,'state':state,
                  'signature':catalog_signature(root) if kind=='catalog' else None},root)
    if len(packed)>MAX_BYTES:raise ValueError('配置缓存超过大小上限')
    compressed=zlib.compress(packed,1)
    blob=MAGIC+hashlib.sha256(compressed).digest()+compressed
    path=cache_path(root,kind);path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent,prefix='.'+kind,suffix='.tmp',delete=False) as f:
        temporary=Path(f.name)
        try:f.write(blob);f.flush();os.fsync(f.fileno())
        except Exception:temporary.unlink(missing_ok=True);raise
    try:os.replace(temporary,path)
    finally:temporary.unlink(missing_ok=True)
    return created

def read_snapshot(root,kind):
    root=Path(root).resolve();path=cache_path(root,kind)
    if path.stat().st_size>MAX_BYTES:raise ValueError('缓存文件超限')
    blob=path.read_bytes()
    if not blob.startswith(MAGIC) or len(blob)<len(MAGIC)+32:raise ValueError('缓存格式失效')
    checksum=blob[len(MAGIC):len(MAGIC)+32];compressed=blob[len(MAGIC)+32:]
    if hashlib.sha256(compressed).digest()!=checksum:raise ValueError('缓存文件损坏')
    decoder=zlib.decompressobj();packed=decoder.decompress(compressed,MAX_BYTES+1)
    if len(packed)>MAX_BYTES or not decoder.eof or decoder.unused_data:raise ValueError('缓存压缩数据无效')
    # Validate paths while decoding their extension records, rather than
    # revisiting millions of ordinary scalar fields after decoding.
    obj=_unpack(packed,root)
    if obj.get('revision')!=REVISION or obj.get('kind')!=kind or obj.get('root')!=str(root):raise ValueError('缓存版本或目录不匹配')
    state=obj['state']
    cls=_class(kind)
    if any(callable(getattr(cls,k,None)) for k in state):raise ValueError('缓存属性无效')
    if state.get('root')!=root:raise ValueError('缓存配置不完整')
    if kind=='catalog':
        if obj.get('signature')!=catalog_signature(root):raise ValueError('装备配置已变化')
        if not isinstance(state.get('snapshots'),dict) or not isinstance(state.get('items'),dict):raise ValueError('缓存配置不完整')
    elif not isinstance(state.get('originals'),dict) or not isinstance(state.get('tables'),dict):raise ValueError('缓存配置不完整')
    lib=cls.__new__(cls);lib.__dict__.update(state)
    if kind!='catalog':
        from client_config import Assets
        lib.assets=Assets(lib.originals[lib.assets_path])
    if kind=='role':
        from role_locations import RoleLocations
        lib.places=RoleLocations(lib)
    if kind!='catalog' and lib.modified():raise ValueError('缓存包含未保存草稿')
    lib.cache_source='local';lib.cache_created=obj['created'];lib.cache_warning=''
    return lib

def catalog_signature(root):
    """Revalidate every source used by Catalog; save files are always read live."""
    paths={root/'DreamRivakes.exe',root/'DreamRivakes_Data/resources.assets'}
    from shadow_runtime import PLUGIN,FLAGS,RECEIPT
    paths.update(root/name for name in (PLUGIN,FLAGS,RECEIPT))
    for folder,pattern in [('TableData','*.bytes'),('DreamRivakes_Data/Plugins','*.dll'),('ModProject/GameProject/Mod_MJH/Json','*.json')]:
        paths.update((root/folder).glob(pattern))
    return [(str(p.relative_to(root)),p.stat().st_size,p.stat().st_mtime_ns) if p.exists() else (str(p.relative_to(root)),None,None) for p in sorted(paths)]

def load_catalog(root):
    return load_library(root,'catalog')

def load_library(root,kind,force_refresh=False):
    root=Path(root).resolve();warning=''
    from shadow_runtime import ensure
    shadow_status=ensure(root) if kind=='catalog' else ''
    if not force_refresh:
        try:
            cached=read_snapshot(root,kind)
            if kind=='catalog':
                cached.shadow_status=shadow_status
                cached.validate_runtime()
            return cached
        except FileNotFoundError:pass
        except (OSError,ValueError,TypeError,KeyError,AttributeError,OverflowError,RecursionError) as error:
            warning='本地缓存异常，已重新读取配置：'+str(error)
    lib=_class(kind)(root)
    if kind=='catalog' and shadow_status:lib.shadow_status=shadow_status
    lib.cache_source='fresh';lib.cache_warning=warning
    try:lib.cache_created=write_snapshot(lib,kind)
    except (OSError,ValueError,TypeError,OverflowError) as error:
        lib.cache_created='';lib.cache_warning='配置已读取，本地缓存未写入：'+str(error)
    return lib

def note(lib):
    text=('已使用本地缓存' if lib.cache_source=='local' else
          '已完整读取配置并更新缓存' if lib.cache_created else '已完整读取配置')
    if lib.cache_created:text+=' · '+lib.cache_created
    return text+'。外部修改后请点刷新缓存。'+(' '+lib.cache_warning if lib.cache_warning else '')

def invalidate(root,payloads):
    root=Path(root).resolve()
    relevant=any(Path(p).suffix in ('.bytes','.json') or Path(p).name=='resources.assets' for p in payloads)
    if not relevant:return
    for kind in KINDS:
        try:cache_path(root,kind).unlink(missing_ok=True)
        except OSError:pass # Saving the game succeeded; cache errors cannot undo it.
