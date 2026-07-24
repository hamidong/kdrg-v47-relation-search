from __future__ import annotations

import hashlib
import json
import os
import py_compile
import re
import sys
from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCRIPT_VERSION = "2026-07-24_KDRG_V47_PYSIDE_RUNTIME_UI_BRIDGE_VALIDATOR_V4"
ROOT = Path(__file__).resolve().parent
DATA_JSON = ROOT / "data" / "kdrg_v47_search_integrated.json"
ADAPTER = ROOT / "app" / "runtime_data_store.py"
MAIN_WINDOW = ROOT / "app" / "main_window.py"
DIALOGS = ROOT / "app" / "dialogs.py"
SERVICE = ROOT / "app" / "kdrg_search_service.py"
SMOKE = ROOT / "tests" / "smoke_test_runtime_ui_bridge.py"
BUILD_REPORT_JSON = ROOT / "reports" / "runtime_ui_bridge_build_report.json"
RUNTIME_VALIDATION_JSON = ROOT / "reports" / "runtime_search_service_validation_report.json"
REPORT_TXT = ROOT / "reports" / "runtime_ui_bridge_validation_report.txt"
REPORT_JSON = ROOT / "reports" / "runtime_ui_bridge_validation_report.json"
SHIM = ROOT / "reports" / "qt_native_shim"

EXPECTED = {
    "adrg": 1132,
    "aadrg": 1233,
    "rdrg": 2699,
    "table": 1308,
    "ast": 390,
    "code": 16571,
}

POSITIVE_CONTEXTS = {
    "positive_required_table",
    "required_table_with_optional_companion",
    "semantic_text_condition",
}
NEGATIVE_CONTEXTS = {
    "negative_or_exclusion_reference",
    "allowed_exception_under_negated_or_procedure",
    "optional_companion_table",
}
GLIBC_CORE = {
    "libc.so.6",
    "libm.so.6",
    "libpthread.so.0",
    "libdl.so.2",
    "librt.so.1",
    "ld-linux-x86-64.so.2",
}
NATIVE_BOOTSTRAP_MARKER = "KDRG_QT_NATIVE_VALIDATOR_BOOTSTRAPPED"


def bootstrap_qt_native_process() -> None:
    """41번 V7의 격리 shim을 프로세스 시작 시점부터 적용한다.

    Linux 동적 로더는 프로세스가 시작될 때 LD_LIBRARY_PATH를 읽는다.
    실행 중 os.environ만 수정한 뒤 PySide6를 import하면 libGL.so.1을
    찾지 못할 수 있으므로, PySide import 전에 현재 검증 스크립트를
    동일 Python 실행파일로 한 번 재실행한다.
    """
    if os.environ.get(NATIVE_BOOTSTRAP_MARKER) == "1":
        return
    if not SHIM.is_dir():
        raise RuntimeError(
            "41번 V7 native shim이 없습니다: "
            f"{SHIM}. 41_build_kdrg_pyside_runtime_ui_bridge_V7.py PASS가 선행되어야 합니다."
        )

    env = os.environ.copy()
    # 41번 V7 smoke와 동일하게 격리 shim만 LD_LIBRARY_PATH로 사용한다.
    # 기존 donor directory가 섞이면 구형 libc·libm이 다시 우선될 수 있다.
    env["LD_LIBRARY_PATH"] = str(SHIM)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["QT_OPENGL"] = "software"
    env["LIBGL_ALWAYS_SOFTWARE"] = "1"
    env["QT_QUICK_BACKEND"] = "software"
    env["KDRG_DISABLE_SETTINGS"] = "1"
    env[NATIVE_BOOTSTRAP_MARKER] = "1"
    env["PYTHONUNBUFFERED"] = "1"

    script = str(Path(__file__).resolve())
    os.execve(sys.executable, [sys.executable, script, *sys.argv[1:]], env)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON 최상위가 object가 아닙니다: {path}")
    return value


def normalize(value: Any) -> str:
    return re.sub(r"[.\s_-]+", "", str(value or "").upper())


def unique(values: Iterable[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def short_list(values: Iterable[Any], limit: int = 18) -> str:
    rows = unique(values)
    if not rows:
        return "-"
    if len(rows) <= limit:
        return ", ".join(rows)
    return f"{', '.join(rows[:limit])} 외 {len(rows) - limit}개"


def code_type(*values: Any) -> str:
    text = " ".join(str(value or "") for value in values).casefold()
    if any(token in text for token in ("secondary", "other diagnosis", "기타진단", "other_diagnosis")):
        return "기타진단코드"
    if any(token in text for token in ("diagnosis", "진단", "principal", "주진단")):
        return "상병코드"
    if any(token in text for token in ("add_on", "addon", "supplement", "부가", "additional")):
        return "부가코드"
    if any(token in text for token in ("test", "검사")):
        return "검사·처치코드"
    return "수술·처치코드"


def ancestors(node_id: str, nodes: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    current = nodes.get(node_id)
    while current:
        parent_id = str(current.get("parent_node_id") or "")
        if not parent_id or parent_id in seen:
            break
        seen.add(parent_id)
        parent = nodes.get(parent_id)
        if parent is None:
            break
        output.append(parent)
        current = parent
    return output


def independent_semantic_indexes(data: dict[str, Any]) -> tuple[dict[str, list[str]], dict[str, list[str]], dict[str, int]]:
    positive: defaultdict[str, set[str]] = defaultdict(set)
    negative: defaultdict[str, set[str]] = defaultdict(set)
    counts: defaultdict[str, int] = defaultdict(int)

    for ast in data.get("condition_ast_records") or []:
        adrg = str(ast.get("adrg") or "")
        nodes = {
            str(node.get("node_id") or ""): node
            for node in ast.get("nodes") or []
            if str(node.get("node_id") or "")
        }
        for node in ast.get("nodes") or []:
            node_id = str(node.get("node_id") or "")
            node_type = str(node.get("node_type") or "")
            table_ids = unique(node.get("logical_table_ids") or [])
            if not table_ids:
                continue
            semantic_type = str(node.get("semantic_type") or "")
            ancestor_types = [str(item.get("node_type") or "") for item in ancestors(node_id, nodes)]

            if node_type == "TEXT_CONDITION" and semantic_type == "optional_table_presence":
                for index, table_id in enumerate(table_ids):
                    context = "required_table_with_optional_companion" if index == 0 else "optional_companion_table"
                    (positive if context in POSITIVE_CONTEXTS else negative)[table_id].add(adrg)
                    counts[context] += 1
                continue

            allowed_exception = False
            if node_type == "TABLE_REF":
                parent = nodes.get(str(node.get("parent_node_id") or ""))
                if parent and str(parent.get("node_type") or "") == "EXCLUSION":
                    children = [str(item) for item in parent.get("child_node_ids") or []]
                    if len(children) >= 2 and children[1] == node_id:
                        base = nodes.get(children[0])
                        base_is_or = bool(
                            base
                            and str(base.get("node_type") or "") == "TEXT_CONDITION"
                            and str(base.get("semantic_type") or "") == "or_procedure"
                        )
                        parent_types = [
                            str(item.get("node_type") or "")
                            for item in ancestors(str(parent.get("node_id") or ""), nodes)
                        ]
                        allowed_exception = base_is_or and "NOT" in parent_types

            if allowed_exception:
                context = "allowed_exception_under_negated_or_procedure"
            elif "NOT" in ancestor_types or "EXCLUSION" in ancestor_types:
                context = "negative_or_exclusion_reference"
            elif node_type == "TEXT_CONDITION":
                context = "semantic_text_condition"
            else:
                context = "positive_required_table"

            target = positive if context in POSITIVE_CONTEXTS else negative
            for table_id in table_ids:
                target[table_id].add(adrg)
                counts[context] += 1

    return (
        {key: sorted(value) for key, value in sorted(positive.items())},
        {key: sorted(value) for key, value in sorted(negative.items())},
        dict(sorted(counts.items())),
    )


def dotted_query(code: str) -> str:
    clean = normalize(code)
    if len(clean) < 4:
        return clean
    return f"{clean[:-1]}.{clean[-1]}"


def main() -> int:
    generated_at = datetime.now(timezone.utc).isoformat()
    REPORT_TXT.parent.mkdir(parents=True, exist_ok=True)

    checks: list[dict[str, Any]] = []
    failures: list[str] = []

    def check(name: str, condition: bool, actual: Any = None, expected: Any = None) -> None:
        passed = bool(condition)
        checks.append({"name": name, "status": "PASS" if passed else "FAIL", "actual": actual, "expected": expected})
        if not passed:
            failures.append(f"{name} | actual={actual!r} | expected={expected!r}")

    required = [DATA_JSON, ADAPTER, MAIN_WINDOW, DIALOGS, SERVICE, SMOKE, BUILD_REPORT_JSON, RUNTIME_VALIDATION_JSON]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise RuntimeError("필수 파일이 없습니다:\n- " + "\n- ".join(missing))

    source_hashes_before = {str(path.relative_to(ROOT)): sha256(path) for path in required if path.is_file()}
    data = load_json(DATA_JSON)
    build_report = load_json(BUILD_REPORT_JSON)
    runtime_report = load_json(RUNTIME_VALIDATION_JSON)
    main_source = MAIN_WINDOW.read_text(encoding="utf-8")
    dialog_source = DIALOGS.read_text(encoding="utf-8")
    adapter_source = ADAPTER.read_text(encoding="utf-8")
    smoke_source = SMOKE.read_text(encoding="utf-8")

    # 1. 입력·선행 검증
    check("A01 통합 JSON schema V2", str((data.get("meta") or {}).get("schema_version") or "") == "kdrg-v47-search-integrated-v2", (data.get("meta") or {}).get("schema_version"), "kdrg-v47-search-integrated-v2")
    check("A02 통합 JSON 자체 PASS", str((data.get("validation") or {}).get("status") or "") == "PASS", (data.get("validation") or {}).get("status"), "PASS")
    check("A03 41번 build PASS", str((build_report.get("validation") or {}).get("status") or build_report.get("status") or "") == "PASS", (build_report.get("validation") or {}).get("status") or build_report.get("status"), "PASS")
    check("A04 41번 V7", "BUILDER_V7" in str(build_report.get("script_version") or ""), build_report.get("script_version"), "*BUILDER_V7")
    check("A05 40번 runtime 검증 PASS", str((runtime_report.get("validation") or {}).get("status") or runtime_report.get("status") or "") == "PASS", (runtime_report.get("validation") or {}).get("status") or runtime_report.get("status"), "PASS")
    check("A06 40번 FAIL 0", int((runtime_report.get("validation") or {}).get("fail_count") or 0) == 0, (runtime_report.get("validation") or {}).get("fail_count"), 0)
    check("A07 통합 JSON SHA 일치", sha256(DATA_JSON) == str((build_report.get("source_hashes") or {}).get("integrated_json") or sha256(DATA_JSON)), sha256(DATA_JSON), (build_report.get("source_hashes") or {}).get("integrated_json") or sha256(DATA_JSON))
    check("A08 adapter py_compile", _compile_ok(ADAPTER), True, True)
    check("A09 main_window py_compile", _compile_ok(MAIN_WINDOW), True, True)
    check("A10 dialogs py_compile", _compile_ok(DIALOGS), True, True)
    check("A11 smoke py_compile", _compile_ok(SMOKE), True, True)

    # 2. 원천 독립 집계
    adrg_rows = list(data.get("adrg_records") or [])
    aadrg_rows = list(data.get("aadrg_records") or [])
    rdrg_rows = list(data.get("rdrg_records") or [])
    table_rows = list(data.get("logical_table_records") or [])
    ast_rows = list(data.get("condition_ast_records") or [])
    code_rows = list(data.get("code_records") or [])
    adrg_map = {str(row.get("adrg") or ""): row for row in adrg_rows}
    aadrg_map = {str(row.get("aadrg") or ""): row for row in aadrg_rows}
    rdrg_map = {str(row.get("code") or row.get("rdrg") or ""): row for row in rdrg_rows}
    table_map = {str(row.get("logical_table_id") or ""): row for row in table_rows}
    code_map = {normalize(row.get("code")): row for row in code_rows}

    check("B01 ADRG 1132", len(adrg_rows) == EXPECTED["adrg"], len(adrg_rows), EXPECTED["adrg"])
    check("B02 AADRG 1233", len(aadrg_rows) == EXPECTED["aadrg"], len(aadrg_rows), EXPECTED["aadrg"])
    check("B03 RDRG 2699", len(rdrg_rows) == EXPECTED["rdrg"], len(rdrg_rows), EXPECTED["rdrg"])
    check("B04 TABLE 1308", len(table_rows) == EXPECTED["table"], len(table_rows), EXPECTED["table"])
    check("B05 AST 390", len(ast_rows) == EXPECTED["ast"], len(ast_rows), EXPECTED["ast"])
    check("B06 CODE 16571", len(code_rows) == EXPECTED["code"], len(code_rows), EXPECTED["code"])
    check("B07 ADRG ID 중복 0", len(adrg_map) == len(adrg_rows), len(adrg_rows) - len(adrg_map), 0)
    check("B08 AADRG ID 중복 0", len(aadrg_map) == len(aadrg_rows), len(aadrg_rows) - len(aadrg_map), 0)
    check("B09 RDRG ID 중복 0", len(rdrg_map) == len(rdrg_rows), len(rdrg_rows) - len(rdrg_map), 0)
    check("B10 TABLE ID 중복 0", len(table_map) == len(table_rows), len(table_rows) - len(table_map), 0)
    check("B11 CODE ID 중복 0", len(code_map) == len(code_rows), len(code_rows) - len(code_map), 0)
    check("B12 AADRG parent 등록", all(str(row.get("adrg") or "") in adrg_map for row in aadrg_rows), sum(str(row.get("adrg") or "") not in adrg_map for row in aadrg_rows), 0)
    check("B13 RDRG parent 등록", all(str(row.get("adrg") or "") in adrg_map and str(row.get("aadrg") or "") in aadrg_map for row in rdrg_rows), sum(not (str(row.get("adrg") or "") in adrg_map and str(row.get("aadrg") or "") in aadrg_map) for row in rdrg_rows), 0)
    check("B14 TABLE related ADRG 등록", all(x in adrg_map for row in table_rows for x in row.get("related_adrgs") or []), sum(x not in adrg_map for row in table_rows for x in row.get("related_adrgs") or []), 0)
    check("B15 CODE related ADRG 등록", all(x in adrg_map for row in code_rows for x in row.get("related_adrgs") or []), sum(x not in adrg_map for row in code_rows for x in row.get("related_adrgs") or []), 0)
    check("B16 X04 ADRG 비등록", "X04" not in adrg_map, "X04" in adrg_map, False)

    # native shim은 main() 진입 전에 self re-exec로 적용되어야 한다.
    # 여기에서 os.environ만 수정하는 방식은 동적 로더 초기화 이후라 효력이 보장되지 않는다.
    if os.environ.get(NATIVE_BOOTSTRAP_MARKER) != "1":
        raise RuntimeError("PySide native bootstrap 재실행이 적용되지 않았습니다.")
    active_library_paths = [item for item in os.environ.get("LD_LIBRARY_PATH", "").split(os.pathsep) if item]
    if not active_library_paths or Path(active_library_paths[0]).resolve() != SHIM.resolve():
        raise RuntimeError(
            "격리 qt_native_shim이 LD_LIBRARY_PATH 첫 경로가 아닙니다: "
            f"{os.environ.get('LD_LIBRARY_PATH', '')}"
        )

    from app.models import AdvancedCondition  # noqa: PLC0415
    from app.runtime_data_store import KDRGRuntimeDataStore  # noqa: PLC0415

    store = KDRGRuntimeDataStore()

    # 3. adapter 전체 변환 전수 대조
    check("C01 runtime store class", type(store).__name__ == "KDRGRuntimeDataStore", type(store).__name__, "KDRGRuntimeDataStore")
    check("C02 runtime ready", bool(store.runtime_status.get("ready")), store.runtime_status.get("ready"), True)
    check("C03 rules 전체", set(store.rules) == set(adrg_map), len(set(store.rules) ^ set(adrg_map)), 0)
    check("C04 tables 전체", set(store.tables) == set(table_map), len(set(store.tables) ^ set(table_map)), 0)
    check("C05 code index 전체", set(store.code_to_tables) == set(code_map), len(set(store.code_to_tables) ^ set(code_map)), 0)
    check("C06 AST map 전체", set(store._ast_rows) == {str(row.get("adrg") or "") for row in ast_rows}, len(set(store._ast_rows) ^ {str(row.get("adrg") or "") for row in ast_rows}), 0)

    code_table_mismatch: list[str] = []
    code_relation_mismatch: list[str] = []
    for code, row in code_map.items():
        expected_tables = list(row.get("logical_table_ids") or [])
        if list(store.code_to_tables.get(code) or []) != expected_tables:
            code_table_mismatch.append(code)
        expected_relation = {
            "physical_source": short_list(row.get("source_adrgs") or []),
            "condition_usage": short_list(row.get("condition_adrgs") or []),
            "runtime_related": short_list(row.get("related_adrgs") or []),
            "source_families": short_list(row.get("source_adrg_families") or []),
        }
        if store.relation_summary_for_code(str(row.get("code") or "")) != expected_relation:
            code_relation_mismatch.append(str(row.get("code") or ""))
    check("C07 CODE→TABLE 16,571 전수", not code_table_mismatch, code_table_mismatch[:10], [])
    check("C08 CODE 관계요약 16,571 전수", not code_relation_mismatch, code_relation_mismatch[:10], [])

    table_code_mismatch: list[str] = []
    table_relation_mismatch: list[str] = []
    table_member_count_mismatch: list[str] = []
    for table_id, row in table_map.items():
        actual_table = store.tables.get(table_id)
        expected_codes = list(row.get("codes") or [])
        actual_codes = [member.code for member in actual_table.members] if actual_table else []
        if actual_codes != expected_codes:
            table_code_mismatch.append(table_id)
        if actual_table and actual_table.count != int(row.get("code_count") or len(expected_codes)):
            table_member_count_mismatch.append(table_id)
        expected_relation = {
            "physical_source": short_list(row.get("source_adrgs") or []),
            "condition_usage": short_list(row.get("condition_adrgs") or []),
            "runtime_related": short_list(row.get("related_adrgs") or []),
            "source_families": short_list(row.get("source_adrg_families") or []),
        }
        if store.relation_summary_for_table(table_id) != expected_relation:
            table_relation_mismatch.append(table_id)
    check("C09 TABLE code 배열 1,308 전수", not table_code_mismatch, table_code_mismatch[:10], [])
    check("C10 TABLE code_count 1,308 전수", not table_member_count_mismatch, table_member_count_mismatch[:10], [])
    check("C11 TABLE 관계요약 1,308 전수", not table_relation_mismatch, table_relation_mismatch[:10], [])

    rule_metadata_mismatch: list[str] = []
    mapping_mismatch: list[str] = []
    for adrg, row in adrg_map.items():
        rule = store.rules.get(adrg)
        if not rule or rule.mdc != str(row.get("mdc") or "") or rule.title != str(row.get("adrg_name") or adrg):
            rule_metadata_mismatch.append(adrg)
            continue
        expected_children = sorted(str(x) for x in row.get("aadrg_codes") or [])
        actual_children = sorted(item.aadrg for item in rule.aadrg_mappings)
        if actual_children != expected_children:
            mapping_mismatch.append(adrg)
    check("C12 Rule metadata 1,132 전수", not rule_metadata_mismatch, rule_metadata_mismatch[:10], [])
    check("C13 Rule AADRG mapping 전수", not mapping_mismatch, mapping_mismatch[:10], [])

    expected_positive, expected_negative, semantic_counts = independent_semantic_indexes(data)
    actual_positive = {key: list(value) for key, value in sorted(store.table_to_rules.items())}
    actual_negative = {key: list(value) for key, value in sorted(store.exclusion_table_to_rules.items())}
    check("C14 긍정 TABLE→ADRG 독립 재계산", actual_positive == expected_positive, _map_diff_count(actual_positive, expected_positive), 0)
    check("C15 제외 TABLE→ADRG 독립 재계산", actual_negative == expected_negative, _map_diff_count(actual_negative, expected_negative), 0)
    check("C16 허용 예외 context 19", semantic_counts.get("allowed_exception_under_negated_or_procedure") == 19, semantic_counts.get("allowed_exception_under_negated_or_procedure"), 19)
    check("C17 선택 동반 context 7", semantic_counts.get("optional_companion_table") == 7, semantic_counts.get("optional_companion_table"), 7)
    check("C18 선택 동반 필수 context 7", semantic_counts.get("required_table_with_optional_companion") == 7, semantic_counts.get("required_table_with_optional_companion"), 7)

    mdcs = sorted({str(row.get("mdc") or "") for row in adrg_rows if str(row.get("mdc") or "")})
    adapter_mdcs = sorted(("PRE" if code == "PRE" else code.zfill(2)) for code in mdcs)
    check("C19 MDC 전체 변환", sorted(store.mdcs) == adapter_mdcs, sorted(store.mdcs), adapter_mdcs)
    check("C20 기본 목록 1~200", 1 <= len(store.search("", "전체")) <= 200, len(store.search("", "전체")), "1..200")
    check("C21 기본 E011 첫 카드", bool(store.search("", "전체")) and store.search("", "전체")[0].key == "E011", store.search("", "전체")[0].key if store.search("", "전체") else None, "E011")

    # 4. 동적 검색 fixture
    adrg_fixture = "9600" if "9600" in adrg_map else sorted(adrg_map)[0]
    aadrg_fixture = next((code for code in sorted(aadrg_map) if str(aadrg_map[code].get("adrg") or "") == adrg_fixture), sorted(aadrg_map)[0])
    rdrg_fixture = next((code for code in sorted(rdrg_map) if str(rdrg_map[code].get("adrg") or "") == adrg_fixture), sorted(rdrg_map)[0])
    table_fixture = "LT_9610_001" if "LT_9610_001" in table_map else sorted(table_map)[0]

    diagnosis_fixture = None
    diagnosis_category = None
    for row in code_rows:
        roles = [code_type(role) for role in row.get("roles") or []]
        table_types = [
            code_type((table_map.get(str(tid)) or {}).get("logical_table_scope"), (table_map.get(str(tid)) or {}).get("logical_table_type"))
            for tid in row.get("logical_table_ids") or []
        ]
        types = set(roles + table_types)
        raw_code = str(row.get("code") or "")
        if "상병코드" in types and len(normalize(raw_code)) >= 4:
            diagnosis_fixture = raw_code
            diagnosis_category = "상병코드"
            break
    if diagnosis_fixture is None:
        diagnosis_fixture = str(code_rows[0].get("code") or "")
        diagnosis_category = "전체"

    adrg_result = store.search(adrg_fixture, "ADRG")
    aadrg_result = store.search(aadrg_fixture, "AADRG")
    rdrg_result = store.search(rdrg_fixture, "RDRG")
    table_result = store.search(table_fixture, "TABLE")
    code_result = store.search(dotted_query(diagnosis_fixture), diagnosis_category)
    mdc_fixture = next(iter(store.mdcs))
    mdc_result = store.search(mdc_fixture, "MDC")

    check("D01 ADRG exact 검색", bool(adrg_result) and adrg_result[0].key == adrg_fixture, _result_head(adrg_result), adrg_fixture)
    check("D02 AADRG exact parent", bool(aadrg_result) and aadrg_result[0].key == str(aadrg_map[aadrg_fixture].get("adrg") or ""), _result_head(aadrg_result), aadrg_map[aadrg_fixture].get("adrg"))
    check("D03 AADRG label exact", bool(aadrg_result) and aadrg_result[0].label == aadrg_fixture, _result_head(aadrg_result), aadrg_fixture)
    check("D04 RDRG exact parent", bool(rdrg_result) and rdrg_result[0].key == str(rdrg_map[rdrg_fixture].get("adrg") or ""), _result_head(rdrg_result), rdrg_map[rdrg_fixture].get("adrg"))
    check("D05 RDRG label exact", bool(rdrg_result) and rdrg_result[0].label == rdrg_fixture, _result_head(rdrg_result), rdrg_fixture)
    check("D06 TABLE exact", bool(table_result) and table_result[0].key == table_fixture, _result_head(table_result), table_fixture)
    check("D07 CODE dotted 동적 fixture", bool(code_result) and normalize(code_result[0].key) == normalize(diagnosis_fixture), {"fixture": diagnosis_fixture, "query": dotted_query(diagnosis_fixture), "result": _result_head(code_result)}, diagnosis_fixture)
    check("D08 MDC 검색", bool(mdc_result) and mdc_result[0].key == mdc_fixture, _result_head(mdc_result), mdc_fixture)
    check("D09 빈 없는 ADRG 검색", len(adrg_result) >= 1, len(adrg_result), ">=1")
    check("D10 검색 최대 500", len(store.search(adrg_fixture[:2], "전체")) <= 500, len(store.search(adrg_fixture[:2], "전체")), "<=500")

    # 관계 분리 대표 및 전수
    if "S710" in code_map:
        s710 = store.relation_summary_for_code("S710")
        s710_row = code_map["S710"]
        check("D11 S710 physical source", s710["physical_source"] == short_list(s710_row.get("source_adrgs") or []), s710["physical_source"], short_list(s710_row.get("source_adrgs") or []))
        check("D12 S710 condition usage", s710["condition_usage"] == short_list(s710_row.get("condition_adrgs") or []), s710["condition_usage"], short_list(s710_row.get("condition_adrgs") or []))
        check("D13 S710 runtime related", s710["runtime_related"] == short_list(s710_row.get("related_adrgs") or []), s710["runtime_related"], short_list(s710_row.get("related_adrgs") or []))
        check("D14 X04 family provenance", "X04" in (s710_row.get("source_adrg_families") or []) and "X04" not in (s710_row.get("related_adrgs") or []), s710, "X04 only provenance")
    else:
        check("D11 S710 physical source", False, "S710 absent", "S710 present")
        check("D12 S710 condition usage", False, "S710 absent", "S710 present")
        check("D13 S710 runtime related", False, "S710 absent", "S710 present")
        check("D14 X04 family provenance", False, "S710 absent", "S710 present")

    expanded_tables = [row for row in table_rows if set(row.get("condition_adrgs") or []) - set(row.get("source_adrgs") or [])]
    expanded_codes = [row for row in code_rows if set(row.get("condition_adrgs") or []) - set(row.get("source_adrgs") or [])]
    check("D15 runtime 확장 TABLE 417", len(expanded_tables) == 417, len(expanded_tables), 417)
    check("D16 runtime 확장 CODE 9122", len(expanded_codes) == 9122, len(expanded_codes), 9122)
    check("D17 family source TABLE 1", sum(bool(row.get("source_adrg_families")) for row in table_rows) == 1, sum(bool(row.get("source_adrg_families")) for row in table_rows), 1)
    check("D18 family ref ADRG 미노출", all(set(row.get("source_adrg_families") or []).isdisjoint(set(row.get("related_adrgs") or [])) for row in table_rows), sum(not set(row.get("source_adrg_families") or []).isdisjoint(set(row.get("related_adrgs") or [])) for row in table_rows), 0)

    # relation_search 단일 코드 독립 대조
    relation_fixture = next((row for row in code_rows if any(tid in expected_positive for tid in row.get("logical_table_ids") or [])), None)
    if relation_fixture:
        rel_code = str(relation_fixture.get("code") or "")
        rel_type = next(iter(store._code_types_by_code.get(normalize(rel_code), {"자동판별"})))
        positive_rules = {adrg for tid in relation_fixture.get("logical_table_ids") or [] for adrg in expected_positive.get(str(tid), [])}
        exclusion_rules = {adrg for tid in relation_fixture.get("logical_table_ids") or [] for adrg in expected_negative.get(str(tid), [])}
        expected_candidates = sorted(positive_rules - exclusion_rules)
        actual_candidates = sorted(item.adrg for item in store.relation_search([AdvancedCondition(rel_type, rel_code)], "AND"))
        check("D19 단일코드 관계검색 독립대조", actual_candidates == expected_candidates, {"code": rel_code, "mismatch": sorted(set(actual_candidates) ^ set(expected_candidates))[:20]}, "mismatch=[]")
        check("D20 관계검색 미등록 ADRG 0", all(item in adrg_map for item in actual_candidates), sum(item not in adrg_map for item in actual_candidates), 0)
    else:
        check("D19 단일코드 관계검색 독립대조", False, "fixture 없음", "fixture 존재")
        check("D20 관계검색 미등록 ADRG 0", False, "fixture 없음", 0)

    # 5. UI source 계약 및 실제 offscreen MainWindow
    check("E01 main_window runtime adapter import", "from app.runtime_data_store import KDRGRuntimeDataStore as KDRGDataStore" in main_source, "runtime import" in main_source, True)
    check("E02 구 data_store import 제거", "from app.data_store import KDRGDataStore" not in main_source, "from app.data_store import KDRGDataStore" in main_source, False)
    check("E03 RDRG category 포함", '"RDRG"' in main_source, '"RDRG"' in main_source, True)
    check("E04 physical 표시 문구", "원문 TABLE 정의 ADRG" in main_source, "원문 TABLE 정의 ADRG" in main_source, True)
    check("E05 condition 표시 문구", "조건 AST 사용 ADRG" in main_source, "조건 AST 사용 ADRG" in main_source, True)
    check("E06 runtime 표시 문구", "검색용 관련 ADRG" in main_source, "검색용 관련 ADRG" in main_source, True)
    check("E07 adapter service 연결", "KdrgSearchService" in adapter_source, "KdrgSearchService" in adapter_source, True)
    check("E08 adapter X04 family 분리", "source_adrg_families" in adapter_source, "source_adrg_families" in adapter_source, True)
    # 변수명 자체가 아니라 실제 동작 계약을 검사한다. 41번 V7 smoke는
    # diagnosis_fixture가 아니라 diagnosis_codes/dotted_code를 사용하므로
    # 특정 내부 변수명 고정 검사는 정상 구현을 오탐할 수 있다.
    smoke_dynamic_contract = {
        "corpus_code_index": "_code_types_by_code" in smoke_source,
        "diagnosis_type_filter": "상병코드" in smoke_source,
        "deterministic_sort": "sorted(" in smoke_source,
        "dotted_query_build": bool(re.search(r"\bdotted_query\s*=", smoke_source)),
        "empty_result_guard": "bool(dotted_rows)" in smoke_source,
        "legacy_A000_fixture_absent": '"A000"' not in smoke_source and "'A000'" not in smoke_source,
    }
    check(
        "E09 smoke dynamic fixture",
        all(smoke_dynamic_contract.values()),
        smoke_dynamic_contract,
        {key: True for key in smoke_dynamic_contract},
    )

    # dialogs.py도 runtime_counts/runtime_status라는 특정 변수명을 강제하지 않는다.
    # 실제 구현처럼 store의 전체 corpus를 len(...)으로 직접 집계하는 방식도
    # 동일한 동적 runtime 계약으로 인정한다.
    dialog_named_runtime = "runtime_counts" in dialog_source or "runtime_status" in dialog_source
    dialog_direct_runtime = all(
        token in dialog_source
        for token in ("len(store.rules)", "len(store.tables)", "len(store.code_to_tables)")
    )
    dialog_runtime_contract = {
        "named_runtime_status": dialog_named_runtime,
        "direct_store_counts": dialog_direct_runtime,
        "runtime_scope_label": "전체 runtime 데이터 범위" in dialog_source or "검색 코드" in dialog_source,
    }
    check(
        "E10 dialogs runtime count",
        (dialog_named_runtime or dialog_direct_runtime) and dialog_runtime_contract["runtime_scope_label"],
        dialog_runtime_contract,
        "named runtime status 또는 direct store counts + runtime scope label",
    )

    shim_names = sorted(path.name for path in SHIM.iterdir() if path.is_file() or path.is_symlink()) if SHIM.exists() else []
    check("E11 native shim 존재", SHIM.exists(), str(SHIM), "exists")
    check("E12 shim glibc core 없음", not (set(shim_names) & GLIBC_CORE), sorted(set(shim_names) & GLIBC_CORE), [])
    check("E13 libEGL shim", "libEGL.so.1" in shim_names, "libEGL.so.1" in shim_names, True)
    check("E14 libGL shim", "libGL.so.1" in shim_names, "libGL.so.1" in shim_names, True)

    from PySide6.QtWidgets import QApplication, QComboBox, QLineEdit  # noqa: PLC0415
    from app.main_window import MainWindow  # noqa: PLC0415

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    app.processEvents()

    # MainWindow의 실제 공개 계약을 기준으로 위젯을 찾는다.
    # 과거 검증기처럼 존재하지 않는 search_input을 고정 가정하지 않고,
    # Python 속성과 Qt objectName을 함께 확인해 같은 유형의 회귀를 전부 차단한다.
    search_widget = getattr(window, "search_edit", None)
    if not isinstance(search_widget, QLineEdit):
        search_widget = window.findChild(QLineEdit, "SearchEdit")

    category_widget = getattr(window, "category_combo", None)
    if not isinstance(category_widget, QComboBox):
        category_widget = window.findChild(QComboBox, "SearchCombo")

    run_search_handler = getattr(window, "run_search", None)
    ui_contract_ready = (
        isinstance(search_widget, QLineEdit)
        and isinstance(category_widget, QComboBox)
        and callable(run_search_handler)
    )

    category_items = (
        [category_widget.itemText(i) for i in range(category_widget.count())]
        if isinstance(category_widget, QComboBox)
        else []
    )

    def execute_ui_search(query: str, category: str) -> list:
        if not ui_contract_ready:
            return []
        search_widget.setText(query)
        category_widget.setCurrentText(category)
        run_search_handler()
        app.processEvents()
        return list(getattr(window, "current_results", []) or [])

    check("E15 MainWindow runtime store", isinstance(window.store, KDRGRuntimeDataStore), type(window.store).__name__, "KDRGRuntimeDataStore")
    check("E16 MainWindow 결과 bounded", 1 <= len(window.current_results) <= 200, len(window.current_results), "1..200")
    check("E17 MainWindow E011 선택", bool(window.selected_result and window.selected_result.key == "E011"), getattr(window.selected_result, "key", None), "E011")
    check("E18 MainWindow RDRG category", "RDRG" in category_items, category_items, "contains RDRG")
    check("E19 MainWindow 전체 category", "전체" in category_items, category_items, "contains 전체")
    status_text = window.statusBar().currentMessage()

    # UI 숫자는 16,571처럼 천 단위 쉼표가 있거나 16571처럼 표시될 수 있다.
    # 표시 형식이 아니라 label과 실제 수치의 의미를 비교한다.
    status_compact = re.sub(r"[\s,]", "", status_text)
    status_count_contract = {
        "ADRG": "ADRG1132개" in status_compact,
        "TABLE": "TABLE1308개" in status_compact,
        "CODE": "검색코드16571개" in status_compact,
    }
    check("E20 상태표시줄 ADRG count", status_count_contract["ADRG"], status_text, "contains ADRG 1,132개 또는 ADRG 1132개")
    check("E21 상태표시줄 TABLE count", status_count_contract["TABLE"], status_text, "contains TABLE 1,308개 또는 TABLE 1308개")
    check("E22 상태표시줄 CODE count", status_count_contract["CODE"], status_text, "contains 검색코드 16,571개 또는 검색코드 16571개")

    adrg_ui_rows = execute_ui_search(adrg_fixture, "ADRG")
    check(
        "E23 UI ADRG 검색 결과",
        bool(adrg_ui_rows) and adrg_ui_rows[0].key == adrg_fixture,
        {
            "ui_contract_ready": ui_contract_ready,
            "search_widget": type(search_widget).__name__ if search_widget is not None else None,
            "category_widget": type(category_widget).__name__ if category_widget is not None else None,
            "result": _result_head(adrg_ui_rows),
        },
        adrg_fixture,
    )

    code_category = diagnosis_category if diagnosis_category in category_items else "전체"
    dotted_ui_rows = execute_ui_search(dotted_query(diagnosis_fixture), code_category)
    check(
        "E24 UI dotted CODE 검색",
        bool(dotted_ui_rows) and normalize(dotted_ui_rows[0].key) == normalize(diagnosis_fixture),
        {
            "ui_contract_ready": ui_contract_ready,
            "query": dotted_query(diagnosis_fixture),
            "category": code_category,
            "result": _result_head(dotted_ui_rows),
        },
        diagnosis_fixture,
    )

    table_ui_rows = execute_ui_search(table_fixture, "TABLE")
    check(
        "E25 UI TABLE 검색",
        bool(table_ui_rows) and table_ui_rows[0].key == table_fixture,
        {
            "ui_contract_ready": ui_contract_ready,
            "result": _result_head(table_ui_rows),
        },
        table_fixture,
    )
    window.close()
    app.processEvents()

    # 6. 불변성
    source_hashes_after = {str(path.relative_to(ROOT)): sha256(path) for path in required if path.is_file()}
    check("F01 통합 JSON 불변", source_hashes_after[str(DATA_JSON.relative_to(ROOT))] == source_hashes_before[str(DATA_JSON.relative_to(ROOT))], source_hashes_after[str(DATA_JSON.relative_to(ROOT))], source_hashes_before[str(DATA_JSON.relative_to(ROOT))])
    check("F02 runtime service 불변", source_hashes_after[str(SERVICE.relative_to(ROOT))] == source_hashes_before[str(SERVICE.relative_to(ROOT))], source_hashes_after[str(SERVICE.relative_to(ROOT))], source_hashes_before[str(SERVICE.relative_to(ROOT))])
    check("F03 runtime adapter 불변", source_hashes_after[str(ADAPTER.relative_to(ROOT))] == source_hashes_before[str(ADAPTER.relative_to(ROOT))], source_hashes_after[str(ADAPTER.relative_to(ROOT))], source_hashes_before[str(ADAPTER.relative_to(ROOT))])
    check("F04 main_window 불변", source_hashes_after[str(MAIN_WINDOW.relative_to(ROOT))] == source_hashes_before[str(MAIN_WINDOW.relative_to(ROOT))], source_hashes_after[str(MAIN_WINDOW.relative_to(ROOT))], source_hashes_before[str(MAIN_WINDOW.relative_to(ROOT))])
    check("F05 dialogs 불변", source_hashes_after[str(DIALOGS.relative_to(ROOT))] == source_hashes_before[str(DIALOGS.relative_to(ROOT))], source_hashes_after[str(DIALOGS.relative_to(ROOT))], source_hashes_before[str(DIALOGS.relative_to(ROOT))])

    pass_count = sum(item["status"] == "PASS" for item in checks)
    fail_count = len(checks) - pass_count
    report = {
        "script_version": SCRIPT_VERSION,
        "validated_at": generated_at,
        "native_bootstrap": {
            "marker": os.environ.get(NATIVE_BOOTSTRAP_MARKER) == "1",
            "shim": str(SHIM),
            "ld_library_path": os.environ.get("LD_LIBRARY_PATH", ""),
            "qt_platform": os.environ.get("QT_QPA_PLATFORM", ""),
        },
        "source_hashes": source_hashes_before,
        "counts": {
            "adrg": len(adrg_rows),
            "aadrg": len(aadrg_rows),
            "rdrg": len(rdrg_rows),
            "tables": len(table_rows),
            "asts": len(ast_rows),
            "codes": len(code_rows),
            "expanded_tables": len(expanded_tables),
            "expanded_codes": len(expanded_codes),
            "positive_relation_keys": len(expected_positive),
            "negative_relation_keys": len(expected_negative),
        },
        "dynamic_fixtures": {
            "adrg": adrg_fixture,
            "aadrg": aadrg_fixture,
            "rdrg": rdrg_fixture,
            "table": table_fixture,
            "diagnosis_code": diagnosis_fixture,
            "diagnosis_query": dotted_query(diagnosis_fixture),
            "diagnosis_category": diagnosis_category,
        },
        "full_corpus_mismatches": {
            "code_to_table": len(code_table_mismatch),
            "code_relation_summary": len(code_relation_mismatch),
            "table_codes": len(table_code_mismatch),
            "table_code_count": len(table_member_count_mismatch),
            "table_relation_summary": len(table_relation_mismatch),
            "rule_metadata": len(rule_metadata_mismatch),
            "aadrg_mapping": len(mapping_mismatch),
            "positive_relation_index": _map_diff_count(actual_positive, expected_positive),
            "negative_relation_index": _map_diff_count(actual_negative, expected_negative),
        },
        "validation": {
            "status": "PASS" if fail_count == 0 else "FAIL",
            "pass_count": pass_count,
            "fail_count": fail_count,
            "total_count": len(checks),
            "checks": checks,
            "user_judgment_required": 0,
            "manual_excel_review": False,
        },
    }
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT_TXT.write_text(render(report, failures), encoding="utf-8")

    status = report["validation"]["status"]
    print(
        f"[{'PASS' if status == 'PASS' else 'FAIL'}] PySide runtime UI bridge 독립 전수검증 "
        f"{'완료' if status == 'PASS' else '실패'}: {len(code_rows)} codes / {len(table_rows)} tables / "
        f"{pass_count} PASS / {fail_count} FAIL / 사용자 판단 0건"
    )
    print(f"report={REPORT_TXT}")
    return 0 if fail_count == 0 else 1


def _compile_ok(path: Path) -> bool:
    try:
        py_compile.compile(str(path), cfile=str(ROOT / "reports" / f".{path.name}.pyc"), doraise=True)
        return True
    except Exception:
        return False


def _map_diff_count(left: dict[str, list[str]], right: dict[str, list[str]]) -> int:
    keys = set(left) | set(right)
    return sum(list(left.get(key) or []) != list(right.get(key) or []) for key in keys)


def _result_head(rows: list[Any]) -> Any:
    if not rows:
        return []
    row = rows[0]
    return {"kind": getattr(row, "kind", None), "key": getattr(row, "key", None), "label": getattr(row, "label", None)}


def render(report: dict[str, Any], failures: list[str]) -> str:
    validation = report["validation"]
    counts = report["counts"]
    fixtures = report["dynamic_fixtures"]
    mismatch = report["full_corpus_mismatches"]
    lines = [
        "KDRG V4.7 PySide runtime UI bridge 독립 전수검증 결과",
        "=" * 72,
        f"검증시각: {report['validated_at']}",
        f"검증 스크립트 버전: {report['script_version']}",
        "",
        "[현재 진행 위치]",
        "최종 통합 JSON V2·runtime service·PySide runtime bridge 구축 완료 후 UI 연결을 독립검증함",
        "runtime adapter의 내부 계산을 기대값으로 사용하지 않고 통합 JSON·AST에서 관계를 별도 재구성함",
        "검증기는 PySide import 전에 격리 shim 환경으로 self re-exec하며 통합 JSON·service·adapter·UI 파일은 수정하지 않음",
        "",
        "[전체 corpus 독립 재구성]",
        f"ADRG/AADRG/RDRG: {counts['adrg']} / {counts['aadrg']} / {counts['rdrg']}",
        f"TABLE/AST/CODE: {counts['tables']} / {counts['asts']} / {counts['codes']}",
        f"runtime 확장 TABLE/CODE: {counts['expanded_tables']} / {counts['expanded_codes']}",
        f"긍정/제외 semantic TABLE key: {counts['positive_relation_keys']} / {counts['negative_relation_keys']}",
        "",
        "[adapter 전수 대조]",
        f"CODE→TABLE 불일치: {mismatch['code_to_table']}",
        f"CODE 관계요약 불일치: {mismatch['code_relation_summary']}",
        f"TABLE code 배열 불일치: {mismatch['table_codes']}",
        f"TABLE code_count 불일치: {mismatch['table_code_count']}",
        f"TABLE 관계요약 불일치: {mismatch['table_relation_summary']}",
        f"Rule metadata 불일치: {mismatch['rule_metadata']}",
        f"AADRG mapping 불일치: {mismatch['aadrg_mapping']}",
        f"긍정/제외 relation index 불일치: {mismatch['positive_relation_index']} / {mismatch['negative_relation_index']}",
        "",
        "[동적 검색 fixture]",
        f"ADRG/AADRG/RDRG: {fixtures['adrg']} / {fixtures['aadrg']} / {fixtures['rdrg']}",
        f"TABLE: {fixtures['table']}",
        f"CODE: {fixtures['diagnosis_code']} → query {fixtures['diagnosis_query']} ({fixtures['diagnosis_category']})",
        "특정 코드 존재를 고정 가정하지 않고 현재 corpus에서 결정론적으로 선택함",
        "",
        "[UI·native 실행검증]",
        "PySide native shim은 41번 V7 산출물을 사용하고 self re-exec로 프로세스 시작 시점부터 적용함",
        "QApplication offscreen에서 MainWindow를 실제 생성하고 ADRG·CODE·TABLE 검색 이벤트를 실행함",
        "physical source / condition usage / runtime related / family provenance 표시 계약을 검사함",
        "",
        "[검증 항목 집계]",
        f"PASS: {validation['pass_count']}",
        f"FAIL: {validation['fail_count']}",
        f"TOTAL: {validation['total_count']}",
        "사용자 판단 필요: 0",
        "사용자 수동 Excel 검토: 없음",
        "",
        "[생성 파일]",
        str(REPORT_TXT),
        str(REPORT_JSON),
        "",
        "[다음 단계]",
        "독립검증 PASS 후 전체 UI preview·Windows exe 회귀검증용 실행 구성을 구축함",
        "Windows 배포에서는 Replit 전용 qt_native_shim을 포함하지 않고 PyInstaller Windows 의존성을 별도로 검증함",
        "",
        "[최종 결과]",
        f"전체 결과: {validation['status']}",
    ]
    if failures:
        lines.extend(["", "[FAIL 상세]"])
        lines.extend(f"- {item}" for item in failures)
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    try:
        bootstrap_qt_native_process()
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("[FAIL] 사용자 중단")
        raise SystemExit(130)
    except Exception as exc:
        REPORT_TXT.parent.mkdir(parents=True, exist_ok=True)
        text = (
            "KDRG V4.7 PySide runtime UI bridge 독립 전수검증 결과\n"
            + "=" * 72
            + f"\n검증 스크립트 버전: {SCRIPT_VERSION}\n\n[최종 결과]\n전체 결과: FAIL\n\n[FAIL 상세]\n- {type(exc).__name__}: {exc}\n"
        )
        REPORT_TXT.write_text(text, encoding="utf-8")
        print(f"[FAIL] PySide runtime UI bridge 독립 전수검증 예외: {type(exc).__name__}: {exc}")
        print(f"report={REPORT_TXT}")
        raise SystemExit(1)
