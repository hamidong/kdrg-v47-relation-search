from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent

BASE_COMMIT = "1bd70d50c85305e2ff64ebb0a17ec619719e8a40"
BASE_VERSION = "0.5.18"
NEXT_VERSION = "0.5.19"
BASE_TAG = "electron-v0.5.18"

RUNTIME_REL = Path("data/kdrg_v47_search_integrated_v3.json")
RUNTIME_SHA = "1a3d50400567ecaad9695b7be8e7c0382131f8652f398e010cf01f4d8dda6c58"

SHADOW_SCRIPT = ROOT / "72B_SHADOW_KDRG_0519_RELATION_RESULT_LAYOUT_R4.py"
SHADOW_SCRIPT_SHA = "4ebfb70b370bebd928e7f44114e0e89cbe951e26a6f25319b49af8aa0cafc4fe"
SHADOW_REPORT_DIR = ROOT / "reports/stage72b_0519_relation_result_layout_shadow_r4"
SHADOW_JSON = SHADOW_REPORT_DIR / "shadow.json"
SHADOW_ROOT = SHADOW_REPORT_DIR / "shadow"

APP_REL = Path("electron/renderer/app.js")
CSS_REL = Path("electron/renderer/styles.css")
OLD_VALIDATOR_REL = Path("electron/tests/validate-stage70b-0518-phase1-ui.js")
NEW_VALIDATOR_REL = Path("electron/tests/validate-stage72b-0519-relation-result-layout.js")

EXPECTED_EXISTING = [
    APP_REL,
    CSS_REL,
    OLD_VALIDATOR_REL,
]
EXPECTED_NEW = [
    NEW_VALIDATOR_REL,
]
EXPECTED_FINAL = [
    APP_REL,
    CSS_REL,
    OLD_VALIDATOR_REL,
    NEW_VALIDATOR_REL,
]

REPORT_DIR = ROOT / "reports/stage72c_0519_relation_result_layout_actual_r1"
BACKUP_DIR = REPORT_DIR / "backup"
REPORT_JSON = REPORT_DIR / "actual.json"
REPORT_TXT = REPORT_DIR / "actual_summary.txt"


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


def copy_file(src: Path, dst: Path):
    require(src.is_file(), f"복사 원본 없음: {src}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def collect_actual_scope():
    tracked = sorted(
        x
        for x in git_text(
            "diff",
            "--name-only",
            "HEAD",
            "--",
            str(APP_REL),
            str(CSS_REL),
            str(OLD_VALIDATOR_REL),
        ).splitlines()
        if x
    )
    rc, status = run(
        ["git", "status", "--short", "--", str(NEW_VALIDATOR_REL)],
        timeout=120,
    )
    require(rc == 0, "신규 validator 상태 확인 실패")
    return tracked, status.strip()


def restore_backup(preexisting_new_validator: bool):
    # Restore all pre-existing tracked files.
    for rel in EXPECTED_EXISTING:
        backup = BACKUP_DIR / rel
        if backup.is_file():
            copy_file(backup, ROOT / rel)

    # Restore/remove the new validator according to the pre-apply state.
    new_backup = BACKUP_DIR / NEW_VALIDATOR_REL
    target_new = ROOT / NEW_VALIDATOR_REL

    if preexisting_new_validator:
        require(
            new_backup.is_file(),
            "rollback용 기존 Stage72B validator backup 없음",
        )
        copy_file(new_backup, target_new)
    elif target_new.exists():
        target_new.unlink()


def validate_candidate_shas(shadow_report):
    candidate = shadow_report.get("candidate_sha256") or {}
    for rel in EXPECTED_FINAL:
        key = str(rel)
        require(
            key in candidate,
            f"Shadow candidate SHA 없음: {key}",
        )
        path = SHADOW_ROOT / rel
        require(path.is_file(), f"Shadow candidate 파일 없음: {key}")
        require(
            sha256(path) == candidate[key],
            f"Shadow candidate SHA 불일치: {key}",
        )


def main():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    report = {
        "stage": "72C_0519_RELATION_RESULT_LAYOUT_ACTUAL_R1",
        "status": "FAIL",
        "rollback_performed": False,
    }

    preexisting_new_validator = (ROOT / NEW_VALIDATOR_REL).exists()

    try:
        # ------------------------------------------------------------
        # 1) Immutable 0.5.18 baseline guard
        # ------------------------------------------------------------
        head = git_text("rev-parse", "HEAD")
        origin_main = git_text("rev-parse", "origin/main")
        branch = git_text("branch", "--show-current")

        require(head == BASE_COMMIT, f"HEAD 불일치: {head}")
        require(origin_main == BASE_COMMIT, f"origin/main 불일치: {origin_main}")
        require(branch == "main", f"branch 불일치: {branch}")

        tracked_before = [
            x for x in git_text("diff", "--name-only", "HEAD").splitlines() if x
        ]
        staged_before = [
            x for x in git_text("diff", "--cached", "--name-only").splitlines() if x
        ]

        require(
            not tracked_before,
            f"Actual 적용 전 tracked 변경 있음: {tracked_before}",
        )
        require(
            not staged_before,
            f"Actual 적용 전 staging 변경 있음: {staged_before}",
        )
        require(
            not preexisting_new_validator,
            f"신규 validator가 이미 Actual에 존재함: {NEW_VALIDATOR_REL}",
        )

        package = json.loads(
            (ROOT / "electron/package.json").read_text(encoding="utf-8")
        )
        require(
            package.get("version") == BASE_VERSION,
            f"package version 불일치: {package.get('version')}",
        )
        require(
            sha256(ROOT / RUNTIME_REL) == RUNTIME_SHA,
            "운영 JSON SHA 불일치",
        )
        require(
            git_text("rev-list", "-n", "1", BASE_TAG) == BASE_COMMIT,
            f"{BASE_TAG} local tag 불일치",
        )

        # ------------------------------------------------------------
        # 2) Bind to exact 72B R4 PASS
        # ------------------------------------------------------------
        require(SHADOW_SCRIPT.is_file(), "72B R4 Shadow script 없음")
        require(
            sha256(SHADOW_SCRIPT) == SHADOW_SCRIPT_SHA,
            "72B R4 Shadow script SHA 불일치",
        )
        require(SHADOW_JSON.is_file(), "72B R4 shadow.json 없음")
        require(SHADOW_ROOT.is_dir(), "72B R4 shadow 디렉터리 없음")

        shadow_report = json.loads(
            SHADOW_JSON.read_text(encoding="utf-8")
        )

        require(
            shadow_report.get("status") == "PASS",
            "72B R4 Shadow status != PASS",
        )
        require(
            shadow_report.get("readiness")
            == "READY_FOR_72C_0519_RELATION_RESULT_LAYOUT_ACTUAL",
            f"72B R4 readiness 불일치: {shadow_report.get('readiness')}",
        )
        require(
            shadow_report.get("head") == BASE_COMMIT,
            "72B R4 HEAD 불일치",
        )
        require(
            shadow_report.get("base_version") == BASE_VERSION,
            "72B R4 base version 불일치",
        )
        require(
            shadow_report.get("runtime_json") == "UNCHANGED",
            "72B R4 runtime 계약 불일치",
        )
        require(
            shadow_report.get("actual_performed") is False,
            "72B R4는 Shadow-only여야 함",
        )

        shadow_files = sorted(
            shadow_report.get("shadow_product_files") or []
        )
        require(
            shadow_files == sorted(str(x) for x in EXPECTED_FINAL),
            f"72B R4 product 범위 불일치: {shadow_files}",
        )

        validate_candidate_shas(shadow_report)

        # ------------------------------------------------------------
        # 3) Exact backup before mutation
        # ------------------------------------------------------------
        if BACKUP_DIR.exists():
            shutil.rmtree(BACKUP_DIR)

        for rel in EXPECTED_EXISTING:
            copy_file(ROOT / rel, BACKUP_DIR / rel)

        if preexisting_new_validator:
            copy_file(
                ROOT / NEW_VALIDATOR_REL,
                BACKUP_DIR / NEW_VALIDATOR_REL,
            )

        backup_sha = {
            str(rel): sha256(BACKUP_DIR / rel)
            for rel in EXPECTED_EXISTING
        }

        # ------------------------------------------------------------
        # 4) Apply exact Shadow candidates to Actual
        # ------------------------------------------------------------
        for rel in EXPECTED_FINAL:
            copy_file(SHADOW_ROOT / rel, ROOT / rel)

        candidate_sha = shadow_report["candidate_sha256"]
        for rel in EXPECTED_FINAL:
            require(
                sha256(ROOT / rel) == candidate_sha[str(rel)],
                f"Actual apply SHA 불일치: {rel}",
            )

        # Scope guard: exactly 3 tracked + 1 untracked.
        actual_tracked, new_status = collect_actual_scope()
        require(
            actual_tracked
            == sorted(str(x) for x in EXPECTED_EXISTING),
            (
                "Actual tracked 변경범위 불일치: "
                f"{actual_tracked}"
            ),
        )
        require(
            new_status == f"?? {NEW_VALIDATOR_REL.as_posix()}",
            f"신규 validator 상태 불일치: {new_status}",
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
            "Actual 적용 후 staging 변경 발생",
        )

        # ------------------------------------------------------------
        # 5) Syntax + full regression validation
        # ------------------------------------------------------------
        for rel in (
            APP_REL,
            OLD_VALIDATOR_REL,
            NEW_VALIDATOR_REL,
        ):
            rc, output = run(
                ["node", "--check", str(rel.relative_to("electron"))],
                cwd=ROOT / "electron",
                timeout=120,
            )
            require(
                rc == 0,
                f"node --check FAIL: {rel}\n{output[-3000:]}",
            )

        validations = [
            (
                "stage72b_validator",
                ["node", "tests/validate-stage72b-0519-relation-result-layout.js"],
                ROOT / "electron",
            ),
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
                ["node", "tests/validate-release-version.js", BASE_VERSION],
                ROOT / "electron",
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
                "72C Actual 검증 실패를 전체 수집함\n\n"
                + "\n\n".join(failures)
            )

        # ------------------------------------------------------------
        # 6) Post-apply safety verification
        # ------------------------------------------------------------
        require(
            sha256(ROOT / RUNTIME_REL) == RUNTIME_SHA,
            "Actual 검증 후 운영 JSON 변경됨",
        )

        package_after = json.loads(
            (ROOT / "electron/package.json").read_text(encoding="utf-8")
        )
        require(
            package_after.get("version") == BASE_VERSION,
            "72C에서 package version을 변경하면 안 됨",
        )

        actual_tracked_after, new_status_after = collect_actual_scope()
        require(
            actual_tracked_after
            == sorted(str(x) for x in EXPECTED_EXISTING),
            f"검증 후 tracked 범위 변경: {actual_tracked_after}",
        )
        require(
            new_status_after == f"?? {NEW_VALIDATOR_REL.as_posix()}",
            f"검증 후 신규 validator 상태 변경: {new_status_after}",
        )

        report.update({
            "status": "PASS",
            "readiness": "READY_FOR_72D_0519_RELEASE_PREP_SHADOW",
            "base_commit": BASE_COMMIT,
            "base_version": BASE_VERSION,
            "next_version": NEXT_VERSION,
            "runtime_json": "UNCHANGED",
            "package_version": BASE_VERSION,
            "applied_files": [str(x) for x in EXPECTED_FINAL],
            "actual_sha256": {
                str(rel): sha256(ROOT / rel)
                for rel in EXPECTED_FINAL
            },
            "backup_sha256": backup_sha,
            "rollback_performed": False,
            "checks": results,
        })

        REPORT_JSON.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        lines = [
            "[PASS] Stage72C R1 / 0.5.19 복수검색 결과 레이아웃 Actual",
            "applied_files=4",
            "relation_card_top_right=DISEASE_CLASSIFICATION",
            "relation_card_relation_level_chip=REMOVED",
            "header_summary=COMMON_RELATED_ADRG",
            "header_summary_emphasis=SLIGHTLY_LARGER",
            "general_adrg_layout=PRESERVED",
            "stage72b_validator=PASS",
            "stage70b_validator=PASS",
            "stage69b_validator=PASS",
            "stage68d_validator=PASS",
            "npm_check=PASS",
            "50B_50C_50D=PASS",
            "release_version_0.5.18=PASS",
            "runtime_json=UNCHANGED",
            "package_version=0.5.18",
            "staging=EMPTY",
            "rollback=NOT_NEEDED",
            "readiness=READY_FOR_72D_0519_RELEASE_PREP_SHADOW",
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
        try:
            # Roll back only if backup was created.
            if BACKUP_DIR.exists():
                restore_backup(preexisting_new_validator)

                # Verify exact tracked cleanliness after rollback.
                rollback_tracked = [
                    x
                    for x in git_text(
                        "diff",
                        "--name-only",
                        "HEAD",
                    ).splitlines()
                    if x
                ]
                rollback_staged = [
                    x
                    for x in git_text(
                        "diff",
                        "--cached",
                        "--name-only",
                    ).splitlines()
                    if x
                ]
                require(
                    not rollback_tracked,
                    f"rollback 후 tracked 변경 잔존: {rollback_tracked}",
                )
                require(
                    not rollback_staged,
                    f"rollback 후 staging 변경 잔존: {rollback_staged}",
                )
                require(
                    sha256(ROOT / RUNTIME_REL) == RUNTIME_SHA,
                    "rollback 후 운영 JSON SHA 불일치",
                )
                report["rollback_performed"] = True
        except Exception as rollback_exc:
            rollback_error = f"{type(rollback_exc).__name__}: {rollback_exc}"

        report["error"] = f"{type(exc).__name__}: {exc}"
        if rollback_error:
            report["rollback_error"] = rollback_error

        REPORT_JSON.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        lines = [
            "[FAIL] Stage72C R1 0.5.19 복수검색 결과 레이아웃 Actual",
            f"{type(exc).__name__}: {exc}",
            (
                "rollback=PASS"
                if report.get("rollback_performed")
                else "rollback=NOT_CONFIRMED"
            ),
        ]
        if rollback_error:
            lines.append(f"rollback_error={rollback_error}")
        lines.append(f"report={REPORT_TXT.relative_to(ROOT)}")

        REPORT_TXT.write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )
        print("\n".join(lines))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
