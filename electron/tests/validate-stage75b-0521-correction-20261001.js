'use strict';

const path = require('node:path');
const assert = require('node:assert/strict');
const { KdrgSearchService } = require(path.resolve(__dirname, '..', 'src', 'kdrg-search-service.js'));

const runtime = path.resolve(__dirname, '..', '..', 'data', 'kdrg_v47_search_integrated_v3.json');
const service = new KdrgSearchService(runtime);

function detail(type,id) {
  return service.getDetail(type,id)?.detail || null;
}
function sorted(xs) {
  return [...new Set((xs || []).map(String))].sort();
}

const expected = {"E0732": {"name": "심도자에 의한 순환기능검사-운동부하 우심도자술(선천성 심장병)", "table_ids": ["LT_F023_002", "LT_F044_003", "LT_F103_001", "LT_F172_002", "LT_F502_001"], "adrgs": ["F021", "F022", "F023", "F041", "F043", "F044", "F103", "F172", "F502"], "official_adrgs": ["F021", "F022", "F023", "F041", "F043", "F103", "F172", "F502"]}, "E0733": {"name": "심도자에 의한 순환기능검사-운동부하 우심도자술(기타)", "table_ids": ["LT_F023_002", "LT_F044_003", "LT_F103_001", "LT_F172_002", "LT_F502_001"], "adrgs": ["F021", "F022", "F023", "F041", "F043", "F044", "F103", "F172", "F502"], "official_adrgs": ["F021", "F022", "F023", "F041", "F043", "F103", "F172", "F502"]}, "M6912": {"name": "경피적 고주파열치료술 [유도료 별도 산정]-두경부 미세낭 림프관기형 또는 미세낭 정맥림프관기형", "table_ids": ["LT_D150_001"], "adrgs": ["D150"], "official_adrgs": ["D150"]}};
const d051MemberCodes = ["O0965", "O1050", "O1055", "O1070", "O1091", "O1092", "O1093", "O1100", "O1110", "O1120", "U1150"];
const d051Aadrgs = ["D0510"];

assert.equal(service.recordMaps.ADRG.has('E043'), false, 'E043 must not be reconstructed');
assert.equal(service.recordMaps.ADRG.has('E034'), true, 'resolved E034 missing');

const d051 = detail('ADRG','D051');
assert.ok(d051, 'D051 detail missing');
assert.ok(sorted(d051.source_logical_table_ids).includes("LT_D054_001"), 'D051 source table link missing');

const d051Table = detail('TABLE',"LT_D054_001");
assert.ok(d051Table, 'D051 table detail missing');
assert.ok(sorted(d051Table.related_adrgs).includes('D051'), 'D051 table related_adrgs missing D051');
const d051TableCodes = sorted([
  ...(d051Table.codes || []),
  ...(d051Table.code_records || []).map(x => x?.entity_id ?? x?.code ?? x?.code_id).filter(Boolean),
]);
assert.deepEqual(
  d051TableCodes,
  sorted(d051MemberCodes),
  'D051 table member-code set changed'
);

for (const code of d051MemberCodes) {
  const d = detail('CODE', code);
  assert.ok(d, `D051 table member CODE missing ${code}`);
  assert.ok(sorted(d.logical_table_ids).includes("LT_D054_001"), `D051 table membership missing ${code}`);
  assert.ok(sorted(d.related_adrgs).includes('D051'), `D051 related_adrgs missing on CODE ${code}`);
  for (const aadrg of d051Aadrgs) {
    assert.ok(sorted(d.related_aadrgs).includes(aadrg), `D051 related_aadrgs missing ${aadrg} on CODE ${code}`);
  }
  const expectedAadrgs = [];
  for (const adrg of sorted(d.related_adrgs)) {
    const adrgRow = service.recordMaps.ADRG.get(adrg);
    assert.ok(adrgRow, `runtime ADRG row missing ${adrg} for CODE ${code}`);
    expectedAadrgs.push(...(adrgRow.aadrg_codes || []).map(String));
  }
  assert.deepEqual(
    sorted(d.related_aadrgs),
    sorted(expectedAadrgs),
    `related_adrgs -> related_aadrgs closure mismatch for CODE ${code}`,
  );
}

for (const [code, spec] of Object.entries(expected)) {
  assert.ok(service.recordMaps.CODE.has(code), `${code} CODE record missing`);
  const d = detail('CODE', code);
  assert.ok(d, `${code} detail missing`);
  assert.deepEqual(sorted(d.logical_table_ids), sorted(spec.table_ids), `${code} table relation mismatch`);
  assert.deepEqual(sorted(d.related_adrgs), sorted(spec.adrgs), `${code} runtime ADRG closure mismatch`);
  assert.ok((d.names || []).some(n => String(n).includes(spec.name)), `${code} official name missing`);

  const r = service.search(code, 'ALL', {limit:200});
  assert.ok(r.results.some(x => x.entity_type === 'CODE' && String(x.entity_id) === code), `${code} exact CODE search missing`);

  for (const tid of spec.table_ids) {
    const table = detail('TABLE', tid);
    assert.ok(table, `${code} target TABLE ${tid} missing`);
    assert.ok((table.code_records || []).some(x => String(x.entity_id) === code), `${code} not in ${tid}`);
  }
}

const f022 = detail('ADRG','F022');
assert.ok(f022, 'F022 detail missing');
const f022Text = JSON.stringify({
  condition_ast:f022.condition_ast,
  condition_text:f022.condition_text,
  condition_display:f022.condition_display,
}).toLowerCase();
for (const token of ['table2','table3','table6']) assert.ok(f022Text.includes(token), `F022 condition token missing ${token}`);
assert.ok(f022Text.includes('and') && f022Text.includes('or'), 'F022 AND/OR semantics missing');

const e034 = detail('ADRG','E034');
assert.ok(e034, 'E034 detail missing');
for (const tid of (e034.source_logical_table_ids || [])) {
  const table = detail('TABLE', tid);
  if (!table) continue;
  assert.equal((table.code_records || []).some(x => String(x.entity_id) === 'M6615'), false, `E034 correction M6615 still present in ${tid}`);
}

console.log('[PASS] Stage75B R3 0.5.21 correction validator', JSON.stringify({
  newCodes:Object.keys(expected).length,
  d051Table:"LT_D054_001",
  d051MemberCodes:d051MemberCodes.length,
  e043:'NOOP_RESOLVED_TO_E034',
}));
