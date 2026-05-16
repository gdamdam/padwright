# Icons

Tauri needs platform icons here. Generate them once with:

```bash
cd src-tauri
cargo tauri icon path/to/source-icon-1024.png
```

This produces `32x32.png`, `128x128.png`, `128x128@2x.png`,
`icon.icns` (macOS), and `icon.ico` (Windows).

A `.gitkeep` is intentionally absent — the generated icons should be
committed once you have a real source icon.
