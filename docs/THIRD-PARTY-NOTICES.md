# Bundled software

The application's own code and documentation are licensed under the MIT License
in the root `LICENSE` file. That license does not replace the licenses of the
third-party software listed below.

The portable release bundles Python, Flask, Waitress, yt-dlp (with its default
dependencies and EJS scripts), FFmpeg/FFprobe, and Deno. License texts are in
`licenses/`; exact Python package versions and binary URLs are in `build-info.json`.
These components retain their respective licenses.

- Python: https://www.python.org/psf/license/
- yt-dlp: https://github.com/yt-dlp/yt-dlp
- Deno 2.5.6 (MIT): https://github.com/denoland/deno/tree/v2.5.6
- FFmpeg 8.1.2 essentials build, supplied unmodified by Gyan:
  https://www.gyan.dev/ffmpeg/builds/
  This build is GPL v3; see `licenses/FFmpeg-LICENSE.txt`.
  Upstream source: https://ffmpeg.org/releases/ffmpeg-8.1.2.tar.xz
  Build configuration/dependency information: https://github.com/GyanD/codexffmpeg

FFmpeg and Deno run as separate helper processes. They are not linked into the
application's Python code. Source and build instructions for this app accompany
the release through GitHub's source archives.
