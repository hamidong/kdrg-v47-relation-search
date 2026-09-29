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
assert.match(wrapperSource, /conditionGroupsByAdrg/);
assert.match(wrapperSource, /recordMaps\?\.TABLE|recordMaps\.TABLE|recordMaps\?\.TABLE/);
assert.match(wrapperSource, /relationSearch/);
assert.match(wrapperSource, /public_entity_type: 'ADRG'/);
assert.match(wrapperSource, /aadrg: null/);
assert.doesNotMatch(wrapperSource, /findLegacyRelationSmokeFixture/);
assert.doesNotMatch(wrapperSource, /KdrgSearchService/);
assert.doesNotMatch(wrapperSource, /non-AADRG public result/);
assert.match(source, /function validateRelationResponse\(response, expectedAdrg = null\)/);
assert.match(source, /packaged ADRG relation response contract mismatch/);
assert.match(source, /String\(item\.entity_type \?\? ''\)\.toUpperCase\(\) !== 'ADRG'/);
assert.match(source, /duplicate ADRG results/);
assert.match(source, /public AADRG payload leak/);
assert.match(source, /function findRelationSmokeFixture\(service\)/);
assert.match(source, /public_entity_type: 'ADRG'/);
assert.match(source, /aadrg: null/);
assert.doesNotMatch(source, /function validateRelationResponse\(\.\.\.args\)/);

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
assert.equal(fixture.public_entity_type, 'ADRG');
assert.ok(Array.isArray(fixture.conditions) && fixture.conditions.length >= 2);
assert.equal(fixture.operator, 'AND');
assert.match(String(fixture.adrg || ''), /^[A-Z0-9-]+$/);
assert.equal(fixture.aadrg, null);
assert.ok(service.recordMaps.AADRG instanceof Map && service.recordMaps.AADRG.size > 0, 'internal AADRG map missing');

const response = service.relationSearch(
  fixture.conditions,
  fixture.operator,
  fixture.options || { limit: 500 },
);
assert.ok(response.results.length > 0);
assert.ok(response.results.every((item) => item.entity_type === 'ADRG'));

const projected = response.results.find(
  (item) => (
    String(item.entity_id) === String(fixture.adrg)
    && String(item.parent_adrg) === String(fixture.adrg)
  ),
);
assert.ok(projected, 'runtime ADRG projection fixture not found');

const runStart = source.indexOf('async function runPackagedRuntimeSmoke');
assert.ok(runStart >= 0);
const callStart = source.indexOf('findRelationSmokeFixture(', runStart);
const contractMarker = source.indexOf('relation_contract_verified', callStart);
assert.ok(callStart >= 0 && contractMarker > callStart);

console.log(
  `[PASS] Stage60C runtime ADRG relation fixture: ${fixture.adrg} | ${fixture.codes.join(',')}`,
);
