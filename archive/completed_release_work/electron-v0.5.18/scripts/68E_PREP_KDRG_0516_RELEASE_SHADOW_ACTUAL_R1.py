#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage68E — KDRG 0.5.16 Release Prep Shadow -> Actual R1

68D PASS 상태를 전제로:
- Shadow tree에서 먼저 0.5.16 버전 승격 및 전체 검증
- Shadow PASS 후에만 Actual 3개 파일 반영
- Actual 실패 시 release-prep 3개만 rollback (68D 변경은 유지)

Actual 변경 대상:
1) electron/package.json
2) electron/package-lock.json
3) 50D_validate_kdrg_electron_windows_packaging.py

보호:
- electron/renderer/app.js (68D PASS hash 고정)
- electron/tests/validate-stage68d-0516-classification-derived-aadrg.js
- data/kdrg_v47_search_integrated_v3.json
- electron/src/kdrg-search-service.js
- electron/renderer/styles.css
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd().resolve()
ELECTRON = ROOT / "electron"

BASE_VERSION = "0.5.15"
NEXT_VERSION = "0.5.16"
BASE_TAG = "electron-v0.5.15"
NEXT_TAG = "electron-v0.5.16"
BASE_COMMIT = "6e0bc2857ebf6abb482428b90f452d5e07c486ac"

PACKAGE = ELECTRON / "package.json"
LOCK = ELECTRON / "package-lock.json"
VALIDATE_RELEASE = ELECTRON / "tests" / "validate-release-version.js"
FIFTYD = ROOT / "50D_validate_kdrg_electron_windows_packaging.py"
FIFTYB = ROOT / "50B_validate_kdrg_electron_search_service.py"
FIFTYC = ROOT / "50C_validate_kdrg_electron_renderer_ui.py"

APP = ELECTRON / "renderer" / "app.js"
STAGE68D_VALIDATOR = (
    ELECTRON / "tests" / "validate-stage68d-0516-classification-derived-aadrg.js"
)
DATA = ROOT / "data" / "kdrg_v47_search_integrated_v3.json"
SERVICE = ELECTRON / "src" / "kdrg-search-service.js"
STYLES = ELECTRON / "renderer" / "styles.css"

WORKFLOW_DIR = ROOT / ".github"

EXPECTED_APP_SHA = "715c0ccdfb083eb77e58609a6adfdc27c7e54b6f96307c9dd7e6e0e1b49768b0"
EXPECTED_STAGE68D_VALIDATOR_SHA = (
    "961e4337d1a5b576742da66c5fa7f299597e6ea274eafe05664c53ca73903138"
)
EXPECTED_DATA_SHA = "1a3d50400567ecaad9695b7be8e7c0382131f8652f398e010cf01f4d8dda6c58"

OLD_50D_MARKER = "STAGE50D_VALIDATOR_V14_0515"
NEW_50D_MARKER = "STAGE50D_VALIDATOR_V15_0516"
EXPECTED_50D_VERSION_LITERAL_COUNT = 3

REPORT_DIR = ROOT / "reports" / "stage68e_0516_release_prep_r1"
SHADOW = REPORT_DIR / "shadow"
REPORT_JSON = REPORT_DIR / "release_prep.json"
REPORT_TXT = REPORT_DIR / "release_prep_summary.txt"


class Stop(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise Stop(message)


def run(args, *, cwd=None, timeout=900):
    p = subprocess.run(
        args,
        cwd=(cwd or ROOT),
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    output = (p.stdout or "") + (("\n" + p.stderr) if p.stderr else "")
    return p.returncode, output


def git(*args):
    return run(["git", *args], cwd=ROOT, timeout=180)


def git_text(*args):
    rc, output = git(*args)
    require(rc == 0, f"git {' '.join(args)} 실패: {output[-1000:]}")
    return output.strip()


def git_lines(*args):
    text = git_text(*args)
    return [line for line in text.splitlines() if line.strip()]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def local_tag_sha(tag: str) -> str:
    rc, output = git("rev-list", "-n", "1", tag)
    return output.strip() if rc == 0 else ""


def remote_tag_sha(tag: str) -> str:
    rc, output = run(
        ["git", "ls-remote", "--tags", "origin", f"refs/tags/{tag}"],
        cwd=ROOT,
        timeout=180,
    )
    if rc != 0 or not output.strip():
        return ""
    return output.split()[0].strip()


def json_load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def json_dump(path: Path, obj):
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_summary(status, data, message=""):
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    payload = dict(data)
    payload["status"] = status
    if message:
        payload["message"] = message
    REPORT_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    lines = [
        "Stage68E — KDRG 0.5.16 Release Prep Shadow -> Actual R1",
        "=" * 72,
        f"status={status}",
    ]
    if message:
        lines += ["", message]
    REPORT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_candidates():
    package = json_load(PACKAGE)
    lock = json_load(LOCK)

    require(package.get("version") == BASE_VERSION, "package.json 현재 버전 != 0.5.15")
    require(lock.get("version") == BASE_VERSION, "package-lock top 버전 != 0.5.15")
    require(
        (lock.get("packages") or {}).get("", {}).get("version") == BASE_VERSION,
        "package-lock root package 버전 != 0.5.15",
    )

    package_candidate = dict(package)
    package_candidate["version"] = NEXT_VERSION

    lock_candidate = json.loads(json.dumps(lock))
    lock_candidate["version"] = NEXT_VERSION
    lock_candidate.setdefault("packages", {}).setdefault("", {})["version"] = NEXT_VERSION

    fiftyd_text = FIFTYD.read_text(encoding="utf-8")
    old_literal_count = fiftyd_text.count(BASE_VERSION)
    old_marker_count = fiftyd_text.count(OLD_50D_MARKER)

    require(
        old_literal_count == EXPECTED_50D_VERSION_LITERAL_COUNT,
        f"50D의 {BASE_VERSION} 리터럴 개수 불일치: {old_literal_count}",
    )
    require(
        old_marker_count == 1,
        f"50D old marker 개수 불일치: {old_marker_count}",
    )
    require(
        NEXT_VERSION not in fiftyd_text,
        f"50D에 이미 {NEXT_VERSION} 존재",
    )
    require(
        NEW_50D_MARKER not in fiftyd_text,
        "50D에 이미 새 validator marker 존재",
    )

    fiftyd_candidate = fiftyd_text.replace(BASE_VERSION, NEXT_VERSION)
    fiftyd_candidate = fiftyd_candidate.replace(
        OLD_50D_MARKER,
        NEW_50D_MARKER,
        1,
    )

    require(
        fiftyd_candidate.count(BASE_VERSION) == 0,
        "50D 후보에 old version 리터럴 잔존",
    )
    require(
        fiftyd_candidate.count(NEXT_VERSION) == EXPECTED_50D_VERSION_LITERAL_COUNT,
        "50D 후보 new version 리터럴 개수 불일치",
    )
    require(
        fiftyd_candidate.count(NEW_50D_MARKER) == 1,
        "50D 후보 new marker 개수 불일치",
    )

    # Python syntax 자체 확인. pyc 파일은 만들지 않는다.
    compile(fiftyd_candidate, str(FIFTYD), "exec")

    return {
        "package": package_candidate,
        "lock": lock_candidate,
        "fiftyd": fiftyd_candidate,
        "old_50d_literal_count": old_literal_count,
        "old_50d_marker_count": old_marker_count,
    }


def copy_shadow(candidates):
    if SHADOW.exists():
        shutil.rmtree(SHADOW)
    SHADOW.mkdir(parents=True)

    def ignore_electron(_dir, names):
        skipped = []
        for name in names:
            if name in {"node_modules", "dist", "release", "releases"}:
                skipped.append(name)
        return skipped

    shutil.copytree(
        ELECTRON,
        SHADOW / "electron",
        dirs_exist_ok=True,
        ignore=ignore_electron,
    )

    # runtime data
    (SHADOW / "data").mkdir(parents=True, exist_ok=True)
    shutil.copy2(DATA, SHADOW / "data" / DATA.name)

    # GitHub workflow/support
    if WORKFLOW_DIR.exists():
        shutil.copytree(
            WORKFLOW_DIR,
            SHADOW / ".github",
            dirs_exist_ok=True,
        )

    # root validators
    for src in (FIFTYB, FIFTYC):
        require(src.exists(), f"필수 validator 없음: {src.name}")
        shutil.copy2(src, SHADOW / src.name)

    # candidate release-prep files
    json_dump(SHADOW / "electron" / "package.json", candidates["package"])
    json_dump(SHADOW / "electron" / "package-lock.json", candidates["lock"])
    (SHADOW / FIFTYD.name).write_text(
        candidates["fiftyd"],
        encoding="utf-8",
    )

    return {
        "shadow_root": str(SHADOW),
        "package_sha256": sha256(SHADOW / "electron" / "package.json"),
        "lock_sha256": sha256(SHADOW / "electron" / "package-lock.json"),
        "fiftyd_sha256": sha256(SHADOW / FIFTYD.name),
    }


def run_validation_suite(root: Path, *, label: str):
    electron = root / "electron"
    results = []

    checks = [
        (
            "stage68d validator syntax",
            ["node", "--check", "tests/validate-stage68d-0516-classification-derived-aadrg.js"],
            electron,
        ),
        (
            "stage68d exhaustive validator",
            ["node", "tests/validate-stage68d-0516-classification-derived-aadrg.js"],
            electron,
        ),
        (
            "npm run check",
            ["npm", "run", "check"],
            electron,
        ),
        (
            "50B",
            ["python", "50B_validate_kdrg_electron_search_service.py"],
            root,
        ),
        (
            "50C",
            ["python", "50C_validate_kdrg_electron_renderer_ui.py"],
            root,
        ),
        (
            "50D",
            ["python", FIFTYD.name],
            root,
        ),
        (
            "release version 0.5.16",
            ["node", "tests/validate-release-version.js", NEXT_VERSION],
            electron,
        ),
    ]

    for name, cmd, cwd in checks:
        rc, output = run(cmd, cwd=cwd, timeout=1200)
        results.append({
            "suite": label,
            "name": name,
            "cmd": " ".join(cmd),
            "cwd": str(cwd),
            "rc": rc,
            "status": "PASS" if rc == 0 else "FAIL",
            "tail": output[-6000:],
        })
        if rc != 0:
            raise Stop(
                f"{label} 검증 실패: {name}\n"
                + output[-3500:]
            )

    return results


def preflight():
    for path in (
        PACKAGE,
        LOCK,
        VALIDATE_RELEASE,
        FIFTYD,
        FIFTYB,
        FIFTYC,
        APP,
        STAGE68D_VALIDATOR,
        DATA,
        SERVICE,
        STYLES,
    ):
        require(path.exists(), f"필수 파일 없음: {path}")

    # remote 최신상태만 가져옴. 제품 파일은 변경하지 않음.
    rc, output = git("fetch", "origin", "--tags")
    require(rc == 0, f"git fetch 실패: {output[-1200:]}")

    head = git_text("rev-parse", "HEAD")
    branch = git_text("branch", "--show-current")
    origin_main = git_text("rev-parse", "origin/main")

    require(head == BASE_COMMIT, f"HEAD != 0.5.15 commit: {head}")
    require(origin_main == BASE_COMMIT, f"origin/main != 0.5.15 commit: {origin_main}")
    require(branch == "main", f"branch != main: {branch}")

    require(
        local_tag_sha(BASE_TAG) == BASE_COMMIT,
        "local electron-v0.5.15 tag mismatch",
    )
    require(
        remote_tag_sha(BASE_TAG) == BASE_COMMIT,
        "remote electron-v0.5.15 tag mismatch",
    )
    require(not local_tag_sha(NEXT_TAG), "local electron-v0.5.16 tag already exists")
    require(not remote_tag_sha(NEXT_TAG), "remote electron-v0.5.16 tag already exists")

    staging = git_lines("diff", "--cached", "--name-only")
    require(not staging, f"staging이 비어 있지 않음: {staging}")

    # 68D 이후 tracked 변경은 app.js 정확히 1개여야 함.
    tracked = git_lines("diff", "--name-only", "HEAD")
    require(
        tracked == ["electron/renderer/app.js"],
        f"68D 이후 tracked 변경 예상과 다름: {tracked}",
    )

    untracked_validator = git_lines(
        "ls-files",
        "--others",
        "--exclude-standard",
        "--",
        "electron/tests/validate-stage68d-0516-classification-derived-aadrg.js",
    )
    require(
        untracked_validator
        == ["electron/tests/validate-stage68d-0516-classification-derived-aadrg.js"],
        f"Stage68D validator untracked 상태 불일치: {untracked_validator}",
    )

    require(sha256(APP) == EXPECTED_APP_SHA, "68D app.js SHA 불일치")
    require(
        sha256(STAGE68D_VALIDATOR) == EXPECTED_STAGE68D_VALIDATOR_SHA,
        "68D validator SHA 불일치",
    )
    require(sha256(DATA) == EXPECTED_DATA_SHA, "운영 JSON SHA 불일치")

    package = json_load(PACKAGE)
    lock = json_load(LOCK)
    require(package.get("version") == BASE_VERSION, "package version != 0.5.15")
    require(lock.get("version") == BASE_VERSION, "lock version != 0.5.15")
    require(
        (lock.get("packages") or {}).get("", {}).get("version") == BASE_VERSION,
        "lock root package version != 0.5.15",
    )

    # release-prep 3개는 아직 HEAD와 동일해야 함.
    release_prep_paths = [
        "electron/package.json",
        "electron/package-lock.json",
        FIFTYD.name,
    ]
    for rel in release_prep_paths:
        rc, _ = git("diff", "--quiet", "HEAD", "--", rel)
        require(rc == 0, f"release-prep 대상이 이미 변경됨: {rel}")

    return {
        "head": head,
        "origin_main": origin_main,
        "branch": branch,
        "base_tag": BASE_TAG,
        "next_tag_absent": True,
        "tracked_before_release_prep": tracked,
        "stage68d_app_sha256": sha256(APP),
        "stage68d_validator_sha256": sha256(STAGE68D_VALIDATOR),
        "runtime_sha256": sha256(DATA),
        "package_version": package.get("version"),
        "lock_version": lock.get("version"),
    }


def final_guard(before_protected):
    package = json_load(PACKAGE)
    lock = json_load(LOCK)

    require(package.get("version") == NEXT_VERSION, "Actual package version != 0.5.16")
    require(lock.get("version") == NEXT_VERSION, "Actual lock top version != 0.5.16")
    require(
        (lock.get("packages") or {}).get("", {}).get("version") == NEXT_VERSION,
        "Actual lock root version != 0.5.16",
    )

    require(sha256(APP) == EXPECTED_APP_SHA, "Actual app.js SHA가 68D와 달라짐")
    require(
        sha256(STAGE68D_VALIDATOR) == EXPECTED_STAGE68D_VALIDATOR_SHA,
        "Actual Stage68D validator SHA가 달라짐",
    )
    require(sha256(DATA) == before_protected["data"], "운영 JSON 변경됨")
    require(sha256(SERVICE) == before_protected["service"], "search service 변경됨")
    require(sha256(STYLES) == before_protected["styles"], "styles.css 변경됨")

    require(not git_lines("diff", "--cached", "--name-only"), "staging not empty")

    tracked = git_lines("diff", "--name-only", "HEAD")
    expected_tracked = sorted([
        FIFTYD.name,
        "electron/package-lock.json",
        "electron/package.json",
        "electron/renderer/app.js",
    ])
    require(
        sorted(tracked) == expected_tracked,
        f"최종 tracked 변경파일 불일치: {tracked}",
    )

    untracked_validator = git_lines(
        "ls-files",
        "--others",
        "--exclude-standard",
        "--",
        "electron/tests/validate-stage68d-0516-classification-derived-aadrg.js",
    )
    require(
        untracked_validator
        == ["electron/tests/validate-stage68d-0516-classification-derived-aadrg.js"],
        "최종 Stage68D validator 상태 불일치",
    )

    require(not local_tag_sha(NEXT_TAG), "0.5.16 local tag가 예상보다 일찍 생성됨")
    require(not remote_tag_sha(NEXT_TAG), "0.5.16 remote tag가 예상보다 일찍 생성됨")

    fiftyd_text = FIFTYD.read_text(encoding="utf-8")
    require(fiftyd_text.count(BASE_VERSION) == 0, "50D old version 잔존")
    require(
        fiftyd_text.count(NEXT_VERSION) == EXPECTED_50D_VERSION_LITERAL_COUNT,
        "50D new version 리터럴 개수 불일치",
    )
    require(fiftyd_text.count(NEW_50D_MARKER) == 1, "50D V15_0516 marker 불일치")

    return {
        "tracked_final": tracked,
        "untracked_release_file": untracked_validator,
        "package_version": package.get("version"),
        "lock_version": lock.get("version"),
        "lock_root_version": (lock.get("packages") or {}).get("", {}).get("version"),
        "next_tag_absent": True,
        "staging_empty": True,
        "app_sha256": sha256(APP),
        "stage68d_validator_sha256": sha256(STAGE68D_VALIDATOR),
        "50d_sha256": sha256(FIFTYD),
        "package_sha256": sha256(PACKAGE),
        "lock_sha256": sha256(LOCK),
    }


def main():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    data = {"stage": "68E", "version": NEXT_VERSION}
    backups = {}
    actual_started = False

    try:
        pre = preflight()
        data["preflight"] = pre

        candidates = build_candidates()
        data["candidate_contract"] = {
            "50d_old_version_literal_count": candidates["old_50d_literal_count"],
            "50d_old_marker_count": candidates["old_50d_marker_count"],
            "old_marker": OLD_50D_MARKER,
            "new_marker": NEW_50D_MARKER,
        }

        # ---------------- Shadow ----------------
        shadow_info = copy_shadow(candidates)
        data["shadow"] = shadow_info

        shadow_results = run_validation_suite(SHADOW, label="SHADOW")
        data["shadow_validations"] = shadow_results

        shadow_package = json_load(SHADOW / "electron" / "package.json")
        shadow_lock = json_load(SHADOW / "electron" / "package-lock.json")
        require(shadow_package.get("version") == NEXT_VERSION, "Shadow package version 실패")
        require(shadow_lock.get("version") == NEXT_VERSION, "Shadow lock version 실패")
        require(
            (shadow_lock.get("packages") or {}).get("", {}).get("version")
            == NEXT_VERSION,
            "Shadow lock root version 실패",
        )

        print("[PASS] Stage68E Shadow")
        print("shadow_version=0.5.16")
        print("shadow_npm_check=PASS")
        print("shadow_50B_50C_50D=PASS")
        print("shadow_release_version=PASS")

        # ---------------- Actual ----------------
        before_protected = {
            "data": sha256(DATA),
            "service": sha256(SERVICE),
            "styles": sha256(STYLES),
        }

        for path in (PACKAGE, LOCK, FIFTYD):
            backups[path] = path.read_bytes()

        actual_started = True

        shutil.copy2(SHADOW / "electron" / "package.json", PACKAGE)
        shutil.copy2(SHADOW / "electron" / "package-lock.json", LOCK)
        shutil.copy2(SHADOW / FIFTYD.name, FIFTYD)

        actual_results = run_validation_suite(ROOT, label="ACTUAL")
        data["actual_validations"] = actual_results

        guard = final_guard(before_protected)
        data["final_guard"] = guard

        write_summary("PASS", data)

        print("[PASS] Stage68E 0.5.16 Release Prep Actual")
        print("package_version=0.5.16")
        print("lock_version=0.5.16")
        print("50D_marker=V15_0516")
        print("final_changed_tracked=4")
        print("final_new_validator=1")
        print("total_release_files_changed=5")
        print("staging=EMPTY")
        print("electron-v0.5.16_tag=ABSENT")
        print("runtime_json=UNCHANGED")
        print("search_service=UNCHANGED")
        print("styles=UNCHANGED")
        print("readiness=READY_FOR_0516_COMMIT_PUSH_RC")
        print(f"report={REPORT_TXT.relative_to(ROOT)}")
        print(f"json={REPORT_JSON.relative_to(ROOT)}")
        return 0

    except Exception as exc:
        if actual_started:
            for path, content in backups.items():
                path.write_bytes(content)

            data["rollback"] = {
                "performed": True,
                "files": [str(p.relative_to(ROOT)) for p in backups],
                "stage68d_preserved": True,
            }

        write_summary(
            "FAIL_ROLLED_BACK" if actual_started else "FAIL_BEFORE_ACTUAL",
            data,
            str(exc),
        )

        if actual_started:
            print("[FAIL] Stage68E Actual — release-prep 3개 rollback 완료")
            print("Stage68D_changes=PRESERVED")
        else:
            print("[FAIL] Stage68E Shadow/Preflight — Actual 미수행")

        print(str(exc).splitlines()[0][:1000])
        print(f"report={REPORT_TXT.relative_to(ROOT)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
