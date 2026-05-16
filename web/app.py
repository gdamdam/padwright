"""
web/app.py — FastAPI UI for the SP-404 MK2 toolkit.

Serves a small local web UI on http://localhost:<port> that lets you:
  - browse built kits under <root>
  - inspect a kit's pads with in-browser audio audition
  - swap any pad with a file from your sample library
  - edit and build crates (hand-curated kits)
  - audit duplicates across the tree (uses audit_kits logic)

Run:
  python3 -m web.app --root /path/to/built_kits --samples /path/to/samples
  python3 -m web.app --root ./out --port 0           # auto-pick port
  python3 -m web.app --root ./out --no-browser       # don't open browser

When `--port 0` is used the chosen port is printed to stdout as
`SP404_PORT=<n>` so a parent process (the Tauri shell) can find it.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import tempfile
import threading
import time
import webbrowser
from pathlib import Path
from urllib.parse import quote

import uvicorn
from fastapi import FastAPI, Form, HTTPException, Request, UploadFile, File
from fastapi.responses import (FileResponse, HTMLResponse, RedirectResponse,
                               JSONResponse)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Make the parent dir importable so we can reuse the sibling modules.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sp404_core import (  # noqa: E402
    AUDIO_EXTS, KIND_DRUMKIT, KIND_LOOPBANK, SOUND_SLOTS, SLOT_NAMES,
    build_from_pad_list, classify, load_crate, manifest_to_crate,
    make_silent_wav, sha256_file, ffprobe_info, write_manifest, write_pad_map,
    export as ffmpeg_export,
)
import audit_kits  # noqa: E402


HERE = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(HERE / "templates"))


# ── App state (set at startup) ────────────────────────────────────────────────

class State:
    root: Path                 # directory of built kits
    samples: Path | None       # sample-library root for crate sourcing
    crates_dir: Path           # where saved crates live

    def __init__(self):
        self.root = Path(".")
        self.samples = None
        self.crates_dir = Path(".")


STATE = State()


# ── Helpers ───────────────────────────────────────────────────────────────────

def safe_join(root: Path, sub: str) -> Path:
    """Resolve <root>/<sub> and verify the result is still under root."""
    p = (root / sub).resolve()
    root = root.resolve()
    if root != p and root not in p.parents:
        raise HTTPException(status_code=400, detail=f"path escapes root: {sub}")
    return p


def list_kits(root: Path) -> list[dict]:
    """Find every manifest.json under root and return summary rows."""
    out = []
    if not root.exists():
        return out
    for mpath in sorted(root.rglob("manifest.json")):
        try:
            manifest = json.loads(mpath.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        kit_dir = mpath.parent
        rel = kit_dir.relative_to(root)
        meta = manifest.get("meta") or {}
        pads = manifest.get("pads") or []
        sourced = sum(1 for p in pads if p.get("source"))
        out.append({
            "name": manifest.get("kit_name") or kit_dir.name,
            "rel": str(rel),
            "kind": meta.get("kind") or "?",
            "pads": len(pads),
            "sourced": sourced,
        })
    return out


def list_samples(root: Path, sub: str = "") -> dict:
    """List one directory level of the samples root."""
    if not root:
        return {"folders": [], "files": [], "cwd": sub, "parent": None}
    cur = safe_join(root, sub) if sub else root
    if not cur.is_dir():
        raise HTTPException(status_code=404, detail=f"not a directory: {sub}")
    folders = []
    files = []
    for child in sorted(cur.iterdir()):
        if child.name.startswith("."):
            continue
        if child.is_dir():
            folders.append(child.name)
        elif child.suffix.lower() in AUDIO_EXTS:
            files.append({
                "name": child.name,
                "abs": str(child.resolve()),
                "size": child.stat().st_size,
            })
    parent = None
    if sub:
        parent = str(Path(sub).parent) if str(Path(sub).parent) != "." else ""
    return {"folders": folders, "files": files, "cwd": sub, "parent": parent}


def pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="SP-404 MK2 Toolkit")
app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    kits = list_kits(STATE.root)
    return TEMPLATES.TemplateResponse(request, "library.html", {"kits": kits, "root": str(STATE.root),
        "samples": str(STATE.samples) if STATE.samples else None,
    })


@app.get("/kit/{kit_rel:path}", response_class=HTMLResponse)
def kit_detail(request: Request, kit_rel: str):
    kit_dir = safe_join(STATE.root, kit_rel)
    mpath = kit_dir / "manifest.json"
    if not mpath.exists():
        raise HTTPException(status_code=404, detail="kit has no manifest.json")
    manifest = json.loads(mpath.read_text())
    return TEMPLATES.TemplateResponse(request, "kit.html", {"manifest": manifest, "kit_rel": kit_rel,
        "samples": str(STATE.samples) if STATE.samples else None,
    })


@app.get("/audio/kit/{kit_rel:path}")
def kit_audio(kit_rel: str):
    """Serve a WAV from inside a kit (audio src for <audio> tags)."""
    p = safe_join(STATE.root, kit_rel)
    if not p.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(p, media_type="audio/wav")


@app.get("/audio/sample")
def sample_audio(path: str):
    """Serve a WAV from the samples root (audio src for the source browser)."""
    if not STATE.samples:
        raise HTTPException(status_code=400, detail="no --samples configured")
    # Allow absolute paths only if they're under STATE.samples.
    requested = Path(path).resolve()
    samples_root = STATE.samples.resolve()
    if samples_root not in requested.parents and requested != samples_root:
        raise HTTPException(status_code=400, detail="path escapes samples root")
    if not requested.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(requested)


@app.post("/kit/{kit_rel:path}/swap")
def kit_swap(kit_rel: str, pad: int = Form(...), source: str = Form(...),
             pad_type: str = Form("")):
    """Swap a pad. Mirrors swap_pad.py logic, in-process."""
    kit_dir = safe_join(STATE.root, kit_rel)
    mpath = kit_dir / "manifest.json"
    if not mpath.exists():
        raise HTTPException(status_code=404, detail="no manifest.json")
    manifest = json.loads(mpath.read_text())
    meta = manifest.get("meta") or {}
    pads = manifest.get("pads") or []
    by_pad = {p.get("pad"): p for p in pads}
    entry = by_pad.get(pad)
    if not entry:
        raise HTTPException(status_code=400, detail=f"pad {pad} not in manifest")

    src_path = Path(source).resolve()
    if not src_path.is_file():
        raise HTTPException(status_code=400, detail=f"source not found: {source}")

    ch = 2 if meta.get("kind") == KIND_LOOPBANK else 1
    dst = kit_dir / entry["filename"]
    if not ffmpeg_export(str(src_path), str(dst), channels=ch):
        raise HTTPException(status_code=500, detail="ffmpeg failed")
    info = ffprobe_info(dst)
    by_pad[pad] = {
        "pad": pad, "filename": entry["filename"],
        "type": pad_type or entry.get("type"),
        "source": str(src_path),
        "source_basename": src_path.name,
        "kind": "swap",
        "sha256": sha256_file(dst),
        **info,
    }
    new_pads = list(by_pad.values())
    write_manifest(kit_dir, new_pads, meta=meta)
    write_pad_map(kit_dir, new_pads, meta=meta)
    return RedirectResponse(url=f"/kit/{quote(kit_rel)}", status_code=303)


@app.get("/samples", response_class=HTMLResponse)
def samples_browser(request: Request, path: str = ""):
    if not STATE.samples:
        raise HTTPException(status_code=400,
                            detail="--samples not configured; restart with --samples PATH")
    listing = list_samples(STATE.samples, path)
    return TEMPLATES.TemplateResponse(request, "samples.html", {"listing": listing,
        "samples_root": str(STATE.samples),
    })


@app.get("/api/samples")
def samples_api(path: str = ""):
    """JSON variant of the samples browser, for the crate editor."""
    if not STATE.samples:
        return JSONResponse({"error": "no --samples configured"}, status_code=400)
    return list_samples(STATE.samples, path)


@app.get("/audit", response_class=HTMLResponse)
def audit_view(request: Request, exclude_super: bool = True, by_source: bool = False):
    manifests = audit_kits.load_manifests(STATE.root)
    key = "source" if by_source else "sha256"
    groups = audit_kits.group_pads(manifests, key=key)
    if exclude_super:
        groups = {k: [e for e in v if e.get("kind") != "super"]
                  for k, v in groups.items()}
        groups = {k: v for k, v in groups.items() if v}
    total_pads = sum(len(v) for v in groups.values())
    dups = sorted(
        [(k, v) for k, v in groups.items() if len(v) >= 2],
        key=lambda kv: (-len(kv[1]), kv[0]),
    )
    return TEMPLATES.TemplateResponse(request, "audit.html", {"dups": dups, "total_pads": total_pads,
        "unique": len(groups), "key": key,
        "exclude_super": exclude_super, "by_source": by_source,
    })


@app.get("/crate", response_class=HTMLResponse)
def crate_editor(request: Request, kit_rel: str | None = None):
    """
    Crate editor. If kit_rel is given, pre-seed from that kit's manifest;
    otherwise empty new-kit form.
    """
    crate = {"name": "New Kit", "kind": KIND_DRUMKIT, "pads": []}
    if kit_rel:
        kit_dir = safe_join(STATE.root, kit_rel)
        mpath = kit_dir / "manifest.json"
        if mpath.exists():
            crate = manifest_to_crate(json.loads(mpath.read_text()))
    return TEMPLATES.TemplateResponse(request, "crate.html", {"crate": crate,
        "slot_names": SLOT_NAMES,
        "sound_slots": SOUND_SLOTS,
        "samples": str(STATE.samples) if STATE.samples else None,
    })


@app.post("/crate/build")
def crate_build(name: str = Form(...), kind: str = Form(KIND_DRUMKIT),
                pad_json: str = Form(...)):
    """
    Build a kit from posted crate data. pad_json is the JSON-encoded list of
    {pad, source, type} dicts (the form serializes the grid into one field).
    """
    try:
        pad_specs = json.loads(pad_json)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"bad pad_json: {e}")
    if not isinstance(pad_specs, list):
        raise HTTPException(status_code=400, detail="pad_json must be a list")

    # Drop pads where source is missing or doesn't exist
    cleaned = []
    for p in pad_specs:
        if not p.get("pad"):
            continue
        src = p.get("source") or None
        if src and not Path(src).exists():
            src = None
        cleaned.append({"pad": int(p["pad"]),
                        "source": src,
                        "type": p.get("type") or None})

    dst = STATE.root / name
    build_from_pad_list(dst, cleaned, kind=kind,
                        meta_extra={"source": "web_ui"})

    # Also save the crate JSON next to the bank for re-editing later.
    crate_out = {"name": name, "kind": kind, "pads":
                 [p for p in cleaned if p.get("source")]}
    (dst / "crate.json").write_text(json.dumps(crate_out, indent=2))

    rel = str(dst.relative_to(STATE.root))
    return RedirectResponse(url=f"/kit/{quote(rel)}", status_code=303)


@app.get("/health")
def health():
    return {"status": "ok", "root": str(STATE.root),
            "samples": str(STATE.samples) if STATE.samples else None}


# ── Entry point ───────────────────────────────────────────────────────────────

def open_browser_when_ready(port: int, host: str = "127.0.0.1") -> None:
    """Poll the health endpoint and open the system browser when it's up."""
    import urllib.request
    url = f"http://{host}:{port}"
    for _ in range(60):
        try:
            urllib.request.urlopen(url + "/health", timeout=0.5).read()
            webbrowser.open(url)
            return
        except Exception:
            time.sleep(0.1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, required=True,
                        help="directory of built kits (where manifest.json files live)")
    parser.add_argument("--samples", type=Path, default=None,
                        help="optional sample-library root for crate sourcing")
    parser.add_argument("--crates", type=Path, default=None,
                        help="where to save user crates (defaults to <root>/.crates)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0,
                        help="0 = auto-pick a free port (default)")
    parser.add_argument("--no-browser", action="store_true",
                        help="don't open the system browser")
    args = parser.parse_args()

    STATE.root = args.root.resolve()
    STATE.samples = args.samples.resolve() if args.samples else None
    STATE.crates_dir = (args.crates or (STATE.root / ".crates")).resolve()
    STATE.crates_dir.mkdir(parents=True, exist_ok=True)

    if not STATE.root.exists():
        print(f"warning: --root {STATE.root} does not exist", file=sys.stderr)

    port = args.port or pick_free_port()
    # The Tauri shell parses this line from stdout to find the URL:
    print(f"SP404_PORT={port}", flush=True)

    if not args.no_browser:
        threading.Thread(target=open_browser_when_ready,
                         args=(port, args.host), daemon=True).start()

    uvicorn.run(app, host=args.host, port=port, log_level="info")


if __name__ == "__main__":
    main()
