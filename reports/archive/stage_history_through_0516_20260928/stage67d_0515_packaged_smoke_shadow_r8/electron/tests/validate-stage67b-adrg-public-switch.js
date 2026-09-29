'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const serviceSource = fs.readFileSync(path.join(root, 'src/kdrg-search-service.js'), 'utf8');
const contractSource = fs.readFileSync(path.join(root, 'src/search-result-contract.js'), 'utf8');
const app = fs.readFileSync(path.join(root, 'renderer/app.js'), 'utf8');
const html = fs.readFileSync(path.join(root, 'renderer/index.html'), 'utf8');
const fmt = fs.readFileSync(path.join(root, 'renderer/ui-formatters.js'), 'utf8');
const official = fs.readFileSync(path.join(root, 'renderer/official-condition-text.js'), 'utf8');

assert.match(serviceSource, /STAGE59B_PUBLIC_TYPES = Object\.freeze\(\['CODE', 'ADRG'\]\)/);
assert.match(contractSource, /SEARCH_ENTITY_TYPES = Object\.freeze\(\['CODE', 'ADRG'\]\)/);

// Internal AADRG capability must remain.
assert.match(serviceSource, /ENTITY_TYPES = Object\.freeze\(\['CODE', 'ADRG', 'AADRG', 'RDRG', 'TABLE'\]\)/);
assert.match(serviceSource, /entityType === 'AADRG'/);
assert.match(app, /function renderAadrgDetail\(/);

// Public selector/wording must be ADRG-centered.
assert.match(html, /<option value="ADRG">ADRG<\/option>/);
assert.doesNotMatch(html, /<option value="AADRG">AADRG<\/option>/);
assert.match(html, /코드·ADRG·질병군명 입력/);
assert.doesNotMatch(html, /코드·AADRG·질병군명 입력/);

assert.match(fmt, /const ordered = \['CODE', 'ADRG'\]/);
assert.match(app, /for \(const type of \['CODE', 'ADRG'\]\)/);
assert.match(app, /function renderRelatedAdrgList\(/);
assert.match(app, /\['관련 ADRG', `\$\{Ui\.formatNumber\(relatedAdrgs\.length\)\}개`\]/);
assert.match(app, /이 코드와 직접 연결되는 ADRG입니다/);

// Relation projection must be ADRG, not public AADRG.
assert.match(serviceSource, /entity_type: 'ADRG'.*entity_id: parent\.entity_id/s);
assert.doesNotMatch(
  serviceSource,
  /entity_type: 'AADRG', entity_id: child\.entity_id, title: child\.title/,
);
assert.match(serviceSource, /ADRG 단위로 표시합니다/);

// Exact code public relation must use real related_adrgs.
assert.match(
  serviceSource,
  /entityTypes\.includes\('ADRG'\).*exactCode\.related_adrgs.*add\('ADRG'/s,
);
assert.doesNotMatch(
  serviceSource,
  /DIRECT_CODE_RELATION[\s\S]{0,300}slice\(/,
);

// ADRG detail must not publicly expose derived AADRG section.
const adrgStart = app.indexOf('function renderAdrgDetail(');
const aadrgStart = app.indexOf('function renderAadrgDetail(');
assert.ok(adrgStart >= 0 && aadrgStart > adrgStart);
const adrgBlock = app.slice(adrgStart, aadrgStart);
assert.doesNotMatch(adrgBlock, /파생 AADRG/);
assert.doesNotMatch(adrgBlock, /aadrgSection/);

// Official-source renderer remains present in Shadow.
assert.ok(official.length > 100);
assert.match(app, /renderUserConditionSummary/);

console.log('[PASS] Stage67B ADRG public-switch static contract');
