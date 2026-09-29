from __future__ import annotations

import copy
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent

BASE_COMMIT = "1bd70d50c85305e2ff64ebb0a17ec619719e8a40"
BASE_VERSION = "0.5.18"
TARGET_VERSION = "0.5.19"
BASE_TAG = "electron-v0.5.18"

RUNTIME_REL = Path("data/kdrg_v47_search_integrated_v3.json")
RUNTIME_SHA = "1a3d50400567ecaad9695b7be8e7c0382131f8652f398e010cf01f4d8dda6c58"

ACTUAL_SCRIPT = ROOT / "72C_APPLY_KDRG_0519_RELATION_RESULT_LAYOUT_ACTUAL_R1.py"
ACTUAL_SCRIPT_SHA = "4f78a558fd4f6aa0f7d1b40877ce768549fbd23ac08426aa9162c200fd618b43"
ACTUAL_REPORT = ROOT / "reports/stage72c_0519_relation_result_layout_actual_r1/actual.json"

APP_REL = Path("electron/renderer/app.js")
CSS_REL = Path("electron/renderer/styles.css")
OLD_VALIDATOR_REL = Path("electron/tests/validate-stage70b-0518-phase1-ui.js")
NEW_VALIDATOR_REL = Path("electron/tests/validate-stage72b-0519-relation-result-layout.js")

PRODUCT_ACTUAL = [
    APP_REL,
    CSS_REL,
    OLD_VALIDATOR_REL,
    NEW_VALIDATOR_REL,
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
    APP_REL,
    CSS_REL,
    OLD_VALIDATOR_REL,
])

EXPECTED_UNTRACKED = [str(NEW_VALIDATOR_REL)]

REPORT_DIR = ROOT / "reports/stage72d_0519_release_prep_shadow_r1"
SHADOW = REPORT_DIR / "shadow"
REPORT_JSON = REPORT_DIR / "shadow.json"
REPORT_TXT = REPORT_DIR / "shadow_summary.txt"


class Stop(RuntimeError):
    pass


def require(ok, message):
    if not ok:
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


def write_json(path: Path, data):
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
    write_json(path, new)

    reread = json.loads(path.read_text(encoding="utf-8"))
    expected = copy.deepcopy(old)
    expected["version"] = TARGET_VERSION
    require(
        reread == expected,
        "package.json에서 version 외 구조 변경 발생",
    )
    return sha256(path)


def patch_package_lock(path: Path):
    old = json.loads(path.read_text(encoding="utf-8"))
    require(
        old.get("version") == BASE_VERSION,
        f"package-lock top version 불일치: {old.get('version')}",
    )
    require(
        (old.get("packages") or {}).get("", {}).get("version")
        == BASE_VERSION,
        "package-lock root package version 불일치",
    )

    new = copy.deepcopy(old)
    new["version"] = TARGET_VERSION
    new["packages"][""]["version"] = TARGET_VERSION
    write_json(path, new)

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
    require(
        old_count >= 1,
        f"50D에서 {BASE_VERSION} version anchor를 찾지 못함",
    )

    candidate = source.replace(BASE_VERSION, TARGET_VERSION)

    match = re.search(
        r'(?m)^SCRIPT_VERSION\s*=\s*(["\'])(?P<value>[^"\']+)\1\s*$',
        candidate,
    )
    require(match is not None, "50D SCRIPT_VERSION line 없음")

    before = match.group("value")
    after = before.replace("0518", "0519")
    if after != before:
        candidate = candidate.replace(before, after, 1)

    require(
        BASE_VERSION not in candidate,
        f"50D에 {BASE_VERSION} expectation 잔존",
    )
    require(
        TARGET_VERSION in candidate,
        f"50D에 {TARGET_VERSION} expectation 없음",
    )

    path.write_text(candidate, encoding="utf-8")
    compile(candidate, str(path), "exec")

    return {
        "old_version_occurrences": old_count,
        "script_version_before": before,
        "script_version_after": after,
        "sha256": sha256(path),
    }


def scoped_status(cwd: Path):
    rc, out = run(
        [
            "git",
            "status",
            "--porcelain=v1",
            "--",
            *[str(x) for x in FINAL_RELEASE_FILES],
        ],
        cwd=cwd,
        timeout=120,
    )
    require(rc == 0, f"git status 실패\n{out[-3000:]}")

    modified = []
    untracked = []

    for line in out.splitlines():
        if not line:
            continue
        status = line[:2]
        name = line[3:]
        if status == "??":
            untracked.append(name)
        else:
            modified.append(name)

    return sorted(modified), sorted(untracked)


def node_check(rel: Path, cwd: Path):
    rc, out = run(
        ["node", "--check", str(rel)],
        cwd=cwd,
        timeout=120,
    )
    require(
        rc == 0,
        f"node --check FAIL: {rel}\n{out[-3000:]}",
    )


def main():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    report = {
        "stage": "72D_0519_RELEASE_PREP_SHADOW_R1",
        "status": "FAIL",
        "actual_performed": False,
    }

    try:
        # ------------------------------------------------------------
        # 1. Baseline + exact 72C binding
        # ------------------------------------------------------------
        head = git_text("rev-parse", "HEAD")
        origin_main = git_text("rev-parse", "origin/main")
        branch = git_text("branch", "--show-current")
        staged = [
            x
            for x in git_text(
                "diff",
                "--cached",
                "--name-only",
            ).splitlines()
            if x
        ]

        require(head == BASE_COMMIT, f"HEAD 불일치: {head}")
        require(
            origin_main == BASE_COMMIT,
            f"origin/main 불일치: {origin_main}",
        )
        require(branch == "main", f"branch 불일치: {branch}")
        require(not staged, f"staging 변경 있음: {staged}")
        require(
            sha256(ROOT / RUNTIME_REL) == RUNTIME_SHA,
            "운영 JSON SHA 불일치",
        )
        require(
            git_text("rev-list", "-n", "1", BASE_TAG)
            == BASE_COMMIT,
            f"{BASE_TAG} local tag 불일치",
        )

        require(
            ACTUAL_SCRIPT.is_file(),
            "72C Actual 작업파일 없음",
        )
        require(
            sha256(ACTUAL_SCRIPT) == ACTUAL_SCRIPT_SHA,
            "72C Actual 작업파일 SHA 불일치",
        )
        require(
            ACTUAL_REPORT.is_file(),
            "72C actual.json 없음",
        )

        actual = json.loads(
            ACTUAL_REPORT.read_text(encoding="utf-8")
        )
        require(
            actual.get("status") == "PASS",
            "72C Actual status != PASS",
        )
        require(
            actual.get("readiness")
            == "READY_FOR_72D_0519_RELEASE_PREP_SHADOW",
            f"72C readiness 불일치: {actual.get('readiness')}",
        )
        require(
            actual.get("base_commit") == BASE_COMMIT,
            "72C base commit 불일치",
        )
        require(
            actual.get("base_version") == BASE_VERSION,
            "72C base version 불일치",
        )
        require(
            actual.get("next_version") == TARGET_VERSION,
            "72C target version 불일치",
        )
        require(
            actual.get("package_version") == BASE_VERSION,
            "72C package version 불일치",
        )
        require(
            actual.get("runtime_json") == "UNCHANGED",
            "72C runtime 계약 불일치",
        )
        require(
            sorted(actual.get("applied_files") or [])
            == sorted(str(x) for x in PRODUCT_ACTUAL),
            "72C 적용파일 범위 불일치",
        )

        checks = actual.get("checks") or []
        require(
            checks and all(x.get("status") == "PASS" for x in checks),
            "72C validation chain 불완전",
        )

        actual_sha = actual.get("actual_sha256") or {}
        for rel in PRODUCT_ACTUAL:
            path = ROOT / rel
            require(path.is_file(), f"제품파일 없음: {rel}")
            require(
                actual_sha.get(str(rel)) == sha256(path),
                f"72C actual SHA 불일치: {rel}",
            )

        # ------------------------------------------------------------
        # 2. Current Actual scope = 3 tracked + 1 untracked
        # ------------------------------------------------------------
        current_modified, current_untracked = scoped_status(ROOT)

        expected_current_modified = sorted(str(x) for x in [
            APP_REL,
            CSS_REL,
            OLD_VALIDATOR_REL,
        ])
        expected_current_untracked = [str(NEW_VALIDATOR_REL)]

        require(
            current_modified == expected_current_modified,
            (
                "72C tracked 범위 불일치: "
                f"actual={current_modified}, "
                f"expected={expected_current_modified}"
            ),
        )
        require(
            current_untracked == expected_current_untracked,
            (
                "72C untracked 범위 불일치: "
                f"actual={current_untracked}, "
                f"expected={expected_current_untracked}"
            ),
        )

        # Release-prep files must still be pristine 0.5.18 HEAD.
        for rel in RELEASE_PREP:
            require(
                (ROOT / rel).is_file(),
                f"release-prep 기준파일 없음: {rel}",
            )
            require(
                (ROOT / rel).read_bytes() == git_show_bytes(rel),
                f"release-prep 기준파일이 HEAD와 다름: {rel}",
            )

        pkg_actual = json.loads(
            (ROOT / "electron/package.json").read_text(encoding="utf-8")
        )
        lock_actual = json.loads(
            (ROOT / "electron/package-lock.json").read_text(encoding="utf-8")
        )

        require(
            pkg_actual.get("version") == BASE_VERSION,
            "Actual package version != 0.5.18",
        )
        require(
            lock_actual.get("version") == BASE_VERSION,
            "Actual package-lock version != 0.5.18",
        )
        require(
            lock_actual.get("packages", {}).get("", {}).get("version")
            == BASE_VERSION,
            "Actual package-lock root version != 0.5.18",
        )

        release_prep_before = {
            str(rel): sha256(ROOT / rel)
            for rel in RELEASE_PREP
        }

        # ------------------------------------------------------------
        # 3. Build Shadow from HEAD + overlay exact 72C product files
        # ------------------------------------------------------------
        if SHADOW.exists():
            shutil.rmtree(SHADOW)

        rc, out = run(
            [
                "git",
                "clone",
                "--quiet",
                "--no-hardlinks",
                "--local",
                str(ROOT),
                str(SHADOW),
            ],
            timeout=600,
        )
        require(
            rc == 0,
            f"Shadow clone 실패\n{out[-3000:]}",
        )
        require(
            git_text("rev-parse", "HEAD", cwd=SHADOW)
            == BASE_COMMIT,
            "Shadow HEAD 불일치",
        )

        for rel in PRODUCT_ACTUAL:
            src = ROOT / rel
            dst = SHADOW / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(src.read_bytes())
            require(
                sha256(dst) == actual_sha[str(rel)],
                f"Shadow overlay SHA 불일치: {rel}",
            )

        # ------------------------------------------------------------
        # 4. Release prep: exact 3-file Shadow delta
        # ------------------------------------------------------------
        pkg_sha = patch_package_json(
            SHADOW / "electron/package.json"
        )
        lock_sha = patch_package_lock(
            SHADOW / "electron/package-lock.json"
        )
        info_50d = patch_50d(
            SHADOW / "50D_validate_kdrg_electron_windows_packaging.py"
        )

        shadow_pkg = json.loads(
            (SHADOW / "electron/package.json").read_text(encoding="utf-8")
        )
        shadow_lock = json.loads(
            (SHADOW / "electron/package-lock.json").read_text(encoding="utf-8")
        )

        require(
            shadow_pkg.get("version") == TARGET_VERSION,
            "Shadow package 0.5.19 적용 실패",
        )
        require(
            shadow_lock.get("version") == TARGET_VERSION,
            "Shadow package-lock top 0.5.19 적용 실패",
        )
        require(
            shadow_lock.get("packages", {}).get("", {}).get("version")
            == TARGET_VERSION,
            "Shadow package-lock root 0.5.19 적용 실패",
        )

        # Syntax
        for rel in [
            APP_REL,
            OLD_VALIDATOR_REL,
            NEW_VALIDATOR_REL,
        ]:
            node_check(rel, SHADOW)

        compile(
            (
                SHADOW
                / "50D_validate_kdrg_electron_windows_packaging.py"
            ).read_text(encoding="utf-8"),
            str(
                SHADOW
                / "50D_validate_kdrg_electron_windows_packaging.py"
            ),
            "exec",
        )

        # ------------------------------------------------------------
        # 5. Full release-prep validation
        # ------------------------------------------------------------
        validations = [
            (
                "stage72b_validator",
                [
                    "node",
                    "tests/validate-stage72b-0519-relation-result-layout.js",
                ],
                SHADOW / "electron",
            ),
            (
                "stage70b_validator",
                [
                    "node",
                    "tests/validate-stage70b-0518-phase1-ui.js",
                ],
                SHADOW / "electron",
            ),
            (
                "stage69b_validator",
                [
                    "node",
                    "tests/validate-stage69b-0517-search-relation-ux.js",
                ],
                SHADOW / "electron",
            ),
            (
                "stage68d_validator",
                [
                    "node",
                    "tests/validate-stage68d-0516-classification-derived-aadrg.js",
                ],
                SHADOW / "electron",
            ),
            (
                "npm_check",
                ["npm", "run", "check"],
                SHADOW / "electron",
            ),
            (
                "50B",
                ["python", "50B_validate_kdrg_electron_search_service.py"],
                SHADOW,
            ),
            (
                "50C",
                ["python", "50C_validate_kdrg_electron_renderer_ui.py"],
                SHADOW,
            ),
            (
                "50D",
                ["python", "50D_validate_kdrg_electron_windows_packaging.py"],
                SHADOW,
            ),
            (
                "release_version_0519",
                [
                    "node",
                    "tests/validate-release-version.js",
                    TARGET_VERSION,
                ],
                SHADOW / "electron",
            ),
        ]

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
                failures.append(
                    f"{name} FAIL\n{output[-6000:]}"
                )

        if failures:
            raise Stop(
                "Release-prep Shadow 검증 실패를 전체 수집함\n\n"
                + "\n\n".join(failures)
            )

        # ------------------------------------------------------------
        # 6. Exact final candidate scope = 7
        # ------------------------------------------------------------
        shadow_modified, shadow_untracked = scoped_status(SHADOW)

        require(
            shadow_modified == EXPECTED_MODIFIED_TRACKED,
            (
                "Shadow tracked 범위 불일치: "
                f"actual={shadow_modified}, "
                f"expected={EXPECTED_MODIFIED_TRACKED}"
            ),
        )
        require(
            shadow_untracked == EXPECTED_UNTRACKED,
            (
                "Shadow untracked 범위 불일치: "
                f"actual={shadow_untracked}, "
                f"expected={EXPECTED_UNTRACKED}"
            ),
        )

        shadow_candidate_sha = {
            str(rel): sha256(SHADOW / rel)
            for rel in FINAL_RELEASE_FILES
        }

        # No extra mutation to 72C product files.
        for rel in PRODUCT_ACTUAL:
            require(
                sha256(SHADOW / rel) == sha256(ROOT / rel),
                f"Release-prep가 72C 제품파일을 변경함: {rel}",
            )

        # Exactly 3 prep files changed.
        for rel in RELEASE_PREP:
            require(
                sha256(SHADOW / rel) != sha256(ROOT / rel),
                f"Release-prep 대상 변경 없음: {rel}",
            )

        # ------------------------------------------------------------
        # 7. Actual workspace untouched
        # ------------------------------------------------------------
        require(
            sha256(ROOT / RUNTIME_REL) == RUNTIME_SHA,
            "Actual 운영 JSON 변경됨",
        )

        actual_pkg_after = json.loads(
            (ROOT / "electron/package.json").read_text(encoding="utf-8")
        )
        actual_lock_after = json.loads(
            (ROOT / "electron/package-lock.json").read_text(encoding="utf-8")
        )

        require(
            actual_pkg_after.get("version") == BASE_VERSION,
            "Shadow가 Actual package version 변경",
        )
        require(
            actual_lock_after.get("version") == BASE_VERSION,
            "Shadow가 Actual package-lock top 변경",
        )
        require(
            actual_lock_after.get("packages", {}).get("", {}).get("version")
            == BASE_VERSION,
            "Shadow가 Actual package-lock root 변경",
        )

        for rel in RELEASE_PREP:
            require(
                sha256(ROOT / rel) == release_prep_before[str(rel)],
                f"Shadow가 Actual release-prep 파일 변경: {rel}",
            )

        final_modified, final_untracked = scoped_status(ROOT)
        require(
            final_modified == current_modified,
            "Shadow 후 Actual tracked 상태 변경",
        )
        require(
            final_untracked == current_untracked,
            "Shadow 후 Actual untracked 상태 변경",
        )
        require(
            not [
                x
                for x in git_text(
                    "diff",
                    "--cached",
                    "--name-only",
                ).splitlines()
                if x
            ],
            "Shadow 단계에서 staging 변경 발생",
        )

        report.update({
            "status": "PASS",
            "readiness": "READY_FOR_72E_0519_RELEASE_PREP_ACTUAL",
            "head": head,
            "origin_main": origin_main,
            "base_version": BASE_VERSION,
            "target_version": TARGET_VERSION,
            "actual_product_files": [
                str(x) for x in PRODUCT_ACTUAL
            ],
            "release_prep_files": [
                str(x) for x in RELEASE_PREP
            ],
            "final_release_files": [
                str(x) for x in FINAL_RELEASE_FILES
            ],
            "shadow_modified_tracked": shadow_modified,
            "shadow_untracked": shadow_untracked,
            "shadow_candidate_sha256": shadow_candidate_sha,
            "release_prep_sha256": {
                "electron/package.json": pkg_sha,
                "electron/package-lock.json": lock_sha,
                "50D_validate_kdrg_electron_windows_packaging.py":
                    info_50d["sha256"],
            },
            "validator_50d_migration": info_50d,
            "checks": results,
            "runtime_json": "UNCHANGED",
            "actual_package_version": BASE_VERSION,
            "actual_staging": "EMPTY",
            "actual_performed": False,
        })

        write_json(REPORT_JSON, report)

        lines = [
            "[PASS] Stage72D R1 / 0.5.19 Release Prep Shadow",
            "stage72c_actual_binding=PASS",
            "shadow_version_package_package_lock=0.5.19",
            f"50D_version_occurrences_migrated={info_50d['old_version_occurrences']}",
            f"50D_script_version={info_50d['script_version_after']}",
            "release_prep_delta_files=3",
            "final_release_candidate_files=7",
            "relation_layout_0519=PRESERVED",
            "general_adrg_layout=PRESERVED",
            "stage72b_validator=PASS",
            "stage70b_validator=PASS",
            "stage69b_validator=PASS",
            "stage68d_validator=PASS",
            "npm_check=PASS",
            "50B_50C_50D=PASS",
            "release_version_0.5.19=PASS",
            "runtime_json=UNCHANGED",
            "actual_package_version=0.5.18",
            "actual_staging=EMPTY",
            "actual=NOT_PERFORMED",
            "readiness=READY_FOR_72E_0519_RELEASE_PREP_ACTUAL",
            f"report={REPORT_TXT.relative_to(ROOT)}",
            f"json={REPORT_JSON.relative_to(ROOT)}",
        ]

        REPORT_TXT.write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )
        print("\n".join(lines))
        return 0

    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        write_json(REPORT_JSON, report)

        lines = [
            "[FAIL] Stage72D 0.5.19 Release Prep Shadow — Actual 미수행",
            f"{type(exc).__name__}: {exc}",
            f"report={REPORT_TXT.relative_to(ROOT)}",
        ]
        REPORT_TXT.write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )
        print("\n".join(lines))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
