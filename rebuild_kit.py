#!/usr/bin/env python3
"""
rebuild_kit.py — Re-export a bank using its manifest.json as the source of truth.

Useful when:
  - You hand-edited manifest.json (swapped a source path, changed a type)
  - You want to re-convert with different audio settings later
  - You want to recover a bank after a partial corruption

Reads <kit_dir>/manifest.json, re-runs the exporter against every pad's
recorded `source`, and rewrites manifest.json + pad-map.html.

Usage:
  python3 rebuild_kit.py <kit_dir>
  python3 rebuild_kit.py <kit_dir> --dry-run
  python3 rebuild_kit.py <kit_dir> --out /path/to/new_dir   # build a copy
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sp404_core import (
    KIND_DRUMKIT, build_from_pad_list, manifest_to_crate,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("kit_dir", type=Path)
    parser.add_argument("--out", type=Path, default=None,
                        help="write rebuilt bank here instead of overwriting")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    mpath = args.kit_dir / "manifest.json"
    if not mpath.exists():
        print(f"error: no manifest.json in {args.kit_dir}", file=sys.stderr)
        sys.exit(2)

    manifest = json.loads(mpath.read_text())
    meta = manifest.get("meta") or {}
    kind = meta.get("kind") or KIND_DRUMKIT

    crate = manifest_to_crate(manifest)
    pad_specs = crate["pads"]

    dst = args.out or args.kit_dir
    print(f"Rebuild : {args.kit_dir}")
    print(f"Output  : {dst}")
    print(f"Kind    : {kind}")
    print(f"Sources : {len(pad_specs)} pads with audio "
          f"({16 - len(pad_specs)} silent)")
    print()

    build_from_pad_list(
        dst, pad_specs, kind=kind,
        meta_extra={k: v for k, v in meta.items() if k != "kind"},
        dry_run=args.dry_run,
    )

    if args.dry_run:
        print("\n(dry run — nothing written)")
    else:
        print(f"\nDone — manifest + pad-map updated in {dst}")


if __name__ == "__main__":
    main()
