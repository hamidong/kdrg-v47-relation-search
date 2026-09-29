from __future__ import annotations

import json
import hashlib
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent

BASE_COMMIT = "08b51f4fa487a3ae05c1e279aa1c533f9f3aed52"
BASE_VERSION = "0.5.17"
NEXT_VERSION = "0.5.18"
RUNTIME_REL = Path("data/kdrg_v47_search_integrated_v3.json")
RUNTIME_SHA = "1a3d50400567ecaad9695b7be8e7c0382131f8652f398e010cf01f4d8dda6c58"

APP = ROOT / "electron/renderer/app.js"
INDEX = ROOT / "electron/renderer/index.html"
STYLES = ROOT / "electron/renderer/styles.css"
SERVICE = ROOT / "electron/src/kdrg-search-service.js"
PACKAGE = ROOT / "electron/package.json"

REPORT_DIR = ROOT / "reports/stage70a_0518_phase1_ui_completion_audit_r3"
REPORT_TXT = REPORT_DIR / "audit_summary.txt"
REPORT_JSON = REPORT_DIR / "audit.json"


class AuditStop(RuntimeError):
    pass


def require(ok: bool, message: str) -> None:
    if not ok:
        raise AuditStop(message)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def run(cmd, cwd=ROOT, timeout=1200):
    p = subprocess.run(
        [str(x) for x in cmd],
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    return p.returncode, p.stdout


def git_text(*args: str) -> str:
    rc, out = run(["git", *args], timeout=120)
    require(rc == 0, f"git {' '.join(args)} 실패\n{out[-2500:]}")
    return out.strip()


def function_span(source: str, name: str) -> tuple[int, int]:
    marker = f"function {name}"
    start = source.find(marker)
    require(start >= 0, f"function 없음: {name}")

    brace = source.find("{", start)
    require(brace >= 0, f"function 여는 괄호 없음: {name}")

    depth = 0
    quote = None
    escape = False
    line_comment = False
    block_comment = False
    i = brace

    while i < len(source):
        ch = source[i]
        nxt = source[i + 1] if i + 1 < len(source) else ""

        if line_comment:
            if ch == "\n":
                line_comment = False
            i += 1
            continue

        if block_comment:
            if ch == "*" and nxt == "/":
                block_comment = False
                i += 2
                continue
            i += 1
            continue

        if quote:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote:
                quote = None
            i += 1
            continue

        if ch == "/" and nxt == "/":
            line_comment = True
            i += 2
            continue

        if ch == "/" and nxt == "*":
            block_comment = True
            i += 2
            continue

        if ch in ("'", '"', "`"):
            quote = ch
            i += 1
            continue

        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return start, i + 1

        i += 1

    raise AuditStop(f"function 닫는 괄호 탐색 실패: {name}")


def block(source: str, name: str) -> str:
    s, e = function_span(source, name)
    return source[s:e]


def css_rule(source: str, selector_fragment: str) -> str:
    # Simple audit helper: gather rules whose selector contains fragment.
    pattern = re.compile(
        r"(?ms)([^{}]*" + re.escape(selector_fragment) + r"[^{}]*)\{([^{}]*)\}"
    )
    return "\n".join(
        f"{m.group(1).strip()}{{{m.group(2)}}}" for m in pattern.finditer(source)
    )


def add(checks, cid, title, ok, detail, *, gate=True, status_if_false="FAIL"):
    checks.append(
        {
            "id": cid,
            "title": title,
            "status": "PASS" if ok else status_if_false,
            "detail": detail,
            "gate": gate,
        }
    )


def main() -> int:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    checks = []

    try:
        # ------------------------------------------------------------
        # 0. Immutable 0.5.17 release baseline
        # ------------------------------------------------------------
        head = git_text("rev-parse", "HEAD")
        origin_main = git_text("rev-parse", "origin/main")
        branch = git_text("branch", "--show-current")
        tracked = [x for x in git_text("diff", "--name-only", "HEAD").splitlines() if x]
        staged = [x for x in git_text("diff", "--cached", "--name-only").splitlines() if x]

        require(head == BASE_COMMIT, f"HEAD 불일치: {head}")
        require(origin_main == BASE_COMMIT, f"origin/main 불일치: {origin_main}")
        require(branch == "main", f"branch 불일치: {branch}")
        require(not tracked, f"tracked worktree 변경 있음: {tracked}")
        require(not staged, f"staging 변경 있음: {staged}")
        require(sha256(ROOT / RUNTIME_REL) == RUNTIME_SHA, "운영 JSON SHA 불일치")

        package = json.loads(PACKAGE.read_text(encoding="utf-8"))
        require(
            package.get("version") == BASE_VERSION,
            f"package version 불일치: {package.get('version')}",
        )

        for path in (APP, INDEX, STYLES, SERVICE):
            require(path.is_file(), f"필수 제품파일 없음: {path.relative_to(ROOT)}")

        app = APP.read_text(encoding="utf-8")
        html = INDEX.read_text(encoding="utf-8")
        css = STYLES.read_text(encoding="utf-8")
        service = SERVICE.read_text(encoding="utf-8")

        render_results = block(app, "renderResults")
        render_relation = block(app, "renderRelationResults")
        render_adrg = block(app, "renderAdrgDetail")
        render_code = block(app, "renderCodeDetail")
        render_derived = block(app, "renderDerivedAadrgList")
        render_tables = block(app, "renderUserConditionTables")

        # ------------------------------------------------------------
        # A. Latest public product structure
        # ------------------------------------------------------------
        public_ok = (
            '<option value="CODE">코드</option>' in html
            and '<option value="ADRG">ADRG</option>' in html
            and '<option value="AADRG">' not in html
            and '<option value="TABLE">' not in html
            and '<option value="RDRG">' not in html
        )
        add(
            checks, "A01", "공개 검색유형 전체·코드·ADRG", public_ok,
            "AADRG/RDRG/TABLE은 독립 공개 검색유형으로 되돌리지 않음",
        )

        add(
            checks, "A02", "0.5.17 exact public-ID 계약 유지",
            "STAGE69B_EXACT_PUBLIC_ID_V2" in service,
            "CODE-only/ADRG-only/shared exact ID의 불필요 관계결과 차단",
        )

        # ------------------------------------------------------------
        # B. 일반 검색결과 ADRG 질병군 분류 — 이번 확정 누락
        # ------------------------------------------------------------
        general_adrg_branch = (
            re.search(
                r"entity_type[^;\n]*ADRG|ADRG[^;\n]*entity_type",
                render_results,
                re.I,
            ) is not None
        )
        general_has_abc = "abc_display_labels" in render_results
        general_has_badges = (
            "appendClassificationBadges" in render_results
            or "makeClassificationBadgeGroup" in render_results
        )
        general_class_ok = (
            general_adrg_branch and general_has_abc and general_has_badges
        )
        add(
            checks,
            "B01",
            "일반 ADRG 검색결과 카드 질병군 분류 표시",
            general_class_ok,
            (
                f"adrg_branch={general_adrg_branch}, "
                f"abc_display_labels={general_has_abc}, "
                f"badge_renderer={general_has_badges}"
            ),
        )

        # CODE result must not receive a single misleading A/B/C badge.
        code_classification_injection = (
            re.search(
                r"entity_type[^;\n]*CODE[\s\S]{0,450}"
                r"(abc_display_labels|appendClassificationBadges|makeClassificationBadgeGroup)",
                render_results,
                re.I,
            )
            is not None
        )
        add(
            checks,
            "B02",
            "CODE 검색결과에 단일 질병군 분류 오표시 없음",
            not code_classification_injection,
            "CODE는 여러 ADRG와 연결될 수 있어 A/B/C 단일 라벨을 강제로 붙이지 않음",
        )

        # ------------------------------------------------------------
        # C. 사용자 요청: 일반/복수검색 모두 분류 라벨을 우측 배치
        # ------------------------------------------------------------
        relation_class_ok = (
            "STAGE69B_RELATION_RESULT_CLASSIFICATION_TITLE_ROW" in render_relation
            and "abc_display_labels" in render_relation
            and "result-card-classification" in render_relation
        )
        add(
            checks,
            "C01",
            "복수코드 관계검색 카드 질병군 분류 존재",
            relation_class_ok,
            "0.5.17에서 추가한 A/B/C label 유지",
        )

        class_css = css_rule(css, "result-card-classification")
        right_alignment_tokens = (
            "margin-left" in class_css
            and "auto" in class_css
            and (
                "justify-content" in class_css
                or "text-align" in class_css
                or "margin-inline-start" in class_css
            )
        )
        add(
            checks,
            "C02",
            "검색결과 질병군 분류 라벨 우측 정렬 CSS",
            right_alignment_tokens,
            (
                "목표: 공통 result-card-classification을 우측 정렬. "
                f"current_rule={class_css[:900]!r}"
            ),
        )

        # Relation result should use the common classification class so the same
        # right-alignment rule can apply to normal ADRG and relation cards.
        common_class_ok = "result-card-classification" in render_relation
        add(
            checks,
            "C03",
            "일반검색·복수검색 공통 분류 라벨 class 사용 가능",
            common_class_ok,
            "70B에서는 두 경로 모두 동일한 우측 정렬 class로 통일",
        )

        # Relation chip + classification coexistence: keep relation-level chip
        # and place classification on the right without removing it.
        relation_level_preserved = "relation_level_label" in render_relation
        add(
            checks,
            "C04",
            "복수검색 관계단계 라벨 유지",
            relation_level_preserved,
            "우측 이동 시 '같은 조건 선택지' 등 관계 chip은 제거하지 않음",
        )

        # ------------------------------------------------------------
        # D. Relation detail + normal ADRG detail / derived AADRG
        # ------------------------------------------------------------
        relation_conditions_ok = (
            "loadRelationOfficialAdrgConditions" in app
            and "renderUserConditionSummary(detail)" in app
            and "renderUserConditionTables(detail)" in app
            and "STAGE69B_RELATION_OFFICIAL_CONDITIONS" in app
        )
        add(
            checks,
            "D01",
            "복수검색 상세 분류 조건·조건 상세",
            relation_conditions_ok,
            "canonical ADRG detail renderer 재사용 유지",
        )

        derived_section_ok = (
            "파생 AADRG" in render_adrg
            and "renderDerivedAadrgList" in render_adrg
        )
        add(
            checks,
            "D02",
            "ADRG 상세 파생 AADRG 섹션",
            derived_section_ok,
            "0.5.16에서 복원한 파생 AADRG 유지",
        )

        derived_class_ok = (
            (
                "appendClassificationBadges" in render_derived
                or "makeClassificationBadgeGroup" in render_derived
            )
            and (
                "abc_display_labels" in render_derived
                or "classification_code" in render_derived
                or "classification_display_label" in render_derived
            )
        )
        add(
            checks,
            "D03",
            "파생 AADRG 행별 질병군 분류",
            derived_class_ok,
            "display label 우선 + legacy fallback 유지",
        )

        pos_derived = render_adrg.find("파생 AADRG")
        pos_summary = render_adrg.find("renderUserConditionSummary")
        pos_tables = render_adrg.find("renderUserConditionTables")
        order_ok = (
            pos_derived >= 0
            and pos_summary >= 0
            and pos_tables >= 0
            and pos_derived < pos_summary < pos_tables
        )
        add(
            checks,
            "D04",
            "ADRG 상세 순서",
            order_ok,
            "파생 AADRG → 분류 조건 → 조건 상세",
        )

        normal_detail_class_ok = (
            "질병군 분류" in render_adrg
            or "abc_display_labels" in render_adrg
            or "makeClassificationBadgeGroup" in render_adrg
        )
        add(
            checks,
            "D05",
            "ADRG 상세 질병군 분류 표시",
            normal_detail_class_ok,
            "검색카드뿐 아니라 상세 분류도 유지",
        )

        # ------------------------------------------------------------
        # E. Previously requested UI cleanup: TABLE technical exposure
        # ------------------------------------------------------------
        result_table_leak = any(
            token in render_results
            for token in (
                "TABLE n개",
                "TABLE ${",
                "table_count",
                "table_ids",
                "연결 TABLE",
                "포함 TABLE",
            )
        )
        add(
            checks,
            "E01",
            "검색결과 TABLE 개수/기술 노출 제거",
            not result_table_leak,
            "검색카드는 사용자용 CODE/ADRG 정보만 표시",
        )

        code_table_leak = (
            "연결 TABLE" in render_code
            or "포함 TABLE" in render_code
        )
        add(
            checks,
            "E02",
            "CODE 상세 연결/포함 TABLE 상단 노출 제거",
            not code_table_leak,
            "TABLE 데이터 자체는 삭제하지 않고 조건 상세에서 필요 시 사용",
        )

        condition_sets_retained = (
            "renderUserConditionTables" in app
            and len(render_tables) > 100
        )
        add(
            checks,
            "E03",
            "분류조건 실제 코드집합 펼침 유지",
            condition_sets_retained,
            "table1/table2/table3 코드집합 개념은 사용자 검증용으로 유지",
        )

        technical_default_leak = (
            "physical_section_definition" in render_adrg
            or "AST family metadata" in render_adrg
        )
        add(
            checks,
            "E04",
            "ADRG 기본 UI 내부 기술 metadata 숨김",
            not technical_default_leak,
            "LT_* / parser / AST family metadata 기본노출 금지",
        )

        # ------------------------------------------------------------
        # F. Other phase-1 UX requirements
        # ------------------------------------------------------------
        mdc_helper_ok = "function mdcDisplayText" in app
        mdc_result_ok = "mdcDisplayText" in render_results
        mdc_detail_ok = "mdcDisplayText" in render_adrg
        add(
            checks,
            "F01",
            "MDC 번호+명칭 표시",
            mdc_helper_ok and mdc_result_ok and mdc_detail_ok,
            (
                f"helper={mdc_helper_ok}, "
                f"result={mdc_result_ok}, detail={mdc_detail_ok}"
            ),
        )

        condition_structure_ok = (
            "renderUserConditionSummary" in render_adrg
            and "renderUserConditionTables" in render_adrg
        )
        add(
            checks,
            "F02",
            "분류조건 요약과 조건상세 분리",
            condition_structure_ok,
            "상단 이해용 / 하단 검증용",
        )

        nav_tokens = ("historyStack", "restoreScroll", "restoreWindowScroll")
        nav_ok = all(token in app for token in nav_tokens)
        add(
            checks,
            "F03",
            "뒤로가기 검색·스크롤 상태 복원",
            nav_ok,
            f"required={nav_tokens}",
        )

        filter_ok = (
            "classification" in html.lower()
            and "classification" in app
        )
        add(
            checks,
            "F04",
            "질병군 분류 필터 유지",
            filter_ok,
            "일반 ADRG 카드 표시 추가 후 필터 계약도 회귀하지 않아야 함",
        )

        # ------------------------------------------------------------
        # G. Exhaustive runtime data coverage for the future general ADRG badges
        # ------------------------------------------------------------
        probe = r"""
'use strict';
const path = require('node:path');
const { KdrgSearchService } = require('./electron/src/kdrg-search-service');
const service = new KdrgSearchService(
  path.resolve('data/kdrg_v47_search_integrated_v3.json')
);

let total = 0;
let displayArray = 0;
let fallbackOnly = 0;
let noDisplay = 0;
let multiLabel = 0;
const missing = [];
const fallbackSamples = [];
const multiSamples = [];

for (const id of [...service.recordMaps.ADRG.keys()].sort()) {
  total += 1;
  const row = service.makeSearchResult(
    'ADRG',
    id,
    1000,
    'EXACT_ID',
    ['entity_id'],
  );
  const labels = Array.isArray(row?.summary?.abc_display_labels)
    ? row.summary.abc_display_labels.filter(Boolean)
    : [];
  const fallback = row?.summary?.classification_code
    || row?.summary?.classification_display_label
    || null;

  if (labels.length) {
    displayArray += 1;
    if (labels.length > 1) {
      multiLabel += 1;
      if (multiSamples.length < 20) multiSamples.push({id, labels});
    }
  } else if (fallback) {
    fallbackOnly += 1;
    if (fallbackSamples.length < 20) fallbackSamples.push({id, fallback});
  } else {
    noDisplay += 1;
    if (missing.length < 20) missing.push(id);
  }
}

console.log(JSON.stringify({
  total,
  displayArray,
  fallbackOnly,
  noDisplay,
  multiLabel,
  missing,
  fallbackSamples,
  multiSamples,
}));
"""
        rc, out = run(["node", "-e", probe], timeout=1200)
        require(rc == 0, f"ADRG classification runtime probe 실패\n{out[-3000:]}")
        runtime = json.loads(out.strip().splitlines()[-1])

        add(
            checks,
            "G01",
            "ADRG 1,132건 검색카드용 질병군 분류 데이터 가용성",
            runtime.get("noDisplay") == 0,
            (
                f"total={runtime.get('total')}, "
                f"displayArray={runtime.get('displayArray')}, "
                f"fallbackOnly={runtime.get('fallbackOnly')}, "
                f"noDisplay={runtime.get('noDisplay')}, "
                f"multiLabel={runtime.get('multiLabel')}, "
                f"missing={runtime.get('missing')}"
            ),
        )

        # Existing CSS support is informational. 70B may add/adjust one shared rule.
        css_group_ok = (
            ".classification-badge" in css
            and ".classification-badge-group" in css
        )
        add(
            checks,
            "G02",
            "기존 질병군 badge CSS 재사용 가능",
            css_group_ok,
            "새 badge 디자인을 만들지 않고 기존 A/B/C 디자인 재사용",
            gate=False,
            status_if_false="WARN",
        )

        gate_failures = [
            c for c in checks
            if c["gate"] and c["status"] == "FAIL"
        ]
        warnings = [c for c in checks if c["status"] == "WARN"]

        report = {
            "stage": "70A_AUDIT_0518_PHASE1_UI_COMPLETION_R3",
            "status": "PASS" if not gate_failures else "GAPS_FOUND",
            "base_commit": head,
            "base_version": BASE_VERSION,
            "next_version": NEXT_VERSION,
            "runtime_json": "UNCHANGED",
            "tracked_files": "UNCHANGED",
            "staging": "EMPTY",
            "checks": checks,
            "gate_failure_ids": [c["id"] for c in gate_failures],
            "gate_fail_count": len(gate_failures),
            "warning_count": len(warnings),
            "runtime_adrg_classification": runtime,
            "requested_layout": {
                "normal_adrg_result_classification": "RIGHT_ALIGNED",
                "relation_result_classification": "RIGHT_ALIGNED",
                "shared_css_class": "result-card-classification",
                "responsive": "ALLOW_WRAP_BUT_KEEP_RIGHT_ALIGNMENT",
                "relation_level_chip": "PRESERVE",
            },
            "readiness": (
                "READY_FOR_PHASE1_CLOSE"
                if not gate_failures
                else "READY_FOR_70B_GENERALIZED_UI_FIX_SHADOW"
            ),
        }

        REPORT_JSON.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        lines = [
            "[AUDIT] Stage70A R3 / 0.5.18 1차 UI 완료 전수감사",
            f"base_commit={head}",
            f"base_version={BASE_VERSION}",
            f"next_version={NEXT_VERSION}",
            f"gate_fail_count={len(gate_failures)}",
            f"warning_count={len(warnings)}",
            "",
        ]
        for c in checks:
            lines.append(
                f"[{c['status']}] {c['id']} {c['title']} | {c['detail']}"
            )
        lines += [
            "",
            "target_general_adrg_classification=RIGHT_ALIGNED",
            "target_relation_classification=RIGHT_ALIGNED",
            "relation_level_chip=PRESERVE",
            "runtime_json=UNCHANGED",
            "tracked_files=UNCHANGED",
            "staging=EMPTY",
            f"readiness={report['readiness']}",
            f"report={REPORT_TXT.relative_to(ROOT)}",
            f"json={REPORT_JSON.relative_to(ROOT)}",
        ]

        REPORT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("\n".join(lines))
        return 0

    except Exception as exc:
        payload = {
            "stage": "70A_AUDIT_0518_PHASE1_UI_COMPLETION_R3",
            "status": "FAIL",
            "error": f"{type(exc).__name__}: {exc}",
        }
        REPORT_JSON.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        lines = [
            "[FAIL] Stage70A R3 1차 UI 완료 전수감사",
            f"{type(exc).__name__}: {exc}",
            f"report={REPORT_TXT.relative_to(ROOT)}",
        ]
        REPORT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("\n".join(lines))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
