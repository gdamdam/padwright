#!/usr/bin/env python3
"""
swap_pad.py — Replace one pad in an already-built SP-404MKII bank.

The manifest written by make_kits.py / make_breakbeats.py is the source of
truth. This script re-exports a single pad from a new source file, updates
the manifest, and regenerates pad-map.html — without rebuilding the rest
of the bank.

Usage:
  python swap_pad.py <kit_dir> <pad_num> <new_source>
  python swap_pad.py <kit_dir> <pad_num> --silence
  python swap_pad.py <kit_dir> <pad_num> <new_source> --type kick
  python swap_pad.py <kit_dir> <pad_num> <new_source> --dry-run

The bank's manifest.json must already exist (build with make_kits.py or
make_breakbeats.py first). The pad's existing filename is reused so the
SP-404 import order doesn't change — only the WAV contents and the
manifest entry change.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

from sp404_core import (
    export, make_silent_wav, ffprobe_info, sha256_file,
    write_manifest, write_pad_map,
)

SILENT_WAV = os.path.join(tempfile.gettempdir(), "sp404_swap_empty.wav")


def load_manifest(kit_dir: Path) -> dict:
    mpath = kit_dir / "manifest.json"
    if not mpath.exists():
        print(f"error: no manifest.json in {kit_dir}", file=sys.stderr)
        print("       build the bank first with make_kits.py / make_breakbeats.py",
              file=sys.stderr)
        sys.exit(2)
    with open(mpath) as f:
        return json.load(f)


def channels_for(meta: dict) -> int:
    """loop_bank → stereo; everything else → mono (matches build defaults)."""
    return 2 if meta.get("kind") == "loop_bank" else 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("kit_dir", type=Path)
    parser.add_argument("pad", type=int, help="pad number 1..16")
    parser.add_argument("source", nargs="?",
                        help="new source audio file (or omit with --silence)")
    parser.add_argument("--silence", action="store_true",
                        help="replace pad with a silent placeholder")
    parser.add_argument("--type", default=None,
                        help="override pad type label (kick, snare, loop, …)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not (1 <= args.pad <= 16):
        parser.error("pad must be 1..16")
    if not args.silence and not args.source:
        parser.error("provide a source file or use --silence")
    if args.source and not Path(args.source).exists():
        parser.error(f"source not found: {args.source}")

    kit_dir = args.kit_dir
    if not kit_dir.is_dir():
        parser.error(f"kit dir not found: {kit_dir}")

    manifest = load_manifest(kit_dir)
    meta = manifest.get("meta") or {}
    pads = manifest.get("pads") or []

    by_pad = {entry.get("pad"): entry for entry in pads}
    entry = by_pad.get(args.pad)
    if not entry:
        parser.error(f"pad {args.pad} not present in manifest")

    fname = entry.get("filename")
    if not fname:
        p.error(f"pad {args.pad} manifest entry has no filename")
    dst = kit_dir / fname

    new_type = args.type or entry.get("type") or "loop"
    ch = channels_for(meta)

    if args.dry_run:
        action = "silence" if args.silence else f"export ({ch}ch) ← {args.source}"
        print(f"[dry-run] pad {args.pad:02d} ({fname}): {action}, type='{new_type}'")
        return

    # Replace audio
    if args.silence:
        make_silent_wav(SILENT_WAV)
        shutil.copy(SILENT_WAV, dst)
        new_entry = {
            "pad": args.pad, "filename": fname, "type": "empty",
            "source": None, "source_basename": None,
            "kind": "silent",
        }
        print(f"pad {args.pad:02d} ({fname}): replaced with silence")
    else:
        ok = export(args.source, str(dst), channels=ch)
        if not ok:
            print(f"error: ffmpeg failed for {args.source}", file=sys.stderr)
            sys.exit(1)
        info = ffprobe_info(dst)
        new_entry = {
            "pad": args.pad, "filename": fname, "type": new_type,
            "source": str(args.source),
            "source_basename": os.path.basename(args.source),
            "kind": "swap",
            "sha256": sha256_file(dst),
            **info,
        }
        print(f"pad {args.pad:02d} ({fname}): swapped ← {args.source}")

    # Patch manifest in-place
    by_pad[args.pad] = new_entry
    new_pads = list(by_pad.values())
    write_manifest(kit_dir, new_pads, meta=meta)
    write_pad_map(kit_dir, new_pads, meta=meta)
    print(f"manifest + pad-map updated in {kit_dir}")


if __name__ == "__main__":
    main()
