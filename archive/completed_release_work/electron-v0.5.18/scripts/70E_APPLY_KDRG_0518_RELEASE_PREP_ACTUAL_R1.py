from __future__ import annotations

import hashlib
import json
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

ACTUAL_70C_SCRIPT = ROOT / "70C_APPLY_KDRG_0518_PHASE1_UI_ACTUAL_R2.py"
ACTUAL_70C_SCRIPT_SHA = "e7eb32e701c639ce75da8a572742a288aedd5dd1e5d5edc4815f0de8c4b14fc0"
ACTUAL_70C_REPORT = ROOT / "reports/stage70c_0518_phase1_ui_actual_r2/actual.json"

SHADOW_70D_SCRIPT = ROOT / "70D_PREP_KDRG_0518_RELEASE_SHADOW_R1.py"
SHADOW_70D_SCRIPT_SHA = "6789f2a3b389bb3445b261ac245f0775d40fc82fc25dca53d37f132b17d230b3"
SHADOW_70D_DIR = ROOT / "reports/stage70d_0518_release_prep_shadow_r1"
SHADOW_70D_ROOT = SHADOW_70D_DIR / "shadow"
SHADOW_70D_REPORT = SHADOW_70D_DIR / "shadow.json"
SHADOW_70D_SUMMARY = SHADOW_70D_DIR / "shadow_summary.txt"

REPORT_DIR = ROOT / "reports/stage70e_0518_release_prep_actual_r1"
REPORT_JSON = REPORT_DIR / "actual.json"
REPORT_TXT = REPORT_DIR / "actual_summary.txt"
BACKUP_DIR = REPORT_DIR / "backup"

PRODUCT_70C = [
    Path("electron/renderer/app.js"),
    Path("electron/renderer/styles.css"),
    Path("electron/tests/validate-stage70b-0518-phase1-ui.js"),
]

RELEASE_PREP = [
    Path("50D_validate_kdrg_electron_windows_packaging.py"),
    Path("electron/package.json"),
    Path("electron/package-lock.json"),
]

FINAL_RELEASE_FILES = PRODUCT_70C + RELEASE_PREP

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

GENERATED_REPORTS = [
    Path("reports/electron_stage50b_validation_report.json"),
    Path("reports/electron_stage50b_validation_report.txt"),
    Path("reports/electron_stage50c_validation_report.json"),
    Path("reports/electron_stage50c_validation_report.txt"),
    Path("reports/electron_stage50d_validation_report.json"),
    Path("reports/electron_stage50d_validation_report.txt"),
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


def snapshot_paths(paths):
    snapshots = {}
    for rel in paths:
        path = ROOT / rel
        snapshots[str(rel)] = {
            "exists": path.exists(),
            "bytes": path.read_bytes() if path.exists() else None,
        }
    return snapshots


def restore_paths(snapshots):
    for rel_text, snap in snapshots.items():
        path = ROOT / rel_text
        if snap["exists"]:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(snap["bytes"])
        elif path.exists():
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()


def scoped_status():
    rc, out = run(
        [
            "git",
            "status",
            "--porcelain=v1",
            "--",
            *[str(x) for x in FINAL_RELEASE_FILES],
        ],
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


def node_check(rel_from_electron: Path):
    rc, out = run(
        ["node", "--check", str(rel_from_electron)],
        cwd=ROOT / "electron",
        timeout=120,
    )
    require(
        rc == 0,
        f"node --check FAIL: {rel_from_electron}\n{out[-3000:]}",
    )


def run_full_validation():
    checks = [
        (
            "stage70b_validator",
            ["node", "tests/validate-stage70b-0518-phase1-ui.js"],
            ROOT / "electron",
        ),
        (
            "stage69b_validator",
            ["node", "tests/validate-stage69b-0517-search-relation-ux.js"],
            ROOT / "electron",
        ),
        (
            "stage68d_validator",
            ["node", "tests/validate-stage68d-0516-classification-derived-aadrg.js"],
            ROOT / "electron",
        ),
        (
            "npm_check",
            ["npm", "run", "check"],
            ROOT / "electron",
        ),
        (
            "50B",
            ["python", "50B_validate_kdrg_electron_search_service.py"],
            ROOT,
        ),
        (
            "50C",
            ["python", "50C_validate_kdrg_electron_renderer_ui.py"],
            ROOT,
        ),
        (
            "50D",
            ["python", "50D_validate_kdrg_electron_windows_packaging.py"],
            ROOT,
        ),
        (
            "release_version_0518",
            [
                "node",
                "tests/validate-release-version.js",
                TARGET_VERSION,
            ],
            ROOT / "electron",
        ),
    ]

    required = [
        ROOT / "electron/tests/validate-stage70b-0518-phase1-ui.js",
        ROOT / "electron/tests/validate-stage69b-0517-search-relation-ux.js",
        ROOT / "electron/tests/validate-stage68d-0516-classification-derived-aadrg.js",
        ROOT / "electron/package.json",
        ROOT / "50B_validate_kdrg_electron_search_service.py",
        ROOT / "50C_validate_kdrg_electron_renderer_ui.py",
        ROOT / "50D_validate_kdrg_electron_windows_packaging.py",
        ROOT / "electron/tests/validate-release-version.js",
    ]

    for path in required:
        require(
            path.is_file(),
            f"검증 필수파일 없음: {path.relative_to(ROOT)}",
        )

    results = []
    failures = []

    for name, cmd, cwd in checks:
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

    return results, failures


def main():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    report = {
        "stage": "70E_RELEASE_PREP_ACTUAL_R1",
        "status": "FAIL",
        "actual_performed": False,
        "rollback_performed": False,
    }

    prep_snapshot = None
    report_snapshot = None
    actual_written = False

    try:
        # ------------------------------------------------------------
        # 1) Bind to exact 70C Actual + 70D Shadow PASS
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
        require(origin_main == BASE_COMMIT, f"origin/main 불일치: {origin_main}")
        require(branch == "main", f"branch 불일치: {branch}")
        require(not staged, f"staging 변경 있음: {staged}")
        require(
            sha256(ROOT / RUNTIME_REL) == RUNTIME_SHA,
            "운영 JSON SHA 불일치",
        )

        local_tag = git_text("rev-list", "-n", "1", BASE_TAG)
        require(
            local_tag == BASE_COMMIT,
            f"{BASE_TAG} local tag commit 불일치",
        )
        remote_tag_line = git_text(
            "ls-remote",
            "--tags",
            "origin",
            f"refs/tags/{BASE_TAG}",
        )
        require(
            remote_tag_line.startswith(BASE_COMMIT),
            f"{BASE_TAG} remote tag commit 불일치",
        )

        require(
            ACTUAL_70C_SCRIPT.is_file(),
            "70C Actual 작업파일 없음",
        )
        require(
            sha256(ACTUAL_70C_SCRIPT) == ACTUAL_70C_SCRIPT_SHA,
            "70C Actual 작업파일 SHA 불일치",
        )
        require(
            ACTUAL_70C_REPORT.is_file(),
            "70C actual.json 없음",
        )

        actual70c = json.loads(
            ACTUAL_70C_REPORT.read_text(encoding="utf-8")
        )

        require(
            actual70c.get("status") == "PASS",
            "70C Actual status != PASS",
        )
        require(
            actual70c.get("readiness")
            == "READY_FOR_70D_0518_RELEASE_PREP_SHADOW",
            f"70C Actual readiness 불일치: {actual70c.get('readiness')}",
        )
        require(
            actual70c.get("runtime_json") == "UNCHANGED",
            "70C runtime JSON 계약 불일치",
        )
        require(
            actual70c.get("rollback") == "NOT_NEEDED",
            "70C rollback 상태 불일치",
        )

        require(
            SHADOW_70D_SCRIPT.is_file(),
            "70D Shadow 작업파일 없음",
        )
        require(
            sha256(SHADOW_70D_SCRIPT) == SHADOW_70D_SCRIPT_SHA,
            "70D Shadow 작업파일 SHA 불일치",
        )
        require(
            SHADOW_70D_REPORT.is_file(),
            "70D shadow.json 없음",
        )
        require(
            SHADOW_70D_SUMMARY.is_file(),
            "70D shadow_summary.txt 없음",
        )
        require(
            SHADOW_70D_ROOT.is_dir(),
            "70D Shadow 후보 디렉터리 없음",
        )

        shadow70d = json.loads(
            SHADOW_70D_REPORT.read_text(encoding="utf-8")
        )
        shadow_summary = SHADOW_70D_SUMMARY.read_text(encoding="utf-8")

        require(
            shadow70d.get("status") == "PASS",
            "70D Shadow status != PASS",
        )
        require(
            shadow70d.get("readiness")
            == "READY_FOR_70E_0518_RELEASE_PREP_ACTUAL",
            f"70D Shadow readiness 불일치: {shadow70d.get('readiness')}",
        )
        require(
            shadow70d.get("head") == BASE_COMMIT,
            "70D Shadow HEAD 불일치",
        )
        require(
            shadow70d.get("origin_main") == BASE_COMMIT,
            "70D Shadow origin/main 불일치",
        )
        require(
            shadow70d.get("base_version") == BASE_VERSION,
            "70D base version 불일치",
        )
        require(
            shadow70d.get("target_version") == TARGET_VERSION,
            "70D target version 불일치",
        )
        require(
            shadow70d.get("runtime_json") == "UNCHANGED",
            "70D runtime JSON 계약 불일치",
        )
        require(
            shadow70d.get("actual_performed") is False,
            "70D actual_performed 불일치",
        )

        require(
            sorted(shadow70d.get("release_prep_files") or [])
            == sorted(str(x) for x in RELEASE_PREP),
            "70D release-prep 파일범위 불일치",
        )
        require(
            sorted(shadow70d.get("final_release_files") or [])
            == sorted(str(x) for x in FINAL_RELEASE_FILES),
            "70D final release 파일범위 불일치",
        )

        shadow_candidate_sha = (
            shadow70d.get("shadow_candidate_sha256") or {}
        )
        require(
            set(shadow_candidate_sha)
            == set(str(x) for x in FINAL_RELEASE_FILES),
            "70D candidate SHA manifest 범위 불일치",
        )

        for marker in (
            "shadow_version_package_package_lock=0.5.18",
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
            "readiness=READY_FOR_70E_0518_RELEASE_PREP_ACTUAL",
        ):
            require(
                marker in shadow_summary,
                f"70D PASS marker 없음: {marker}",
            )

        checks70d = shadow70d.get("checks") or []
        require(
            checks70d
            and all(x.get("status") == "PASS" for x in checks70d),
            "70D validation chain 불완전",
        )

        # ------------------------------------------------------------
        # 2) Confirm current worktree is exact 70C state
        # ------------------------------------------------------------
        current_modified, current_untracked = scoped_status()

        expected_70c_modified = sorted([
            "electron/renderer/app.js",
            "electron/renderer/styles.css",
        ])

        require(
            current_modified == expected_70c_modified,
            (
                "70C tracked 상태 불일치: "
                f"actual={current_modified}, "
                f"expected={expected_70c_modified}"
            ),
        )
        require(
            current_untracked == EXPECTED_UNTRACKED,
            (
                "70C untracked 상태 불일치: "
                f"actual={current_untracked}, "
                f"expected={EXPECTED_UNTRACKED}"
            ),
        )

        actual70c_sha = actual70c.get("actual_sha256") or {}
        require(
            set(actual70c_sha) == set(str(x) for x in PRODUCT_70C),
            "70C Actual SHA 범위 불일치",
        )

        for rel in PRODUCT_70C:
            actual_path = ROOT / rel
            shadow_path = SHADOW_70D_ROOT / rel

            require(
                actual_path.is_file(),
                f"70C 제품파일 없음: {rel}",
            )
            require(
                shadow_path.is_file(),
                f"70D Shadow 제품파일 없음: {rel}",
            )

            actual_sha = sha256(actual_path)

            require(
                actual70c_sha.get(str(rel)) == actual_sha,
                f"70C Actual SHA 불일치: {rel}",
            )
            require(
                shadow_candidate_sha.get(str(rel)) == actual_sha,
                f"70D Shadow가 70C 제품파일을 변경함: {rel}",
            )
            require(
                sha256(shadow_path) == actual_sha,
                f"70D Shadow 제품파일 bytes 불일치: {rel}",
            )

        # Release-prep Actual files must still be 0.5.17.
        for rel in RELEASE_PREP:
            actual_path = ROOT / rel
            shadow_path = SHADOW_70D_ROOT / rel

            require(
                actual_path.is_file(),
                f"Actual release-prep 기준파일 없음: {rel}",
            )
            require(
                shadow_path.is_file(),
                f"70D Shadow release-prep 후보 없음: {rel}",
            )
            require(
                sha256(shadow_path)
                == shadow_candidate_sha.get(str(rel)),
                f"70D Shadow candidate SHA 불일치: {rel}",
            )
            require(
                sha256(actual_path) != sha256(shadow_path),
                f"70D release-prep 후보가 Actual과 동일함: {rel}",
            )

        package_before = json.loads(
            (ROOT / "electron/package.json").read_text(encoding="utf-8")
        )
        lock_before = json.loads(
            (ROOT / "electron/package-lock.json").read_text(encoding="utf-8")
        )

        require(
            package_before.get("version") == BASE_VERSION,
            "Actual package != 0.5.17",
        )
        require(
            lock_before.get("version") == BASE_VERSION,
            "Actual package-lock != 0.5.17",
        )
        require(
            lock_before.get("packages", {}).get("", {}).get("version")
            == BASE_VERSION,
            "Actual package-lock root != 0.5.17",
        )

        # ------------------------------------------------------------
        # 3) Backup exactly what this Actual stage can mutate
        # ------------------------------------------------------------
        prep_snapshot = snapshot_paths(RELEASE_PREP)
        report_snapshot = snapshot_paths(GENERATED_REPORTS)

        if BACKUP_DIR.exists():
            shutil.rmtree(BACKUP_DIR)
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)

        backup_manifest = {}

        for rel in RELEASE_PREP:
            snap = prep_snapshot[str(rel)]
            backup_manifest[str(rel)] = {
                "existed": snap["exists"],
                "sha256": (
                    hashlib.sha256(snap["bytes"]).hexdigest()
                    if snap["bytes"] is not None
                    else None
                ),
            }

            if snap["exists"]:
                dst = BACKUP_DIR / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(snap["bytes"])

        # ------------------------------------------------------------
        # 4) Actual apply: exact three files from verified 70D Shadow
        # ------------------------------------------------------------
        for rel in RELEASE_PREP:
            src = SHADOW_70D_ROOT / rel
            dst = ROOT / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

        actual_written = True
        report["actual_performed"] = True

        for rel in RELEASE_PREP:
            require(
                sha256(ROOT / rel)
                == shadow_candidate_sha[str(rel)],
                f"Actual 적용 직후 70D candidate SHA 불일치: {rel}",
            )

        package_after = json.loads(
            (ROOT / "electron/package.json").read_text(encoding="utf-8")
        )
        lock_after = json.loads(
            (ROOT / "electron/package-lock.json").read_text(encoding="utf-8")
        )

        require(
            package_after.get("version") == TARGET_VERSION,
            "Actual package 0.5.18 적용 실패",
        )
        require(
            lock_after.get("version") == TARGET_VERSION,
            "Actual package-lock 0.5.18 적용 실패",
        )
        require(
            lock_after.get("packages", {}).get("", {}).get("version")
            == TARGET_VERSION,
            "Actual package-lock root 0.5.18 적용 실패",
        )

        compile(
            (
                ROOT
                / "50D_validate_kdrg_electron_windows_packaging.py"
            ).read_text(encoding="utf-8"),
            str(
                ROOT
                / "50D_validate_kdrg_electron_windows_packaging.py"
            ),
            "exec",
        )

        node_check(Path("renderer/app.js"))
        node_check(Path("tests/validate-stage70b-0518-phase1-ui.js"))

        # ------------------------------------------------------------
        # 5) Full validation chain on Actual 0.5.18 candidate
        # ------------------------------------------------------------
        results, failures = run_full_validation()

        if failures:
            raise Stop(
                "70E Actual 검증 실패를 전체 실행 후 수집함\n\n"
                + "\n\n".join(failures)
            )

        # ------------------------------------------------------------
        # 6) Final release-candidate guards
        # ------------------------------------------------------------
        require(
            sha256(ROOT / RUNTIME_REL) == RUNTIME_SHA,
            "Actual 후 운영 JSON 변경됨",
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
            "70E Actual에서 staging 변경 발생",
        )

        final_modified, final_untracked = scoped_status()

        require(
            final_modified == EXPECTED_MODIFIED_TRACKED,
            (
                "최종 tracked 변경범위 불일치: "
                f"actual={final_modified}, "
                f"expected={EXPECTED_MODIFIED_TRACKED}"
            ),
        )
        require(
            final_untracked == EXPECTED_UNTRACKED,
            (
                "최종 untracked 변경범위 불일치: "
                f"actual={final_untracked}, "
                f"expected={EXPECTED_UNTRACKED}"
            ),
        )

        final_sha = {}

        for rel in FINAL_RELEASE_FILES:
            require(
                (ROOT / rel).is_file(),
                f"최종 release 후보파일 없음: {rel}",
            )

            actual_sha = sha256(ROOT / rel)

            require(
                actual_sha == shadow_candidate_sha[str(rel)],
                f"최종 release 후보 SHA가 70D Shadow와 불일치: {rel}",
            )
            final_sha[str(rel)] = actual_sha

        report.update({
            "status": "PASS",
            "readiness": "READY_FOR_70F_0518_COMMIT_PUSH_RC",
            "rollback_performed": False,
            "head": head,
            "origin_main": origin_main,
            "package_version": TARGET_VERSION,
            "runtime_json": "UNCHANGED",
            "release_prep_files": [str(x) for x in RELEASE_PREP],
            "final_release_files": [str(x) for x in FINAL_RELEASE_FILES],
            "final_modified_tracked": final_modified,
            "final_untracked": final_untracked,
            "final_candidate_sha256": final_sha,
            "backup_manifest": backup_manifest,
            "checks": results,
        })

        REPORT_JSON.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        lines = [
            "[PASS] Stage70E R1 / 0.5.18 Release Prep Actual",
            "stage70c_actual_binding=PASS",
            "stage70d_shadow_binding=PASS",
            "release_prep_actual_files=3",
            "final_release_candidate_files=6",
            "package_version=0.5.18",
            "package_lock_version=0.5.18",
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
            "staging=EMPTY",
            "rollback=NOT_NEEDED",
            "readiness=READY_FOR_70F_0518_COMMIT_PUSH_RC",
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
        rollback_error = None

        if actual_written:
            try:
                if prep_snapshot is not None:
                    restore_paths(prep_snapshot)

                if report_snapshot is not None:
                    restore_paths(report_snapshot)

                actual70c = json.loads(
                    ACTUAL_70C_REPORT.read_text(encoding="utf-8")
                )
                actual70c_sha = actual70c.get("actual_sha256") or {}

                for rel in PRODUCT_70C:
                    require(
                        sha256(ROOT / rel)
                        == actual70c_sha.get(str(rel)),
                        f"rollback 후 70C 제품파일 변경됨: {rel}",
                    )

                pkg = json.loads(
                    (ROOT / "electron/package.json").read_text(
                        encoding="utf-8"
                    )
                )
                lock = json.loads(
                    (ROOT / "electron/package-lock.json").read_text(
                        encoding="utf-8"
                    )
                )

                require(
                    pkg.get("version") == BASE_VERSION,
                    "rollback 후 package != 0.5.17",
                )
                require(
                    lock.get("version") == BASE_VERSION,
                    "rollback 후 package-lock != 0.5.17",
                )
                require(
                    lock.get("packages", {}).get("", {}).get("version")
                    == BASE_VERSION,
                    "rollback 후 package-lock root != 0.5.17",
                )
                require(
                    sha256(ROOT / RUNTIME_REL) == RUNTIME_SHA,
                    "rollback 후 운영 JSON SHA 불일치",
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
                    "rollback 후 staging 변경 잔존",
                )

                report["rollback_performed"] = True

            except Exception as rb_exc:
                rollback_error = (
                    f"{type(rb_exc).__name__}: {rb_exc}"
                )

        report["error"] = f"{type(exc).__name__}: {exc}"

        if rollback_error:
            report["rollback_error"] = rollback_error

        REPORT_JSON.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        lines = [
            "[FAIL] Stage70E Release Prep Actual",
            f"error={type(exc).__name__}: {exc}",
            f"actual_performed={'YES' if actual_written else 'NO'}",
            (
                "rollback=PASS"
                if (
                    actual_written
                    and report.get("rollback_performed")
                    and not rollback_error
                )
                else "rollback=NOT_NEEDED"
                if not actual_written
                else "rollback=FAIL"
            ),
        ]

        if rollback_error:
            lines.append(f"rollback_error={rollback_error}")

        lines.append(
            f"report={REPORT_TXT.relative_to(ROOT)}"
        )

        REPORT_TXT.write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )
        print("\n".join(lines))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
