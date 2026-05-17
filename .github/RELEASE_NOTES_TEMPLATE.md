<!--
.github/RELEASE_NOTES_TEMPLATE.md

This is the framing the release-notes composition step in
.github/workflows/release.yml wraps around the CHANGELOG section for
the tag being released. The workflow substitutes:

  {{ version }}     → the tag (e.g. v1.0.0)
  {{ repo }}        → owner/name (e.g. you/padwright)
  {{ changelog }}   → the CHANGELOG.md section for {{ version }}

Edit this file to change the wrapping copy without touching the
workflow.
-->
## Padwright {{ version }}

{{ changelog }}

---

## Install

Download the bundle matching your platform:

| Platform | File |
| --- | --- |
| macOS Apple Silicon (M-series) | `Padwright_*_aarch64.dmg` |
| macOS Intel                    | `Padwright_*_x64.dmg`     |
| Windows x64                    | `Padwright_*_x64_en-US.msi` |
| Linux x64                      | `Padwright_*_amd64.AppImage` / `.deb` |

### First-launch warning, one-time

The bundles aren't yet code-signed, so your OS will warn on first
launch. This is expected and goes away once you bypass it once:

- **macOS** — right-click Padwright in Applications → **Open** →
  confirm. Subsequent launches don't prompt.
- **Windows** — SmartScreen → **More info** → **Run anyway**.
- **Linux** — no warning.

Permanent fix (planned): paid code signing — see the README's
[Releasing → Adding code signing later](https://github.com/{{ repo }}#adding-code-signing-later-optional).

## After install

1. Launch Padwright.
2. Click **Settings** (top right) and set:
   - **Built kits folder** — where Padwright reads/writes banks
     (e.g. `~/Music/SP_EXPORT`).
   - **Samples library folder** — root of your local samples.
3. Build banks (the CLI bulk-builds whole archives;
   **New crate** in the UI hand-curates one kit).
4. Drag the 16 WAVs from each kit folder into the Roland SP-404MKII app.

See the [README](https://github.com/{{ repo }}#readme) for the full
workflow and [Troubleshooting](https://github.com/{{ repo }}#troubleshooting)
for common issues.

---

🐛 Bug reports: <https://github.com/{{ repo }}/issues>
