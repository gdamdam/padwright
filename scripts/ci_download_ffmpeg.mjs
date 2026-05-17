#!/usr/bin/env node
/**
 * scripts/ci_download_ffmpeg.mjs
 *
 * Download static LGPL ffmpeg + ffprobe binaries for a given target triple
 * and install them as Tauri sidecars under src-tauri/binaries/.
 *
 * Used by .github/workflows/release.yml.
 *
 * Sources (per platform):
 *   Linux x86_64 / arm64    BtbN/FFmpeg-Builds (tar.xz, LGPL)
 *   Windows x86_64          BtbN/FFmpeg-Builds (zip, LGPL)
 *   macOS x86_64 (Intel)    evermeet.cx static builds
 *
 * NOTE: BtbN does not publish macOS binaries — only Linux + Windows.
 * macOS arm64 is NOT supported here for v1.0.x; Apple Silicon users run
 * the Intel build via Rosetta. See .github/workflows/release.yml matrix
 * comment for rationale.
 *
 * Usage:
 *   node scripts/ci_download_ffmpeg.mjs --target <target-triple>
 *
 * Examples:
 *   node scripts/ci_download_ffmpeg.mjs --target aarch64-apple-darwin
 *   node scripts/ci_download_ffmpeg.mjs --target x86_64-pc-windows-msvc
 *   node scripts/ci_download_ffmpeg.mjs --target x86_64-unknown-linux-gnu
 */

import { execSync } from 'node:child_process';
import { chmodSync, createWriteStream, mkdirSync,
         readdirSync, renameSync, rmSync, statSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import https from 'node:https';

const DST_DIR = path.resolve('src-tauri', 'binaries');

// ── Parse args ──────────────────────────────────────────────────────────────
const targetIdx = process.argv.indexOf('--target');
if (targetIdx < 0 || !process.argv[targetIdx + 1]) {
  console.error('error: missing --target <target-triple>');
  process.exit(2);
}
const target = process.argv[targetIdx + 1];
const isWindows = target.includes('windows');

console.log(`target:  ${target}`);
console.log(`dest:    ${DST_DIR}/`);

// ── HTTP helpers ────────────────────────────────────────────────────────────
function httpGet(url, { hops = 10, headers = {} } = {}) {
  return new Promise((resolve, reject) => {
    function attempt(u, n) {
      if (n <= 0) { reject(new Error('too many redirects')); return; }
      https.get(u, { headers: { 'User-Agent': 'padwright-ci', ...headers } }, res => {
        if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
          const next = new URL(res.headers.location, u).toString();
          res.resume();
          attempt(next, n - 1);
          return;
        }
        if (res.statusCode !== 200) {
          reject(new Error(`HTTP ${res.statusCode} from ${u}`));
          return;
        }
        resolve(res);
      }).on('error', reject);
    }
    attempt(url, hops);
  });
}

async function download(url, dst) {
  const res = await httpGet(url);
  await new Promise((resolve, reject) => {
    const out = createWriteStream(dst);
    res.pipe(out);
    out.on('finish', () => out.close(resolve));
    out.on('error', reject);
  });
  return statSync(dst).size;
}

// ── Extract helpers ─────────────────────────────────────────────────────────
function extractZip(archive, into) {
  if (process.platform === 'win32') {
    execSync(
      `powershell -NoProfile -Command "Expand-Archive -Path '${archive}' -DestinationPath '${into}' -Force"`,
      { stdio: 'inherit' }
    );
  } else {
    execSync(`unzip -q -o '${archive}' -d '${into}'`, { stdio: 'inherit' });
  }
}

function extractTarXz(archive, into) {
  execSync(`tar -xJf '${archive}' -C '${into}'`, { stdio: 'inherit' });
}

function findBin(dir, baseName) {
  const candidates = isWindows ? [`${baseName}.exe`] : [baseName];
  for (const ent of readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, ent.name);
    if (ent.isFile() && candidates.includes(ent.name)) return p;
    if (ent.isDirectory()) {
      const found = findBin(p, baseName);
      if (found) return found;
    }
  }
  return null;
}

// ── Per-target sources ──────────────────────────────────────────────────────
const BTBN = 'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest';
const EVERMEET = 'https://evermeet.cx/ffmpeg';

// Returns { ffmpegBin, ffprobeBin } — absolute paths to extracted binaries.
async function fetchForTarget(workDir) {
  // ─── BtbN: Linux + Windows ────────────────────────────────────────────────
  const btbn = {
    'x86_64-unknown-linux-gnu':  { slug: 'linux64',    ext: 'tar.xz' },
    'aarch64-unknown-linux-gnu': { slug: 'linuxarm64', ext: 'tar.xz' },
    'x86_64-pc-windows-msvc':    { slug: 'win64',      ext: 'zip' },
  }[target];
  if (btbn) {
    const name = `ffmpeg-master-latest-${btbn.slug}-lgpl.${btbn.ext}`;
    const url = `${BTBN}/${name}`;
    const archive = path.join(workDir, name);
    console.log(`source:  BtbN/FFmpeg-Builds (${btbn.slug})`);
    console.log(`archive: ${url}`);
    const bytes = await download(url, archive);
    console.log(`downloaded ${bytes.toLocaleString()} bytes`);
    const into = path.join(workDir, 'extract');
    mkdirSync(into, { recursive: true });
    (btbn.ext === 'zip' ? extractZip : extractTarXz)(archive, into);
    return { ffmpegBin: findBin(into, 'ffmpeg'), ffprobeBin: findBin(into, 'ffprobe') };
  }

  // ─── evermeet.cx: macOS Intel ─────────────────────────────────────────────
  if (target === 'x86_64-apple-darwin') {
    console.log('source:  evermeet.cx (macOS Intel)');
    const out = {};
    for (const bin of ['ffmpeg', 'ffprobe']) {
      const url = `${EVERMEET}/getrelease/${bin}/zip`;
      const archive = path.join(workDir, `${bin}.zip`);
      console.log(`  ${bin}: ${url}`);
      const bytes = await download(url, archive);
      console.log(`  downloaded ${bytes.toLocaleString()} bytes`);
      const into = path.join(workDir, `extract-${bin}`);
      mkdirSync(into, { recursive: true });
      extractZip(archive, into);
      const found = findBin(into, bin);
      if (!found) throw new Error(`could not find ${bin} in evermeet archive`);
      out[`${bin}Bin`] = found;
    }
    return out;
  }

  if (target === 'aarch64-apple-darwin') {
    console.error('error: aarch64-apple-darwin is not supported by this '
                + 'script. Apple Silicon users run the Intel build via '
                + 'Rosetta. See release.yml matrix comment.');
    process.exit(2);
  }

  console.error(`error: unsupported target ${target}`);
  process.exit(2);
}

// ── Main ────────────────────────────────────────────────────────────────────
const workDir = path.join(tmpdir(), `padwright-ffmpeg-${target}`);
rmSync(workDir, { recursive: true, force: true });
mkdirSync(workDir, { recursive: true });

const { ffmpegBin, ffprobeBin } = await fetchForTarget(workDir);
if (!ffmpegBin || !ffprobeBin) {
  console.error('error: could not locate ffmpeg/ffprobe after extraction.');
  process.exit(1);
}

mkdirSync(DST_DIR, { recursive: true });
const ext = isWindows ? '.exe' : '';
const ffmpegDst  = path.join(DST_DIR, `ffmpeg-${target}${ext}`);
const ffprobeDst = path.join(DST_DIR, `ffprobe-${target}${ext}`);

renameSync(ffmpegBin,  ffmpegDst);
renameSync(ffprobeBin, ffprobeDst);
if (!isWindows) {
  chmodSync(ffmpegDst,  0o755);
  chmodSync(ffprobeDst, 0o755);
}

console.log(`installed ${ffmpegDst}  (${statSync(ffmpegDst).size.toLocaleString()} bytes)`);
console.log(`installed ${ffprobeDst} (${statSync(ffprobeDst).size.toLocaleString()} bytes)`);
console.log('done.');
