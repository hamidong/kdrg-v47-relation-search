from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import py_compile
import platform
import re
import shutil
import subprocess
import tarfile
import urllib.request
import sys
import tempfile
from pathlib import Path
from typing import Any

SCRIPT_VERSION = "2026-07-30_KDRG_V47_ELECTRON_STAGE50B_VALIDATOR_V5_RELATION_SEARCH"
ROOT = Path(__file__).resolve().parent
ELECTRON = ROOT / "electron"
REPORT_DIR = ROOT / "reports"
REPORT_TXT = REPORT_DIR / "electron_stage50b_validation_report.txt"
REPORT_JSON = REPORT_DIR / "electron_stage50b_validation_report.json"

PROTECTED_HASHES = {
    "data/kdrg_v47_search_integrated.json": "3de5d6d95cd9cbd16e674f5a4cffcd8bf89da2ee70627501f56d81b05bbe8af1",
    "data/kdrg_v47_search_integrated_v3.json": "d865b8a421acb728b9cbc01ef3ba01036206bdc22b1877e70f938ead724e3dda",
    "data/kdrg_v47_ui_semantic_profile.json": "c9401fd9d6dcc1253fa2134b22048fe4a73c4c04aeea4d1d86c7fe1504d5456e",
    "data/kdrg_v47_ui_display_contract.json": "9976307acd77bb6a0c8a48b2788d055faf563d497381b2c2cacfc7435df0f1ac",
    "app/kdrg_search_service.py": "35766cfd10b887c9852536a2165d6719e20c5ad2791a5d1a0d0166d7b94cb6cd",
    "app/runtime_data_store.py": "e2d5bf1de4c9697f84e30f9e8ec9664abf9cda0acddb392620c3a7b71f28d48d",
    "app/main_window.py": "291b4f76d389b24695ebe2b180b1cd4a729a8978af758dd279656c67ac5df242",
    "tests/windows_runtime_source_smoke.py": "5fc535d44956e4e5efef3e4356c5f8629954b5a9e60bf6d912987257629fc907",
    "version.py": "2c30bcec8f896845e26f371297c75dde609a27df693059c9faab3d91b828506c",
}

REQUIRED_ELECTRON_FILES = [
    "package.json",
    "main.js",
    "preload.js",
    "src/bootstrap-data.js",
    "src/data-paths.js",
    "src/search-normalizer.js",
    "src/search-result-contract.js",
    "src/kdrg-search-service.js",
    "tests/validate-electron-skeleton.js",
    "tests/validate-search-service.js",
    "tests/run-search-parity.js",
    "README_STAGE50A.md",
    "README_STAGE50B.md",
]

SEARCH_SCENARIOS = [
    {"name": "all_E011", "query": "E011", "entity_type": "ALL", "options": {"limit": 50}},
    {"name": "all_A010", "query": "A010", "entity_type": "ALL", "options": {"limit": 50}},
    {"name": "dotted_A010", "query": "A01.0", "entity_type": "ALL", "options": {"limit": 50}},
    {"name": "table_9610", "query": "LT_9610_001", "entity_type": "TABLE", "options": {"limit": 50}},
    {"name": "drg_9610", "query": "9610", "entity_type": ["ADRG", "AADRG", "RDRG"], "options": {"limit": 50}},
    {"name": "all_9620", "query": "9620", "entity_type": "ALL", "options": {"limit": 20}},
    {"name": "korean_early_death", "query": "조기 사망", "entity_type": "ALL", "options": {"limit": 20}},
    {"name": "classification_text", "query": "질병군 분류(일반)", "entity_type": "ALL", "options": {"limit": 20}},
    {"name": "code_only", "query": "A010", "entity_type": "CODE", "options": {"limit": 10}},
    {"name": "mdc_filter", "query": "A010", "entity_type": "ALL", "options": {"limit": 10, "mdc": "01"}},
    {"name": "classification_A", "query": "A010", "entity_type": "ALL", "options": {"limit": 10, "classification": "A"}},
    {"name": "classification_korean", "query": "A010", "entity_type": "ALL", "options": {"limit": 10, "classification": "전문"}},
    {"name": "table_pagination", "query": "001", "entity_type": "TABLE", "options": {"limit": 10, "offset": 5}},
    {"name": "aad_rg_only", "query": "96000", "entity_type": "AADRG", "options": {"limit": 10}},
    {"name": "rdrg_only", "query": "960000", "entity_type": "RDRG", "options": {"limit": 10}},
    {"name": "contains_table", "query": "LT_E011", "entity_type": "TABLE", "options": {"limit": 20}},
    {"name": "mdc_pre", "query": "사망", "entity_type": "ALL", "options": {"limit": 20, "mdc": "PRE"}},
    {"name": "classification_B", "query": "9610", "entity_type": "ALL", "options": {"limit": 20, "classification": "B"}},
    {"name": "mixed_types", "query": "E011", "entity_type": ["CODE", "TABLE"], "options": {"limit": 30}},
    {"name": "offset_result", "query": "9620", "entity_type": "ALL", "options": {"limit": 15, "offset": 15}},
]

DETAIL_SCENARIOS = [
    ("code_A010", "CODE", "A010"),
    ("adrg_E011", "ADRG", "E011"),
    ("adrg_9610", "ADRG", "9610"),
    ("adrg_9620", "ADRG", "9620"),
    ("aadrg_96100", "AADRG", "96100"),
    ("rdrg_961000", "RDRG", "961000"),
    ("table_9610", "TABLE", "LT_9610_001"),
    ("table_9620_excluded", "TABLE", "LT_9620_002"),
    ("table_E011_base", "TABLE", "LT_E011_002"),
    ("table_E011_excluded", "TABLE", "LT_E011_003"),
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


NODE_REQUIRED_MAJOR = 22
NODE_RELEASE_BASE = "https://nodejs.org/download/release/latest-v22.x"
NODE_CACHE_ROOT = ROOT.parent / ".cache" / "kdrg-stage50a-node-v22"


def parse_node_major(version_text: str) -> int:
    raw = version_text.strip().lstrip("v").split(".", 1)[0]
    try:
        return int(raw)
    except ValueError:
        return -1


def run_node_command(args: list[str]) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            args,
            cwd=ROOT,
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


def detect_node_arch() -> str:
    machine = platform.machine().lower()
    mapping = {
        "x86_64": "x64",
        "amd64": "x64",
        "aarch64": "arm64",
        "arm64": "arm64",
    }
    if machine not in mapping:
        raise RuntimeError(f"지원하지 않는 Linux architecture: {machine}")
    return mapping[machine]


def validate_node_candidate(path: Path) -> dict[str, Any]:
    result = run_node_command([str(path), "--version"])
    major = parse_node_major(result["stdout"])
    return {
        "path": str(path),
        "returncode": result["returncode"],
        "version": result["stdout"],
        "stderr": result["stderr"],
        "major": major,
        "usable": result["returncode"] == 0 and major >= NODE_REQUIRED_MAJOR,
    }


def existing_node_candidates() -> list[Path]:
    from shutil import which

    candidates: list[Path] = []
    explicit = os.environ.get("KDRG_NODE_BIN", "").strip()
    if explicit:
        candidates.append(Path(explicit))

    candidates.extend(
        [
            NODE_CACHE_ROOT / "current" / "bin" / "node",
            Path("/home/runner/.cache/kdrg-stage50a-node-v22/current/bin/node"),
            Path.home() / ".cache/kdrg-stage50a-node-v22/current/bin/node",
            Path.home() / ".nix-profile/bin/node",
            Path("/usr/local/bin/node"),
            Path("/usr/bin/node"),
        ]
    )

    for command in ("node", "nodejs"):
        resolved = which(command)
        if resolved:
            candidates.append(Path(resolved))

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        try:
            key = str(candidate.resolve(strict=False))
        except OSError:
            key = str(candidate)
        if key not in seen:
            unique.append(candidate)
            seen.add(key)
    return unique


def sha256_local(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_extract_tar(archive: tarfile.TarFile, destination: Path) -> None:
    destination_resolved = destination.resolve()
    for member in archive.getmembers():
        target = (destination / member.name).resolve()
        if destination_resolved not in target.parents and target != destination_resolved:
            raise RuntimeError(f"tar 경로 이탈 감지: {member.name}")
        if member.issym() or member.islnk():
            link_target = (target.parent / member.linkname).resolve()
            if (
                destination_resolved not in link_target.parents
                and link_target != destination_resolved
            ):
                raise RuntimeError(f"tar 링크 경로 이탈 감지: {member.name}")
    archive.extractall(destination)


def download_portable_node() -> Path:
    arch = detect_node_arch()
    NODE_CACHE_ROOT.mkdir(parents=True, exist_ok=True)

    headers = {"User-Agent": "KDRG-Stage50B-Validator/1.0"}
    shasums_url = f"{NODE_RELEASE_BASE}/SHASUMS256.txt"
    print("[INFO] Node.js v22 공식 SHA256 목록 확인 중...", flush=True)
    request = urllib.request.Request(shasums_url, headers=headers)
    with urllib.request.urlopen(request, timeout=45) as response:
        shasums_text = response.read().decode("utf-8")

    pattern = re.compile(
        rf"^([0-9a-f]{{64}})  (node-v22\.[0-9.]+-linux-{re.escape(arch)}\.tar\.xz)$",
        re.MULTILINE,
    )
    match = pattern.search(shasums_text)
    if not match:
        raise RuntimeError(
            f"Node v22 Linux {arch} 배포파일을 SHASUMS256.txt에서 찾지 못했습니다."
        )

    expected_sha, filename = match.groups()
    archive_path = NODE_CACHE_ROOT / filename
    partial_path = NODE_CACHE_ROOT / f"{filename}.partial"
    archive_url = f"{NODE_RELEASE_BASE}/{filename}"

    archive_is_valid = archive_path.exists() and sha256_local(archive_path) == expected_sha
    if archive_is_valid:
        print(
            f"[INFO] SHA256가 확인된 기존 Node archive 재사용: {filename}",
            flush=True,
        )
    else:
        archive_path.unlink(missing_ok=True)
        partial_path.unlink(missing_ok=True)
        print(
            f"[INFO] 공식 Node.js v22 portable 다운로드 시작: {filename}",
            flush=True,
        )
        digest = hashlib.sha256()
        downloaded = 0
        request = urllib.request.Request(archive_url, headers=headers)
        with urllib.request.urlopen(request, timeout=120) as response, partial_path.open("wb") as out:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                digest.update(chunk)
                downloaded += len(chunk)
                if downloaded % (5 * 1024 * 1024) < len(chunk):
                    print(
                        f"[INFO] Node archive 다운로드: {downloaded // (1024 * 1024)}MB",
                        flush=True,
                    )
        actual_sha = digest.hexdigest()
        if actual_sha != expected_sha:
            partial_path.unlink(missing_ok=True)
            raise RuntimeError(
                f"Node archive SHA256 불일치: actual={actual_sha}, expected={expected_sha}"
            )
        partial_path.replace(archive_path)

    extract_root = NODE_CACHE_ROOT / "extracting"
    if extract_root.exists():
        shutil.rmtree(extract_root)
    extract_root.mkdir(parents=True)

    with tarfile.open(archive_path, "r:xz") as archive:
        safe_extract_tar(archive, extract_root)

    extracted_dirs = [path for path in extract_root.iterdir() if path.is_dir()]
    if len(extracted_dirs) != 1:
        raise RuntimeError(
            f"Node archive 최상위 디렉터리 수가 예상과 다릅니다: {len(extracted_dirs)}"
        )

    current = NODE_CACHE_ROOT / "current"
    if current.exists() or current.is_symlink():
        if current.is_dir() and not current.is_symlink():
            shutil.rmtree(current)
        else:
            current.unlink()
    extracted_dirs[0].replace(current)
    shutil.rmtree(extract_root, ignore_errors=True)

    node_path = current / "bin" / "node"
    if not node_path.exists():
        raise RuntimeError(f"압축 해제 후 node 실행파일 없음: {node_path}")
    return node_path


def activate_node(path: Path) -> None:
    os.environ["PATH"] = f"{path.parent}{os.pathsep}{os.environ.get('PATH', '')}"
    os.environ["KDRG_NODE_BIN"] = str(path)


def locate_node() -> Path | None:
    for candidate in existing_node_candidates():
        if not candidate.exists():
            continue
        result = validate_node_candidate(candidate)
        if result["usable"]:
            activate_node(candidate)
            print(
                f"[INFO] Stage 50B Node 사용: {candidate} ({result['version']})",
                flush=True,
            )
            return candidate

    try:
        node_path = download_portable_node()
        validation = validate_node_candidate(node_path)
        if not validation["usable"]:
            raise RuntimeError(f"다운로드한 Node가 기준 미달: {validation}")
        activate_node(node_path)
        print(
            f"[INFO] 공식 Node v22 portable runtime 준비 완료: "
            f"{validation['version']} ({node_path})",
            flush=True,
        )
        return node_path
    except Exception as exc:
        print(
            f"[FAIL] Stage 50B용 Node v22 실행환경 준비 실패: "
            f"{type(exc).__name__}: {exc}",
            flush=True,
        )
        return None

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


def load_python_service() -> tuple[Any, Any]:
    module_path = ROOT / "app/kdrg_search_service.py"
    spec = importlib.util.spec_from_file_location("kdrg_stage50b_python_service", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Python service import spec 생성 실패: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, module.KdrgSearchService(ROOT / "data/kdrg_v47_search_integrated.json")


def search_document_fingerprint(service: Any) -> dict[str, Any]:
    rows = []
    for key, document in sorted(service._search_documents.items()):
        rows.append(
            {
                "key": key,
                "entity_type": document["entity_type"],
                "entity_id": document["entity_id"],
                "title": document["title"],
                "subtitle": document["subtitle"],
                "fields": document["fields"],
                "haystack": document["haystack"],
                "tokens": sorted(document["tokens"]),
            }
        )
    return {"count": len(rows), "sha256": canonical_sha256(rows)}


def semantic_context_fingerprint(service: Any) -> dict[str, Any]:
    rows = [
        {"adrg": adrg, "table_id": table_id, "contexts": contexts}
        for (adrg, table_id), contexts in sorted(service._semantic_context_index.items())
    ]
    return {
        "key_count": len(rows),
        "occurrence_count": sum(len(row["contexts"]) for row in rows),
        "sha256": canonical_sha256(rows),
    }


def exact_id_audit(service: Any, module: Any) -> dict[str, Any]:
    failures = []
    for key, document in service._search_documents.items():
        match = service._match_document(
            document,
            document["entity_id"],
            module.query_tokens(document["entity_id"]),
        )
        if match is None or match[0] != 1000 or match[1] != "EXACT_ID":
            failures.append(key)
    return {"checked": len(service._search_documents), "failures": failures}


def create_baseline(service: Any, module: Any) -> dict[str, Any]:
    status = service.status()
    status.pop("data_path", None)
    searches = []
    for scenario in SEARCH_SCENARIOS:
        options = scenario["options"]
        response = service.search(
            scenario["query"],
            scenario["entity_type"],
            limit=options.get("limit", 50),
            offset=options.get("offset", 0),
            mdc=options.get("mdc"),
            classification=options.get("classification"),
        )
        searches.append(
            {
                "name": scenario["name"],
                "request": {
                    "query": scenario["query"],
                    "entity_type": scenario["entity_type"],
                    "options": options,
                },
                "response": response,
            }
        )
    details = [
        {
            "name": name,
            "request": {"entity_type": entity_type, "entity_id": entity_id},
            "response": service.get_detail(entity_type, entity_id),
        }
        for name, entity_type, entity_id in DETAIL_SCENARIOS
    ]
    return {
        "meta": {"validator": SCRIPT_VERSION, "python": sys.version.split()[0]},
        "status": status,
        "search_document_fingerprint": search_document_fingerprint(service),
        "semantic_context_fingerprint": semantic_context_fingerprint(service),
        "exact_id_audit": exact_id_audit(service, module),
        "search_scenarios": searches,
        "detail_scenarios": details,
    }


def main() -> int:
    checks: list[dict[str, Any]] = []

    def check(name: str, actual: Any, expected: Any, predicate=None) -> None:
        passed = predicate(actual, expected) if predicate else actual == expected
        checks.append({"name": name, "actual": actual, "expected": expected, "passed": bool(passed)})

    for relative, expected_hash in PROTECTED_HASHES.items():
        path = ROOT / relative
        check(f"보호 파일 존재 {relative}", path.exists(), True)
        if path.exists():
            check(f"보호 파일 SHA256 {relative}", sha256_file(path), expected_hash)

    for relative in REQUIRED_ELECTRON_FILES:
        check(f"Electron 파일 존재 {relative}", (ELECTRON / relative).exists(), True)

    for relative in [
        "electron/src/search-normalizer.js",
        "electron/src/search-result-contract.js",
        "electron/src/kdrg-search-service.js",
        "electron/tests/validate-search-service.js",
        "electron/tests/run-search-parity.js",
        "electron/main.js",
        "electron/preload.js",
    ]:
        path = ROOT / relative
        if path.exists():
            check(f"파일 비어 있지 않음 {relative}", path.stat().st_size > 100, True)

    try:
        py_compile.compile(str(ROOT / "app/kdrg_search_service.py"), doraise=True)
        check("Python 기준 service py_compile", "PASS", "PASS")
    except Exception as exc:
        check("Python 기준 service py_compile", f"{type(exc).__name__}: {exc}", "PASS")

    node = locate_node()
    check("Node v22 실행환경", str(node) if node else None, "available", lambda a, _e: bool(a))
    if node is None:
        failures = [item for item in checks if not item["passed"]]
        return write_report(checks, failures, {}, {})

    js_files = [
        "main.js",
        "preload.js",
        "src/bootstrap-data.js",
        "src/search-normalizer.js",
        "src/search-result-contract.js",
        "src/kdrg-search-service.js",
        "tests/validate-electron-skeleton.js",
        "tests/validate-search-service.js",
        "tests/run-search-parity.js",
    ]
    for relative in js_files:
        result = run_command([str(node), "--check", str(ELECTRON / relative)], ROOT)
        check(f"node --check electron/{relative}", result["returncode"], 0)

    module, python_service = load_python_service()
    baseline = create_baseline(python_service, module)
    check("Python search document count", baseline["search_document_fingerprint"]["count"], 22943)
    check("Python semantic relationship key count", baseline["semantic_context_fingerprint"]["key_count"], 906)
    check("Python semantic occurrence count", baseline["semantic_context_fingerprint"]["occurrence_count"], 939)
    check("Python exact ID audit", baseline["exact_id_audit"]["failures"], [])
    check("검색 시나리오 수", len(baseline["search_scenarios"]), 20)
    check("상세 시나리오 수", len(baseline["detail_scenarios"]), 10)

    with tempfile.TemporaryDirectory(prefix="kdrg_stage50b_") as temp_dir:
        baseline_path = Path(temp_dir) / "python_search_baseline.json"
        baseline_path.write_text(json.dumps(baseline, ensure_ascii=False), encoding="utf-8")
        parity_result = run_command(
            [
                str(node),
                str(ELECTRON / "tests/run-search-parity.js"),
                str(baseline_path),
                str(ROOT / "data/kdrg_v47_search_integrated_v3.json"),
            ],
            ROOT,
        )
    check(
        "Python-JavaScript 동등성",
        {"returncode": parity_result["returncode"], "stdout": parity_result["stdout"], "stderr": parity_result["stderr"]},
        "returncode=0 and PASS",
        lambda a, _e: a["returncode"] == 0 and "[PASS] Python-JavaScript 검색 동등성" in a["stdout"],
    )

    skeleton_validation = run_command([str(node), str(ELECTRON / "tests/validate-electron-skeleton.js")], ROOT)
    check(
        "Node Electron 보안 골격 검증",
        {"returncode": skeleton_validation["returncode"], "stdout": skeleton_validation["stdout"], "stderr": skeleton_validation["stderr"]},
        "returncode=0 and PASS",
        lambda a, _e: a["returncode"] == 0 and "[PASS] Electron Stage 50C 보안 골격 검증" in a["stdout"],
    )

    node_validation = run_command([str(node), str(ELECTRON / "tests/validate-search-service.js")], ROOT)
    check(
        "Node 검색 service 전수검증",
        {"returncode": node_validation["returncode"], "stdout": node_validation["stdout"], "stderr": node_validation["stderr"]},
        "returncode=0 and PASS",
        lambda a, _e: a["returncode"] == 0 and "[PASS] Electron Stage 50C 검색 service 호환성 검증" in a["stdout"],
    )

    package = json.loads((ELECTRON / "package.json").read_text(encoding="utf-8"))
    check("package Node engine", package.get("engines", {}).get("node"), ">=22.0.0")
    check("Electron pin 유지", package.get("devDependencies", {}).get("electron"), "43.2.0")
    check("Stage 50D package-lock 존재", (ELECTRON / "package-lock.json").exists(), True)
    check("node_modules 경로가 파일이 아님", (ELECTRON / "node_modules").is_file(), False)

    main_source = (ELECTRON / "main.js").read_text(encoding="utf-8")
    preload_source = (ELECTRON / "preload.js").read_text(encoding="utf-8")
    check("contextIsolation 유지", "contextIsolation: true" in main_source, True)
    check("nodeIntegration 비활성 유지", "nodeIntegration: false" in main_source, True)
    check("sandbox 유지", "sandbox: true" in main_source, True)
    check("IPC 검색 입력검증", "normalizeSearchRequest(payload)" in main_source, True)
    check("IPC 관계검색 입력검증", "normalizeRelationRequest(payload)" in main_source, True)
    check("IPC 관계검색 채널", "kdrg:relation-search" in main_source, True)
    check("preload 관계검색 bridge", "relationSearch: (request)" in preload_source, True)
    check("IPC 상세 입력검증", "normalizeDetailRequest(payload)" in main_source, True)
    check("preload ipcRenderer 직접 미노출", "ipcRenderer," in preload_source, False)

    failures = [item for item in checks if not item["passed"]]
    return write_report(checks, failures, parity_result, node_validation, baseline, skeleton_validation)


def write_report(
    checks: list[dict[str, Any]],
    failures: list[dict[str, Any]],
    parity_result: dict[str, Any],
    node_validation: dict[str, Any],
    baseline: dict[str, Any] | None = None,
    skeleton_validation: dict[str, Any] | None = None,
) -> int:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    pass_count = sum(1 for item in checks if item["passed"])
    lines = [
        "KDRG V4.7 Stage 50B Electron JavaScript 검색 service 독립검증",
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
    if parity_result:
        lines.extend(["", "[Python↔JavaScript 동등성 stdout]", parity_result.get("stdout", "")])
    if skeleton_validation:
        lines.extend(["", "[Node 보안 골격 검증 stdout]", skeleton_validation.get("stdout", "")])
    if node_validation:
        lines.extend(["", "[Node 검색 검증 stdout]", node_validation.get("stdout", "")])
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
                "baseline_summary": {
                    "search_scenarios": len((baseline or {}).get("search_scenarios", [])),
                    "detail_scenarios": len((baseline or {}).get("detail_scenarios", [])),
                    "search_document_fingerprint": (baseline or {}).get("search_document_fingerprint"),
                    "semantic_context_fingerprint": (baseline or {}).get("semantic_context_fingerprint"),
                },
                "parity_result": parity_result,
                "node_validation": node_validation,
                "skeleton_validation": skeleton_validation or {},
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    if failures:
        print(f"[FAIL] KDRG Stage 50B Electron 검색 service 검증: {pass_count} PASS / {len(failures)} FAIL")
        print("[FAIL 상세]")
        for item in failures:
            print(f"- {item['name']} | actual={item['actual']} | expected={item['expected']}")
        print(f"report={REPORT_TXT}")
        return 1
    print(f"[PASS] KDRG Stage 50B Electron 검색 service 검증: {pass_count} PASS / 0 FAIL")
    print(f"report={REPORT_TXT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
