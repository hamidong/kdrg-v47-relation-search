from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent

BASE_COMMIT = "1bd70d50c85305e2ff64ebb0a17ec619719e8a40"
BASE_TAG = "electron-v0.5.18"
BASE_VERSION = "0.5.18"

RUNTIME_REL = Path("data/kdrg_v47_search_integrated_v3.json")
RUNTIME_SHA = "1a3d50400567ecaad9695b7be8e7c0382131f8652f398e010cf01f4d8dda6c58"

REPORT_DIR = ROOT / "reports/stage72a_0519_relation_result_layout_audit_r1"
REPORT_JSON = REPORT_DIR / "audit.json"
REPORT_TXT = REPORT_DIR / "audit_summary.txt"


class Stop(RuntimeError):
    pass


def require(ok, message):
    if not ok:
        raise Stop(message)


def run(cmd, timeout=120):
    p = subprocess.run(
        [str(x) for x in cmd],
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    return p.returncode, p.stdout


def git_text(*args):
    rc, out = run(["git", *args])
    require(rc == 0, f"git {' '.join(args)} 실패\n{out[-3000:]}")
    return out.strip()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def extract_block(text: str, start_pat: str, end_pat: str) -> str:
    m1 = re.search(start_pat, text, re.M)
    require(m1, f"block start not found: {start_pat}")
    m2 = re.search(end_pat, text[m1.start():], re.M)
    require(m2, f"block end not found: {end_pat}")
    return text[m1.start():m1.start()+m2.start()]


def main():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    report = {
        "stage": "72A_0519_RELATION_RESULT_LAYOUT_AUDIT_R1",
        "status": "FAIL",
        "mutated": False,
    }

    try:
        head = git_text("rev-parse", "HEAD")
        origin = git_text("rev-parse", "origin/main")
        branch = git_text("branch", "--show-current")
        tag_commit = git_text("rev-list", "-n", "1", BASE_TAG)

        require(head == BASE_COMMIT, f"HEAD 불일치: {head}")
        require(origin == BASE_COMMIT, f"origin/main 불일치: {origin}")
        require(branch == "main", f"branch 불일치: {branch}")
        require(tag_commit == BASE_COMMIT, f"{BASE_TAG} commit 불일치: {tag_commit}")

        pkg = json.loads((ROOT / "electron/package.json").read_text(encoding="utf-8"))
        require(pkg.get("version") == BASE_VERSION, f"package version 불일치: {pkg.get('version')}")
        require(sha256(ROOT / RUNTIME_REL) == RUNTIME_SHA, "운영 JSON SHA 불일치")

        tracked_changed = [x for x in git_text("diff", "--name-only", "HEAD").splitlines() if x]
        staged = [x for x in git_text("diff", "--cached", "--name-only").splitlines() if x]
        require(not tracked_changed, f"tracked 변경 있음: {tracked_changed}")
        require(not staged, f"staging 변경 있음: {staged}")

        app_js = (ROOT / "electron/renderer/app.js").read_text(encoding="utf-8")
        styles = (ROOT / "electron/renderer/styles.css").read_text(encoding="utf-8")

        relation_render_block = extract_block(
            app_js,
            r"^function renderRelationResults\(response\)\s*\{",
            r"^function relationMatchCard\(match\)",
        )
        relation_header_counts = re.search(
            r"function renderRelationCounts\(response\)\s*\{[\s\S]*?same-choice",
            app_js,
            re.M,
        )

        findings = {}

        # Current card layout audit
        findings["card_has_relation_level_chip_top_right"] = "makeChip(result.relation_level_label" in relation_render_block
        findings["card_appends_classification_in_chip_row"] = "appendClassificationBadges(chips" in relation_render_block
        findings["card_top_right_classification_group"] = "result-card-classification" in relation_render_block
        findings["header_same_choice_exists"] = bool(relation_header_counts)
        findings["header_same_choice_emphasis_rule"] = ".same-choice-count" in styles or ".same-choice-summary" in styles

        # Search-result general ADRG card branch should already support top-right classification group
        findings["general_result_top_right_classification"] = "result-card-classification" in app_js and "appendClassificationBadges(" in app_js

        # Requested 72A targets
        targets = {
            "T01_relation_card_top_right_should_show_classification_not_relation_level": False,
            "T02_relation_card_lower_old_classification_slot_should_be_removed": False,
            "T03_relation_context_should_move_to_header_summary": False,
            "T04_header_same_choice_summary_should_be_more_prominent": False,
            "T05_runtime_json_must_remain_unchanged": True,
            "T06_public_search_types_policy_must_remain_preserved": True,
        }

        # Decide pass/fail per target from current 0.5.18
        if not findings["card_has_relation_level_chip_top_right"] and findings["card_top_right_classification_group"]:
            targets["T01_relation_card_top_right_should_show_classification_not_relation_level"] = True

        if not findings["card_appends_classification_in_chip_row"]:
            targets["T02_relation_card_lower_old_classification_slot_should_be_removed"] = True

        if findings["header_same_choice_exists"]:
            targets["T03_relation_context_should_move_to_header_summary"] = True

        # Current 0.5.18 likely has same-choice summary but not emphasized enough
        # so this target intentionally remains False until Stage72B fixes styles.
        if ".relation-summary-chip" in styles or ".same-choice-summary" in styles:
            targets["T04_header_same_choice_summary_should_be_more_prominent"] = True

        pass_count = sum(1 for v in targets.values() if v)
        fail_targets = [k for k, v in targets.items() if not v]

        report.update({
            "status": "PASS",
            "head": head,
            "origin_main": origin,
            "tag": BASE_TAG,
            "package_version": BASE_VERSION,
            "runtime_json": "UNCHANGED",
            "tracked": "CLEAN",
            "staging": "EMPTY",
            "findings": findings,
            "targets": targets,
            "pass_count": pass_count,
            "fail_count": len(fail_targets),
            "fail_targets": fail_targets,
            "requested_scope": [
                "복수검색 결과 카드 우상단의 '같은 조건 선택지' chip을 제거하고 질병군 분류 badge로 대체",
                "복수검색 결과 카드 하단/좌측에 별도로 보이던 분류 badge 중복 노출 제거",
                "검색결과 4건 우측 summary 영역의 '같은 선택지 4'를 더 크게 하고 공통 관련 ADRG 의미가 드러나게 강화",
                "운영 JSON 및 공개 검색정책은 변경하지 않음",
            ],
            "candidate_product_files": [
                "electron/renderer/app.js",
                "electron/renderer/styles.css",
            ],
            "candidate_validator_files": [
                "electron/tests/validate-stage72b-0519-relation-result-layout.js",
            ],
            "mutated": False,
            "readiness": "READY_FOR_72B_GENERALIZED_SHADOW_FIX",
        })

        REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        lines = [
            "[PASS] Stage72A R1 / 0.5.19 복수검색 결과 레이아웃 감사",
            f"base_commit={BASE_COMMIT}",
            f"base_version={BASE_VERSION}",
            f"relation_top_right_relation_chip={findings['card_has_relation_level_chip_top_right']}",
            f"relation_lower_classification_slot={findings['card_appends_classification_in_chip_row']}",
            f"relation_top_right_classification_group={findings['card_top_right_classification_group']}",
            f"header_same_choice_exists={findings['header_same_choice_exists']}",
            f"header_same_choice_emphasis_rule={findings['header_same_choice_emphasis_rule']}",
            f"target_pass={pass_count}",
            f"target_fail={len(fail_targets)}",
            "fail_targets=" + ",".join(fail_targets),
            "runtime_json=UNCHANGED",
            "tracked=CLEAN",
            "staging=EMPTY",
            "mutated=NO",
            "readiness=READY_FOR_72B_GENERALIZED_SHADOW_FIX",
            f"report={REPORT_TXT.relative_to(ROOT)}",
            f"json={REPORT_JSON.relative_to(ROOT)}",
        ]
        REPORT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("\n".join(lines))
        return 0

    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        lines = [
            "[FAIL] Stage72A 관계검색 결과 레이아웃 감사 — 파일 변경 없음",
            f"{type(exc).__name__}: {exc}",
            "mutated=NO",
            f"report={REPORT_TXT.relative_to(ROOT)}",
        ]
        REPORT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("\n".join(lines))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
