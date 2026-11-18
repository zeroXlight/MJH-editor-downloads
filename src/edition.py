"""Application version and optional resources found at startup."""
import json
import sys
from pathlib import Path

VERSION = 'V2.5.4'
APP_DIR = Path(sys.executable if getattr(sys, 'frozen', False) else __file__).resolve().parent
ASSET_DIR = APP_DIR / 'mobile_assets'


def find_mobile_assets():
    roots = [ASSET_DIR]
    if not getattr(sys, 'frozen', False):
        roots.append(APP_DIR.parent / 'mobile_assets')
    for root in roots:
        try:
            catalog = json.loads((root / 'catalog.json').read_text(encoding='utf-8-sig'))
            if catalog.get('models') and all((root / part).is_dir() for part in ('models', 'heads', 'portraits')):
                return root
        except (OSError, ValueError, AttributeError):
            continue
    return None


MOBILE_ASSETS = find_mobile_assets()
MOBILE_ENABLED = MOBILE_ASSETS is not None
EDITION_NAME = '已安装手游资源' if MOBILE_ENABLED else '标准版'
DISPLAY_VERSION = VERSION + ' · ' + EDITION_NAME


def require_mobile():
    if not MOBILE_ENABLED:
        raise ValueError('请运行安装器添加手游模型与立绘，再重启编辑器。')
