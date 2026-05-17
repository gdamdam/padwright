# Padwright — SP-404MKII Bank Builder

**v1.0.0** · A toolkit for turning sample folders into SP-404MKII-friendly
banks. Ships as a desktop app (Tauri) wrapping a small Python+FastAPI web
UI, plus standalone CLI tools. Not a sample browser, not a Sononym
replacement — this is the **last-mile exporter** that lives between
"huge sample library" and "16 playable pads on the SP".

The workflow it covers:

```text
scan → classify → export → manifest → audit → swap/curate → drag-and-drop
```

Discovery and crate-digging live in other tools (Sononym, XO, COSMOS,
Finder). Padwright makes sure that whatever you point it at ends up as a
predictable, inspectable, re-curatable 16-pad bank.

## Contents

- [Quick start](#quick-start)
- [Requirements](#requirements)
- [Using Padwright](#using-padwright)
- [Pad layout](#pad-layout)
- [Building the desktop app](#building-the-desktop-app)
- [Releasing (CI)](#releasing-ci)
- [Scripts](#scripts)
- [Manifests & pad maps](#manifests--pad-maps)
- [Crates](#crates)
- [Troubleshooting](#troubleshooting)
- [Before a release](#before-a-release)
- [License](#license)
- [What's still rough](#whats-still-rough)
- [Direction](#direction)

## Quick start

Three ways to use it, depending on how comfortable you are with a terminal.

### A. Desktop app (no terminal, no Python knowledge required)

Download a pre-built bundle from the [Releases page][releases]:

[releases]: ../../releases/latest

- **macOS Apple Silicon (M-series)** — `Padwright_<ver>_aarch64.dmg`
  (native arm64 app; bundled ffmpeg sidecar is Intel and runs via
  Rosetta, which macOS auto-prompts on first launch). Intel Macs are
  not covered in v1.0.x.
- **Windows x64** — `Padwright_<ver>_x64_en-US.msi`
- **Linux x64** — `Padwright_<ver>_amd64.AppImage` or `.deb`

> **First-launch warning, one-time:** the bundles aren't yet code-signed,
> so the OS will warn the first time you open Padwright. This is expected.
> - **macOS**: right-click the app → Open → confirm.
> - **Windows**: SmartScreen → "More info" → "Run anyway".
> - **Linux**: no warning.
>
> See [What's still rough](#whats-still-rough) for why and how this will
> change.

Once installed:

1. Double-click the app.
2. First-launch shows an empty library — click **Settings** and point
   it at:
   - **Built kits folder (root)** — where Padwright reads/writes banks.
     Pick a folder you control (`~/Music/SP_EXPORT` is a good default).
   - **Samples library folder** — the root of your local sample folders.
3. Click **New crate**, drag samples onto pads, **Build kit**.
4. In Finder, drag the 16 WAV files from the kit folder into the Roland
   SP-404MKII app.

Settings persist in a per-user config file:

| Platform | Path |
| --- | --- |
| macOS   | `~/Library/Application Support/com.padwright.app/config.json` |
| Windows | `%APPDATA%\Padwright\config.json`                              |
| Linux   | `~/.config/padwright/config.json`                              |

(If you used a pre-1.0 dev build with the old `com.sp404mk2.toolkit`
identifier, Padwright migrates that config automatically on first launch.)

If no release matches your platform, you can build one yourself — see
[Building the desktop app](#building-the-desktop-app).

### B. Local web UI (Python users)

```bash
git clone <repo-url> padwright
cd padwright
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 -m web.app --root ~/Music/SP_EXPORT --samples ~/Music/Samples
# → browser opens at localhost:<auto-port>
```

Same UI as the desktop app, served from a local FastAPI process. `--root`
and `--samples` here override any saved config; omit them to use the
Settings page instead.

### C. Command line (scripts only)

```bash
pip install --upgrade pip   # no requirements.txt needed for CLI tools
# (only ffmpeg + ffprobe on PATH)

# Build all kits from a folder of unzipped sample packs:
python3 make_kits.py --unzipped \
  --src ~/Music/Samples --dst ~/Music/SP_EXPORT

# Build loop banks (uses ffprobe duration ≤ 16s by default):
python3 make_breakbeats.py --src ~/Music/Samples --dst ~/Music/SP_LOOPS

# Find duplicate pads across built kits:
python3 audit_kits.py ~/Music/SP_EXPORT --exclude-super

# Replace one pad in a built kit:
python3 swap_pad.py ~/Music/SP_EXPORT/Roland_TR808 13 ~/Music/Samples/kick.wav
```

Every script has `--help`.

## Requirements

- **Python 3.11+** (uses `X | Y` type hints)
- **`ffmpeg` and `ffprobe`** on `PATH` (or set `FFMPEG_PATH` / `FFPROBE_PATH`)
- A source folder of `.zip` packs, unzipped pack folders, or loose audio
- The Roland SP-404MKII app for final drag-and-drop

Web/desktop additionally need: `fastapi`, `uvicorn`, `jinja2`,
`python-multipart` (all in `requirements.txt`).

Running the test suite or building the bundle additionally needs:
`httpx`, `pyinstaller`, `Pillow` (all in `requirements-dev.txt`).
Install both with:

```bash
pip install -r requirements.txt -r requirements-dev.txt
```

Building the desktop app additionally needs: Rust toolchain, Tauri CLI,
Node.js ≥ 18.

Output WAV formats:

- Drum kits (`make_kits.py`): `48 kHz / 16-bit / mono`
- Loop banks (`make_breakbeats.py`): `48 kHz / 16-bit / stereo`
- Silent placeholder pads: short `48 kHz / 16-bit / mono` WAVs

## Using Padwright

Whether you're in the desktop app, the web UI, or the CLI, the
end-to-end flow is the same:

```text
1. scan      a folder of samples / packs
2. classify  by filename (kick, snare, hat, …)
3. export    one 16-pad bank per source (deterministic)
4. manifest  per-pad sha256/source/type/duration written next to the WAVs
5. audit     find duplicate pads across the library
6. swap      replace any pad with a hand-picked source
7. crate     write a JSON file describing intent; build from it
8. drag      the 16 WAVs into the Roland SP-404MKII app
```

### Recommended workflow (desktop app or web UI)

1. **Set folders** in Settings: built-kits root + samples library.
2. **Build a library** from the CLI once:
   ```bash
   python3 make_kits.py --unzipped --src <samples> --dst <root>
   ```
   The UI's Library view immediately reflects what's there.
3. **Open a kit** to see the 4×4 pad grid with audio audition.
4. **Swap any pad** that picked a mediocre source — paste an absolute
   path or use the desktop app's drag-from-sample-browser.
5. **Edit as crate** lets you hand-curate: dump the kit to JSON, edit,
   rebuild without touching the other 15 pads.
6. **Audit** to find duplicates across the library; `--exclude-super`
   filters out super-bank entries (which are intentional copies).
7. Drag the 16 WAVs from the kit folder into the Roland SP-404MKII app.

### Recommended workflow (CLI only)

```bash
# 1. Dry-run scan first
python3 make_kits.py --dry-run --unzipped --src <samples> --dst <root>

# 2. If the breakdown looks reasonable, build for real
python3 make_kits.py --unzipped --src <samples> --dst <root>

# 3. Open the static pad-map.html for any kit to audition
open <root>/drumkit/SomeKit/pad-map.html

# 4. Swap a pad whose representative is weak
python3 swap_pad.py <root>/drumkit/SomeKit 13 /path/to/better_kick.wav

# 5. Drag the 16 WAVs into the Roland SP-404MKII app
```

Hand-curated kits via crate:

```bash
# Dump a built kit as an editable crate
python3 make_kit_from_crate.py --from-kit <root>/drumkit/SomeKit \
  --out my.crate.json

# … edit my.crate.json in any text editor …
# Build the curated kit
python3 make_kit_from_crate.py my.crate.json <root>
```

## Pad layout

Every 16-pad drum kit follows this layout:

```text
01_empty      02_empty      03_empty       04_empty
05_rim        06_clap       07_cowbell     08_perc
09_low_tom    10_mid_tom    11_hi_tom      12_crash
13_kick       14_snare      15_closed_hh   16_open_hh
```

Files are named in pad order so the Roland app's sorted import lands
exactly where you expect. Kick / snare / hats sit on the bottom row for
finger drumming. Top row is silent placeholders.

Loop banks (`make_breakbeats.py`) use the same numbering but every pad is
a loop, no silent rows.

Every generated bank ships with a `manifest.json` and a `pad-map.html`
next to the WAVs. See **Manifests & pad maps** below.

## Building the desktop app

This produces a double-clickable `.app` (macOS), `.msi` (Windows), or
`.deb`/`.AppImage` (Linux) that bundles the Python runtime and ffmpeg
inside. End users don't need Python, pip, or a terminal.

The architecture: Tauri's Rust shell opens a window pointing at a
loading screen, spawns a bundled Python (PyInstaller) sidecar that
runs the FastAPI app on a random localhost port, prints
`PADWRIGHT_PORT=<n>` from its lifespan hook, and the Rust shell then
navigates the webview via a custom `app://` URI scheme that proxies
every request to the sidecar. ATS / localhost-block issues are
sidestepped because the webview never sees an `http://` URL.

### One-time setup

1. **Rust + Tauri CLI**
   ```bash
   curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
   cargo install tauri-cli@^2 --locked
   ```
2. **Node ≥ 18** — used only to drive a few packaging scripts.
3. **Python ≥ 3.11** in a venv:
   ```bash
   python3 -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   pip install pyinstaller pillow
   ```
4. **App icon** (one-time per clone): the committed `icon.png` at the
   repo root is the master. Generate the platform-specific derived
   icons (they're gitignored, so a fresh clone has none):
   ```bash
   cd src-tauri && cargo tauri icon ../icon.png && cd ..
   ```
   To change the icon: replace `./icon.png` (1024×1024 recommended) and
   rerun the command above. CI regenerates derived icons from the
   committed master on every build.
5. **Apple Developer account** (only if shipping to non-technical Mac
   users; $99/year). Without it, users get a Gatekeeper warning —
   right-click → Open works as a one-time bypass for friends.

### Build

```bash
# 1. Bundle web/app.py into a single padwright-server executable.
pyinstaller --clean pyinstaller_app.spec

# 2. Rename it with Tauri's target-triple suffix and copy to src-tauri/binaries/
node scripts/install_sidecar.mjs

# 3. Drop static ffmpeg + ffprobe binaries into src-tauri/binaries/
node scripts/install_ffmpeg.mjs
# (script prints LGPL-build URLs; download, unzip, rename to
#  ffmpeg-<target-triple> and ffprobe-<target-triple>, chmod +x)

# 4. Dev run with hot reload
npm install                # one-time
npm run tauri:dev

# 5. Production bundle (writes to src-tauri/target/release/bundle/)
npm run tauri:build
```

Output on macOS:

```text
src-tauri/target/release/bundle/
  dmg/Padwright_1.0.0_<arch>.dmg
  macos/Padwright.app
```

### Signing & notarization (macOS, optional)

Only needed for distribution to non-technical Mac users.

```bash
# Sign (assumes a Developer ID Application cert in your keychain)
export APPLE_SIGNING_IDENTITY="Developer ID Application: Your Name (TEAMID)"
npm run tauri:build

# Notarize the resulting .dmg
xcrun notarytool submit \
  "src-tauri/target/release/bundle/dmg/Padwright_1.0.0_*.dmg" \
  --apple-id you@example.com \
  --team-id TEAMID \
  --password app-specific-password \
  --wait

# Staple the notarization to the .dmg so Gatekeeper trusts it offline
xcrun stapler staple "src-tauri/target/release/bundle/dmg/Padwright_1.0.0_*.dmg"
```

### Cross-compilation

Building Mac → Windows / Linux is unreliable. Use a GitHub Actions
matrix (one runner per OS) — `.github/workflows/release.yml` is wired
up to do exactly that on a `v*.*.*` tag push. See **Releasing (CI)**
below.

### When you change code

- **Python (`web/app.py` etc.):** re-run `pyinstaller --clean
  pyinstaller_app.spec && node scripts/install_sidecar.mjs`. Tauri's
  file watcher will spot the new sidecar and trigger a Rust rebuild.
- **Rust (`src-tauri/src/*.rs`):** `cargo tauri dev` recompiles
  automatically.
- **Templates / static (`web/templates`, `web/static`):** re-bundle
  the sidecar because they're embedded in the PyInstaller output.

If the Rust target cache gets confused after a path move:
`rm -rf src-tauri/target` and rebuild.

## Releasing (CI)

GitHub Actions builds Padwright for macOS arm64, Windows x64,
and Linux x64 on every semver tag push. See
[`.github/workflows/release.yml`](.github/workflows/release.yml).

To cut a release:

```bash
# Bump versions in package.json, src-tauri/Cargo.toml, src-tauri/tauri.conf.json
git commit -am "release v1.1.0"
git tag v1.1.0
git push origin main --tags
```

The workflow, in order:

1. Spins up a runner per OS (matrix build, ~20–30 min) and installs
   Rust, Node, Python, system deps, **plus `requirements-dev.txt` so
   the full test suite runs**.
2. Installs ffmpeg/ffprobe on the runner (via brew / apt / choco) so the
   ffmpeg-dependent tests actually exercise the binary.
3. **Runs `python tests.py` — a failing test aborts the run before any
   bundle is produced.**
4. Bundles `web/app.py` into a PyInstaller executable, renamed with
   Tauri's target-triple suffix into `src-tauri/binaries/`.
5. Downloads static LGPL ffmpeg + ffprobe builds (BtbN/FFmpeg-Builds)
   and installs them as Tauri sidecars in `src-tauri/binaries/`.
6. Installs npm deps (provides tauri-cli).
7. Regenerates platform-specific icons from the committed root
   `icon.png` master via `npx @tauri-apps/cli icon icon.png`.
8. **Runs `cargo check`** — intentionally *after* sidecars and icons
   exist, because Tauri's `build.rs` validates `bundle.externalBin`
   paths during configure, so checking earlier would fail on a clean
   runner.
9. Composes release notes by merging `CHANGELOG.md` into
   `.github/RELEASE_NOTES_TEMPLATE.md`.
10. Runs `cargo tauri build` and uploads the bundles to a **draft**
    release named after the tag.

You review the draft on GitHub → publish when ready.

Tag conventions:

- `v1.2.3` → release
- `v1.2.3-beta.1` (any tag containing `-`) → pre-release
- Manual trigger via the Actions tab → `workflow_dispatch`

Per-tag CI consumes 4 runner-instances × ~25 min on free GitHub Actions
minutes. Macs are the expensive runners (10× the per-minute cost).

### Adding code signing later (optional)

Drop these secrets into the repo's Actions settings without touching
`release.yml`:

- **Mac**: `APPLE_CERTIFICATE`, `APPLE_CERTIFICATE_PASSWORD`,
  `APPLE_SIGNING_IDENTITY`, `APPLE_ID`, `APPLE_PASSWORD`, `APPLE_TEAM_ID`
- **Windows**: `TAURI_SIGNING_PRIVATE_KEY`, `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`

`tauri-action` picks these up automatically and signs+notarizes. The
first-launch warnings then disappear. Apple Developer is $99/year,
Windows code-signing certs are typically $200/year from a CA.

## Scripts

### `make_kits.py` — batch drum-kit builder

Scans a source of `.zip` packs (or unzipped folders), classifies audio
files by drum type, picks one representative per slot, exports a 16-pad
kit per pack, and writes per-kit manifests + pad maps.

```bash
cd ~/padwright

python3 make_kits.py --help
python3 make_kits.py --status
python3 make_kits.py --dry-run
python3 make_kits.py --batch 1
python3 make_kits.py --super-only
```

Custom source / destination:

```bash
python3 make_kits.py \
  --unzipped \
  --src ~/Music/Samples \
  --dst ~/Music/SP_EXPORT
```

Filter to packs matching a word:

```bash
python3 make_kits.py --unzipped --src ... --dst ... TR808
```

What it produces under `--dst`:

- `drumkit/<pack>/` — one 16-pad kit per source pack
- `blocks/<pack>/<pack>_<CATEGORY>/` — extra category banks for packs
  with ≥ 100 audio files (KICKS, SNARES, HATS, TOMS, CLAPS, PERC)
- `super/SUPER_<TYPE>/` — cross-pack "best of" banks built after all
  individual kits exist

Tier logic:

- ≤ 16 audio files → use all sounds where possible
- 17–99 files → pick one best-per-type for the main kit
- ≥ 100 files → main kit plus category blocks

Re-running is safe — kits that already contain WAVs are skipped.

### `make_breakbeats.py` — loop-bank builder

Scans a folder recursively for loop files, groups them by folder, exports
up to 16 loops per bank.

```bash
python3 make_breakbeats.py --help
python3 make_breakbeats.py --dry-run
python3 make_breakbeats.py --status
python3 make_breakbeats.py --src /path/to/loops --dst /path/to/output
python3 make_breakbeats.py --loop-seconds 12 --src /path/to/loops --dst ...
```

Loop detection rules, in order:

- `.wav` / `.aif` / `.aiff`, not hidden, not Ableton `.asd`
- `loop` appears in the filename or any parent folder name
- File size under the 8 MB safety cap (never probe huge stems)
- **ffprobe duration ≤ `--loop-seconds`** (default 16s — covers up to
  4 bars at 60 BPM / 8 bars at 120 BPM). This is the real signal.
- If ffprobe isn't available, falls back to the legacy "size < 1 MB"
  heuristic.

Each leaf folder with qualifying loops becomes one bank, sampled evenly
to 16 files. Writes manifest + pad map per bank.

### `reorder_kits.py` — legacy renamer

For kits exported before `make_kits.py` enforced the current pad layout.
Renames old numbered files into the new layout and adds 4 silent
placeholders for the top row.

```bash
python3 reorder_kits.py                            # process default dir in place
python3 reorder_kits.py --src /path/to/kits        # custom source, in place
python3 reorder_kits.py --src SRC --dst DST        # copy reordered kits to DST
python3 reorder_kits.py --dry-run                  # preview only
```

Kits already containing `01_empty.wav` are skipped.

### `swap_pad.py` — replace one pad

Re-exports a single pad from a new source file, updates `manifest.json`,
regenerates `pad-map.html`. The pad's existing filename is reused so the
SP import order doesn't change.

```bash
python3 swap_pad.py <kit_dir> <pad#> <new_source.wav>
python3 swap_pad.py <kit_dir> <pad#> --silence
python3 swap_pad.py <kit_dir> <pad#> <new_source.wav> --type kick
python3 swap_pad.py <kit_dir> <pad#> <new_source.wav> --dry-run
```

Mono / stereo follows the bank's stored `meta.kind` (drumkit → mono,
loop_bank → stereo). The manifest entry's `kind` becomes `"swap"` so you
can later tell auto-built pads apart from hand-chosen ones.

### `rebuild_kit.py` — re-export from manifest

Reads a bank's `manifest.json` and re-runs the exporter against every
pad's recorded `source`. Useful for hand-edited manifests, format
re-conversion, or partial-corruption recovery.

```bash
python3 rebuild_kit.py <kit_dir>
python3 rebuild_kit.py <kit_dir> --out /path/to/copy
python3 rebuild_kit.py <kit_dir> --dry-run
```

Because the export is deterministic, rebuilding from an unchanged
manifest yields byte-identical WAVs (the test suite verifies this).

### `make_kit_from_crate.py` — hand-curated kits

Build a bank from a small JSON crate describing intent. Crates are the
escape hatch from "middle of sorted candidates" — you pick the kick.

```bash
python3 make_kit_from_crate.py <crate.json> <dst_dir>
python3 make_kit_from_crate.py <crate.json> <dst_dir> --name "Override"
python3 make_kit_from_crate.py <crate.json> <dst_dir> --dry-run

# Dump an existing kit as an editable crate:
python3 make_kit_from_crate.py --from-kit <kit_dir> > my.crate.json
python3 make_kit_from_crate.py --from-kit <kit_dir> --out my.crate.json
```

Source files referenced by a crate that no longer exist degrade to
silent placeholders with a warning, so a moved source doesn't abort the
build. See **Crates** below for the format.

### `web/app.py` — local browser UI (FastAPI)

A small web UI on `http://localhost:<port>` that wraps the CLI tools for
non-terminal users. Browse the library, inspect kits with in-browser
audio audition, swap pads via form, edit and build crates with
drag-and-drop from a sample browser, view the duplicate audit.

```bash
pip install -r requirements.txt
python3 -m web.app --root /path/to/built_kits --samples /path/to/samples
python3 -m web.app                                       # use saved config
python3 -m web.app --port 0 --no-browser                 # Tauri sidecar mode
```

Routes: `/` (library), `/kit/<rel>` (kit detail), `/audit`, `/crate`,
`/samples`, `/settings`. POST: `/kit/<rel>/swap`, `/crate/build`,
`/settings`. Audio: `/audio/kit/...` and `/audio/sample?path=...`.

Config persistence: `--root` / `--samples` flags win over a saved
`config.json` (per-user, in the platform data dir). The Settings page
writes the config so the desktop app remembers your folders across
launches.

Path safety: when a samples root is configured, pad swaps and crate
builds reject sources outside it (a warning is recorded in the
manifest for dropped pads). CLI users without `--samples` retain full
flexibility.

Honors `FFMPEG_PATH` / `FFPROBE_PATH` env vars so the bundled-app build
(see [Building the desktop app](#building-the-desktop-app)) can ship its own ffmpeg binaries.

### `audit_kits.py` — find duplicate pads across a built tree

Walks a destination directory, reads every `manifest.json`, groups pad
entries by sha256. Catches cases where two kits picked the same source
file. Super-bank entries are duplicates of drumkit pads by design — pass
`--exclude-super` to filter them out.

```bash
python3 audit_kits.py ~/Music/SP_EXPORT
python3 audit_kits.py ~/Music/SP_EXPORT --exclude-super
python3 audit_kits.py ~/Music/SP_EXPORT --by-source   # group by source path
python3 audit_kits.py ~/Music/SP_EXPORT --json        # machine-readable
```

### `sp404_core.py` — shared library

Single source of truth for: pad layout (`SOUND_SLOTS`, `SLOT_NAMES`,
`SUPER_FILES`), classifier (`classify`, `CLASSIFIERS`), ffmpeg/ffprobe
wrappers (`export`, `ffprobe_info`), file helpers
(`list_audio`, `extract_audio`, `sanitize`, `shorten_name`,
`evenly_sample`, `sha256_file`), manifest + pad-map writers
(`write_manifest`, `write_pad_map`), the unified exporter
(`build_from_pad_list`), crate helpers (`load_crate`,
`manifest_to_crate`), and the terminal UI dashboard (`UI`).

Importing-script style: `from sp404_core import ...`. No package, no
install step — it's a flat module next to the scripts.

### `tests.py` — sanity checks

```bash
python3 tests.py
```

No pytest dependency. ~5s. Covers: classifier behavior, pad-layout
invariants, manifest/pad-map round-trip, end-to-end kit build,
end-to-end pad swap, rebuild determinism (sha256 stable), crate
round-trip, and missing-source fallback. End-to-end cases skip
automatically if `ffmpeg` / `ffprobe` are absent.

## Manifests & pad maps

Every bank exported by these tools writes two extra files alongside the
WAVs:

```text
Roland TR-808/
  01_empty.wav … 16_open_hh.wav
  manifest.json    ← machine-readable record of what landed on each pad
  pad-map.html     ← static 4×4 grid, opens in a browser with <audio> tags
```

`manifest.json` (one entry per pad):

```json
{
  "manifest_version": 1,
  "kit_name": "Roland TR-808",
  "generated_at": 1717000000,
  "meta": {"kind": "drumkit", "filled": 12, "empty": 0},
  "pads": [
    {
      "pad": 13,
      "filename": "13_kick.wav",
      "type": "kick",
      "source": "~/Samples/Roland TR-808.zip#BD0000.WAV",
      "source_basename": "BD0000.WAV",
      "kind": "auto",
      "sha256": "…",
      "duration_s": 0.42,
      "sample_rate": 48000,
      "channels": 1
    }
  ]
}
```

The `kind` field on a pad tells you how it got there:

- `auto` — chosen by the classifier
- `swap` — replaced by `swap_pad.py`
- `silent` — placeholder
- `fail` — ffmpeg failed (rare; check stderr)

`pad-map.html` is a single static page — no server needed. Open it in
Finder, click play on any pad to audition. Colored by type, source
filename shown under each pad, duration on the bottom row.

The manifest is the source of truth: `rebuild_kit.py`, `swap_pad.py`,
and `make_kit_from_crate.py --from-kit` all read it back.

## Crates

A crate is a small JSON file describing the intent for one bank:

```json
{
  "name": "Bedroom Kit",
  "kind": "drumkit",
  "pads": [
    {"pad": 13, "source": "/samples/909_kick_03.wav",   "type": "kick"},
    {"pad": 14, "source": "/samples/Linn_snare.wav",    "type": "snare"},
    {"pad": 15, "source": "/samples/707_closedhat.wav", "type": "closed_hh"},
    {"pad": 16, "source": "/samples/626_openhat.wav",   "type": "open_hh"}
  ]
}
```

Supported `kind` values: `drumkit`, `loop_bank`, `block`, `super`.
Pads not listed get silent placeholders (for `drumkit` and `loop_bank`).
Missing source files become silent placeholders with a warning rather
than aborting.

Hand-curation flow:

```bash
# Dump a machine-built kit as an editable crate
python3 make_kit_from_crate.py --from-kit drumkit/Roland_TR-808 \
  --out 808.crate.json

# Edit 808.crate.json in any text editor:
#   - swap a pad's `source` to your favorite kick
#   - change `name` so the output folder is distinct
#   - delete pads you don't want (they'll go silent)

# Build the curated kit
python3 make_kit_from_crate.py 808.crate.json ~/Music/SP_EXPORT
```

Crates are checkable into git — they're the record of a curated kit
that's small enough to share or version.

## Troubleshooting

### Web UI

- **`ModuleNotFoundError: No module named 'fastapi'`** — install deps:
  `pip install -r requirements.txt`.
- **`ffmpeg` failures during swap / build** — set `FFMPEG_PATH` and
  `FFPROBE_PATH` to the binaries you want, or put them on `PATH`. The
  `/settings` page shows the resolved paths and an availability check.
- **Audio doesn't play in the browser** — your browser must support
  WAV (all modern ones do). The audio routes are `/audio/kit/...` and
  `/audio/sample?path=...` and only serve files under the configured
  roots.

### Desktop app

- **"padwright-server sidecar not found"** at `cargo tauri dev` —
  re-run `pyinstaller --clean pyinstaller_app.spec && node
  scripts/install_sidecar.mjs`. Verify
  `src-tauri/binaries/padwright-server-<triple>` exists.
- **Window stays on the loading screen** — open devtools
  (right-click → Inspect) and look at the terminal log for
  `[padwright-server]` lines. Common causes:
  - PyInstaller missed a hidden import (e.g., `multipart`,
    `anyio._backends._asyncio`). Add it to `hiddenimports` in
    `pyinstaller_app.spec` and re-bundle.
  - The sidecar's `PADWRIGHT_PORT=…` line never printed (probably an
    earlier Python traceback above it in the log).
- **macOS "app is damaged" Gatekeeper error** on the bundle — the
  `.app` isn't signed/notarized. For personal use, right-click →
  Open the first time. For sharing, see
  [Signing & notarization](#signing--notarization-macos-optional).
- **"proxy error: Connection refused"** in devtools — the Rust
  proxy reached the sidecar before uvicorn finished binding. The
  current code retries for ~3s; if you still see it, the sidecar is
  actually failing to start — check `[padwright-server]` logs.

### CLI

- **`PermissionError: /tmp/sp404…`** — your `/tmp` has stale files
  from a prior run with different perms. The scripts honor `TMPDIR`,
  so `export TMPDIR=$HOME/.tmp` works; or just `rm /tmp/sp404_*.wav`.
- **`make_kits.py` skips a kit that "already built"** — that's the
  resume behavior. Delete the kit folder or pass a different
  `--dst` to force a rebuild.
- **Numeric-only packs (CR78, Linndrum) classify as "synth-spread"**
  — expected; filename classifier has nothing to go on. Use a crate
  to hand-curate.

## Before a release

A short hand-checklist before pushing a `v*.*.*` tag. CI catches most of
this but it's faster to fail locally.

- [ ] Tests green locally: `pip install -r requirements.txt -r requirements-dev.txt && python tests.py`
- [ ] `cargo check --manifest-path src-tauri/Cargo.toml` clean
- [ ] Versions match in `package.json`, `src-tauri/Cargo.toml`,
      `src-tauri/tauri.conf.json`
- [ ] `CHANGELOG.md` has a new `## [x.y.z] - YYYY-MM-DD` entry above
      `## [Unreleased]`
- [ ] `LICENSE` and `NOTICE` present (they should be — Apache-2.0
      shipped in v1.0.0)
- [ ] Source icon committed at `src-tauri/icons/` (or the placeholder
      generator will run in CI)
- [ ] Lockfiles up to date: `package-lock.json`, `src-tauri/Cargo.lock`
- [ ] No personal paths in any committed file (`grep -rn '/Users/\|/Volumes/'`
      should return nothing in `.md`, `.json`, `.toml`, `.yml`, `.rs`,
      `.py` files)

After pushing the tag:

- [ ] All 4 matrix jobs green (Actions tab)
- [ ] Draft release inspected: title, body (rendered from
      `CHANGELOG.md`), all 4 bundles attached
- [ ] One platform installed end-to-end and a kit built through the UI
- [ ] Release published

## License

Code in this repository is licensed under the
**[Apache License, Version 2.0](LICENSE)**.
Copyright 2026 Padwright contributors. See `NOTICE` for attributions.

A few specifics that aren't covered by the boilerplate:

- **Padwright name and branding** are not licensed for misleading reuse.
  The Apache License explicitly carves trademarks out of its grant
  (Section 6). Forks, derivatives, and modified distributions must use
  a different product name and identifier — keep your fork's identity
  distinct from the upstream so users don't get confused.
- **User-provided audio** (samples, packs, exported banks) remains the
  responsibility of the rights holder. Padwright is a tool; what you
  feed it and what you redistribute is on you.
- **Bundled `ffmpeg` / `ffprobe`** in the desktop releases are
  third-party LGPL builds from the FFmpeg project, not part of the
  Padwright source. They retain their own license. See `NOTICE`.
- **Bundled Python runtime** ships under the Python Software Foundation
  license. See `NOTICE`.

## What's still rough

- **Classifier is filename-only.** Numeric-only packs (CR78, Linndrum,
  EMU Drumulator-style "01.wav … 14.wav") still get the "spread evenly
  across 12 slots" fallback. Real audio-feature classification (spectral
  kick/snare detection) is a large undertaking and would only help a
  minority of packs. The crate workflow is the answer for these packs.
- **BPM detection for loop banks isn't done yet.** The new duration
  heuristic catches "is this a loop" but doesn't compute tempo. ffprobe
  duration + filename pattern matching would be the next step.
- **No SD-card writer.** A `copy-to-import` command would just be a
  `cp -R`; not worth a script until you find yourself doing it daily.
- **Bundles aren't code-signed yet.** First-launch warnings on Mac
  (Gatekeeper) and Windows (SmartScreen) are inherent to unsigned apps.
  Workaround per-user: right-click → Open on Mac, "More info" → "Run
  anyway" on Windows. Permanent fix: $99/year Apple Developer + ~$200/year
  Windows CA cert, dropped into GitHub Actions secrets — see
  [Adding code signing later](#adding-code-signing-later-optional).
- **Auto-update for the desktop app isn't wired up** (Tauri supports it
  via the updater plugin; defer until there's a v1.1).
- **macOS universal binary not produced** — Mac users on Intel and Apple
  Silicon download separate `.dmg`s. CI builds both. A `lipo` step
  could merge them; skipped for now.

## Direction

Keep this repo focused on the last-mile pipeline:

```text
big sample library → discovery (external) → Padwright → SP-ready banks → SP-404MKII
```

Padwright covers `scan / classify / export / manifest / audition / swap /
crate / audit`. Discovery (which file is the right kick?) lives elsewhere.
The desktop app's job is to make the last-mile prep fast enough that you
don't dread it.
