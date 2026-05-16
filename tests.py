#!/usr/bin/env python3
"""
tests.py — self-contained sanity checks (no pytest required).

Run:
    python3 tests.py

Covers:
- classify() recognises common drum-machine naming
- SOUND_SLOTS is 12 pads, all unique types, slot numbers 5..16
- write_manifest / write_pad_map round-trip
- end-to-end: build_kit on a synthetic source produces 16 pads
  with manifest + pad-map (skipped automatically if ffmpeg is missing)
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import sp404_core as core


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print(f"  ok  {msg}")


def test_classify():
    print("classify()")
    cases = {
        "Roland TR-808/BD0000.WAV": "kick",
        "Roland TR-909/SD7575.WAV": "snare",
        "kit/kick_03.wav": "kick",
        "kit/snare_drum_01.wav": "snare",
        "pack/HHc_001.wav": "closed_hh",
        "pack/HHo_001.wav": "open_hh",
        "pack/Hcp_01.aif": "clap",
        "pack/CrashRide.wav": "crash",
        "pack/rimshot.aiff": "rim",
        "pack/Cowbell 2.wav": "cowbell",
        "pack/Lt03.wav": "low_tom",
        "pack/Mt03.wav": "mid_tom",
        "pack/Ht03.wav": "hi_tom",
        # Regression: Roland TR-606/808/909 naming
        "Roland TR606/Hat_C04.wav": "closed_hh",
        "Roland TR606/Hat_O02.wav": "open_hh",
        "Roland TR606/TomLo04.wav": "low_tom",
        "Roland TR606/TomMi02.wav": "mid_tom",
        "Roland TR606/TomHi_OD.wav": "hi_tom",
        "pack/tambourine_1.wav": "perc",
        "pack/synth_pluck_C3.wav": None,
    }
    for path, expected in cases.items():
        got = core.classify(path)
        check(got == expected, f"classify({path!r}) → {got!r} (expected {expected!r})")


def test_pad_layout():
    print("pad layout")
    check(len(core.SOUND_SLOTS) == 12, "12 sound slots")
    nums = [n for n, _ in core.SOUND_SLOTS]
    types = [t for _, t in core.SOUND_SLOTS]
    check(nums == list(range(5, 17)), "slot numbers are 5..16 in order")
    check(len(set(types)) == 12, "all 12 slot types are unique")
    check(core.SLOT_NAMES == types, "SLOT_NAMES mirrors SOUND_SLOTS order")
    for t in core.SUPER_FILES:
        check(t in core.SLOT_NAMES, f"SUPER_FILES type {t!r} is a real slot")


def test_manifest_padmap_roundtrip():
    print("manifest + pad-map")
    with tempfile.TemporaryDirectory() as d:
        kit_dir = Path(d) / "TR808"
        kit_dir.mkdir()
        pads = []
        for i in range(1, 5):
            pads.append({"pad": i, "filename": f"0{i}_empty.wav", "type": "empty",
                         "source": None, "source_basename": None, "kind": "silent"})
        for pad_num, slot in core.SOUND_SLOTS:
            pads.append({"pad": pad_num,
                         "filename": f"{pad_num:02d}_{slot}.wav",
                         "type": slot,
                         "source": f"/fake/{slot}.wav",
                         "source_basename": f"{slot}.wav",
                         "kind": "auto"})
        mpath = core.write_manifest(kit_dir, pads, meta={"kind": "drumkit"})
        pmap = core.write_pad_map(kit_dir, pads, meta={"kind": "drumkit"})
        check(mpath.exists(), "manifest.json written")
        check(pmap.exists(), "pad-map.html written")
        data = json.loads(mpath.read_text())
        check(data["manifest_version"] == 1, "manifest_version=1")
        check(len(data["pads"]) == 16, "16 pads in manifest")
        check([p["pad"] for p in data["pads"]] == list(range(1, 17)),
              "pads sorted 1..16")
        html = pmap.read_text()
        check("13_kick.wav" in html, "pad-map references 13_kick.wav")
        check("<audio" in html, "pad-map embeds <audio> tags")


def has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _write_tiny_wav(path: Path, ms: int = 30, sr: int = 22050):
    """Write a tiny pseudo-source WAV without needing ffmpeg."""
    n = int(sr * ms / 1000)
    with wave.open(str(path), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(b"\x00\x01" * n)


def test_build_kit_e2e():
    print("end-to-end build_kit")
    if not has_ffmpeg():
        print("  skip (ffmpeg/ffprobe not on PATH)")
        return

    import make_kits

    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "src" / "FakeMachine"
        src.mkdir(parents=True)
        # Create one source per drum type so build_kit can fully populate it.
        names = {
            "kick": "BD01.wav", "snare": "SD01.wav",
            "closed_hh": "HHc01.wav", "open_hh": "HHo01.wav",
            "clap": "Hcp01.wav", "rim": "rim01.wav",
            "cowbell": "cowbell01.wav", "perc": "tambourine01.wav",
            "low_tom": "Lt01.wav", "mid_tom": "Mt01.wav", "hi_tom": "Ht01.wav",
            "crash": "crash01.wav",
        }
        audio_files = []
        for fname in names.values():
            p = src / fname
            _write_tiny_wav(p)
            audio_files.append(str(p))

        # build_kit needs the silent WAV that make_kits writes in main().
        # Override the global to a sandbox-writable path for the test.
        make_kits.SILENT_WAV = str(Path(d) / "silent.wav")
        core.make_silent_wav(make_kits.SILENT_WAV)

        kit_dir = Path(d) / "out" / "FakeMachine"
        make_kits.build_kit(audio_files, str(kit_dir), dry_run=False, ui=None)

        wavs = sorted(f.name for f in kit_dir.glob("*.wav"))
        check(len(wavs) == 16, f"16 WAVs in kit (got {len(wavs)})")
        check(wavs[0] == "01_empty.wav", "01_empty.wav present")
        check("13_kick.wav" in wavs, "13_kick.wav present")
        check((kit_dir / "manifest.json").exists(), "manifest.json present")
        check((kit_dir / "pad-map.html").exists(), "pad-map.html present")

        data = json.loads((kit_dir / "manifest.json").read_text())
        kick = next(p for p in data["pads"] if p["pad"] == 13)
        check(kick["type"] == "kick", "pad 13 type=kick in manifest")
        check(kick["source_basename"] == "BD01.wav", "pad 13 source recorded")


def test_extract_audio_preserves_original_source():
    """
    Regression: when make_kits.py extracts a pack to a tempdir before
    building, the manifest's `source` field must reference the *original*
    file, not the (soon-to-be-deleted) temp copy. Otherwise rebuild_kit
    and crate dumps produce dead paths.
    """
    print("extract_audio source-map preserves original paths")
    if not has_ffmpeg():
        print("  skip (ffmpeg/ffprobe not on PATH)")
        return

    import make_kits

    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        pack = d / "pack" / "TR808"
        pack.mkdir(parents=True)
        original_kick = pack / "BD01.wav"
        _write_tiny_wav(original_kick)
        _write_tiny_wav(pack / "SD01.wav")

        with tempfile.TemporaryDirectory() as tmp:
            audio_files, source_map = core.extract_audio(pack, tmp)
            check(len(audio_files) == 2, "extracted 2 files")
            for f in audio_files:
                check(f.startswith(tmp), "extracted path is under tmpdir")
                check(source_map[f].startswith(str(pack.resolve())),
                      "source_map points back at original pack")

            make_kits.SILENT_WAV = str(d / "silent.wav")
            core.make_silent_wav(make_kits.SILENT_WAV)
            kit_dir = d / "out" / "TR808"
            make_kits.build_kit(audio_files, str(kit_dir), dry_run=False,
                                ui=None, source_map=source_map)

        # tmpdir is gone now — verify the manifest survives the loss
        manifest = json.loads((kit_dir / "manifest.json").read_text())
        kick = next(p for p in manifest["pads"] if p["pad"] == 13)
        check(Path(kick["source"]).exists(),
              f"pad 13 source path still exists after tmpdir cleanup ({kick['source']})")
        check(kick["source"] == str(original_kick.resolve()),
              "pad 13 source is the original, not the temp copy")


def test_swap_pad_e2e():
    print("end-to-end swap_pad")
    if not has_ffmpeg():
        print("  skip (ffmpeg/ffprobe not on PATH)")
        return

    import make_kits

    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "src" / "FakeMachine"
        src.mkdir(parents=True)
        names = {
            "kick": "BD01.wav", "snare": "SD01.wav",
            "closed_hh": "HHc01.wav", "open_hh": "HHo01.wav",
        }
        for fname in names.values():
            _write_tiny_wav(src / fname)
        # Extra "boutique" kick to swap in
        new_kick = src / "BoutiqueKick.wav"
        _write_tiny_wav(new_kick, ms=80)

        make_kits.SILENT_WAV = str(Path(d) / "silent.wav")
        core.make_silent_wav(make_kits.SILENT_WAV)
        kit_dir = Path(d) / "out" / "FakeMachine"
        audio_files = [str(src / n) for n in names.values()]
        make_kits.build_kit(audio_files, str(kit_dir), dry_run=False, ui=None)

        r = subprocess.run(
            [sys.executable, "swap_pad.py", str(kit_dir), "13", str(new_kick)],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            capture_output=True, text=True,
        )
        check(r.returncode == 0, f"swap_pad exit 0 (stderr={r.stderr!r})")

        data = json.loads((kit_dir / "manifest.json").read_text())
        kick = next(p for p in data["pads"] if p["pad"] == 13)
        check(kick["kind"] == "swap", "pad 13 kind=swap after swap")
        check(kick["source_basename"] == "BoutiqueKick.wav",
              "pad 13 source updated in manifest")
        check((kit_dir / "13_kick.wav").exists(),
              "pad 13 WAV file kept its filename")


def _build_minimal_kit(d: Path):
    """Helper: build a 4-pad-populated drumkit at d/out/FakeKit. Returns kit_dir + sources."""
    import make_kits
    src = d / "src" / "FakeKit"
    src.mkdir(parents=True)
    names = {
        "kick": "BD01.wav", "snare": "SD01.wav",
        "closed_hh": "HHc01.wav", "open_hh": "HHo01.wav",
    }
    audio_files = []
    for fname in names.values():
        p = src / fname
        _write_tiny_wav(p)
        audio_files.append(str(p))
    make_kits.SILENT_WAV = str(d / "silent.wav")
    core.make_silent_wav(make_kits.SILENT_WAV)
    kit_dir = d / "out" / "FakeKit"
    make_kits.build_kit(audio_files, str(kit_dir), dry_run=False, ui=None)
    return kit_dir, src


def test_rebuild_kit_e2e():
    print("end-to-end rebuild_kit")
    if not has_ffmpeg():
        print("  skip (ffmpeg/ffprobe not on PATH)")
        return
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        kit_dir, _ = _build_minimal_kit(d)
        before_kick_sha = next(p for p in json.loads(
            (kit_dir / "manifest.json").read_text())["pads"] if p["pad"] == 13)["sha256"]

        out_dir = d / "rebuilt"
        r = subprocess.run(
            [sys.executable, "rebuild_kit.py", str(kit_dir), "--out", str(out_dir)],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            capture_output=True, text=True,
        )
        check(r.returncode == 0, f"rebuild_kit exit 0 (stderr={r.stderr!r})")
        check((out_dir / "manifest.json").exists(), "rebuilt manifest.json present")
        check((out_dir / "13_kick.wav").exists(), "rebuilt 13_kick.wav present")
        # Same source → same content → same sha
        rebuilt_kick = next(p for p in json.loads(
            (out_dir / "manifest.json").read_text())["pads"] if p["pad"] == 13)
        check(rebuilt_kick["sha256"] == before_kick_sha,
              "rebuilt pad 13 sha256 matches original (deterministic export)")


def test_crate_roundtrip_e2e():
    print("end-to-end crate round-trip")
    if not has_ffmpeg():
        print("  skip (ffmpeg/ffprobe not on PATH)")
        return
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        kit_dir, src = _build_minimal_kit(d)

        # Dump kit → crate
        crate_path = d / "kit.crate.json"
        r = subprocess.run(
            [sys.executable, "make_kit_from_crate.py",
             "--from-kit", str(kit_dir), "--out", str(crate_path)],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            capture_output=True, text=True,
        )
        check(r.returncode == 0, f"dump crate exit 0 (stderr={r.stderr!r})")
        check(crate_path.exists(), "crate file written")
        crate = json.loads(crate_path.read_text())
        check(crate["kind"] == "drumkit", "crate kind=drumkit")
        check(len(crate["pads"]) == 4, "crate has 4 sourced pads (silent omitted)")

        # Hand-edit: swap pad 13 source to a different audio file
        new_kick = src / "Boutique.wav"
        _write_tiny_wav(new_kick, ms=90)
        for p in crate["pads"]:
            if p["pad"] == 13:
                p["source"] = str(new_kick)
        crate["name"] = "EditedKit"
        crate_path.write_text(json.dumps(crate, indent=2))

        # Build from edited crate
        dst = d / "from_crate"
        r = subprocess.run(
            [sys.executable, "make_kit_from_crate.py",
             str(crate_path), str(dst)],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            capture_output=True, text=True,
        )
        check(r.returncode == 0, f"build crate exit 0 (stderr={r.stderr!r})")
        built = dst / "EditedKit"
        check((built / "manifest.json").exists(), "built kit manifest present")
        m = json.loads((built / "manifest.json").read_text())
        # 16 pads total (silents auto-filled), 13_kick references Boutique
        check(len(m["pads"]) == 16, "built kit has 16 pads (silents filled)")
        kick = next(p for p in m["pads"] if p["pad"] == 13)
        check(kick["source_basename"] == "Boutique.wav",
              "pad 13 came from edited crate source")
        check(m["meta"].get("source_crate") == str(crate_path),
              "manifest records source_crate")


def test_audit_kits_e2e():
    print("end-to-end audit_kits")
    if not has_ffmpeg():
        print("  skip (ffmpeg/ffprobe not on PATH)")
        return
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        # Two kits that share a source — should be flagged as a duplicate.
        # Use distinct durations so the two source WAVs are *actually* different
        # (otherwise ffmpeg yields byte-identical output and everything looks
        # like one big duplicate group).
        shared = d / "shared_kick.wav"
        _write_tiny_wav(shared, ms=30)
        unique = d / "unique_snare.wav"
        _write_tiny_wav(unique, ms=80)

        for name in ("KitA", "KitB"):
            crate = {
                "name": name, "kind": "drumkit",
                "pads": [
                    {"pad": 13, "source": str(shared), "type": "kick"},
                    {"pad": 14, "source": str(unique), "type": "snare"},
                ],
            }
            cpath = d / f"{name}.crate.json"
            cpath.write_text(json.dumps(crate))
            r = subprocess.run(
                [sys.executable, "make_kit_from_crate.py", str(cpath), str(d / "out")],
                cwd=os.path.dirname(os.path.abspath(__file__)),
                capture_output=True, text=True,
            )
            check(r.returncode == 0, f"build {name} exit 0 ({r.stderr!r})")

        r = subprocess.run(
            [sys.executable, "audit_kits.py", str(d / "out"), "--json"],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            capture_output=True, text=True,
        )
        check(r.returncode == 0, f"audit exit 0 ({r.stderr!r})")
        report = json.loads(r.stdout)
        # The shared_kick.wav (pad 13 in both kits) should appear as one group of 2.
        # The unique_snare.wav (pad 14 in both kits) is ALSO a duplicate (same
        # source written into both kits) — both should be reported.
        check(report["unique"] == 2, f"2 distinct sha256s (got {report['unique']})")
        check(len(report["groups"]) == 2, "2 duplicate groups reported")
        for g in report["groups"]:
            check(g["count"] == 2, f"group count = 2 (got {g['count']})")
            kits = sorted(p["kit"] for p in g["pads"])
            check(kits == ["KitA", "KitB"],
                  f"group spans KitA and KitB (got {kits})")


def test_crate_missing_source_falls_back_silent():
    print("crate missing source → silent fallback")
    if not has_ffmpeg():
        print("  skip (ffmpeg/ffprobe not on PATH)")
        return
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        real = d / "real.wav"
        _write_tiny_wav(real)
        crate = {
            "name": "PartialKit", "kind": "drumkit",
            "pads": [
                {"pad": 13, "source": str(real), "type": "kick"},
                {"pad": 14, "source": str(d / "missing.wav"), "type": "snare"},
            ],
        }
        crate_path = d / "c.json"
        crate_path.write_text(json.dumps(crate))
        dst = d / "out"
        r = subprocess.run(
            [sys.executable, "make_kit_from_crate.py",
             str(crate_path), str(dst)],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            capture_output=True, text=True,
        )
        check(r.returncode == 0, f"build exit 0 (stderr={r.stderr!r})")
        m = json.loads((dst / "PartialKit" / "manifest.json").read_text())
        snare = next(p for p in m["pads"] if p["pad"] == 14)
        check(snare["kind"] == "silent",
              "missing-source pad becomes silent rather than failing")


def has_web_deps() -> bool:
    """Whether all deps needed by web/app.py are importable."""
    try:
        import fastapi  # noqa: F401
        from fastapi.testclient import TestClient  # noqa: F401
        # Also tries python-multipart implicitly via Form() route decorators.
        from web import app as webapp  # noqa: F401
        return True
    except (ImportError, RuntimeError):
        return False


def test_web_app_routes():
    print("web app routes")
    if not has_ffmpeg():
        print("  skip (ffmpeg/ffprobe not on PATH)")
        return
    if not has_web_deps():
        print("  skip (web deps missing — pip install -r requirements.txt)")
        return

    import make_kits
    from fastapi.testclient import TestClient
    from web import app as webapp

    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        src = d / "src" / "TestKit"; src.mkdir(parents=True)
        for name in ("BD01.wav", "SD01.wav"):
            _write_tiny_wav(src / name)
        boutique = src / "Boutique.wav"
        _write_tiny_wav(boutique, ms=80)

        make_kits.SILENT_WAV = str(d / "silent.wav")
        core.make_silent_wav(make_kits.SILENT_WAV)
        make_kits.build_kit(
            [str(src / "BD01.wav"), str(src / "SD01.wav")],
            str(d / "out" / "TestKit"), dry_run=False,
        )

        webapp.STATE.root = (d / "out").resolve()
        webapp.STATE.samples = src.resolve()
        webapp.STATE.crates_dir = (d / "crates").resolve()
        webapp.STATE.crates_dir.mkdir(exist_ok=True)
        c = TestClient(webapp.app)

        for url in ["/health", "/", "/kit/TestKit", "/audit", "/crate",
                    "/samples", "/api/samples",
                    "/audio/kit/TestKit/13_kick.wav"]:
            r = c.get(url, follow_redirects=False)
            check(r.status_code == 200,
                  f"GET {url} -> 200 (got {r.status_code})")

        # Swap pad 13 via POST
        r = c.post("/kit/TestKit/swap",
                   data={"pad": "13", "source": str(boutique), "pad_type": "kick"},
                   follow_redirects=False)
        check(r.status_code == 303, f"POST swap -> 303 (got {r.status_code})")
        m = json.loads((d / "out" / "TestKit" / "manifest.json").read_text())
        kick = next(p for p in m["pads"] if p["pad"] == 13)
        check(kick["kind"] == "swap", "pad 13 kind=swap after web swap")
        check(kick["source_basename"] == "Boutique.wav",
              "pad 13 source updated by web swap")

        # Build a kit from the crate editor POST
        crate_pads = [{"pad": 13, "source": str(boutique), "type": "kick"}]
        r = c.post("/crate/build",
                   data={"name": "WebKit", "kind": "drumkit",
                         "pad_json": json.dumps(crate_pads)},
                   follow_redirects=False)
        check(r.status_code == 303, f"POST crate build -> 303 (got {r.status_code})")
        built = d / "out" / "WebKit"
        check((built / "manifest.json").exists(), "crate build wrote manifest")
        check((built / "crate.json").exists(), "crate build also saved crate.json")
        m = json.loads((built / "manifest.json").read_text())
        check(m["meta"].get("source") == "web_ui",
              "manifest records web_ui as source")


def main():
    failures = 0
    for fn in [test_classify, test_pad_layout,
               test_manifest_padmap_roundtrip, test_build_kit_e2e,
               test_extract_audio_preserves_original_source,
               test_swap_pad_e2e, test_rebuild_kit_e2e,
               test_crate_roundtrip_e2e,
               test_crate_missing_source_falls_back_silent,
               test_audit_kits_e2e,
               test_web_app_routes]:
        try:
            fn()
        except AssertionError as e:
            print(f"FAIL  {fn.__name__}: {e}")
            failures += 1
        print()
    if failures:
        print(f"{failures} test(s) failed")
        sys.exit(1)
    print("all tests passed")


if __name__ == "__main__":
    main()
