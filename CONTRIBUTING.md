# Contributing

Bug reports, documentation fixes, UI improvements, and code contributions are
welcome. You do not need to write code to help.

## Report a problem or suggest an improvement

Search [existing issues](https://github.com/Nuqb/YouTubeToMP3/issues) first. If your
problem is new, open an issue with:

- Your operating system and app release version.
- What you expected and what happened.
- Steps to reproduce, the error message, and a screenshot if useful.
- Whether the problem affects one public link or several platforms.

Only share links you have permission to share. Remove personal information,
private URLs, cookies, and credentials from logs and screenshots. Startup logs
on Windows are at `%LOCALAPPDATA%\YouTubeToMP3\app.log`.

## Make a change

1. Fork the repository and create a branch for your change.
2. Follow the [developer setup in the README](README.md#for-developers).
3. Keep the change focused. Update documentation when behavior changes.
4. Check the affected flow in your browser. For UI changes, check both a narrow
   mobile layout and a desktop layout, including keyboard navigation.
5. Open a pull request describing the problem, your change, and how you checked it.
   Include before/after screenshots for visible UI changes.

For larger features or changes to the download experience, opening an issue first
helps agree on the approach before you spend time implementing it.

## Validate a Windows package

When changing the launcher, conversion dependencies, or packaging, use 64-bit
Windows with Python 3.12 and run:

```powershell
python -m pip install -r requirements-build.txt
python tools/build_release.py
python tools/smoke_release.py
```

The smoke check extracts and runs the actual ZIP, checks the UI and bundled tools,
and converts a generated local audio sample. It does not test third-party platform
availability. The root `test_*.py` scripts are manual network diagnostics, not an
automated test suite. Use content you own or have permission to download for
any manual platform checks.

Do not commit virtual environments, build output, downloaded binaries, temporary
audio, credentials, or Python cache files. Release artifacts are uploaded through
GitHub Releases rather than committed to Git.

## License and collaboration

By submitting a contribution, you agree to license it under this project's
[MIT License](LICENSE). Only contribute work you have the right to share, and
preserve third-party notices when adding or updating dependencies. Bundled tools
retain their own licenses; see [third-party notices](docs/THIRD-PARTY-NOTICES.md).

Be respectful and keep feedback focused on the work. Maintainers review pull
requests before merging; a contribution does not guarantee acceptance.
