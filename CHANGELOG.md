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
- **No pre-built releases.** Users build the desktop bundle from
  source per the README's *Building the desktop app* section.
  GitHub Actions / matrix CI is intentionally not part of this repo
  (removed after several rounds of platform-specific runner +
  ffmpeg-source issues didn't pay off for a small audience).
- **Padwright** brand applied across user-visible strings *and*
  technical identifiers: Tauri bundle id `com.padwright.app`,
  Rust crate `padwright` (lib `padwright_lib`), npm package
  `padwright`, sidecar binary `padwright-server`, stdout marker
  `PADWRIGHT_PORT`. Pre-1.0 dev builds used `com.sp404mk2.toolkit` —
  the web app reads the legacy data dir on first launch and migrates
  config to the new path automatically.
- **Apache License 2.0** (`LICENSE`, `NOTICE`). All source code is
  Apache-2.0; bundled ffmpeg/ffprobe ship under their own LGPL terms.
- **`requirements-dev.txt`** for test + build deps (`httpx` for the
  FastAPI TestClient, `pyinstaller`, `Pillow`). The web tests no longer
  silently skip when dev deps are installed.

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
