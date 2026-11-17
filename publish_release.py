"""Publish a committed source snapshot and its verified assets to one explicit GitHub branch."""
import argparse
import ast
import json
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parent


def run(*command):
    return subprocess.check_output(command, cwd=ROOT, text=True, encoding='utf-8').strip()


def version():
    module = ast.parse((ROOT / 'src' / 'edition.py').read_text(encoding='utf-8'))
    for node in module.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'VERSION' for t in node.targets):
            return ast.literal_eval(node.value).removeprefix('V')
    raise ValueError('缺少 VERSION。')


def verify_source(archive):
    tracked = set(run('git', '-c', 'core.quotepath=false', 'ls-files', '-z').strip('\0').split('\0'))
    with ZipFile(archive) as source:
        archived = {item.filename for item in source.infolist() if not item.is_dir()}
        if archived != tracked:
            raise ValueError(f'源码 ZIP 与 Git 跟踪清单不同。仅 Git 有 {sorted(tracked - archived)}，仅 ZIP 有 {sorted(archived - tracked)}')
        for name in sorted(tracked):
            if source.read(name) != (ROOT / name).read_bytes():
                raise ValueError('源码 ZIP 与待发布提交内容不同：' + name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repository', required=True, help='The explicitly authorized GitHub owner/repository')
    parser.add_argument('--branch', required=True, help='The explicitly authorized source branch')
    parser.add_argument('--notes-file', type=Path, required=True)
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    if len(args.repository.split('/')) != 2 or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._/' for c in args.repository):
        parser.error('repository must be owner/repository')
    if not args.notes_file.is_file():
        parser.error('notes-file does not exist')
    remote = run('git', 'remote', 'get-url', 'origin')
    accepted = {f'https://github.com/{args.repository}', f'https://github.com/{args.repository}.git',
                f'git@github.com:{args.repository}.git'}
    if remote not in accepted:
        raise ValueError('origin 与指定的发布仓库不同。')
    if run('git', 'branch', '--show-current') != args.branch:
        raise ValueError('当前分支与指定的发布分支不同。')
    if run('git', 'status', '--porcelain'):
        raise ValueError('先提交源码和文档，确保工作区干净，再执行发布。')
    sys.path.insert(0, str(ROOT / 'src'))
    from editor_update import (MOBILE_NAME, RELEASES, SETUP_NAME, SOURCE_NAME, delta_name,
                               verify_installer, verify_manifest, version_tuple)
    if RELEASES != f'https://github.com/{args.repository}/releases':
        raise ValueError('客户端的 RELEASES 与指定发布仓库不同。个人分支请先配置自己的更新渠道和签名公钥。')
    current = version()
    version_tuple(current)
    out = ROOT / 'release-assets'
    release = verify_manifest((out / 'update.json').read_bytes())
    if release['version'] != current:
        raise ValueError('更新清单版本号与源码不同。')
    verify_installer(out / SETUP_NAME, release)
    verify_source(out / SOURCE_NAME)
    paths = [out / name for name in (SETUP_NAME, MOBILE_NAME, SOURCE_NAME, 'update.json')]
    for delta in release.get('deltas', {}).values():
        path = out / delta_name(delta['base_version'])
        verify_installer(path, delta)
        paths.append(path)
    for path in paths:
        if not path.is_file():
            raise ValueError('缺少发布附件：' + path.name)
    config = {}
    for line in (out / 'installer-config.iss').read_text(encoding='utf-8-sig').splitlines():
        _, name, value = line.split(' ', 2)
        config[name] = value.strip('"')
    from build_release import digest
    if config['BuildVersion'] != current or config['MobileHash'] != digest(out / MOBILE_NAME) or config['SourceHash'] != digest(out / SOURCE_NAME):
        raise ValueError('安装器构建配置与本次附件不同。')
    commit = run('git', 'rev-parse', 'HEAD')
    tag = 'v' + current
    print(f'Verified {args.repository} {args.branch} {commit} {tag}', flush=True)
    if args.check_only:
        return
    run('gh', 'auth', 'status')
    # Push without force so concurrently published source cannot be overwritten.
    subprocess.run(['git', 'push', 'origin', f'HEAD:refs/heads/{args.branch}'], cwd=ROOT, check=True)
    existing = subprocess.run(['git', 'show-ref', '--verify', '--quiet', f'refs/tags/{tag}'], cwd=ROOT).returncode == 0
    if existing:
        if run('git', 'rev-list', '-n', '1', tag) != commit:
            raise ValueError('本地版本标签已指向其他提交。')
    else:
        subprocess.run(['git', 'tag', tag, commit], cwd=ROOT, check=True)
    subprocess.run(['git', 'push', 'origin', f'refs/tags/{tag}'], cwd=ROOT, check=True)
    lookup = subprocess.run(['gh', 'release', 'view', tag, '--repo', args.repository, '--json', 'isDraft,targetCommitish'],
                            cwd=ROOT, text=True, encoding='utf-8', capture_output=True)
    if lookup.returncode == 0:
        if not json.loads(lookup.stdout)['isDraft']:
            raise ValueError('该版本已发布。后续修正请创建新的版本号。')
    else:
        subprocess.run(['gh', 'release', 'create', tag, '--repo', args.repository, '--verify-tag', '--draft',
                        '--title', f'MJH-editor V{current}', '--notes-file', str(args.notes_file.resolve())],
                       cwd=ROOT, check=True)
    subprocess.run(['gh', 'release', 'upload', tag, '--repo', args.repository, '--clobber', *map(str, paths)],
                   cwd=ROOT, check=True)
    actual = json.loads(run('gh', 'api', f'repos/{args.repository}/releases/tags/{tag}'))['assets']
    actual = {asset['name']: asset for asset in actual}
    if set(actual) != {p.name for p in paths}:
        raise ValueError('草稿附件清单与本次构建不同。')
    for path in paths:
        item = actual[path.name]
        if item['size'] != path.stat().st_size or item.get('digest') != 'sha256:' + digest(path):
            raise ValueError('GitHub 附件校验失败：' + path.name)
    subprocess.run(['gh', 'release', 'edit', tag, '--repo', args.repository, '--draft=false', '--latest'],
                   cwd=ROOT, check=True)
    print(f'Published https://github.com/{args.repository}/releases/tag/{tag}')


if __name__ == '__main__':
    main()
