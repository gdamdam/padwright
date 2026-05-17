# Sidecar binaries

Tauri's `bundle.externalBin` looks for files named with a target-triple
suffix:

```
padwright-server-aarch64-apple-darwin
padwright-server-x86_64-apple-darwin
padwright-server-x86_64-pc-windows-msvc.exe
padwright-server-x86_64-unknown-linux-gnu

ffmpeg-aarch64-apple-darwin
ffmpeg-x86_64-apple-darwin
…

ffprobe-aarch64-apple-darwin
ffprobe-x86_64-apple-darwin
…
```

These files are not committed (`.gitignore` excludes them). They're
produced by:

1. **`padwright-server`** — PyInstaller against `pyinstaller_app.spec` from
   the repo root. See the README section "Building the desktop app".
2. **`ffmpeg` / `ffprobe`** — static LGPL builds:
   - macOS: <https://evermeet.cx/ffmpeg/>
   - Windows: <https://www.gyan.dev/ffmpeg/builds/>
   - Linux: <https://johnvansickle.com/ffmpeg/>
   Rename each to `ffmpeg-<target-triple>` (no `.exe` on non-Windows).
