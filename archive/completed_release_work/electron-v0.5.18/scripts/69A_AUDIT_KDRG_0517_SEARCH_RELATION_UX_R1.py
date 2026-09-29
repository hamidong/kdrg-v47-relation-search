from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path.cwd()
REPORT_DIR = ROOT / "reports" / "stage69a_0517_user_feedback_audit_r1"
REPORT_JSON = REPORT_DIR / "audit.json"
REPORT_TXT = REPORT_DIR / "audit_summary.txt"

BASE_COMMIT = "d1c1b126fee9f7bd3e226d4cfcee77e863baec0c"
BASE_VERSION = "0.5.16"
NEXT_VERSION = "0.5.17"
RUNTIME_JSON_SHA256 = "1a3d50400567ecaad9695b7be8e7c0382131f8652f398e010cf01f4d8dda6c58"

APP = ROOT / "electron" / "renderer" / "app.js"
SERVICE = ROOT / "electron" / "src" / "kdrg-search-service.js"
PACKAGE = ROOT / "electron" / "package.json"
RUNTIME_JSON = ROOT / "data" / "kdrg_v47_search_integrated_v3.json"


class Stop(RuntimeError):
    pass


def run(cmd, cwd=ROOT, timeout=1200):
    p = subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    return p.returncode, p.stdout


def git(*args):
    rc, out = run(["git", *args], timeout=120)
    if rc != 0:
        raise Stop(f"git {' '.join(args)} 실패\n{out[-3000:]}")
    return out.strip()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def require(ok, message):
    if not ok:
        raise Stop(message)


def function_block(source: str, name: str) -> str:
    m = re.search(rf"\bfunction\s+{re.escape(name)}\s*\(", source)
    if not m:
        return ""
    start = m.start()
    brace = source.find("{", m.end())
    if brace < 0:
        return ""
    depth = 0
    quote = None
    escape = False
    i = brace
    while i < len(source):
        ch = source[i]
        if quote:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote:
                quote = None
        else:
            if ch in ("'", '"', "`"):
                quote = ch
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return source[start:i + 1]
        i += 1
    return source[start:]


def main():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    result = {
        "stage": "69A",
        "target_version": NEXT_VERSION,
        "status": "FAIL",
        "readiness": "NOT_READY",
    }

    try:
        require((ROOT / ".git").exists(), "현재 위치가 Git 저장소 루트가 아닙니다.")
        for path in (APP, SERVICE, PACKAGE, RUNTIME_JSON):
            require(path.is_file(), f"필수 파일 없음: {path.relative_to(ROOT)}")

        head = git("rev-parse", "HEAD")
        branch = git("branch", "--show-current")
        package = json.loads(PACKAGE.read_text(encoding="utf-8"))

        tracked = [x for x in git("diff", "--name-only", "HEAD").splitlines() if x.strip()]
        staged = [x for x in git("diff", "--cached", "--name-only").splitlines() if x.strip()]

        require(head == BASE_COMMIT, f"0.5.16 기준 커밋 불일치: {head}")
        require(branch == "main", f"branch 불일치: {branch}")
        require(package.get("version") == BASE_VERSION, f"package version 불일치: {package.get('version')}")
        require(not tracked, f"tracked 작업트리가 깨끗하지 않음: {tracked}")
        require(not staged, f"staging이 비어 있지 않음: {staged}")
        require(sha256(RUNTIME_JSON) == RUNTIME_JSON_SHA256, "운영 JSON SHA256 불일치")

        syntax = {}
        for name, path in (("app", APP), ("service", SERVICE)):
            rc, out = run(["node", "--check", str(path)], timeout=120)
            syntax[name] = {"rc": rc, "tail": out[-2000:]}
            require(rc == 0, f"{name} JS syntax FAIL\n{out[-2000:]}")

        root_js = json.dumps(str(ROOT))
        probe_js = f"""
'use strict';
const path = require('node:path');
const {{ KdrgSearchService }} = require(path.join({root_js}, 'electron', 'src', 'kdrg-search-service.js'));
const service = new KdrgSearchService(path.join({root_js}, 'data', 'kdrg_v47_search_integrated_v3.json'));

function compact(response) {{
  return {{
    total_count: response?.total_count ?? null,
    type_counts: response?.type_counts ?? null,
    results: (response?.results ?? []).map((row) => ({{
      entity_type: row.entity_type,
      entity_id: row.entity_id,
      title: row.title,
      match_type: row.match_type,
      matched_fields: row.matched_fields,
      summary: row.summary,
    }})),
  }};
}}

function exactState(id, response) {{
  const rows = response?.results ?? [];
  const wanted = new Set([`CODE:${{id}}`, `ADRG:${{id}}`]);
  const actual = new Set(rows.map((row) => `${{row.entity_type}}:${{row.entity_id}}`));
  return {{
    id,
    has_code_record: service.recordMaps.CODE.has(id),
    has_adrg_record: service.recordMaps.ADRG.has(id),
    exact_code_present: actual.has(`CODE:${{id}}`),
    exact_adrg_present: actual.has(`ADRG:${{id}}`),
    extra_results: rows.filter((row) => !wanted.has(`${{row.entity_type}}:${{row.entity_id}}`))
      .map((row) => `${{row.entity_type}}:${{row.entity_id}}`),
    actual: [...actual],
  }};
}}

(async () => {{
  const report = {{
    public_map_counts: {{
      CODE: service.recordMaps.CODE.size,
      ADRG: service.recordMaps.ADRG.size,
    }},
    f022: {{}},
    shared_id_audit: {{}},
    detail_contract: {{}},
    search_method_source: String(service.search),
  }};

  for (const type of ['ALL', 'CODE', 'ADRG']) {{
    report.f022[type] = compact(await Promise.resolve(service.search('F022', type, {{ limit: 500, offset: 0 }})));
  }}
  report.f022.state = exactState('F022', report.f022.ALL);

  const shared = [...service.recordMaps.CODE.keys()].filter((id) => service.recordMaps.ADRG.has(id)).sort();
  const misses = [];
  const polluted = [];
  const samples = [];

  for (const id of shared) {{
    const response = await Promise.resolve(service.search(id, 'ALL', {{ limit: 500, offset: 0 }}));
    const state = exactState(id, response);
    if (!state.exact_code_present || !state.exact_adrg_present) misses.push(state);
    if (state.extra_results.length) polluted.push(state);
    if (samples.length < 30) samples.push(state);
  }}

  report.shared_id_audit = {{
    shared_id_count: shared.length,
    shared_ids: shared,
    exact_pair_missing_count: misses.length,
    exact_pair_missing: misses,
    exact_query_pollution_count: polluted.length,
    exact_query_pollution: polluted,
    samples,
  }};

  for (const id of ['F111', 'F122', 'F022', 'P651', 'F212']) {{
    const payload = await Promise.resolve(service.getDetail('ADRG', id));
    const d = payload?.detail ?? {{}};
    report.detail_contract[id] = {{
      exists: Boolean(payload?.detail),
      has_condition_ast: Boolean(d.condition_ast),
      condition_ast_id: d.condition_ast_id ?? null,
      user_condition_status: d.user_condition_status ?? null,
      user_condition_text: d.user_condition_text ?? null,
      user_condition_source: d.user_condition_source ?? null,
      user_condition_page: d.user_condition_page ?? null,
      user_condition_tables_count: Array.isArray(d.user_condition_tables) ? d.user_condition_tables.length : null,
    }};
  }}

  process.stdout.write(JSON.stringify(report));
}})().catch((error) => {{
  console.error(error && error.stack ? error.stack : String(error));
  process.exitCode = 1;
}});
"""
        probe_path = REPORT_DIR / "stage69a_probe.js"
        probe_path.write_text(probe_js, encoding="utf-8")

        rc, out = run(["node", "--check", str(probe_path)], timeout=120)
        require(rc == 0, f"probe JS syntax FAIL\n{out[-3000:]}")

        rc, out = run(["node", str(probe_path)], timeout=1200)
        require(rc == 0, f"search probe FAIL\n{out[-5000:]}")
        probe = json.loads(out)

        app_source = APP.read_text(encoding="utf-8")
        relation_results = function_block(app_source, "renderRelationResults")
        relation_detail = function_block(app_source, "renderRelationDetail")
        adrg_detail = function_block(app_source, "renderAdrgDetail")

        ui = {
            "renderRelationResults_found": bool(relation_results),
            "renderRelationDetail_found": bool(relation_detail),
            "renderAdrgDetail_found": bool(adrg_detail),
            "relation_result_has_classification": (
                "abc_display_labels" in relation_results
                or "classification_display_label" in relation_results
                or "makeClassificationBadgeGroup" in relation_results
            ),
            "relation_detail_has_classification": "질병군 분류" in relation_detail,
            "relation_detail_has_full_condition_summary": "renderUserConditionSummary(" in relation_detail,
            "relation_detail_has_full_condition_tables": "renderUserConditionTables(" in relation_detail,
            "relation_detail_has_full_condition_evidence": "renderUserConditionEvidence(" in relation_detail,
            "adrg_detail_has_full_condition_summary": "renderUserConditionSummary(" in adrg_detail,
            "adrg_detail_has_full_condition_tables": "renderUserConditionTables(" in adrg_detail,
            "adrg_detail_has_full_condition_evidence": "renderUserConditionEvidence(" in adrg_detail,
            "getDetail_bridge_available": "window.KDRG.getDetail" in app_source,
        }

        f022_state = probe["f022"]["state"]
        issue1_reproduced = (
            f022_state["has_code_record"]
            and f022_state["has_adrg_record"]
            and (
                not f022_state["exact_code_present"]
                or not f022_state["exact_adrg_present"]
                or bool(f022_state["extra_results"])
            )
        )
        issue2_reproduced = not ui["relation_result_has_classification"]
        issue3_reproduced = not (
            ui["relation_detail_has_full_condition_summary"]
            and ui["relation_detail_has_full_condition_tables"]
            and ui["relation_detail_has_full_condition_evidence"]
        )

        result.update({
            "status": "PASS",
            "readiness": "READY_FOR_0517_GENERALIZED_FIX",
            "base": {
                "head": head,
                "branch": branch,
                "package_version": package.get("version"),
                "runtime_json_sha256": sha256(RUNTIME_JSON),
                "tracked_clean": not tracked,
                "staging_empty": not staged,
                "app_sha256": sha256(APP),
                "service_sha256": sha256(SERVICE),
            },
            "syntax": syntax,
            "issue_reproduction": {
                "1_exact_search": issue1_reproduced,
                "2_relation_result_classification": issue2_reproduced,
                "3_relation_full_condition_detail": issue3_reproduced,
            },
            "search_probe": probe,
            "ui_audit": ui,
            "planned_contract": {
                "exact_identifier_rule": (
                    "ALL 검색에서 입력값이 공개 entity의 정확한 ID와 일치하면 "
                    "CODE/ADRG의 정확한 ID 결과만 표시하고 관계·부분일치 확장 결과는 제외"
                ),
                "dedupe_key_rule": "동일 문자열 ID라도 entity_type:entity_id 단위로 독립 보존",
                "relation_result_rule": "관계검색 결과 카드에 질병군 분류 badge를 함께 표시",
                "relation_detail_rule": (
                    "관계검색 상세에서 ADRG 전체상세와 동일한 분류 조건·조건 상세·원문 근거를 "
                    "공식 ADRG detail 데이터로 재사용"
                ),
            },
        })

        REPORT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        shared = probe["shared_id_audit"]
        lines = [
            "[PASS] Stage69A / 0.5.17 사용자 피드백 전수감사",
            f"base_commit={head}",
            f"F022_ALL={','.join(f022_state['actual'])}",
            f"F022_extra={','.join(f022_state['extra_results']) or 'NONE'}",
            f"shared_CODE_ADRG_ids={shared['shared_id_count']}",
            f"shared_exact_pair_missing={shared['exact_pair_missing_count']}",
            f"shared_exact_query_pollution={shared['exact_query_pollution_count']}",
            f"relation_result_classification={'PRESENT' if ui['relation_result_has_classification'] else 'MISSING'}",
            "relation_detail_full_conditions=" + ("PRESENT" if not issue3_reproduced else "MISSING"),
            "runtime_json=UNCHANGED",
            "tracked_files=UNCHANGED",
            "readiness=READY_FOR_0517_GENERALIZED_FIX",
            f"report={REPORT_TXT.relative_to(ROOT)}",
            f"json={REPORT_JSON.relative_to(ROOT)}",
        ]
        REPORT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("\n".join(lines))
        return 0

    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        REPORT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        REPORT_TXT.write_text(
            "[FAIL] Stage69A / 0.5.17 사용자 피드백 전수감사\n" + result["error"] + "\n",
            encoding="utf-8",
        )
        print("[FAIL] Stage69A")
        print(str(exc))
        print(f"report={REPORT_TXT.relative_to(ROOT)}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
