from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent

BASE_COMMIT = "08b51f4fa487a3ae05c1e279aa1c533f9f3aed52"
BASE_VERSION = "0.5.17"
NEXT_VERSION = "0.5.18"
BASE_TAG = "electron-v0.5.17"

RUNTIME_REL = Path("data/kdrg_v47_search_integrated_v3.json")
RUNTIME_SHA = "1a3d50400567ecaad9695b7be8e7c0382131f8652f398e010cf01f4d8dda6c58"

APP_REL = Path("electron/renderer/app.js")
CSS_REL = Path("electron/renderer/styles.css")
VALIDATOR_REL = Path("electron/tests/validate-stage70b-0518-phase1-ui.js")

SHADOW_SCRIPT = ROOT / "70B_SHADOW_KDRG_0518_PHASE1_UI_R2.py"
SHADOW_SCRIPT_SHA = "fee616429f53f08df3be1bdd752d7c14ea1dcdc34ac545cc2a511bcae90ecf01"
SHADOW_REPORT_DIR = ROOT / "reports/stage70b_0518_phase1_ui_shadow_r2"
SHADOW_REPORT_JSON = SHADOW_REPORT_DIR / "shadow.json"
SHADOW_DIR = SHADOW_REPORT_DIR / "shadow"

REPORT_DIR = ROOT / "reports/stage70c_0518_phase1_ui_actual_r2"
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


def load_shadow_module():
    require(SHADOW_SCRIPT.is_file(), f"70B Shadow script 없음: {SHADOW_SCRIPT.name}")
    require(
        sha256(SHADOW_SCRIPT) == SHADOW_SCRIPT_SHA,
        "70B Shadow script SHA256 불일치",
    )

    spec = importlib.util.spec_from_file_location(
        "stage70b_shadow_r2_bound",
        SHADOW_SCRIPT,
    )
    require(spec is not None and spec.loader is not None, "70B Shadow module 로드 준비 실패")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def copy_file(src: Path, dst: Path):
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def write_bytes_atomic(path: Path, data: bytes):
    tmp = path.with_name(path.name + ".stage70c.tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def rollback(originals):
    errors = []
    for rel, info in originals.items():
        path = ROOT / rel
        try:
            if info["existed"]:
                write_bytes_atomic(path, info["bytes"])
            elif path.exists():
                path.unlink()
        except Exception as exc:
            errors.append(f"{rel}: {type(exc).__name__}: {exc}")
    return errors


def validate_shadow_binding(shadow_report, shadow_module):
    require(
        shadow_report.get("status") == "PASS",
        f"70B Shadow status 불일치: {shadow_report.get('status')}",
    )
    require(
        shadow_report.get("readiness") == "READY_FOR_70C_0518_PHASE1_UI_ACTUAL",
        f"70B readiness 불일치: {shadow_report.get('readiness')}",
    )
    require(
        shadow_report.get("head") == BASE_COMMIT,
        f"70B head 불일치: {shadow_report.get('head')}",
    )
    require(
        shadow_report.get("base_version") == BASE_VERSION,
        f"70B base_version 불일치: {shadow_report.get('base_version')}",
    )
    require(
        shadow_report.get("runtime_json") == "UNCHANGED",
        "70B runtime_json 계약 불일치",
    )
    require(
        shadow_report.get("actual_performed") is False,
        "70B Shadow에서 Actual 수행 흔적 있음",
    )

    expected_files = sorted(
        [str(APP_REL), str(CSS_REL), str(VALIDATOR_REL)]
    )
    require(
        sorted(shadow_report.get("shadow_product_files") or []) == expected_files,
        "70B Shadow 후보파일 범위 불일치",
    )

    reported_sha = shadow_report.get("candidate_sha256") or {}
    require(
        set(reported_sha) == set(expected_files),
        f"70B candidate_sha256 키 불일치: {sorted(reported_sha)}",
    )

    for rel in expected_files:
        candidate = SHADOW_DIR / rel
        require(candidate.is_file(), f"70B Shadow candidate 없음: {rel}")
        require(
            sha256(candidate) == reported_sha[rel],
            f"70B Shadow candidate SHA 불일치: {rel}",
        )

    # Re-generate candidate from immutable HEAD source using the exact 70B logic.
    app_base = (ROOT / APP_REL).read_text(encoding="utf-8")
    css_base = (ROOT / CSS_REL).read_text(encoding="utf-8")

    regenerated = {
        str(APP_REL): shadow_module.patch_app(app_base).encode("utf-8"),
        str(CSS_REL): shadow_module.patch_css(css_base).encode("utf-8"),
        str(VALIDATOR_REL): (shadow_module.VALIDATOR_JS + "\n").encode("utf-8"),
    }

    for rel, data in regenerated.items():
        candidate = SHADOW_DIR / rel
        require(
            data == candidate.read_bytes(),
            f"70B candidate regeneration parity FAIL: {rel}",
        )
        require(
            hashlib.sha256(data).hexdigest() == reported_sha[rel],
            f"70B regenerated SHA FAIL: {rel}",
        )

    return regenerated


def main():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "stage": "70C_ACTUAL_0518_PHASE1_UI_R2",
        "status": "FAIL",
        "rollback": "NOT_STARTED",
    }
    originals = {}

    try:
        # ------------------------------------------------------------
        # 1) Immutable release baseline / workspace guard
        # ------------------------------------------------------------
        head = git_text("rev-parse", "HEAD")
        origin_main = git_text("rev-parse", "origin/main")
        branch = git_text("branch", "--show-current")
        tracked = [
            x for x in git_text("diff", "--name-only", "HEAD").splitlines() if x
        ]
        staged = [
            x for x in git_text("diff", "--cached", "--name-only").splitlines() if x
        ]

        require(head == BASE_COMMIT, f"HEAD 불일치: {head}")
        require(origin_main == BASE_COMMIT, f"origin/main 불일치: {origin_main}")
        require(branch == "main", f"branch 불일치: {branch}")
        require(not tracked, f"tracked worktree 변경 있음: {tracked}")
        require(not staged, f"staging 변경 있음: {staged}")

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

        local_tag = git_text("rev-list", "-n", "1", BASE_TAG)
        require(local_tag == BASE_COMMIT, f"{BASE_TAG} local tag commit 불일치")
        remote_tag_line = git_text(
            "ls-remote", "--tags", "origin", f"refs/tags/{BASE_TAG}"
        )
        require(
            remote_tag_line.startswith(BASE_COMMIT),
            f"{BASE_TAG} remote tag commit 불일치",
        )

        # ------------------------------------------------------------
        # 2) Bind exactly to the PASSed Stage70B Shadow candidate
        # ------------------------------------------------------------
        require(
            SHADOW_REPORT_JSON.is_file(),
            f"70B Shadow report 없음: {SHADOW_REPORT_JSON}",
        )
        shadow_report = json.loads(
            SHADOW_REPORT_JSON.read_text(encoding="utf-8")
        )
        shadow_module = load_shadow_module()
        regenerated = validate_shadow_binding(shadow_report, shadow_module)

        # ------------------------------------------------------------
        # 3) Back up only the three exact Actual targets
        # ------------------------------------------------------------
        if BACKUP_DIR.exists():
            shutil.rmtree(BACKUP_DIR)
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)

        for rel in (APP_REL, CSS_REL, VALIDATOR_REL):
            path = ROOT / rel
            existed = path.exists()
            data = path.read_bytes() if existed else b""
            originals[str(rel)] = {
                "existed": existed,
                "bytes": data,
                "sha256": hashlib.sha256(data).hexdigest() if existed else None,
            }
            if existed:
                copy_file(path, BACKUP_DIR / rel)

        # ------------------------------------------------------------
        # 4) Actual apply: byte-identical to Stage70B candidate
        # ------------------------------------------------------------
        for rel in (APP_REL, CSS_REL, VALIDATOR_REL):
            write_bytes_atomic(ROOT / rel, regenerated[str(rel)])

        for rel in (APP_REL, CSS_REL, VALIDATOR_REL):
            require(
                (ROOT / rel).read_bytes() == (SHADOW_DIR / rel).read_bytes(),
                f"Actual != 70B Shadow candidate: {rel}",
            )

        # ------------------------------------------------------------
        # 5) Syntax + exact changed-scope guard
        # ------------------------------------------------------------
        for rel in (APP_REL, VALIDATOR_REL):
            rc, output = run(
                ["node", "--check", str(rel.relative_to("electron"))],
                cwd=ROOT / "electron",
                timeout=120,
            )
            require(
                rc == 0,
                f"node --check FAIL: {rel}\n{output[-3000:]}",
            )

        # app.js / styles.css are tracked modifications.
        # The new Stage70B validator does not exist in 0.5.17 HEAD, so it is
        # intentionally untracked at this point and must be checked separately.
        tracked_changed = sorted(
            x for x in git_text(
                "diff",
                "--name-only",
                "HEAD",
                "--",
                str(APP_REL),
                str(CSS_REL),
            ).splitlines()
            if x
        )
        expected_tracked = sorted([str(APP_REL), str(CSS_REL)])
        require(
            tracked_changed == expected_tracked,
            f"Actual tracked 변경범위 불일치: {tracked_changed}",
        )

        rc, validator_status = run(
            ["git", "status", "--short", "--", str(VALIDATOR_REL)],
            cwd=ROOT,
            timeout=120,
        )
        require(rc == 0, "Actual validator git status 확인 실패")
        require(
            validator_status.strip() == f"?? {VALIDATOR_REL.as_posix()}",
            f"Actual validator 상태 불일치: {validator_status.strip()}",
        )

        actual_changed_scope = sorted(
            tracked_changed + [str(VALIDATOR_REL)]
        )
        expected_changed = sorted(
            [str(APP_REL), str(CSS_REL), str(VALIDATOR_REL)]
        )
        require(
            actual_changed_scope == expected_changed,
            f"Actual 전체 변경범위 불일치: {actual_changed_scope}",
        )

        require(
            not [
                x for x in git_text(
                    "diff", "--cached", "--name-only"
                ).splitlines() if x
            ],
            "Actual 적용 중 staging 변경됨",
        )

        # ------------------------------------------------------------
        # 6) Full validations — collect all before stopping
        # ------------------------------------------------------------
        validations = [
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
                "release_version_0517",
                [
                    "node",
                    "tests/validate-release-version.js",
                    BASE_VERSION,
                ],
                ROOT / "electron",
            ),
        ]

        results = []
        failures = []
        for name, cmd, cwd in validations:
            rc, output = run(cmd, cwd=cwd, timeout=1200)
            results.append(
                {
                    "name": name,
                    "rc": rc,
                    "status": "PASS" if rc == 0 else "FAIL",
                    "tail": output[-8000:],
                }
            )
            if rc != 0:
                failures.append(
                    f"{name} FAIL\n{output[-6000:]}"
                )

        if failures:
            raise Stop(
                "Stage70C Actual 검증 실패를 전체 실행 후 수집함\n\n"
                + "\n\n".join(failures)
            )

        # ------------------------------------------------------------
        # 7) Final invariants
        # ------------------------------------------------------------
        require(
            sha256(ROOT / RUNTIME_REL) == RUNTIME_SHA,
            "Actual 후 운영 JSON 변경됨",
        )
        require(
            json.loads(
                (ROOT / "electron/package.json").read_text(encoding="utf-8")
            ).get("version") == BASE_VERSION,
            "Actual 단계에서 package version 변경됨",
        )
        require(
            not [
                x for x in git_text(
                    "diff", "--cached", "--name-only"
                ).splitlines() if x
            ],
            "Actual 후 staging 변경됨",
        )

        actual_sha = {
            str(rel): sha256(ROOT / rel)
            for rel in (APP_REL, CSS_REL, VALIDATOR_REL)
        }
        require(
            actual_sha == shadow_report["candidate_sha256"],
            "Actual SHA 집합 != 70B Shadow candidate SHA 집합",
        )

        report.update(
            {
                "status": "PASS",
                "head": head,
                "base_version": BASE_VERSION,
                "next_version": NEXT_VERSION,
                "shadow_script_sha256": SHADOW_SCRIPT_SHA,
                "shadow_binding": "PASS",
                "candidate_regeneration_parity": "PASS",
                "actual_product_files": [
                    str(APP_REL), str(CSS_REL), str(VALIDATOR_REL)
                ],
                "actual_sha256": actual_sha,
                "runtime_json": "UNCHANGED",
                "staging": "EMPTY",
                "rollback": "NOT_NEEDED",
                "checks": results,
                "readiness": "READY_FOR_70D_0518_RELEASE_PREP_SHADOW",
            }
        )

        REPORT_JSON.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        lines = [
            "[PASS] Stage70C R2 / 0.5.18 1차 UI 마감 Actual",
            "stage70b_shadow_binding=PASS",
            "candidate_regeneration_parity=PASS",
            "tracked_changed_files=2",
            "new_validator_untracked=PASS",
            "actual_product_files=3",
            "general_adrg_classification=RIGHT",
            "relation_classification=RIGHT",
            "unclassified_display=분류정보 없음",
            "classification_data_inference=NONE",
            "general_result_mdc_name=PASS",
            "adrg_detail_mdc_name=PASS",
            "relation_result_mdc_name=PASS",
            "stage70b_validator=PASS",
            "stage69b_validator=PASS",
            "stage68d_validator=PASS",
            "npm_check=PASS",
            "50B_50C_50D=PASS",
            "release_version_0.5.17=PASS",
            "runtime_json=UNCHANGED",
            "package_version=0.5.17",
            "staging=EMPTY",
            "rollback=NOT_NEEDED",
            "readiness=READY_FOR_70D_0518_RELEASE_PREP_SHADOW",
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
        rollback_errors = []
        if originals:
            rollback_errors = rollback(originals)

        report["error"] = f"{type(exc).__name__}: {exc}"
        report["rollback"] = (
            "PASS" if originals and not rollback_errors
            else "FAILED" if rollback_errors
            else "NOT_NEEDED"
        )
        report["rollback_errors"] = rollback_errors

        try:
            REPORT_JSON.write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except Exception:
            pass

        lines = [
            "[FAIL] Stage70C 0.5.18 1차 UI 마감 Actual",
            f"{type(exc).__name__}: {exc}",
            f"rollback={report['rollback']}",
        ]
        if rollback_errors:
            lines.extend(f"- {item}" for item in rollback_errors)
        lines.append(f"report={REPORT_TXT.relative_to(ROOT)}")

        try:
            REPORT_TXT.write_text(
                "\n".join(lines) + "\n",
                encoding="utf-8",
            )
        except Exception:
            pass

        print("\n".join(lines))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
