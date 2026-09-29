# -*- coding: utf-8 -*-
"""Windows 실행 전 정적 검증 스크립트.

실행
    python tests/verify_release_readiness.py

실제 Windows exe를 실행하지 않고도 다음을 점검합니다.
- main.py 존재
- app 모듈 import 가능
- data JSON 포함 및 로딩 가능
- 파일럿 9개 ADRG 존재
- E011 기본 선택
- 코드 검색 동작
- 관계검색 동작(O1311+O1326 AND → E011 분산)
- 뒤로가기 함수(go_back) 존재
- PyInstaller 결과 exe 존재 (dist/ 폴더, 빌드 후에만 통과)
- sources/raw, legacy_reference가 exe 번들 대상(datas)에 없음
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Windows 콘솔 기본 인코딩(cp1252)에서도 한글 출력이 깨지지 않도록 강제 UTF-8 설정
for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name, None)
    if _stream is not None and hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "[PASS]" if condition else "[FAIL]"
    print(f"{status} {label}" + (f" - {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(label)


def main() -> int:
    import version

    # 1. main.py 존재
    main_py = ROOT / "main.py"
    check("main.py 존재", main_py.exists())

    # 2. app 모듈 import 가능
    try:
        from app.main_window import MainWindow  # noqa: F401
        from app.data_store import KDRGDataStore

        app_import_ok = True
    except Exception as exc:  # noqa: BLE001
        app_import_ok = False
        print(f"       import 오류: {exc}")
    check("app 모듈 import 가능", app_import_ok)

    # 3. data JSON 포함 및 로딩 가능
    data_path = ROOT / "data" / "kdrg_v47_ui_fixture.json"
    check("data/kdrg_v47_ui_fixture.json 포함", data_path.exists())
    fixture = None
    if data_path.exists():
        try:
            fixture = json.loads(data_path.read_text(encoding="utf-8"))
            json_ok = True
        except Exception as exc:  # noqa: BLE001
            json_ok = False
            print(f"       JSON 로딩 오류: {exc}")
        check("data JSON 로딩 가능", json_ok)
    else:
        check("data JSON 로딩 가능", False)

    # 4. 파일럿 9개 ADRG 존재
    expected_adrgs = {"E011", "E501", "E502", "E511", "E512", "F022", "F136", "F194", "F195"}
    if fixture is not None:
        actual_adrgs = {rule.get("adrg") for rule in fixture.get("rules", [])}
        check(
            "파일럿 9개 ADRG 존재",
            expected_adrgs.issubset(actual_adrgs),
            f"expected={sorted(expected_adrgs)} actual={sorted(actual_adrgs)}",
        )
    else:
        check("파일럿 9개 ADRG 존재", False)

    # 5~8. GUI 동작 (offscreen)
    if app_import_ok:
        import os

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtWidgets import QApplication

            qt_app = QApplication.instance() or QApplication([])
            window = MainWindow()

            check(
                "E011 기본 선택",
                bool(window.selected_result) and window.selected_result.key == "E011",
            )

            window.search_edit.setText("E0110")
            window.category_combo.setCurrentText("전체")
            window.run_search()
            check("코드 검색 동작", len(window.current_results) > 0)

            window.advanced_toggle.setChecked(True)
            window.advanced_rows[0].type_combo.setCurrentText("수술·처치코드")
            window.advanced_rows[0].code_edit.setText("O1311")
            window.advanced_rows[1].type_combo.setCurrentText("수술·처치코드")
            window.advanced_rows[1].code_edit.setText("O1326")
            window.relation_operator_combo.setCurrentText("AND")
            window.run_relation_search()
            candidate = window.relation_candidates.get("E011")
            check(
                "관계검색 동작(E011 분산 판정)",
                candidate is not None and candidate.relation_level == "split",
            )

            check("뒤로가기 함수(go_back) 존재", hasattr(window, "go_back") and callable(window.go_back))
        except Exception as exc:  # noqa: BLE001
            check("GUI 동작 검증", False, str(exc))
    else:
        check("GUI 동작 검증", False, "app 모듈 import 실패로 건너뜀")

    # 9. PyInstaller 결과 exe 존재 (빌드 후에만 유효 - 없으면 경고만 남기고 계속 진행)
    dist_dir = ROOT / "dist"
    exe_path = dist_dir / version.EXE_NAME
    exe_exists = exe_path.exists()
    if exe_exists:
        size_mb = exe_path.stat().st_size / (1024 * 1024)
        check("PyInstaller 결과 exe 존재", True, f"{exe_path} ({size_mb:.1f} MB)")
        check("exe 크기가 비정상적으로 작지 않음(30MB 이상)", size_mb >= 30, f"{size_mb:.1f} MB")
    else:
        print(f"[정보] {exe_path} 이(가) 아직 없습니다. 빌드 전 단계라면 정상입니다.")

    # 10. sources/raw, legacy_reference가 exe 번들 대상에서 제외됨
    spec_text = (ROOT / "kdrg.spec").read_text(encoding="utf-8")
    check(
        "sources/raw가 kdrg.spec datas에 없음",
        "sources/raw" not in spec_text and "sources\\\\raw" not in spec_text,
    )
    check(
        "legacy_reference가 kdrg.spec datas에 없음",
        "legacy_reference" not in spec_text,
    )

    print()
    if FAILURES:
        print(f"[실패 {len(FAILURES)}건] " + ", ".join(FAILURES))
        return 1
    print("[통과] 모든 정적 검증 항목을 통과했습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
