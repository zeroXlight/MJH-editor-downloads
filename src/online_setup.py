"""Download the latest signed release and launch its interactive installer."""
import ctypes
import http.client
import os
import subprocess
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from queue import Empty, SimpleQueue
from tkinter import ttk

from editor_update import (
    RELEASES, DownloadCancelled, fetch_latest_release, stage_installer, verify_installer,
)


def main():
    root = tk.Tk()
    root.title('MJH-editor 联网安装')
    root.resizable(False, False)
    frame = ttk.Frame(root, padding=24)
    frame.pack(fill='both', expand=True)
    ttk.Label(frame, text='MJH-editor 联网安装', font=('Microsoft YaHei UI', 15)).pack(anchor='w')
    status = ttk.Label(frame, width=46, wraplength=375)
    status.pack(anchor='w', pady=(12, 8))
    progress = ttk.Progressbar(frame, mode='determinate', maximum=100)
    progress.pack(fill='x')
    size = ttk.Label(frame)
    size.pack(anchor='w', pady=(4, 12))
    buttons = ttk.Frame(frame)
    buttons.pack(anchor='w')

    events = SimpleQueue()
    closing = threading.Event()

    def download():
        def report(received, total, kind):
            if closing.is_set():
                raise DownloadCancelled()
            events.put(('progress', (received, total)))

        try:
            release = fetch_latest_release()
            events.put(('version', release['version']))
            base = Path(os.environ.get('LOCALAPPDATA', str(Path.home())))
            path = stage_installer(base / 'MengJiangHuEquipEditor' / 'updates', None, release, report)
            verify_installer(path, release)
            events.put(('ready', path))
        except DownloadCancelled:
            pass
        except ValueError as exc:
            events.put(('error', str(exc)))
        except (OSError, http.client.HTTPException):
            events.put(('error', '暂时无法从 GitHub 下载，请重试或打开发布页。'))

    def start():
        retry.state(['disabled'])
        status['text'] = '正在检查 GitHub 上的最新正式版…'
        size['text'] = ''
        progress['value'] = 0
        # Let the worker clean up a partial download if the window is closed.
        threading.Thread(target=download).start()

    def close():
        closing.set()
        root.destroy()

    retry = ttk.Button(buttons, text='重试', command=start)
    retry.pack(side='left')
    ttk.Button(buttons, text='打开发布页', command=lambda: webbrowser.open(RELEASES + '/latest')).pack(side='left', padx=8)
    ttk.Button(buttons, text='取消', command=close).pack(side='left')
    root.protocol('WM_DELETE_WINDOW', close)

    def render():
        while True:
            try:
                event, data = events.get_nowait()
            except Empty:
                break
            if event == 'version':
                status['text'] = f'正在准备 V{data} 安装包…'
            elif event == 'progress':
                received, total = data
                progress['value'] = 100 * received / total
                size['text'] = f'{received / 1048576:.1f} / {total / 1048576:.1f} MB'
            elif event == 'ready':
                try:
                    # Use normal DLL search rules for the native installer.
                    ctypes.windll.kernel32.SetDllDirectoryW(None)
                    subprocess.Popen([str(data)], cwd=data.parent, close_fds=True)
                except OSError:
                    status['text'] = '无法启动安装向导，请重试或打开发布页。'
                    retry.state(['!disabled'])
                else:
                    close()
                    return
            elif event == 'error':
                status['text'] = data
                retry.state(['!disabled'])
        root.after(100, render)

    start()
    render()
    root.mainloop()


if __name__ == '__main__':
    main()
