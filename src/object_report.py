"""Small, readable dependency diagnostics outside message boxes."""
import os,tempfile
from pathlib import Path

def write_report(path,report):
    path=Path(path)
    lines=['完整配置包依赖检查（V2.0.32）',
           '必需依赖缺失：'+str(sum(r['required'] for r in report)),
           '显示文本提醒：'+str(sum(not r['required'] for r in report)),'']
    for row in report:
        lines.append(('错误' if row['required'] else '文本提醒')+'：'+row['target']+' — '+row['reason'])
        for ref in row['references']:
            lines.append('  引用来源：'+ref['source']+' / '+'.'.join(map(str,ref['path'])))
        lines.append('')
    fd,temp=tempfile.mkstemp(prefix='.mjh_report_',dir=path.parent);os.close(fd)
    try:
        Path(temp).write_text('\n'.join(lines),encoding='utf8');os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)
    return path
