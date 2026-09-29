'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const service = fs.readFileSync(path.join(root, 'src/kdrg-search-service.js'), 'utf8');
const contract = fs.readFileSync(path.join(root, 'src/search-result-contract.js'), 'utf8');
const app = fs.readFileSync(path.join(root, 'renderer/app.js'), 'utf8');
const html = fs.readFileSync(path.join(root, 'renderer/index.html'), 'utf8');
const fmt = fs.readFileSync(path.join(root, 'renderer/ui-formatters.js'), 'utf8');

// Public contract.
assert.match(service, /STAGE59B_PUBLIC_TYPES = Object\.freeze\(\['CODE', 'ADRG'\]\)/);
assert.match(contract, /SEARCH_ENTITY_TYPES = Object\.freeze\(\['CODE', 'ADRG'\]\)/);
assert.match(fmt, /const ordered = \['CODE', 'ADRG'\]/);
assert.match(html, /<option value="ADRG">ADRG<\/option>/);
assert.doesNotMatch(html, /AADRG/);

// Overview public metric uses ADRG count.
assert.match(
  app,
  /setText\('metric-aadrg', Ui\.formatNumber\(snapshot\.counts\.adrg\)\)/,
);
assert.doesNotMatch(
  app,
  /setText\('metric-aadrg', Ui\.formatNumber\(snapshot\.counts\.aadrg\)\)/,
);

// CODE and relation public UI.
assert.match(app, /'관련 ADRG'/);
assert.match(app, /관련 ADRG \$\{Ui\.formatNumber/);
assert.match(app, /detail\.related_adrg_summaries/);
assert.doesNotMatch(app, /detail\.related_adrg_summaries[^\n]*length,/);
assert.doesNotMatch(
  app,
  /관련 AADRG \$\{Ui\.formatNumber\([\s\S]{0,120}detail\.related_aadrg_summaries/,
);
assert.match(app, /관계검색 ADRG/);
assert.match(app, /ADRG 상세 보기/);
assert.match(app, /makeBadge\('ADRG'\)/);

// Public formatter order and ADRG card chips.
assert.match(fmt, /const ordered = \['CODE', 'ADRG'\]/);
assert.doesNotMatch(fmt, /`AADRG \$\{formatNumber\(summary\.aadrg_count/);
assert.match(fmt, /`세부 질병군 \$\{formatNumber\(summary\.aadrg_count/);
assert.doesNotMatch(fmt, /`관련 AADRG \$\{formatNumber\(summary\.related_aadrg_count/);

// Exact code route must use real related_adrgs.
assert.match(
  service,
  /entityTypes\.includes\('ADRG'\).*exactCode\.related_adrgs.*add\('ADRG'/s,
);

// Internal AADRG capability remains.
assert.match(service, /ENTITY_TYPES = Object\.freeze\(\['CODE', 'ADRG', 'AADRG', 'RDRG', 'TABLE'\]\)/);
assert.match(service, /recordMaps\.AADRG/);
assert.match(service, /entityType === 'AADRG'/);
assert.match(app, /function renderAadrgDetail\(/);
assert.match(app, /row\.dataset\.entityType = 'AADRG'/);

// Public ADRG detail must not render the derived AADRG section.
const adrgStart = app.indexOf('function renderAdrgDetail(');
const aadrgStart = app.indexOf('function renderAadrgDetail(');
assert.ok(adrgStart >= 0 && aadrgStart > adrgStart);
const adrgBlock = app.slice(adrgStart, aadrgStart);
assert.doesNotMatch(adrgBlock, /파생 AADRG/);
assert.doesNotMatch(adrgBlock, /aadrgSection/);

console.log('[PASS] Stage67C ADRG public UI contract');
