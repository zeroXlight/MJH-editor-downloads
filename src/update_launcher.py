"""Standalone update and repair window for an installed copy of MJH-editor."""
import tkinter as tk
import webbrowser
from tkinter import ttk

from editor_update import RELEASES, EditorUpdate


def main():
    updater = EditorUpdate(repair=True)
    root = tk.Tk()
    root.title('MJH-editor 更新与修复')
    root.minsize(460, 260)
    root.resizable(True, False)

    panel = ttk.Frame(root, padding=22)
    panel.pack(fill='both', expand=True)
    ttk.Label(panel, text='更新与修复', font=('Microsoft YaHei UI', 15)).pack(anchor='w')
    ttk.Label(panel, text=f'当前安装版本 V{updater.current}').pack(anchor='w', pady=(6, 0))
    ttk.Label(panel, text='请先关闭编辑器。如果编辑器无法启动，可直接在这里修复。', wraplength=410).pack(anchor='w', pady=(8, 14))
    status = ttk.Label(panel, wraplength=410)
    status.pack(anchor='w')
    progress = ttk.Progressbar(panel, mode='determinate', maximum=100)
    progress.pack(fill='x', pady=(8, 0))
    transfers = ttk.Label(panel)
    transfers.pack(anchor='w', pady=(4, 12))
    actions = ttk.Frame(panel)
    actions.pack(anchor='w')
    check = ttk.Button(actions, text='检查新版', command=updater.check)
    check.pack(side='left')
    install = ttk.Button(actions, text='下载并安装', command=updater.download)
    install.pack(side='left', padx=6)
    ttk.Button(actions, text='打开下载页', command=lambda: webbrowser.open(RELEASES + '/latest')).pack(side='left')

    def render():
        state = updater.snapshot()
        phase = state['status']
        target = state['latest']
        busy = phase in ('checking', 'downloading')
        mode = state['transfer']
        messages = {
            'idle': '准备检查版本。',
            'checking': '正在检查 GitHub 上的正式版本…',
            'current': '当前已安装比下载页更新的版本。',
            'available': f'可安装 V{target}。' if target else '可重试下载。',
            'downloading': '正在校验并重建安装包…' if mode == 'patching' else '正在下载更新…',
            'ready': '安装包已验证，正在启动安装…',
        }
        status['text'] = state['message'] or messages.get(phase, '暂时无法检查更新。')
        received, total = state['received'], state['total']
        progress['value'] = received * 100 / total if total else 0
        if total:
            kind = '差分包' if mode in ('delta', 'patching') else '安装包'
            transfers['text'] = f'{kind}  {received / 1048576:.1f} / {total / 1048576:.1f} MB'
        check['state'] = 'disabled' if busy or phase == 'ready' else 'normal'
        install['state'] = 'normal' if phase == 'available' and updater.managed else 'disabled'
        install['text'] = '修复当前版本' if target == updater.current else '下载并安装'
        if phase == 'ready' and state['pending']:
            if updater.after_close():
                root.destroy()
                return
            updater.cancel()
        root.after(120, render)

    if updater.managed:
        updater.check()
        render()
    else:
        status['text'] = '找不到安装记录。请从下载页运行完整安装包。'
        check.state(['disabled'])
        install.state(['disabled'])
    root.mainloop()


if __name__ == '__main__':
    main()
