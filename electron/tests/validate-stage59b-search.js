'use strict';
const assert = require('node:assert/strict');
const path = require('node:path');
const { KdrgSearchService } = require('../src/kdrg-search-service');
const { SEARCH_ENTITY_TYPES } = require('../src/search-result-contract');
const service = new KdrgSearchService(path.resolve(__dirname, '..', '..', 'data', 'kdrg_v47_search_integrated_v3.json'));
let pass = 0; const fail = [];
function check(name, fn) { try { fn(); pass += 1; } catch (e) { fail.push(`${name}: ${e.message}`); } }
check('public types', () => assert.deepEqual(SEARCH_ENTITY_TYPES, ['CODE','AADRG']));
for (const code of ['T601','ADC3A']) check(`exact ${code}`, () => {
  const row = service.recordMaps.CODE.get(code); assert.ok(row);
  const res = service.search(code, 'ALL', {limit:500});
  const expected = new Set([`CODE:${code}`, ...(row.related_aadrgs||[]).map(x=>`AADRG:${x}`)]);
  const actual = new Set(res.results.map(x=>`${x.entity_type}:${x.entity_id}`));
  assert.equal(actual.size, expected.size); for (const x of expected) assert.ok(actual.has(x), x);
});
check('AADRG condition inheritance', () => { const d=service.getDetail('AADRG','P6510').detail; assert.equal(d.adrg,'P651'); assert.ok(d.parent_adrg_detail); assert.ok('condition_ast' in d); assert.ok(Array.isArray(d.user_condition_tables)); });
check('MDC master', () => { const s=service.status(); const codes=s.mdc_master.items.map(x=>x.code); for(const c of ['PRE','18-1','18-2','21-1','21-2']) assert.ok(codes.includes(c),c); assert.ok(!codes.includes('24')); assert.ok(!codes.includes('25')); });
check('M6536 namespace', () => { const r=service.recordMaps.CODE.get('M6536'); assert.ok(r.names.includes('결절성 힘줄병, 아래다리')); assert.ok(r.names.includes('클립을 사용한 경피적 경도관 승모판 재건술')); assert.ok(r.namespace_meanings?.diagnosis && r.namespace_meanings?.procedure); });
check('dual role 60', () => assert.equal([...service.recordMaps.CODE.values()].filter(r=>r.namespace_meanings?.diagnosis&&r.namespace_meanings?.procedure).length,60));
for (const [tid,code] of [['LT_B780_001','B79'],['LT_D610_001','D62'],['LT_D760_001','D77'],['LT_F680_001','F69'],['LT_J600_001','J61']]) check(`boundary ${tid}`,()=>assert.ok(!(service.recordMaps.TABLE.get(tid)?.codes||[]).includes(code)));
check('M6536 F022/P020',()=>{ for(const tid of ['LT_PATCH_F022_PROCEDURE_TABLE06','LT_P020_001']) assert.ok((service.recordMaps.TABLE.get(tid)?.codes||[]).includes('M6536'),tid); });
for (const [adrg,count] of Object.entries({'9630':3376,'E013':427,'G504':610,'G524':610,'G534':610,'J031':738,'J032':738,'R020':161,'R040':161})) check(`MDC virtual ${adrg}`,()=>assert.equal(service.recordMaps.ADRG.get(adrg)?.mdc_virtual_principal_diagnosis?.code_count,count));
for (const adrg of ['B024','B092','H612','L632','O024','O062','S630']) check(`MDC HOLD ${adrg}`,()=>assert.equal(service.recordMaps.ADRG.get(adrg)?.mdc_virtual_review_status,'HOLD'));
console.log(`stage59_search: ${pass} PASS / ${fail.length} FAIL`); if(fail.length){fail.forEach(x=>console.log('- '+x));process.exitCode=1;}
