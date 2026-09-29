'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'src/packaged-runtime-smoke.js'), 'utf8');
const validate = fs.readFileSync(path.join(root, 'tests/validate-packaged-runtime-smoke.js'), 'utf8');
const stage60c = fs.readFileSync(path.join(root, 'tests/validate-stage60c-packaged-relation-smoke.js'), 'utf8');
const service = fs.readFileSync(path.join(root, 'src/kdrg-search-service.js'), 'utf8');
const app = fs.readFileSync(path.join(root, 'renderer/app.js'), 'utf8');
const html = fs.readFileSync(path.join(root, 'renderer/index.html'), 'utf8');

// Public packaged relation contract is ADRG.
assert.match(source, /public_entity_type: 'ADRG'/);
assert.doesNotMatch(source, /public_entity_type: 'AADRG'/);
assert.match(source, /function validateRelationResponse\(/);
assert.match(source, /String\(item\.entity_type \?\? ''\)\.toUpperCase\(\) !== 'ADRG'/);
assert.match(source, /duplicate ADRG results/);
assert.match(source, /public AADRG payload leak/);
assert.match(source, /function findRelationSmokeFixture\(/);
assert.match(source, /aadrg: null/);
assert.match(source, /filter\.value = 'ADRG';/);
assert.doesNotMatch(source, /filter\.value = 'AADRG';/);
assert.match(source, /data-entity-type=\\"ADRG\\"/);
assert.doesNotMatch(source, /data-entity-type=\\"AADRG\\"/);
assert.match(source, /detailCaption === fixture\.adrg/);
assert.doesNotMatch(source, /detailCaption === fixture\.aadrg/);
assert.match(source, /fixture\.adrg \+ ' inline TABLE load'/);
assert.doesNotMatch(source, /fixture\.aadrg \+ ' inline TABLE load'/);
assert.match(source, /selected_aadrg: null/);
assert.match(source, /non-ADRG public result/);
assert.doesNotMatch(source, /non-AADRG public result/);

// Packaged validator follows the same public contract.
assert.match(validate, /packaged smoke ADRG filter/);
assert.match(validate, /packaged smoke ADRG result selector/);
assert.match(validate, /packaged smoke ADRG detail caption/);
assert.match(validate, /selected_aadrg: null/);

// Stage60C relation smoke projects the public parent ADRG.
const stage60cLines = stage60c.split(/\r?\n/);
assert.ok(stage60cLines.some(
  (line) => line.includes('assert.match')
    && line.includes('wrapperSource')
    && line.includes('conditionGroupsByAdrg'),
));
assert.ok(stage60cLines.some(
  (line) => line.includes('assert.match')
    && line.includes('wrapperSource')
    && line.includes('relationSearch'),
));
assert.ok(!stage60cLines.some(
  (line) => line.includes('assert.match')
    && line.includes('wrapperSource')
    && line.includes('KdrgSearchService'),
));
assert.ok(!stage60cLines.some(
  (line) => line.includes('assert.match')
    && line.includes('wrapperSource')
    && line.includes('recordMaps')
    && line.includes('AADRG'),
));
assert.match(stage60c, /fixture\.public_entity_type, 'ADRG'/);
assert.match(stage60c, /item\.entity_type === 'ADRG'/);
assert.match(stage60c, /item\.entity_id\) === String\(fixture\.adrg\)/);
assert.match(stage60c, /item\.parent_adrg\) === String\(fixture\.adrg\)/);
assert.match(stage60c, /fixture\.aadrg, null/);
assert.match(stage60c, /service\.recordMaps\.AADRG instanceof Map/);

// AADRG internal capability is still intentionally preserved.
assert.match(service, /recordMaps\.AADRG/);
assert.match(service, /entityType === 'AADRG'/);
assert.match(app, /function renderAadrgDetail\(/);

// But the primary HTML surface stays hidden.
assert.doesNotMatch(html, /AADRG/);

console.log('[PASS] Stage67D packaged ADRG public contract');
