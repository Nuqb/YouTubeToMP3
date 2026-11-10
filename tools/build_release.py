"""Build the portable Windows ZIP using the current Python environment."""
import hashlib
import importlib.metadata
import json
import re
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / '.cache' / 'release'
TOOLS = CACHE / 'tools'
VERSION = '1.0.0'


def download(url, destination):
    if not destination.exists():
        print(f'Downloading {url}', flush=True)
        request = urllib.request.Request(url, headers={'User-Agent': 'YouTubeToMP3-release'})
        temporary = destination.with_suffix(destination.suffix + '.partial')
        with urllib.request.urlopen(request, timeout=180) as response, temporary.open('wb') as output:
            shutil.copyfileobj(response, output)
        temporary.replace(destination)


def main():
    if sys.platform != 'win32':
        raise SystemExit('Build this Windows release on Windows.')
    TOOLS.mkdir(parents=True, exist_ok=True)
    ffmpeg_url = 'https://github.com/GyanD/codexffmpeg/releases/download/8.1.2/ffmpeg-8.1.2-essentials_build.zip'
    ffmpeg_zip = CACHE / 'ffmpeg.zip'
    download(ffmpeg_url, ffmpeg_zip)
    download('https://api.github.com/repos/GyanD/codexffmpeg/releases/tags/8.1.2', CACHE / 'ffmpeg-release.json')
    assets = json.loads((CACHE / 'ffmpeg-release.json').read_text())['assets']
    expected = next(a['digest'].removeprefix('sha256:') for a in assets
                    if a['name'] == ffmpeg_url.rsplit('/', 1)[1])
    if hashlib.file_digest(ffmpeg_zip.open('rb'), 'sha256').hexdigest() != expected:
        raise SystemExit('FFmpeg checksum mismatch')
    with zipfile.ZipFile(ffmpeg_zip) as archive:
        for name in ('ffmpeg.exe', 'ffprobe.exe'):
            member = next(n for n in archive.namelist() if n.endswith('/bin/' + name))
            (TOOLS / name).write_bytes(archive.read(member))
        license_member = next(n for n in archive.namelist() if n.endswith('/LICENSE'))
        (CACHE / 'FFmpeg-LICENSE.txt').write_bytes(archive.read(license_member))
    deno_url = 'https://github.com/denoland/deno/releases/download/v2.5.6/deno-x86_64-pc-windows-msvc.zip'
    download(deno_url, CACHE / 'deno.zip')
    download(deno_url + '.sha256sum', CACHE / 'deno.sha256')
    expected = re.search(r'\b[0-9a-fA-F]{64}\b', (CACHE / 'deno.sha256').read_text()).group().lower()
    if hashlib.file_digest((CACHE / 'deno.zip').open('rb'), 'sha256').hexdigest() != expected:
        raise SystemExit('Deno checksum mismatch')
    with zipfile.ZipFile(CACHE / 'deno.zip') as archive:
        (TOOLS / 'deno.exe').write_bytes(archive.read('deno.exe'))
    command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
               '--windowed', '--onedir', '--name', 'YouTubeToMP3',
               '--add-data', 'templates;templates', '--add-data', 'static;static',
               '--add-binary', f'{TOOLS};tools', '--collect-all', 'yt_dlp',
               '--collect-all', 'yt_dlp_ejs', '--collect-all', 'mutagen', 'desktop.py']
    subprocess.run(command, cwd=ROOT, check=True)
    folder = ROOT / 'dist' / 'YouTubeToMP3'
    shutil.copy2(ROOT / 'docs' / 'START-HERE.txt', folder)
    shutil.copy2(ROOT / 'docs' / 'THIRD-PARTY-NOTICES.md', folder)
    licenses = folder / 'licenses'
    licenses.mkdir(exist_ok=True)
    shutil.copy2(CACHE / 'FFmpeg-LICENSE.txt', licenses)
    download('https://raw.githubusercontent.com/denoland/deno/v2.5.6/LICENSE.md', licenses / 'Deno-LICENSE.md')
    # Preserve license files shipped by every installed runtime dependency.
    for distribution in importlib.metadata.distributions():
        for file in distribution.files or []:
            if any(part.lower().startswith(('license', 'copying', 'notice')) for part in file.parts):
                source = Path(distribution.locate_file(file))
                if source.is_file():
                    target = licenses / distribution.metadata['Name'] / str(file)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
    manifest = {'version': VERSION, 'ffmpeg': ffmpeg_url, 'deno': deno_url,
                'packages': {d.metadata['Name']: d.version for d in importlib.metadata.distributions()}}
    (folder / 'build-info.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    archive = Path(shutil.make_archive(str(ROOT / 'dist' / 'YouTubeToMP3-Windows-x64'),
                                     'zip', folder.parent, folder.name))
    digest = hashlib.file_digest(archive.open('rb'), 'sha256').hexdigest()
    (archive.parent / 'SHA256SUMS.txt').write_text(f'{digest}  {archive.name}\n', encoding='ascii')
    print(f'Release ready: {archive}', flush=True)


if __name__ == '__main__':
    main()
