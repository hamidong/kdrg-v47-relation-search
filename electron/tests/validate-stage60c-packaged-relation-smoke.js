'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { KdrgSearchService } = require('../src/kdrg-search-service');

const root = path.resolve(__dirname, '..');
const smokePath = path.join(root, 'src', 'packaged-runtime-smoke.js');
const dataPath = path.resolve(root, '..', 'data', 'kdrg_v47_search_integrated_v3.json');
const source = fs.readFileSync(smokePath, 'utf8');

function declarationSlice(marker, nextMarkers) {
  const start = source.indexOf(marker);
  assert.ok(start >= 0, `missing declaration marker: ${marker}`);

  const candidates = nextMarkers
    .map((next) => source.indexOf(next, start + marker.length))
    .filter((value) => value > start);

  const end = candidates.length ? Math.min(...candidates) : source.length;
  return source.slice(start, end).trim();
}

const legacySource = declarationSlice(
  'function findLegacyRelationSmokeFixture',
  ['\nfunction findRelationSmokeFixture'],
);
const wrapperSource = declarationSlice(
  'function findRelationSmokeFixture',
  ['\nfunction ', '\nasync function '],
);

assert.match(legacySource, /condition\/table indexes unavailable/);
assert.match(wrapperSource, /KdrgSearchService/);
assert.match(wrapperSource, /findLegacyRelationSmokeFixture/);
assert.match(wrapperSource, /recordMaps\.CODE/);
assert.match(wrapperSource, /recordMaps\.AADRG/);
assert.match(wrapperSource, /non-AADRG public result/);
assert.match(wrapperSource, /parent_adrg/);

const context = vm.createContext({
  console,
  Map,
  String,
  Array,
  Boolean,
  Error,
});
vm.runInContext(
  `${legacySource}\n${wrapperSource}`,
  context,
  { filename: 'stage60c-relation-fixture-wrapper.vm.js' },
);

const findRelationSmokeFixture = context.findRelationSmokeFixture;
assert.equal(typeof findRelationSmokeFixture, 'function');

const service = new KdrgSearchService(dataPath);
const fixture = findRelationSmokeFixture(service);

assert.equal(fixture.runtime_fixture, true);
assert.equal(fixture.public_entity_type, 'AADRG');
assert.ok(Array.isArray(fixture.conditions) && fixture.conditions.length >= 2);
assert.equal(fixture.operator, 'AND');
assert.match(String(fixture.adrg || ''), /^[A-Z0-9-]+$/);
assert.match(String(fixture.aadrg || ''), /^[A-Z0-9-]+$/);

const response = service.relationSearch(
  fixture.conditions,
  fixture.operator,
  fixture.options || { limit: 500 },
);
assert.ok(response.results.length > 0);
assert.ok(response.results.every((item) => item.entity_type === 'AADRG'));

const projected = response.results.find(
  (item) => (
    String(item.entity_id) === String(fixture.aadrg)
    && String(item.parent_adrg) === String(fixture.adrg)
  ),
);
assert.ok(projected, 'runtime AADRG projection fixture not found');

const runStart = source.indexOf('async function runPackagedRuntimeSmoke');
assert.ok(runStart >= 0);
const callStart = source.indexOf('findRelationSmokeFixture(', runStart);
const contractMarker = source.indexOf('relation_contract_verified', callStart);
assert.ok(callStart >= 0 && contractMarker > callStart);

console.log(
  `[PASS] Stage60C runtime relation fixture: ${fixture.adrg} -> ${fixture.aadrg} | ${fixture.codes.join(',')}`,
);
