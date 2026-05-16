"""Shared core for SP-404 MK2 kit/loop builders.

This module is the single source of truth for things that used to be
duplicated across make_kits.py, make_breakbeats.py, and reorder_kits.py:

- Pad layout (SOUND_SLOTS, SLOT_NAMES, SUPER_FILES)
- Drum-type classifier (classify, CLASSIFIERS)
- Audio helpers (export, make_silent_wav, list_audio, extract_audio)
- String helpers (sanitize, shorten_name, evenly_sample)
- The terminal UI dashboard (UI)
- Manifest + pad-map writers (write_manifest, write_pad_map)
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import wave
import zipfile
from collections import deque
from pathlib import Path

# ── Audio constants ───────────────────────────────────────────────────────────
AUDIO_EXTS = {".wav", ".aif", ".aiff"}
SR = 48000
SILENT_MS = 50

# ── Pad layout ────────────────────────────────────────────────────────────────
# Files 01-04 are silent placeholders (top row). Files 05-16 are sounds.
SOUND_SLOTS: list[tuple[int, str]] = [
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
SLOT_NAMES: list[str] = [t for _, t in SOUND_SLOTS]

# Already-exported kit files used for cross-machine super banks
SUPER_FILES: dict[str, str] = {
    "kick":      "13_kick.wav",
    "snare":     "14_snare.wav",
    "closed_hh": "15_closed_hh.wav",
    "open_hh":   "16_open_hh.wav",
    "clap":      "06_clap.wav",
    "perc":      "08_perc.wav",
}

# ── Classifier ────────────────────────────────────────────────────────────────
CLASSIFIERS: list[tuple[str, list[str]]] = [
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


def classify(filepath: str) -> str | None:
    """Return drum type string or None using keyword matching."""
    p = filepath.lower().replace("\\", "/")
    stem = Path(p).stem.lower()
    compact = re.sub(r"[^a-z0-9]", "", stem)
    tokens = [t for t in re.split(r"[^a-z0-9]+", stem) if t]

    if compact.startswith("bd") or "bd" in tokens:
        return "kick"
    if compact.startswith("sd") or "sd" in tokens:
        return "snare"
    if compact.startswith("hho") or "hho" in tokens or "ophh" in compact:
        return "open_hh"
    if compact.startswith("hhc") or "hhc" in tokens or "clhh" in compact:
        return "closed_hh"
    if compact.startswith("hcp") or "handclap" in compact:
        return "clap"
    # Roland-style "Hat_C03.wav" / "Hat_O02.wav" — common in TR-606/808/909 packs
    if compact.startswith("hatc"):
        return "closed_hh"
    if compact.startswith("hato"):
        return "open_hh"
    # Tom prefix variants: "TomLo04" / "TomHi_OD" / "TomMid01"
    if compact.startswith("tomlo") or compact.startswith("tomlow"):
        return "low_tom"
    if compact.startswith("tommi") or compact.startswith("tommid"):
        return "mid_tom"
    if compact.startswith("tomhi") or compact.startswith("tomhigh"):
        return "hi_tom"
    if compact in ("lt", "lotom") or compact.startswith("lt"):
        return "low_tom"
    if compact in ("mt", "midtom") or compact.startswith("mt"):
        return "mid_tom"
    if compact in ("ht", "hitom", "hitomtom", "hightom") or compact.startswith("ht"):
        return "hi_tom"
    if compact.startswith("crs") or compact.startswith("crash"):
        return "crash"
    if compact.startswith("rid") or compact.startswith("ride") or compact.startswith("cymb"):
        return "crash"
    if compact.startswith("rim"):
        return "rim"
    if compact.startswith("cow"):
        return "cowbell"
    if compact.startswith("tam") or compact.startswith("tamb"):
        return "perc"

    for drum_type, keywords in CLASSIFIERS:
        for kw in keywords:
            if kw in p:
                return drum_type

    if "/tom" in p or "_tom" in p or " tom" in p or "tom." in p:
        return "low_tom"
    if "/hh" in p or "_hh" in p or "hat" in p:
        return "closed_hh"
    return None


def pick_file(candidates: list[str]) -> str | None:
    """Pick the middle file from a sorted list (avoids extreme variants)."""
    if not candidates:
        return None
    s = sorted(candidates)
    return s[len(s) // 2]


# ── Audio I/O ─────────────────────────────────────────────────────────────────

def _ffmpeg_bin() -> str:
    """Path to ffmpeg. Honors $FFMPEG_PATH so bundled apps can ship their own."""
    return os.environ.get("FFMPEG_PATH") or "ffmpeg"


def _ffprobe_bin() -> str:
    """Path to ffprobe. Honors $FFPROBE_PATH so bundled apps can ship their own."""
    return os.environ.get("FFPROBE_PATH") or "ffprobe"


def export(src: str, dst: str, channels: int = 1, sr: int = SR) -> bool:
    """Convert src → 16-bit / sr / mono|stereo WAV via ffmpeg."""
    cmd = [_ffmpeg_bin(), "-y", "-i", str(src),
           "-ac", str(channels), "-ar", str(sr), "-sample_fmt", "s16", str(dst)]
    r = subprocess.run(cmd, capture_output=True)
    return r.returncode == 0


def make_silent_wav(path: str, sr: int = SR, ms: int = SILENT_MS) -> None:
    """Write a minimal silent 16-bit mono WAV."""
    n = int(sr * ms / 1000)
    with wave.open(path, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(b"\x00" * n * 2)


def list_audio(pack_path: str | Path) -> list[str]:
    """List relative audio file names inside a zip or directory (sorted)."""
    pack_path = Path(pack_path)
    if pack_path.suffix.lower() == ".zip":
        with zipfile.ZipFile(pack_path) as zf:
            return sorted(
                n for n in zf.namelist()
                if not os.path.basename(n).startswith(".")
                and Path(n).suffix.lower() in AUDIO_EXTS
                and not n.endswith("/")
            )
    return sorted(
        str(f.relative_to(pack_path))
        for f in pack_path.rglob("*")
        if f.is_file()
        and not f.name.startswith(".")
        and f.suffix.lower() in AUDIO_EXTS
    )


def extract_audio(pack_path: str | Path, tmp_dir: str) -> tuple[list[str], dict[str, str]]:
    """
    Extract/copy all audio files into tmp_dir.

    Returns `(sorted_extracted_paths, source_map)` where source_map maps each
    extracted path back to the *original* source:
      - unzipped pack:  absolute path to the original file
      - zip pack:       "<zip_path>#<internal_member>" — informational marker
                        (the underlying file is gone with the temp dir, but
                        the manifest can still record where it came from)
    """
    pack_path = Path(pack_path)
    out: list[str] = []
    source_map: dict[str, str] = {}
    if pack_path.suffix.lower() == ".zip":
        with zipfile.ZipFile(pack_path) as zf:
            for member in zf.namelist():
                if (not os.path.basename(member).startswith(".")
                        and Path(member).suffix.lower() in AUDIO_EXTS
                        and not member.endswith("/")):
                    zf.extract(member, tmp_dir)
                    extracted = os.path.join(tmp_dir, member)
                    out.append(extracted)
                    source_map[extracted] = f"{pack_path}#{member}"
    else:
        for f in sorted(pack_path.rglob("*")):
            if f.is_file() and not f.name.startswith(".") \
                    and f.suffix.lower() in AUDIO_EXTS:
                rel = f.relative_to(pack_path)
                dst = Path(tmp_dir) / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(f), str(dst))
                extracted = str(dst)
                out.append(extracted)
                source_map[extracted] = str(f.resolve())
    return sorted(out), source_map


# ── String helpers ────────────────────────────────────────────────────────────

def sanitize(s: str, n: int = 20) -> str:
    s = re.sub(r"[^a-zA-Z0-9]", "_", s)
    return re.sub(r"_+", "_", s).strip("_")[:n] or "pad"


def shorten_name(stem: str, n: int = 18) -> str:
    """Strip common pack prefixes/BPM suffixes and shorten."""
    stem = re.sub(r"(?i)^cymatics\s*-\s*", "", stem)
    stem = re.sub(r"\s*[-–]\s*\d+\s*BPM.*$", "", stem, flags=re.IGNORECASE)
    stem = re.sub(r"\s+\d+\s*BPM.*$", "", stem, flags=re.IGNORECASE)
    return sanitize(stem, n)


def evenly_sample(items: list, n: int) -> list:
    """Pick n items evenly spaced from items."""
    if len(items) <= n:
        return items
    step = len(items) / n
    return [items[int(i * step)] for i in range(n)]


def ffprobe_info(path: str | Path) -> dict:
    """Return {duration, sample_rate, channels} via ffprobe (best effort)."""
    cmd = [_ffprobe_bin(), "-v", "error", "-select_streams", "a:0",
           "-show_entries", "stream=sample_rate,channels:format=duration",
           "-of", "json", str(path)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            return {}
        data = json.loads(r.stdout)
        stream = (data.get("streams") or [{}])[0]
        fmt = data.get("format") or {}
        dur = fmt.get("duration")
        return {
            "duration_s": float(dur) if dur else None,
            "sample_rate": int(stream["sample_rate"]) if stream.get("sample_rate") else None,
            "channels": int(stream["channels"]) if stream.get("channels") else None,
        }
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError, ValueError):
        return {}


def sha256_file(path: str | Path, chunk: int = 1 << 20) -> str | None:
    """Return hex sha256 of file contents, or None on error."""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(chunk), b""):
                h.update(block)
        return h.hexdigest()
    except OSError:
        return None


# ── Bank kinds ────────────────────────────────────────────────────────────────

# A "kind" tells the exporter how to lay out a bank:
#   drumkit   — pads 1-4 silent, pads 5-16 are SOUND_SLOTS by type, mono
#   loop_bank — all 16 pads are loops, stereo
#   block     — all 16 pads are one category (e.g. kicks), mono
#   super     — all 16 pads are one category across machines, mono
KIND_DRUMKIT  = "drumkit"
KIND_LOOPBANK = "loop_bank"
KIND_BLOCK    = "block"
KIND_SUPER    = "super"

_STEREO_KINDS = {KIND_LOOPBANK}


# ── Manifest + pad map ────────────────────────────────────────────────────────

MANIFEST_VERSION = 1


def write_manifest(kit_dir: str | Path, pads: list[dict], meta: dict | None = None) -> Path:
    """
    Write manifest.json describing a 16-pad bank.

    Each entry in `pads` should already be a dict shaped like:
      {
        "pad": 1..16,
        "filename": "13_kick.wav",
        "type": "kick" | "loop" | "empty" | None,
        "source": "/abs/path/to/original" | None,
        "source_basename": "...",
        "kind": "auto" | "manual" | "silent" | "swap",
        "sha256": "...",
        "duration_s": float | None,
        "sample_rate": int | None,
        "channels": int | None,
      }

    Missing fields are tolerated. Returns the manifest path.
    """
    kit_dir = Path(kit_dir)
    kit_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "manifest_version": MANIFEST_VERSION,
        "kit_name": kit_dir.name,
        "generated_at": int(time.time()),
        "meta": meta or {},
        "pads": sorted(pads, key=lambda p: p.get("pad", 0)),
    }
    path = kit_dir / "manifest.json"
    with open(path, "w") as f:
        json.dump(payload, f, indent=2, sort_keys=False)
        f.write("\n")
    return path


_TYPE_COLORS = {
    "kick":      "#7a3b3b",
    "snare":     "#8a6a2e",
    "closed_hh": "#3b6a7a",
    "open_hh":   "#3b557a",
    "clap":      "#7a3b6a",
    "perc":      "#3b7a55",
    "rim":       "#555555",
    "cowbell":   "#7a7a3b",
    "low_tom":   "#5a3b7a",
    "mid_tom":   "#6a3b7a",
    "hi_tom":    "#7a3b7a",
    "crash":     "#3b7a7a",
    "loop":      "#3b7a3b",
    "empty":     "#222222",
}


def write_pad_map(kit_dir: str | Path, pads: list[dict], meta: dict | None = None) -> Path:
    """
    Write pad-map.html: a static 4x4 grid that audits the bank in a browser.

    Each cell shows pad number, type, source basename, and an <audio> tag
    pointing at the local exported WAV (relative path — works when the HTML
    is opened directly from Finder).
    """
    kit_dir = Path(kit_dir)
    kit_name = kit_dir.name
    meta = meta or {}

    # Roland SP layout: pad 1 = top-left, pad 16 = bottom-right.
    by_pad = {p.get("pad"): p for p in pads}
    rows = []
    for r in range(0, 4):
        cells = []
        for c in range(0, 4):
            pad_num = r * 4 + c + 1
            p = by_pad.get(pad_num, {"pad": pad_num, "type": "empty", "filename": ""})
            t = (p.get("type") or "empty")
            color = _TYPE_COLORS.get(t, "#444")
            src_bn = p.get("source_basename") or ""
            fname = p.get("filename") or ""
            dur = p.get("duration_s")
            dur_s = f"{dur:.2f}s" if isinstance(dur, (int, float)) else ""
            audio = f'<audio controls preload="none" src="{fname}"></audio>' if fname else ""
            cells.append(f"""
              <td style="background:{color};">
                <div class="pn">{pad_num:02d}</div>
                <div class="ty">{t}</div>
                <div class="fn">{fname}</div>
                <div class="sr" title="{src_bn}">{src_bn}</div>
                <div class="du">{dur_s}</div>
                {audio}
              </td>""")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    grid = "\n".join(rows)

    meta_html = ""
    if meta:
        items = "".join(f"<li><b>{k}</b>: {v}</li>" for k, v in meta.items())
        meta_html = f"<ul class='meta'>{items}</ul>"

    html = f"""<!doctype html>
<html><head><meta charset="utf-8">
<title>{kit_name} — SP-404 MK2 pad map</title>
<style>
  body {{ font-family: -apple-system, system-ui, sans-serif;
         background:#111; color:#eee; padding:20px; margin:0; }}
  h1 {{ font-size:18px; margin:0 0 12px; }}
  table {{ border-collapse:separate; border-spacing:6px; width:100%; }}
  td {{ width:25%; vertical-align:top; padding:10px; border-radius:8px;
        color:#fff; font-size:12px; line-height:1.35; }}
  .pn {{ font-size:20px; font-weight:700; opacity:.85; }}
  .ty {{ font-size:11px; text-transform:uppercase; letter-spacing:.08em; opacity:.85; }}
  .fn {{ font-family: ui-monospace, Menlo, monospace; font-size:11px; margin-top:6px; word-break:break-all; }}
  .sr {{ font-size:10px; opacity:.7; margin-top:4px; word-break:break-all; }}
  .du {{ font-size:10px; opacity:.6; margin-top:2px; }}
  audio {{ width:100%; margin-top:6px; height:28px; }}
  ul.meta {{ list-style:none; padding:0; margin:0 0 12px; font-size:12px; opacity:.8; }}
  ul.meta li {{ display:inline-block; margin-right:14px; }}
</style></head><body>
<h1>{kit_name}</h1>
{meta_html}
<table>{grid}</table>
</body></html>
"""
    path = kit_dir / "pad-map.html"
    with open(path, "w") as f:
        f.write(html)
    return path


# ── Exporter: pad specs → bank on disk ────────────────────────────────────────

def channels_for_kind(kind: str) -> int:
    return 2 if kind in _STEREO_KINDS else 1


def _filename_for(kind: str, pad: int, type_label: str | None, source: str | None) -> str:
    """
    Pick a stable on-disk filename for a pad.

    drumkit:    01-04 → "0N_empty.wav"; 05-16 → "NN_<slot_type>.wav"
                       (slot_type comes from SOUND_SLOTS when type is unset).
    loop_bank:  "NN_<short(source_stem)>.wav" or "NN_loop.wav" / "NN_empty.wav".
    block/super:"NN_<sanitize(type_or_stem)>.wav".
    """
    n = f"{pad:02d}"
    if kind == KIND_DRUMKIT:
        if pad <= 4 and not source:
            return f"{n}_empty.wav"
        slot_lookup = {p: t for p, t in SOUND_SLOTS}
        slot_t = type_label or slot_lookup.get(pad) or "pad"
        return f"{n}_{slot_t}.wav"
    if kind == KIND_LOOPBANK:
        if not source:
            return f"{n}_empty.wav"
        return f"{n}_{shorten_name(Path(source).stem)}.wav"
    # block / super
    label = type_label or (sanitize(Path(source).stem, 14) if source else "pad")
    return f"{n}_{label}.wav"


def build_from_pad_list(
    dst_dir: str | Path,
    pad_specs: list[dict],
    kind: str,
    meta_extra: dict | None = None,
    silent_wav_path: str | None = None,
    dry_run: bool = False,
) -> list[dict]:
    """
    Export a bank from a list of pad specs and write manifest + pad-map.

    pad_specs: each entry shaped like {"pad": int, "source": str|None,
               "type": str|None}. Missing pad numbers are filled per `kind`
               (silent for drumkit pads 1-4 and any gaps; silent for loop_bank
               gaps; just skipped for block/super).

    Returns the manifest pad list that was written. With dry_run=True nothing
    is written; the function returns the would-be manifest entries.
    """
    dst_dir = Path(dst_dir)
    ch = channels_for_kind(kind)

    by_pad: dict[int, dict] = {}
    for spec in pad_specs:
        if "pad" not in spec:
            continue
        by_pad[int(spec["pad"])] = spec

    # Determine which pad numbers belong to this bank.
    if kind in (KIND_DRUMKIT, KIND_LOOPBANK):
        pad_range = list(range(1, 17))
    else:
        pad_range = sorted(by_pad.keys()) or list(range(1, 17))

    if not dry_run:
        dst_dir.mkdir(parents=True, exist_ok=True)
        if silent_wav_path is None:
            silent_wav_path = str(dst_dir / ".silent.wav")
        make_silent_wav(silent_wav_path)

    out_pads: list[dict] = []
    for pad in pad_range:
        spec = by_pad.get(pad, {})
        source = spec.get("source") or None
        type_label = spec.get("type")
        fname = _filename_for(kind, pad, type_label, source)
        dst = dst_dir / fname

        if dry_run:
            action = "silent" if not source else f"export {source}"
            print(f"  pad {pad:02d}  {fname:<24}  {action}")
            out_pads.append({
                "pad": pad, "filename": fname,
                "type": type_label or ("empty" if not source else None),
                "source": source,
                "source_basename": os.path.basename(source) if source else None,
                "kind": "silent" if not source else "auto",
            })
            continue

        if not source:
            shutil.copy(silent_wav_path, dst)
            out_pads.append({
                "pad": pad, "filename": fname, "type": "empty",
                "source": None, "source_basename": None,
                "kind": "silent",
            })
            print(f"  pad {pad:02d}  {fname:<24}  SILENT")
            continue

        ok = export(source, str(dst), channels=ch)
        info = ffprobe_info(dst) if ok else {}
        out_pads.append({
            "pad": pad, "filename": fname,
            "type": type_label or ("loop" if kind == KIND_LOOPBANK else None),
            "source": source,
            "source_basename": os.path.basename(source),
            "kind": "auto" if ok else "fail",
            "sha256": sha256_file(dst) if ok else None,
            **info,
        })
        print(f"  pad {pad:02d}  {fname:<24}  {'OK' if ok else 'FAIL'}  {os.path.basename(source)}")

    if not dry_run:
        # Clean up the local silent placeholder so it doesn't pollute the bank.
        try:
            if silent_wav_path and silent_wav_path.startswith(str(dst_dir)):
                Path(silent_wav_path).unlink(missing_ok=True)
        except OSError:
            pass
        meta = {"kind": kind, **(meta_extra or {})}
        write_manifest(dst_dir, out_pads, meta=meta)
        write_pad_map(dst_dir, out_pads, meta=meta)

    return out_pads


def manifest_to_crate(manifest: dict) -> dict:
    """Project a manifest down to a crate: intent only (pad, source, type)."""
    meta = manifest.get("meta") or {}
    kind = meta.get("kind") or KIND_DRUMKIT
    pads = []
    for p in manifest.get("pads") or []:
        if not p.get("source"):
            continue   # silent/empty pads are implied
        pads.append({
            "pad": p.get("pad"),
            "source": p.get("source"),
            "type": p.get("type"),
        })
    return {
        "name": manifest.get("kit_name"),
        "kind": kind,
        "pads": sorted(pads, key=lambda x: x.get("pad", 0)),
    }


def load_crate(path: str | Path) -> dict:
    """Read a crate JSON file and validate the minimal shape."""
    with open(path) as f:
        crate = json.load(f)
    if "pads" not in crate or not isinstance(crate["pads"], list):
        raise ValueError(f"crate {path}: missing 'pads' list")
    crate.setdefault("kind", KIND_DRUMKIT)
    crate.setdefault("name", Path(path).stem)
    for i, p in enumerate(crate["pads"]):
        if "pad" not in p:
            raise ValueError(f"crate {path}: pads[{i}] missing 'pad'")
    return crate


# ── Terminal UI ───────────────────────────────────────────────────────────────

def _fmt_time(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"


class UI:
    """
    Split-screen TUI: ring-buffer log box + progress bar pinned to the bottom.

    Hijacks sys.stdout so print() output flows into the log box. Falls back to
    plain text when stdout is not a TTY.
    """
    LOG_H = 16

    def __init__(self, total: int):
        self.total = total
        self.done = 0
        self.start = time.time()
        self._name = ""
        self._buf: deque[str] = deque(maxlen=self.LOG_H)
        self._cur = ""
        self._real = sys.__stdout__
        self._tty = self._real.isatty()
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

    def _setup(self) -> None:
        scroll_end = self._rows - self._dash
        out = [f"\033[1;{scroll_end}r"]
        for r in range(scroll_end + 1, self._rows + 1):
            out.append(f"\033[{r};1H\033[2K")
        out.append(f"\033[{scroll_end};1H")
        self._real.write("".join(out))
        self._real.flush()
        self._redraw()

    def _bar_str(self) -> str:
        W = min(36, self._cols - 36)
        pct = self.done / self.total if self.total else 1.0
        filled = int(W * pct)
        bar = "█" * filled + "░" * (W - filled)
        elapsed = time.time() - self.start
        eta_s = ""
        if 0 < self.done < self.total:
            eta = elapsed / self.done * (self.total - self.done)
            eta_s = f"  eta {_fmt_time(eta)}"
        label = (self._name[:24] + "…") if len(self._name) > 25 else self._name
        return f"[{bar}] {self.done}/{self.total}  {_fmt_time(elapsed)}{eta_s}  {label}"

    def _redraw(self) -> None:
        cols = self._cols
        r0 = self._rows - self._dash + 1
        lines = list(self._buf)
        out = ["\033[s"]
        out.append(f"\033[{r0};1H\033[2K{'─' * cols}")
        for i in range(self.LOG_H):
            row = r0 + 1 + i
            text = (lines[i] if i < len(lines) else "")[:cols]
            out.append(f"\033[{row};1H\033[2K{text}")
        sep_row = r0 + 1 + self.LOG_H
        out.append(f"\033[{sep_row};1H\033[2K{'─' * cols}")
        out.append(f"\033[{self._rows};1H\033[2K{self._bar_str()}")
        out.append("\033[u")
        self._real.write("".join(out))
        self._real.flush()

    def write(self, text: str) -> None:
        if not self._tty:
            self._real.write(text)
            return
        parts = text.split("\n")
        self._cur += parts[0]
        for part in parts[1:]:
            self._buf.append(self._cur)
            self._cur = part
            self._redraw()

    def flush(self) -> None:
        self._real.flush()

    def clear(self) -> None:
        pass

    def update(self, name: str = "") -> None:
        self.done += 1
        self._name = name
        if self._tty:
            self._redraw()
        else:
            self._real.write(f"\r{self._bar_str()}\n")
            self._real.flush()

    def advance(self, n: int, name: str = "") -> None:
        self.done = min(self.done + n, self.total)
        self._name = name
        if self._tty:
            self._redraw()
        else:
            self._real.write(f"\r{self._bar_str()}\n")
            self._real.flush()

    def finish(self) -> None:
        self.done = self.total
        self._name = ""
        if self._tty and self._rows:
            self._redraw()
            self._real.write(f"\033[1;{self._rows}r\033[{self._rows};1H\n")
            self._real.flush()
        else:
            self._real.write(f"\r{self._bar_str()}\n")
            self._real.flush()
        sys.stdout = self._real
