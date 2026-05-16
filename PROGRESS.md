# SP404MK2 FF Kit Build — Progress

## Source
`/Volumes/eight/ff/` — 470 zip files (classic drum machines & synths)

## Output
`/Volumes/eight/MUSIC_PRODUCTION/SP404MK2_DRUMKITS/`

---

## Quick status check (run any time)
```
python make_kits.py --status
```

---

## Phases

### Phase 0 — Dry run ✅ DONE
- 470 kits scanned (391 drum, 79 synth-spread, 0 skipped)

---

### Phase 1 — `drumkit/` + `blocks/`

Build one batch at a time. Script auto-skips already-built kits (safe to re-run).
Log output with: `... 2>&1 | tee /tmp/sp404mk2_ffN.log`

| Batch | Letters | Kits | Status | Command |
|-------|---------|------|--------|---------|
| 1 | 4, A, B | 58 | ⬜ PENDING | `python make_kits.py --batch 1` |
| 2 | C, D, E | 89 | ⬜ PENDING | `python make_kits.py --batch 2` |
| 3 | F–L     | 95 | ⬜ PENDING | `python make_kits.py --batch 3` |
| 4 | M–R    | 104 | ⬜ PENDING | `python make_kits.py --batch 4` |
| 5 | S–W     | 57 | ⬜ PENDING | `python make_kits.py --batch 5` |
| 6 | Y, Z    | 67 | ⬜ PENDING | `python make_kits.py --batch 6` |

**Monster kits** (also build category blocks inline):
- Roland MC-909 (849 files), Roland TR-909 (474 files), Alesis SR16 (237 files), others ≥100

---

### Phase 2 — `super/` (run after ALL batches done)

```
python make_kits.py --super-only
```

| Bank | Contents | Status |
|------|----------|--------|
| SUPER_KICK | 1 kick per machine (≤16) | ⬜ |
| SUPER_SNARE | 1 snare per machine | ⬜ |
| SUPER_CLOSED_HH | 1 closed hat per machine | ⬜ |
| SUPER_OPEN_HH | 1 open hat per machine | ⬜ |
| SUPER_CLAP | 1 clap per machine | ⬜ |
| SUPER_PERC | 1 perc per machine | ⬜ |

---

## Update this file after each batch

Replace `⬜ PENDING` → `✅ DONE` for each batch row when complete.
