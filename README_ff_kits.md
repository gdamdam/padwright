# SP-404 MK2 Drum Kits — FF Archive

Kits built from the **FF archive** (`/Volumes/eight/ff/`) — 470 classic drum machines
and synthesizers, converted and organised for the SP-404 MK2.

Output lives in three folders under `/Volumes/eight/MUSIC_PRODUCTION/SP404MK2_DRUMKITS/`:

---

## drumkit/

**One curated 16-pad kit per machine.**

Each machine gets its own folder (`Roland TR-808/`, `Akai MPC3000/`, …).
Inside: 16 WAV files, numbered and named so drag-and-drop into the Roland app
lands on the right pads immediately — no manual re-ordering needed.

File number = pad number (top-left → bottom-right):

```
01_empty.wav     → pad  1 (top-left,  silent)
02_empty.wav     → pad  2 (top,       silent)
03_empty.wav     → pad  3 (top,       silent)
04_empty.wav     → pad  4 (top-right, silent)
05_rim.wav       → pad  5
06_clap.wav      → pad  6
07_cowbell.wav   → pad  7
08_perc.wav      → pad  8
09_low_tom.wav   → pad  9
10_mid_tom.wav   → pad 10
11_hi_tom.wav    → pad 11
12_crash.wav     → pad 12
13_kick.wav      → pad 13 ← bottom-left ✓
14_snare.wav     → pad 14
15_closed_hh.wav → pad 15
16_open_hh.wav   → pad 16
```

**Tier logic** (how sounds are chosen):
- **≤ 16 files** — all sounds used, each classified to its slot
- **17–99 files** — one best representative per type (middle of alphabetically sorted candidates)
- **≥ 100 files** — same as above, plus category blocks (see below)
- **No classifiable sounds** (generic names like `001.wav`) — spread evenly across all 12 pad slots

---

## blocks/

**Per-category 16-pad banks for monster kits (machines with ≥ 100 sounds).**

Some machines ship with hundreds of samples — far more kicks or hats than one kit
can hold. Blocks let you load all of them onto the SP-404 MK2 across multiple banks.

Each block is a folder containing up to 16 sounds of the same type, evenly sampled
across the full collection:

```
blocks/
  Roland TR-909/
    Roland_TR-909_KICKS/    ← 16 kicks from across the collection
    Roland_TR-909_SNARES/   ← 16 snares
    Roland_TR-909_HATS/     ← 16 hi-hats (open + closed combined)
    Roland_TR-909_TOMS/     ← 16 toms
    Roland_TR-909_PERC/     ← 16 cymbals, rims, cowbells, perc
  Roland MC-909/
    …
```

**Machines that get blocks:** Roland MC-909 (849 files), Roland TR-909 (474),
Alesis SR16 (237), and any other machine with ≥ 100 audio files.

---

## super/

**Cross-machine themed banks — the best of everything in one place.**

After all individual kits are built, the script harvests the chosen sound from each
machine and assembles six "super banks". Each bank holds up to 16 machines, evenly
sampled across the full 470-machine collection.

```
super/
  SUPER_KICK/      ← one kick from 16 different machines
  SUPER_SNARE/     ← one snare from 16 different machines
  SUPER_CLOSED_HH/ ← one closed hat from 16 machines
  SUPER_OPEN_HH/   ← one open hat from 16 machines
  SUPER_CLAP/      ← one clap from 16 machines
  SUPER_PERC/      ← one perc hit from 16 machines
```

Files are named `01_Roland_TR-808.wav`, `02_Akai_MPC3000.wav`, … so you always
know which machine a sound came from.

---

## Scripts

### make_kits.py

Builds all kits from the FF archive. Run `python make_kits.py --help` for full usage.

```bash
cd /Users/gio/dev/music/sp404mk2

python make_kits.py --status          # check progress
python make_kits.py --batch 1         # 4, A, B  (58 kits)
python make_kits.py --batch 2         # C, D, E  (89 kits)
python make_kits.py --batch 3         # F–L      (95 kits)
python make_kits.py --batch 4         # M–R     (104 kits)
python make_kits.py --batch 5         # S–W      (57 kits)
python make_kits.py --batch 6         # Y, Z     (67 kits)
python make_kits.py --super-only      # build super banks after all batches
```

Re-running a batch is safe — already-built kits are skipped automatically.

### reorder_kits.py

Reorders existing kits (not built by `make_kits.py`) so drag-and-drop into the
Roland app places sounds on the correct pads. Renames files and adds 4 silent
top-row placeholders. Run `python reorder_kits.py --help` for full usage.

```bash
python reorder_kits.py    # process all unordered kits under KITS_DIR
```

Kits that already have `01_empty.wav` are skipped automatically.

### make_breakbeats.py

Scans a Cymatics (or any) sample library for loop audio files under 1 MB —
breakbeats, drum loops, percussion loops — and organises them into 16-pad
SP-404 MK2 banks. Each source subfolder becomes one bank, evenly sampled to
16 files. Run `python make_breakbeats.py --help` for full usage.

```bash
python make_breakbeats.py --dry-run   # scan only, no file output
python make_breakbeats.py --status    # show built vs total
python make_breakbeats.py             # build all banks
python make_breakbeats.py --src /path/to/samples --dst /path/to/output
```
