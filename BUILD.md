# Building the desktop app

This produces a double-clickable `.app` (macOS), `.msi` (Windows), or
`.deb`/`.AppImage` (Linux) that wraps the Python web UI from
`web/app.py` in a Tauri window. The Python interpreter and ffmpeg are
bundled inside; end users don't need to install anything.

## One-time setup

1. **Rust + Tauri CLI**
   ```bash
   curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
   cargo install tauri-cli@^2 --locked
   ```
2. **Node ≥ 18** (only used to drive npm scripts)
3. **Python ≥ 3.11** in a venv:
   ```bash
   python3 -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   pip install pyinstaller
   ```
4. **Icon** (one-time):
   ```bash
   cd src-tauri
   cargo tauri icon path/to/source-icon-1024.png
   cd ..
   ```
5. **Apple Developer account** (only if you'll distribute to non-technical
   Mac users — $99/year). Without it, users get a Gatekeeper warning.

## Building

```bash
# 1. Bundle the Python web app into a single executable
pyinstaller --clean pyinstaller_app.spec

# 2. Rename it with the target triple Tauri expects
node scripts/install_sidecar.mjs

# 3. Install static ffmpeg/ffprobe sidecars (script prints the URLs;
#    drop the unpacked binaries into src-tauri/binaries/)
node scripts/install_ffmpeg.mjs

# 4. Dev run (hot reload):
npm run tauri:dev

# 5. Production build (writes the installer under src-tauri/target/):
npm run tauri:build
```

Output:

```
src-tauri/target/release/bundle/
  dmg/SP-404 Toolkit_0.1.0_<arch>.dmg
  macos/SP-404 Toolkit.app
```

## How the lifecycle works

1. Tauri opens the main window pointing at the static `loading/index.html`
   placeholder ("starting Python sidecar…").
2. Tauri spawns the bundled `sp404-server` sidecar with `--port 0` and
   `FFMPEG_PATH` / `FFPROBE_PATH` pointing at the bundled ffmpeg binaries.
3. The Rust setup task listens to stdout, parses `SP404_PORT=<n>`, and
   navigates the webview to `http://127.0.0.1:<n>/`.
4. On app exit, the Rust runtime kills the sidecar.

## Signing & notarization (Mac)

```bash
# Sign (assumes Apple Developer ID Application certificate in your keychain)
export APPLE_SIGNING_IDENTITY="Developer ID Application: Your Name (TEAMID)"
npm run tauri:build

# Notarize
xcrun notarytool submit \
  "src-tauri/target/release/bundle/dmg/SP-404 Toolkit_0.1.0_*.dmg" \
  --apple-id you@example.com \
  --team-id TEAMID \
  --password app-specific-password \
  --wait

# Staple
xcrun stapler staple "src-tauri/target/release/bundle/dmg/SP-404 Toolkit_*.dmg"
```

## Cross-compilation

Mac to Windows / Linux is unreliable. Recommended pattern: GitHub Actions
matrix with one runner per OS. A starter workflow lives at
`.github/workflows/build.yml` (not committed yet — add it before the first
public release).

## Troubleshooting

- **"sp404-server sidecar not found"** during `tauri:dev` — re-run steps
  1 and 2; verify `src-tauri/binaries/sp404-server-<triple>` exists.
- **Webview shows the loading screen forever** — open the devtools
  (right-click → Inspect) and look at the terminal log for
  `[sp404-server]` lines. Most likely the sidecar failed to start
  because PyInstaller didn't bundle a hidden import. Add it to
  `hiddenimports` in `pyinstaller_app.spec`.
- **macOS "app is damaged" Gatekeeper error** — your `.app` isn't signed.
  Either sign it (see above) or right-click → Open the first time.
- **Audio doesn't play in the bundled app but works in `python -m web.app`**
  — the bundle may not be exposing the bundled ffmpeg path correctly.
  Check `[sp404-server]` log for whether `FFMPEG_PATH` is set.
