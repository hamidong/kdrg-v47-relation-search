
'use strict';

const fs = require('node:fs');
const path = require('node:path');

const ROOT = process.cwd();
const ELECTRON_ROOT = path.join(ROOT, 'electron');
const OUT = path.join(
  ROOT,
  'reports',
  'stage68c_0516_service_native_full_shadow_r4',
  '_service_native_probe_output.json'
);

const { resolveDataFiles } = require(path.join(ELECTRON_ROOT, 'src', 'data-paths'));
const {
  KdrgSearchService,
  normalizeEntityId,
} = require(path.join(ELECTRON_ROOT, 'src', 'kdrg-search-service'));
const {
  SEARCH_ENTITY_TYPES,
} = require(path.join(ELECTRON_ROOT, 'src', 'search-result-contract'));

const dataFiles = resolveDataFiles({
  isPackaged: false,
  resourcesPath: null,
  moduleDirectory: path.join(ELECTRON_ROOT, 'src'),
});
const service = new KdrgSearchService(dataFiles.integrated);
const status = service.status();

function arr(v) {
  if (Array.isArray(v)) return v;
  if (v === undefined || v === null || v === '') return [];
  return [v];
}

function normList(v) {
  return [...new Set(arr(v).map((x) => String(x).trim()).filter(Boolean))];
}

function sameSet(a, b) {
  const aa = [...normList(a)].sort();
  const bb = [...normList(b)].sort();
  return JSON.stringify(aa) === JSON.stringify(bb);
}

function directLabels(row) {
  return normList(row?.summary?.abc_display_labels);
}

function detailLabels(payload) {
  return normList(payload?.detail?.abc_display_labels);
}

function relationLabels(candidate) {
  return normList(candidate?.summary?.abc_display_labels);
}

function codesForTables(tableIds) {
  const output = [];
  const seen = new Set();
  for (const tableId of tableIds ?? []) {
    const table = service.recordMaps.TABLE.get(String(tableId));
    for (const code of table?.codes ?? []) {
      const normalized = normalizeEntityId(code, 'CODE');
      if (!normalized || seen.has(normalized)) continue;
      seen.add(normalized);
      output.push(String(code));
    }
  }
  return output;
}

function chooseRelationFixture(adrg) {
  const groups = service.conditionGroupsByAdrg.get(adrg) ?? [];

  // 1순위: 같은 include group 안에서 서로 다른 코드 2개 -> AND strict 후보
  for (const group of groups) {
    const codes = codesForTables(group.include_table_ids);
    for (let i = 0; i < codes.length; i += 1) {
      for (let j = i + 1; j < codes.length; j += 1) {
        if (normalizeEntityId(codes[i], 'CODE') !== normalizeEntityId(codes[j], 'CODE')) {
          return { codes: [codes[i], codes[j]], operator: 'AND', source: 'SAME_GROUP' };
        }
      }
    }
  }

  // 2순위: ADRG 전체 include table에서 서로 다른 코드 2개 -> OR로 candidate projection 확인
  const allCodes = [];
  const seen = new Set();
  for (const group of groups) {
    for (const code of codesForTables(group.include_table_ids)) {
      const normalized = normalizeEntityId(code, 'CODE');
      if (!normalized || seen.has(normalized)) continue;
      seen.add(normalized);
      allCodes.push(code);
    }
  }
  if (allCodes.length >= 2) {
    return { codes: allCodes.slice(0, 2), operator: 'OR', source: 'CROSS_GROUP' };
  }
  return null;
}

function relationCall(codes, operator, options = {}) {
  return service.relationSearch(
    codes.map((code) => ({ code, codeType: 'AUTO' })),
    operator,
    options,
  );
}

const appText = fs.readFileSync(path.join(ELECTRON_ROOT, 'renderer', 'app.js'), 'utf8');

const uiContract = {
  relation_reads_candidate_summary_abc:
    appText.includes("candidate.summary?.abc_display_labels") ||
    appText.includes("candidate.summary.abc_display_labels"),
  render_derived_function_exists:
    appText.includes("function renderDerivedAadrgList("),
  derived_reads_classification_code:
    appText.includes("summary.classification_code"),
  derived_reads_classification_label:
    appText.includes("summary.classification_display_label"),
  adrg_detail_has_derived_header:
    appText.includes("makeSection('파생 AADRG'") ||
    appText.includes('makeSection("파생 AADRG"'),
  adrg_detail_calls_derived_exact:
    appText.includes("renderDerivedAadrgList(detail.aadrg_records)"),
  derived_default_closed:
    /makeSection\(\s*['"]파생 AADRG['"][\s\S]{0,500}?open\s*:\s*false/.test(appText),
  relation_has_derived_header:
    /function\s+renderRelationDetail[\s\S]*?makeSection\(\s*['"]파생 AADRG['"]/.test(appText),
};

const publicTypes = Array.from(SEARCH_ENTITY_TYPES ?? []);

const anomalies = {
  direct_missing: [],
  detail_missing: [],
  direct_detail_mismatch: [],
  derived_missing_entity_id: [],
  derived_missing_title: [],
  derived_missing_code: [],
  derived_missing_label: [],
  relation_candidate_not_found: [],
  relation_missing_labels: [],
  relation_direct_mismatch: [],
};

let derivedTotal = 0;
let relationEligible = 0;
let relationCandidateFound = 0;
let relationCompared = 0;

const allAdrgIds = [...service.recordMaps.ADRG.keys()].sort();

for (const adrg of allAdrgIds) {
  const search = service.search(adrg, 'ADRG', { limit: 50 });
  const direct = search.results.find(
    (row) => row.entity_type === 'ADRG' && row.entity_id === adrg
  );
  const detail = service.getDetail('ADRG', adrg);

  const dl = directLabels(direct);
  const tl = detailLabels(detail);

  if (!direct) anomalies.direct_missing.push(adrg);
  if (!detail?.detail) anomalies.detail_missing.push(adrg);

  // 분류가 실제 존재하는 ADRG에 대해 direct/detail projection 일치 확인.
  if ((dl.length || tl.length) && !sameSet(dl, tl)) {
    anomalies.direct_detail_mismatch.push({
      adrg,
      direct: dl,
      detail: tl,
    });
  }

  const children = detail?.detail?.aadrg_records ?? [];
  for (const child of children) {
    derivedTotal += 1;
    if (!child?.entity_id) {
      anomalies.derived_missing_entity_id.push({ adrg });
      continue;
    }
    if (!child?.title) {
      anomalies.derived_missing_title.push({ adrg, aadrg: child.entity_id });
    }
    if (!String(child?.summary?.classification_code ?? '').trim()) {
      anomalies.derived_missing_code.push({ adrg, aadrg: child.entity_id });
    }
    if (!String(child?.summary?.classification_display_label ?? '').trim()) {
      anomalies.derived_missing_label.push({ adrg, aadrg: child.entity_id });
    }
  }

  const fixture = chooseRelationFixture(adrg);
  if (!fixture) continue;
  relationEligible += 1;

  let response;
  try {
    response = relationCall(fixture.codes, fixture.operator);
  } catch (error) {
    anomalies.relation_candidate_not_found.push({
      adrg,
      fixture,
      error: String(error?.message ?? error),
    });
    continue;
  }

  const candidate = response.results.find((row) => row.entity_id === adrg);
  if (!candidate) {
    anomalies.relation_candidate_not_found.push({ adrg, fixture });
    continue;
  }

  relationCandidateFound += 1;
  const rl = relationLabels(candidate);

  // direct/detail 둘 다 분류가 없는 ADRG는 projection 비교대상 아님.
  const expectedLabels = tl.length ? tl : dl;
  if (expectedLabels.length) {
    relationCompared += 1;
    if (!rl.length) {
      anomalies.relation_missing_labels.push({
        adrg,
        fixture,
        expected: expectedLabels,
      });
    } else if (!sameSet(rl, expectedLabels)) {
      anomalies.relation_direct_mismatch.push({
        adrg,
        fixture,
        direct: dl,
        detail: tl,
        relation: rl,
      });
    }
  }
}

// 사용자 실제 재현 fixture
const actualRequest = [
  { code: 'i214', codeType: 'AUTO' },
  { code: 'm6569', codeType: 'AUTO' },
];
let actualRelation = null;
let actualRelationError = null;
try {
  actualRelation = service.relationSearch(actualRequest, 'AND', {});
} catch (error) {
  actualRelationError = String(error?.stack ?? error?.message ?? error);
}

const fixtureIds = ['F111', 'F112', 'F121', 'F122'];
const actualCandidates = {};
for (const id of fixtureIds) {
  const candidate = actualRelation?.results?.find((row) => row.entity_id === id) ?? null;
  actualCandidates[id] = candidate ? {
    entity_id: candidate.entity_id,
    title: candidate.title,
    summary: candidate.summary ?? null,
    relation_level: candidate.relation_level,
    matched_count: candidate.matched_count,
    total_count: candidate.total_count,
    aadrg_records: candidate.aadrg_records ?? [],
  } : null;
}

const f111Direct = service.search('F111', 'ADRG', { limit: 50 })
  .results.find((row) => row.entity_type === 'ADRG' && row.entity_id === 'F111') ?? null;
const f111Detail = service.getDetail('ADRG', 'F111');
const f111Relation = actualCandidates.F111;

let rootCause = 'UNRESOLVED';
if (actualRelationError) {
  rootCause = 'ACTUAL_FIXTURE_CALL_ERROR';
} else if (!f111Relation) {
  rootCause = 'ACTUAL_FIXTURE_F111_NOT_RETURNED';
} else {
  const direct = directLabels(f111Direct);
  const detail = detailLabels(f111Detail);
  const relation = relationLabels(f111Relation);
  if ((direct.length || detail.length) && !relation.length) {
    rootCause = 'RELATION_CANDIDATE_CLASSIFICATION_PROJECTION_MISSING';
  } else if (relation.length && uiContract.relation_reads_candidate_summary_abc) {
    rootCause = 'SERVICE_AND_RENDERER_CURRENT_SOURCE_OK_CHECK_DEPLOYED_BUILD_OR_OTHER_PATH';
  } else if (relation.length && !uiContract.relation_reads_candidate_summary_abc) {
    rootCause = 'RELATION_RENDERER_FIELD_MISMATCH';
  } else {
    rootCause = 'RELATION_CLASSIFICATION_REVIEW';
  }
}

const output = {
  ok: true,
  status: {
    ready: status.ready,
    counts: status.counts,
    public_search_entity_types: publicTypes,
  },
  ui_contract: uiContract,
  full_audit: {
    adrg_record_map_size: service.recordMaps.ADRG.size,
    aadrg_record_map_size: service.recordMaps.AADRG.size,
    adrg_scanned: allAdrgIds.length,
    derived_aadrg_total: derivedTotal,
    relation_eligible: relationEligible,
    relation_candidate_found: relationCandidateFound,
    relation_compared_with_classification: relationCompared,
    anomaly_counts: Object.fromEntries(
      Object.entries(anomalies).map(([key, value]) => [key, value.length])
    ),
    anomalies,
  },
  actual_fixture: {
    request: actualRequest,
    operator: 'AND',
    error: actualRelationError,
    total_count: actualRelation?.total_count ?? null,
    result_ids: (actualRelation?.results ?? []).map((row) => row.entity_id),
    candidates: actualCandidates,
  },
  f111: {
    direct: f111Direct ? {
      entity_id: f111Direct.entity_id,
      summary: f111Direct.summary ?? null,
    } : null,
    detail: f111Detail ? {
      entity_id: f111Detail.entity_id,
      abc_classification_codes: f111Detail.detail?.abc_classification_codes ?? [],
      abc_display_labels: f111Detail.detail?.abc_display_labels ?? [],
      aadrg_records: f111Detail.detail?.aadrg_records ?? [],
    } : null,
    relation: f111Relation,
    direct_labels: directLabels(f111Direct),
    detail_labels: detailLabels(f111Detail),
    relation_labels: relationLabels(f111Relation),
  },
  root_cause: rootCause,
};

fs.writeFileSync(OUT, JSON.stringify(output, null, 2), 'utf8');
