'use strict';
const { spawnSync } = require('node:child_process');
const path = require('node:path');
const target = path.join(__dirname, 'validate-stage59b-ui.js');
const result = spawnSync(process.execPath, [target], { encoding: 'utf8' });
if (result.stdout) process.stdout.write(result.stdout);
if (result.stderr) process.stderr.write(result.stderr);
if (result.status !== 0) process.exit(result.status ?? 1);
console.log('[PASS] Electron Stage 50C renderer UI 검증: Stage59B/0.5.10 사용자 계약');
