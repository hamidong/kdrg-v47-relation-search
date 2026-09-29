#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KDRG V4.7 Electron Stage67I6D
0.5.15 Workflow Dispatch Failure Diagnosis R1

READ-ONLY.

Stage67I6 already committed and pushed the validated four-file repair, but
`gh workflow run build-electron-windows.yml --ref main` itself returned exit 1.
Therefore no new RC was started.

This diagnosis checks:
- exact full gh CLI error stored by Stage67I6,
- HEAD/origin and exact commit preservation,
- 0.5.15 tag/release absence,
- workflow registration/state through GitHub API,
- workflow_dispatch presence in local and parent workflow,
- whether the Stage67I4B inserted diagnostic marker has unsafe YAML indentation,
- whether the workflow diff touched only the intended packaged failure block,
- whether an RC run was nevertheless created.

No workflow dispatch, rerun, commit, push, reset, tag, or release.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import time
import traceback


ROOT = Path.cwd().resolve()

SOURCE_JSON = ROOT / "stage67i6_0515_full_pipeline_commit_push_rc_r1.json"
WORKFLOW_REL = ".github/workflows/build-electron-windows.yml"
WORKFLOW_NAME = "build-electron-windows.yml"
RELEASE_TAG = "electron-v0.5.15"

REPORT_TXT = ROOT / "stage67i6d_0515_workflow_dispatch_failure_r1.txt"
REPORT_JSON = ROOT / "stage67i6d_0515_workflow_dispatch_failure_r1.json"


class StageError(RuntimeError):
    pass


def require(value, message):
    if not value:
        raise StageError(message)


def run(cmd, check=False, timeout=600):
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
    r = run(["git", *args], check=True)
    return r["output"].strip()


def git_lines(*args):
    r = run(["git", *args], check=True)
    return [x for x in r["output"].splitlines() if x]


def remote_main_sha():
    r = run(["git", "ls-remote", "origin", "refs/heads/main"], check=True)
    require(r["output"].strip(), "origin/main unavailable")
    return r["output"].strip().split()[0]


def tag_exists_remote(tag):
    r = run(["git", "ls-remote", "--tags", "origin", f"refs/tags/{tag}"], check=True)
    return bool(r["output"].strip())


def release_exists(tag):
    r = run(["gh", "release", "view", tag, "--json", "tagName"])
    return r["returncode"] == 0


def load_stage67i6():
    require(SOURCE_JSON.is_file(), "Stage67I6 JSON missing")
    data = json.loads(SOURCE_JSON.read_text(encoding="utf-8"))

    require(data.get("status") == "FAIL", "Stage67I6 is not FAIL")
    require(
        data.get("readiness") == "NOT_READY_FOR_0515_TAG_RELEASE",
        "Stage67I6 readiness mismatch",
    )

    commit = (data.get("commit") or {}).get("commit")
    require(commit, "preserved commit missing from Stage67I6 report")

    error = str(data.get("error") or "")
    require("gh workflow run" in error, "Stage67I6 failure is not workflow dispatch")

    return data, commit, error


def repo_guard(commit):
    require(git_text("rev-parse", "HEAD") == commit, "HEAD != preserved commit")
    require(remote_main_sha() == commit, "origin/main != preserved commit")
    require(not git_lines("diff", "--name-only"), "tracked worktree is not clean")
    require(not git_lines("diff", "--cached", "--name-only"), "staging is not empty")
    require(not tag_exists_remote(RELEASE_TAG), "0.5.15 remote tag exists")
    require(not release_exists(RELEASE_TAG), "0.5.15 GitHub Release exists")

    return {
        "head": commit,
        "origin_main": commit,
        "worktree_clean": True,
        "staging_empty": True,
        "release_tag_absent": True,
        "release_absent": True,
    }


def workflow_registration():
    repo = run(["gh", "repo", "view", "--json", "nameWithOwner"], check=True)
    owner_repo = json.loads(repo["output"]).get("nameWithOwner")
    require(owner_repo, "repository nameWithOwner missing")

    api = run(
        ["gh", "api", f"repos/{owner_repo}/actions/workflows"],
        check=False,
    )

    result = {
        "owner_repo": owner_repo,
        "api_returncode": api["returncode"],
        "registered": False,
        "workflow": None,
        "api_error": None,
    }

    if api["returncode"] != 0:
        result["api_error"] = api["output"].strip()
        return result

    data = json.loads(api["output"])
    wanted_path = "/" + WORKFLOW_REL
    for wf in data.get("workflows") or []:
        path = str(wf.get("path") or "")
        if path == WORKFLOW_REL or path == wanted_path or path.endswith("/" + WORKFLOW_NAME):
            result["registered"] = True
            result["workflow"] = {
                "id": wf.get("id"),
                "name": wf.get("name"),
                "path": wf.get("path"),
                "state": wf.get("state"),
            }
            break

    return result


def leading_spaces(line):
    return len(line) - len(line.lstrip(" "))


def workflow_source_audit(commit):
    current_path = ROOT / WORKFLOW_REL
    require(current_path.is_file(), "workflow file missing")
    current = current_path.read_text(encoding="utf-8")

    parent = git_text("rev-parse", f"{commit}^")
    parent_show = run(
        ["git", "show", f"{parent}:{WORKFLOW_REL}"],
        check=True,
    )
    parent_text = parent_show["output"]

    marker_text = "Stage67I4B: emit diagnostics before terminating"
    error_text = 'Write-Error "packaged 핵심검증 실패"'

    current_lines = current.splitlines()
    marker_rows = [
        (i + 1, leading_spaces(line), line)
        for i, line in enumerate(current_lines)
        if marker_text in line
    ]
    error_rows = [
        (i + 1, leading_spaces(line), line)
        for i, line in enumerate(current_lines)
        if error_text in line
    ]

    require(len(marker_rows) == 1, f"marker count={len(marker_rows)}")
    require(len(error_rows) == 1, f"Write-Error count={len(error_rows)}")

    marker_row = marker_rows[0]
    error_row = error_rows[0]

    # If marker indentation is less than the surrounding PowerShell line,
    # it can terminate the YAML block scalar and invalidate the workflow.
    marker_indent_unsafe = marker_row[1] < error_row[1]

    local_dispatch = bool(re.search(
        r"(?m)^\s*workflow_dispatch\s*:",
        current,
    ))
    parent_dispatch = bool(re.search(
        r"(?m)^\s*workflow_dispatch\s*:",
        parent_text,
    ))

    tabs_in_indentation = []
    for i, line in enumerate(current_lines, 1):
        prefix = line[:len(line) - len(line.lstrip())]
        if "\t" in prefix:
            tabs_in_indentation.append(i)

    diff = run(
        ["git", "diff", f"{parent}..{commit}", "--", WORKFLOW_REL],
        check=True,
    )["output"]

    added = [
        line[1:]
        for line in diff.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]
    removed = [
        line[1:]
        for line in diff.splitlines()
        if line.startswith("-") and not line.startswith("---")
    ]

    return {
        "parent_commit": parent,
        "local_workflow_dispatch_present": local_dispatch,
        "parent_workflow_dispatch_present": parent_dispatch,
        "marker_line": marker_row[0],
        "marker_indent": marker_row[1],
        "write_error_line": error_row[0],
        "write_error_indent": error_row[1],
        "marker_indent_unsafe": marker_indent_unsafe,
        "tab_indentation_lines": tabs_in_indentation[:20],
        "diff_added_count": len(added),
        "diff_removed_count": len(removed),
        "diff_added_sample": added[:20],
        "diff_removed_sample": removed[:20],
    }


def matching_runs(commit):
    r = run(
        [
            "gh", "run", "list",
            "--workflow", WORKFLOW_NAME,
            "--limit", "20",
            "--json",
            "databaseId,headSha,headBranch,event,status,conclusion,createdAt,url",
        ],
        check=False,
    )

    result = {
        "returncode": r["returncode"],
        "error": None,
        "matching": [],
    }

    if r["returncode"] != 0:
        result["error"] = r["output"].strip()
        return result

    rows = json.loads(r["output"] or "[]")
    result["matching"] = [
        row for row in rows
        if row.get("headSha") == commit
        and row.get("event") == "workflow_dispatch"
    ]
    return result


def classify(error, registration, source, runs):
    error_low = error.lower()
    reasons = []

    if source.get("marker_indent_unsafe"):
        reasons.append("WORKFLOW_MARKER_INDENTATION_UNSAFE")

    if not source.get("local_workflow_dispatch_present"):
        reasons.append("LOCAL_WORKFLOW_DISPATCH_MISSING")

    if source.get("parent_workflow_dispatch_present") and not source.get("local_workflow_dispatch_present"):
        reasons.append("WORKFLOW_DISPATCH_REMOVED_IN_FIX_COMMIT")

    if not registration.get("registered"):
        reasons.append("WORKFLOW_NOT_REGISTERED_BY_GITHUB")
    elif (registration.get("workflow") or {}).get("state") != "active":
        reasons.append("WORKFLOW_NOT_ACTIVE")

    if "422" in error_low:
        reasons.append("GH_HTTP_422")
    if "workflow does not have" in error_low and "workflow_dispatch" in error_low:
        reasons.append("GITHUB_SAYS_WORKFLOW_DISPATCH_UNAVAILABLE")
    if "could not resolve" in error_low or "not found" in error_low or "404" in error_low:
        reasons.append("GITHUB_WORKFLOW_LOOKUP_FAILURE")

    if (runs.get("matching") or []):
        reasons.append("RC_RUN_EXISTS_DESPITE_COMMAND_FAILURE")
    else:
        reasons.append("NO_RC_RUN_CREATED")

    if source.get("marker_indent_unsafe"):
        root = (
            "LIKELY_INVALID_WORKFLOW_YAML_FROM_DIAGNOSTIC_MARKER_INDENTATION"
        )
    elif not registration.get("registered"):
        root = "WORKFLOW_REGISTRATION_OR_YAML_VALIDITY_FAILURE"
    elif "GITHUB_SAYS_WORKFLOW_DISPATCH_UNAVAILABLE" in reasons:
        root = "WORKFLOW_DISPATCH_TRIGGER_UNAVAILABLE_ON_GITHUB"
    else:
        root = "GH_WORKFLOW_DISPATCH_FAILURE_NEEDS_EXACT_ERROR_CONTEXT"

    return {
        "root_classification": root,
        "signals": reasons,
        "automatic_rerun_allowed": False,
        "repair_before_next_rc": True,
    }


def compact_error(error):
    lines = [
        line.strip()
        for line in error.splitlines()
        if line.strip()
    ]
    # First line is generic StageError; following lines usually contain gh's
    # actual HTTP/API reason. Keep output small but complete enough.
    return lines[:12]


def write_report(payload):
    REPORT_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    lines = [
        "KDRG V4.7 Electron Stage67I6D / 0.5.15 Workflow Dispatch Failure Diagnosis R1",
        "=" * 110,
        f"status={payload['status']}",
        f"classification={(payload.get('classification') or {}).get('root_classification', '')}",
        "",
        "[GH ERROR]",
    ]

    for line in payload.get("gh_error_compact") or []:
        lines.append(line)

    lines += [
        "",
        "[WORKFLOW]",
        json.dumps({
            "registered": (payload.get("registration") or {}).get("registered"),
            "workflow": (payload.get("registration") or {}).get("workflow"),
            "local_workflow_dispatch_present":
                (payload.get("source_audit") or {}).get("local_workflow_dispatch_present"),
            "parent_workflow_dispatch_present":
                (payload.get("source_audit") or {}).get("parent_workflow_dispatch_present"),
            "marker_indent":
                (payload.get("source_audit") or {}).get("marker_indent"),
            "write_error_indent":
                (payload.get("source_audit") or {}).get("write_error_indent"),
            "marker_indent_unsafe":
                (payload.get("source_audit") or {}).get("marker_indent_unsafe"),
        }, ensure_ascii=False, indent=2),
        "",
        "[RUN]",
        json.dumps(payload.get("runs", {}), ensure_ascii=False, indent=2),
        "",
        "[CLASSIFICATION]",
        json.dumps(payload.get("classification", {}), ensure_ascii=False, indent=2),
        "",
    ]

    if payload.get("error"):
        lines += ["[BLOCKER]", payload["error"].splitlines()[0], ""]

    lines += [
        "[STOP]",
        "diagnosis only; no workflow dispatch/rerun/commit/push/tag/release",
        f"report_json={REPORT_JSON}",
    ]

    REPORT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    payload = {
        "status": "FAIL",
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "commit": None,
        "repo_guard": {},
        "gh_error_compact": [],
        "registration": {},
        "source_audit": {},
        "runs": {},
        "classification": {},
        "error": None,
    }

    try:
        stage, commit, full_error = load_stage67i6()
        payload["commit"] = commit
        payload["repo_guard"] = repo_guard(commit)
        payload["gh_error_compact"] = compact_error(full_error)
        payload["registration"] = workflow_registration()
        payload["source_audit"] = workflow_source_audit(commit)
        payload["runs"] = matching_runs(commit)
        payload["classification"] = classify(
            full_error,
            payload["registration"],
            payload["source_audit"],
            payload["runs"],
        )
        payload["status"] = "PASS"

    except Exception as exc:
        payload["error"] = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"

    payload["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    write_report(payload)

    if payload["status"] == "PASS":
        c = payload["classification"]
        s = payload["source_audit"]
        reg = payload["registration"]

        print("[PASS] Stage67I6D / 0.5.15 Workflow Dispatch Failure Diagnosis R1")
        print(f"classification={c['root_classification']}")
        print("[GH ERROR]")
        for line in payload["gh_error_compact"][-6:]:
            print(line)
        print(
            "workflow="
            f"registered:{reg.get('registered')} "
            f"dispatch_local:{s.get('local_workflow_dispatch_present')} "
            f"dispatch_parent:{s.get('parent_workflow_dispatch_present')}"
        )
        print(
            "indent="
            f"marker:{s.get('marker_indent')} "
            f"write_error:{s.get('write_error_indent')} "
            f"unsafe:{s.get('marker_indent_unsafe')}"
        )
        print(f"matching_rc_runs={len((payload['runs'] or {}).get('matching') or [])}")
        print("[STOP] no rerun/commit/push/tag/release")
        print(f"report_txt={REPORT_TXT}")
        return 0

    print("[FAIL] Stage67I6D / Workflow Dispatch Failure Diagnosis R1")
    if payload.get("error"):
        print("[BLOCKER] " + payload["error"].splitlines()[0])
    print("[STOP] no rerun/commit/push/tag/release")
    print(f"report_txt={REPORT_TXT}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
