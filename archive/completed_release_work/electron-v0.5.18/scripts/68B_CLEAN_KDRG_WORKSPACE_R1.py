#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KDRG workspace cleanup R1

기준
----
- 68A 감사 JSON을 근거로만 정리한다.
- Git 추적 파일은 절대 삭제/이동하지 않는다.
- 50B/50C/50D 핵심 검증기는 보존한다.
- 과거 untracked Stage .py 는 삭제한다.
- 최종 0.5.15 작업 .py 는 root에서 치우되 archive로 이동한다.
- root의 untracked stage*.txt/json 보고서는 reports/archive로 이동한다.
- releases/ 루트의 낙오 파일은:
    * 버전 폴더 안 동일 SHA 파일이 있으면 삭제
    * 동일 파일이 없으면 releases/_unclassified 로 이동
- 실제 제품/데이터/electron/.github/git history/tag/release는 건드리지 않는다.

이 스크립트는 되돌릴 수 없는 삭제를 최소화하기 위해
'오래된 untracked Stage .py'만 삭제하고,
최신 0.5.15 작업파일과 보고서는 archive로 보존한다.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time

ROOT = Path.cwd().resolve()

AUDIT_JSON = ROOT / "kdrg_workspace_cleanup_audit_r1.json"

ARCHIVE_ROOT = ROOT / "archive" / "kdrg_workspace_cleanup_20260923"
ARCHIVE_0515_PY = ARCHIVE_ROOT / "electron_0.5.15_stage_scripts"
ARCHIVE_REPORTS = ROOT / "reports" / "archive" / "root_stage_history"
UNCLASSIFIED_RELEASES = ROOT / "releases" / "_unclassified"

REPORT_DIR = ROOT / "reports" / "workspace_cleanup"
REPORT_TXT = REPORT_DIR / "kdrg_workspace_cleanup_r1.txt"
REPORT_JSON = REPORT_DIR / "kdrg_workspace_cleanup_r1.json"

PROTECTED_ROOT_PY = {
    "50B_validate_kdrg_electron_search_service.py",
    "50C_validate_kdrg_electron_renderer_ui.py",
    "50D_validate_kdrg_electron_windows_packaging.py",
}

SAFE_OLD_CATEGORY = "SAFE_CANDIDATE_UNTRACKED_HISTORICAL_STAGE_PY"
KEEP_0515_CATEGORY = "KEEP_CURRENT_0515_AUDIT_TRAIL"


class CleanupError(RuntimeError):
    pass


def require(value, message):
    if not value:
        raise CleanupError(message)


def run(cmd):
    p = subprocess.run(
        [str(x) for x in cmd],
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return p.returncode, p.stdout


def git_tracked_set():
    rc, out = run(["git", "ls-files"])
    require(rc == 0, "git ls-files failed")
    return {x.strip() for x in out.splitlines() if x.strip()}


def git_status_lines():
    rc, out = run(["git", "status", "--short"])
    require(rc == 0, "git status failed")
    return [x for x in out.splitlines() if x.strip()]


def sha256_path(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def unique_destination(base_dir, source_name):
    base_dir.mkdir(parents=True, exist_ok=True)
    candidate = base_dir / source_name
    if not candidate.exists():
        return candidate

    stem = Path(source_name).stem
    suffix = Path(source_name).suffix
    n = 2
    while True:
        candidate = base_dir / f"{stem}__{n}{suffix}"
        if not candidate.exists():
            return candidate
        n += 1


def move_preserving(source, dest_dir):
    dest = unique_destination(dest_dir, source.name)
    shutil.move(str(source), str(dest))
    return dest


def audit_gate(audit, tracked):
    require(audit.get("policy", {}).get("no_changes_performed") is True,
            "68A audit is not read-only PASS data")

    root_py = audit.get("root_python") or []

    # 감사 당시 tracked로 판단된 파일이 삭제 후보에 섞이면 즉시 중단.
    for item in root_py:
        category = item.get("category")
        path = item.get("path")
        if category in (SAFE_OLD_CATEGORY, KEEP_0515_CATEGORY):
            require(item.get("tracked") is False,
                    f"audit candidate unexpectedly tracked: {path}")
            require(path not in tracked,
                    f"candidate is tracked now: {path}")

    for name in PROTECTED_ROOT_PY:
        require((ROOT / name).is_file(), f"protected validator missing: {name}")
        require(name in tracked or (ROOT / name).exists(),
                f"protected validator unavailable: {name}")


def delete_old_untracked_stage_py(audit, tracked):
    deleted = []
    skipped = []

    for item in audit.get("root_python") or []:
        if item.get("category") != SAFE_OLD_CATEGORY:
            continue

        rel = item.get("path")
        if not rel:
            continue

        path = ROOT / rel

        if rel in tracked:
            skipped.append({"path": rel, "reason": "TRACKED_NOW"})
            continue

        if not path.exists():
            skipped.append({"path": rel, "reason": "ALREADY_MISSING"})
            continue

        require(path.parent == ROOT,
                f"refuse non-root delete candidate: {rel}")
        require(path.suffix.lower() == ".py",
                f"refuse non-py delete candidate: {rel}")
        require(path.name not in PROTECTED_ROOT_PY,
                f"refuse protected validator: {rel}")

        deleted.append({
            "path": rel,
            "size_bytes": path.stat().st_size,
            "sha256": sha256_path(path),
        })
        path.unlink()

    return deleted, skipped


def archive_current_0515_py(audit, tracked):
    moved = []
    skipped = []

    for item in audit.get("root_python") or []:
        if item.get("category") != KEEP_0515_CATEGORY:
            continue

        rel = item.get("path")
        if not rel:
            continue

        path = ROOT / rel

        if rel in tracked:
            skipped.append({"path": rel, "reason": "TRACKED_NOW"})
            continue

        if not path.exists():
            skipped.append({"path": rel, "reason": "ALREADY_MISSING"})
            continue

        require(path.parent == ROOT,
                f"refuse non-root 0.5.15 archive candidate: {rel}")
        require(path.suffix.lower() == ".py",
                f"refuse non-py 0.5.15 archive candidate: {rel}")

        before_sha = sha256_path(path)
        dest = move_preserving(path, ARCHIVE_0515_PY)
        require(sha256_path(dest) == before_sha,
                f"archive SHA mismatch: {rel}")

        moved.append({
            "from": rel,
            "to": dest.relative_to(ROOT).as_posix(),
            "sha256": before_sha,
        })

    return moved, skipped


def archive_root_stage_reports(audit, tracked):
    moved = []
    skipped = []

    for item in audit.get("root_stage_reports") or []:
        rel = item.get("path")
        if not rel:
            continue

        path = ROOT / rel

        if item.get("tracked") is True or rel in tracked:
            skipped.append({"path": rel, "reason": "TRACKED"})
            continue

        if not path.exists():
            skipped.append({"path": rel, "reason": "ALREADY_MISSING"})
            continue

        require(path.parent == ROOT,
                f"refuse non-root report candidate: {rel}")
        require(path.suffix.lower() in (".txt", ".json"),
                f"refuse report extension: {rel}")
        require(path.name.lower().startswith("stage"),
                f"refuse non-stage report: {rel}")

        before_sha = sha256_path(path)
        dest = move_preserving(path, ARCHIVE_REPORTS)
        require(sha256_path(dest) == before_sha,
                f"report archive SHA mismatch: {rel}")

        moved.append({
            "from": rel,
            "to": dest.relative_to(ROOT).as_posix(),
            "sha256": before_sha,
        })

    return moved, skipped


def release_version_files():
    releases = ROOT / "releases"
    mapping = {}

    if not releases.is_dir():
        return mapping

    for d in releases.iterdir():
        if not d.is_dir():
            continue
        if d.name.startswith("_"):
            continue

        for f in d.iterdir():
            if f.is_file():
                mapping.setdefault(f.name, []).append(f)

    return mapping


def cleanup_release_strays(audit, tracked):
    releases = ROOT / "releases"
    duplicates_deleted = []
    moved_unclassified = []
    skipped = []

    mapping = release_version_files()

    for item in (audit.get("releases") or {}).get("stray_files") or []:
        name = item.get("name")
        if not name:
            continue

        rel = f"releases/{name}"
        path = releases / name

        if rel in tracked:
            skipped.append({"path": rel, "reason": "TRACKED"})
            continue

        if not path.exists():
            skipped.append({"path": rel, "reason": "ALREADY_MISSING"})
            continue

        source_sha = sha256_path(path)
        exact_matches = []

        for candidate in mapping.get(name, []):
            if candidate.exists() and sha256_path(candidate) == source_sha:
                exact_matches.append(candidate)

        if exact_matches:
            duplicates_deleted.append({
                "path": rel,
                "sha256": source_sha,
                "duplicate_of": [
                    p.relative_to(ROOT).as_posix() for p in exact_matches
                ],
            })
            path.unlink()
        else:
            dest = move_preserving(path, UNCLASSIFIED_RELEASES)
            require(sha256_path(dest) == source_sha,
                    f"release stray archive SHA mismatch: {rel}")
            moved_unclassified.append({
                "from": rel,
                "to": dest.relative_to(ROOT).as_posix(),
                "sha256": source_sha,
            })

    return duplicates_deleted, moved_unclassified, skipped


def final_guard(tracked_before):
    # 핵심 검증기는 그대로 있어야 한다.
    for name in PROTECTED_ROOT_PY:
        require((ROOT / name).is_file(),
                f"protected validator missing after cleanup: {name}")

    # 제품/릴리즈 핵심 폴더가 있어야 한다.
    require((ROOT / "electron").is_dir(), "electron directory missing")
    require((ROOT / "data").is_dir(), "data directory missing")
    require((ROOT / ".github").is_dir(), ".github directory missing")

    # 0.5.15 최종 release folder 필수 파일 확인.
    rel_dir = ROOT / "releases" / "electron-v0.5.15"
    exe = rel_dir / "KDRG_V47_Relation_Search_Electron_0.5.15_Portable.exe"
    sums = rel_dir / "SHA256SUMS_ELECTRON.txt"

    require(exe.is_file(), "0.5.15 Portable EXE missing")
    require(sums.is_file(), "0.5.15 SHA256SUMS missing")

    # Git tracked working tree는 cleanup으로 수정되면 안 된다.
    rc, out = run(["git", "diff", "--name-only"])
    require(rc == 0, "git diff failed")
    require(not out.strip(),
            "cleanup changed tracked files: " + out.strip())

    rc, out_cached = run(["git", "diff", "--cached", "--name-only"])
    require(rc == 0, "git cached diff failed")
    require(not out_cached.strip(),
            "cleanup changed staging: " + out_cached.strip())

    tracked_after = git_tracked_set()
    require(tracked_after == tracked_before,
            "tracked file set changed during cleanup")

    return {
        "core_validators_present": True,
        "electron_data_github_present": True,
        "release_0515_present": True,
        "tracked_diff_clean": True,
        "staging_empty": True,
        "tracked_file_set_unchanged": True,
    }


def main():
    require(AUDIT_JSON.is_file(),
            "kdrg_workspace_cleanup_audit_r1.json missing")

    audit = json.loads(AUDIT_JSON.read_text(encoding="utf-8"))
    tracked_before = git_tracked_set()

    audit_gate(audit, tracked_before)

    deleted_py, skipped_py = delete_old_untracked_stage_py(
        audit, tracked_before
    )
    archived_0515, skipped_0515 = archive_current_0515_py(
        audit, tracked_before
    )
    archived_reports, skipped_reports = archive_root_stage_reports(
        audit, tracked_before
    )
    release_dupes, release_unclassified, release_skipped = (
        cleanup_release_strays(audit, tracked_before)
    )

    final = final_guard(tracked_before)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    payload = {
        "status": "PASS",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "deleted_old_untracked_stage_py": deleted_py,
        "archived_current_0515_py": archived_0515,
        "archived_root_stage_reports": archived_reports,
        "release_duplicate_strays_deleted": release_dupes,
        "release_strays_moved_unclassified": release_unclassified,
        "skipped": {
            "old_py": skipped_py,
            "current_0515_py": skipped_0515,
            "reports": skipped_reports,
            "release_strays": release_skipped,
        },
        "final_guard": final,
    }

    REPORT_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    lines = [
        "KDRG workspace cleanup R1",
        "=" * 72,
        "status=PASS",
        f"deleted_old_untracked_stage_py={len(deleted_py)}",
        f"archived_current_0515_py={len(archived_0515)}",
        f"archived_root_stage_reports={len(archived_reports)}",
        f"release_duplicate_strays_deleted={len(release_dupes)}",
        f"release_strays_moved_unclassified={len(release_unclassified)}",
        "",
        "[FINAL GUARD]",
        json.dumps(final, ensure_ascii=False, indent=2),
        "",
        f"archive_0515_py={ARCHIVE_0515_PY}",
        f"archive_reports={ARCHIVE_REPORTS}",
        f"unclassified_releases={UNCLASSIFIED_RELEASES}",
        f"report_json={REPORT_JSON}",
    ]

    REPORT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("[PASS] KDRG workspace cleanup R1")
    print(f"deleted_old_stage_py={len(deleted_py)}")
    print(f"archived_0515_stage_py={len(archived_0515)}")
    print(f"archived_stage_reports={len(archived_reports)}")
    print(f"release_duplicate_deleted={len(release_dupes)}")
    print(f"release_unclassified_moved={len(release_unclassified)}")
    print("[PASS] tracked files unchanged / staging empty")
    print("[PASS] 0.5.15 release folder preserved")
    print(f"report_txt={REPORT_TXT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
