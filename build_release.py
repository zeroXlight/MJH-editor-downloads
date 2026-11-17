"""Build the Windows installer and the matching public GitHub Release assets."""
import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parent
SRC = ROOT / 'src'
OUT = ROOT / 'release-assets'
PUBLIC_KEY = SRC / 'update_public_key.py'
DEFAULT_KEY = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'MJH-editor-release' / 'ed25519.key'
SKIP = {'node_modules', '__pycache__', '.git', '.venv', '.tools'}


def load_key(path, initialize=False):
    if initialize and not path.exists():
        if PUBLIC_KEY.exists():
            raise ValueError('源码已有公钥。请提供原签名私钥，或在独立的开发副本中初始化新密钥。')
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(Ed25519PrivateKey.generate().private_bytes_raw())
    key = Ed25519PrivateKey.from_private_bytes(path.read_bytes())
    public_text = f"UPDATE_PUBLIC_KEY = '{key.public_key().public_bytes_raw().hex()}'\n"
    if PUBLIC_KEY.exists() and PUBLIC_KEY.read_text(encoding='utf-8') != public_text:
        raise ValueError('提供的私钥与编辑器内置公钥不匹配。')
    if initialize:
        PUBLIC_KEY.write_text(public_text, encoding='utf-8')
    return key


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def files(root):
    for directory, subdirs, names in os.walk(root):
        subdirs[:] = sorted(name for name in subdirs if name not in SKIP)
        for name in sorted(names):
            if not name.startswith('.') and not name.endswith(('.pyc', '.pyo', '.log')):
                path = Path(directory) / name
                if path.is_symlink():
                    raise ValueError(f'发布文件必须为常规文件：{path.relative_to(root)}')
                yield path


def pack(output, entries, marker=None):
    size = 0
    with ZipFile(output, 'w', compression=ZIP_DEFLATED, compresslevel=3) as archive:
        for path, name in entries:
            size += path.stat().st_size
            archive.write(path, name)
        if marker:
            name, contents = marker
            size += len(contents)
            archive.writestr(name, contents)
    with ZipFile(output) as archive:
        failed = archive.testzip()
        if failed:
            raise ValueError(f'压缩包 CRC 校验失败：{failed}')
    return size


def complete_catalog(value, root):
    if isinstance(value, list):
        for item in value:
            complete_catalog(item, root)
    elif isinstance(value, dict):
        if isinstance(value.get('file'), str) and isinstance(value.get('sha256'), str):
            path = (root / value['file']).resolve()
            if not path.is_relative_to(root) or digest(path) != value['sha256'].lower():
                raise ValueError(f"手游资源清单校验失败：{value['file']}")
        for item in value.values():
            complete_catalog(item, root)


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument('--key', type=Path, default=DEFAULT_KEY)
    parser.add_argument('--init-key', action='store_true', help='Initialize the signing key for a new release channel')
    parser.add_argument('--mobile-assets', type=Path)
    parser.add_argument('--iscc', type=Path)
    parser.add_argument('--chinese-language', type=Path)
    parser.add_argument('--previous-release', type=Path, action='append', default=[],
                        help='Directory containing a previous signed update.json and MJH-editor-Setup.exe')
    parser.add_argument('--skip-app-build', action='store_true', help='Reuse the app binary already built for this source version')
    args = parser.parse_args()
    key = load_key(args.key, args.init_key)
    if args.init_key:
        print('更新签名公钥已准备。签名私钥保存在指定的本地路径。')
        return
    if not all((args.mobile_assets, args.iscc, args.chinese_language)):
        parser.error('building a release requires --mobile-assets, --iscc and --chinese-language')

    sys.path.insert(0, str(SRC))
    from edition import VERSION
    from editor_update import (MOBILE_NAME, RELEASES, SETUP_NAME, SOURCE_NAME, asset_url,
                               delta_name, manifest_payload, verify_installer, verify_manifest, version_tuple)
    version = VERSION.removeprefix('V')
    OUT.mkdir(exist_ok=True)
    if not args.skip_app_build:
        subprocess.run(
            [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--distpath', str(OUT / 'build'), '--workpath', str(OUT / 'work'), 'desktop.spec'],
            check=True, cwd=SRC,
        )
        subprocess.run(
            [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--onefile', '--windowed',
             '--icon', str(SRC / 'app.ico'), '--name', 'MJH-editor-Update', '--distpath', str(OUT / 'build'),
             '--workpath', str(OUT / 'work'), '--specpath', str(OUT / 'work'), 'update_launcher.py'],
            check=True, cwd=SRC,
        )
    mobile = args.mobile_assets.resolve()
    catalog = json.loads((mobile / 'catalog.json').read_text(encoding='utf-8-sig'))
    if not catalog['models'] or any(not (mobile / part).is_dir() for part in ('models', 'heads', 'portraits')):
        raise ValueError('手游资源目录不完整。')
    complete_catalog(catalog, mobile)
    mobile_paths = list(files(mobile))
    mobile_identity = hashlib.sha256()
    for path in mobile_paths:
        mobile_identity.update((path.relative_to(mobile).as_posix() + '\0' + digest(path) + '\n').encode('utf-8'))
    resource_version = mobile_identity.hexdigest()
    mobile_zip = OUT / MOBILE_NAME
    if mobile_zip.is_file():
        with ZipFile(mobile_zip) as previous:
            if previous.read('mobile_assets/.mjh-resource-version').decode('ascii') != resource_version:
                raise ValueError('当前输出目录已有另一版手游资源包，请使用新的构建目录。')
    else:
        pack(mobile_zip, ((path, 'mobile_assets/' + path.relative_to(mobile).as_posix()) for path in mobile_paths),
             ('mobile_assets/.mjh-resource-version', resource_version.encode('ascii')))
    with ZipFile(mobile_zip) as archive:
        mobile_size = sum(item.file_size for item in archive.infolist())

    top = [ROOT / name for name in ('installer.iss', 'build_release.py', 'publish_release.py',
                                   'README.md', 'RELEASING.md', '.gitignore', '升级使用说明.txt')]
    source_zip = OUT / SOURCE_NAME
    source_size = pack(source_zip, ((path, path.relative_to(ROOT).as_posix()) for path in (*top, *files(SRC))))
    config = {
        'BuildVersion': version, 'ReleasesURL': RELEASES, 'ChineseLanguage': str(args.chinese_language.resolve()),
        'MobileURL': asset_url(version, MOBILE_NAME), 'MobileHash': digest(mobile_zip),
        'MobileVersion': resource_version, 'MobileSize': mobile_size,
        'SourceURL': asset_url(version, SOURCE_NAME), 'SourceHash': digest(source_zip), 'SourceSize': source_size,
    }
    (OUT / 'installer-config.iss').write_text(
        ''.join(f'#define {name} "{value}"\n' if isinstance(value, str) else f'#define {name} {value}\n'
                for name, value in config.items()), encoding='utf-8-sig',
    )
    subprocess.run([str(args.iscc.resolve()), '/Qp', str(ROOT / 'installer.iss')], check=True, cwd=ROOT)
    setup = OUT / SETUP_NAME
    release = {'schema': 1, 'version': version, 'size': setup.stat().st_size, 'sha256': digest(setup)}
    deltas = {}
    for previous in args.previous_release:
        import bsdiff4
        old = verify_manifest((previous / 'update.json').read_bytes())
        if version_tuple(old['version']) >= version_tuple(version):
            raise ValueError('差分基线必须早于当前版本。')
        base_setup = previous / SETUP_NAME
        verify_installer(base_setup, old)
        patch = OUT / delta_name(old['version'])
        bsdiff4.file_diff(str(base_setup), str(setup), str(patch))
        if patch.stat().st_size >= release['size'] * 0.8:
            patch.unlink()
            continue
        deltas[old['sha256']] = {
            'base_version': old['version'], 'size': patch.stat().st_size, 'sha256': digest(patch),
        }
    if deltas:
        release['deltas'] = deltas
    manifest = {'release': release, 'signature': base64.b64encode(key.sign(manifest_payload(release))).decode('ascii')}
    manifest_path = OUT / 'update.json'
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    verify_manifest(manifest_path.read_bytes())
    print(f'v{version} release assets ready:')
    for path in (setup, mobile_zip, source_zip, manifest_path):
        print(path.name, path.stat().st_size, digest(path))
    for patch in deltas.values():
        print(delta_name(patch['base_version']), patch['size'], patch['sha256'])


if __name__ == '__main__':
    run()
