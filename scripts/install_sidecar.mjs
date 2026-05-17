#!/usr/bin/env node
// Copy the PyInstaller-produced binary into src-tauri/binaries/ with the
// target-triple suffix that Tauri's bundler expects.
//
// Usage: node scripts/install_sidecar.mjs

import { execSync } from 'node:child_process';
import { copyFileSync, existsSync, mkdirSync, chmodSync } from 'node:fs';
import { platform, arch } from 'node:os';
import path from 'node:path';

const SRC_DIR = path.resolve('dist');
const DST_DIR = path.resolve('src-tauri', 'binaries');

function targetTriple() {
  // Trust `rustc -vV` if available — it's the canonical source.
  try {
    const out = execSync('rustc -vV', { encoding: 'utf8' });
    const m = out.match(/host:\s*(\S+)/);
    if (m) return m[1];
  } catch { /* fall through */ }
  // Fallback heuristic.
  const p = platform();
  const a = arch();
  if (p === 'darwin') return a === 'arm64' ? 'aarch64-apple-darwin' : 'x86_64-apple-darwin';
  if (p === 'win32') return 'x86_64-pc-windows-msvc';
  if (p === 'linux') return a === 'arm64' ? 'aarch64-unknown-linux-gnu' : 'x86_64-unknown-linux-gnu';
  throw new Error(`unsupported platform: ${p}/${a}`);
}

function install(name) {
  const isWin = platform() === 'win32';
  const ext = isWin ? '.exe' : '';
  const src = path.join(SRC_DIR, name + ext);
  if (!existsSync(src)) {
    console.error(`error: ${src} not found — run \`pyinstaller --clean pyinstaller_app.spec\` first`);
    process.exit(1);
  }
  mkdirSync(DST_DIR, { recursive: true });
  const triple = targetTriple();
  const dst = path.join(DST_DIR, `${name}-${triple}${ext}`);
  copyFileSync(src, dst);
  if (!isWin) chmodSync(dst, 0o755);
  console.log(`installed: ${dst}`);
}

install('padwright-server');
