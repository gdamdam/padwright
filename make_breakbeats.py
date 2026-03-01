#!/usr/bin/env python3
"""
make_breakbeats.py — Build SP-404 MK2 loop banks from a sample library.

Scans a source directory recursively, finds audio loop files under 1 MB
(breakbeats, drum loops, percussion loops), and exports 16-pad banks
ready to drag-and-drop into the Roland SP-404 MK2 app.

Default source : /Volumes/eight/MUSIC_PRODUCTION/SAMPLES/Cymatics/
Default output : /Volumes/eight/MUSIC_PRODUCTION/SP404MK2_BREAKBEATS/

What counts as a loop:
  - Audio file (.wav / .aif / .aiff), not hidden, not an Ableton .asd sidecar
  - File size < 1 MB  (distinguishes short loops from full stems/tracks)
  - "loop" appears in the filename OR in any parent folder name (case-insensitive)

Bank grouping:
  Each leaf folder that contains qualifying loops becomes one bank.
  Up to 16 loops per bank (evenly sampled if more). Folders with zero
  qualifying loops are skipped.

Pad layout (file number = pad number, all 16 pads filled with loops):
  File 01 → pad  1 (top-left)      File 09 → pad  9
  File 02 → pad  2                  File 10 → pad 10
  File 03 → pad  3                  File 11 → pad 11
  File 04 → pad  4 (top-right)     File 12 → pad 12
  File 05 → pad  5                  File 13 → pad 13 (bottom-left)
  File 06 → pad  6                  File 14 → pad 14
  File 07 → pad  7                  File 15 → pad 15
  File 08 → pad  8                  File 16 → pad 16 (bottom-right)

Audio format: 16-bit / 48 kHz / stereo WAV.

Usage:
  python make_breakbeats.py                        build all banks
  python make_breakbeats.py --dry-run              scan only, no file output
  python make_breakbeats.py --status               show built vs total, then exit
  python make_breakbeats.py --src /path/to/loops   override source directory
  python make_breakbeats.py --dst /path/to/output  override output directory
  python make_breakbeats.py Cymatics Roland        only banks matching any filter word
  python make_breakbeats.py --help                 show this message

Re-running is safe — already-built banks are skipped automatically.
"""

import os
import re
import sys
import shutil
import subprocess
import time
from collections import deque
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────
SRC_DIR = Path("/Volumes/eight/MUSIC_PRODUCTION/SAMPLES/Cymatics")
DST_DIR = Path("/Volumes/eight/MUSIC_PRODUCTION/SP404MK2_BREAKBEATS")

MAX_SIZE   = 1 * 1024 * 1024   # 1 MB
MAX_PADS   = 16
AUDIO_EXTS = {".wav", ".aif", ".aiff"}

HELP = """\
make_breakbeats.py — Build SP-404 MK2 loop banks from a sample library.

Scans a source directory recursively, finds audio loop files under 1 MB
(breakbeats, drum loops, percussion loops), and exports 16-pad banks
ready to drag-and-drop into the Roland SP-404 MK2 app.

Default source : /Volumes/eight/MUSIC_PRODUCTION/SAMPLES/Cymatics/
Default output : /Volumes/eight/MUSIC_PRODUCTION/SP404MK2_BREAKBEATS/

What counts as a loop:
  - Audio file (.wav / .aif / .aiff), not hidden, not an Ableton .asd sidecar
  - File size < 1 MB
  - "loop" appears in the filename OR in any ancestor folder name

Bank grouping:
  Each leaf folder with qualifying loops becomes one bank (up to 16 files,
  evenly sampled if more). The bank name is derived from the folder path
  relative to the source root.

Usage:
  python make_breakbeats.py                        build all banks
  python make_breakbeats.py --dry-run              scan only, no file output
  python make_breakbeats.py --status               show built vs total, then exit
  python make_breakbeats.py --src /path/to/loops   override source directory
  python make_breakbeats.py --dst /path/to/output  override output directory
  python make_breakbeats.py Cymatics Roland        only banks matching filter words
  python make_breakbeats.py --help                 show this message

Re-running is safe — already-built banks are skipped automatically.
Audio output: 16-bit / 48 kHz / stereo WAV.
"""


# ── Helpers ────────────────────────────────────────────────────────────────────

def is_loop_file(path: Path, src_root: Path) -> bool:
    """Return True if this audio file qualifies as a loop."""
    if path.suffix.lower() not in AUDIO_EXTS:
        return False
    if path.name.startswith(".") or path.name.endswith(".asd"):
        return False
    try:
        if path.stat().st_size >= MAX_SIZE:
            return False
    except OSError:
        return False
    # "loop" anywhere in the filename or any ancestor folder name
    rel = path.relative_to(src_root)
    combined = "/".join(rel.parts).lower()
    return "loop" in combined


def collect_banks(src_root: Path) -> list[tuple[str, list[Path]]]:
    """
    Walk src_root. For each directory, collect qualifying loop files that live
    directly inside it (not in subdirs). Return list of (bank_name, [paths]).
    bank_name is the folder path relative to src_root, / replaced with __.
    """
    banks = []
    for dirpath, dirnames, filenames in os.walk(src_root):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        folder = Path(dirpath)
        loops = sorted(
            f for name in filenames
            if is_loop_file(f := folder / name, src_root)
        )
        if not loops:
            continue
        rel = folder.relative_to(src_root)
        # Use folder path parts joined with __ as bank name; fall back to folder name
        parts = list(rel.parts)
        bank_name = "__".join(parts) if parts else folder.name
        banks.append((bank_name, loops))
    return banks


def sanitize(s: str, n: int = 20) -> str:
    s = re.sub(r"[^a-zA-Z0-9]", "_", s)
    return re.sub(r"_+", "_", s).strip("_")[:n] or "loop"


def shorten_name(stem: str, n: int = 18) -> str:
    """Strip common Cymatics prefix patterns and shorten."""
    # Remove leading "Cymatics - " or "cymatics - "
    stem = re.sub(r"(?i)^cymatics\s*-\s*", "", stem)
    # Remove trailing BPM pattern like " - 130 BPM" or "130BPM"
    stem = re.sub(r"\s*[-–]\s*\d+\s*BPM.*$", "", stem, flags=re.IGNORECASE)
    stem = re.sub(r"\s+\d+\s*BPM.*$", "", stem, flags=re.IGNORECASE)
    return sanitize(stem, n)


def export(src: Path, dst: str) -> bool:
    """Convert src to 16-bit / 48 kHz / stereo WAV via ffmpeg."""
    cmd = ["ffmpeg", "-y", "-i", str(src),
           "-ac", "2", "-ar", "48000", "-sample_fmt", "s16", dst]
    r = subprocess.run(cmd, capture_output=True)
    return r.returncode == 0


def evenly_sample(items: list, n: int) -> list:
    """Pick n items evenly spaced from items."""
    if len(items) <= n:
        return items
    step = len(items) / n
    return [items[int(i * step)] for i in range(n)]


# ── Bank builder ───────────────────────────────────────────────────────────────

def build_bank(loops: list[Path], bank_dir: str, dry_run: bool) -> int:
    """Export up to MAX_PADS loops into bank_dir. Returns count exported."""
    files = evenly_sample(loops, MAX_PADS)

    if dry_run:
        print(f"    {len(files):2d} loops → {os.path.basename(bank_dir)}")
        return len(files)

    os.makedirs(bank_dir, exist_ok=True)
    ok_count = 0
    for i, src in enumerate(files, 1):
        label = shorten_name(src.stem)
        dst = os.path.join(bank_dir, f"{i:02d}_{label}.wav")
        ok = export(src, dst)
        status = "OK  " if ok else "FAIL"
        print(f"    {i:02d}_{label:<20} {status}  {src.name}")
        if ok:
            ok_count += 1
    return ok_count


# ── Status ─────────────────────────────────────────────────────────────────────

def show_status(src_dir: Path, dst_dir: Path) -> None:
    banks = collect_banks(src_dir)
    total = len(banks)
    built = 0
    for bank_name, _ in banks:
        bank_dir = dst_dir / bank_name
        if bank_dir.is_dir() and any(
            f.suffix == ".wav" for f in bank_dir.iterdir()
        ):
            built += 1
    pct = built * 100 // total if total else 0
    print(f"Source : {src_dir}")
    print(f"Output : {dst_dir}")
    print(f"Status : {built}/{total} banks built ({pct}%)")
    print(f"Remaining : {total - built}")


# ── Terminal UI (same design as make_kits.py) ──────────────────────────────────

def _fmt_time(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"


class UI:
    LOG_H = 16

    def __init__(self, total: int):
        self.total = total
        self.done  = 0
        self.start = time.time()
        self._name = ""
        self._buf  = deque(maxlen=self.LOG_H)
        self._cur  = ""
        self._real = sys.__stdout__
        self._tty  = self._real.isatty()
        self._rows = 0
        self._cols = 80

        if self._tty:
            try:
                sz = os.get_terminal_size(self._real.fileno())
                self._rows, self._cols = sz.lines, sz.columns
                self._dash = self.LOG_H + 3
                if self._rows > self._dash + 3:
                    self._setup()
                else:
                    self._tty = False
            except OSError:
                self._tty = False

        sys.stdout = self

    def _setup(self):
        scroll_end = self._rows - self._dash
        out = [f"\033[1;{scroll_end}r"]
        for r in range(scroll_end + 1, self._rows + 1):
            out.append(f"\033[{r};1H\033[2K")
        out.append(f"\033[{scroll_end};1H")
        self._real.write("".join(out))
        self._real.flush()
        self._redraw()

    def _bar_str(self) -> str:
        W      = min(36, self._cols - 36)
        pct    = self.done / self.total if self.total else 1.0
        filled = int(W * pct)
        bar    = "█" * filled + "░" * (W - filled)
        elapsed = time.time() - self.start
        eta_s  = ""
        if 0 < self.done < self.total:
            eta   = elapsed / self.done * (self.total - self.done)
            eta_s = f"  eta {_fmt_time(eta)}"
        label = (self._name[:24] + "…") if len(self._name) > 25 else self._name
        return f"[{bar}] {self.done}/{self.total}  {_fmt_time(elapsed)}{eta_s}  {label}"

    def _redraw(self):
        cols  = self._cols
        r0    = self._rows - self._dash + 1
        lines = list(self._buf)
        out   = ["\033[s"]
        out.append(f"\033[{r0};1H\033[2K{'─' * cols}")
        for i in range(self.LOG_H):
            row  = r0 + 1 + i
            text = (lines[i] if i < len(lines) else "")[:cols]
            out.append(f"\033[{row};1H\033[2K{text}")
        sep_row = r0 + 1 + self.LOG_H
        out.append(f"\033[{sep_row};1H\033[2K{'─' * cols}")
        out.append(f"\033[{self._rows};1H\033[2K{self._bar_str()}")
        out.append("\033[u")
        self._real.write("".join(out))
        self._real.flush()

    def write(self, text: str):
        if not self._tty:
            self._real.write(text)
            return
        parts = text.split("\n")
        self._cur += parts[0]
        for part in parts[1:]:
            self._buf.append(self._cur)
            self._cur = part
            self._redraw()

    def flush(self):
        self._real.flush()

    def clear(self):
        pass

    def update(self, name: str = ""):
        self.done  += 1
        self._name  = name
        if self._tty:
            self._redraw()
        else:
            self._real.write(f"\r{self._bar_str()}\n")
            self._real.flush()

    def finish(self):
        self.done  = self.total
        self._name = ""
        if self._tty and self._rows:
            self._redraw()
            self._real.write(f"\033[1;{self._rows}r\033[{self._rows};1H\n")
            self._real.flush()
        else:
            self._real.write(f"\r{self._bar_str()}\n")
            self._real.flush()
        sys.stdout = self._real


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    if "--help" in sys.argv or "-h" in sys.argv:
        print(HELP)
        return

    dry_run     = "--dry-run" in sys.argv
    status_only = "--status"  in sys.argv

    args = sys.argv[1:]

    # --src / --dst overrides
    src_dir = SRC_DIR
    dst_dir = DST_DIR
    for i, a in enumerate(args):
        if a == "--src" and i + 1 < len(args):
            src_dir = Path(args[i + 1])
        if a == "--dst" and i + 1 < len(args):
            dst_dir = Path(args[i + 1])

    if status_only:
        show_status(src_dir, dst_dir)
        return

    # Optional filter words (positional args, not flags)
    skip_next = False
    filters = []
    for a in args:
        if skip_next:
            skip_next = False
            continue
        if a in ("--src", "--dst"):
            skip_next = True
            continue
        if not a.startswith("--"):
            filters.append(a)

    print(f"Source : {src_dir}")
    print(f"Output : {dst_dir}")
    print(f"Mode   : {'DRY RUN' if dry_run else 'BUILD'}")
    print("Scanning for loop files under 1 MB …\n")

    banks = collect_banks(src_dir)

    if filters:
        banks = [
            (name, loops) for name, loops in banks
            if any(f.lower() in name.lower() for f in filters)
        ]

    print(f"Banks  : {len(banks)}\n")

    if not banks:
        print("No matching banks found.")
        return

    if not dry_run:
        dst_dir.mkdir(parents=True, exist_ok=True)

    ui = None if dry_run else UI(len(banks))

    total_ok   = 0
    total_skip = 0
    total_loops = 0

    for bank_name, loops in banks:
        bank_dir = str(dst_dir / bank_name)

        if not dry_run:
            ui.clear()

        n = len(loops)
        capped = min(n, MAX_PADS)
        print(f"\n{'─' * 60}")
        print(f"  [{n:3d} loops → {capped} pads]  {bank_name}")

        if dry_run:
            build_bank(loops, bank_dir, dry_run=True)
            total_ok += 1
            total_loops += capped
            continue

        # Skip already-built banks
        if os.path.isdir(bank_dir) and any(
            f.endswith(".wav") for f in os.listdir(bank_dir)
        ):
            print(f"  [SKIP] already built")
            total_ok += 1
            if ui:
                ui.update(bank_name)
            continue

        exported = build_bank(loops, bank_dir, dry_run=False)
        total_loops += exported
        total_ok += 1
        if ui:
            ui.update(bank_name)

    if dry_run:
        print(f"\n{'═' * 60}")
        print(f"DRY RUN SUMMARY")
        print(f"  {total_ok} banks  •  {total_loops} loop slots")
        print(f"  Run without --dry-run to build.")
        return

    if ui:
        ui.finish()

    print(f"\n{'═' * 60}")
    print(f"DONE — {total_ok} banks, {total_skip} skipped")
    print(f"Output : {dst_dir}")


if __name__ == "__main__":
    main()
