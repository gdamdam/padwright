# Changelog

All notable changes to Padwright are documented here.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning: [Semantic Versioning](https://semver.org/).

## [Unreleased]

_Nothing yet._

## [1.0.0] - 2026-05-17

First tagged release. Padwright now ships as a desktop app (Tauri)
wrapping the Python + FastAPI web UI, alongside the existing CLI tools.

### Added

- **Desktop app**: Tauri shell with a bundled Python sidecar
  (PyInstaller) and bundled ffmpeg/ffprobe. Loads the FastAPI UI via
  a custom `app://` URI scheme so macOS ATS doesn't block plain-HTTP
  localhost loads.
- **Web UI** (`web/app.py`, FastAPI + Jinja2 + small vanilla JS): library
  browse, kit detail with in-browser audio audition, pad swap,
  drag-and-drop crate editor, samples browser, duplicate audit, and a
  Settings page that persists per-user config (root + samples folders).
- **`make_kit_from_crate.py`**, **`rebuild_kit.py`**, **`swap_pad.py`**,
  **`audit_kits.py`** CLI tools alongside the existing kit/loop
  builders. Manifests + pad maps for every bank.
- **GitHub Actions** matrix build for macOS arm64, macOS x64, Windows
  x64, and Linux x64. Pushing a `v*.*.*` tag produces draft GitHub
  Releases with bundles for each platform.
- **Padwright** brand applied to user-visible strings while the
  technical identifier (`com.sp404mk2.toolkit`) stays put so the
  macOS data dir doesn't move on upgrade.

### Changed

- **Loop detection** in `make_breakbeats.py` now uses ffprobe duration
  (default ≤ 16s, override via `--loop-seconds`) instead of the legacy
  1 MB size heuristic. Size acts only as a safety fallback when ffprobe
  is unavailable. 8 MB hard cap to avoid probing huge stems.
- **`make_kits.build_kit`** now delegates to the shared
  `sp404_core.build_from_pad_list` exporter (new `export_source` field
  + `on_pad_done` callback). Output is byte-identical to before,
  verified by the deterministic-sha256 rebuild test.
- **Classifier** picks up Roland-style `Hat_C*`, `Hat_O*`, and
  `Tom{Lo,Mi,Hi}*` naming used by TR-606/808/909 packs.
- **Path safety** in the web/desktop app: swap and crate-build reject
  source paths outside the configured samples root. Sources that
  silently fail validation are recorded as warnings in the manifest
  rather than aborting the build. CLI users without `--samples` keep
  full flexibility.

### Fixed

- **Audit page** links to kits — previously referenced an undefined
  `root` template variable. Route now annotates each entry with
  `kit_rel` so links resolve correctly.
- **Silent WAV paths** honor `TMPDIR` so all scripts work under
  hardened or restricted `/tmp` environments.
- **Manifest source paths** preserved after temp extraction — previously
  pointed at deleted tempdir copies, which broke `rebuild_kit.py` and
  crate-dump round-trips on zip-extracted builds.
