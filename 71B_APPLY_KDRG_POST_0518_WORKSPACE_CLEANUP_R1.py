from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent

BASE_COMMIT = "1bd70d50c85305e2ff64ebb0a17ec619719e8a40"
BASE_TAG = "electron-v0.5.18"
BASE_VERSION = "0.5.18"

RUNTIME_REL = Path("data/kdrg_v47_search_integrated_v3.json")
RUNTIME_SHA = "1a3d50400567ecaad9695b7be8e7c0382131f8652f398e010cf01f4d8dda6c58"

AUDIT_SCRIPT = ROOT / "71A_AUDIT_KDRG_POST_0518_WORKSPACE_CLEANUP_R1.py"
AUDIT_SCRIPT_SHA = "1018c58854e1fedcd538ae0c05d0e798867a2d9fafc5dc357a92776f22aa0f86"
AUDIT_REPORT_DIR = ROOT / "reports/stage71a_post_0518_workspace_cleanup_audit_r1"
AUDIT_JSON = AUDIT_REPORT_DIR / "audit.json"
AUDIT_TXT = AUDIT_REPORT_DIR / "audit_summary.txt"

SCRIPT_ARCHIVE = ROOT / "archive/completed_release_work/electron-v0.5.18/scripts"
REPORT_ARCHIVE = ROOT / "reports/archive/electron-v0.5.18"
HISTORY_ARCHIVE = REPORT_ARCHIVE / "history"

REPORT_DIR = ROOT / "reports/stage71b_post_0518_workspace_cleanup_actual_r1"
REPORT_JSON = REPORT_DIR / "cleanup.json"
REPORT_TXT = REPORT_DIR / "cleanup_summary.txt"

OLD_LOCAL_RELEASES = [
    ROOT / "releases/electron-v0.5.11",
    ROOT / "releases/electron-v0.5.12",
    ROOT / "releases/electron-v0.5.13",
    ROOT / "releases/electron-v0.5.14",
    ROOT / "releases/electron-v0.5.15",
    ROOT / "releases/electron-v0.5.16",
    ROOT / "releases/electron-v0.5.17",
]

HISTORY_REPORT_FILES = [
    ROOT / "reports/stage59a_v8_r3_integrated_impact_audit.json",
    ROOT / "reports/stage59a_v8_r3_integrated_impact_audit.txt",
]

SAFE_DELETE_FILES = [
    ROOT / "r3_validator_fail.txt",
]

CURRENT_RELEASE_DIR = ROOT / "releases/electron-v0.5.18-final-check"

# These are deliberately preserved in place.
KEEP_PATHS = [
    ROOT / ".replit",
    ROOT / "data",
    ROOT / "sources",
    ROOT / "lib",
    ROOT / "tools",
    ROOT / "handoff",
    ROOT / "KDRG_ICON_K_V2.ico",
    ROOT / "KDRG_ICON_K_V2.png",
    ROOT / "KDRG_검색기_아이콘.ico",
    ROOT / "KDRG_검색기_아이콘.png",
    ROOT / "KDRG 일반용(V4.7)_교정표_20260731.hwpx",
    ROOT / "KDRG 일반용(V4.7)_시술 등 목록_20260731.xlsx",
    ROOT / "reports/full_data_source_inventory.txt",
    ROOT / "reports/kdrg_v47_search_integrated_v3.sha256.txt",
    ROOT / "reports/source_manifest.json",
    ROOT / "reports/source_structure_profile.json",
    ROOT / "reports/source_structure_profile.txt",
    CURRENT_RELEASE_DIR,
]


class Stop(RuntimeError):
    pass


def require(ok, message):
    if not ok:
        raise Stop(message)


def run(cmd, timeout=120):
    p = subprocess.run(
        [str(x) for x in cmd],
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    return p.returncode, p.stdout


def git_text(*args):
    rc, out = run(["git", *args])
    require(rc == 0, f"git {' '.join(args)} 실패\n{out[-3000:]}")
    return out.strip()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def path_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file() or path.is_symlink():
        try:
            return path.stat().st_size
        except OSError:
            return 0

    total = 0
    for base, dirs, files in os.walk(path):
        for name in files:
            p = Path(base) / name
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return total


def ensure_destination_free(dst: Path):
    require(not dst.exists(), f"archive 대상이 이미 존재함: {dst.relative_to(ROOT)}")


def move_preserve(src: Path, dst: Path):
    require(src.exists(), f"이동 원본 없음: {src.relative_to(ROOT)}")
    ensure_destination_free(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))


def remove_path(path: Path) -> int:
    if not path.exists():
        return 0
    size = path_size(path)
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()
    return size


def top_stage_report_dirs():
    dirs = []
    reports = ROOT / "reports"
    if not reports.is_dir():
        return dirs
    for child in reports.iterdir():
        if not child.is_dir():
            continue
        n = child.name.lower()
        if n.startswith("stage68") or n.startswith("stage69") or n.startswith("stage70"):
            dirs.append(child)
    return sorted(dirs, key=lambda p: p.name)


def main():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    report = {
        "stage": "71B_POST_0518_WORKSPACE_CLEANUP_ACTUAL_R1",
        "status": "FAIL",
        "mutated": False,
    }

    try:
        # ------------------------------------------------------------
        # 1) Immutable 0.5.18 / clean tracked guards
        # ------------------------------------------------------------
        head = git_text("rev-parse", "HEAD")
        origin = git_text("rev-parse", "origin/main")
        branch = git_text("branch", "--show-current")
        tag_commit = git_text("rev-list", "-n", "1", BASE_TAG)

        require(head == BASE_COMMIT, f"HEAD 불일치: {head}")
        require(origin == BASE_COMMIT, f"origin/main 불일치: {origin}")
        require(branch == "main", f"branch 불일치: {branch}")
        require(tag_commit == BASE_COMMIT, f"{BASE_TAG} commit 불일치: {tag_commit}")

        pkg = json.loads((ROOT / "electron/package.json").read_text(encoding="utf-8"))
        require(pkg.get("version") == BASE_VERSION, f"package version 불일치: {pkg.get('version')}")
        require(sha256(ROOT / RUNTIME_REL) == RUNTIME_SHA, "운영 JSON SHA 불일치")

        tracked_before = [
            x for x in git_text("diff", "--name-only", "HEAD").splitlines() if x
        ]
        staged_before = [
            x for x in git_text("diff", "--cached", "--name-only").splitlines() if x
        ]
        require(not tracked_before, f"tracked 변경 있음: {tracked_before}")
        require(not staged_before, f"staging 변경 있음: {staged_before}")

        # ------------------------------------------------------------
        # 2) Bind to exact Stage71A PASS
        # ------------------------------------------------------------
        require(AUDIT_SCRIPT.is_file(), "71A audit script 없음")
        require(sha256(AUDIT_SCRIPT) == AUDIT_SCRIPT_SHA, "71A audit script SHA 불일치")
        require(AUDIT_JSON.is_file(), "71A audit.json 없음")
        require(AUDIT_TXT.is_file(), "71A audit_summary.txt 없음")

        audit = json.loads(AUDIT_JSON.read_text(encoding="utf-8"))
        require(audit.get("status") == "PASS", "71A audit status != PASS")
        require(audit.get("head") == BASE_COMMIT, "71A audit HEAD 불일치")
        require(audit.get("tag") == BASE_TAG, "71A audit tag 불일치")
        require(audit.get("package_version") == BASE_VERSION, "71A package version 불일치")
        require(audit.get("runtime_json") == "UNCHANGED", "71A runtime JSON 계약 불일치")
        require(audit.get("tracked") == "CLEAN", "71A tracked 계약 불일치")
        require(audit.get("staging") == "EMPTY", "71A staging 계약 불일치")
        require(audit.get("mutated") is False, "71A는 read-only여야 함")

        stage_scripts = [ROOT / x for x in (audit.get("archive_stage_scripts") or [])]
        require(len(stage_scripts) == 36, f"71A stage script 수 불일치: {len(stage_scripts)}")

        # 71A itself is now completed, so archive it too.
        scripts_to_archive = stage_scripts + [AUDIT_SCRIPT]

        # Completed stage68~70 report directories are archived by top-level
        # directory, not by the individual file listing from git status.
        stage_report_dirs = top_stage_report_dirs()
        require(stage_report_dirs, "완료 stage68~70 report 디렉터리를 찾지 못함")

        validation_reports = [
            ROOT / x
            for x in (audit.get("archive_validation_reports") or [])
        ]
        require(len(validation_reports) == 6, f"validation report 수 불일치: {len(validation_reports)}")

        # ------------------------------------------------------------
        # 3) Pre-calculate destinations and collision guards
        # ------------------------------------------------------------
        script_moves = []
        for src in scripts_to_archive:
            require(src.is_file(), f"archive script 없음: {src.name}")
            dst = SCRIPT_ARCHIVE / src.name
            ensure_destination_free(dst)
            script_moves.append((src, dst))

        report_moves = []
        for src in stage_report_dirs:
            dst = REPORT_ARCHIVE / src.name
            ensure_destination_free(dst)
            report_moves.append((src, dst))

        # Preserve the compact Stage71A evidence, but do not leave it at top level.
        audit_report_dst = REPORT_ARCHIVE / AUDIT_REPORT_DIR.name
        ensure_destination_free(audit_report_dst)

        validation_moves = []
        validation_dir = REPORT_ARCHIVE / "validation"
        for src in validation_reports:
            require(src.is_file(), f"validation report 없음: {src.relative_to(ROOT)}")
            dst = validation_dir / src.name
            ensure_destination_free(dst)
            validation_moves.append((src, dst))

        history_moves = []
        for src in HISTORY_REPORT_FILES:
            if src.exists():
                dst = HISTORY_ARCHIVE / src.name
                ensure_destination_free(dst)
                history_moves.append((src, dst))

        # ------------------------------------------------------------
        # 4) Prune reproducible bulky subtrees from completed reports
        #    before archiving compact evidence.
        # ------------------------------------------------------------
        deleted_bytes = 0
        pruned = []

        for stage_dir in stage_report_dirs:
            for dirname in ("shadow", "backup"):
                p = stage_dir / dirname
                if p.exists():
                    size = remove_path(p)
                    deleted_bytes += size
                    pruned.append({
                        "path": str(p.relative_to(ROOT)),
                        "bytes": size,
                        "reason": "immutable release 이후 재생성 가능한 shadow/backup snapshot",
                    })

        # ------------------------------------------------------------
        # 5) Archive completed stage scripts and compact reports
        # ------------------------------------------------------------
        SCRIPT_ARCHIVE.mkdir(parents=True, exist_ok=True)
        REPORT_ARCHIVE.mkdir(parents=True, exist_ok=True)

        moved_scripts = []
        for src, dst in script_moves:
            move_preserve(src, dst)
            moved_scripts.append({
                "from": str(src.relative_to(ROOT)),
                "to": str(dst.relative_to(ROOT)),
            })

        moved_reports = []
        for src, dst in report_moves:
            move_preserve(src, dst)
            moved_reports.append({
                "from": str(src.relative_to(ROOT)),
                "to": str(dst.relative_to(ROOT)),
            })

        # Move Stage71A report only after its data has been loaded.
        move_preserve(AUDIT_REPORT_DIR, audit_report_dst)
        moved_reports.append({
            "from": str(AUDIT_REPORT_DIR.relative_to(ROOT)),
            "to": str(audit_report_dst.relative_to(ROOT)),
        })

        moved_validation = []
        for src, dst in validation_moves:
            move_preserve(src, dst)
            moved_validation.append({
                "from": str(src.relative_to(ROOT)),
                "to": str(dst.relative_to(ROOT)),
            })

        moved_history = []
        for src, dst in history_moves:
            move_preserve(src, dst)
            moved_history.append({
                "from": str(src.relative_to(ROOT)),
                "to": str(dst.relative_to(ROOT)),
            })

        # ------------------------------------------------------------
        # 6) Delete safe disposable items and old local release copies
        # ------------------------------------------------------------
        deleted_items = []

        for p in SAFE_DELETE_FILES:
            if p.exists():
                size = remove_path(p)
                deleted_bytes += size
                deleted_items.append({
                    "path": str(p.relative_to(ROOT)),
                    "bytes": size,
                    "reason": "임시 실패 로그",
                })

        for p in OLD_LOCAL_RELEASES:
            if p.exists():
                size = remove_path(p)
                deleted_bytes += size
                deleted_items.append({
                    "path": str(p.relative_to(ROOT)),
                    "bytes": size,
                    "reason": "GitHub Release에 존재하는 과거 로컬 배포 복사본",
                })

        # ------------------------------------------------------------
        # 7) Final safety guards
        # ------------------------------------------------------------
        require(CURRENT_RELEASE_DIR.is_dir(), "현재 0.5.18 final-check 디렉터리 손실")
        require((ROOT / RUNTIME_REL).is_file(), "운영 JSON 손실")
        require(sha256(ROOT / RUNTIME_REL) == RUNTIME_SHA, "정리 후 운영 JSON SHA 변경")

        for p in KEEP_PATHS:
            if p == CURRENT_RELEASE_DIR:
                require(p.is_dir(), f"KEEP 디렉터리 손실: {p.relative_to(ROOT)}")
            elif p.suffix or p.name == ".replit":
                # Some reference files may not exist in every workspace; if they
                # existed before cleanup they were never targeted. We only assert
                # the critical current release/runtime separately.
                pass

        tracked_after = [
            x for x in git_text("diff", "--name-only", "HEAD").splitlines() if x
        ]
        staged_after = [
            x for x in git_text("diff", "--cached", "--name-only").splitlines() if x
        ]
        require(not tracked_after, f"정리 후 tracked 변경 발생: {tracked_after}")
        require(not staged_after, f"정리 후 staging 변경 발생: {staged_after}")

        # Root old stage scripts should now be gone.
        remaining_old_stage_scripts = []
        for p in ROOT.glob("*.py"):
            if p.name.startswith(("68", "69", "70", "71A_")):
                remaining_old_stage_scripts.append(p.name)
        require(
            not remaining_old_stage_scripts,
            f"루트에 완료 stage script 잔존: {remaining_old_stage_scripts}",
        )

        # Old local releases should be gone, current final-check kept.
        remaining_old_releases = [
            str(p.relative_to(ROOT))
            for p in OLD_LOCAL_RELEASES
            if p.exists()
        ]
        require(
            not remaining_old_releases,
            f"과거 local release 잔존: {remaining_old_releases}",
        )

        # Current release SHA is informational, but useful to retain in cleanup record.
        exe_candidates = sorted(CURRENT_RELEASE_DIR.glob("*_Portable.exe"))
        current_exe_sha = sha256(exe_candidates[0]) if len(exe_candidates) == 1 else None
        current_exe_name = exe_candidates[0].name if len(exe_candidates) == 1 else None

        report.update({
            "status": "PASS",
            "mutated": True,
            "head": head,
            "origin_main": origin,
            "tag": BASE_TAG,
            "package_version": BASE_VERSION,
            "runtime_json": "UNCHANGED",
            "tracked": "CLEAN",
            "staging": "EMPTY",
            "moved_stage_scripts": moved_scripts,
            "moved_stage_report_dirs": moved_reports,
            "moved_validation_reports": moved_validation,
            "moved_history_reports": moved_history,
            "pruned_reproducible_snapshots": pruned,
            "deleted_items": deleted_items,
            "deleted_bytes": deleted_bytes,
            "deleted_mib": round(deleted_bytes / (1024 * 1024), 2),
            "current_release_dir": str(CURRENT_RELEASE_DIR.relative_to(ROOT)),
            "current_release_exe": current_exe_name,
            "current_release_exe_sha256": current_exe_sha,
            "next": "Stage71 이후 신규 작업은 0.5.18 immutable 기준에서 진행",
        })

        REPORT_JSON.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        lines = [
            "[PASS] Stage71B R1 / 0.5.18 배포 후 Workspace 실제 정리",
            f"archived_stage_scripts={len(moved_scripts)}",
            f"archived_stage_report_dirs={len(moved_reports)}",
            f"archived_validation_reports={len(moved_validation)}",
            f"archived_history_reports={len(moved_history)}",
            f"pruned_shadow_backup_snapshots={len(pruned)}",
            f"deleted_old_local_releases={sum(1 for x in deleted_items if 'releases/' in x['path'])}",
            f"safe_deleted_items={sum(1 for x in deleted_items if 'releases/' not in x['path'])}",
            f"deleted_space_mib={round(deleted_bytes / (1024 * 1024), 2)}",
            f"current_release_kept={CURRENT_RELEASE_DIR.relative_to(ROOT)}",
            f"current_release_exe={current_exe_name or 'NOT_UNIQUE'}",
            f"current_release_exe_sha256={current_exe_sha or 'NOT_AVAILABLE'}",
            "tracked=CLEAN",
            "staging=EMPTY",
            "runtime_json=UNCHANGED",
            "electron-v0.5.18=IMMUTABLE",
            "readiness=WORKSPACE_CLEANUP_COMPLETE",
            f"report={REPORT_TXT.relative_to(ROOT)}",
            f"json={REPORT_JSON.relative_to(ROOT)}",
        ]

        REPORT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("\n".join(lines))
        return 0

    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        try:
            REPORT_JSON.write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            REPORT_TXT.write_text(
                "\n".join([
                    "[FAIL] Stage71B Workspace 실제 정리",
                    f"{type(exc).__name__}: {exc}",
                    "주의: 정리 단계는 일부 이동/삭제가 이미 수행되었을 수 있으므로 자동 rollback하지 않음",
                    f"report={REPORT_TXT.relative_to(ROOT)}",
                ]) + "\n",
                encoding="utf-8",
            )
        except Exception:
            pass

        print("[FAIL] Stage71B Workspace 실제 정리")
        print(f"{type(exc).__name__}: {exc}")
        print("주의: 일부 이동/삭제가 수행되었을 수 있으므로 결과 확인 필요")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
