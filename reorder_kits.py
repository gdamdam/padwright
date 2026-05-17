#!/usr/bin/env python3
"""
Reorder SP-404MKII kit files so drag-and-drop lands correctly.

The Roland app fills pads top-left → right → down (pad 13 first, pad 1 last).
We rename files so kick/snare/hats end up on the BOTTOM ROW (pads 1-4),
and add 4 silent WAV placeholders for the TOP ROW (pads 13-16).

Result layout on device (file number = pad number):
  [01_empty][02_empty][03_empty][04_empty]  ← top row   (pads  1-4,  silent)
  [05_rim  ][06_clap ][07_cowbl][08_perc ]  ← row 2     (pads  5-8 )
  [09_lo_tm][10_md_tm][11_hi_tm][12_crash]  ← row 3     (pads  9-12)
  [13_kick ][14_snare][15_cl_hh][16_op_hh]  ← bottom    (pads 13-16) ← kick ✓
"""

import argparse
import os
import shutil
import tempfile

from sp404_core import make_silent_wav

DEFAULT_KITS_DIR = "/Volumes/eight/MUSIC_PRODUCTION/SAMPLES_SP404MK2"
SILENT_WAV = os.path.join(tempfile.gettempdir(), "sp404_empty.wav")

# Old prefix → New prefix  (for files named NN_name.wav)
REMAP = {
    "01": "13",   # kick      → pad 13 (bottom-left)
    "02": "14",   # snare     → pad 14
    "03": "15",   # closed_hh → pad 15
    "04": "16",   # open_hh   → pad 16
    "05": "09",   # low_tom   → pad 9
    "06": "10",   # mid_tom   → pad 10
    "07": "11",   # hi_tom    → pad 11
    "08": "12",   # crash     → pad 12
    "09": "05",   # rim       → pad 5
    "10": "06",   # clap      → pad 6
    "11": "07",   # cowbell   → pad 7
    "12": "08",   # perc      → pad 8
}


def reorder_kit(kit_dir, dst_dir=None, dry_run=False):
    """
    Reorder a kit in-place, or write the reordered copy under dst_dir.

    When dst_dir is None: rename in place.
    When dst_dir is given: copy each source file to dst_dir/<basename(kit_dir)>/
    under its new name (original kit is left untouched).
    """
    files = [f for f in os.listdir(kit_dir)
             if f.endswith('.wav') and not f.startswith('.')]

    rename_plan = []   # list of (old_name, new_name)
    for fname in files:
        prefix = fname[:2]
        if prefix in REMAP:
            new_prefix = REMAP[prefix]
            new_name = new_prefix + fname[2:]   # keep _name.wav suffix
            rename_plan.append((fname, new_name))

    target_dir = (os.path.join(dst_dir, os.path.basename(kit_dir))
                  if dst_dir else kit_dir)

    if dry_run:
        print(f"  {os.path.basename(kit_dir)}: would rename "
              f"{len(rename_plan)}, add 4 silent → {target_dir}")
        for old, new in rename_plan:
            print(f"    {old} → {new}")
        return len(rename_plan)

    if dst_dir:
        os.makedirs(target_dir, exist_ok=True)
        # Copy renamed files
        for old, new in rename_plan:
            shutil.copy2(os.path.join(kit_dir, old),
                         os.path.join(target_dir, new))
    else:
        # In-place rename via temp names to avoid collisions
        temp_map = {}
        for old, new in rename_plan:
            tmp_name = "TMP_" + old
            os.rename(os.path.join(kit_dir, old),
                      os.path.join(kit_dir, tmp_name))
            temp_map[tmp_name] = new
        for tmp_name, final_name in temp_map.items():
            os.rename(os.path.join(kit_dir, tmp_name),
                      os.path.join(kit_dir, final_name))

    # Add silent top-row placeholders
    for i in range(1, 5):
        dst = os.path.join(target_dir, f"0{i}_empty.wav")
        if not os.path.exists(dst):
            shutil.copy(SILENT_WAV, dst)

    print(f"  {os.path.basename(kit_dir)}: {len(rename_plan)} files "
          f"renamed, 4 silent pads added")
    return len(rename_plan)


def find_kit_dirs(base):
    """Recursively find all leaf dirs containing WAV files (kit dirs).
    Skips dirs that already have 01_empty.wav (already reordered)."""
    kit_dirs = []
    for root, dirs, files in os.walk(base):
        wavs = [f for f in files if f.endswith('.wav') and not f.startswith('.')]
        if wavs and '01_empty.wav' not in files:
            kit_dirs.append(root)
    return sorted(kit_dirs)


HELP = """\
reorder_kits.py — Reorder SP-404MKII kit files for correct drag-and-drop placement.

The Roland SP-404MKII app fills pads top-left → right → down (pad 13 first,
pad 1 last). This script renames files so kick/snare/hats land on the BOTTOM
ROW (pads 1-4) and adds 4 silent WAV placeholders for the TOP ROW (pads 13-16).

Use this on kits that were NOT built by make_kits.py (which already applies this
layout). Kits that already have 01_empty.wav are skipped automatically.

Default input : /Volumes/eight/MUSIC_PRODUCTION/SAMPLES_SP404MK2/

Remapping applied (file number = pad number after rename):
  01_kick.wav      → 13_kick.wav      (pad 13, bottom-left)
  02_snare.wav     → 14_snare.wav     (pad 14)
  03_closed_hh.wav → 15_closed_hh.wav (pad 15)
  04_open_hh.wav   → 16_open_hh.wav   (pad 16)
  05_low_tom.wav   → 09_low_tom.wav   (pad 9)
  06_mid_tom.wav   → 10_mid_tom.wav   (pad 10)
  07_hi_tom.wav    → 11_hi_tom.wav    (pad 11)
  08_crash.wav     → 12_crash.wav     (pad 12)
  09_rim.wav       → 05_rim.wav       (pad 5)
  10_clap.wav      → 06_clap.wav      (pad 6)
  11_cowbell.wav   → 07_cowbell.wav   (pad 7)
  12_perc.wav      → 08_perc.wav      (pad 8)

After renaming, 4 silent placeholders are added:
  01_empty.wav → pad 1  (top-left, silent)
  02_empty.wav → pad 2
  03_empty.wav → pad 3
  04_empty.wav → pad 4  (top-right, silent)

Usage:
  python reorder_kits.py                          process default dir in-place
  python reorder_kits.py --src /path/to/kits      process custom source in-place
  python reorder_kits.py --src SRC --dst DST      copy reordered kits to DST
  python reorder_kits.py --dry-run                preview without modifying
  python reorder_kits.py --help                   show this message
"""


def main():
    parser = argparse.ArgumentParser(
        add_help=False, usage="reorder_kits.py [--src SRC] [--dst DST] [--dry-run] [--help]")
    parser.add_argument("--src", default=DEFAULT_KITS_DIR)
    parser.add_argument("--dst", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--help", "-h", action="store_true")
    args = parser.parse_args()

    if args.help:
        print(HELP)
        return

    print("Generating silent WAV placeholder...")
    make_silent_wav(SILENT_WAV)

    kit_dirs = find_kit_dirs(args.src)

    mode = "DRY RUN" if args.dry_run else ("COPY" if args.dst else "IN-PLACE")
    print(f"Source : {args.src}")
    if args.dst:
        print(f"Output : {args.dst}")
    print(f"Mode   : {mode}")
    print(f"Found {len(kit_dirs)} unprocessed kits\n")

    if args.dst and not args.dry_run:
        os.makedirs(args.dst, exist_ok=True)

    total = 0
    for kit_dir in kit_dirs:
        total += reorder_kit(kit_dir, dst_dir=args.dst, dry_run=args.dry_run)

    suffix = " (dry run — nothing written)" if args.dry_run else ""
    print(f"\nDone — {total} files renamed across {len(kit_dirs)} kits.{suffix}")


if __name__ == "__main__":
    main()
