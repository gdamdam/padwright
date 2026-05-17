#!/usr/bin/env node
/**
 * scripts/ci_download_ffmpeg.mjs
 *
 * Download static LGPL ffmpeg + ffprobe binaries for a given target triple
 * and install them as Tauri sidecars under src-tauri/binaries/.
 *
 * Used by .github/workflows/release.yml. Source: BtbN/FFmpeg-Builds, which
 * publishes consistent LGPL releases for all major platforms.
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
import { chmodSync, createWriteStream, existsSync, mkdirSync,
         readdirSync, renameSync, rmSync, statSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import https from 'node:https';

const DST_DIR = path.resolve('src-tauri', 'binaries');
const BTBN_BASE = 'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest';

// BtbN naming convention: ffmpeg-master-latest-<slug>-lgpl.<ext>
const PLATFORM_MAP = {
  'aarch64-apple-darwin':     { slug: 'macosarm64', ext: 'zip',    isWin: false },
  'x86_64-apple-darwin':      { slug: 'macos64',    ext: 'zip',    isWin: false },
  'x86_64-pc-windows-msvc':   { slug: 'win64',      ext: 'zip',    isWin: true  },
  'x86_64-unknown-linux-gnu': { slug: 'linux64',    ext: 'tar.xz', isWin: false },
  'aarch64-unknown-linux-gnu':{ slug: 'linuxarm64', ext: 'tar.xz', isWin: false },
};

// ── Parse args ──────────────────────────────────────────────────────────────
const targetIdx = process.argv.indexOf('--target');
if (targetIdx < 0 || !process.argv[targetIdx + 1]) {
  console.error('error: missing --target <target-triple>');
  console.error('valid targets:', Object.keys(PLATFORM_MAP).join(', '));
  process.exit(2);
}
const target = process.argv[targetIdx + 1];
const plat = PLATFORM_MAP[target];
if (!plat) {
  console.error(`error: unsupported target ${target}`);
  console.error('valid targets:', Object.keys(PLATFORM_MAP).join(', '));
  process.exit(2);
}

const archiveName = `ffmpeg-master-latest-${plat.slug}-lgpl.${plat.ext}`;
const archiveUrl  = `${BTBN_BASE}/${archiveName}`;
const archivePath = path.join(tmpdir(), archiveName);
const extractDir  = path.join(tmpdir(), `ffmpeg-extract-${plat.slug}`);

console.log(`target:  ${target}`);
console.log(`archive: ${archiveUrl}`);
console.log(`dest:    ${DST_DIR}/`);

// ── Download (follows redirects) ────────────────────────────────────────────
function download(url, dst, maxHops = 10) {
  return new Promise((resolve, reject) => {
    function attempt(u, hops) {
      if (hops <= 0) { reject(new Error('too many redirects')); return; }
      https.get(u, { headers: { 'User-Agent': 'padwright-ci' } }, res => {
        if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
          // Resolve relative redirect against current URL
          const next = new URL(res.headers.location, u).toString();
          res.resume();
          attempt(next, hops - 1);
          return;
        }
        if (res.statusCode !== 200) {
          reject(new Error(`HTTP ${res.statusCode} from ${u}`));
          return;
        }
        const out = createWriteStream(dst);
        res.pipe(out);
        out.on('finish', () => out.close(resolve));
        out.on('error', reject);
      }).on('error', reject);
    }
    attempt(url, maxHops);
  });
}

console.log('downloading…');
await download(archiveUrl, archivePath);
console.log(`downloaded ${statSync(archivePath).size.toLocaleString()} bytes`);

// ── Extract ─────────────────────────────────────────────────────────────────
rmSync(extractDir, { recursive: true, force: true });
mkdirSync(extractDir, { recursive: true });

console.log(`extracting → ${extractDir}`);
if (plat.ext === 'zip') {
  if (process.platform === 'win32') {
    execSync(
      `powershell -NoProfile -Command "Expand-Archive -Path '${archivePath}' -DestinationPath '${extractDir}' -Force"`,
      { stdio: 'inherit' }
    );
  } else {
    execSync(`unzip -q '${archivePath}' -d '${extractDir}'`, { stdio: 'inherit' });
  }
} else {
  // tar.xz
  execSync(`tar -xJf '${archivePath}' -C '${extractDir}'`, { stdio: 'inherit' });
}

// ── Locate ffmpeg + ffprobe inside the extracted tree ──────────────────────
function findBin(dir, baseName) {
  const candidates = plat.isWin ? [`${baseName}.exe`] : [baseName];
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

const ffmpegBin  = findBin(extractDir, 'ffmpeg');
const ffprobeBin = findBin(extractDir, 'ffprobe');
if (!ffmpegBin || !ffprobeBin) {
  console.error('error: could not locate ffmpeg/ffprobe inside extracted archive');
  console.error(`  extractDir: ${extractDir}`);
  process.exit(1);
}

// ── Install into src-tauri/binaries/ with target-triple suffix ──────────────
mkdirSync(DST_DIR, { recursive: true });

const ext = plat.isWin ? '.exe' : '';
const ffmpegDst  = path.join(DST_DIR, `ffmpeg-${target}${ext}`);
const ffprobeDst = path.join(DST_DIR, `ffprobe-${target}${ext}`);

renameSync(ffmpegBin,  ffmpegDst);
renameSync(ffprobeBin, ffprobeDst);
if (!plat.isWin) {
  chmodSync(ffmpegDst,  0o755);
  chmodSync(ffprobeDst, 0o755);
}

console.log(`installed ${ffmpegDst}  (${statSync(ffmpegDst).size.toLocaleString()} bytes)`);
console.log(`installed ${ffprobeDst} (${statSync(ffprobeDst).size.toLocaleString()} bytes)`);
console.log('done.');
