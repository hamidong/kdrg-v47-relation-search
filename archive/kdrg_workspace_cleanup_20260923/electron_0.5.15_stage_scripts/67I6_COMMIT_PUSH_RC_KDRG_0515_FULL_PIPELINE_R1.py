#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KDRG V4.7 Electron Stage67I6
0.5.15 Full Pipeline Fix Commit + Push + RC R1

Gate:
  Stage67I5 Actual Apply R1 PASS
  readiness=READY_FOR_0515_FIX_COMMIT_PUSH_RC

This stage:
1) verifies the exact four validated Actual files and SHAs,
2) stages exactly those four files,
3) commits on top of the current pushed 0.5.15 fix commit,
4) pushes main without force,
5) dispatches build-electron-windows.yml for the new commit,
6) waits for the exact workflow_dispatch run,
7) verifies RC completion/success,
8) on RC failure, prints a compact failure diagnosis automatically.

No tag/release is created here.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
import traceback


ROOT = Path.cwd().resolve()

STAGE67I5_JSON = ROOT / "stage67i5_0515_full_pipeline_actual_r1.json"

REPORT_TXT = ROOT / "stage67i6_0515_full_pipeline_commit_push_rc_r1.txt"
REPORT_JSON = ROOT / "stage67i6_0515_full_pipeline_commit_push_rc_r1.json"

WORKFLOW = "build-electron-windows.yml"
BASE_TAG = "electron-v0.5.14"
BASE_0514_COMMIT = "4b79e02e8a45a8cabc88b63bc373d95cc21b6d9c"
RELEASE_TAG = "electron-v0.5.15"

COMMIT_MESSAGE = "fix: normalize ADRG packaged search pipeline"

TARGETS = [
    ".github/workflows/build-electron-windows.yml",
    "electron/src/search-result-contract.js",
    "electron/tests/validate-packaged-runtime-smoke.js",
    "electron/tests/validate-stage59b-search.js",
]


class StageError(RuntimeError):
    pass


def require(value, message):
    if not value:
        raise StageError(message)


def run(cmd, check=True, timeout=1800):
    p = subprocess.run(
        [str(x) for x in cmd],
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    result = {
        "cmd": [str(x) for x in cmd],
        "returncode": p.returncode,
        "output": p.stdout,
    }
    if check and p.returncode != 0:
        raise StageError(
            f"command failed ({p.returncode}): {' '.join(result['cmd'])}\n{p.stdout}"
        )
    return result


def git_text(*args):
    return run(["git", *args])["output"].strip()


def git_lines(*args):
    return [
        x for x in run(["git", *args])["output"].splitlines()
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


def sha256_path(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_gate():
    require(STAGE67I5_JSON.is_file(), "Stage67I5 report JSON missing")
    data = json.loads(STAGE67I5_JSON.read_text(encoding="utf-8"))

    require(data.get("status") == "PASS", "Stage67I5 is not PASS")
    require(
        data.get("readiness") == "READY_FOR_0515_FIX_COMMIT_PUSH_RC",
        "Stage67I5 readiness mismatch",
    )

    preflight = data.get("preflight") or {}
    apply = data.get("apply") or {}
    final_guard = data.get("final_guard") or {}

    base_commit = preflight.get("head") or final_guard.get("head")
    require(base_commit, "Stage67I5 base commit missing")
    require(final_guard.get("origin_main") == base_commit, "Stage67I5 origin mismatch")
    require(final_guard.get("staging_empty") is True, "Stage67I5 staging guard mismatch")
    require(final_guard.get("candidate_sha_exact") is True, "Stage67I5 candidate SHA guard missing")

    applied_sha = apply.get("applied_sha256") or {}
    require(sorted(applied_sha) == sorted(TARGETS), "Stage67I5 applied SHA set mismatch")

    return {
        "base_commit": base_commit,
        "candidate_sha256": applied_sha,
    }


def preflight(gate):
    base = gate["base_commit"]

    require(git_text("branch", "--show-current") == "main", "branch != main")
    require(git_text("rev-parse", "HEAD") == base, "HEAD != Stage67I5 base commit")
    require(remote_main_sha() == base, "origin/main != Stage67I5 base commit")
    require(not git_lines("diff", "--cached", "--name-only"), "staging not empty")

    changed = sorted(git_lines("diff", "--name-only"))
    require(changed == sorted(TARGETS),
            "tracked delta is not exact 4 validated files: " + json.dumps(changed))

    for rel in TARGETS:
        require((ROOT / rel).is_file(), f"candidate file missing: {rel}")
        require(
            sha256_path(ROOT / rel) == gate["candidate_sha256"][rel],
            f"candidate SHA mismatch: {rel}",
        )

    diff_check = run(["git", "diff", "--check"], check=False)
    require(diff_check["returncode"] == 0,
            "git diff --check failed:\n" + diff_check["output"])

    require(local_tag_sha(BASE_TAG) == BASE_0514_COMMIT, "0.5.14 local tag mismatch")
    require(remote_tag_sha(BASE_TAG) == BASE_0514_COMMIT, "0.5.14 remote tag mismatch")
    require(not local_tag_sha(RELEASE_TAG), "0.5.15 local tag already exists")
    require(not remote_tag_sha(RELEASE_TAG), "0.5.15 remote tag already exists")
    require(not release_exists(RELEASE_TAG), "0.5.15 GitHub Release already exists")

    return {
        "head": base,
        "origin_main": base,
        "tracked_delta": changed,
        "staging_empty": True,
        "candidate_sha_exact": True,
        "tag_release_absent": True,
    }


def existing_commit_for_candidate(base_commit):
    """
    Safe re-entry support:
    If HEAD already moved one commit beyond base and that commit is exactly our
    message/files, reuse it instead of creating another commit.
    """
    head = git_text("rev-parse", "HEAD")
    if head == base_commit:
        return None

    parent = git_text("rev-parse", f"{head}^")
    subject = git_text("show", "-s", "--format=%s", head)
    files = sorted(git_lines("diff-tree", "--no-commit-id", "--name-only", "-r", head))

    if (
        parent == base_commit
        and subject == COMMIT_MESSAGE
        and files == sorted(TARGETS)
    ):
        return head

    raise StageError(
        f"HEAD moved unexpectedly: head={head} parent={parent} subject={subject}"
    )


def stage_and_commit(gate):
    base = gate["base_commit"]

    existing = existing_commit_for_candidate(base)
    if existing:
        return {
            "commit": existing,
            "reused_existing_commit": True,
        }

    # Exact staging only.
    run(["git", "add", "--", *TARGETS])

    staged = sorted(git_lines("diff", "--cached", "--name-only"))
    require(staged == sorted(TARGETS),
            "staged set is not exact 4 files: " + json.dumps(staged))

    cached_check = run(["git", "diff", "--cached", "--check"], check=False)
    require(cached_check["returncode"] == 0,
            "cached diff --check failed:\n" + cached_check["output"])

    run(["git", "commit", "-m", COMMIT_MESSAGE])
    commit = git_text("rev-parse", "HEAD")

    require(git_text("rev-parse", f"{commit}^") == base, "new commit parent mismatch")
    require(
        git_text("show", "-s", "--format=%s", commit) == COMMIT_MESSAGE,
        "commit subject mismatch",
    )

    committed_files = sorted(
        git_lines("diff-tree", "--no-commit-id", "--name-only", "-r", commit)
    )
    require(committed_files == sorted(TARGETS),
            "commit file set mismatch: " + json.dumps(committed_files))

    require(not git_lines("diff", "--name-only"), "worktree not clean after commit")
    require(not git_lines("diff", "--cached", "--name-only"), "staging not empty after commit")

    return {
        "commit": commit,
        "reused_existing_commit": False,
    }


def push_commit(commit):
    origin_before = remote_main_sha()

    if origin_before == commit:
        return {
            "origin_before": origin_before,
            "origin_after": commit,
            "reused_existing_push": True,
        }

    parent = git_text("rev-parse", f"{commit}^")
    require(origin_before == parent,
            f"origin/main is not commit parent: origin={origin_before} parent={parent}")

    run(["git", "push", "origin", "main"])
    origin_after = remote_main_sha()
    require(origin_after == commit, "origin/main did not reach new commit")

    return {
        "origin_before": origin_before,
        "origin_after": origin_after,
        "reused_existing_push": False,
    }


def list_matching_runs(commit):
    r = run(
        [
            "gh", "run", "list",
            "--workflow", WORKFLOW,
            "--limit", "30",
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


def dispatch_or_reuse(commit):
    existing = list_matching_runs(commit)

    # Never blindly duplicate a failed RC for the same commit.
    failed = [x for x in existing if x.get("status") == "completed"
              and x.get("conclusion") not in (None, "success")]
    if failed:
        newest = sorted(failed, key=lambda x: x.get("createdAt") or "", reverse=True)[0]
        return {
            "run": newest,
            "dispatch_action": "REUSE_EXISTING_FAILED",
        }

    success = [x for x in existing if x.get("status") == "completed"
               and x.get("conclusion") == "success"]
    if success:
        newest = sorted(success, key=lambda x: x.get("createdAt") or "", reverse=True)[0]
        return {
            "run": newest,
            "dispatch_action": "REUSE_EXISTING_SUCCESS",
        }

    active = [x for x in existing if x.get("status") != "completed"]
    if active:
        newest = sorted(active, key=lambda x: x.get("createdAt") or "", reverse=True)[0]
        return {
            "run": newest,
            "dispatch_action": "REUSE_EXISTING_ACTIVE",
        }

    before_ids = {x.get("databaseId") for x in existing}
    run(["gh", "workflow", "run", WORKFLOW, "--ref", "main"])

    deadline = time.time() + 120
    while time.time() < deadline:
        time.sleep(3)
        rows = list_matching_runs(commit)
        new_rows = [x for x in rows if x.get("databaseId") not in before_ids]
        if new_rows:
            newest = sorted(
                new_rows,
                key=lambda x: x.get("createdAt") or "",
                reverse=True,
            )[0]
            return {
                "run": newest,
                "dispatch_action": "DISPATCHED_NEW",
            }

    raise StageError("new exact workflow_dispatch RC run not found within 120s")


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


def failed_step_summary(run_data):
    rows = []
    for job in run_data.get("jobs") or []:
        for step in job.get("steps") or []:
            if step.get("conclusion") == "failure":
                rows.append({
                    "job": job.get("name"),
                    "step_number": step.get("number"),
                    "step_name": step.get("name"),
                    "conclusion": step.get("conclusion"),
                })
    return rows


def compact_failed_log(run_id):
    r = run(
        ["gh", "run", "view", str(run_id), "--log-failed"],
        check=False,
        timeout=900,
    )
    text = r["output"] or ""
    lines = text.splitlines()

    keywords = [
        "error",
        "failed",
        "failure",
        "timeout",
        "failed_step=",
        "message=",
        "missing_steps=",
        "status=",
        "write-error",
        "process completed with exit code",
    ]

    focused = []
    for line in lines:
        low = line.lower()
        if any(k.lower() in low for k in keywords):
            focused.append(line)

    # Keep only a compact tail. Full log remains in GitHub Actions.
    return focused[-30:]


def wait_and_verify_rc(dispatch, commit):
    run_info = dispatch["run"]
    run_id = run_info.get("databaseId")
    require(run_id, "RC run id missing")

    run_data = refresh_run(run_id)

    require(run_data.get("headSha") == commit, "RC head SHA mismatch")
    require(run_data.get("headBranch") == "main", "RC head branch mismatch")
    require(run_data.get("event") == "workflow_dispatch", "RC event mismatch")

    if run_data.get("status") != "completed":
        watch = run(
            ["gh", "run", "watch", str(run_id), "--exit-status"],
            check=False,
            timeout=3600,
        )
        # Do not trust watch alone; refresh exact final state.
        run_data = refresh_run(run_id)

    require(run_data.get("status") == "completed", "RC did not complete")

    failed_steps = failed_step_summary(run_data)
    error_focus = []

    if run_data.get("conclusion") != "success":
        error_focus = compact_failed_log(run_id)

    return {
        "run": run_data,
        "failed_steps": failed_steps,
        "error_focus": error_focus,
        "success": run_data.get("conclusion") == "success",
    }


def final_guard(commit):
    require(git_text("rev-parse", "HEAD") == commit, "HEAD changed after RC")
    require(remote_main_sha() == commit, "origin/main changed after RC")
    require(not git_lines("diff", "--name-only"), "worktree not clean after RC")
    require(not git_lines("diff", "--cached", "--name-only"), "staging not empty after RC")
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
        "KDRG V4.7 Electron Stage67I6 / 0.5.15 Full Pipeline Fix Commit + Push + RC R1",
        "=" * 104,
        f"status={payload['status']}",
        f"readiness={payload['readiness']}",
        "",
        "[COMMIT]",
        json.dumps(payload.get("commit", {}), ensure_ascii=False, indent=2),
        "",
        "[PUSH]",
        json.dumps(payload.get("push", {}), ensure_ascii=False, indent=2),
        "",
        "[DISPATCH]",
        json.dumps(payload.get("dispatch", {}), ensure_ascii=False, indent=2),
        "",
        "[RC]",
        json.dumps({
            "databaseId": run_data.get("databaseId"),
            "headSha": run_data.get("headSha"),
            "headBranch": run_data.get("headBranch"),
            "event": run_data.get("event"),
            "status": run_data.get("status"),
            "conclusion": run_data.get("conclusion"),
            "url": run_data.get("url"),
            "failed_steps": rc.get("failed_steps"),
            "error_focus": rc.get("error_focus"),
        }, ensure_ascii=False, indent=2),
        "",
        "[FINAL GUARD]",
        json.dumps(payload.get("final_guard", {}), ensure_ascii=False, indent=2),
        "",
    ]

    if payload.get("error"):
        lines += ["[BLOCKER]", payload["error"].splitlines()[0], ""]

    lines += [
        "[NEXT]",
        "- RC success이면 READY_FOR_0515_TAG_RELEASE.",
        "- RC failure이면 같은 commit을 자동 재실행하지 말고 failed_steps/error_focus 기준으로 수정.",
        "- 이 Stage는 tag/release를 생성하지 않음.",
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
        "preflight": {},
        "commit": {},
        "push": {},
        "dispatch": {},
        "rc": {},
        "final_guard": {},
        "error": None,
    }

    try:
        payload["gate"] = load_gate()
        payload["preflight"] = preflight(payload["gate"])

        payload["commit"] = stage_and_commit(payload["gate"])
        commit = payload["commit"]["commit"]

        payload["push"] = push_commit(commit)

        payload["dispatch"] = dispatch_or_reuse(commit)
        payload["rc"] = wait_and_verify_rc(payload["dispatch"], commit)

        payload["final_guard"] = final_guard(commit)

        if payload["rc"]["success"]:
            payload["status"] = "PASS"
            payload["readiness"] = "READY_FOR_0515_TAG_RELEASE"
        else:
            raise StageError(
                "RC conclusion is not success: "
                + str((payload["rc"].get("run") or {}).get("conclusion"))
            )

    except Exception as exc:
        payload["error"] = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"

        # If commit/push already happened, preserve it. No reset/revert/amend.
        commit = (payload.get("commit") or {}).get("commit")
        if commit:
            try:
                payload["final_guard"] = final_guard(commit)
            except Exception:
                pass

    payload["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    write_report(payload)

    if payload["status"] == "PASS":
        run_data = payload["rc"]["run"]
        print("[PASS] Stage67I6 / 0.5.15 Full Pipeline Fix Commit + Push + RC R1")
        print("readiness=READY_FOR_0515_TAG_RELEASE")
        print(f"[PASS] commit={payload['commit']['commit']}")
        print(f"[PASS] origin/main={payload['push']['origin_after']}")
        print(
            f"[PASS] RC run={run_data.get('databaseId')} "
            f"conclusion={run_data.get('conclusion')}"
        )
        print("[PASS] worktree/staging clean / 0.5.15 tag+release absent")
        print("[STOP] no tag/release")
        print(f"report_txt={REPORT_TXT}")
        return 0

    print("[FAIL] Stage67I6 / 0.5.15 Full Pipeline Fix Commit + Push + RC R1")
    print("readiness=NOT_READY_FOR_0515_TAG_RELEASE")

    commit = (payload.get("commit") or {}).get("commit")
    if commit:
        print(f"[PRESERVED] commit={commit}")

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

    if payload.get("error"):
        print("[BLOCKER] " + payload["error"].splitlines()[0])

    print("[STOP] no automatic rerun / no tag/release")
    print(f"report_txt={REPORT_TXT}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
