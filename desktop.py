"""Portable desktop launcher; the converter is served only on loopback."""
import argparse
import atexit
import logging
import os
from pathlib import Path
import shutil
import sys
import threading
import webbrowser


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--headless', action='store_true', help='Do not open a window/browser')
    parser.add_argument('--port', type=int, default=0, help='0 chooses an available local port')
    args = parser.parse_args()
    bundle = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
    tools = bundle / 'tools'
    if tools.is_dir():
        os.environ['PATH'] = str(tools) + os.pathsep + os.environ.get('PATH', '')
    log_dir = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'YouTubeToMP3'
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / 'app.log'
    stream = open(log_path, 'a', encoding='utf-8', buffering=1)
    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream
    logging.basicConfig(filename=log_path, level=logging.INFO)

    from app import app, TEMP_FOLDER
    from waitress import create_server
    atexit.register(shutil.rmtree, TEMP_FOLDER, ignore_errors=True)

    root = None
    try:
        if not args.headless:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
        for tool in ('ffmpeg', 'ffprobe', 'deno'):
            if not shutil.which(tool):
                raise RuntimeError(f'{tool} is missing. Extract the entire ZIP and try again.')
        server = create_server(app, host='127.0.0.1', port=args.port, threads=4)
        url = f'http://127.0.0.1:{server.effective_port}'
        if args.headless:
            print(url, flush=True)
            server.run()
            return
        threading.Thread(target=server.run, daemon=True).start()
        root.title('YouTube to MP3')
        root.geometry('420x240')
        root.resizable(False, False)
        root.configure(bg='#101214')
        tk.Label(root, text='YouTube to MP3', font=('Segoe UI', 21, 'bold'),
                 fg='#f09cbd', bg='#101214').pack(pady=(24, 8))
        tk.Label(root, text='The converter is running in your browser.\nClose this window when you are finished.',
                 font=('Segoe UI', 10), fg='white', bg='#101214').pack(pady=8)
        tk.Button(root, text='Open converter', command=lambda: webbrowser.open(url),
                  font=('Segoe UI', 11), bg='#f09cbd', relief='flat', padx=20).pack(pady=10)
        tk.Label(root, text=url, fg='#aaaaaa', bg='#101214').pack()
        root.protocol('WM_DELETE_WINDOW', root.destroy)
        root.deiconify()
        webbrowser.open(url)
        try:
            root.mainloop()
        finally:
            server.close()
    except Exception as exc:
        logging.exception('Unable to start')
        if root is not None:
            messagebox.showerror('YouTube to MP3 could not start', f'{exc}\n\nDetails: {log_path}')
            root.destroy()
        else:
            raise


if __name__ == '__main__':
    main()
