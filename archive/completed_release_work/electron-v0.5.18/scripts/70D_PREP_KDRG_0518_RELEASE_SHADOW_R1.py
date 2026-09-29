from __future__ import annotations

import copy
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent

BASE_COMMIT = "08b51f4fa487a3ae05c1e279aa1c533f9f3aed52"
BASE_VERSION = "0.5.17"
TARGET_VERSION = "0.5.18"
BASE_TAG = "electron-v0.5.17"

RUNTIME_REL = Path("data/kdrg_v47_search_integrated_v3.json")
RUNTIME_SHA = "1a3d50400567ecaad9695b7be8e7c0382131f8652f398e010cf01f4d8dda6c58"

ACTUAL_SCRIPT = ROOT / "70C_APPLY_KDRG_0518_PHASE1_UI_ACTUAL_R2.py"
ACTUAL_SCRIPT_SHA = "e7eb32e701c639ce75da8a572742a288aedd5dd1e5d5edc4815f0de8c4b14fc0"
ACTUAL_REPORT = ROOT / "reports/stage70c_0518_phase1_ui_actual_r2/actual.json"

REPORT_DIR = ROOT / "reports/stage70d_0518_release_prep_shadow_r1"
SHADOW = REPORT_DIR / "shadow"
REPORT_JSON = REPORT_DIR / "shadow.json"
REPORT_TXT = REPORT_DIR / "shadow_summary.txt"

PRODUCT_ACTUAL = [
    Path("electron/renderer/app.js"),
    Path("electron/renderer/styles.css"),
    Path("electron/tests/validate-stage70b-0518-phase1-ui.js"),
]

RELEASE_PREP = [
    Path("50D_validate_kdrg_electron_windows_packaging.py"),
    Path("electron/package.json"),
    Path("electron/package-lock.json"),
]

FINAL_RELEASE_FILES = PRODUCT_ACTUAL + RELEASE_PREP

EXPECTED_MODIFIED_TRACKED = sorted(str(x) for x in [
    Path("50D_validate_kdrg_electron_windows_packaging.py"),
    Path("electron/package-lock.json"),
    Path("electron/package.json"),
    Path("electron/renderer/app.js"),
    Path("electron/renderer/styles.css"),
])
EXPECTED_UNTRACKED = [
    "electron/tests/validate-stage70b-0518-phase1-ui.js",
]


class Stop(RuntimeError):
    pass


def require(value, message):
    if not value:
        raise Stop(message)


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


def git_text(*args, cwd=ROOT):
    rc, out = run(["git", *args], cwd=cwd, timeout=120)
    require(rc == 0, f"git {' '.join(args)} 실패\n{out[-3000:]}")
    return out.strip()


def git_show_bytes(rel: Path, cwd=ROOT) -> bytes:
    p = subprocess.run(
        ["git", "show", f"HEAD:{rel.as_posix()}"],
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=120,
    )
    require(
        p.returncode == 0,
        f"HEAD blob 읽기 실패: {rel}\n"
        + p.stderr.decode("utf-8", errors="replace")[-2000:],
    )
    return p.stdout


def write_json_standard(path: Path, data):
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def patch_package_json(path: Path):
    old = json.loads(path.read_text(encoding="utf-8"))
    require(
        old.get("version") == BASE_VERSION,
        f"package base version 불일치: {old.get('version')}",
    )
    new = copy.deepcopy(old)
    new["version"] = TARGET_VERSION
    write_json_standard(path, new)
    reread = json.loads(path.read_text(encoding="utf-8"))
    expected = copy.deepcopy(old)
    expected["version"] = TARGET_VERSION
    require(reread == expected, "package.json에서 version 외 구조 변경 발생")
    return sha256(path)


def patch_package_lock(path: Path):
    old = json.loads(path.read_text(encoding="utf-8"))
    require(
        old.get("version") == BASE_VERSION,
        f"package-lock top version 불일치: {old.get('version')}",
    )
    require(
        (old.get("packages") or {}).get("", {}).get("version") == BASE_VERSION,
        "package-lock root package version 불일치",
    )
    new = copy.deepcopy(old)
    new["version"] = TARGET_VERSION
    new["packages"][""]["version"] = TARGET_VERSION
    write_json_standard(path, new)
    reread = json.loads(path.read_text(encoding="utf-8"))
    expected = copy.deepcopy(old)
    expected["version"] = TARGET_VERSION
    expected["packages"][""]["version"] = TARGET_VERSION
    require(
        reread == expected,
        "package-lock에서 허용된 2개 version 외 구조 변경 발생",
    )
    return sha256(path)


def patch_50d(path: Path):
    source = path.read_text(encoding="utf-8")
    old_count = source.count(BASE_VERSION)
    require(old_count >= 1, "50D에서 0.5.17 release version anchor를 찾지 못함")

    candidate = source.replace(BASE_VERSION, TARGET_VERSION)
    script_line = re.search(
        r'(?m)^SCRIPT_VERSION\s*=\s*(["\'])(?P<value>[^"\']+)\1\s*$',
        candidate,
    )
    require(script_line is not None, "50D SCRIPT_VERSION line 없음")
    old_script_version = script_line.group("value")
    new_script_version = old_script_version.replace("0517", "0518")
    if new_script_version != old_script_version:
        candidate = candidate.replace(old_script_version, new_script_version, 1)

    require(BASE_VERSION not in candidate, "50D에 0.5.17 release expectation이 남아 있음")
    require(TARGET_VERSION in candidate, "50D에 0.5.18 release expectation이 없음")

    path.write_text(candidate, encoding="utf-8")
    compile(candidate, str(path), "exec")
    return {
        "old_version_occurrences": old_count,
        "script_version_before": old_script_version,
        "script_version_after": new_script_version,
        "sha256": sha256(path),
    }


def node_check(rel: Path, cwd: Path):
    rc, out = run(["node", "--check", str(rel)], cwd=cwd, timeout=120)
    require(rc == 0, f"node --check FAIL: {rel}\n{out[-3000:]}")


def scoped_status(cwd: Path):
    rc, out = run(
        ["git", "status", "--porcelain=v1", "--", *[str(x) for x in FINAL_RELEASE_FILES]],
        cwd=cwd,
        timeout=120,
    )
    require(rc == 0, f"git status 실패\n{out[-3000:]}")
    modified = []
    untracked = []
    raw = []
    for line in out.splitlines():
        if not line:
            continue
        raw.append(line)
        status = line[:2]
        name = line[3:]
        if status == "??":
            untracked.append(name)
        else:
            modified.append(name)
    return sorted(modified), sorted(untracked), raw


def main():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "stage": "70D_RELEASE_PREP_SHADOW_R1",
        "status": "FAIL",
        "actual_performed": False,
    }

    try:
        # 1) Bind to exact Stage70C Actual PASS.
        head = git_text("rev-parse", "HEAD")
        origin_main = git_text("rev-parse", "origin/main")
        branch = git_text("branch", "--show-current")
        staged = [
            x for x in git_text("diff", "--cached", "--name-only").splitlines() if x
        ]

        require(head == BASE_COMMIT, f"HEAD 불일치: {head}")
        require(origin_main == BASE_COMMIT, f"origin/main 불일치: {origin_main}")
        require(branch == "main", f"branch 불일치: {branch}")
        require(not staged, f"staging 변경 있음: {staged}")
        require(sha256(ROOT / RUNTIME_REL) == RUNTIME_SHA, "운영 JSON SHA 불일치")

        local_tag = git_text("rev-list", "-n", "1", BASE_TAG)
        require(local_tag == BASE_COMMIT, f"{BASE_TAG} local tag commit 불일치")
        remote_tag_line = git_text("ls-remote", "--tags", "origin", f"refs/tags/{BASE_TAG}")
        require(remote_tag_line.startswith(BASE_COMMIT), f"{BASE_TAG} remote tag commit 불일치")

        require(ACTUAL_SCRIPT.is_file(), "70C Actual 작업파일 없음")
        require(sha256(ACTUAL_SCRIPT) == ACTUAL_SCRIPT_SHA, "70C Actual 작업파일 SHA 불일치")
        require(ACTUAL_REPORT.is_file(), "70C actual.json 없음")

        actual = json.loads(ACTUAL_REPORT.read_text(encoding="utf-8"))
        require(actual.get("status") == "PASS", "70C Actual status != PASS")
        require(
            actual.get("readiness") == "READY_FOR_70D_0518_RELEASE_PREP_SHADOW",
            f"70C readiness 불일치: {actual.get('readiness')}",
        )
        require(actual.get("head") == BASE_COMMIT, "70C Actual HEAD 불일치")
        require(actual.get("base_version") == BASE_VERSION, "70C Actual base_version 불일치")
        require(actual.get("next_version") == TARGET_VERSION, "70C Actual next_version 불일치")
        require(actual.get("runtime_json") == "UNCHANGED", "70C Actual runtime JSON 계약 불일치")
        require(actual.get("rollback") == "NOT_NEEDED", "70C Actual rollback 상태 불일치")
        require(
            sorted(actual.get("actual_product_files") or [])
            == sorted(str(x) for x in PRODUCT_ACTUAL),
            "70C Actual 제품파일 범위 불일치",
        )
        checks = actual.get("checks") or []
        require(
            checks and all(x.get("status") == "PASS" for x in checks),
            "70C Actual validation chain 불완전",
        )

        actual_sha = actual.get("actual_sha256") or {}
        require(
            set(actual_sha) == set(str(x) for x in PRODUCT_ACTUAL),
            "70C Actual SHA key 범위 불일치",
        )
        for rel in PRODUCT_ACTUAL:
            path = ROOT / rel
            require(path.is_file(), f"70C Actual 제품파일 없음: {rel}")
            require(
                actual_sha.get(str(rel)) == sha256(path),
                f"70C Actual SHA 불일치: {rel}",
            )

        current_modified, current_untracked, current_raw = scoped_status(ROOT)
        expected_current_modified = sorted([
            "electron/renderer/app.js",
            "electron/renderer/styles.css",
        ])
        require(
            current_modified == expected_current_modified,
            f"70C Actual tracked 범위 불일치: actual={current_modified}, expected={expected_current_modified}",
        )
        require(
            current_untracked == EXPECTED_UNTRACKED,
            f"70C Actual untracked 범위 불일치: actual={current_untracked}, expected={EXPECTED_UNTRACKED}",
        )

        # Release-prep files must still equal immutable 0.5.17 HEAD.
        for rel in RELEASE_PREP:
            require((ROOT / rel).is_file(), f"release-prep 기준파일 없음: {rel}")
            require(
                (ROOT / rel).read_bytes() == git_show_bytes(rel),
                f"release-prep 기준파일이 HEAD와 다름: {rel}",
            )

        pkg_actual = json.loads((ROOT / "electron/package.json").read_text(encoding="utf-8"))
        lock_actual = json.loads((ROOT / "electron/package-lock.json").read_text(encoding="utf-8"))
        require(pkg_actual.get("version") == BASE_VERSION, "Actual package version != 0.5.17")
        require(lock_actual.get("version") == BASE_VERSION, "Actual package-lock version != 0.5.17")
        require(
            (lock_actual.get("packages") or {}).get("", {}).get("version") == BASE_VERSION,
            "Actual package-lock root version != 0.5.17",
        )

        actual_release_prep_sha_before = {
            str(rel): sha256(ROOT / rel) for rel in RELEASE_PREP
        }

        # 2) Build Shadow from immutable HEAD, then overlay exact 70C Actual files.
        if SHADOW.exists():
            shutil.rmtree(SHADOW)
        rc, out = run(
            ["git", "clone", "--quiet", "--no-hardlinks", "--local", str(ROOT), str(SHADOW)],
            timeout=600,
        )
        require(rc == 0, f"Shadow local clone 실패\n{out[-3000:]}")
        require(git_text("rev-parse", "HEAD", cwd=SHADOW) == BASE_COMMIT, "Shadow HEAD 불일치")

        for rel in PRODUCT_ACTUAL:
            src_path = ROOT / rel
            dst_path = SHADOW / rel
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            dst_path.write_bytes(src_path.read_bytes())
            require(
                sha256(dst_path) == actual_sha[str(rel)],
                f"Shadow 70C overlay SHA 불일치: {rel}",
            )

        # 3) Release-prep Shadow: exact three-file delta.
        pkg_sha = patch_package_json(SHADOW / "electron/package.json")
        lock_sha = patch_package_lock(SHADOW / "electron/package-lock.json")
        info_50d = patch_50d(SHADOW / "50D_validate_kdrg_electron_windows_packaging.py")

        shadow_pkg = json.loads((SHADOW / "electron/package.json").read_text(encoding="utf-8"))
        shadow_lock = json.loads((SHADOW / "electron/package-lock.json").read_text(encoding="utf-8"))
        require(shadow_pkg.get("version") == TARGET_VERSION, "Shadow package 0.5.18 적용 실패")
        require(shadow_lock.get("version") == TARGET_VERSION, "Shadow package-lock top 0.5.18 적용 실패")
        require(
            shadow_lock.get("packages", {}).get("", {}).get("version") == TARGET_VERSION,
            "Shadow package-lock root 0.5.18 적용 실패",
        )

        # Syntax guards.
        for rel in [
            Path("electron/renderer/app.js"),
            Path("electron/tests/validate-stage70b-0518-phase1-ui.js"),
            Path("electron/tests/validate-stage69b-0517-search-relation-ux.js"),
            Path("electron/tests/validate-stage68d-0516-classification-derived-aadrg.js"),
        ]:
            node_check(rel, SHADOW)
        compile(
            (SHADOW / "50D_validate_kdrg_electron_windows_packaging.py").read_text(encoding="utf-8"),
            str(SHADOW / "50D_validate_kdrg_electron_windows_packaging.py"),
            "exec",
        )

        # 4) Full 0.5.18 release-prep validation chain.
        validations = [
            ("stage70b_validator", ["node", "tests/validate-stage70b-0518-phase1-ui.js"], SHADOW / "electron"),
            ("stage69b_validator", ["node", "tests/validate-stage69b-0517-search-relation-ux.js"], SHADOW / "electron"),
            ("stage68d_validator", ["node", "tests/validate-stage68d-0516-classification-derived-aadrg.js"], SHADOW / "electron"),
            ("npm_check", ["npm", "run", "check"], SHADOW / "electron"),
            ("50B", ["python", "50B_validate_kdrg_electron_search_service.py"], SHADOW),
            ("50C", ["python", "50C_validate_kdrg_electron_renderer_ui.py"], SHADOW),
            ("50D", ["python", "50D_validate_kdrg_electron_windows_packaging.py"], SHADOW),
            ("release_version_0518", ["node", "tests/validate-release-version.js", TARGET_VERSION], SHADOW / "electron"),
        ]

        command_paths = [
            SHADOW / "electron/tests/validate-stage70b-0518-phase1-ui.js",
            SHADOW / "electron/tests/validate-stage69b-0517-search-relation-ux.js",
            SHADOW / "electron/tests/validate-stage68d-0516-classification-derived-aadrg.js",
            SHADOW / "electron/package.json",
            SHADOW / "50B_validate_kdrg_electron_search_service.py",
            SHADOW / "50C_validate_kdrg_electron_renderer_ui.py",
            SHADOW / "50D_validate_kdrg_electron_windows_packaging.py",
            SHADOW / "electron/tests/validate-release-version.js",
        ]
        for path in command_paths:
            require(path.is_file(), f"검증 명령 경로 없음: {path.relative_to(SHADOW)}")

        results = []
        failures = []
        for name, cmd, cwd in validations:
            rc, output = run(cmd, cwd=cwd, timeout=1200)
            results.append({
                "name": name,
                "rc": rc,
                "status": "PASS" if rc == 0 else "FAIL",
                "tail": output[-8000:],
            })
            if rc != 0:
                failures.append(f"{name} FAIL\n{output[-6000:]}")

        if failures:
            raise Stop(
                "Release-prep Shadow 검증 실패를 전체 수집함\n\n"
                + "\n\n".join(failures)
            )

        # 5) Exact final release-candidate scope: 6 files only.
        shadow_modified, shadow_untracked, shadow_raw = scoped_status(SHADOW)
        require(
            shadow_modified == EXPECTED_MODIFIED_TRACKED,
            f"Shadow modified tracked 범위 불일치: actual={shadow_modified}, expected={EXPECTED_MODIFIED_TRACKED}",
        )
        require(
            shadow_untracked == EXPECTED_UNTRACKED,
            f"Shadow untracked 범위 불일치: actual={shadow_untracked}, expected={EXPECTED_UNTRACKED}",
        )

        shadow_candidate_sha = {
            str(rel): sha256(SHADOW / rel) for rel in FINAL_RELEASE_FILES
        }

        for rel in PRODUCT_ACTUAL:
            require(
                sha256(SHADOW / rel) == sha256(ROOT / rel),
                f"Release-prep가 70C 제품파일을 추가 변경함: {rel}",
            )
        for rel in RELEASE_PREP:
            require(
                sha256(SHADOW / rel) != sha256(ROOT / rel),
                f"Release-prep 대상이 변경되지 않음: {rel}",
            )

        # 6) Actual workspace must remain untouched by this Shadow stage.
        require(sha256(ROOT / RUNTIME_REL) == RUNTIME_SHA, "Actual 운영 JSON 변경됨")
        actual_pkg_after = json.loads((ROOT / "electron/package.json").read_text(encoding="utf-8"))
        actual_lock_after = json.loads((ROOT / "electron/package-lock.json").read_text(encoding="utf-8"))
        require(actual_pkg_after.get("version") == BASE_VERSION, "Shadow가 Actual package version을 변경함")
        require(actual_lock_after.get("version") == BASE_VERSION, "Shadow가 Actual package-lock version을 변경함")
        require(
            actual_lock_after.get("packages", {}).get("", {}).get("version") == BASE_VERSION,
            "Shadow가 Actual package-lock root version을 변경함",
        )
        for rel in RELEASE_PREP:
            require(
                sha256(ROOT / rel) == actual_release_prep_sha_before[str(rel)],
                f"Shadow가 Actual release-prep 파일을 변경함: {rel}",
            )

        final_modified, final_untracked, final_raw = scoped_status(ROOT)
        require(final_modified == current_modified, "Shadow 후 Actual tracked 상태 변경됨")
        require(final_untracked == current_untracked, "Shadow 후 Actual untracked 상태 변경됨")
        require(
            not [x for x in git_text("diff", "--cached", "--name-only").splitlines() if x],
            "Shadow 단계에서 staging 변경 발생",
        )

        report.update({
            "status": "PASS",
            "readiness": "READY_FOR_70E_0518_RELEASE_PREP_ACTUAL",
            "head": head,
            "origin_main": origin_main,
            "base_version": BASE_VERSION,
            "target_version": TARGET_VERSION,
            "actual_product_files": [str(x) for x in PRODUCT_ACTUAL],
            "release_prep_files": [str(x) for x in RELEASE_PREP],
            "final_release_files": [str(x) for x in FINAL_RELEASE_FILES],
            "shadow_modified_tracked": shadow_modified,
            "shadow_untracked": shadow_untracked,
            "shadow_candidate_sha256": shadow_candidate_sha,
            "release_prep_sha256": {
                "electron/package.json": pkg_sha,
                "electron/package-lock.json": lock_sha,
                "50D_validate_kdrg_electron_windows_packaging.py": info_50d["sha256"],
            },
            "validator_50d_migration": info_50d,
            "checks": results,
            "runtime_json": "UNCHANGED",
            "actual_package_version": BASE_VERSION,
            "actual_staging": "EMPTY",
            "actual_performed": False,
        })

        REPORT_JSON.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        lines = [
            "[PASS] Stage70D R1 / 0.5.18 Release Prep Shadow",
            "stage70c_actual_binding=PASS",
            "shadow_version_package_package_lock=0.5.18",
            f"50D_version_occurrences_migrated={info_50d['old_version_occurrences']}",
            f"50D_script_version={info_50d['script_version_after']}",
            "release_prep_delta_files=3",
            "final_release_candidate_files=6",
            "phase1_ui=PRESERVED",
            "general_adrg_classification=RIGHT",
            "relation_classification=RIGHT",
            "stage70b_validator=PASS",
            "stage69b_validator=PASS",
            "stage68d_validator=PASS",
            "npm_check=PASS",
            "50B_50C_50D=PASS",
            "release_version_0.5.18=PASS",
            "runtime_json=UNCHANGED",
            "actual_package_version=0.5.17",
            "actual_staging=EMPTY",
            "actual=NOT_PERFORMED",
            "readiness=READY_FOR_70E_0518_RELEASE_PREP_ACTUAL",
            f"report={REPORT_TXT.relative_to(ROOT)}",
            f"json={REPORT_JSON.relative_to(ROOT)}",
        ]
        REPORT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("\n".join(lines))
        return 0

    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        REPORT_JSON.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        lines = [
            "[FAIL] Stage70D Release Prep Shadow — Actual 미수행",
            f"{type(exc).__name__}: {exc}",
            f"report={REPORT_TXT.relative_to(ROOT)}",
        ]
        REPORT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("\n".join(lines))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
