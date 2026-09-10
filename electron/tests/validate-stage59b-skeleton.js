'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const pkg = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8'));
const lock = JSON.parse(fs.readFileSync(path.join(root, 'package-lock.json'), 'utf8'));
const main = fs.readFileSync(path.join(root, 'main.js'), 'utf8');
const preload = fs.readFileSync(path.join(root, 'preload.js'), 'utf8');
const app = fs.readFileSync(path.join(root, 'renderer/app.js'), 'utf8');

const stableSemver = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/;

assert.match(pkg.version, stableSemver, 'package.version must be stable semver');
assert.equal(lock.version, pkg.version, 'package-lock.version must match package.version');

const lockRootVersion = lock.packages?.['']?.version;
if (lockRootVersion !== undefined) {
  assert.equal(
    lockRootVersion,
    pkg.version,
    "package-lock packages[''].version must match package.version",
  );
}

assert.match(main, /contextIsolation:\s*true/);
assert.match(main, /nodeIntegration:\s*false/);
assert.match(preload, /contextBridge\.exposeInMainWorld/);
assert.doesNotMatch(app, /\brequire\s*\(/);
assert.doesNotMatch(app, /\beval\s*\(/);
assert.doesNotMatch(app, /innerHTML/);

console.log(`stage59_skeleton: PASS version=${pkg.version}`);
