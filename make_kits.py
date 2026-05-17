#!/usr/bin/env python3
"""
make_kits_ff.py — Build SP-404MKII drum kits from the ff archive.

Source : ~/Music/Samples/*.zip   (drum machine sample packs)
Output : ~/Music/SP_EXPORT/
  drumkit/  — one curated 16-pad kit per machine (all 470 zips)
  blocks/   — per-type 16-pad banks for monster kits (≥100 audio files)
  super/    — cross-machine "best-of" themed banks (kicks, snares, hats…)

Audio format : 16-bit / 48 kHz / mono WAV  (matches existing SP-404MK2 kits)

Pad layout (drag-and-drop ready — already pre-reordered like reorder_kits.py):
  File 01-04 → silent pads   → pads 1-4   (top row, empty)
  File 05 rim       → pad 5     File 13 kick      → pad 13 ✓
  File 06 clap      → pad 6     File 14 snare     → pad 14
  File 07 cowbell   → pad 7     File 15 closed_hh → pad 15
  File 08 perc      → pad 8     File 16 open_hh   → pad 16
  File 09 low_tom   → pad 9
  File 10 mid_tom   → pad 10
  File 11 hi_tom    → pad 11
  File 12 crash     → pad 12

Tier logic:
  Tier 1 (≤16 files)  : extract all sounds, classify each to its slot
  Tier 2 (17-99 files): pick one best-per-type (middle of sorted candidates)
  Tier 4 (≥100 files) : same as Tier 2 + also build per-type category blocks

Usage:
  python make_kits_ff.py                   # build all
  python make_kits_ff.py --dry-run         # scan only, no file output
  python make_kits_ff.py --status          # count built vs total, then exit
  python make_kits_ff.py --batch 1         # only batch 1 (4,A,B — 58 kits)
  python make_kits_ff.py --batch 2         # batch 2 (C,D,E — 89 kits)
  python make_kits_ff.py --batch 3         # batch 3 (F–L — 95 kits)
  python make_kits_ff.py --batch 4         # batch 4 (M–R — 104 kits)
  python make_kits_ff.py --batch 5         # batch 5 (S–W — 57 kits)
  python make_kits_ff.py --batch 6         # batch 6 (Y,Z — 67 kits)
  python make_kits_ff.py Roland Boss       # only zips matching any filter word
  # Super banks only (after all batches done):
  python make_kits_ff.py --super-only
  # Override source / destination:
  python make_kits_ff.py --src /path/to/packs --dst /path/to/output
  # Source can be a folder of .zip files OR a folder of unzipped subdirectories
"""

import os, sys, shutil, tempfile
from pathlib import Path
from collections import defaultdict

_TMP = tempfile.gettempdir()

from sp404_core import (
    SOUND_SLOTS, SLOT_NAMES, SUPER_FILES,
    KIND_DRUMKIT,
    classify, pick_file, export, make_silent_wav,
    list_audio, extract_audio, sanitize, ffprobe_info, sha256_file,
    write_manifest, write_pad_map, build_from_pad_list, UI,
)

# ── Paths ──────────────────────────────────────────────────────────────────────
SRC_DIR    = Path.home() / "Music" / "Samples"
DST_DIR    = Path.home() / "Music" / "SP_EXPORT"
SILENT_WAV = os.path.join(_TMP, "sp404mk2_ff_empty.wav")

TIER_BLOCK = 100  # ≥ this many audio files → also build category blocks

# Batch letter ranges (first char of machine name, lowercased)
BATCHES = {
    1: set("4ab"),
    2: set("cde"),
    3: set("fghjkl"),
    4: set("mnopqr"),
    5: set("stuvw"),
    6: set("yz"),
}


# ── Kit builder ────────────────────────────────────────────────────────────────

def build_kit(audio_files, kit_dir, dry_run, ui=None, source_map=None):
    """
    Classify files, pick one per slot, export a full 16-pad kit.

    All 16 WAV files are always written — silent placeholder for any slot
    that has no matching sound, so drag-and-drop always loads 16 pads.

    Filling priority (drum kits):
      1. One best-per-type to its designated slot (kick→13, snare→14 …)
      2. Generic "tom" names → lowest empty tom slot
      3. Any remaining unclassified sounds → remaining empty slots
      4. Still-empty slots → silent placeholder WAV

    Non-drum / synth kits: sounds spread evenly across all 12 slots.

    Returns dict of type → chosen_src_path (for super bank collection).
    """
    buckets = defaultdict(list)
    unclassified = []
    for f in audio_files:
        t = classify(f)
        (buckets[t] if t else unclassified).append(f)

    is_drum = bool(buckets)
    assignments = {}  # slot_type → abs_src_path

    if is_drum:
        # Pass 1: best representative per classified type
        for slot_type in SLOT_NAMES:
            chosen = pick_file(buckets.get(slot_type, []))
            if chosen:
                assignments[slot_type] = chosen

        # Pass 2: generic "tom" names → lowest empty tom slot
        for ts in ["low_tom", "mid_tom", "hi_tom"]:
            if ts not in assignments:
                tom_cands = [f for f in unclassified
                             if "tom" in os.path.basename(f).lower()]
                if tom_cands:
                    chosen = tom_cands[0]
                    assignments[ts] = chosen
                    unclassified.remove(chosen)

        # Pass 3: fill remaining empty slots with unclassified sounds
        for slot_type in SLOT_NAMES:
            if slot_type not in assignments and unclassified:
                assignments[slot_type] = unclassified.pop(0)

    else:
        # Non-drum / synth: spread evenly across all 12 sound slots
        files = sorted(audio_files)
        if len(files) > len(SLOT_NAMES):
            step = len(files) / len(SLOT_NAMES)
            files = [files[int(i * step)] for i in range(len(SLOT_NAMES))]
        for slot_type, f in zip(SLOT_NAMES, files):
            assignments[slot_type] = f

    filled   = len(assignments)
    empty    = len(SLOT_NAMES) - filled
    tag      = "(drum)" if is_drum else "(synth-spread)"

    if dry_run:
        print(f"    {filled:2d}/12 filled  {empty} silent  {tag}")
        return assignments

    # Convert assignments → pad_specs for the shared exporter.
    # `source` is the original (for the manifest); `export_source` is the
    # temp-extracted path that ffmpeg actually reads (zips and unzipped
    # both extract to a temp dir before classification).
    src_lookup = (lambda f: source_map.get(f, f)) if source_map else (lambda f: f)
    slot_to_pad = {slot_type: pad_num for pad_num, slot_type in SOUND_SLOTS}
    pad_specs = []
    for slot_type, extracted in assignments.items():
        pad_specs.append({
            "pad": slot_to_pad[slot_type],
            "source": src_lookup(extracted),
            "export_source": extracted,
            "type": slot_type,
        })

    # Preserve the existing "synth-spread" tag in the manifest meta.
    meta_extra = {"filled": filled, "empty": empty}
    if not is_drum:
        meta_extra["kind"] = "synth-spread"

    def _ui_tick(pad_dict):
        # Original build_kit pulsed the UI for each of the 16 slots
        # (including silent ones). build_from_pad_list calls on_pad_done
        # once per pad in pad_range, matching that behavior.
        if ui:
            ui.update(pad_dict.get("type") or "")

    build_from_pad_list(
        kit_dir, pad_specs,
        kind=KIND_DRUMKIT,
        meta_extra=meta_extra,
        silent_wav_path=SILENT_WAV,
        on_pad_done=_ui_tick,
    )

    return assignments


# ── Category blocks (monster kits) ────────────────────────────────────────────

def build_blocks(audio_files, machine_name, blocks_dir, dry_run, source_map=None):
    """
    Build per-type 16-pad banks for monster kits (≥100 files).
    Each block: up to 16 sounds of the same category, evenly sampled.
    """
    buckets = defaultdict(list)
    for f in audio_files:
        t = classify(f)
        if t:
            buckets[t].append(f)

    groups = {
        "KICKS":  sorted(buckets.get("kick", [])),
        "SNARES": sorted(buckets.get("snare", [])),
        "HATS":   sorted(buckets.get("closed_hh", []) + buckets.get("open_hh", [])),
        "TOMS":   sorted(buckets.get("low_tom", []) + buckets.get("mid_tom", []) +
                         buckets.get("hi_tom", [])),
        "CLAPS":  sorted(buckets.get("clap", [])),
        "PERC":   sorted(buckets.get("perc", []) + buckets.get("rim", []) +
                         buckets.get("cowbell", []) + buckets.get("crash", [])),
    }

    pfx = sanitize(machine_name, 14)

    for block_name, files in groups.items():
        if not files:
            continue
        # Evenly sample down to 16 if needed
        if len(files) > 16:
            step = len(files) / 16
            files = [files[int(i * step)] for i in range(16)]

        block_dir = os.path.join(blocks_dir, machine_name, f"{pfx}_{block_name}")
        print(f"    BLOCK {block_name:<8} {len(files):2d} files → {os.path.basename(block_dir)}")

        if dry_run:
            continue

        os.makedirs(block_dir, exist_ok=True)
        pads: list[dict] = []
        src_lookup = (lambda f: source_map.get(f, f)) if source_map else (lambda f: f)
        for i, src in enumerate(files, 1):
            label = sanitize(Path(src).stem, 14)
            fname = f"{i:02d}_{label}.wav"
            dst = os.path.join(block_dir, fname)
            ok = export(src, dst)
            info = ffprobe_info(dst) if ok else {}
            orig = src_lookup(src)
            pads.append({
                "pad": i, "filename": fname,
                "type": block_name.lower(),
                "source": orig,
                "source_basename": os.path.basename(orig.split("#")[-1]),
                "kind": "auto" if ok else "fail",
                "sha256": sha256_file(dst) if ok else None,
                **info,
            })
        write_manifest(block_dir, pads, meta={"kind": "block",
                                              "machine": machine_name,
                                              "category": block_name})
        write_pad_map(block_dir, pads, meta={"kind": "block",
                                             "machine": machine_name,
                                             "category": block_name})


# ── Super banks ────────────────────────────────────────────────────────────────

def build_super_banks(super_data, super_dir, dry_run):
    """
    Build cross-machine themed banks from already-exported kit files.
    super_data: dict of type → [(machine_name, abs_path_to_exported_wav)]
    Each bank gets ≤16 machines, evenly sampled if more.
    """
    for bank_type, entries in super_data.items():
        if not entries:
            continue

        # Evenly sample to 16 machines
        if len(entries) > 16:
            step = len(entries) / 16
            entries = [entries[int(i * step)] for i in range(16)]

        bank_name = f"SUPER_{bank_type.upper()}"
        bank_dir  = os.path.join(super_dir, bank_name)
        print(f"\n  {bank_name}  ({len(entries)} machines)")

        if dry_run:
            for machine, _ in entries:
                print(f"    {machine}")
            continue

        os.makedirs(bank_dir, exist_ok=True)
        pads: list[dict] = []
        for i, (machine, src) in enumerate(entries, 1):
            label = sanitize(machine, 16)
            fname = f"{i:02d}_{label}.wav"
            dst   = os.path.join(bank_dir, fname)
            if os.path.exists(src):
                shutil.copy(src, dst)
                print(f"    {i:02d}_{label:<18} OK   {machine}")
                info = ffprobe_info(dst)
                pads.append({
                    "pad": i, "filename": fname, "type": bank_type,
                    "source": src, "source_basename": machine,
                    "kind": "auto",
                    "sha256": sha256_file(dst),
                    **info,
                })
            else:
                print(f"    {i:02d}_{label:<18} MISS {machine}")
                pads.append({
                    "pad": i, "filename": fname, "type": bank_type,
                    "source": src, "source_basename": machine,
                    "kind": "fail",
                })
        write_manifest(bank_dir, pads, meta={"kind": "super",
                                             "category": bank_type})
        write_pad_map(bank_dir, pads, meta={"kind": "super",
                                            "category": bank_type})


# ── Main ───────────────────────────────────────────────────────────────────────

def dry_run_kit(audio_names, machine):
    """Fast dry-run analysis using only file names (no extraction needed)."""
    buckets = defaultdict(list)
    unclassified = []
    for name in audio_names:
        t = classify(name)
        (buckets[t] if t else unclassified).append(name)
    is_drum = bool(buckets)
    if is_drum:
        filled = len(set(SLOT_NAMES) & set(buckets.keys()))
        # account for unclassified filling empty slots
        empty_slots = len(SLOT_NAMES) - filled
        from_unclassified = min(len(unclassified), empty_slots)
        filled += from_unclassified
    else:
        filled = min(len(audio_names), len(SLOT_NAMES))
    empty = len(SLOT_NAMES) - filled
    tag   = "(drum)" if is_drum else "(synth-spread)"
    print(f"    {filled:2d}/12 filled  {empty} silent  {tag}")
    return is_drum


def discover_packs(src_dir, use_unzipped=False):
    """Return source packs from zip archives or immediate subdirectories."""
    if not src_dir.exists():
        return []
    if use_unzipped:
        return sorted(
            p for p in src_dir.iterdir()
            if p.is_dir() and not p.name.startswith('.')
        )
    return sorted(src_dir.glob("*.zip"))


def show_status(src_dir=SRC_DIR, dst_dir=DST_DIR, use_unzipped=False):
    """Print how many kits are built vs total, then exit."""
    packs = discover_packs(src_dir, use_unzipped)
    total = len(packs)
    drumkit_dir = dst_dir / "drumkit"
    built = 0
    if drumkit_dir.exists():
        for pack in packs:
            kit = drumkit_dir / pack.stem
            if kit.is_dir() and any(f.suffix == '.wav' for f in kit.iterdir()):
                built += 1
    pct = built * 100 // total if total else 0
    print(f"Source : {src_dir}")
    print(f"Output : {dst_dir}")
    print(f"Status : {built}/{total} kits built ({pct}%)")
    print(f"Remaining : {total - built}")
    # Per-batch breakdown
    for batch_num, letters in BATCHES.items():
        batch_packs = [p for p in packs if p.stem[0].lower() in letters]
        b_built = sum(
            1 for pack in batch_packs
            if (drumkit_dir / pack.stem).is_dir()
            and any(f.suffix == '.wav' for f in (drumkit_dir / pack.stem).iterdir())
        ) if drumkit_dir.exists() else 0
        status = "✅" if b_built == len(batch_packs) and batch_packs else ("🔄" if b_built > 0 else "⬜")
        print(f"  Batch {batch_num}: {b_built:3d}/{len(batch_packs)} {status}")
    super_dir = dst_dir / "super"
    super_status = "✅" if super_dir.exists() and any(super_dir.iterdir()) else "⬜"
    print(f"  Super banks: {super_status}")


HELP = """\
make_kits.py — Build SP-404MKII drum kits from a sample pack archive.

Scans a source directory of .zip files (or unzipped subfolders), classifies
every audio file by drum type (kick, snare, hi-hat, etc.), picks one best
representative per slot, and exports a drag-and-drop-ready 16-pad kit for
each machine. Also builds per-category blocks for large packs and cross-
machine super banks after all kits are done.

Default source : ~/Music/Samples/
Default output : ~/Music/SP_EXPORT/

Pad layout (file number = pad number, top-left to bottom-right):
  01-04  silent  → pads 1-4   (top row, empty)
  05 rim          → pad 5     13 kick      → pad 13 ✓
  06 clap         → pad 6     14 snare     → pad 14
  07 cowbell      → pad 7     15 closed_hh → pad 15
  08 perc         → pad 8     16 open_hh   → pad 16
  09 low_tom      → pad 9
  10 mid_tom      → pad 10
  11 hi_tom       → pad 11
  12 crash        → pad 12

Output folders:
  drumkit/  — one 16-pad kit per pack (always 16 WAVs, silent fill for empty slots)
  blocks/   — per-category banks for packs with ≥100 audio files
  super/    — cross-pack themed banks: SUPER_KICK, SUPER_SNARE, etc.

Tier logic:
  ≤16 files   — all sounds used, classified to their slots
  17-99 files — one best-per-type (middle of sorted candidates)
  ≥100 files  — same + per-category blocks (kicks, snares, hats, toms, perc)

Usage:
  python make_kits.py                        build all packs
  python make_kits.py --dry-run              scan only, no file output
  python make_kits.py --status               show built vs total, then exit
  python make_kits.py --super-only           rebuild super banks from existing kits
  python make_kits.py --batch 1              batch 1 only (letters 4,A,B — 58 kits)
  python make_kits.py --batch 2              batch 2 (C,D,E — 89 kits)
  python make_kits.py --batch 3              batch 3 (F–L — 95 kits)
  python make_kits.py --batch 4              batch 4 (M–R — 104 kits)
  python make_kits.py --batch 5              batch 5 (S–W — 57 kits)
  python make_kits.py --batch 6              batch 6 (Y,Z — 67 kits)
  python make_kits.py Roland Boss            only packs matching any filter word
  python make_kits.py --src /path/to/packs   override source directory
  python make_kits.py --dst /path/to/output  override output directory
  python make_kits.py --unzipped             source contains unzipped subfolders
  python make_kits.py --help                 show this message

Re-running is safe — already-built kits are skipped automatically.
Audio output: 16-bit / 48 kHz / mono WAV.
"""


def main():
    if "--help" in sys.argv or "-h" in sys.argv:
        print(HELP)
        return

    dry_run    = "--dry-run"    in sys.argv
    super_only = "--super-only" in sys.argv
    status_only= "--status"     in sys.argv

    batch_num = None
    args = sys.argv[1:]
    for i, a in enumerate(args):
        if a == "--batch" and i + 1 < len(args):
            batch_num = int(args[i + 1])
            break
        if a.startswith("--batch="):
            batch_num = int(a.split("=", 1)[1])
            break

    # ── Resolve src / dst (CLI overrides defaults) ────────────────────────────
    src_dir = SRC_DIR
    dst_dir = DST_DIR
    for i, a in enumerate(args):
        if a == "--src" and i + 1 < len(args):
            src_dir = Path(args[i + 1])
        if a == "--dst" and i + 1 < len(args):
            dst_dir = Path(args[i + 1])

    use_unzipped = "--unzipped" in sys.argv

    if status_only:
        show_status(src_dir, dst_dir, use_unzipped)
        return

    filters = []
    skip_next = False
    for a in args:
        if skip_next:
            skip_next = False
            continue
        if a in ("--batch", "--src", "--dst"):
            skip_next = True
            continue
        if a.startswith("--batch="):
            continue
        if not a.startswith("--"):
            filters.append(a)

    # ── Discover packs: .zip files OR unzipped subdirectories ─────────────────
    # When both exist for the same stem, --unzipped picks dirs, default picks zips.
    packs = discover_packs(src_dir, use_unzipped)

    if batch_num is not None:
        letters = BATCHES.get(batch_num, set())
        packs = [p for p in packs if p.stem[0].lower() in letters]
    elif filters:
        packs = [p for p in packs if any(f.lower() in p.name.lower() for f in filters)]

    src_type = "unzipped folders" if use_unzipped else "zip archives"
    print(f"Source : {src_dir}  ({src_type})")
    print(f"Output : {dst_dir}")
    print(f"Packs  : {len(packs)}{f'  (batch {batch_num})' if batch_num else ''}")
    print(f"Mode   : {'DRY RUN' if dry_run else ('SUPER ONLY' if super_only else 'BUILD')}\n")

    ui = None if dry_run else UI(len(packs) * len(SOUND_SLOTS))

    if not dry_run:
        for sub in ("drumkit", "blocks", "super"):
            (dst_dir / sub).mkdir(parents=True, exist_ok=True)
        make_silent_wav(SILENT_WAV)

    super_data  = defaultdict(list)  # type → [(machine_name, abs_path)]
    total_ok    = 0
    total_skip  = 0
    dry_drum    = 0
    dry_synth   = 0

    # --super-only: collect from already-built kits then jump to super banks
    if super_only:
        drumkit_dir = dst_dir / "drumkit"
        if not drumkit_dir.exists():
            print(f"No existing drumkit folder found: {drumkit_dir}")
            return
        for kit_path in sorted(drumkit_dir.iterdir()):
            if not kit_path.is_dir():
                continue
            for stype, fname in SUPER_FILES.items():
                fpath = kit_path / fname
                if fpath.exists():
                    super_data[stype].append((kit_path.name, str(fpath)))
        print(f"Collected super data from existing kits:")
        for stype, entries in super_data.items():
            print(f"  {stype}: {len(entries)} machines")
        print()
        build_super_banks(super_data, str(dst_dir / "super"), dry_run=False)
        print("\nDone — super banks built.")
        return

    for pack in packs:
        machine = pack.stem

        if ui: ui.clear()

        try:
            audio_names = list_audio(pack)
        except Exception as e:
            print(f"[SKIP] {machine}: {e}")
            total_skip += 1
            if ui: ui.advance(len(SOUND_SLOTS), machine)
            continue

        n = len(audio_names)
        if n == 0:
            print(f"[SKIP] {machine}: no audio files")
            total_skip += 1
            if ui: ui.advance(len(SOUND_SLOTS), machine)
            continue

        tier = 1 if n <= 16 else (2 if n < TIER_BLOCK else 4)
        print(f"\n{'─' * 60}")
        print(f"  [{n:4d} files  T{tier}]  {machine}")

        if dry_run:
            is_drum = dry_run_kit(audio_names, machine)
            if is_drum:
                dry_drum += 1
            else:
                dry_synth += 1
            if tier == 4:
                # Show which blocks would be built
                buckets = defaultdict(list)
                for name in audio_names:
                    t = classify(name)
                    if t:
                        buckets[t].append(name)
                groups = {
                    "KICKS":  len(buckets.get("kick", [])),
                    "SNARES": len(buckets.get("snare", [])),
                    "HATS":   len(buckets.get("closed_hh", []) + buckets.get("open_hh", [])),
                    "TOMS":   len(buckets.get("low_tom", []) + buckets.get("mid_tom", []) +
                                  buckets.get("hi_tom", [])),
                    "CLAPS":  len(buckets.get("clap", [])),
                    "PERC":   len(buckets.get("perc", []) + buckets.get("rim", []) +
                                  buckets.get("cowbell", []) + buckets.get("crash", [])),
                }
                for bname, cnt in groups.items():
                    if cnt:
                        capped = min(cnt, 16)
                        print(f"    BLOCK {bname:<8} {capped:2d} files")
            total_ok += 1
            continue

        # ── Real build ────────────────────────────────────────────────────────
        kit_dir = str(dst_dir / "drumkit" / machine)

        # Skip already-built kits (resume support)
        if os.path.isdir(kit_dir) and any(
            f.endswith('.wav') for f in os.listdir(kit_dir)
        ):
            print(f"  [SKIP] already built — {machine}")
            # Still collect super bank files from existing kit
            for stype, fname in SUPER_FILES.items():
                fpath = os.path.join(kit_dir, fname)
                if os.path.exists(fpath):
                    super_data[stype].append((machine, fpath))
            total_ok += 1
            if ui: ui.advance(len(SOUND_SLOTS), machine)
            continue

        with tempfile.TemporaryDirectory() as tmp:
            try:
                audio_files, source_map = extract_audio(pack, tmp)
            except Exception as e:
                print(f"  [FAIL] extract: {e}")
                total_skip += 1
                if ui: ui.advance(len(SOUND_SLOTS), machine)
                continue

            build_kit(audio_files, kit_dir, dry_run=False, ui=ui,
                      source_map=source_map)

            if tier == 4:
                build_blocks(audio_files, machine,
                             str(dst_dir / "blocks"), dry_run=False,
                             source_map=source_map)

        # Collect already-exported files for super banks (temp dir is gone)
        for stype, fname in SUPER_FILES.items():
            fpath = os.path.join(kit_dir, fname)
            if os.path.exists(fpath):
                super_data[stype].append((machine, fpath))

        total_ok += 1

    if dry_run:
        print(f"\n{'═' * 60}")
        print(f"DRY RUN SUMMARY")
        print(f"  {total_ok} kits scanned  ({dry_drum} drum, {dry_synth} synth-spread)")
        print(f"  {total_skip} skipped")
        print(f"  Run without --dry-run to build.")
        return

    if ui: ui.finish()
    print(f"\n{'═' * 60}")
    print("BUILDING SUPER BANKS")
    print('═' * 60)
    build_super_banks(super_data, str(dst_dir / "super"), dry_run=False)

    print(f"\n{'═' * 60}")
    print(f"DONE — {total_ok} kits, {total_skip} skipped")
    print(f"Output : {dst_dir}")


if __name__ == "__main__":
    main()
