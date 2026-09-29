from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent

BASE_COMMIT = "1bd70d50c85305e2ff64ebb0a17ec619719e8a40"
BASE_TAG = "electron-v0.5.18"
BASE_VERSION = "0.5.18"
RUNTIME_REL = Path("data/kdrg_v47_search_integrated_v3.json")
RUNTIME_SHA = "1a3d50400567ecaad9695b7be8e7c0382131f8652f398e010cf01f4d8dda6c58"

REPORT_DIR = ROOT / "reports/stage71a_post_0518_workspace_cleanup_audit_r1"
REPORT_JSON = REPORT_DIR / "audit.json"
REPORT_TXT = REPORT_DIR / "audit_summary.txt"

# Root-level Stage work scripts from completed 0.5.16~0.5.18 work.
STAGE_SCRIPT_RE = re.compile(r"^(68|69|70)[A-Z0-9_].*\.py$", re.I)

# Completed stage report directories from 0.5.16~0.5.18 work.
STAGE_REPORT_RE = re.compile(
    r"^reports/(stage68|stage69|stage70)[^/]*(?:/.*)?$",
    re.I,
)

# Old generated validator reports are reproducible and can be archived.
VALIDATION_REPORT_RE = re.compile(
    r"^reports/electron_stage50[BCD]_validation_report\.(json|txt)$",
    re.I,
)

# Obvious disposable scratch artifacts.
SAFE_DELETE_EXACT = {
    "r3_validator_fail.txt",
}

# Keep these as active/reference assets for now.
KEEP_PREFIXES = (
    "data/",
    "sources/",
    "lib/",
    "tools/",
    "handoff/",
    "archive/",
)

KEEP_EXACT = {
    ".replit",
    "SHA256SUMS.json",
    "KDRG_ICON_K_V2.ico",
    "KDRG_ICON_K_V2.png",
    "KDRG_검색기_아이콘.ico",
    "KDRG_검색기_아이콘.png",
    "KDRG 일반용(V4.7)_교정표_20260731.hwpx",
    "KDRG 일반용(V4.7)_시술 등 목록_20260731.xlsx",
    "electron/tests/run-stage51d-runtime-ui-preview.js",
    "kdrg_workspace_cleanup_audit_r1.json",
    "kdrg_workspace_cleanup_audit_r1.txt",
}

# Keep current final-check release directory.
KEEP_RELEASE_PREFIX = "releases/electron-v0.5.18-final-check/"


class Stop(RuntimeError):
    pass


def require(ok, msg):
    if not ok:
        raise Stop(msg)


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


def normalize_status_name(line: str) -> tuple[str, str]:
    status = line[:2]
    name = line[3:]

    # Rename entries can be "old -> new". For this audit we only care about
    # current untracked paths, so keep status parsing simple and strict.
    return status, name


def classify(path: str) -> tuple[str, str]:
    name = Path(path).name

    if path in SAFE_DELETE_EXACT:
        return "SAFE_DELETE", "실패/임시 scratch 파일"

    if STAGE_SCRIPT_RE.match(name) and "/" not in path:
        return "ARCHIVE_STAGE_SCRIPT", "완료된 0.5.16~0.5.18 단계 작업 Python"

    if STAGE_REPORT_RE.match(path):
        return "ARCHIVE_STAGE_REPORT", "완료된 0.5.16~0.5.18 단계 report"

    if VALIDATION_REPORT_RE.match(path):
        return "ARCHIVE_VALIDATION_REPORT", "재생성 가능한 Stage50 검증 report"

    if path.startswith(KEEP_RELEASE_PREFIX):
        return "KEEP", "0.5.18 최종 배포 실물 검증본"

    if path == "releases":
        return "KEEP", "릴리스 보관 디렉터리"

    if path in KEEP_EXACT:
        return "KEEP", "현재 기준/reference 파일"

    if any(path.startswith(prefix) for prefix in KEEP_PREFIXES):
        return "KEEP", "데이터·소스·도구·보관 자산"

    if path.startswith("reports/archive/"):
        return "KEEP", "기존 report archive"

    if path.startswith("reports/workspace_cleanup/"):
        return "KEEP", "기존 workspace cleanup 기록"

    if path.startswith("reports/"):
        return "REVIEW", "Stage68~70 외 report — 자동 삭제 금지"

    return "REVIEW", "자동 분류 근거 부족 — 수동 확인 필요"


def main():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    report = {
        "stage": "71A_POST_0518_WORKSPACE_CLEANUP_AUDIT_R1",
        "status": "FAIL",
        "mutated": False,
    }

    try:
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

        tracked_changed = [
            x for x in git_text("diff", "--name-only", "HEAD").splitlines() if x
        ]
        staged = [
            x for x in git_text("diff", "--cached", "--name-only").splitlines() if x
        ]

        require(not tracked_changed, f"tracked 변경 있음: {tracked_changed}")
        require(not staged, f"staging 변경 있음: {staged}")

        rc, status_out = run(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"],
            timeout=120,
        )
        require(rc == 0, f"git status 실패\n{status_out[-3000:]}")

        rows = []
        for raw in status_out.splitlines():
            if not raw:
                continue
            status, path = normalize_status_name(raw)

            # At this point all tracked/staged changes were already forbidden.
            # Only untracked items are expected.
            require(
                status == "??",
                f"예상하지 않은 tracked/staged 상태 발견: {raw}",
            )

            category, reason = classify(path)
            rows.append({
                "path": path,
                "category": category,
                "reason": reason,
            })

        categories = {}
        for row in rows:
            categories.setdefault(row["category"], []).append(row["path"])

        for values in categories.values():
            values.sort()

        archive_stage_scripts = categories.get("ARCHIVE_STAGE_SCRIPT", [])
        archive_stage_reports = categories.get("ARCHIVE_STAGE_REPORT", [])
        archive_validation_reports = categories.get("ARCHIVE_VALIDATION_REPORT", [])
        safe_delete = categories.get("SAFE_DELETE", [])
        keep = categories.get("KEEP", [])
        review = categories.get("REVIEW", [])

        report.update({
            "status": "PASS",
            "head": head,
            "origin_main": origin,
            "tag": BASE_TAG,
            "package_version": BASE_VERSION,
            "runtime_json": "UNCHANGED",
            "tracked": "CLEAN",
            "staging": "EMPTY",
            "untracked_total": len(rows),
            "archive_stage_scripts": archive_stage_scripts,
            "archive_stage_reports": archive_stage_reports,
            "archive_validation_reports": archive_validation_reports,
            "safe_delete": safe_delete,
            "keep": keep,
            "review": review,
            "proposed_archive_root": "archive/completed_release_work/electron-v0.5.18/",
            "proposed_report_archive_root": "reports/archive/electron-v0.5.18/",
            "next": (
                "Stage71B Actual에서는 ARCHIVE_*만 이동, SAFE_DELETE만 삭제, "
                "KEEP/REVIEW는 건드리지 않음"
            ),
            "mutated": False,
        })

        REPORT_JSON.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        lines = [
            "[PASS] Stage71A R1 / 0.5.18 배포 후 Workspace 정리 감사",
            f"untracked_total={len(rows)}",
            f"archive_stage_scripts={len(archive_stage_scripts)}",
            f"archive_stage_reports={len(archive_stage_reports)}",
            f"archive_validation_reports={len(archive_validation_reports)}",
            f"safe_delete={len(safe_delete)}",
            f"keep={len(keep)}",
            f"review={len(review)}",
            "tracked=CLEAN",
            "staging=EMPTY",
            "runtime_json=UNCHANGED",
            "mutated=NO",
            "",
            "[ARCHIVE_STAGE_SCRIPT]",
            *archive_stage_scripts,
            "",
            "[ARCHIVE_STAGE_REPORT]",
            *archive_stage_reports,
            "",
            "[ARCHIVE_VALIDATION_REPORT]",
            *archive_validation_reports,
            "",
            "[SAFE_DELETE]",
            *safe_delete,
            "",
            "[REVIEW]",
            *review,
            "",
            "[KEEP_COUNT]",
            str(len(keep)),
            "",
            "readiness=READY_FOR_71B_CLEANUP_ACTUAL_REVIEW",
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
            "[FAIL] Stage71A Workspace 정리 감사 — 파일 변경 없음",
            f"{type(exc).__name__}: {exc}",
            "mutated=NO",
            f"report={REPORT_TXT.relative_to(ROOT)}",
        ]
        REPORT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("\n".join(lines))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
