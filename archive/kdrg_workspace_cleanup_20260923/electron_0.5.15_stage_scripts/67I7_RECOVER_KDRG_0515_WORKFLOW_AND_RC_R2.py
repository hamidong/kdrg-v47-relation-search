#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KDRG V4.7 Electron Stage67I7
0.5.15 Workflow Exact Restore + Full Validation + RC R2

핵심 원칙
---------
R1은 제품이 아니라 검증 스크립트의 diff 해석 가정 때문에 safe-fail 했다.
R2는 workflow를 더 이상 부분 편집하지 않는다.

1) f1025ca...의 부모 commit workflow를 byte-for-byte 복원
2) 그 부모 commit이 GitHub에서 실제 workflow_dispatch 실행 이력이 있었는지 확인
3) Shadow 전체검증
4) Actual 전체검증
5) workflow 1개만 commit/push
6) 원격 workflow bytes가 부모와 완전히 동일한지 확인
7) GitHub metadata propagation을 기다린 뒤 RC 1회 시작
8) RC 실패 시 외부 gh 로그에서 failed step/error focus 자동 추출

재실행 안전성
-------------
- recovery commit이 이미 있으면 재사용
- 이미 push됐으면 재사용
- 해당 commit RC가 이미 있으면 재사용
- 실패한 RC가 있으면 자동 재실행하지 않음
- commit 전 실패면 workflow를 정확히 원복
- commit 이후 실패면 reset/revert/amend 없이 이력 보존

이 단계는 tag/release를 만들지 않는다.
"""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import traceback


ROOT = Path.cwd().resolve()
ELECTRON = ROOT / "electron"

DIAG_JSON = ROOT / "stage67i6d_0515_workflow_dispatch_failure_r1.json"
ACTUAL_JSON = ROOT / "stage67i5_0515_full_pipeline_actual_r1.json"

REPORT_TXT = ROOT / "stage67i7_0515_workflow_recovery_rc_r2.txt"
REPORT_JSON = ROOT / "stage67i7_0515_workflow_recovery_rc_r2.json"

WORKFLOW_REL = ".github/workflows/build-electron-windows.yml"
WORKFLOW_NAME = "build-electron-windows.yml"

BROKEN_COMMIT = "f1025ca771a5efb36f843566ab6609f8f02c37d1"
RECOVERY_MESSAGE = "fix: restore dispatchable workflow"

BASE_TAG = "electron-v0.5.14"
BASE_0514_COMMIT = "4b79e02e8a45a8cabc88b63bc373d95cc21b6d9c"
RELEASE_TAG = "electron-v0.5.15"
VERSION = "0.5.15"

RUNTIME_REL = "data/kdrg_v47_search_integrated_v3.json"
RUNTIME_SHA = "1a3d50400567ecaad9695b7be8e7c0382131f8652f398e010cf01f4d8dda6c58"

OFFICIAL_REL = "electron/renderer/official-condition-text.js"
OFFICIAL_SHA = "6f8dcef30a2eb54ce4b36d918bd5d7949712979fd0f880f1990ffc43e915581e"

ICON_PNG_REL = "electron/renderer/assets/icon-kdrg-v47.png"
ICON_PNG_SHA = "6ddc9f093a82cf9c5f1cc910fce1a0b101352305c71fbc38ae578e11bf93a79d"

ICON_ICO_REL = "electron/renderer/assets/icon-kdrg-v47.ico"
ICON_ICO_SHA = "2321ec9bd820e50e8da73d6faf63f7b15d3a4ceb02da2ed54f4d9332a66a8c45"

ROOT_VALIDATORS = [
    "50B_validate_kdrg_electron_search_service.py",
    "50C_validate_kdrg_electron_renderer_ui.py",
    "50D_validate_kdrg_electron_windows_packaging.py",
]

BROKEN_COMMIT_FILES = [
    WORKFLOW_REL,
    "electron/src/search-result-contract.js",
    "electron/tests/validate-packaged-runtime-smoke.js",
    "electron/tests/validate-stage59b-search.js",
]


class StageError(RuntimeError):
    pass


def require(value, message):
    if not value:
        raise StageError(message)


def run(cmd, cwd=None, check=True, timeout=1800):
    p = subprocess.run(
        [str(x) for x in cmd],
        cwd=str(cwd or ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    result = {
        "cmd": [str(x) for x in cmd],
        "cwd": str(cwd or ROOT),
        "returncode": p.returncode,
        "output": p.stdout,
    }
    if check and p.returncode != 0:
        raise StageError(
            f"command failed ({p.returncode}): {' '.join(result['cmd'])}\n{p.stdout}"
        )
    return result


def run_bytes(cmd, cwd=None, check=True, timeout=600):
    p = subprocess.run(
        [str(x) for x in cmd],
        cwd=str(cwd or ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
    if check and p.returncode != 0:
        err = p.stderr.decode("utf-8", errors="replace")
        raise StageError(
            f"command failed ({p.returncode}): {' '.join(str(x) for x in cmd)}\n{err}"
        )
    return p.returncode, p.stdout, p.stderr


def git_text(*args, cwd=None):
    return run(["git", *args], cwd=cwd)["output"].strip()


def git_lines(*args, cwd=None):
    return [
        x for x in run(["git", *args], cwd=cwd)["output"].splitlines()
        if x
    ]


def remote_main_sha():
    out = run(["git", "ls-remote", "origin", "refs/heads/main"])["output"].strip()
    require(out, "origin/main unavailable")
    return out.split()[0]


def local_tag_sha(tag):
    r = run(
        ["git", "rev-parse", "-q", "--verify", f"refs/tags/{tag}"],
        check=False,
    )
    return r["output"].strip() if r["returncode"] == 0 else ""


def remote_tag_sha(tag):
    out = run(
        ["git", "ls-remote", "--tags", "origin", f"refs/tags/{tag}"]
    )["output"].strip()
    return out.split()[0] if out else ""


def release_exists(tag):
    r = run(["gh", "release", "view", tag, "--json", "tagName"], check=False)
    return r["returncode"] == 0


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_path(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def repo_name():
    data = json.loads(
        run(["gh", "repo", "view", "--json", "nameWithOwner"])["output"]
    )
    name = data.get("nameWithOwner")
    require(name, "repository nameWithOwner missing")
    return name


def load_gates():
    require(DIAG_JSON.is_file(), "Stage67I6D diagnosis JSON missing")
    require(ACTUAL_JSON.is_file(), "Stage67I5 Actual JSON missing")

    diag = json.loads(DIAG_JSON.read_text(encoding="utf-8"))
    actual = json.loads(ACTUAL_JSON.read_text(encoding="utf-8"))

    require(diag.get("status") == "PASS", "Stage67I6D is not PASS")
    require(diag.get("commit") == BROKEN_COMMIT, "Stage67I6D commit mismatch")
    require(
        (diag.get("classification") or {}).get("root_classification")
        == "LIKELY_INVALID_WORKFLOW_YAML_FROM_DIAGNOSTIC_MARKER_INDENTATION",
        "Stage67I6D classification mismatch",
    )

    source = diag.get("source_audit") or {}
    require(source.get("marker_indent_unsafe") is True,
            "unsafe workflow indentation was not confirmed")
    require(source.get("local_workflow_dispatch_present") is True,
            "current workflow_dispatch text missing")
    require(source.get("parent_workflow_dispatch_present") is True,
            "parent workflow_dispatch text missing")
    require((diag.get("runs") or {}).get("matching") == [],
            "RC already exists for broken commit")

    diagnosed_error = "\n".join(diag.get("gh_error_compact") or [])
    require("HTTP 422" in diagnosed_error, "HTTP 422 diagnosis missing")
    require("workflow_dispatch" in diagnosed_error,
            "workflow_dispatch diagnosis missing")

    require(actual.get("status") == "PASS", "Stage67I5 Actual is not PASS")
    require(
        actual.get("readiness") == "READY_FOR_0515_FIX_COMMIT_PUSH_RC",
        "Stage67I5 readiness mismatch",
    )

    return {
        "broken_commit": BROKEN_COMMIT,
        "diagnosis": "workflow YAML block indentation",
    }


def immutable_guard():
    require(local_tag_sha(BASE_TAG) == BASE_0514_COMMIT,
            "0.5.14 local tag mismatch")
    require(remote_tag_sha(BASE_TAG) == BASE_0514_COMMIT,
            "0.5.14 remote tag mismatch")
    require(not local_tag_sha(RELEASE_TAG), "0.5.15 local tag exists")
    require(not remote_tag_sha(RELEASE_TAG), "0.5.15 remote tag exists")
    require(not release_exists(RELEASE_TAG), "0.5.15 Release exists")

    require(sha256_path(ROOT / RUNTIME_REL) == RUNTIME_SHA, "runtime SHA mismatch")
    require(sha256_path(ROOT / OFFICIAL_REL) == OFFICIAL_SHA,
            "official-condition SHA mismatch")
    require(sha256_path(ROOT / ICON_PNG_REL) == ICON_PNG_SHA,
            "PNG icon SHA mismatch")
    require(sha256_path(ROOT / ICON_ICO_REL) == ICON_ICO_SHA,
            "ICO icon SHA mismatch")


def recovery_commit_info(head):
    parent = git_text("rev-parse", f"{head}^")
    subject = git_text("show", "-s", "--format=%s", head)
    files = sorted(
        git_lines("diff-tree", "--no-commit-id", "--name-only", "-r", head)
    )

    if (
        parent == BROKEN_COMMIT
        and subject == RECOVERY_MESSAGE
        and files == [WORKFLOW_REL]
    ):
        return {
            "commit": head,
            "parent": parent,
            "subject": subject,
            "files": files,
        }
    return None


def detect_state():
    immutable_guard()

    require(git_text("branch", "--show-current") == "main", "branch != main")
    require(not git_lines("diff", "--name-only"), "tracked worktree not clean")
    require(not git_lines("diff", "--cached", "--name-only"), "staging not empty")

    broken_files = sorted(
        git_lines(
            "diff-tree",
            "--no-commit-id",
            "--name-only",
            "-r",
            BROKEN_COMMIT,
        )
    )
    require(
        broken_files == sorted(BROKEN_COMMIT_FILES),
        "broken commit file set mismatch: " + json.dumps(broken_files),
    )

    head = git_text("rev-parse", "HEAD")
    origin = remote_main_sha()

    if head == BROKEN_COMMIT:
        require(origin == BROKEN_COMMIT,
                "HEAD is broken commit but origin/main differs")
        return {
            "mode": "BROKEN_BASE",
            "head": head,
            "origin_main": origin,
        }

    recovery = recovery_commit_info(head)
    require(recovery is not None, f"unexpected HEAD state: {head}")
    require(origin in (BROKEN_COMMIT, head),
            f"unexpected origin/main for recovery state: {origin}")

    return {
        "mode": "RECOVERY_COMMIT",
        "head": head,
        "origin_main": origin,
        "recovery": recovery,
    }


def parent_commit():
    return git_text("rev-parse", f"{BROKEN_COMMIT}^")


def parent_workflow_bytes(parent):
    _, out, _ = run_bytes(
        ["git", "show", f"{parent}:{WORKFLOW_REL}"],
        check=True,
    )
    require(out, "parent workflow is empty")
    return out


def workflow_contract(data):
    text = data.decode("utf-8")
    require("workflow_dispatch:" in text,
            "known parent workflow lacks workflow_dispatch")
    require("packaged 핵심검증 판정" in text,
            "known parent workflow lacks packaged verification step")
    require('Write-Error "packaged 핵심검증 실패"' in text,
            "known parent workflow hard-failure gate missing")
    require("Stage67I4B: emit diagnostics before terminating" not in text,
            "unsafe marker exists in known parent workflow")
    return {
        "workflow_dispatch_present": True,
        "packaged_verification_present": True,
        "unsafe_marker_absent": True,
    }


def historical_dispatch_proof(parent):
    r = run(
        [
            "gh", "run", "list",
            "--workflow", WORKFLOW_NAME,
            "--limit", "50",
            "--json",
            "databaseId,headSha,headBranch,event,status,conclusion,createdAt,url",
        ],
        check=False,
        timeout=600,
    )
    require(r["returncode"] == 0, "gh run list failed:\n" + r["output"])

    rows = json.loads(r["output"] or "[]")
    matches = [
        row for row in rows
        if row.get("headSha") == parent
        and row.get("event") == "workflow_dispatch"
    ]
    require(matches,
            "known parent commit has no historical workflow_dispatch run")

    newest = sorted(
        matches,
        key=lambda x: x.get("createdAt") or "",
        reverse=True,
    )[0]

    return {
        "parent_commit": parent,
        "proof": "KNOWN_DISPATCHABLE_ON_GITHUB",
        "historical_run": newest,
    }


def create_shadow(commit):
    shadow = Path(tempfile.mkdtemp(prefix="kdrg_stage67i7_r2_shadow_"))
    shutil.rmtree(shadow)

    r = run(
        ["git", "worktree", "add", "--detach", str(shadow), commit],
        check=False,
        timeout=600,
    )
    require(r["returncode"] == 0, "git worktree add failed:\n" + r["output"])
    return shadow


def validate_repo(tree):
    commands = []

    def check(cmd, cwd=None, timeout=1800):
        r = run(cmd, cwd=cwd or tree, check=False, timeout=timeout)
        commands.append({
            "cmd": " ".join(str(x) for x in cmd),
            "returncode": r["returncode"],
            "tail": "\n".join(r["output"].splitlines()[-6:]),
        })
        require(
            r["returncode"] == 0,
            f"validation failed: {' '.join(cmd)}\n{r['output']}",
        )

    check(["node", "tests/validate-stage59b-search.js"], cwd=tree / "electron")
    check(["node", "tests/validate-packaged-runtime-smoke.js"], cwd=tree / "electron")
    check(["node", "tests/validate-stage60c-packaged-relation-smoke.js"],
          cwd=tree / "electron")
    check(["node", "tests/validate-stage59b-ui.js"], cwd=tree / "electron")
    check(["node", "tests/validate-stage59b-smoke.js"], cwd=tree / "electron")
    check(["npm", "run", "check"], cwd=tree / "electron", timeout=1800)

    for rel in ROOT_VALIDATORS:
        check(["python", rel], cwd=tree, timeout=1800)

    check(
        ["node", "tests/validate-release-version.js", VERSION],
        cwd=tree / "electron",
        timeout=600,
    )

    require(sha256_path(tree / RUNTIME_REL) == RUNTIME_SHA,
            "runtime changed during validation")
    require(sha256_path(tree / OFFICIAL_REL) == OFFICIAL_SHA,
            "official-condition changed during validation")
    require(sha256_path(tree / ICON_PNG_REL) == ICON_PNG_SHA,
            "PNG icon changed during validation")
    require(sha256_path(tree / ICON_ICO_REL) == ICON_ICO_SHA,
            "ICO icon changed during validation")

    return {
        "npm_stage_validators": "PASS",
        "root_50b_50c_50d": "PASS",
        "release_version": "PASS",
        "immutable_assets": "PASS",
        "commands": commands,
    }


def shadow_restore(parent_bytes):
    shadow = create_shadow(BROKEN_COMMIT)
    try:
        target = shadow / WORKFLOW_REL
        target.write_bytes(parent_bytes)

        require(target.read_bytes() == parent_bytes,
                "Shadow workflow != known parent bytes")

        changed = sorted(git_lines("diff", "--name-only", cwd=shadow))
        require(changed == [WORKFLOW_REL],
                "Shadow delta is not exact workflow file")

        diff_check = run(["git", "diff", "--check"], cwd=shadow, check=False)
        require(diff_check["returncode"] == 0,
                "Shadow git diff --check failed:\n" + diff_check["output"])

        result = {
            "shadow_root": str(shadow),
            "candidate_sha256": sha256_bytes(parent_bytes),
            "byte_identical_to_known_parent": True,
            "tracked_delta": changed,
            "git_diff_check": "PASS",
            "workflow_contract": workflow_contract(parent_bytes),
            "validation": validate_repo(shadow),
        }
        return result, shadow

    except Exception:
        run(
            ["git", "worktree", "remove", "--force", str(shadow)],
            check=False,
            timeout=600,
        )
        raise


def rollback_actual(before_bytes):
    target = ROOT / WORKFLOW_REL
    target.write_bytes(before_bytes)
    run(["git", "reset", "--", WORKFLOW_REL], check=False)

    clean = not git_lines("diff", "--name-only")
    staged_empty = not git_lines("diff", "--cached", "--name-only")
    require(clean and staged_empty, "Actual rollback did not restore clean state")

    return {
        "performed": True,
        "worktree_clean": clean,
        "staging_empty": staged_empty,
    }


def actual_restore(parent_bytes):
    target = ROOT / WORKFLOW_REL
    before = target.read_bytes()

    try:
        target.write_bytes(parent_bytes)

        require(target.read_bytes() == parent_bytes,
                "Actual workflow != known parent bytes")

        changed = sorted(git_lines("diff", "--name-only"))
        require(changed == [WORKFLOW_REL],
                "Actual delta is not exact workflow file")

        diff_check = run(["git", "diff", "--check"], check=False)
        require(diff_check["returncode"] == 0,
                "Actual git diff --check failed:\n" + diff_check["output"])

        result = {
            "before_sha256": sha256_bytes(before),
            "after_sha256": sha256_path(target),
            "byte_identical_to_known_parent": True,
            "tracked_delta": changed,
            "git_diff_check": "PASS",
            "workflow_contract": workflow_contract(parent_bytes),
            "validation": validate_repo(ROOT),
        }

        require(not git_lines("diff", "--cached", "--name-only"),
                "staging not empty before commit")

        return result, before

    except Exception:
        rollback_actual(before)
        raise


def commit_recovery(candidate_sha):
    require(git_text("rev-parse", "HEAD") == BROKEN_COMMIT,
            "pre-commit HEAD changed")
    require(remote_main_sha() == BROKEN_COMMIT,
            "pre-commit origin/main changed")
    require(sorted(git_lines("diff", "--name-only")) == [WORKFLOW_REL],
            "pre-commit delta is not exact workflow")
    require(sha256_path(ROOT / WORKFLOW_REL) == candidate_sha,
            "pre-commit workflow SHA mismatch")

    run(["git", "add", "--", WORKFLOW_REL])

    staged = sorted(git_lines("diff", "--cached", "--name-only"))
    require(staged == [WORKFLOW_REL], "staged set is not exact workflow")

    cached_check = run(["git", "diff", "--cached", "--check"], check=False)
    require(cached_check["returncode"] == 0,
            "cached diff --check failed:\n" + cached_check["output"])

    run(["git", "commit", "-m", RECOVERY_MESSAGE])

    commit = git_text("rev-parse", "HEAD")
    info = recovery_commit_info(commit)
    require(info is not None, "recovery commit contract mismatch")
    require(not git_lines("diff", "--name-only"),
            "worktree not clean after recovery commit")
    require(not git_lines("diff", "--cached", "--name-only"),
            "staging not empty after recovery commit")

    return info


def push_or_reuse(commit):
    origin = remote_main_sha()

    if origin == commit:
        return {
            "origin_before": origin,
            "origin_after": origin,
            "push_action": "REUSED_EXISTING_PUSH",
        }

    require(origin == BROKEN_COMMIT,
            f"origin/main unexpected before push: {origin}")

    run(["git", "push", "origin", "main"])

    after = remote_main_sha()
    require(after == commit, "origin/main did not reach recovery commit")

    return {
        "origin_before": origin,
        "origin_after": after,
        "push_action": "PUSHED",
    }


def remote_workflow_bytes(owner_repo, commit):
    r = run(
        [
            "gh", "api",
            f"repos/{owner_repo}/contents/{WORKFLOW_REL}?ref={commit}",
        ],
        check=False,
        timeout=600,
    )
    require(r["returncode"] == 0,
            "remote workflow contents API failed:\n" + r["output"])

    data = json.loads(r["output"])
    content = str(data.get("content") or "").replace("\n", "")
    require(content, "remote workflow content missing")
    return base64.b64decode(content)


def get_workflow_registration(owner_repo):
    r = run(
        ["gh", "api", f"repos/{owner_repo}/actions/workflows"],
        check=False,
        timeout=600,
    )
    require(r["returncode"] == 0,
            "workflow registration API failed:\n" + r["output"])

    data = json.loads(r["output"])
    for wf in data.get("workflows") or []:
        path = str(wf.get("path") or "")
        if path.endswith("/" + WORKFLOW_NAME):
            return {
                "id": wf.get("id"),
                "name": wf.get("name"),
                "path": wf.get("path"),
                "state": wf.get("state"),
            }
    return None


def remote_metadata_gate(commit, expected_bytes, timeout=90):
    owner_repo = repo_name()
    deadline = time.time() + timeout
    last = None

    while time.time() < deadline:
        remote_bytes = remote_workflow_bytes(owner_repo, commit)
        registration = get_workflow_registration(owner_repo)

        last = {
            "owner_repo": owner_repo,
            "remote_byte_exact": remote_bytes == expected_bytes,
            "remote_sha256": sha256_bytes(remote_bytes),
            "workflow": registration,
        }

        if (
            last["remote_byte_exact"]
            and registration
            and registration.get("state") == "active"
        ):
            return last

        time.sleep(5)

    raise StageError(
        "remote workflow metadata did not stabilize: "
        + json.dumps(last, ensure_ascii=False)
    )


def list_dispatch_runs(commit):
    r = run(
        [
            "gh", "run", "list",
            "--workflow", WORKFLOW_NAME,
            "--limit", "40",
            "--json",
            "databaseId,headSha,headBranch,event,status,conclusion,createdAt,url",
        ],
        check=False,
        timeout=600,
    )
    require(r["returncode"] == 0, "gh run list failed:\n" + r["output"])

    rows = json.loads(r["output"] or "[]")
    return [
        row for row in rows
        if row.get("headSha") == commit
        and row.get("headBranch") == "main"
        and row.get("event") == "workflow_dispatch"
    ]


def dispatch_or_reuse(commit, propagation_timeout=90):
    existing = list_dispatch_runs(commit)
    if existing:
        newest = sorted(
            existing,
            key=lambda x: x.get("createdAt") or "",
            reverse=True,
        )[0]
        return {
            "action": "REUSED_EXISTING_RC",
            "run": newest,
            "dispatch_attempts": 0,
        }

    deadline = time.time() + propagation_timeout
    attempts = 0
    last_error = ""

    while time.time() < deadline:
        # A run may appear between attempts.
        existing = list_dispatch_runs(commit)
        if existing:
            newest = sorted(
                existing,
                key=lambda x: x.get("createdAt") or "",
                reverse=True,
            )[0]
            return {
                "action": "REUSED_RC_APPEARED",
                "run": newest,
                "dispatch_attempts": attempts,
            }

        attempts += 1
        r = run(
            ["gh", "workflow", "run", WORKFLOW_NAME, "--ref", "main"],
            check=False,
            timeout=600,
        )

        if r["returncode"] == 0:
            break

        last_error = r["output"].strip()
        low = last_error.lower()

        # This 422 produces no run; it can occur while Actions metadata catches up.
        if (
            "422" in low
            and "workflow_dispatch" in low
            and "does not have" in low
        ):
            time.sleep(5)
            continue

        raise StageError("workflow dispatch failed:\n" + last_error)

    else:
        raise StageError(
            "workflow dispatch metadata propagation timeout; "
            f"attempts={attempts}; last_error={last_error}"
        )

    deadline2 = time.time() + 120
    while time.time() < deadline2:
        time.sleep(3)
        rows = list_dispatch_runs(commit)
        if rows:
            newest = sorted(
                rows,
                key=lambda x: x.get("createdAt") or "",
                reverse=True,
            )[0]
            return {
                "action": "DISPATCHED_NEW_RC",
                "run": newest,
                "dispatch_attempts": attempts,
            }

    raise StageError("dispatch succeeded but exact RC run was not found")


def refresh_run(run_id):
    r = run(
        [
            "gh", "run", "view", str(run_id),
            "--json",
            "databaseId,headSha,headBranch,event,status,conclusion,url,jobs",
        ],
        check=False,
        timeout=600,
    )
    require(r["returncode"] == 0, "gh run view failed:\n" + r["output"])
    return json.loads(r["output"])


def failure_context(run_id, run_data):
    failed_steps = []
    for job in run_data.get("jobs") or []:
        for step in job.get("steps") or []:
            if step.get("conclusion") == "failure":
                failed_steps.append({
                    "job": job.get("name"),
                    "step_number": step.get("number"),
                    "step_name": step.get("name"),
                })

    log = run(
        ["gh", "run", "view", str(run_id), "--log-failed"],
        check=False,
        timeout=900,
    )["output"]

    keywords = [
        "error",
        "failed",
        "failure",
        "timeout",
        "status=",
        "failed_step=",
        "missing_steps=",
        "message=",
        "write-error",
        "process completed with exit code",
    ]

    focus = [
        line
        for line in log.splitlines()
        if any(k.lower() in line.lower() for k in keywords)
    ]

    return {
        "failed_steps": failed_steps,
        "error_focus": focus[-30:],
    }


def wait_rc(run_row, commit):
    run_id = run_row.get("databaseId")
    require(run_id, "RC run id missing")

    data = refresh_run(run_id)
    require(data.get("headSha") == commit, "RC head SHA mismatch")
    require(data.get("headBranch") == "main", "RC branch mismatch")
    require(data.get("event") == "workflow_dispatch", "RC event mismatch")

    if data.get("status") != "completed":
        run(
            ["gh", "run", "watch", str(run_id), "--exit-status"],
            check=False,
            timeout=3600,
        )
        data = refresh_run(run_id)

    require(data.get("status") == "completed", "RC did not complete")

    ctx = {
        "failed_steps": [],
        "error_focus": [],
    }
    if data.get("conclusion") != "success":
        ctx = failure_context(run_id, data)

    return {
        "run": data,
        "success": data.get("conclusion") == "success",
        **ctx,
    }


def final_guard(commit):
    require(git_text("rev-parse", "HEAD") == commit, "HEAD changed after RC")
    require(remote_main_sha() == commit, "origin/main changed after RC")
    require(not git_lines("diff", "--name-only"), "worktree not clean after RC")
    require(not git_lines("diff", "--cached", "--name-only"),
            "staging not empty after RC")
    require(not local_tag_sha(RELEASE_TAG), "0.5.15 local tag appeared")
    require(not remote_tag_sha(RELEASE_TAG), "0.5.15 remote tag appeared")
    require(not release_exists(RELEASE_TAG), "0.5.15 Release appeared")

    return {
        "head": commit,
        "origin_main": commit,
        "worktree_clean": True,
        "staging_empty": True,
        "release_tag_absent": True,
        "release_absent": True,
    }


def write_report(payload):
    REPORT_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    rc = payload.get("rc") or {}
    run_data = rc.get("run") or {}

    lines = [
        "KDRG V4.7 Electron Stage67I7 / 0.5.15 Exact Workflow Restore + RC R2",
        "=" * 100,
        f"status={payload['status']}",
        f"readiness={payload['readiness']}",
        "",
        "[STATE]",
        json.dumps(payload.get("state", {}), ensure_ascii=False, indent=2),
        "",
        "[KNOWN DISPATCHABLE PARENT]",
        json.dumps(payload.get("parent_proof", {}), ensure_ascii=False, indent=2),
        "",
        "[SHADOW]",
        json.dumps({
            "candidate_sha256":
                (payload.get("shadow") or {}).get("candidate_sha256"),
            "byte_identical_to_known_parent":
                (payload.get("shadow") or {}).get("byte_identical_to_known_parent"),
            "git_diff_check":
                (payload.get("shadow") or {}).get("git_diff_check"),
            "validation":
                (payload.get("shadow") or {}).get("validation"),
        }, ensure_ascii=False, indent=2),
        "",
        "[ACTUAL]",
        json.dumps(payload.get("actual", {}), ensure_ascii=False, indent=2),
        "",
        "[COMMIT/PUSH]",
        json.dumps(payload.get("commit_push", {}), ensure_ascii=False, indent=2),
        "",
        "[REMOTE METADATA]",
        json.dumps(payload.get("remote_metadata", {}),
                   ensure_ascii=False, indent=2),
        "",
        "[DISPATCH]",
        json.dumps(payload.get("dispatch", {}), ensure_ascii=False, indent=2),
        "",
        "[RC]",
        json.dumps({
            "databaseId": run_data.get("databaseId"),
            "headSha": run_data.get("headSha"),
            "status": run_data.get("status"),
            "conclusion": run_data.get("conclusion"),
            "url": run_data.get("url"),
            "failed_steps": rc.get("failed_steps"),
            "error_focus": rc.get("error_focus"),
        }, ensure_ascii=False, indent=2),
        "",
        "[FINAL GUARD]",
        json.dumps(payload.get("final_guard", {}),
                   ensure_ascii=False, indent=2),
        "",
        "[ROLLBACK]",
        json.dumps(payload.get("rollback", {}),
                   ensure_ascii=False, indent=2),
        "",
    ]

    if payload.get("error"):
        lines += ["[BLOCKER]", payload["error"].splitlines()[0], ""]

    lines += [
        "[NEXT]",
        "- RC success이면 READY_FOR_0515_TAG_RELEASE.",
        "- RC failure이면 같은 RC 자동 재실행 금지.",
        "- tag/release는 이 단계에서 생성하지 않음.",
        "",
        f"report_json={REPORT_JSON}",
    ]

    REPORT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    payload = {
        "status": "FAIL",
        "readiness": "NOT_READY_FOR_0515_TAG_RELEASE",
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "gate": {},
        "state": {},
        "parent_proof": {},
        "shadow": {},
        "actual": {},
        "commit_push": {},
        "remote_metadata": {},
        "dispatch": {},
        "rc": {},
        "final_guard": {},
        "rollback": {"performed": False},
        "error": None,
    }

    shadow = None
    actual_before = None
    actual_applied = False

    try:
        payload["gate"] = load_gates()
        payload["state"] = detect_state()

        parent = parent_commit()
        parent_bytes = parent_workflow_bytes(parent)
        candidate_sha = sha256_bytes(parent_bytes)

        payload["parent_proof"] = historical_dispatch_proof(parent)
        payload["parent_proof"]["candidate_sha256"] = candidate_sha
        payload["parent_proof"]["workflow_contract"] = workflow_contract(
            parent_bytes
        )

        if payload["state"]["mode"] == "BROKEN_BASE":
            payload["shadow"], shadow = shadow_restore(parent_bytes)
            require(
                payload["shadow"]["candidate_sha256"] == candidate_sha,
                "Shadow candidate SHA mismatch",
            )

            payload["actual"], actual_before = actual_restore(parent_bytes)
            actual_applied = True

            run(
                ["git", "worktree", "remove", "--force", str(shadow)],
                check=False,
                timeout=600,
            )
            shadow = None

            recovery = commit_recovery(candidate_sha)
            recovery_commit = recovery["commit"]

            payload["commit_push"] = {
                **recovery,
                **push_or_reuse(recovery_commit),
            }

        else:
            recovery = payload["state"]["recovery"]
            recovery_commit = recovery["commit"]

            require(
                sha256_path(ROOT / WORKFLOW_REL) == candidate_sha,
                "existing recovery workflow != known parent bytes",
            )
            workflow_contract((ROOT / WORKFLOW_REL).read_bytes())

            payload["actual"] = {
                "reentry_validation": validate_repo(ROOT),
                "byte_identical_to_known_parent": True,
                "after_sha256": candidate_sha,
            }

            payload["commit_push"] = {
                **recovery,
                **push_or_reuse(recovery_commit),
            }

        # From this point a recovery commit exists. Never rewrite history.
        actual_applied = False

        payload["remote_metadata"] = remote_metadata_gate(
            recovery_commit,
            parent_bytes,
            timeout=90,
        )

        payload["dispatch"] = dispatch_or_reuse(
            recovery_commit,
            propagation_timeout=90,
        )

        payload["rc"] = wait_rc(
            payload["dispatch"]["run"],
            recovery_commit,
        )

        payload["final_guard"] = final_guard(recovery_commit)

        if not payload["rc"]["success"]:
            raise StageError(
                "RC conclusion is not success: "
                + str((payload["rc"].get("run") or {}).get("conclusion"))
            )

        payload["status"] = "PASS"
        payload["readiness"] = "READY_FOR_0515_TAG_RELEASE"

    except Exception as exc:
        payload["error"] = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"

        if shadow is not None:
            run(
                ["git", "worktree", "remove", "--force", str(shadow)],
                check=False,
                timeout=600,
            )

        try:
            current_head = git_text("rev-parse", "HEAD")
            if (
                actual_applied
                and actual_before is not None
                and current_head == BROKEN_COMMIT
            ):
                payload["rollback"] = rollback_actual(actual_before)
        except Exception as rollback_exc:
            payload["rollback"] = {
                "performed": True,
                "error": f"{type(rollback_exc).__name__}: {rollback_exc}",
            }

        # If a recovery commit exists, preserve it. No reset/revert/amend.
        try:
            current_head = git_text("rev-parse", "HEAD")
            info = recovery_commit_info(current_head)
            if info is not None:
                payload["final_guard"] = final_guard(current_head)
        except Exception:
            pass

    payload["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    write_report(payload)

    if payload["status"] == "PASS":
        run_data = payload["rc"]["run"]
        print("[PASS] Stage67I7 / 0.5.15 Exact Workflow Restore + RC R2")
        print("readiness=READY_FOR_0515_TAG_RELEASE")
        print("[PASS] workflow byte-for-byte restored to known-dispatchable parent")
        print("[PASS] historical workflow_dispatch proof")
        print("[PASS] Shadow full validation + Actual full validation")
        print(
            f"[PASS] recovery commit={payload['commit_push']['commit']} "
            f"origin/main={payload['commit_push']['origin_after']}"
        )
        print("[PASS] remote workflow bytes exact / workflow active")
        print(
            f"[PASS] RC run={run_data.get('databaseId')} "
            f"conclusion={run_data.get('conclusion')}"
        )
        print("[PASS] worktree/staging clean / 0.5.15 tag+release absent")
        print("[STOP] no tag/release")
        print(f"report_txt={REPORT_TXT}")
        return 0

    print("[FAIL] Stage67I7 / 0.5.15 Exact Workflow Restore + RC R2")
    print("readiness=NOT_READY_FOR_0515_TAG_RELEASE")

    try:
        current = git_text("rev-parse", "HEAD")
        if recovery_commit_info(current) is not None:
            print(f"[PRESERVED] recovery_commit={current}")
    except Exception:
        pass

    run_data = (payload.get("rc") or {}).get("run") or {}
    if run_data.get("databaseId"):
        print(
            f"[RC] run={run_data.get('databaseId')} "
            f"conclusion={run_data.get('conclusion')}"
        )

    for row in (payload.get("rc") or {}).get("failed_steps") or []:
        print(
            "[FAIL STEP] "
            f"job={row.get('job')} "
            f"step={row.get('step_number')} "
            f"name={row.get('step_name')}"
        )

    focus = (payload.get("rc") or {}).get("error_focus") or []
    if focus:
        print("[ERROR FOCUS]")
        for line in focus[-20:]:
            print(line)

    if payload.get("rollback", {}).get("performed"):
        print(
            "[ROLLBACK] "
            f"worktree_clean={payload['rollback'].get('worktree_clean')} "
            f"staging_empty={payload['rollback'].get('staging_empty')}"
        )

    if payload.get("error"):
        print("[BLOCKER] " + payload["error"].splitlines()[0])

    print("[STOP] no automatic RC rerun / no tag/release")
    print(f"report_txt={REPORT_TXT}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
