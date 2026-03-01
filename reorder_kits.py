#!/usr/bin/env python3
"""
Reorder SP-404 MK2 kit files so drag-and-drop lands correctly.

The Roland app fills pads top-left → right → down (pad 13 first, pad 1 last).
We rename files so kick/snare/hats end up on the BOTTOM ROW (pads 1-4),
and add 4 silent WAV placeholders for the TOP ROW (pads 13-16).

Result layout on device:
  [01_empty][02_empty][03_empty][04_empty]  ← top row  (pad 13-16, silent)
  [05_rim  ][06_clap ][07_cowbl][08_perc ]  ← row 3    (pad  9-12)
  [09_lo_tm][10_md_tm][11_hi_tm][12_crash]  ← row 2    (pad  5-8 )
  [13_kick ][14_snare][15_cl_hh][16_op_hh]  ← bottom   (pad  1-4 ) ← kick ✓
"""

import os
import struct
import shutil
import wave

KITS_DIR = "/Volumes/eight/MUSIC_PRODUCTION/SAMPLES_SP404MK2"
SILENT_WAV = "/tmp/sp404_empty.wav"

# Old prefix → New prefix  (for files named NN_name.wav)
REMAP = {
    "01": "13",   # kick      → pad 1  (bottom-left)
    "02": "14",   # snare     → pad 2
    "03": "15",   # closed_hh → pad 3
    "04": "16",   # open_hh   → pad 4
    "05": "09",   # low_tom   → pad 5
    "06": "10",   # mid_tom   → pad 6
    "07": "11",   # hi_tom    → pad 7
    "08": "12",   # crash     → pad 8
    "09": "05",   # rim       → pad 9
    "10": "06",   # clap      → pad 10
    "11": "07",   # cowbell   → pad 11
    "12": "08",   # perc      → pad 12
}


def make_silent_wav(path, duration_sec=0.05, sr=48000):
    """Write a minimal silent 16-bit mono WAV."""
    n_samples = int(sr * duration_sec)
    with wave.open(path, 'w') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(b'\x00' * n_samples * 2)


def reorder_kit(kit_dir):
    files = [f for f in os.listdir(kit_dir)
             if f.endswith('.wav') and not f.startswith('.')]

    # ── Step 1: rename to temp names to avoid collisions ──────────────────────
    temp_map = {}   # tempname → final name
    for fname in files:
        prefix = fname[:2]
        if prefix in REMAP:
            new_prefix = REMAP[prefix]
            new_name = new_prefix + fname[2:]   # keep _name.wav suffix
            tmp_name = "TMP_" + fname
            os.rename(os.path.join(kit_dir, fname),
                      os.path.join(kit_dir, tmp_name))
            temp_map[tmp_name] = new_name

    # ── Step 2: rename temp names to final names ───────────────────────────────
    for tmp_name, final_name in temp_map.items():
        os.rename(os.path.join(kit_dir, tmp_name),
                  os.path.join(kit_dir, final_name))

    # ── Step 3: add 4 silent placeholder files (top row) ──────────────────────
    for i in range(1, 5):
        dst = os.path.join(kit_dir, f"0{i}_empty.wav")
        if not os.path.exists(dst):
            shutil.copy(SILENT_WAV, dst)

    renamed = len(temp_map)
    print(f"  {os.path.basename(kit_dir)}: {renamed} files renamed, 4 silent pads added")
    return renamed


def find_kit_dirs(base):
    """Recursively find all leaf dirs containing WAV files (kit dirs).
    Skips dirs that already have 01_empty.wav (already reordered)."""
    kit_dirs = []
    for root, dirs, files in os.walk(base):
        wavs = [f for f in files if f.endswith('.wav') and not f.startswith('.')]
        if wavs and '01_empty.wav' not in files:
            kit_dirs.append(root)
    return sorted(kit_dirs)


def main():
    print("Generating silent WAV placeholder...")
    make_silent_wav(SILENT_WAV)

    kit_dirs = find_kit_dirs(KITS_DIR)

    print(f"Found {len(kit_dirs)} unprocessed kits under {KITS_DIR}\n")
    total = 0
    for kit_dir in kit_dirs:
        total += reorder_kit(kit_dir)

    print(f"\nDone — {total} files renamed across {len(kit_dirs)} kits.")
    print("Each kit now has 16 files: 4 silent (top row) + 12 sounds (rows 1-3 from bottom).")


if __name__ == "__main__":
    main()
