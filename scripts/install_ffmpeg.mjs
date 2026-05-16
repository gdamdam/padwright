#!/usr/bin/env node
// Download static ffmpeg/ffprobe binaries and install them as Tauri sidecars.
//
// Usage:
//   node scripts/install_ffmpeg.mjs            # auto-detect host
//   node scripts/install_ffmpeg.mjs --target aarch64-apple-darwin
//
// Sources used (all LGPL-compatible static builds):
//   macOS  arm64 / x64 — https://evermeet.cx/ffmpeg/
//   Linux  x64         — https://johnvansickle.com/ffmpeg/
//   Windows x64        — https://www.gyan.dev/ffmpeg/builds/
//
// This script intentionally favors clarity over completeness — for niche
// targets, drop the binaries into src-tauri/binaries/ manually.

import { execSync } from 'node:child_process';
import { chmodSync, existsSync, mkdirSync, renameSync, rmSync } from 'node:fs';
import { platform, arch, tmpdir } from 'node:os';
import path from 'node:path';

const DST_DIR = path.resolve('src-tauri', 'binaries');
const argTarget = process.argv.find(a => a.startsWith('--target='))?.split('=')[1];

function hostTriple() {
  try {
    const m = execSync('rustc -vV', { encoding: 'utf8' }).match(/host:\s*(\S+)/);
    if (m) return m[1];
  } catch {}
  const p = platform(), a = arch();
  if (p === 'darwin') return a === 'arm64' ? 'aarch64-apple-darwin' : 'x86_64-apple-darwin';
  if (p === 'win32') return 'x86_64-pc-windows-msvc';
  return a === 'arm64' ? 'aarch64-unknown-linux-gnu' : 'x86_64-unknown-linux-gnu';
}

const triple = argTarget || hostTriple();
const isWin = triple.includes('windows');
const ext = isWin ? '.exe' : '';

console.log(`target: ${triple}`);
console.log('NOTE: this script prints download URLs — run them yourself and');
console.log('drop the unpacked ffmpeg/ffprobe binaries into:');
console.log(`  ${DST_DIR}/ffmpeg-${triple}${ext}`);
console.log(`  ${DST_DIR}/ffprobe-${triple}${ext}`);
console.log();

const sources = {
  'aarch64-apple-darwin':       'https://evermeet.cx/ffmpeg/ffmpeg-7.1.zip   (arm64 build) and ffprobe-7.1.zip',
  'x86_64-apple-darwin':        'https://evermeet.cx/ffmpeg/ffmpeg-7.1.zip   (intel) and ffprobe-7.1.zip',
  'x86_64-pc-windows-msvc':     'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip',
  'x86_64-unknown-linux-gnu':   'https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz',
  'aarch64-unknown-linux-gnu':  'https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-arm64-static.tar.xz',
};

console.log('source for this target:');
console.log('  ' + (sources[triple] || 'unknown — please find a static LGPL build'));
console.log();
console.log('after downloading and unpacking, set perms:');
console.log(`  chmod +x ${DST_DIR}/ffmpeg-${triple}${ext} ${DST_DIR}/ffprobe-${triple}${ext}`);
