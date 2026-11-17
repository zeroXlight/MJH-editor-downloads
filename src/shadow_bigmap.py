"""Read-only certification of Shadow v0.47d on the certified big-map build.

The supplied strict reverser runs only on temporary bytes. Acceptance requires
the entire restored image to equal the known native SHA, not just its hooks.
No installer, game path or save file is passed to that reverser.
"""
from pathlib import Path
import hashlib, json, subprocess, tempfile, zipfile

RACE_SHA='b029d553b2effba3b84868cf9e088d43f22bae825a0f51c0d04539698751ed1f'
CLIENT_SHA='a751183a3ec31af2fded561c0cb4a1ab56739d5197de575ac61dce016748099b'
RESOURCE_SHA='c42922e376832949a6197eba8f2f6b6dea34802eaa89c3c69d093954b2ca5f27'
_cache={}
_client_repair_cache={}

def sha(raw):return hashlib.sha256(raw).hexdigest()

def plugin_known(root):
    files={'BepInEx/plugins/XiakeConsultFix.dll':'75dfeac9a3d9a5c1d0d4da3d34ab2ebf2f9a5f57d706802063ccb0392cd14a4b',
           'BepInEx/plugins/XiakeConsultFix/consult_hook.lua':'5796be610c4136f498b1faf602d60b52cb794a96bea9fd355669b476694d26da'}
    try:return all(sha((Path(root)/name).read_bytes())==value for name,value in files.items())
    except OSError:return False

def resource():
    from engine import DATA_ROOT
    path=DATA_ROOT/'shadow_bigmap_v047d.zip'
    if sha(path.read_bytes())!=RESOURCE_SHA:raise ValueError('暗影大地图认证资源被修改，未写入文件')
    return path

def race_parent(raw):
    digest=sha(raw)
    if digest==RACE_SHA:return True
    if digest in _cache:return _cache[digest]
    import pefile
    try:
        pe=pefile.PE(data=raw,fast_load=True)
        names=[s.Name.rstrip(b'\0') for s in pe.sections]
        allowed={b'.text',b'.rdata',b'.data',b'.pdata',b'.tls',b'.rsrc',b'.reloc',b'.dyout',b'.dyfrag',b'.dycap',b'.dyswp',b'.dyadv'}
        rd=next(s for s in pe.sections if s.Name.rstrip(b'\0')==b'.rdata')
        if pe.FILE_HEADER.Machine!=0x8664 or pe.OPTIONAL_HEADER.Magic!=0x20b or len(names)!=len(set(names)) or set(names)-allowed or rd.VirtualAddress!=0xf72000 or rd.PointerToRawData!=0xf70a00:
            return False
        with tempfile.TemporaryDirectory(prefix='mjh_shadow_cert_') as folder:
            root=Path(folder);src=root/'input.dll';out=root/'original.dll';src.write_bytes(raw)
            with zipfile.ZipFile(resource()) as z:
                for name in z.namelist():
                    if not (root/name).resolve().is_relative_to(root):raise ValueError('暗影认证资源路径无效')
                z.extractall(root)
            script=root/'certify.ps1'
            script.write_text("""$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'patch_classic_bundle.ps1')
[byte[]]$raw=[IO.File]::ReadAllBytes((Join-Path $PSScriptRoot 'input.dll'))
$result=Update-ClassicNativeBundleStrict $raw @{} $PSScriptRoot @() @()
[IO.File]::WriteAllBytes((Join-Path $PSScriptRoot 'original.dll'),[byte[]]$result.Original)
""",'utf-8-sig')
            result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(script)],capture_output=True,timeout=55,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            valid=result.returncode==0 and out.is_file() and sha(out.read_bytes())==RACE_SHA
    except (ValueError,OSError,StopIteration,subprocess.TimeoutExpired,pefile.PEFormatError):valid=False
    if len(_cache)>64:_cache.clear()
    _cache[digest]=valid
    return valid

def client_parent(raw):
    if sha(raw)==CLIENT_SHA:return True
    # The only client modification made by this MOD is a complete 151-byte
    # Martial JSON upsert fix; prove the rest of the entire native image too.
    import pefile
    try:
        pe=pefile.PE(data=raw,fast_load=True)
        if any(s.Name.rstrip(b'\0').startswith(b'.mjh') for s in pe.sections):return False
        with zipfile.ZipFile(resource()) as z:
            prefix='profiles/classic_26315803/'
            cfg=json.loads(z.read(prefix+'martial_json_upsert_layout.json'))
            original=bytes.fromhex(z.read(prefix+'martial_json_upsert_original.hex').decode().strip())
        off=cfg['offset'];size=cfg['size']
        if len(original)!=size or sha(original)!=cfg['original'] or sha(raw[off:off+size])!=cfg['patched']:return False
        for g in cfg['guards']:
            if sha(raw[g['offset']:g['offset']+g['size']])!=g['sha256']:return False
        return sha(raw[:off]+original+raw[off+size:])==CLIENT_SHA
    except (OSError,KeyError,ValueError,pefile.PEFormatError):return False

def repair_legacy_client(raw):
    """Rebase an exact editor pet image after Shadow changed only JSON upsert.

    Reverse the known 151 bytes, then validate/rebuild the entire old pet image
    with its original parent digest. No unchecked parent hash is accepted.
    """
    digest=sha(raw)
    if digest in _client_repair_cache:return _client_repair_cache[digest]
    import pefile
    pe=pefile.PE(data=raw,fast_load=True)
    if not pe.sections or pe.sections[-1].Name.rstrip(b'\0')!=b'.mjhpet':return raw
    with zipfile.ZipFile(resource()) as z:
        prefix='profiles/classic_26315803/'
        cfg=json.loads(z.read(prefix+'martial_json_upsert_layout.json'))
        original_code=bytes.fromhex(z.read(prefix+'martial_json_upsert_original.hex').decode().strip())
    at=cfg['offset'];size=cfg['size'];code=raw[at:at+size]
    if sha(code)!=cfg['patched']:return raw
    from bigmap_martial_limit_enhance import normalize_client,patch_client
    from bigmap_pet_runtime import original,_build
    reversed_image=raw[:at]+original_code+raw[at+size:]
    normalized,limit=normalize_client(reversed_image)
    try:parent=original(normalized)
    except ValueError:return raw
    if sha(parent)!=CLIENT_SHA:return raw
    changed_parent=parent[:at]+code+parent[at+size:]
    if not client_parent(changed_parent):return raw
    fixed=_build(changed_parent)
    if limit:fixed=patch_client(fixed,True)
    if len(_client_repair_cache)>8:_client_repair_cache.clear()
    _client_repair_cache[digest]=fixed
    return fixed
