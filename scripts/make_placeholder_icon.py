#!/usr/bin/env python3
"""
Generate a placeholder 1024x1024 icon so `cargo tauri icon` has something
to chew on while you find or commission a real one.

Usage:
  python3 scripts/make_placeholder_icon.py                # writes ./icon.png
  python3 scripts/make_placeholder_icon.py out/foo.png    # custom path
"""
from __future__ import annotations
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.exit("pip install pillow  (or use your real icon)")

out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("icon.png")
out.parent.mkdir(parents=True, exist_ok=True)

# Dark background matching the web UI; amber rounded square; "SP" wordmark.
img = Image.new("RGB", (1024, 1024), "#111")
d = ImageDraw.Draw(img)
d.rounded_rectangle((96, 96, 928, 928), radius=128, fill="#d59f3d")

# Try a few common system fonts; fall back to default if none found.
font = None
for candidate in (
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
):
    try:
        font = ImageFont.truetype(candidate, 420)
        break
    except OSError:
        continue

d.text((512, 530), "SP", fill="#111", anchor="mm", font=font)
img.save(out)
print(f"wrote {out.resolve()}  ({out.stat().st_size} bytes)")
