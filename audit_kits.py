#!/usr/bin/env python3
"""
audit_kits.py — Find duplicate pads across an SP-404 MK2 export tree.

Walks a destination directory, reads every `manifest.json` it finds, and
groups pad entries by their `sha256` field. Anything that appears in more
than one place is the same WAV — often the same source picked by two kits,
or a super bank's "best of" that copied an already-exported pad.

Usage:
  python3 audit_kits.py <root>
  python3 audit_kits.py <root> --min 3          only show groups of ≥3
  python3 audit_kits.py <root> --super-only     restrict to super/ subtree
  python3 audit_kits.py <root> --json           machine-readable output
  python3 audit_kits.py <root> --by-source      group by source path instead
                                                of sha256 (catches cases where
                                                two builds chose the same file)
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path


def load_manifests(root: Path) -> list[tuple[Path, dict]]:
    """Return [(manifest_path, parsed_manifest)] for every manifest under root."""
    out = []
    for mpath in sorted(root.rglob("manifest.json")):
        try:
            out.append((mpath, json.loads(mpath.read_text())))
        except (json.JSONDecodeError, OSError) as e:
            print(f"warning: skipping {mpath}: {e}", file=sys.stderr)
    return out


def group_pads(manifests: list[tuple[Path, dict]], *,
               key: str = "sha256") -> dict[str, list[dict]]:
    """
    Build {key_value: [pad_record, ...]}.

    pad_record carries enough context to print where each duplicate lives:
      kit, pad, filename, type, source.
    """
    groups: dict[str, list[dict]] = defaultdict(list)
    for mpath, manifest in manifests:
        kit_dir = mpath.parent
        kit_name = manifest.get("kit_name") or kit_dir.name
        kind = (manifest.get("meta") or {}).get("kind")
        for p in manifest.get("pads") or []:
            v = p.get(key)
            if not v:
                continue
            groups[v].append({
                "kit": kit_name,
                "kit_dir": str(kit_dir),
                "kind": kind,
                "pad": p.get("pad"),
                "filename": p.get("filename"),
                "type": p.get("type"),
                "source": p.get("source"),
            })
    return groups


def print_report(groups: dict[str, list[dict]], *, min_count: int,
                 key: str, total_pads: int) -> int:
    """Human-readable report. Returns the duplicate-group count."""
    dups = [(k, v) for k, v in groups.items() if len(v) >= min_count]
    dups.sort(key=lambda kv: (-len(kv[1]), kv[0]))

    total_groups = len(groups)
    dup_pads = sum(len(v) for _, v in dups)
    unique_pads = total_groups
    print(f"Scanned    : {total_pads} pads in {total_groups} unique {key}s")
    print(f"Duplicates : {len(dups)} groups, {dup_pads} pads "
          f"(threshold ≥ {min_count})")
    if total_pads:
        savings = total_pads - unique_pads
        print(f"Redundancy : {savings} pads are duplicates of another "
              f"({savings * 100 // total_pads}% of total)")
    print()

    for key_val, entries in dups:
        print(f"── {key} {key_val[:12]}…  ({len(entries)} pads) ─────────────")
        # If all entries share a source path, show it once at the top
        sources = {e.get("source") for e in entries if e.get("source")}
        if len(sources) == 1:
            print(f"   source : {sources.pop()}")
        for e in entries:
            tag = f"[{e['kind']}]" if e.get("kind") else ""
            print(f"   {tag:<10} {e['kit']:<28}  pad {e['pad']:>2}  "
                  f"{e['filename']}")
        print()

    return len(dups)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("root", type=Path)
    parser.add_argument("--min", type=int, default=2,
                        help="minimum group size to report (default 2)")
    parser.add_argument("--super-only", action="store_true",
                        help="restrict to <root>/super subtree")
    parser.add_argument("--exclude-super", action="store_true",
                        help="drop pads from super-bank kits (they're copies "
                             "of other pads by design)")
    parser.add_argument("--by-source", action="store_true",
                        help="group by source path instead of sha256")
    parser.add_argument("--json", action="store_true",
                        help="machine-readable JSON output")
    args = parser.parse_args()

    if not args.root.is_dir():
        parser.error(f"root not found: {args.root}")

    scan_root = args.root / "super" if args.super_only else args.root
    if args.super_only and not scan_root.is_dir():
        parser.error(f"--super-only given but {scan_root} doesn't exist")

    manifests = load_manifests(scan_root)
    if not manifests:
        print(f"no manifest.json files found under {scan_root}",
              file=sys.stderr)
        sys.exit(0)

    key = "source" if args.by_source else "sha256"
    groups = group_pads(manifests, key=key)

    if args.exclude_super:
        filtered: dict[str, list[dict]] = {}
        for k, v in groups.items():
            kept = [e for e in v if e.get("kind") != "super"]
            if kept:
                filtered[k] = kept
        groups = filtered

    total_pads = sum(len(v) for v in groups.values())

    if args.json:
        out = {
            "root": str(scan_root),
            "key": key,
            "total_pads": total_pads,
            "unique": len(groups),
            "groups": [
                {"value": k, "count": len(v), "pads": v}
                for k, v in sorted(groups.items(),
                                   key=lambda kv: -len(kv[1]))
                if len(v) >= args.min
            ],
        }
        json.dump(out, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return

    n = print_report(groups, min_count=args.min, key=key, total_pads=total_pads)
    if n == 0:
        print(f"No duplicates found (groups of ≥ {args.min}).")


if __name__ == "__main__":
    main()
