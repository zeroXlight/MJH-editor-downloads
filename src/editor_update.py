"""Check the public release channel and install verified updates after exit."""
import base64
import binascii
import configparser
import ctypes
import hashlib
import http.client
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import webbrowser
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from edition import APP_DIR, VERSION
from update_public_key import UPDATE_PUBLIC_KEY

RELEASES = 'https://github.com/zeroXlight/MJH-editor-downloads/releases'
MANIFEST = RELEASES + '/latest/download/update.json'
SETUP_NAME = 'MJH-editor-Setup.exe'
SOURCE_NAME = 'MJH-editor-Source.zip'
MOBILE_NAME = 'MJH-editor-MobileAssets.zip'
APP_MUTEX = 'MJH-editor-Desktop-v2'
MODES = ('notify', 'auto')
MAX_SETUP = 512 * 1024 * 1024


def version_tuple(version):
    if not isinstance(version, str) or not re.fullmatch(r'(?:0|[1-9][0-9]{0,3})(?:\.(?:0|[1-9][0-9]{0,3})){2}', version):
        raise ValueError('版本号格式错误。')
    return tuple(map(int, version.split('.')))


def asset_url(version, name):
    version_tuple(version)
    return f'{RELEASES}/download/v{version}/{name}'


def manifest_payload(manifest):
    return json.dumps(manifest, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')


def verify_manifest(raw, public_key=UPDATE_PUBLIC_KEY):
    try:
        envelope = json.loads(raw)
        data = envelope['release']
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key)).verify(
            base64.b64decode(envelope['signature'], validate=True), manifest_payload(data)
        )
        if not isinstance(data, dict) or data.get('schema') != 1:
            raise ValueError('Unsupported schema')
        version_tuple(data['version'])
        if type(data['size']) is not int or not 0 < data['size'] <= MAX_SETUP:
            raise ValueError('Invalid installer size')
        if not isinstance(data['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', data['sha256']):
            raise ValueError('Invalid installer digest')
    except (KeyError, TypeError, ValueError, binascii.Error, InvalidSignature) as exc:
        raise ValueError('更新清单签名或格式无效。') from exc
    return data


class GitHubRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urlsplit(newurl)
        if parsed.scheme != 'https' or parsed.hostname not in ('github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com'):
            raise ValueError('更新下载地址无效。')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def open_release(url):
    opener = build_opener(GitHubRedirects())
    return opener.open(Request(url, headers={'User-Agent': 'MJH-editor/' + VERSION}), timeout=20)


def verify_installer(path, release):
    if path.stat().st_size != release['size']:
        raise ValueError('安装包大小校验失败。')
    with path.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != release['sha256']:
            raise ValueError('安装包 SHA-256 校验失败。')


def installed_version(directory):
    try:
        config = configparser.ConfigParser()
        config.read(directory / 'installation.ini', encoding='utf-8-sig')
        if config.get('MJH-editor', 'managed', fallback='') == '1':
            version = config.get('MJH-editor', 'version')
            version_tuple(version)
            return version
    except (OSError, ValueError, configparser.Error):
        pass
    return None


def delta_name(base_version):
    version_tuple(base_version)
    return f'MJH-editor-From-{base_version}.bsdiff'


def matching_delta(base, release):
    if not base.is_file():
        return None
    with base.open('rb') as stream:
        sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    deltas = release.get('deltas')
    patch = deltas.get(sha) if isinstance(deltas, dict) else None
    if not isinstance(patch, dict):
        return None
    if type(patch.get('size')) is not int or not 0 < patch['size'] < release['size']:
        return None
    if not isinstance(patch.get('sha256'), str) or not re.fullmatch('[a-f0-9]{64}', patch['sha256']):
        return None
    try:
        delta_name(patch.get('base_version'))
    except ValueError:
        return None
    return patch


class DownloadCancelled(Exception):
    pass


def download_asset(url, path, expected, report, transfer):
    total = expected['size']
    received = 0
    report(received, total, transfer)
    with open_release(url) as response, path.open('wb') as stream:
        while chunk := response.read(256 * 1024):
            received += len(chunk)
            if received > total:
                raise ValueError('下载文件超过预期大小。')
            report(received, total, transfer)
            stream.write(chunk)
    verify_installer(path, expected)


def stage_installer(folder, base, release, report):
    """Reuse a verified download or reconstruct the signed installer from a smaller patch."""
    folder.mkdir(parents=True, exist_ok=True)
    output = folder / f"{release['version']}-{release['sha256']}.exe"
    if output.is_file():
        try:
            verify_installer(output, release)
            report(release['size'], release['size'], 'cached')
            return output
        except (OSError, ValueError):
            pass

    with tempfile.TemporaryDirectory(dir=folder) as temp:
        setup = Path(temp) / SETUP_NAME
        try:
            delta = matching_delta(base, release)
            if delta:
                import bsdiff4
                patch = Path(temp) / 'update.bsdiff'
                download_asset(asset_url(release['version'], delta_name(delta['base_version'])), patch, delta, report, 'delta')
                report(delta['size'], delta['size'], 'patching')
                bsdiff4.file_patch(str(base), str(setup), str(patch))
                verify_installer(setup, release)
                setup.replace(output)
                return output
        except (OSError, ValueError, EOFError, http.client.HTTPException, MemoryError):
            report(0, release['size'], 'fallback')
        download_asset(asset_url(release['version'], SETUP_NAME), setup, release, report, 'full')
        setup.replace(output)
        return output


class EditorUpdate:
    def __init__(self, repair=False):
        self.settings = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'MengJiangHuEquipEditor' / 'update.json'
        self.directory = APP_DIR
        self.repair = repair
        installed = installed_version(self.directory)
        self.current = installed if repair and installed else VERSION.removeprefix('V')
        self.managed = bool(getattr(sys, 'frozen', False) and installed)
        self.lock = threading.RLock()
        self.mode = 'notify'
        try:
            saved = json.loads(self.settings.read_text(encoding='utf-8')).get('mode')
            if not repair and saved in MODES:
                self.mode = saved
        except (AttributeError, OSError, ValueError):
            pass
        self.status = 'idle'
        self.message = ''
        self.release = None
        self.cached = None
        self.pending = False
        self.epoch = 0
        self.received = 0
        self.total = 0
        self.transfer = ''

    def snapshot(self):
        with self.lock:
            return {
                'mode': self.mode, 'status': self.status, 'message': self.message,
                'current': self.current, 'latest': self.release['version'] if self.release else None,
                'managed': self.managed, 'pending': self.pending,
                'received': self.received, 'total': self.total, 'transfer': self.transfer,
            }

    def change_mode(self, mode):
        if mode not in MODES:
            raise ValueError('未知更新方式。')
        with self.lock:
            self.settings.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=self.settings.parent, delete=False) as stream:
                path = Path(stream.name)
                stream.write(json.dumps({'mode': mode}).encode('utf-8'))
            try:
                path.replace(self.settings)
            finally:
                path.unlink(missing_ok=True)
            self.mode = mode
            if mode != 'auto':
                self.pending = False
                self.epoch += 1
                if self.status == 'ready':
                    self.status = 'available'
            elif self.cached:
                self.pending = True
                self.status = 'ready'
            elif self.release and self.status == 'available' and self.managed:
                self.download()

    def check(self):
        with self.lock:
            if self.pending or self.status in ('checking', 'downloading'):
                return
            self.status = 'checking'
            self.message = ''
            threading.Thread(target=self._check, daemon=True).start()

    def _check(self):
        try:
            with open_release(MANIFEST) as response:
                raw = response.read(16385)
            if len(raw) > 16384:
                raise ValueError('更新清单超出大小限制。')
            release = verify_manifest(raw)
            with self.lock:
                if release != self.release:
                    self.cached = None
                newest = version_tuple(release['version'])
                installed = version_tuple(self.current)
                if newest < installed or (newest == installed and not self.repair):
                    self.status = 'current'
                    self.release = None
                    return
                self.release = release
                self.status = 'available'
                if self.mode == 'auto' and self.managed:
                    self.download()
        except (OSError, ValueError, http.client.HTTPException) as exc:
            with self.lock:
                self.status = 'error'
                self.message = str(exc) if isinstance(exc, ValueError) else '暂时无法检查更新。'

    def download(self):
        with self.lock:
            if not self.release or self.status in ('checking', 'downloading'):
                return
            if not self.managed:
                webbrowser.open(f"{RELEASES}/tag/v{self.release['version']}")
                return
            if self.cached:
                self.status = 'ready'
                self.pending = True
                return
            self.status = 'downloading'
            self.message = ''
            self.received = self.total = 0
            self.transfer = ''
            threading.Thread(target=self._download, args=(self.release, self.epoch), daemon=True).start()

    def _download(self, release, epoch):
        def report(received, total, transfer):
            with self.lock:
                if self.epoch != epoch:
                    raise DownloadCancelled()
                self.received, self.total, self.transfer = received, total, transfer
                if transfer == 'fallback':
                    self.message = '差分更新未能完成，正在下载完整安装包。'

        try:
            folder = self.settings.parent / 'updates'
            base = self.directory / '.update' / 'installed-setup.exe'
            path = stage_installer(folder, base, release, report)
            with self.lock:
                self.cached = path
                self.status = 'ready' if self.epoch == epoch else 'available'
                self.pending = self.epoch == epoch
                self.message = ''
        except DownloadCancelled:
            with self.lock:
                self.status = 'available'
                self.message = '已取消本次下载。'
        except (OSError, ValueError, http.client.HTTPException) as exc:
            with self.lock:
                self.status = 'available'
                self.message = str(exc) if isinstance(exc, ValueError) else '暂时无法下载更新，请稍后重试。'

    def cancel(self):
        with self.lock:
            self.pending = False
            self.epoch += 1
            if self.status == 'ready':
                self.status = 'available'

    def open_current(self, source=False):
        webbrowser.open(asset_url(self.current, SOURCE_NAME) if source else f'{RELEASES}/tag/v{self.current}')

    def after_close(self):
        with self.lock:
            if not (self.pending and self.cached and self.managed and installed_version(self.directory)):
                return False
            try:
                verify_installer(self.cached, self.release)
                args = [str(self.cached), f'/DIR={self.directory}', f'/WAITPID={os.getppid()}',
                        '/SILENT', '/NORESTART', '/NOCLOSEAPPLICATIONS', '/NORESTARTAPPLICATIONS']
                # Avoid passing PyInstaller's DLL-search override to a native child.
                ctypes.windll.kernel32.SetDllDirectoryW(None)
                subprocess.Popen(args, cwd=self.directory, close_fds=True)
                return True
            except (OSError, ValueError) as exc:
                self.settings.parent.mkdir(parents=True, exist_ok=True)
                (self.settings.parent / 'update-error.log').write_text(str(exc), encoding='utf-8')
                self.message = '无法启动安装器，请重试。'
                return False
