"""Bounded, automatically cleaned staging space for complete configuration imports."""
import shutil,sys,tempfile
from pathlib import Path
from contextlib import contextmanager

@contextmanager
def workspace_temp(root,prefix):
    root=Path(root).resolve();asset=root/'DreamRivakes_Data/resources.assets'
    required=max(256*1024**2,(asset.stat().st_size if asset.exists() else 0)*3+256*1024**2)
    candidates=[Path(tempfile.gettempdir()).resolve(),root.parent,Path(sys.executable).resolve().parent]
    seen=set();directory=None
    for base in candidates:
        if base in seen:continue
        seen.add(base)
        try:
            if not base.is_dir() or shutil.disk_usage(base).free<required:continue
            directory=tempfile.TemporaryDirectory(prefix=prefix,dir=base)
            break
        except OSError:continue
    if directory is None:raise ValueError(f'导入临时空间不足或目录不可写，需要约 {required/1024**3:.1f} GB 可用空间。请释放系统临时盘或游戏所在盘的空间后重试。')
    with directory as folder:yield folder
