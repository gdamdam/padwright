#!/usr/bin/env node
/**
 * scripts/changelog_extract.mjs
 *
 * Extract the section of CHANGELOG.md that corresponds to a given
 * version, for feeding into a GitHub Release body. The leading `v`
 * is optional in --version.
 *
 * Usage:
 *   node scripts/changelog_extract.mjs --version v1.0.0
 *   node scripts/changelog_extract.mjs --version 1.0.0
 *
 * Stdout: the section content (without its own `## [x.y.z]` header).
 * Exits 1 if no matching section is found, 2 on bad args.
 */

import { readFileSync } from 'node:fs';

const versionIdx = process.argv.indexOf('--version');
if (versionIdx < 0 || !process.argv[versionIdx + 1]) {
  console.error('usage: changelog_extract.mjs --version <semver>');
  process.exit(2);
}
const version = process.argv[versionIdx + 1].replace(/^v/, '');
const path = process.argv.includes('--file')
  ? process.argv[process.argv.indexOf('--file') + 1]
  : 'CHANGELOG.md';

let text;
try { text = readFileSync(path, 'utf8'); }
catch (e) { console.error(`could not read ${path}: ${e.message}`); process.exit(1); }

const lines = text.split('\n');
const startRe = new RegExp(`^##\\s*\\[${version.replace(/\./g, '\\.')}\\]`);
const nextSectionRe = /^##\s*\[/;

const out = [];
let inSection = false;
for (const line of lines) {
  if (!inSection && startRe.test(line)) { inSection = true; continue; }
  if (inSection && nextSectionRe.test(line)) break;
  if (inSection) out.push(line);
}

const content = out.join('\n').trim();
if (!content) {
  console.error(`no CHANGELOG section found for ${version}`);
  process.exit(1);
}

process.stdout.write(content + '\n');
