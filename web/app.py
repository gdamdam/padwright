"""
web/app.py — Padwright local web UI (FastAPI).

Serves http://localhost:<port> with: library browse, kit detail + audition,
pad swap, crate editor, duplicate audit, samples browser, settings.

Run modes:
  python3 -m web.app --root PATH --samples PATH      # explicit CLI mode
  python3 -m web.app                                 # use saved config
  python3 -m web.app --port 0 --no-browser           # Tauri sidecar mode

Config persists at <platform-specific>/config.json (see _default_data_dir).
CLI flags always win over config; an in-app /settings page writes config.

When --port 0 is used, the chosen port is printed to stdout from the
FastAPI lifespan hook (so it's emitted only after uvicorn has bound)
as `PADWRIGHT_PORT=<n>`. The Tauri parent reads that line to navigate the
webview.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
import webbrowser
from contextlib import asynccontextmanager
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


def _resource_dir() -> Path:
    """
    Where bundled assets live.

    - Source runs (`python -m web.app`): next to this file → web/.
    - PyInstaller bundle: under sys._MEIPASS at the bundle root (the
      spec puts templates/ and static/ there directly, since PyInstaller
      flattens the entry script's path).
    """
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        return Path(bundle)
    return Path(__file__).resolve().parent


HERE = _resource_dir()
TEMPLATES = Jinja2Templates(directory=str(HERE / "templates"))


# ── App state (set at startup) ────────────────────────────────────────────────

class State:
    root: Path                 # directory of built kits
    samples: Path | None       # sample-library root for crate sourcing
    crates_dir: Path           # where saved crates live
    port: int                  # set in main() before uvicorn.run()

    def __init__(self):
        self.root = Path(".")
        self.samples = None
        self.crates_dir = Path(".")
        self.port = 0


STATE = State()


# ── Config persistence ────────────────────────────────────────────────────────

CONFIG_VERSION = 1
APP_ID = "com.padwright.app"
# Pre-1.0 internal builds used this identifier. We still read its config
# on first launch if no Padwright config exists, so anyone upgrading from
# a dev build doesn't lose their settings. Migration is one-shot: the
# next save() writes to the new APP_ID path.
LEGACY_APP_ID = "com.sp404mk2.toolkit"


def _data_dir_for(app_id: str) -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / app_id
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home())
        # On Windows we use the short brand name as the folder.
        return Path(base) / ("Padwright" if app_id == APP_ID else "Sp404Toolkit")
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / ("padwright" if app_id == APP_ID else "sp404-toolkit")


def _default_data_dir() -> Path:
    """Per-user app data dir, platform-aware."""
    return _data_dir_for(APP_ID)


def config_path() -> Path:
    return _default_data_dir() / "config.json"


def _legacy_config_path() -> Path:
    return _data_dir_for(LEGACY_APP_ID) / "config.json"


def load_config() -> dict:
    """
    Load config.json. Falls back to the legacy (pre-rename) location once
    so upgrade-from-dev-build users don't lose settings; subsequent saves
    land at the new path.
    """
    p = config_path()
    if p.exists():
        try:
            return json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    legacy = _legacy_config_path()
    if legacy.exists():
        try:
            print(f"[padwright] migrating config from legacy path {legacy}",
                  file=sys.stderr)
            return json.loads(legacy.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_config(config: dict) -> Path:
    config = {**config, "version": CONFIG_VERSION}
    p = config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(config, indent=2))
    return p


def _bin_status(bin_name: str, env_var: str) -> dict:
    """Diagnostic for ffmpeg/ffprobe availability."""
    env_path = os.environ.get(env_var)
    resolved = env_path or shutil.which(bin_name)
    return {
        "name": bin_name,
        "env_var": env_var,
        "from_env": bool(env_path),
        "path": resolved,
        "ok": bool(resolved and Path(resolved).exists()),
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _source_is_allowed(src: Path) -> bool:
    """
    When STATE.samples is configured (always the case in the desktop app),
    swap/crate sources must live under it. CLI users running without
    --samples retain full flexibility.
    """
    if STATE.samples is None:
        return True
    samples_root = STATE.samples.resolve()
    src = src.resolve()
    return src == samples_root or samples_root in src.parents


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

@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Lifespan startup runs AFTER uvicorn binds the socket — so this is the
    # safe moment to announce the port to the Tauri parent. Printing earlier
    # (before uvicorn.run) creates a race where the parent's first proxied
    # request lands before uvicorn is listening, yielding "Connection refused".
    print(f"PADWRIGHT_PORT={STATE.port}", flush=True)
    yield


app = FastAPI(title="Padwright", lifespan=lifespan)
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
    if not _source_is_allowed(src_path):
        raise HTTPException(
            status_code=400,
            detail=f"source must be under the configured samples root ({STATE.samples})",
        )

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

    # Annotate each entry with a kit_rel link the template can use directly.
    # Without this, templates would have to compute it from kit_dir which is
    # absolute — see the fixed audit.html.
    root_str = str(STATE.root.resolve())
    for entries in groups.values():
        for e in entries:
            kd = e.get("kit_dir")
            if not kd:
                e["kit_rel"] = None
                continue
            try:
                e["kit_rel"] = str(Path(kd).resolve().relative_to(root_str))
            except ValueError:
                e["kit_rel"] = None

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

    # Validate + clean: drop sources that don't exist OR escape the samples
    # root. Each is reported back as a warning in the manifest meta so the
    # user can see what was silently dropped.
    cleaned = []
    warnings: list[str] = []
    for p in pad_specs:
        if not p.get("pad"):
            continue
        src_raw = p.get("source") or None
        src: str | None = src_raw
        if src:
            src_path = Path(src).resolve()
            if not src_path.is_file():
                warnings.append(f"pad {p['pad']}: source not found, set to silent ({src})")
                src = None
            elif not _source_is_allowed(src_path):
                warnings.append(f"pad {p['pad']}: source outside samples root, set to silent ({src})")
                src = None
            else:
                src = str(src_path)
        cleaned.append({"pad": int(p["pad"]),
                        "source": src,
                        "type": p.get("type") or None})

    dst = STATE.root / name
    meta_extra = {"source": "web_ui"}
    if warnings:
        meta_extra["warnings"] = warnings
    build_from_pad_list(dst, cleaned, kind=kind, meta_extra=meta_extra)

    # Also save the crate JSON next to the bank for re-editing later.
    crate_out = {"name": name, "kind": kind, "pads":
                 [p for p in cleaned if p.get("source")]}
    (dst / "crate.json").write_text(json.dumps(crate_out, indent=2))

    rel = str(dst.relative_to(STATE.root))
    return RedirectResponse(url=f"/kit/{quote(rel)}", status_code=303)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "root": str(STATE.root),
        "samples": str(STATE.samples) if STATE.samples else None,
        "ffmpeg": _bin_status("ffmpeg", "FFMPEG_PATH"),
        "ffprobe": _bin_status("ffprobe", "FFPROBE_PATH"),
        "port": STATE.port,
        "config_path": str(config_path()),
    }


@app.get("/settings", response_class=HTMLResponse)
def settings_view(request: Request):
    return TEMPLATES.TemplateResponse(request, "settings.html", {
        "root": str(STATE.root) if STATE.root else "",
        "samples": str(STATE.samples) if STATE.samples else "",
        "config_path": str(config_path()),
        "config_exists": config_path().exists(),
        "ffmpeg": _bin_status("ffmpeg", "FFMPEG_PATH"),
        "ffprobe": _bin_status("ffprobe", "FFPROBE_PATH"),
        "platform": sys.platform,
        "port": STATE.port,
        "saved": request.query_params.get("saved") == "1",
    })


@app.post("/settings")
def settings_save(root: str = Form(""), samples: str = Form("")):
    cfg = load_config()
    root = root.strip()
    samples = samples.strip()

    if root:
        root_path = Path(root).expanduser().resolve()
        root_path.mkdir(parents=True, exist_ok=True)
        cfg["root"] = str(root_path)
        STATE.root = root_path
        # Re-anchor crates dir under the new root
        STATE.crates_dir = (root_path / ".crates").resolve()
        STATE.crates_dir.mkdir(parents=True, exist_ok=True)
    if samples:
        samples_path = Path(samples).expanduser().resolve()
        if not samples_path.exists():
            raise HTTPException(status_code=400,
                                detail=f"samples path does not exist: {samples_path}")
        cfg["samples"] = str(samples_path)
        STATE.samples = samples_path
    else:
        cfg.pop("samples", None)
        STATE.samples = None

    save_config(cfg)
    return RedirectResponse(url="/settings?saved=1", status_code=303)


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
    parser.add_argument("--root", type=Path, default=None,
                        help="directory of built kits (default: saved config, then platform data dir)")
    parser.add_argument("--samples", type=Path, default=None,
                        help="optional sample-library root for crate sourcing (default: saved config)")
    parser.add_argument("--crates", type=Path, default=None,
                        help="where to save user crates (defaults to <root>/.crates)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0,
                        help="0 = auto-pick a free port (default)")
    parser.add_argument("--no-browser", action="store_true",
                        help="don't open the system browser")
    args = parser.parse_args()

    # Resolution order: CLI > saved config > platform default.
    cfg = load_config()

    if args.root:
        STATE.root = args.root.resolve()
    elif cfg.get("root"):
        STATE.root = Path(cfg["root"]).resolve()
    else:
        STATE.root = (_default_data_dir() / "kits").resolve()
    STATE.root.mkdir(parents=True, exist_ok=True)

    if args.samples:
        STATE.samples = args.samples.resolve()
    elif cfg.get("samples"):
        STATE.samples = Path(cfg["samples"]).resolve()
    else:
        STATE.samples = None

    STATE.crates_dir = (args.crates or (STATE.root / ".crates")).resolve()
    STATE.crates_dir.mkdir(parents=True, exist_ok=True)

    print(f"[padwright] config: {config_path()}", file=sys.stderr)
    print(f"[padwright] root:    {STATE.root}", file=sys.stderr)
    print(f"[padwright] samples: {STATE.samples or '(unset — set via /settings)'}",
          file=sys.stderr)

    port = args.port or pick_free_port()
    STATE.port = port
    # Note: PADWRIGHT_PORT is printed from the lifespan hook above, *after*
    # uvicorn has actually bound the socket. Printing here would race.

    if not args.no_browser:
        threading.Thread(target=open_browser_when_ready,
                         args=(port, args.host), daemon=True).start()

    uvicorn.run(app, host=args.host, port=port, log_level="info")


if __name__ == "__main__":
    main()
