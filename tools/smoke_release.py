"""Exercise the shipped ZIP without Python/dependencies on its executable's PATH."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    cache = ROOT / '.cache'
    cache.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='release smoke ', dir=cache) as temporary:
        work = Path(temporary)
        with zipfile.ZipFile(ROOT / 'dist' / 'YouTubeToMP3-Windows-x64.zip') as archive:
            archive.extractall(work)
        app_folder = work / 'YouTubeToMP3'
        tools = app_folder / '_internal' / 'tools'
        for name in ('ffmpeg', 'ffprobe', 'deno'):
            subprocess.run([str(tools / (name + '.exe')), '-version' if name != 'deno' else '--version'],
                           check=True, capture_output=True)
        # A local WAV avoids relying on network availability or any copyrighted track.
        audio = work / 'youtube.com-test.wav'
        subprocess.run([str(tools / 'ffmpeg.exe'), '-y', '-f', 'lavfi', '-i',
                        'sine=frequency=440:duration=2', str(audio)], check=True, capture_output=True)
        media = ThreadingHTTPServer(('127.0.0.1', 0), partial(SimpleHTTPRequestHandler, directory=str(work)))
        threading.Thread(target=media.serve_forever, daemon=True).start()
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        env = os.environ.copy()
        env['PATH'] = str(Path(env.get('SYSTEMROOT', 'C:/Windows')) / 'System32')
        process = subprocess.Popen([str(app_folder / 'YouTubeToMP3.exe'), '--headless', '--port', str(port)],
                                   cwd=work, env=env)
        base = f'http://127.0.0.1:{port}'
        try:
            for _ in range(90):
                if process.poll() is not None:
                    raise RuntimeError('Packaged executable exited during startup; check app.log')
                try:
                    with urllib.request.urlopen(base, timeout=1) as response:
                        page = response.read()
                    break
                except (OSError, urllib.error.URLError):
                    time.sleep(0.5)
            else:
                raise RuntimeError('Packaged executable did not become ready')
            assert b'YouTube to MP3' in page and b'convert-form' in page
            for asset in ('/static/style.css', '/static/script.js'):
                with urllib.request.urlopen(base + asset) as response:
                    assert response.status == 200 and len(response.read()) > 100
            invalid = urllib.request.Request(base + '/convert', data=b'{"url":""}',
                                             headers={'Content-Type': 'application/json'})
            try:
                urllib.request.urlopen(invalid)
                raise AssertionError('Empty URL was accepted')
            except urllib.error.HTTPError as error:
                assert error.code == 400
            payload = json.dumps({'url': f'http://127.0.0.1:{media.server_port}/{audio.name}'}).encode()
            request = urllib.request.Request(base + '/convert', data=payload,
                                             headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(request, timeout=90) as response:
                result = json.load(response)
            assert result['success'], result
            with urllib.request.urlopen(base + result['download_url']) as response:
                assert 'attachment' in response.headers['Content-Disposition']
                mp3 = work / 'download.mp3'
                mp3.write_bytes(response.read())
            output = subprocess.check_output([str(tools / 'ffprobe.exe'), '-v', 'error',
                       '-show_entries', 'stream=codec_name', '-of', 'json', str(mp3)])
            assert json.loads(output)['streams'][0]['codec_name'] == 'mp3'
            print('PASS: extracted executable, isolated PATH, UI/assets, validation, conversion/download, FFmpeg/FFprobe/Deno')
        finally:
            process.terminate()
            process.wait(timeout=15)
            media.shutdown()
            media.server_close()


if __name__ == '__main__':
    main()
