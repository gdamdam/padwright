#!/usr/bin/env node
/**
 * scripts/compose_release_notes.mjs
 *
 * Render .github/RELEASE_NOTES_TEMPLATE.md with substitutions:
 *   {{ version }}    → the supplied version
 *   {{ repo }}       → the supplied owner/name
 *   {{ changelog }}  → the CHANGELOG.md section for that version
 *                      (falls back to a placeholder if missing)
 *
 * Writes the result to stdout. Used by .github/workflows/release.yml
 * to set tauri-action's releaseBody.
 *
 * Usage:
 *   node scripts/compose_release_notes.mjs \
 *     --version v1.0.0 \
 *     --repo myorg/padwright \
 *     [--template .github/RELEASE_NOTES_TEMPLATE.md] \
 *     [--changelog CHANGELOG.md]
 */

import { readFileSync } from 'node:fs';

function arg(name, required = true, fallback = null) {
  const i = process.argv.indexOf(`--${name}`);
  if (i < 0 || !process.argv[i + 1]) {
    if (required) {
      console.error(`error: missing --${name} <value>`);
      process.exit(2);
    }
    return fallback;
  }
  return process.argv[i + 1];
}

const version  = arg('version');
const repo     = arg('repo');
const tplPath  = arg('template', false, '.github/RELEASE_NOTES_TEMPLATE.md');
const clPath   = arg('changelog', false, 'CHANGELOG.md');

function readChangelogSection(text, version) {
  const v = version.replace(/^v/, '');
  const startRe = new RegExp(`^##\\s*\\[${v.replace(/\./g, '\\.')}\\]`);
  const nextRe  = /^##\s*\[/;
  const lines = text.split('\n');
  const out = [];
  let inside = false;
  for (const line of lines) {
    if (!inside && startRe.test(line)) { inside = true; continue; }
    if (inside && nextRe.test(line)) break;
    if (inside) out.push(line);
  }
  return out.join('\n').trim();
}

let template;
try { template = readFileSync(tplPath, 'utf8'); }
catch (e) {
  console.error(`could not read ${tplPath}: ${e.message}`);
  process.exit(1);
}

let changelog = '';
try { changelog = readChangelogSection(readFileSync(clPath, 'utf8'), version); }
catch (e) { /* CHANGELOG missing is fine */ }

if (!changelog) {
  changelog = `_No CHANGELOG entry for ${version} yet._`;
}

// Strip leading HTML comment (template authoring notes) before publishing.
template = template.replace(/^<!--[\s\S]*?-->\n*/, '');

const out = template
  .replaceAll('{{ version }}', version)
  .replaceAll('{{ repo }}', repo)
  .replaceAll('{{ changelog }}', changelog);

process.stdout.write(out);
