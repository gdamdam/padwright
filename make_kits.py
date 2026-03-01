#!/usr/bin/env python3
"""
Build SP-404 MK2 drum kits from sample packs.
Output: /Volumes/eight/MUSIC_PRODUCTION/SAMPLES_SP404MK2/
Each kit: folder with 01_kick.wav ... 12_perc.wav (16-bit / 48kHz / mono WAV)
"""

import os
import re
import subprocess

OUTPUT_DIR = "/Volumes/eight/MUSIC_PRODUCTION/SAMPLES_SP404MK2"
SFM = "/Volumes/eight/MUSIC_PRODUCTION/SAMPLES/SamplesFromMars"
SMP = "/Volumes/eight/MUSIC_PRODUCTION/SAMPLES"

PADS = [
    (1,  "kick"),
    (2,  "snare"),
    (3,  "closed_hh"),
    (4,  "open_hh"),
    (5,  "low_tom"),
    (6,  "mid_tom"),
    (7,  "hi_tom"),
    (8,  "crash"),
    (9,  "rim"),
    (10, "clap"),
    (11, "cowbell"),
    (12, "perc"),
]

# Ordered classifiers — first match wins.
# Keywords are checked against the full lowercased file path.
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


def collect_wavs(root):
    """Return sorted list of all audio files under root (no hidden files)."""
    result = []
    if not os.path.isdir(root):
        return result
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            if fn.startswith('.'):
                continue
            if fn.lower().endswith(('.wav', '.aif', '.aiff')):
                result.append(os.path.join(dirpath, fn))
    return sorted(result)


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
    """Pick the middle file from a sorted list (avoids extremes)."""
    if not candidates:
        return None
    s = sorted(candidates)
    return s[len(s) // 2]


def export(src, dst):
    """Convert src to 16-bit / 48kHz / mono WAV."""
    cmd = [
        "ffmpeg", "-y", "-i", src,
        "-ac", "1", "-ar", "48000", "-sample_fmt", "s16",
        dst
    ]
    r = subprocess.run(cmd, capture_output=True)
    return r.returncode == 0


def sanitize_name(s):
    """Make a string safe for use in filenames (max 20 chars)."""
    s = re.sub(r'[^a-zA-Z0-9]', '_', s)
    s = re.sub(r'_+', '_', s).strip('_')
    return s[:20] or 'pad'


def build_synth_kit(kit_name, wav_root, output_subdir, max_pads=12):
    """Build a kit by picking one sample per first-level subfolder (patch), evenly sampled."""
    out_dir = os.path.join(OUTPUT_DIR, output_subdir, kit_name)
    os.makedirs(out_dir, exist_ok=True)

    wavs = collect_wavs(wav_root)
    if not wavs:
        print(f"  !! no WAV files found at: {wav_root}")
        return 0

    # Group by first-level subfolder relative to wav_root
    groups = {}
    for f in wavs:
        rel = os.path.relpath(f, wav_root)
        parts = rel.split(os.sep)
        group = parts[0] if len(parts) > 1 else '_root'
        groups.setdefault(group, []).append(f)

    group_names = sorted(groups.keys())

    if len(group_names) == 1 and group_names[0] == '_root':
        # Flat folder: spread evenly across pads
        all_files = sorted(groups['_root'])
        if len(all_files) <= max_pads:
            picks = [(os.path.splitext(os.path.basename(f))[0], f) for f in all_files]
        else:
            step = len(all_files) / max_pads
            picks = [(os.path.splitext(os.path.basename(all_files[int(i * step)]))[0],
                      all_files[int(i * step)]) for i in range(max_pads)]
    else:
        # One pick per subfolder group, evenly sampled if more than max_pads
        all_picks = [(name, pick_file(files)) for name, files in sorted(groups.items())]
        if len(all_picks) > max_pads:
            step = len(all_picks) / max_pads
            picks = [all_picks[int(i * step)] for i in range(max_pads)]
        else:
            picks = all_picks

    picks = picks[:max_pads]

    exported = 0
    for i, (label, src) in enumerate(picks, 1):
        label_clean = sanitize_name(label)
        dst = os.path.join(out_dir, f"{i:02d}_{label_clean}.wav")
        ok = export(src, dst)
        src_short = "/".join(src.replace(SFM, "SFM").replace(SMP, "SMP").split("/")[-3:])
        status = "OK  " if ok else "FAIL"
        print(f"  {i:02d}_{label_clean:<20} {status}  {src_short}")
        if ok:
            exported += 1
    return exported


def build_kit(kit_name, wav_root, is_special=False):
    out_dir = os.path.join(OUTPUT_DIR, "drumkit", kit_name)
    os.makedirs(out_dir, exist_ok=True)

    wavs = collect_wavs(wav_root)
    if not wavs:
        print(f"  !! no WAV files found at: {wav_root}")
        return 0

    # Classify all files into drum type buckets
    candidates = {pad_name: [] for _, pad_name in PADS}
    unclassified = []

    for f in wavs:
        t = classify(f)
        if t and t in candidates:
            candidates[t].append(f)
        else:
            unclassified.append(f)

    # For special/non-drum kits: spread unclassified across empty pads
    if is_special and unclassified:
        empty_pads = [pn for _, pn in PADS if not candidates[pn]]
        for i, pad_name in enumerate(empty_pads):
            if i < len(unclassified):
                candidates[pad_name].append(unclassified[i])

    # Generic tom distribution: spread plain "tom" files across empty tom pads
    tom_pads = ["low_tom", "mid_tom", "hi_tom"]
    tom_files = [f for f in unclassified if "tom" in f.lower()]
    tom_idx = 0
    for pn in tom_pads:
        if not candidates[pn] and tom_idx < len(tom_files):
            candidates[pn].append(tom_files[tom_idx])
            tom_idx += 1

    # Export
    exported = 0
    for pad_num, pad_name in PADS:
        chosen = pick_file(candidates[pad_name])
        if not chosen:
            print(f"  {pad_num:02d}_{pad_name:<12} --")
            continue
        dst = os.path.join(out_dir, f"{pad_num:02d}_{pad_name}.wav")
        ok = export(chosen, dst)
        src_short = "/".join(chosen.replace(SFM, "SFM").replace(SMP, "SMP").split("/")[-3:])
        status = "OK  " if ok else "FAIL"
        print(f"  {pad_num:02d}_{pad_name:<12} {status}  {src_short}")
        if ok:
            exported += 1

    return exported


# ── Kit definitions ────────────────────────────────────────────────────────────

KITS_MAIN = [
    # ── SamplesFromMars: classic drum machines ────────────────────────────────
    ("01_TR505",             f"{SFM}/505 From Mars/WAV/01. Individual Hits"),
    ("02_TR606",             f"{SFM}/606 From Mars/WAV/01. Individual Hits"),
    ("03_TR626",             f"{SFM}/626 From Mars/WAV/01. Individual Hits"),
    ("04_TR707",             f"{SFM}/707 From Mars/WAV/01. Individual Hits"),
    ("05_TR808",             f"{SFM}/808 From Mars/WAV/01. Individual Hits"),
    ("06_TR808_Legacy",      f"{SFM}/808 From Mars - Legacy/WAV/1. Individual Hits"),
    ("07_TR909",             f"{SFM}/909 From Mars/WAV/Individual Hits"),
    ("08_CR78",              f"{SFM}/CR78 From Mars/WAV/One Shots/Individual Hits/Original/Clean"),
    ("09_DMX",               f"{SFM}/DMX From Mars/WAV/01. Individual Hits/DMX"),
    ("10_DrBohm",            f"{SFM}/Dr Bohm From Mars/WAV/Individual Hits/Dr Bohm"),
    ("11_Drumtrax",          f"{SFM}/Drumtrax From Mars/WAV/01. Individual Hits/Digital Clean"),
    ("12_Drumulator",        f"{SFM}/Drumulator From Mars/WAV/01. Individual Hits/Drumulator"),
    ("13_JupiterDrums",      f"{SFM}/Jupiter Drums From Mars/WAV/01. Individual Hits"),
    ("14_LinnDrum",          f"{SFM}/Lindrum From Mars/WAV/01. Individual Hits"),
    ("15_LinnDrum_Legacy",   f"{SFM}/Lindrum From Mars - Legacy/WAV/01. Individual Hits"),
    ("16_Linn60",            f"{SFM}/Linn60 From Mars/WAV/01. Individual Hits"),
    ("17_LM1",               f"{SFM}/LM1 From Mars/WAV/01. Individual Hits"),
    ("18_ModularDrums",      f"{SFM}/Modular Drums From Mars/WAV/01. Individual Hits"),
    ("19_MPC1",              f"{SFM}/MPC1 From Mars/WAV/01. Individual Hits"),
    ("20_MPC3000",           f"{SFM}/MPC3000 From Mars/WAV/01. Individual Hits"),
    ("21_MPC60",             f"{SFM}/MPC60 From Mars/WAV/Individual Hits"),
    ("22_MR10",              f"{SFM}/MR10 From Mars/WAV/01. Individual Hits"),
    ("23_Pulsar",            f"{SFM}/Pulsar From Mars/WAV/01. One Shots/01. Individual Hits"),
    ("24_Rhythm700",         f"{SFM}/Rhythm From Mars/WAV/Individual Hits"),
    ("25_SDS800",            f"{SFM}/SDS800 From Mars/WAV/Individual Hits"),
    ("26_SDSV",              f"{SFM}/SDSV From Mars/WAV/Individual Hits"),
    ("27_SP909",             f"{SFM}/SP 909 From Mars/WAV/01. Individual Hits"),
    ("28_SP1200",            f"{SFM}/SP1200 From Mars/WAV/Drums/Individual Hits"),
    ("29_Synare",            f"{SFM}/Synare From Mars/WAV/01. One Hits"),
    ("30_TOM",               f"{SFM}/TOM From Mars/WAV/01. Individual Hits/01. TOM"),
    ("31_VinylDrumMachines", f"{SFM}/Vinyl Drum Machines From Mars/WAV/01. Individual Hits"),
    ("32_VinylDrums",        f"{SFM}/Vinyl Drums From Mars/WAV/01. Individual Hits"),
    ("33_Viscount",          f"{SFM}/Viscount From Mars/WAV/01. Individual Hits"),
    ("34_Wendel",            f"{SFM}/Wendel From Mars/WAV/01. Individual Hits"),
    # ── Other packs ───────────────────────────────────────────────────────────
    ("35_Psymun",            f"{SMP}/psymun samples 4"),
    ("36_XLNT_QuestForBass", f"{SMP}/XLNT Quest For Bass/Drums"),
    ("37_Burial_Style",      f"{SMP}/Samples by Vanity In The Style Of Vol.23 BURIAL WAV"),
    ("38_Cr2_Bratwave",      f"{SMP}/Sample Tools by Cr2 bratwave beats (incl. Vocals)/One_Shots/Drum_One_Shots"),
    ("39_Cr2_UKGarage",      f"{SMP}/Sample Tools by Cr2 UK Garage & Vocals/One_Shots/Drum_One_Shots"),
    ("40_Ghosthack_Techno",  f"{SMP}/Ghosthack - AC2023 - Day 1 - Techno Pack/One Shots"),
    ("41_HighTech_House",    f"{SMP}/High Tech Minimal and Melodic House"),
    ("42_FEM_808_909",       f"{SMP}/FEM sample pack/2. Drum hits"),
    ("43_Zenhiser_Convex",   f"{SMP}/Zenhiser Convex Breakbeat & Electro/one_shots"),
    ("44_Oversampled",       f"{SMP}/Oversampled Super Heavy Power Drum Fills WAV/Drum Fill Creator_s Kit"),
    ("45_PO12",              f"{SMP}/Audio Wanderer - PO-12 Drum Kit (Sample Library)"),
    ("46_RARE_Percussion",   f"{SMP}/RARE Percussion AmaPercussion vol.2/ONESHOTS"),
]

KITS_SPECIAL = [
    ("47_101_FromMars",   f"{SFM}/101 From Mars/WAV"),
    ("48_360_FromMars",   f"{SFM}/360 From Mars/WAV"),
    ("49_727_WorldPerc",  f"{SFM}/727 From Mars/WAV/01. Clean/01. Hits"),
    ("50_Micro_FromMars", f"{SFM}/Micro From Mars/WAV"),
    ("51_Minipops",       f"{SFM}/Minipops Snacks From Mars/WAV/02. One Hits"),
    ("52_SK1_FromMars",   f"{SFM}/SK1 From Mars/WAV"),
]


# ── Non-drum kit definitions ────────────────────────────────────────────────

KITS_SYNTH = [
    # ── SamplesFromMars: classic synths (one sound per patch/subfolder) ───────
    ("01_Mini_Moog",      f"{SFM}/Mini From Mars/WAV"),
    ("02_OB_Oberheim",    f"{SFM}/OB From Mars/WAV"),
    ("03_Sid_C64",        f"{SFM}/Sid From Mars/WAV"),
    ("04_Soviet_Synths",  f"{SFM}/Soviet Synths From Mars/WAV"),
    ("05_SH5_Roland",     f"{SFM}/SH5 From Mars/WAV"),
    ("06_MS10_Korg",      f"{SFM}/MS10 From Mars/WAV"),
    ("07_SYS100M_Roland", f"{SFM}/SYS100M From Mars/WAV"),
    ("08_Voyetra",        f"{SFM}/Voyetra From Mars/WAV"),
    ("09_VP330_Roland",   f"{SFM}/VP330 From Mars/WAV"),
    ("10_Wasp_EDP",       f"{SFM}/Wasp From Mars/WAV"),
    ("11_DX7_Yamaha",     f"{SFM}/DX From Mars/WAV/Individual Hits"),
    ("12_DX100_Yamaha",   f"{SFM}/DX100 From Mars/WAV"),
    ("13_Kawaii_Dreams",  f"{SFM}/Kawaii Dreams From Mars/WAV"),
    ("14_Acid_TB303",     f"{SFM}/Acid From Mars/WAV/Acid Synths"),
    ("15_Vinyl_Synths",   f"{SFM}/Vinyl Synths From Mars/WAV"),
    ("16_Mirage_EMU",     f"{SFM}/Mirage From Mars/WAV"),
    ("17_S612_EMU",       f"{SFM}/S612 From Mars/WAV/Synths"),
    ("18_ARP_2600",       f"{SFM}/2600 From Mars/WAV/Instrument Samples"),
]

KITS_BASS = [
    ("01_808_F1LTHY",     f"{SMP}/F1LTHY x LUKRATIVE KIT [VOL II]/808s"),
]

KITS_FX = [
    ("01_Found_Sounds",      f"{SFM}/Found Sounds From Mars/WAV"),
    ("02_Foley",             f"{SMP}/Big Room Sound Essential Foley Sounds"),
    ("03_Tape_Fragments",    f"{SFM}/Tape Fragments From Mars/WAV"),
    ("04_Trumpet_Fragments", f"{SFM}/Trumpet Fragments From Mars/WAV"),
]

KITS_PERC = [
    ("01_Underdog_Perc",  f"{SMP}/2023 Underdog ear candy"),
]

KITS_VOCAL = [
    ("01_Afrobeat_Vocals", f"{SMP}/Ultra Afrobeat Vocals"),
]

KITS_MPC = [
    ("01_MPC2000_Snacks",  f"{SFM}/MPC2000 Snacks From Mars/WAV"),
    ("02_S950_Keys",       f"{SFM}/S950 Snacks From Mars/WAV/Keys"),
]

ALL_NON_DRUM = [
    ("SYNTH",  KITS_SYNTH,  "synth"),
    ("BASS",   KITS_BASS,   "bass"),
    ("FX",     KITS_FX,     "fx"),
    ("PERC",   KITS_PERC,   "perc"),
    ("VOCAL",  KITS_VOCAL,  "vocal"),
    ("MPC",    KITS_MPC,    "mpc"),
]


def main(build_drums=True, build_non_drum=True):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"Output: {OUTPUT_DIR}\n")

    total_kits = 0
    total_samples = 0

    if build_drums:
        print("=" * 60)
        print("DRUM MACHINE KITS (46)")
        print("=" * 60)
        for name, root in KITS_MAIN:
            print(f"\n{name}")
            n = build_kit(name, root, is_special=False)
            total_samples += n
            total_kits += 1

        print("\n" + "=" * 60)
        print("SPECIAL / NON-STANDARD KITS (6)")
        print("=" * 60)
        for name, root in KITS_SPECIAL:
            print(f"\n{name}")
            n = build_kit(name, root, is_special=True)
            total_samples += n
            total_kits += 1

    if build_non_drum:
        for category_name, kit_list, subdir in ALL_NON_DRUM:
            print("\n" + "=" * 60)
            print(f"{category_name} KITS ({len(kit_list)})")
            print("=" * 60)
            for name, root in kit_list:
                print(f"\n{name}")
                n = build_synth_kit(name, root, subdir)
                total_samples += n
                total_kits += 1

    print(f"\n{'=' * 60}")
    print(f"DONE — {total_kits} kits built, {total_samples} samples exported")
    print(f"Output: {OUTPUT_DIR}")


if __name__ == "__main__":
    import sys
    args = sys.argv[1:]

    # Flags: --drums / --non-drum / --all (default: --all)
    build_drums    = "--drums"    in args or "--all" in args or not args
    build_non_drum = "--non-drum" in args or "--all" in args or not args

    # Kit-prefix filter (e.g. python make_kits.py 03 12 14)
    targets = [a for a in args if not a.startswith("--")]
    if targets:
        KITS_MAIN[:]    = [(n, r) for n, r in KITS_MAIN    if any(n.startswith(t) for t in targets)]
        KITS_SPECIAL[:] = [(n, r) for n, r in KITS_SPECIAL if any(n.startswith(t) for t in targets)]
        for _, kit_list, _ in ALL_NON_DRUM:
            kit_list[:] = [(n, r) for n, r in kit_list if any(n.startswith(t) for t in targets)]
        build_drums    = bool(KITS_MAIN or KITS_SPECIAL)
        build_non_drum = any(kit_list for _, kit_list, _ in ALL_NON_DRUM)

    main(build_drums=build_drums, build_non_drum=build_non_drum)
