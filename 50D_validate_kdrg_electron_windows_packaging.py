from __future__ import annotations

import hashlib
import json
import os
import py_compile
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

SCRIPT_VERSION = "2026-07-27_KDRG_V47_ELECTRON_STAGE50D_VALIDATOR_V1"
ROOT = Path(__file__).resolve().parent
ELECTRON = ROOT / "electron"
REPORT_DIR = ROOT / "reports"
REPORT_TXT = REPORT_DIR / "electron_stage50d_validation_report.txt"
REPORT_JSON = REPORT_DIR / "electron_stage50d_validation_report.json"

PROTECTED_HASHES = {'data/kdrg_v47_search_integrated.json': '3de5d6d95cd9cbd16e674f5a4cffcd8bf89da2ee70627501f56d81b05bbe8af1', 'data/kdrg_v47_ui_semantic_profile.json': 'c9401fd9d6dcc1253fa2134b22048fe4a73c4c04aeea4d1d86c7fe1504d5456e', 'data/kdrg_v47_ui_display_contract.json': '9976307acd77bb6a0c8a48b2788d055faf563d497381b2c2cacfc7435df0f1ac', 'app/kdrg_search_service.py': '35766cfd10b887c9852536a2165d6719e20c5ad2791a5d1a0d0166d7b94cb6cd', 'app/runtime_data_store.py': 'e2d5bf1de4c9697f84e30f9e8ec9664abf9cda0acddb392620c3a7b71f28d48d', 'app/main_window.py': '291b4f76d389b24695ebe2b180b1cd4a729a8978af758dd279656c67ac5df242', 'tests/windows_runtime_source_smoke.py': '5fc535d44956e4e5efef3e4356c5f8629954b5a9e60bf6d912987257629fc907', 'version.py': '2c30bcec8f896845e26f371297c75dde609a27df693059c9faab3d91b828506c', '.github/workflows/build-windows-release.yml': 'ccd5347a863c277841d5594b81f7471a8cffd9a16da36ff70d8c44d1e4556f9e', 'electron/preload.js': 'f20cc0a0694f2b365e9e5d67640ac8f3ecd23e86f15234e6614979bb9e4fb672', 'electron/src/data-paths.js': '27cca98bdf68a2d5d71210c36bcddc6068e413000be860b4e9a1a784a4f61316', 'electron/src/search-normalizer.js': 'f59ccccd3a380df450d934b8bdd322f71c906fc68e69caa293e500d7f355d65e', 'electron/src/search-result-contract.js': 'cf979434aace8fde78c28130901295a2fb8e48049f5ef1ca4b69779cb5c48082', 'electron/src/kdrg-search-service.js': 'acecdeb55267341e7570e3f1c60a97f4f9abf9c74fb2c31ae2d64b84c48baad8', 'electron/renderer/index.html': 'd48516ee6a5b09db8c83d7155f5b2ee1c72a0919ca5a6ac6ed8ba149ad25552f', 'electron/renderer/app.js': '43ea2db9431da87de40d72bd8eec373663f07fc8e986afecb212ee56e40790ce', 'electron/renderer/styles.css': '275137e8f05bb78de982f0cf777db4e14b2a2aab702d6afb310062f79afe4c76', 'electron/renderer/ui-formatters.js': '64f123958450a0f6081a1ecb0ac7b5b434f459e4e50b1685c5a35248b4630944', 'electron/tests/run-search-parity.js': '9da5b1529c60f4ea3a7a0507e9a6a796cff3b60e52acd39aef3fd176c980b223', 'electron/tests/validate-renderer-ui.js': '33a915a61cccdd0e4c716f4cd5f5b9c815bced6481dde7f4d8a37be2eeb6ae6f', 'electron/README_STAGE50A.md': 'bdf76fc3075e4ab0d2eec90e144bc4b221e6dd0e0275db2e21a7b299fbe7e886', 'electron/README_STAGE50B.md': '09dc1a57af65ee56121abc18158c4250cda6af258e7360596ce5f6c7cdfd320f', 'electron/README_STAGE50C.md': '35f92d8bd42649ee7bdb651979626235517ea06a3a185bae3128b2b212e0478f'}
TARGET_HASHES = {'50B_validate_kdrg_electron_search_service.py': '5b572166733af104a70d717f16bf777829b97229f735c3ef0b417d5bcd51c4ea', '50C_validate_kdrg_electron_renderer_ui.py': 'd40e700a607f43f64526f4b85ecd5b43c2c32d1f9511e2b813404f5297e8834f', 'electron/package.json': '37e6f5d39e88ea27a07d7712d71a307801245df0f6de3fd7d0cef5359ce1be6c', 'electron/main.js': '56d5dd8fce986e2883d58ab3f39aaba160dc05d98dc95a74409487fb0c61c208', 'electron/src/bootstrap-data.js': 'de31415aa829254a6e915f8f75cf845965073735712d74604502a9e431ff840c', 'electron/src/packaged-runtime-smoke.js': '4b9b26f56783008b2127e34ac2e653e70776a227501a8d1d4f5c1286d0e3ee30', 'electron/tests/validate-packaging-config.js': 'ab8d3cc0862bcf68c3fd1fd610871093a6bff67a91c4b10b372b853b49168098', 'electron/scripts/verify-windows-portable.ps1': '63c98bbd22a4358f0d9954e702686a03590180f03b254f1909508da9b8916500', '.github/workflows/build-electron-windows.yml': 'b439d1e520bd21df84c307dba15d6eb70d3c9f77af19e3b5b5298455518c9cde', 'electron/README_STAGE50D.md': '775cca931043435d0f7696fcd025d0899f3bd79e52da0739588c3171d589c33a', 'electron/tests/validate-electron-skeleton.js': '223680c321fd582f5e4a1641236a673639e41aca3f2ca74ed80f46a0f6394fd0', 'electron/tests/validate-search-service.js': '60a55ea14bc2250d102bf952073736ff8208ee871a893996482d571f18df3d05'}

JS_CHECK_FILES = (
    "electron/main.js",
    "electron/preload.js",
    "electron/src/data-paths.js",
    "electron/src/bootstrap-data.js",
    "electron/src/search-normalizer.js",
    "electron/src/search-result-contract.js",
    "electron/src/kdrg-search-service.js",
    "electron/src/packaged-runtime-smoke.js",
    "electron/renderer/ui-formatters.js",
    "electron/renderer/app.js",
    "electron/tests/validate-electron-skeleton.js",
    "electron/tests/validate-search-service.js",
    "electron/tests/run-search-parity.js",
    "electron/tests/validate-renderer-ui.js",
    "electron/tests/validate-packaging-config.js",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_command(args: list[str], cwd: Path) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            args,
            cwd=cwd,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as exc:
        return {"returncode": 127, "stdout": "", "stderr": f"{type(exc).__name__}: {exc}"}
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def locate_node() -> Path | None:
    candidates: list[Path] = []
    explicit = os.environ.get("KDRG_NODE_BIN", "").strip()
    if explicit:
        candidates.append(Path(explicit))
    candidates.extend(
        [
            ROOT.parent / ".cache/kdrg-stage50a-node-v22/current/bin/node",
            Path("/home/runner/.cache/kdrg-stage50a-node-v22/current/bin/node"),
            Path.home() / ".cache/kdrg-stage50a-node-v22/current/bin/node",
        ]
    )
    for name in ("node", "nodejs"):
        found = shutil.which(name)
        if found:
            candidates.append(Path(found))

    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate.resolve(strict=False))
        if key in seen or not candidate.exists():
            continue
        seen.add(key)
        result = run_command([str(candidate), "--version"], ROOT)
        if result["returncode"] != 0:
            continue
        try:
            major = int(result["stdout"].lstrip("v").split(".", 1)[0])
        except ValueError:
            continue
        if major >= 22:
            os.environ["KDRG_NODE_BIN"] = str(candidate)
            os.environ["PATH"] = f"{candidate.parent}{os.pathsep}{os.environ.get('PATH', '')}"
            return candidate
    return None


def write_report(checks: list[dict[str, Any]], outputs: dict[str, dict[str, Any]]) -> int:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    failures = [item for item in checks if not item["passed"]]
    pass_count = len(checks) - len(failures)
    lines = [
        "KDRG V4.7 Stage 50D Electron Windows packaging 독립검증",
        "=" * 78,
        f"스크립트 버전: {SCRIPT_VERSION}",
        "",
        "[검증 항목]",
    ]
    for item in checks:
        marker = "PASS" if item["passed"] else "FAIL"
        lines.append(
            f"- [{marker}] {item['name']} | actual={item['actual']} | expected={item['expected']}"
        )
    for name, result in outputs.items():
        lines.extend(
            [
                "",
                f"[{name} stdout]",
                result.get("stdout", ""),
                "",
                f"[{name} stderr]",
                result.get("stderr", ""),
            ]
        )
    lines.extend(
        [
            "",
            "[최종 결과]",
            f"PASS: {pass_count}",
            f"FAIL: {len(failures)}",
            f"TOTAL: {len(checks)}",
            f"전체 결과: {'PASS' if not failures else 'FAIL'}",
        ]
    )
    REPORT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    REPORT_JSON.write_text(
        json.dumps(
            {
                "script_version": SCRIPT_VERSION,
                "status": "PASS" if not failures else "FAIL",
                "pass": pass_count,
                "fail": len(failures),
                "total": len(checks),
                "checks": checks,
                "outputs": outputs,
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    if failures:
        print(
            f"[FAIL] KDRG Stage 50D Electron Windows packaging 검증: "
            f"{pass_count} PASS / {len(failures)} FAIL"
        )
        print("[FAIL 상세]")
        for item in failures:
            print(
                f"- {item['name']} | actual={item['actual']} | expected={item['expected']}"
            )
        print(f"report={REPORT_TXT}")
        return 1
    print(
        f"[PASS] KDRG Stage 50D Electron Windows packaging 검증: "
        f"{pass_count} PASS / 0 FAIL"
    )
    print(f"report={REPORT_TXT}")
    return 0


def main() -> int:
    checks: list[dict[str, Any]] = []
    outputs: dict[str, dict[str, Any]] = {}

    def check(name: str, actual: Any, expected: Any, predicate=None) -> bool:
        passed = predicate(actual, expected) if predicate else actual == expected
        checks.append({
            "name": name,
            "actual": actual,
            "expected": expected,
            "passed": bool(passed),
        })
        return bool(passed)

    for relative, expected_hash in PROTECTED_HASHES.items():
        path = ROOT / relative
        check(f"보호 파일 존재 {relative}", path.exists(), True)
        if path.exists():
            check(f"보호 파일 SHA256 {relative}", sha256_file(path), expected_hash)

    for relative, expected_hash in TARGET_HASHES.items():
        path = ROOT / relative
        check(f"50D 파일 존재 {relative}", path.exists(), True)
        if path.exists():
            check(f"50D 파일 SHA256 {relative}", sha256_file(path), expected_hash)

    lock_path = ELECTRON / "package-lock.json"
    check("package-lock 존재", lock_path.exists(), True)
    if lock_path.exists():
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        package = json.loads((ELECTRON / "package.json").read_text(encoding="utf-8"))
        check("package-lock lockfileVersion", lock.get("lockfileVersion"), 3)
        check("package-lock root name", lock.get("name"), package.get("name"))
        check("package-lock root version", lock.get("version"), package.get("version"))
        check(
            "package-lock root Electron pin",
            lock.get("packages", {}).get("", {}).get("devDependencies", {}).get("electron"),
            "43.2.0",
        )
        check(
            "package-lock root electron-builder pin",
            lock.get("packages", {}).get("", {}).get("devDependencies", {}).get("electron-builder"),
            "26.15.3",
        )
        check(
            "package-lock resolved Electron",
            lock.get("packages", {}).get("node_modules/electron", {}).get("version"),
            "43.2.0",
        )
        check(
            "package-lock resolved electron-builder",
            lock.get("packages", {}).get("node_modules/electron-builder", {}).get("version"),
            "26.15.3",
        )
        check(
            "package-lock 실제 dependency graph",
            len(lock.get("packages", {})),
            ">= 50",
            lambda value, _expected: value >= 50,
        )
        check("package-lock SHA256 기록가능", len(sha256_file(lock_path)), 64)

    for relative in (
        "50B_validate_kdrg_electron_search_service.py",
        "50C_validate_kdrg_electron_renderer_ui.py",
        "50D_validate_kdrg_electron_windows_packaging.py",
    ):
        try:
            py_compile.compile(str(ROOT / relative), doraise=True)
            check(f"py_compile {relative}", "PASS", "PASS")
        except Exception as exc:
            check(f"py_compile {relative}", f"{type(exc).__name__}: {exc}", "PASS")

    node = locate_node()
    check("Node v22 실행환경", str(node) if node else None, "available", lambda value, _expected: bool(value))
    if node:
        for relative in JS_CHECK_FILES:
            result = run_command([str(node), "--check", str(ROOT / relative)], ROOT)
            check(f"node --check {relative}", result["returncode"], 0)

        command_specs = {
            "Stage 50D packaging Node 검증": (
                [str(node), "tests/validate-packaging-config.js"],
                ELECTRON,
                "Electron Stage 50D Windows packaging 검증",
            ),
            "Stage 50C renderer UI 회귀검증": (
                [str(node), "tests/validate-renderer-ui.js"],
                ELECTRON,
                "105 PASS / 0 FAIL",
            ),
            "Stage 50C 검색 service 회귀검증": (
                [str(node), "tests/validate-search-service.js"],
                ELECTRON,
                "78 PASS / 0 FAIL",
            ),
            "Stage 50C 보안 골격 회귀검증": (
                [str(node), "tests/validate-electron-skeleton.js"],
                ELECTRON,
                "PASS / 0 FAIL",
            ),
            "Stage 50C Python 전체 회귀검증": (
                [sys.executable, "50C_validate_kdrg_electron_renderer_ui.py"],
                ROOT,
                "85 PASS / 0 FAIL",
            ),
        }
        for name, (args, cwd, marker) in command_specs.items():
            result = run_command(args, cwd)
            outputs[name] = result
            check(
                name,
                {
                    "returncode": result["returncode"],
                    "stdout": result["stdout"],
                    "stderr": result["stderr"],
                },
                f"returncode=0 and {marker}",
                lambda value, _expected, marker=marker: (
                    value["returncode"] == 0 and marker in value["stdout"]
                ),
            )

    package = json.loads((ELECTRON / "package.json").read_text(encoding="utf-8"))
    check("Electron pin", package.get("devDependencies", {}).get("electron"), "43.2.0")
    check("electron-builder pin", package.get("devDependencies", {}).get("electron-builder"), "26.15.3")
    check("dist:win script", package.get("scripts", {}).get("dist:win"), "electron-builder --win portable --x64 --publish never")
    check("build portable target", package.get("build", {}).get("win", {}).get("target", [{}])[0].get("target"), "portable")
    check("build asar", package.get("build", {}).get("asar"), True)
    check("extraResources 수", len(package.get("build", {}).get("extraResources", [])), 3)

    workflow = (ROOT / ".github/workflows/build-electron-windows.yml").read_text(encoding="utf-8")
    check("Electron workflow manual 실행", "workflow_dispatch" in workflow, True)
    check("Electron workflow 태그 분리", 'electron-v*' in workflow, True)
    check("PySide 태그와 비충돌", '"v*.*.*"' in (ROOT / ".github/workflows/build-windows-release.yml").read_text(encoding="utf-8"), True)
    check("Actions artifact 미사용", "actions/upload-artifact" in workflow, False)
    check("Release Assets 사용", "softprops/action-gh-release@v2" in workflow, True)
    check("packaged smoke 사용", "verify-windows-portable.ps1" in workflow, True)

    check("node_modules 경로가 파일이 아님", (ELECTRON / "node_modules").is_file(), False)
    check("dist 경로가 파일이 아님", (ELECTRON / "dist").is_file(), False)

    return write_report(checks, outputs)


if __name__ == "__main__":
    raise SystemExit(main())
