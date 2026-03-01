#!/usr/bin/env python3
"""
make_kits_ff.py — Build SP-404 MK2 drum kits from the ff archive.

Source : /Volumes/eight/ff/*.zip   (470 drum machine sample packs)
Output : /Volumes/eight/MUSIC_PRODUCTION/SP404MK2_DRUMKITS/
  drumkit/  — one curated 16-pad kit per machine (all 470 zips)
  blocks/   — per-type 16-pad banks for monster kits (≥100 audio files)
  super/    — cross-machine "best-of" themed banks (kicks, snares, hats…)

Audio format : 16-bit / 48 kHz / mono WAV  (matches existing SP-404MK2 kits)

Pad layout (drag-and-drop ready — already pre-reordered like reorder_kits.py):
  File 01-04 → silent pads   → pads 13-16 (top row, empty)
  File 05 rim       → pad 9     File 13 kick      → pad 1 ✓
  File 06 clap      → pad 10    File 14 snare     → pad 2
  File 07 cowbell   → pad 11    File 15 closed_hh → pad 3
  File 08 perc      → pad 12    File 16 open_hh   → pad 4
  File 09 low_tom   → pad 5
  File 10 mid_tom   → pad 6
  File 11 hi_tom    → pad 7
  File 12 crash     → pad 8

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
"""

import os, re, sys, shutil, subprocess, tempfile, time, wave, zipfile
from pathlib import Path
from collections import defaultdict

# ── Paths ──────────────────────────────────────────────────────────────────────
SRC_DIR    = Path("/Volumes/eight/ff")
DST_DIR    = Path("/Volumes/eight/MUSIC_PRODUCTION/SP404MK2_DRUMKITS")
SILENT_WAV = "/tmp/sp404mk2_ff_empty.wav"

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

# ── Pad layout (file_number, type_name) ───────────────────────────────────────
# Files 01-04 are silent placeholders (top row). Files 05-16 are sounds.
SOUND_SLOTS = [
    (5,  "rim"),
    (6,  "clap"),
    (7,  "cowbell"),
    (8,  "perc"),
    (9,  "low_tom"),
    (10, "mid_tom"),
    (11, "hi_tom"),
    (12, "crash"),
    (13, "kick"),
    (14, "snare"),
    (15, "closed_hh"),
    (16, "open_hh"),
]
SLOT_NAMES = [t for _, t in SOUND_SLOTS]

# Already-exported kit files used for cross-machine super banks
SUPER_FILES = {
    "kick":      "13_kick.wav",
    "snare":     "14_snare.wav",
    "closed_hh": "15_closed_hh.wav",
    "open_hh":   "16_open_hh.wav",
    "clap":      "06_clap.wav",
    "perc":      "08_perc.wav",
}

# ── Classifiers (same keywords as make_kits.py) ────────────────────────────────
CLASSIFIERS = [
    ("kick",      ["bass drum", "bassdrum", "bass_drum",
                   "bd a ", "bd b ", "bd c ", "/bd ", " bd ", "/bd.", " bd.", "_bd.",
                   "/kick", "kick/", "kicks/", "kick_", "_kick.", " kick ",
                   "bass-drum", "bassdrm", "kick shot", "/bass/", "bass/"]),
    ("snare",     ["snare drum", "snaredrum", "snare_drum",
                   "/snare", "snare/", "snares/", "_snare", " snare",
                   "sd a ", "sd b ", "sd c ", "/sd ", " sd ", "/sd.", "_sd."]),
    ("open_hh",   ["open hh", "open_hh", "openhat", "open hat",
                   "hh open", "hh_open", " oh ", "/oh ", "_oh_", "oh a ",
                   "oh.", "open hi", "hat open", "hihat op"]),
    ("closed_hh", ["closed hh", "closed_hh", "closedhat", "closed hat",
                   "hh close", "hh_close", " ch ", "/ch ", "_ch_", "/ch_", "ch a ",
                   "ch.", " hh ", "hihat cl", "hi-hat cl", "hat close",
                   "hihat", "hi hat", "hi-hat", "/hh", "_hh", "hats/"]),
    ("low_tom",   ["low tom", "lo tom", "tom lo", "tom low",
                   "floor tom", "tom a ", "tom_lo", "low_tom", "lowtom"]),
    ("mid_tom",   ["mid tom", "tom mid", "tom_mid", "tom b ", "mid_tom", "midtom"]),
    ("hi_tom",    ["hi tom", "high tom", "tom hi", "tom_hi",
                   "tom c ", "hi_tom", "hitom", "hightom"]),
    ("crash",     ["crash", "cymbal", "ride"]),
    ("rim",       ["rimshot", "rim shot", "rim_shot", " rim ", "/rim.",
                   "_rim.", "side stick", "sidestick", "cross stick",
                   "crossstick", "cross-stick"]),
    ("clap",      ["hand clap", "handclap", "hand_clap",
                   "/clap", "clap/", "claps/", " clap", "clap_", "_clap."]),
    ("cowbell",   ["cowbell", "cow bell", "cow_bell"]),
    ("perc",      ["tambourine", " tamb", "tamb ", "shaker", "maracas",
                   "conga", "bongo", "clave", "cabasa", "agogo",
                   "timbale", "guiro", "woodblock", "quijada",
                   "perc/", "percs/", "percussion/", "perc_", "_perc"]),
]


def classify(filepath):
    """Return drum type string or None using keyword matching."""
    p = filepath.lower().replace('\\', '/')
    for drum_type, keywords in CLASSIFIERS:
        for kw in keywords:
            if kw in p:
                return drum_type
    # Generic fallbacks
    if "/tom" in p or "_tom" in p or " tom" in p or "tom." in p:
        return "low_tom"
    if "/hh" in p or "_hh" in p or "hat" in p:
        return "closed_hh"
    return None


def pick_file(candidates):
    """Pick the middle file from a sorted list (avoids extreme variants)."""
    if not candidates:
        return None
    s = sorted(candidates)
    return s[len(s) // 2]


def export(src, dst):
    """Convert src to 16-bit / 48 kHz / mono WAV via ffmpeg."""
    cmd = ["ffmpeg", "-y", "-i", src,
           "-ac", "1", "-ar", "48000", "-sample_fmt", "s16", dst]
    r = subprocess.run(cmd, capture_output=True)
    return r.returncode == 0


def make_silent_wav(path, sr=48000, ms=50):
    n = int(sr * ms / 1000)
    with wave.open(path, 'w') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(b'\x00' * n * 2)


def list_audio(zip_path):
    """List audio file paths inside a zip (sorted)."""
    exts = {'.wav', '.aif', '.aiff'}
    with zipfile.ZipFile(zip_path) as zf:
        return sorted(
            n for n in zf.namelist()
            if not os.path.basename(n).startswith('.')
            and Path(n).suffix.lower() in exts
            and not n.endswith('/')
        )


def extract_zip(zip_path, tmp_dir):
    """Extract all audio files into tmp_dir. Return sorted list of abs paths."""
    exts = {'.wav', '.aif', '.aiff'}
    out = []
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.namelist():
            if (not os.path.basename(member).startswith('.')
                    and Path(member).suffix.lower() in exts
                    and not member.endswith('/')):
                zf.extract(member, tmp_dir)
                out.append(os.path.join(tmp_dir, member))
    return sorted(out)


def sanitize(s, n=20):
    s = re.sub(r'[^a-zA-Z0-9]', '_', s)
    return re.sub(r'_+', '_', s).strip('_')[:n] or 'pad'


# ── Kit builder ────────────────────────────────────────────────────────────────

def build_kit(audio_files, kit_dir, is_small, dry_run):
    """
    Classify files, pick one per slot, export 16-pad kit.

    Small kits (≤16 sounds): use ALL sounds, classify each to a slot.
    Larger kits            : pick one best-per-type (middle of sorted candidates).
    Non-drum / synth kits  : spread sounds evenly across all 12 slots.

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
        for slot_type in SLOT_NAMES:
            chosen = pick_file(buckets.get(slot_type, []))
            if chosen:
                assignments[slot_type] = chosen

        # Small kits: fill remaining empty slots with unclassified sounds
        if is_small and unclassified:
            for slot_type in SLOT_NAMES:
                if slot_type not in assignments and unclassified:
                    assignments[slot_type] = unclassified.pop(0)

        # Tom fallback: generic "tom" in name → lowest empty tom slot
        tom_files = [f for f in unclassified if "tom" in os.path.basename(f).lower()]
        for ts in ["low_tom", "mid_tom", "hi_tom"]:
            if ts not in assignments and tom_files:
                assignments[ts] = tom_files.pop(0)
    else:
        # Non-drum / synth: spread evenly across all 12 sound slots
        files = sorted(audio_files)
        if len(files) > len(SLOT_NAMES):
            step = len(files) / len(SLOT_NAMES)
            files = [files[int(i * step)] for i in range(len(SLOT_NAMES))]
        for slot_type, f in zip(SLOT_NAMES, files):
            assignments[slot_type] = f

    if dry_run:
        tag = "(drum)" if is_drum else "(synth-spread)"
        print(f"    {len(assignments):2d}/12 slots filled  {tag}")
        return assignments

    os.makedirs(kit_dir, exist_ok=True)

    # Silent top-row pads (01-04)
    for i in range(1, 5):
        shutil.copy(SILENT_WAV, os.path.join(kit_dir, f"0{i}_empty.wav"))

    # Sound pads (05-16)
    for file_num, slot_type in SOUND_SLOTS:
        src = assignments.get(slot_type)
        if not src:
            continue
        dst = os.path.join(kit_dir, f"{file_num:02d}_{slot_type}.wav")
        ok = export(src, dst)
        print(f"    {file_num:02d}_{slot_type:<12} {'OK' if ok else 'FAIL'}  {os.path.basename(src)}")

    return assignments


# ── Category blocks (monster kits) ────────────────────────────────────────────

def build_blocks(audio_files, machine_name, blocks_dir, dry_run):
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
        for i, src in enumerate(files, 1):
            label = sanitize(Path(src).stem, 14)
            dst = os.path.join(block_dir, f"{i:02d}_{label}.wav")
            export(src, dst)


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
        for i, (machine, src) in enumerate(entries, 1):
            label = sanitize(machine, 16)
            dst   = os.path.join(bank_dir, f"{i:02d}_{label}.wav")
            if os.path.exists(src):
                shutil.copy(src, dst)
                print(f"    {i:02d}_{label:<18} OK   {machine}")
            else:
                print(f"    {i:02d}_{label:<18} MISS {machine}")


# ── Progress bar ───────────────────────────────────────────────────────────────

def _fmt_time(seconds):
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"


class ProgressBar:
    """
    Sticky-bottom progress bar on stderr.

    Uses ANSI scroll-region to pin the bar to the last terminal row so that
    stdout kit output scrolls above it without pushing the bar off screen.
    Falls back to simple \\r mode when stderr is not a TTY (e.g. piped).
    """
    WIDTH = 36

    def __init__(self, total):
        self.total = total
        self.done  = 0
        self.start = time.time()
        self._tty  = sys.stderr.isatty()
        self._rows = 0
        if self._tty:
            try:
                self._rows = os.get_terminal_size().lines
                # Restrict scrolling to rows 1..N-1; last row is reserved for bar
                sys.stderr.write(
                    f"\033[1;{self._rows - 1}r"   # set scroll region
                    f"\033[{self._rows - 1};1H"   # park cursor just above bar
                )
                sys.stderr.flush()
                self._draw_bar()
            except OSError:
                self._tty = False

    def _render(self, name=""):
        pct    = self.done / self.total if self.total else 1.0
        filled = int(self.WIDTH * pct)
        bar    = "█" * filled + "░" * (self.WIDTH - filled)
        elapsed = time.time() - self.start
        if 0 < self.done < self.total:
            eta     = elapsed / self.done * (self.total - self.done)
            eta_str = f"  eta {_fmt_time(eta)}"
        else:
            eta_str = ""
        label = (name[:26] + "…") if len(name) > 27 else name
        return f"[{bar}] {self.done}/{self.total}  {_fmt_time(elapsed)}{eta_str}  {label}"

    def _draw_bar(self, name=""):
        # Save cursor → jump to last row → clear → draw → restore cursor
        sys.stderr.write(
            f"\033[s"
            f"\033[{self._rows};1H\033[2K"
            f"{self._render(name)}"
            f"\033[u"
        )
        sys.stderr.flush()

    def clear(self):
        pass  # no-op: sticky bar doesn't need clearing before kit output

    def update(self, name=""):
        self.done += 1
        if self._tty:
            self._draw_bar(name)
        else:
            sys.stderr.write(f"\r{self._render(name)}")
            sys.stderr.flush()

    def finish(self):
        self.done = self.total
        if self._tty and self._rows:
            # Draw final bar, restore full scroll region, move past bar
            sys.stderr.write(
                f"\033[s"
                f"\033[{self._rows};1H\033[2K{self._render()}"
                f"\033[u"
                f"\033[1;{self._rows}r"           # restore full scroll region
            )
        else:
            sys.stderr.write(f"\r{self._render()}\n")
        sys.stderr.flush()


# ── Main ───────────────────────────────────────────────────────────────────────

def dry_run_kit(audio_names, machine):
    """Fast dry-run analysis using only zip member names (no extraction needed)."""
    buckets = defaultdict(list)
    unclassified = []
    for name in audio_names:
        t = classify(name)
        (buckets[t] if t else unclassified).append(name)
    is_drum = bool(buckets)
    filled  = len(buckets) if is_drum else min(len(audio_names), len(SLOT_NAMES))
    tag     = "(drum)" if is_drum else "(synth-spread)"
    print(f"    {filled:2d}/12 slots filled  {tag}")
    return is_drum


def show_status():
    """Print how many kits are built vs total, then exit."""
    all_zips = sorted(SRC_DIR.glob("*.zip"))
    total = len(all_zips)
    drumkit_dir = DST_DIR / "drumkit"
    built = 0
    if drumkit_dir.exists():
        for z in all_zips:
            kit = drumkit_dir / z.stem
            if kit.is_dir() and any(f.suffix == '.wav' for f in kit.iterdir()):
                built += 1
    pct = built * 100 // total if total else 0
    print(f"Status : {built}/{total} kits built ({pct}%)")
    print(f"Remaining : {total - built}")
    # Per-batch breakdown
    for batch_num, letters in BATCHES.items():
        batch_zips = [z for z in all_zips if z.stem[0].lower() in letters]
        b_built = sum(
            1 for z in batch_zips
            if (drumkit_dir / z.stem).is_dir()
            and any(f.suffix == '.wav' for f in (drumkit_dir / z.stem).iterdir())
        ) if drumkit_dir.exists() else 0
        status = "✅" if b_built == len(batch_zips) else ("🔄" if b_built > 0 else "⬜")
        print(f"  Batch {batch_num}: {b_built:3d}/{len(batch_zips)} {status}")
    super_dir = DST_DIR / "super"
    super_status = "✅" if super_dir.exists() and any(super_dir.iterdir()) else "⬜"
    print(f"  Super banks: {super_status}")


def main():
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

    if status_only:
        show_status()
        return

    filters = [a for a in sys.argv[1:]
               if not a.startswith("--") and not (
                   len(sys.argv) > sys.argv.index(a) - 1
                   and sys.argv[sys.argv.index(a) - 1] == "--batch"
               )]
    # cleaner filter extraction: skip the value after --batch
    filters = []
    skip_next = False
    for a in sys.argv[1:]:
        if skip_next:
            skip_next = False
            continue
        if a == "--batch":
            skip_next = True
            continue
        if not a.startswith("--"):
            filters.append(a)

    zips = sorted(SRC_DIR.glob("*.zip"))
    if batch_num is not None:
        letters = BATCHES.get(batch_num, set())
        zips = [z for z in zips if z.stem[0].lower() in letters]
    elif filters:
        zips = [z for z in zips if any(f.lower() in z.name.lower() for f in filters)]

    print(f"Source : {SRC_DIR}")
    print(f"Output : {DST_DIR}")
    print(f"Zips   : {len(zips)}{f'  (batch {batch_num})' if batch_num else ''}")
    print(f"Mode   : {'DRY RUN' if dry_run else ('SUPER ONLY' if super_only else 'BUILD')}\n")

    pb = None if dry_run else ProgressBar(len(zips))

    if not dry_run:
        for sub in ("drumkit", "blocks", "super"):
            (DST_DIR / sub).mkdir(parents=True, exist_ok=True)
        make_silent_wav(SILENT_WAV)

    super_data  = defaultdict(list)  # type → [(machine_name, abs_path)]
    total_ok    = 0
    total_skip  = 0
    dry_drum    = 0
    dry_synth   = 0

    # --super-only: collect from already-built kits then jump to super banks
    if super_only:
        all_zips = sorted(SRC_DIR.glob("*.zip"))
        for z in all_zips:
            kit_dir = str(DST_DIR / "drumkit" / z.stem)
            for stype, fname in SUPER_FILES.items():
                fpath = os.path.join(kit_dir, fname)
                if os.path.exists(fpath):
                    super_data[stype].append((z.stem, fpath))
        print(f"Collected super data from existing kits:")
        for stype, entries in super_data.items():
            print(f"  {stype}: {len(entries)} machines")
        print()
        build_super_banks(super_data, str(DST_DIR / "super"), dry_run=False)
        print("\nDone — super banks built.")
        return

    for zip_path in zips:
        machine = zip_path.stem

        if pb: pb.clear()

        try:
            audio_names = list_audio(zip_path)
        except Exception as e:
            print(f"[SKIP] {machine}: {e}")
            total_skip += 1
            if pb: pb.update(machine)
            continue

        n = len(audio_names)
        if n == 0:
            print(f"[SKIP] {machine}: no audio files")
            total_skip += 1
            if pb: pb.update(machine)
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
        kit_dir = str(DST_DIR / "drumkit" / machine)

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
            if pb: pb.update(machine)
            continue

        with tempfile.TemporaryDirectory() as tmp:
            try:
                audio_files = extract_zip(zip_path, tmp)
            except Exception as e:
                print(f"  [FAIL] extract: {e}")
                total_skip += 1
                if pb: pb.update(machine)
                continue

            build_kit(audio_files, kit_dir, is_small=(n <= 16), dry_run=False)

            if tier == 4:
                build_blocks(audio_files, machine,
                             str(DST_DIR / "blocks"), dry_run=False)

        # Collect already-exported files for super banks (temp dir is gone)
        for stype, fname in SUPER_FILES.items():
            fpath = os.path.join(kit_dir, fname)
            if os.path.exists(fpath):
                super_data[stype].append((machine, fpath))

        total_ok += 1
        if pb: pb.update(machine)

    if dry_run:
        print(f"\n{'═' * 60}")
        print(f"DRY RUN SUMMARY")
        print(f"  {total_ok} kits scanned  ({dry_drum} drum, {dry_synth} synth-spread)")
        print(f"  {total_skip} skipped")
        print(f"  Run without --dry-run to build.")
        return

    if pb: pb.finish()
    print(f"\n{'═' * 60}")
    print("BUILDING SUPER BANKS")
    print('═' * 60)
    build_super_banks(super_data, str(DST_DIR / "super"), dry_run=False)

    print(f"\n{'═' * 60}")
    print(f"DONE — {total_ok} kits, {total_skip} skipped")
    print(f"Output : {DST_DIR}")


if __name__ == "__main__":
    main()
