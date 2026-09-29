#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage68C R4 — KDRG 0.5.16 Service-Native Full Classification Shadow Audit

핵심 원칙
- 운영 JSON / 제품 JS / CSS / validator를 수정하지 않는다.
- 현재 Electron 검증기와 동일하게 KdrgSearchService + resolveDataFiles를 사용한다.
- ADRG/AADRG 수는 raw JSON 재귀탐색이 아니라 service.status()/recordMaps에서 읽는다.
- relationSearch는 실제 서비스 시그니처:
    service.relationSearch(conditionsArray, operator, options)
  로 호출한다.
- 실제 재현 fixture:
    i214 + m6569 / AUTO + AUTO / AND
- 1,132 ADRG direct/detail 분류와 derived AADRG를 전수검사한다.
- relation 생성이 가능한 ADRG는 실제 candidate projection까지 비교한다.
"""

from __future__ import annotations
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
REPORT_DIR = ROOT / "reports" / "stage68c_0516_service_native_full_shadow_r4"
REPORT_JSON = REPORT_DIR / "audit.json"
REPORT_TXT = REPORT_DIR / "audit_summary.txt"
NODE_PROBE = REPORT_DIR / "_service_native_probe.js"
NODE_OUT = REPORT_DIR / "_service_native_probe_output.json"

DATA = ROOT / "data" / "kdrg_v47_search_integrated_v3.json"
SERVICE = ROOT / "electron" / "src" / "kdrg-search-service.js"
CONTRACT = ROOT / "electron" / "src" / "search-result-contract.js"
DATAPATHS = ROOT / "electron" / "src" / "data-paths.js"
APP = ROOT / "electron" / "renderer" / "app.js"
CSS = ROOT / "electron" / "renderer" / "styles.css"
FORMATTERS = ROOT / "electron" / "renderer" / "ui-formatters.js"

EXPECTED_SHA = "1a3d50400567ecaad9695b7be8e7c0382131f8652f398e010cf01f4d8dda6c58"
EXPECTED_ADRG = 1132
EXPECTED_AADRG = 1233
EXPECTED_PUBLIC_TYPES = ["CODE", "ADRG"]

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def write_node_probe():
    js = r"""
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
"""
    NODE_PROBE.write_text(js, encoding="utf-8")

def main() -> int:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    required = [DATA, SERVICE, CONTRACT, DATAPATHS, APP, CSS, FORMATTERS]
    missing = [str(p.relative_to(ROOT)) for p in required if not p.exists()]
    if missing:
        REPORT_TXT.write_text(
            "[FAIL] 필수 파일 누락\n" + "\n".join(missing) + "\n",
            encoding="utf-8",
        )
        print(f"[FAIL] Stage68C R4 required_missing={len(missing)}")
        print(f"report={REPORT_TXT.relative_to(ROOT)}")
        return 1

    data_sha = sha256(DATA)
    sha_ok = data_sha == EXPECTED_SHA

    write_node_probe()
    proc = subprocess.run(
        ["node", str(NODE_PROBE.relative_to(ROOT))],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=240,
    )

    if proc.returncode != 0 or not NODE_OUT.exists():
        log = ((proc.stdout or "") + "\n" + (proc.stderr or ""))[-5000:]
        REPORT_TXT.write_text(
            "[FAIL] service-native probe 실행 실패\n" + log + "\n",
            encoding="utf-8",
        )
        print("[FAIL] Stage68C R4 node probe")
        print(f"report={REPORT_TXT.relative_to(ROOT)}")
        return 1

    try:
        runtime = json.loads(NODE_OUT.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[FAIL] probe JSON parse: {exc}")
        return 1

    counts = runtime.get("status", {}).get("counts", {})
    full = runtime.get("full_audit", {})
    ui = runtime.get("ui_contract", {})
    f111 = runtime.get("f111", {})
    actual = runtime.get("actual_fixture", {})
    public_types = runtime.get("status", {}).get("public_search_entity_types", [])
    anomaly_counts = full.get("anomaly_counts", {})

    count_ok = (
        counts.get("adrg_records") == EXPECTED_ADRG
        and counts.get("aadrg_records") == EXPECTED_AADRG
        and full.get("adrg_record_map_size") == EXPECTED_ADRG
        and full.get("aadrg_record_map_size") == EXPECTED_AADRG
    )
    public_ok = public_types == EXPECTED_PUBLIC_TYPES
    fixture_ok = all(actual.get("candidates", {}).get(x) is not None for x in ["F111","F112","F121","F122"])
    derived_data_ok = (
        anomaly_counts.get("derived_missing_entity_id", 0) == 0
        and anomaly_counts.get("derived_missing_title", 0) == 0
        and anomaly_counts.get("derived_missing_code", 0) == 0
        and anomaly_counts.get("derived_missing_label", 0) == 0
    )
    direct_detail_ok = anomaly_counts.get("direct_detail_mismatch", 0) == 0

    audit_complete = (
        sha_ok
        and runtime.get("ok") is True
        and count_ok
        and full.get("adrg_scanned") == EXPECTED_ADRG
        and public_ok
    )

    final = {
        "stage": "68C_R4",
        "shadow": True,
        "product_files_modified": False,
        "audit_complete": audit_complete,
        "operating_json": {
            "path": str(DATA.relative_to(ROOT)),
            "sha256": data_sha,
            "expected": EXPECTED_SHA,
            "match": sha_ok,
        },
        "contract_checks": {
            "service_counts_ok": count_ok,
            "public_search_types_ok": public_ok,
            "actual_fixture_contains_F111_F112_F121_F122": fixture_ok,
            "direct_detail_classification_consistent": direct_detail_ok,
            "derived_aadrg_data_complete": derived_data_ok,
        },
        "runtime": runtime,
    }
    REPORT_JSON.write_text(
        json.dumps(final, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    lines = [
        "Stage68C R4 — KDRG 0.5.16 Service-Native Shadow Audit",
        "=" * 68,
        f"audit_complete={'PASS' if audit_complete else 'FAIL'}",
        f"operating_json_sha256={'PASS' if sha_ok else 'FAIL'}",
        f"service_ready={runtime.get('status',{}).get('ready')}",
        f"ADRG={counts.get('adrg_records')} / expected={EXPECTED_ADRG}",
        f"AADRG={counts.get('aadrg_records')} / expected={EXPECTED_AADRG}",
        f"recordMaps.ADRG={full.get('adrg_record_map_size')}",
        f"recordMaps.AADRG={full.get('aadrg_record_map_size')}",
        f"public_search_types={public_types}",
        "",
        "[actual fixture i214 + m6569 / AND]",
        f"total_count={actual.get('total_count')}",
        f"F111/F112/F121/F122_present={fixture_ok}",
        f"F111_direct_labels={f111.get('direct_labels')}",
        f"F111_detail_labels={f111.get('detail_labels')}",
        f"F111_relation_labels={f111.get('relation_labels')}",
        f"ROOT_CAUSE={runtime.get('root_cause')}",
        "",
        "[full ADRG audit]",
        f"adrg_scanned={full.get('adrg_scanned')}",
        f"derived_aadrg_total={full.get('derived_aadrg_total')}",
        f"relation_eligible={full.get('relation_eligible')}",
        f"relation_candidate_found={full.get('relation_candidate_found')}",
        f"relation_compared_with_classification={full.get('relation_compared_with_classification')}",
    ]
    for key, value in anomaly_counts.items():
        lines.append(f"{key}={value}")

    lines += [
        "",
        "[renderer current source]",
        f"relation_reads_candidate_summary_abc={ui.get('relation_reads_candidate_summary_abc')}",
        f"render_derived_function_exists={ui.get('render_derived_function_exists')}",
        f"derived_reads_classification_code={ui.get('derived_reads_classification_code')}",
        f"derived_reads_classification_label={ui.get('derived_reads_classification_label')}",
        f"adrg_detail_has_derived_header={ui.get('adrg_detail_has_derived_header')}",
        f"adrg_detail_calls_derived_exact={ui.get('adrg_detail_calls_derived_exact')}",
        f"derived_default_closed={ui.get('derived_default_closed')}",
        f"relation_has_derived_header={ui.get('relation_has_derived_header')}",
        "",
        "제품/운영 JSON 수정 없음.",
        "이 보고서의 ROOT_CAUSE와 anomaly_counts를 기준으로 68D Actual 범위를 결정한다.",
    ]
    REPORT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"[{'PASS' if audit_complete else 'FAIL'}] Stage68C R4 service-native shadow audit")
    print(f"ADRG={counts.get('adrg_records')} AADRG={counts.get('aadrg_records')} scanned={full.get('adrg_scanned')}")
    print(f"public_search_types={public_types}")
    print(f"fixture_total={actual.get('total_count')} F111_F112_F121_F122={fixture_ok}")
    print(f"F111_direct={f111.get('direct_labels')}")
    print(f"F111_detail={f111.get('detail_labels')}")
    print(f"F111_relation={f111.get('relation_labels')}")
    print(f"ROOT_CAUSE={runtime.get('root_cause')}")
    print(
        "relation_audit="
        f"{full.get('relation_candidate_found')}/{full.get('relation_eligible')} "
        f"missing_labels={anomaly_counts.get('relation_missing_labels')} "
        f"mismatch={anomaly_counts.get('relation_direct_mismatch')}"
    )
    print(
        "derived_aadrg="
        f"{full.get('derived_aadrg_total')} "
        f"missing_code={anomaly_counts.get('derived_missing_code')} "
        f"missing_label={anomaly_counts.get('derived_missing_label')}"
    )
    print(
        "ui="
        f"adrg_section={ui.get('adrg_detail_has_derived_header')} "
        f"adrg_call={ui.get('adrg_detail_calls_derived_exact')} "
        f"derived_classification="
        f"{ui.get('derived_reads_classification_code') and ui.get('derived_reads_classification_label')}"
    )
    print(f"report={REPORT_TXT.relative_to(ROOT)}")
    print(f"json={REPORT_JSON.relative_to(ROOT)}")

    return 0 if audit_complete else 1

if __name__ == "__main__":
    sys.exit(main())
