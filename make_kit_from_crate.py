#!/usr/bin/env python3
"""
make_kit_from_crate.py — Build an SP-404MKII bank from a hand-curated crate.

A crate is a small JSON file describing intent:

    {
      "name": "Bedroom Kit",
      "kind": "drumkit",
      "pads": [
        {"pad": 13, "source": "/path/to/kick.wav",  "type": "kick"},
        {"pad": 14, "source": "/path/to/snare.wav", "type": "snare"},
        ...
      ]
    }

Supported "kind" values: drumkit (default), loop_bank, block, super.
Pads not listed get silent placeholders (drumkit / loop_bank).

Usage:
  python3 make_kit_from_crate.py <crate.json> <dst_dir>
  python3 make_kit_from_crate.py <crate.json> <dst_dir> --name "Override"
  python3 make_kit_from_crate.py <crate.json> <dst_dir> --dry-run

Dump mode — turn a built kit back into a crate you can hand-edit:
  python3 make_kit_from_crate.py --from-kit <kit_dir> > crate.json
  python3 make_kit_from_crate.py --from-kit <kit_dir> --out crate.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sp404_core import (
    KIND_DRUMKIT, KIND_LOOPBANK, KIND_BLOCK, KIND_SUPER,
    build_from_pad_list, load_crate, manifest_to_crate,
)


VALID_KINDS = {KIND_DRUMKIT, KIND_LOOPBANK, KIND_BLOCK, KIND_SUPER}


def cmd_dump(kit_dir: Path, out: Path | None) -> None:
    mpath = kit_dir / "manifest.json"
    if not mpath.exists():
        print(f"error: no manifest.json in {kit_dir}", file=sys.stderr)
        sys.exit(2)
    crate = manifest_to_crate(json.loads(mpath.read_text()))
    text = json.dumps(crate, indent=2) + "\n"
    if out:
        out.write_text(text)
        print(f"wrote crate → {out}", file=sys.stderr)
    else:
        sys.stdout.write(text)


def cmd_build(crate_path: Path, dst_dir: Path, name: str | None, dry_run: bool) -> None:
    crate = load_crate(crate_path)
    if name:
        crate["name"] = name
    kind = crate.get("kind") or KIND_DRUMKIT
    if kind not in VALID_KINDS:
        print(f"error: unknown kind {kind!r} (use one of {sorted(VALID_KINDS)})",
              file=sys.stderr)
        sys.exit(2)

    # Validate that listed sources exist (warn but don't abort; silent fallback).
    missing = [p["source"] for p in crate["pads"]
               if p.get("source") and not Path(p["source"]).exists()]
    if missing:
        print(f"warning: {len(missing)} source file(s) missing — those pads "
              f"will be silent", file=sys.stderr)
        for m in missing[:5]:
            print(f"  missing: {m}", file=sys.stderr)
        if len(missing) > 5:
            print(f"  …and {len(missing) - 5} more", file=sys.stderr)

    # Strip missing sources so build_from_pad_list writes silence instead of failing
    pad_specs = []
    for p in crate["pads"]:
        if p.get("source") and not Path(p["source"]).exists():
            pad_specs.append({"pad": p["pad"], "source": None,
                              "type": p.get("type")})
        else:
            pad_specs.append(p)

    bank_dir = dst_dir / crate["name"]
    print(f"Crate   : {crate_path}")
    print(f"Output  : {bank_dir}")
    print(f"Kind    : {kind}")
    print(f"Pads    : {sum(1 for p in pad_specs if p.get('source'))} "
          f"with audio, {sum(1 for p in pad_specs if not p.get('source'))} silent")
    print()

    build_from_pad_list(
        bank_dir, pad_specs, kind=kind,
        meta_extra={"source_crate": str(crate_path)},
        dry_run=dry_run,
    )

    if dry_run:
        print("\n(dry run — nothing written)")
    else:
        print(f"\nDone — manifest + pad-map written in {bank_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("crate", nargs="?", type=Path,
                        help="crate JSON file (in build mode)")
    parser.add_argument("dst_dir", nargs="?", type=Path,
                        help="output directory (in build mode)")
    parser.add_argument("--name", default=None,
                        help="override crate name")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--from-kit", type=Path, default=None,
                        help="dump a built kit's manifest as a crate")
    parser.add_argument("--out", type=Path, default=None,
                        help="write dumped crate here (default: stdout)")
    args = parser.parse_args()

    if args.from_kit:
        cmd_dump(args.from_kit, args.out)
        return

    if not args.crate or not args.dst_dir:
        parser.error("provide <crate.json> and <dst_dir>, or use --from-kit")
    if not args.crate.exists():
        parser.error(f"crate not found: {args.crate}")

    cmd_build(args.crate, args.dst_dir, args.name, args.dry_run)


if __name__ == "__main__":
    main()
