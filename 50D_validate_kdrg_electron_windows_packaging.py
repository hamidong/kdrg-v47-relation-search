
from __future__ import annotations

import hashlib
import json
import os
import platform
import py_compile
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

SCRIPT_VERSION = "2026-07-30_KDRG_V47_ELECTRON_STAGE50D_VALIDATOR_V12_AGGREGATE_CONTRACT"
NODE_VERSION = "v22.23.1"

ROOT = Path(__file__).resolve().parent
ELECTRON = ROOT / "electron"
REPORT_DIR = ROOT / "reports"
REPORT_TXT = REPORT_DIR / "electron_stage50d_validation_report.txt"
REPORT_JSON = REPORT_DIR / "electron_stage50d_validation_report.json"

NODE_CACHE_DIR = REPORT_DIR / "electron_node_v22_cache"
NODE_CURRENT_DIR = NODE_CACHE_DIR / "current"

EXPECTED_WORKFLOW_HASH = "1e2cafc1c491c3da5989b2a4c9159e2eeb5e557426fda309c6408040aafaa899"
EXPECTED_LOCK_HASH = "cf64b4826ff5feabb81b257797492528f4cbdc5c30d1a008d1960b2f1c003f8c"

PROTECTED_HASHES = {
    "data/kdrg_v47_search_integrated.json":
        "3de5d6d95cd9cbd16e674f5a4cffcd8bf89da2ee70627501f56d81b05bbe8af1",
    "data/kdrg_v47_ui_semantic_profile.json":
        "c9401fd9d6dcc1253fa2134b22048fe4a73c4c04aeea4d1d86c7fe1504d5456e",
    "data/kdrg_v47_ui_display_contract.json":
        "9976307acd77bb6a0c8a48b2788d055faf563d497381b2c2cacfc7435df0f1ac",
    "app/kdrg_search_service.py":
        "35766cfd10b887c9852536a2165d6719e20c5ad2791a5d1a0d0166d7b94cb6cd",
    "app/runtime_data_store.py":
        "e2d5bf1de4c9697f84e30f9e8ec9664abf9cda0acddb392620c3a7b71f28d48d",
    "app/main_window.py":
        "291b4f76d389b24695ebe2b180b1cd4a729a8978af758dd279656c67ac5df242",
    "tests/windows_runtime_source_smoke.py":
        "5fc535d44956e4e5efef3e4356c5f8629954b5a9e60bf6d912987257629fc907",
    "version.py":
        "2c30bcec8f896845e26f371297c75dde609a27df693059c9faab3d91b828506c",
    ".github/workflows/build-windows-release.yml":
        "ccd5347a863c277841d5594b81f7471a8cffd9a16da36ff70d8c44d1e4556f9e",
    ".gitattributes":
        "6e91da75eb4141a20f8296dce65a413d1a08befbebc6ebf9f485fa036fa73ff8",
    "electron/package.json":
        "05bcd0f9466b822f863873113ff742be73889b0f0e2eb07f927eb300456c60b2",
    "electron/package-lock.json":
        "cf64b4826ff5feabb81b257797492528f4cbdc5c30d1a008d1960b2f1c003f8c",
    "electron/main.js":
        "56d5dd8fce986e2883d58ab3f39aaba160dc05d98dc95a74409487fb0c61c208",
    "electron/preload.js":
        "f20cc0a0694f2b365e9e5d67640ac8f3ecd23e86f15234e6614979bb9e4fb672",
    "electron/src/data-paths.js":
        "27cca98bdf68a2d5d71210c36bcddc6068e413000be860b4e9a1a784a4f61316",
    "electron/src/bootstrap-data.js":
        "de31415aa829254a6e915f8f75cf845965073735712d74604502a9e431ff840c",
    "electron/src/search-normalizer.js":
        "f59ccccd3a380df450d934b8bdd322f71c906fc68e69caa293e500d7f355d65e",
    "electron/src/search-result-contract.js":
        "cf979434aace8fde78c28130901295a2fb8e48049f5ef1ca4b69779cb5c48082",
    "electron/src/kdrg-search-service.js":
        "acecdeb55267341e7570e3f1c60a97f4f9abf9c74fb2c31ae2d64b84c48baad8",
    "electron/src/packaged-runtime-smoke.js":
        "0d433dda9fd966eec090a543d2ab9ea79dd6141cdc56db3a50b11a9b05d08c24",
    "electron/renderer/index.html":
        "d48516ee6a5b09db8c83d7155f5b2ee1c72a0919ca5a6ac6ed8ba149ad25552f",
    "electron/renderer/app.js":
        "43ea2db9431da87de40d72bd8eec373663f07fc8e986afecb212ee56e40790ce",
    "electron/renderer/styles.css":
        "275137e8f05bb78de982f0cf777db4e14b2a2aab702d6afb310062f79afe4c76",
    "electron/renderer/ui-formatters.js":
        "64f123958450a0f6081a1ecb0ac7b5b434f459e4e50b1685c5a35248b4630944",
    "electron/tests/run-search-parity.js":
        "9da5b1529c60f4ea3a7a0507e9a6a796cff3b60e52acd39aef3fd176c980b223",
    "electron/tests/validate-renderer-ui.js":
        "33a915a61cccdd0e4c716f4cd5f5b9c815bced6481dde7f4d8a37be2eeb6ae6f",
    "electron/tests/validate-electron-skeleton.js":
        "6048b5cf37bb31b8d2001231d2b79cf97a22880dbfc203e7b33ef62b3ac957c8",
    "electron/tests/validate-search-service.js":
        "60a55ea14bc2250d102bf952073736ff8208ee871a893996482d571f18df3d05",
    "electron/tests/validate-packaging-config.js":
        "4997a8e7a9095c4b95f9cbc20ba90bf37ea7c74153cd4129474e8d37730a166f",
    "electron/tests/validate-packaged-runtime-smoke.js":
        "a117af0918d8f0f71079df3725abd20710001bf70ad04cb81c246e8b6f2fe292",
    "electron/scripts/verify-windows-portable.ps1":
        "63c98bbd22a4358f0d9954e702686a03590180f03b254f1909508da9b8916500",
    "electron/scripts/validate-package-lock-registry.py":
        "ef5dfd00fc5acdb68243119b0d40b71689103c52e02f4ad5c1db7dc66b995d92",
    "electron/scripts/validate-checkout-byte-integrity.py":
        "382072fbd01e499e653f2ebfe7aa5776c26d901c9ee22f03552bb3ed9d67ab7a",
    "electron/README_STAGE50A.md":
        "bdf76fc3075e4ab0d2eec90e144bc4b221e6dd0e0275db2e21a7b299fbe7e886",
    "electron/README_STAGE50B.md":
        "09dc1a57af65ee56121abc18158c4250cda6af258e7360596ce5f6c7cdfd320f",
    "electron/README_STAGE50C.md":
        "35f92d8bd42649ee7bdb651979626235517ea06a3a185bae3128b2b212e0478f",
    "electron/README_STAGE50D.md":
        "adad88a75b3e2c3f20de83ffe3d5e086ca39cf8010d666a08527c18a7bb6cc26",
    "50B_validate_kdrg_electron_search_service.py":
        "5b572166733af104a70d717f16bf777829b97229f735c3ef0b417d5bcd51c4ea",
    "50C_validate_kdrg_electron_renderer_ui.py":
        "d37cf3a0b0806c92ef8120b6974b2430c8c93fea6caa6f7e5bbdc825276d2ae6",
}

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
    "electron/tests/validate-packaged-runtime-smoke.js",
    "electron/tests/validate-packaging-config.js",
)

EXPECTED_STEPS = (
    "체크아웃",
    "Node.js 22.23.1 설치",
    "Python 3.11 설치",
    "checkout 바이트 무결성 검증",
    "Actions 런타임 임시경로 초기화",
    "package-lock 공식 registry 사전검증",
    "npm CLI 11.17.0 무결성 검증 준비",
    "npm 잠금 의존성 설치",
    "Electron source·검색·UI·packaging 검증",
    "Stage 50D Python 독립검증",
    "Windows x64 portable exe 빌드",
    "portable exe 경로 확인",
    "packaged exe 데이터·검색·renderer 기동검증",
    "SHA256 생성",
    "Electron 버전 정보 추출",
    "Electron 태그와 package 버전 일치 확인",
    "회귀검증 요약",
    "GitHub Release 생성 및 Electron exe 업로드",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_command(args: list[str], cwd: Path = ROOT) -> dict[str, Any]:
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
        return {
            "returncode": 127,
            "stdout": "",
            "stderr": f"{type(exc).__name__}: {exc}",
        }
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def collect_resolved_urls(value: object) -> list[str]:
    urls: list[str] = []
    if isinstance(value, dict):
        resolved = value.get("resolved")
        if isinstance(resolved, str) and resolved.strip():
            urls.append(resolved.strip())
        for child in value.values():
            urls.extend(collect_resolved_urls(child))
    elif isinstance(value, list):
        for child in value:
            urls.extend(collect_resolved_urls(child))
    return urls


def node_version(node_path: Path) -> str | None:
    result = run_command([str(node_path), "--version"])
    if result["returncode"] != 0:
        return None
    return result["stdout"].strip()


def activate_node(node_path: Path) -> Path:
    os.environ["PATH"] = (
        f"{node_path.parent}{os.pathsep}{os.environ.get('PATH', '')}"
    )
    os.environ["KDRG_NODE_BIN"] = str(node_path)
    return node_path


def locate_node() -> Path | None:
    candidates: list[Path] = []
    explicit = os.environ.get("KDRG_NODE_BIN", "").strip()
    if explicit:
        candidates.append(Path(explicit))

    exe_name = "node.exe" if os.name == "nt" else "node"
    candidates.extend(
        [
            NODE_CURRENT_DIR / "bin/node",
            NODE_CURRENT_DIR / "node.exe",
            ROOT.parent / ".cache/kdrg-stage50a-node-v22/current/bin/node",
        ]
    )

    resolved = shutil.which(exe_name) or shutil.which("node")
    if resolved:
        candidates.append(Path(resolved))

    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate.resolve(strict=False))
        if key in seen or not candidate.is_file():
            continue
        seen.add(key)
        if node_version(candidate) == NODE_VERSION:
            return activate_node(candidate)
    return None


def download_file(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "KDRG-Stage50D-Validator/1.0"},
    )
    temporary = destination.with_suffix(destination.suffix + ".part")
    temporary.unlink(missing_ok=True)
    with urllib.request.urlopen(request, timeout=120) as response:
        with temporary.open("wb") as output:
            shutil.copyfileobj(response, output)
    temporary.replace(destination)


def expected_archive_hash(manifest_text: str, archive_name: str) -> str:
    for line in manifest_text.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and parts[-1].lstrip("*") == archive_name:
            digest = parts[0].lower()
            if re.fullmatch(r"[0-9a-f]{64}", digest):
                return digest
    raise RuntimeError(
        f"SHASUMS256.txt에서 {archive_name}의 SHA256을 찾지 못했습니다."
    )


def safe_extract_tar(archive_path: Path, destination: Path) -> None:
    destination_resolved = destination.resolve()
    with tarfile.open(archive_path, mode="r:xz") as archive:
        for member in archive.getmembers():
            member_target = (destination / member.name).resolve()
            try:
                member_target.relative_to(destination_resolved)
            except ValueError as exc:
                raise RuntimeError(
                    f"안전하지 않은 tar 경로가 발견됐습니다: {member.name}"
                ) from exc
        archive.extractall(destination)


def recover_node_v22() -> tuple[Path | None, str | None]:
    if os.name == "nt":
        return None, (
            "Windows에서는 actions/setup-node로 Node.js 22.23.1이 "
            "준비돼 있어야 합니다."
        )

    system_name = platform.system().lower()
    machine = platform.machine().lower()

    if system_name != "linux":
        return None, f"자동 복구 미지원 운영체제: {system_name}"

    arch_map = {
        "x86_64": "x64",
        "amd64": "x64",
        "aarch64": "arm64",
        "arm64": "arm64",
    }
    node_arch = arch_map.get(machine)
    if not node_arch:
        return None, f"자동 복구 미지원 CPU: {machine}"

    archive_name = f"node-{NODE_VERSION}-linux-{node_arch}.tar.xz"
    base_url = f"https://nodejs.org/dist/{NODE_VERSION}"
    manifest_path = NODE_CACHE_DIR / "SHASUMS256.txt"
    archive_path = NODE_CACHE_DIR / archive_name

    try:
        download_file(f"{base_url}/SHASUMS256.txt", manifest_path)
        manifest_text = manifest_path.read_text(encoding="utf-8")
        expected_hash = expected_archive_hash(manifest_text, archive_name)

        if (
            not archive_path.is_file()
            or sha256_file(archive_path) != expected_hash
        ):
            download_file(f"{base_url}/{archive_name}", archive_path)

        actual_hash = sha256_file(archive_path)
        if actual_hash != expected_hash:
            raise RuntimeError(
                "Node.js archive SHA256 불일치: "
                f"actual={actual_hash}, expected={expected_hash}"
            )

        NODE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="node_extract_",
            dir=NODE_CACHE_DIR,
        ) as temporary_dir:
            extract_root = Path(temporary_dir)
            safe_extract_tar(archive_path, extract_root)
            extracted = (
                extract_root
                / f"node-{NODE_VERSION}-linux-{node_arch}"
            )
            node_path = extracted / "bin/node"
            if not node_path.is_file():
                raise RuntimeError(
                    f"압축 해제 후 Node 실행파일이 없습니다: {node_path}"
                )

            if NODE_CURRENT_DIR.exists():
                shutil.rmtree(NODE_CURRENT_DIR)
            shutil.move(str(extracted), str(NODE_CURRENT_DIR))

        final_node = NODE_CURRENT_DIR / "bin/node"
        final_node.chmod(final_node.stat().st_mode | 0o111)
        version = node_version(final_node)
        if version != NODE_VERSION:
            raise RuntimeError(
                f"복구된 Node 버전 불일치: {version} != {NODE_VERSION}"
            )
        return activate_node(final_node), None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def ensure_node() -> tuple[Path | None, str, str | None]:
    located = locate_node()
    if located:
        return located, "reused", None

    recovered, error = recover_node_v22()
    if recovered:
        return recovered, "downloaded", None
    return None, "failed", error


def audit_workflow(text: str) -> list[tuple[str, Any, Any, bool]]:
    results: list[tuple[str, Any, Any, bool]] = []

    def add(name: str, actual: Any, expected: Any, passed: bool) -> None:
        results.append((name, actual, expected, passed))

    add("workflow 탭 문자 없음", "\t" in text, False, "\t" not in text)
    add(
        "workflow 최상위 step 이탈 없음",
        bool(re.search(r"(?m)^- name:", text)),
        False,
        re.search(r"(?m)^- name:", text) is None,
    )
    step_names = tuple(
        match.group(1).strip()
        for match in re.finditer(r"(?m)^      - name:\s*(.+)$", text)
    )
    add("workflow step 순서", step_names, EXPECTED_STEPS, step_names == EXPECTED_STEPS)
    add(
        "workflow 모든 named step 들여쓰기",
        len(re.findall(r"(?m)^\s*- name:", text)),
        len(EXPECTED_STEPS),
        len(re.findall(r"(?m)^      - name:", text)) == len(EXPECTED_STEPS)
        and len(re.findall(r"(?m)^\s*- name:", text)) == len(EXPECTED_STEPS),
    )

    trigger_block = '''"on":
  push:
    tags:
      - "electron-v*"
  workflow_dispatch: {}
'''
    add(
        "workflow trigger 계층",
        trigger_block in text,
        True,
        trigger_block in text,
    )
    add(
        "workflow 수동 실행 trigger 단일",
        text.count("workflow_dispatch:"),
        1,
        text.count("workflow_dispatch:") == 1,
    )
    add(
        "workflow jobs 계층",
        "jobs:\n  windows-electron-package:\n" in text,
        True,
        "jobs:\n  windows-electron-package:\n" in text,
    )
    add(
        "workflow steps 계층",
        "    steps:\n      - name: 체크아웃\n" in text,
        True,
        "    steps:\n      - name: 체크아웃\n" in text,
    )
    add(
        "checkout byte 검증 Python 이후",
        (
            set(("checkout 바이트 무결성 검증", "Python 3.11 설치"))
            <= set(step_names)
            and step_names.index("checkout 바이트 무결성 검증")
            > step_names.index("Python 3.11 설치")
        ),
        True,
        (
            set(("checkout 바이트 무결성 검증", "Python 3.11 설치"))
            <= set(step_names)
            and step_names.index("checkout 바이트 무결성 검증")
            > step_names.index("Python 3.11 설치")
        ),
    )
    checkout_hardening_tokens = (
        "git config --local core.autocrlf false",
        "git config --local core.eol lf",
        "git reset --hard HEAD",
        "git check-attr text eol -- .gitattributes",
        "git check-attr text eol -- electron/.gitignore",
        "git check-attr text eol -- electron/renderer/index.html",
        "git check-attr text eol -- electron/renderer/styles.css",
        "python -X utf8 electron/scripts/validate-checkout-byte-integrity.py",
    )
    add(
        "workflow checkout EOL 전수보강",
        all(token in text for token in checkout_hardening_tokens),
        True,
        all(token in text for token in checkout_hardening_tokens),
    )

    release_condition = (
        "if: github.event_name == 'push' "
        "&& startsWith(github.ref, 'refs/tags/electron-v')"
    )
    add(
        "태그 전용 조건 수",
        text.count(release_condition),
        2,
        text.count(release_condition) == 2,
    )
    add(
        "수동 실행 Release 차단",
        (
            release_condition in text
            and "GitHub Release 생성 및 Electron exe 업로드" in text
        ),
        True,
        (
            release_condition in text
            and "GitHub Release 생성 및 Electron exe 업로드" in text
        ),
    )
    add(
        "Actions artifact 미사용",
        "actions/upload-artifact" in text,
        False,
        "actions/upload-artifact" not in text,
    )
    add(
        "Release Assets 사용",
        "softprops/action-gh-release@v2" in text,
        True,
        "softprops/action-gh-release@v2" in text,
    )
    add(
        "workflow runner context 조기평가 없음",
        "${{ runner." in text,
        False,
        "${{ runner." not in text,
    )
    add(
        "workflow concurrency 존재",
        "concurrency:\n  group: kdrg-electron-windows-${{ github.ref }}"
        in text,
        True,
        "concurrency:\n  group: kdrg-electron-windows-${{ github.ref }}"
        in text,
    )
    return results


def write_report(
    checks: list[dict[str, Any]],
    outputs: dict[str, dict[str, Any]],
) -> int:
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
            f"- [{marker}] {item['name']} | "
            f"actual={item['actual']} | expected={item['expected']}"
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
        for item in failures:
            print(
                f"- {item['name']} | "
                f"actual={item['actual']} | expected={item['expected']}"
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
        checks.append(
            {
                "name": name,
                "actual": actual,
                "expected": expected,
                "passed": bool(passed),
            }
        )
        return bool(passed)

    workflow_path = ROOT / ".github/workflows/build-electron-windows.yml"
    check("Electron workflow 존재", workflow_path.is_file(), True)
    workflow_text = ""
    if workflow_path.is_file():
        workflow_text = workflow_path.read_text(encoding="utf-8")
        check(
            "Electron workflow SHA256",
            sha256_file(workflow_path),
            EXPECTED_WORKFLOW_HASH,
        )
        for name, actual, expected, passed in audit_workflow(workflow_text):
            checks.append(
                {
                    "name": name,
                    "actual": actual,
                    "expected": expected,
                    "passed": passed,
                }
            )

    for relative, expected_hash in PROTECTED_HASHES.items():
        path = ROOT / relative
        check(f"보호 파일 존재 {relative}", path.is_file(), True)
        if path.is_file():
            check(f"보호 파일 SHA256 {relative}", sha256_file(path), expected_hash)

    for relative in (
        "50B_validate_kdrg_electron_search_service.py",
        "50C_validate_kdrg_electron_renderer_ui.py",
        "50D_validate_kdrg_electron_windows_packaging.py",
        "electron/scripts/validate-package-lock-registry.py",
        "electron/scripts/validate-checkout-byte-integrity.py",
    ):
        try:
            py_compile.compile(str(ROOT / relative), doraise=True)
            check(f"py_compile {relative}", "PASS", "PASS")
        except Exception as exc:
            check(
                f"py_compile {relative}",
                f"{type(exc).__name__}: {exc}",
                "PASS",
            )

    attributes_text = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    required_attributes = (
        "* text eol=lf",
        ".gitattributes text eol=lf",
        ".gitignore text eol=lf",
        "*.bat text eol=crlf",
        "*.cmd text eol=crlf",
    )
    check(
        ".gitattributes LF 정책",
        all(rule in attributes_text for rule in required_attributes),
        True,
    )

    critical_eol_files = (
        ".gitattributes",
        "electron/.gitignore",
        "electron/renderer/index.html",
        "electron/renderer/styles.css",
        "data/kdrg_v47_search_integrated.json",
        "data/kdrg_v47_ui_semantic_profile.json",
        "data/kdrg_v47_ui_display_contract.json",
    )
    eol_result = run_command(
        [
            "git",
            "ls-files",
            "--eol",
            "--",
            *critical_eol_files,
        ]
    )
    outputs["Git EOL 정책"] = eol_result
    check("Git EOL 정책 종료코드", eol_result["returncode"], 0)
    check(
        "Git EOL 핵심 텍스트 전체 LF",
        eol_result["stdout"],
        f"{len(critical_eol_files)} lines with i/lf and attr/text eol=lf",
        lambda value, _expected: (
            len([line for line in value.splitlines() if line.strip()])
            == len(critical_eol_files)
            and all(
                "i/lf" in line and "attr/text eol=lf" in line
                for line in value.splitlines()
                if line.strip()
            )
        ),
    )

    lock_path = ELECTRON / "package-lock.json"
    check("package-lock 존재", lock_path.is_file(), True)
    if lock_path.is_file():
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        package = json.loads((ELECTRON / "package.json").read_text(encoding="utf-8"))
        check("package-lock SHA256", sha256_file(lock_path), EXPECTED_LOCK_HASH)
        check("package-lock lockfileVersion", lock.get("lockfileVersion"), 3)
        check("package-lock root name", lock.get("name"), package.get("name"))
        check("package-lock root version", lock.get("version"), package.get("version"))
        check(
            "Electron pin",
            package.get("devDependencies", {}).get("electron"),
            "43.2.0",
        )
        check(
            "electron-builder pin",
            package.get("devDependencies", {}).get("electron-builder"),
            "26.15.3",
        )
        urls = collect_resolved_urls(lock)
        official = [
            url for url in urls
            if urlparse(url).hostname == "registry.npmjs.org"
        ]
        internal = [
            url for url in urls
            if "package-firewall.replit.local" in url.lower()
        ]
        plain_http = [
            url for url in urls
            if url.lower().startswith("http://")
        ]
        check(
            "package-lock resolved URL 수",
            len(urls),
            ">= 50",
            lambda value, _expected: value >= 50,
        )
        check("package-lock 공식 registry 전체", len(official), len(urls))
        check("package-lock 내부 registry 없음", len(internal), 0)
        check("package-lock 평문 HTTP 없음", len(plain_http), 0)

    node, node_state, node_error = ensure_node()
    outputs["Node.js 22 준비"] = {
        "returncode": 0 if node else 1,
        "stdout": (
            f"state={node_state}\n"
            f"path={node if node else ''}\n"
            f"version={node_version(node) if node else ''}"
        ),
        "stderr": node_error or "",
    }
    check(
        "Node.js 22 실행환경",
        str(node) if node else node_error,
        "available",
        lambda value, _expected: bool(node),
    )
    check(
        "Node.js 22 준비 방식",
        node_state,
        "reused or downloaded",
        lambda value, _expected: value in {"reused", "downloaded"},
    )
    if node:
        version_result = run_command([str(node), "--version"])
        outputs["Node version"] = version_result
        check("Node.js 버전", version_result["stdout"], "v22.23.1")

        for relative in JS_CHECK_FILES:
            result = run_command([str(node), "--check", str(ROOT / relative)])
            check(f"node --check {relative}", result["returncode"], 0)

        command_specs = {
            "Stage 50D packaged smoke 계약 회귀검증": (
                [str(node), "tests/validate-packaged-runtime-smoke.js"],
                ELECTRON,
                "35 PASS / 0 FAIL",
            ),
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
            "package-lock registry 독립검증": (
                [sys.executable, "scripts/validate-package-lock-registry.py"],
                ELECTRON,
                "package-lock registry canonicalization 검증",
            ),
            "checkout byte integrity 독립검증": (
                [sys.executable, "scripts/validate-checkout-byte-integrity.py"],
                ELECTRON,
                "checkout byte integrity 검증",
            ),
        }
        for name, (args, cwd, marker) in command_specs.items():
            result = run_command(args, cwd)
            outputs[name] = result
            check(
                name,
                result,
                f"returncode=0 and marker={marker}",
                lambda value, _expected, marker=marker: (
                    value["returncode"] == 0
                    and marker in value["stdout"]
                ),
            )

    package = json.loads((ELECTRON / "package.json").read_text(encoding="utf-8"))
    smoke_source = (ELECTRON / "src/packaged-runtime-smoke.js").read_text(encoding="utf-8")
    search_service_source = (ELECTRON / "src/kdrg-search-service.js").read_text(encoding="utf-8")
    package_scripts = package.get("scripts", {})
    check(
        "packaged smoke 현재 results 계약 사용",
        "search.results" in smoke_source and "search.items.some" not in smoke_source,
        True,
    )
    check(
        "검색 service results 응답 계약 존재",
        "results," in search_service_source
        and "schema_version: RESPONSE_SCHEMA_VERSION" in search_service_source,
        True,
    )
    check(
        "packaged smoke 계약검증 script",
        package_scripts.get("validate:smoke-contract"),
        "node tests/validate-packaged-runtime-smoke.js",
    )
    check(
        "전체 validate에 smoke 계약검증 포함",
        "validate:smoke-contract" in package_scripts.get("validate", ""),
        True,
    )
    check(
        "전체 check에 smoke 계약검증 문법 포함",
        "validate-packaged-runtime-smoke.js" in package_scripts.get("check", ""),
        True,
    )
    check(
        "packaged smoke 단계별 진단 포함",
        "completed_steps" in smoke_source and "failed_step" in smoke_source,
        True,
    )
    check(
        "dist:win script",
        package.get("scripts", {}).get("dist:win"),
        "electron-builder --win portable --x64 --publish never",
    )
    check("build asar", package.get("build", {}).get("asar"), True)
    check(
        "build portable target",
        package.get("build", {}).get("win", {}).get("target", [{}])[0].get("target"),
        "portable",
    )
    check(
        "extraResources 수",
        len(package.get("build", {}).get("extraResources", [])),
        3,
    )

    pyside_workflow = (
        ROOT / ".github/workflows/build-windows-release.yml"
    ).read_text(encoding="utf-8")
    check("PySide 태그 유지", '"v*.*.*"' in pyside_workflow, True)
    check("Electron 태그 분리", '"electron-v*"' in workflow_text, True)

    return write_report(checks, outputs)


if __name__ == "__main__":
    raise SystemExit(main())
