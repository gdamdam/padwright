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

```
01_empty.wav   → pad 13 (top-left,  silent)
02_empty.wav   → pad 14 (top,       silent)
03_empty.wav   → pad 15 (top,       silent)
04_empty.wav   → pad 16 (top-right, silent)
05_rim.wav     → pad 9
06_clap.wav    → pad 10
07_cowbell.wav → pad 11
08_perc.wav    → pad 12
09_low_tom.wav → pad 5
10_mid_tom.wav → pad 6
11_hi_tom.wav  → pad 7
12_crash.wav   → pad 8
13_kick.wav    → pad 1  ← bottom-left ✓
14_snare.wav   → pad 2
15_closed_hh.wav → pad 3
16_open_hh.wav → pad 4
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

Use blocks when you want to pick your favourite kick from a machine's full library,
or load a whole bank of just snares for layering.

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

**Use case:** instant access to a curated cross-section of classic drum machine
sounds — great for building kits by mixing and matching across eras and machines.

---

## Building / resuming

```bash
cd /Users/gio/dev/music/sp404mk2

python make_kits_ff.py --status          # check progress
python make_kits_ff.py --batch 1         # 4, A, B  (58 kits)
python make_kits_ff.py --batch 2         # C, D, E  (89 kits)
python make_kits_ff.py --batch 3         # F–L      (95 kits)
python make_kits_ff.py --batch 4         # M–R     (104 kits)
python make_kits_ff.py --batch 5         # S–W      (57 kits)
python make_kits_ff.py --batch 6         # Y, Z     (67 kits)
python make_kits_ff.py --super-only      # build super banks after all batches
```

Re-running a batch is safe — already-built kits are skipped automatically.
