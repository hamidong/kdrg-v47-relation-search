
'use strict';
const path = require('node:path');
const { KdrgSearchService } = require(path.join("/home/runner/workspace", 'electron', 'src', 'kdrg-search-service.js'));
const service = new KdrgSearchService(path.join("/home/runner/workspace", 'data', 'kdrg_v47_search_integrated_v3.json'));

function compact(response) {
  return {
    total_count: response?.total_count ?? null,
    type_counts: response?.type_counts ?? null,
    results: (response?.results ?? []).map((row) => ({
      entity_type: row.entity_type,
      entity_id: row.entity_id,
      title: row.title,
      match_type: row.match_type,
      matched_fields: row.matched_fields,
      summary: row.summary,
    })),
  };
}

function exactState(id, response) {
  const rows = response?.results ?? [];
  const wanted = new Set([`CODE:${id}`, `ADRG:${id}`]);
  const actual = new Set(rows.map((row) => `${row.entity_type}:${row.entity_id}`));
  return {
    id,
    has_code_record: service.recordMaps.CODE.has(id),
    has_adrg_record: service.recordMaps.ADRG.has(id),
    exact_code_present: actual.has(`CODE:${id}`),
    exact_adrg_present: actual.has(`ADRG:${id}`),
    extra_results: rows.filter((row) => !wanted.has(`${row.entity_type}:${row.entity_id}`))
      .map((row) => `${row.entity_type}:${row.entity_id}`),
    actual: [...actual],
  };
}

(async () => {
  const report = {
    public_map_counts: {
      CODE: service.recordMaps.CODE.size,
      ADRG: service.recordMaps.ADRG.size,
    },
    f022: {},
    shared_id_audit: {},
    detail_contract: {},
    search_method_source: String(service.search),
  };

  for (const type of ['ALL', 'CODE', 'ADRG']) {
    report.f022[type] = compact(await Promise.resolve(service.search('F022', type, { limit: 500, offset: 0 })));
  }
  report.f022.state = exactState('F022', report.f022.ALL);

  const shared = [...service.recordMaps.CODE.keys()].filter((id) => service.recordMaps.ADRG.has(id)).sort();
  const misses = [];
  const polluted = [];
  const samples = [];

  for (const id of shared) {
    const response = await Promise.resolve(service.search(id, 'ALL', { limit: 500, offset: 0 }));
    const state = exactState(id, response);
    if (!state.exact_code_present || !state.exact_adrg_present) misses.push(state);
    if (state.extra_results.length) polluted.push(state);
    if (samples.length < 30) samples.push(state);
  }

  report.shared_id_audit = {
    shared_id_count: shared.length,
    shared_ids: shared,
    exact_pair_missing_count: misses.length,
    exact_pair_missing: misses,
    exact_query_pollution_count: polluted.length,
    exact_query_pollution: polluted,
    samples,
  };

  for (const id of ['F111', 'F122', 'F022', 'P651', 'F212']) {
    const payload = await Promise.resolve(service.getDetail('ADRG', id));
    const d = payload?.detail ?? {};
    report.detail_contract[id] = {
      exists: Boolean(payload?.detail),
      has_condition_ast: Boolean(d.condition_ast),
      condition_ast_id: d.condition_ast_id ?? null,
      user_condition_status: d.user_condition_status ?? null,
      user_condition_text: d.user_condition_text ?? null,
      user_condition_source: d.user_condition_source ?? null,
      user_condition_page: d.user_condition_page ?? null,
      user_condition_tables_count: Array.isArray(d.user_condition_tables) ? d.user_condition_tables.length : null,
    };
  }

  process.stdout.write(JSON.stringify(report));
})().catch((error) => {
  console.error(error && error.stack ? error.stack : String(error));
  process.exitCode = 1;
});
