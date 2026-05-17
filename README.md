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

## Three ways to use it

1. **Desktop app** (`.app` / `.dmg` / `.msi`). Double-click, set folders
   in Settings, drag samples onto pads. See `md/BUILD.md` to build.
2. **Local web UI** — `pip install -r requirements.txt && python -m web.app`.
   Same UI, no install, runs in your default browser at `localhost:<port>`.
3. **CLI tools** — `make_kits.py`, `make_breakbeats.py`, `swap_pad.py`,
   `rebuild_kit.py`, `make_kit_from_crate.py`, `audit_kits.py`,
   `reorder_kits.py`. Scriptable, batch-friendly, no GUI deps.

## Requirements

- Python 3.11+ (uses `X | Y` type hints)
- `ffmpeg` and `ffprobe` on `PATH`
- A source folder of `.zip` packs, unzipped pack folders, or loose audio
- The Roland SP-404MKII app for final drag-and-drop

Output WAV formats:

- Drum kits (`make_kits.py`): `48 kHz / 16-bit / mono`
- Loop banks (`make_breakbeats.py`): `48 kHz / 16-bit / stereo`
- Silent placeholder pads: short `48 kHz / 16-bit / mono` WAVs

## Pad Layout

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

## Scripts

### `make_kits.py` — batch drum-kit builder

Scans a source of `.zip` packs (or unzipped folders), classifies audio
files by drum type, picks one representative per slot, exports a 16-pad
kit per pack, and writes per-kit manifests + pad maps.

```bash
cd /Users/gio/dev/music/sp404mk2

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
  --src /Users/gio/dev/music/SAMPLES \
  --dst /Users/gio/dev/music/SP404MK2_EXPORT
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

### Desktop app (Tauri)

The same web UI can be packaged as a double-clickable desktop app
(`.dmg` on macOS, `.msi` on Windows, `.AppImage`/`.deb` on Linux)
that bundles the Python runtime and ffmpeg inside. End users don't
need Python, pip, or a terminal. See `md/BUILD.md` for the full build
recipe. Scaffold lives in `src-tauri/`.

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
(see `md/BUILD.md`) can ship its own ffmpeg binaries.

### `audit_kits.py` — find duplicate pads across a built tree

Walks a destination directory, reads every `manifest.json`, groups pad
entries by sha256. Catches cases where two kits picked the same source
file. Super-bank entries are duplicates of drumkit pads by design — pass
`--exclude-super` to filter them out.

```bash
python3 audit_kits.py /Volumes/eight/SP_EXPORT
python3 audit_kits.py /Volumes/eight/SP_EXPORT --exclude-super
python3 audit_kits.py /Volumes/eight/SP_EXPORT --by-source   # group by source path
python3 audit_kits.py /Volumes/eight/SP_EXPORT --json        # machine-readable
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
      "source": "/Volumes/eight/ff/Roland TR-808.zip/BD0000.WAV",
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
python3 make_kit_from_crate.py 808.crate.json /Volumes/eight/SP_EXPORT
```

Crates are checkable into git — they're the record of a curated kit
that's small enough to share or version.

## Recommended workflow today

```bash
cd /Users/gio/dev/music/sp404mk2

# 1. Dry-run scan of your source folder
python3 make_kits.py --dry-run --unzipped \
  --src /Users/gio/dev/music/SAMPLES \
  --dst /Users/gio/dev/music/SP404MK2_EXPORT

# 2. If the classification breakdown looks reasonable, build for real
python3 make_kits.py --unzipped \
  --src /Users/gio/dev/music/SAMPLES \
  --dst /Users/gio/dev/music/SP404MK2_EXPORT

# 3. Open the pad map for any kit and audition it
open /Users/gio/dev/music/SP404MK2_EXPORT/drumkit/SomeKit/pad-map.html

# 4. Swap any pad that didn't pick a great representative
python3 swap_pad.py \
  /Users/gio/dev/music/SP404MK2_EXPORT/drumkit/SomeKit \
  13 \
  /path/to/better_kick.wav

# 5. Drag the 16 WAV files into the Roland SP-404MKII app
```

For hand-curated kits, skip steps 1–4 and write a crate directly:

```bash
python3 make_kit_from_crate.py my.crate.json /Volumes/eight/SP_EXPORT
```

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
- **Auto-update for the desktop app isn't wired up** (Tauri supports it
  via the updater plugin; defer until there's a v1.1).

## Direction

Keep this repo focused on the last-mile pipeline:

```text
big sample library → discovery (external) → Padwright → SP-ready banks → SP-404MKII
```

Padwright covers `scan / classify / export / manifest / audition / swap /
crate / audit`. Discovery (which file is the right kick?) lives elsewhere.
The desktop app's job is to make the last-mile prep fast enough that you
don't dread it.
