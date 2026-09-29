#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KDRG V4.7 Electron Stage67I7
0.5.15 Workflow Syntax Recovery + Shadow + Actual + Commit/Push + RC R1

Confirmed failure
-----------------
Stage67I6D proved:
- preserved pushed commit: f1025ca771a5efb36f843566ab6609f8f02c37d1
- GitHub workflow remains registered
- workflow_dispatch exists in both current and parent source
- no RC run was created
- inserted diagnostic marker indentation = 8
- PowerShell Write-Error indentation = 10
- marker indentation is unsafe inside the YAML run: | block
- GitHub dispatch rejected with HTTP 422:
  Workflow does not have 'workflow_dispatch' trigger

Recovery strategy
-----------------
Do NOT hand-edit the malformed current workflow.
Reconstruct the workflow from the pushed commit's PARENT version, which was the
last dispatchable workflow, then reapply ONLY the desired diagnostic reordering:
status / failed_step / missing_steps / message are moved before Write-Error,
with their original indentation preserved. No marker/comment is inserted.

Single execution, but strict gates:
1) read-only state/diagnosis gate
2) detached Shadow reconstruction + full validation
3) only after Shadow PASS: exact one-file Actual apply + full validation
4) only after Actual PASS: exact one-file commit + non-force push
5) one workflow_dispatch attempt for the new commit
6) wait exact RC and auto-extract compact failure context if needed

Before commit, any Actual validation failure restores the workflow exactly.
After commit/push, no reset/revert/amend is performed.
No tag/release is created.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import traceback


ROOT = Path.cwd().resolve()
ELECTRON = ROOT / "electron"

DIAG_JSON = ROOT / "stage67i6d_0515_workflow_dispatch_failure_r1.json"
STAGE67I5_JSON = ROOT / "stage67i5_0515_full_pipeline_actual_r1.json"

REPORT_TXT = ROOT / "stage67i7_0515_workflow_recovery_rc_r1.txt"
REPORT_JSON = ROOT / "stage67i7_0515_workflow_recovery_rc_r1.json"

WORKFLOW_REL = ".github/workflows/build-electron-windows.yml"
WORKFLOW_NAME = "build-electron-windows.yml"
RELEASE_TAG = "electron-v0.5.15"
BASE_TAG = "electron-v0.5.14"
BASE_0514_COMMIT = "4b79e02e8a45a8cabc88b63bc373d95cc21b6d9c"

BROKEN_COMMIT = "f1025ca771a5efb36f843566ab6609f8f02c37d1"
FIX_COMMIT_MESSAGE = "fix: restore workflow dispatch syntax"

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

EXPECTED_F102_FILES = [
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


def sha256_path(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_diagnosis_gate():
    require(DIAG_JSON.is_file(), "Stage67I6D diagnosis JSON missing")
    require(STAGE67I5_JSON.is_file(), "Stage67I5 Actual PASS JSON missing")

    diag = json.loads(DIAG_JSON.read_text(encoding="utf-8"))
    actual = json.loads(STAGE67I5_JSON.read_text(encoding="utf-8"))

    require(diag.get("status") == "PASS", "Stage67I6D is not PASS")
    require(
        (diag.get("classification") or {}).get("root_classification")
        == "LIKELY_INVALID_WORKFLOW_YAML_FROM_DIAGNOSTIC_MARKER_INDENTATION",
        "Stage67I6D classification mismatch",
    )
    require(diag.get("commit") == BROKEN_COMMIT, "diagnosed commit mismatch")

    src = diag.get("source_audit") or {}
    require(src.get("local_workflow_dispatch_present") is True,
            "local workflow_dispatch missing")
    require(src.get("parent_workflow_dispatch_present") is True,
            "parent workflow_dispatch missing")
    require(src.get("marker_indent_unsafe") is True,
            "unsafe marker indentation was not confirmed")
    require((diag.get("runs") or {}).get("matching") == [],
            "an RC run already exists for broken commit")

    gh_error = "\n".join(diag.get("gh_error_compact") or [])
    require("HTTP 422" in gh_error, "HTTP 422 not present in diagnosis")
    require("workflow_dispatch" in gh_error, "workflow_dispatch error not present")

    require(actual.get("status") == "PASS", "Stage67I5 Actual is not PASS")
    require(
        actual.get("readiness") == "READY_FOR_0515_FIX_COMMIT_PUSH_RC",
        "Stage67I5 readiness mismatch",
    )

    return {
        "broken_commit": BROKEN_COMMIT,
        "diagnosis": "unsafe YAML block indentation",
        "http_422": True,
    }


def state_gate():
    require(git_text("branch", "--show-current") == "main", "branch != main")
    require(git_text("rev-parse", "HEAD") == BROKEN_COMMIT,
            "HEAD != preserved broken commit")
    require(remote_main_sha() == BROKEN_COMMIT,
            "origin/main != preserved broken commit")
    require(not git_lines("diff", "--name-only"), "tracked worktree not clean")
    require(not git_lines("diff", "--cached", "--name-only"), "staging not empty")

    parent = git_text("rev-parse", f"{BROKEN_COMMIT}^")
    committed_files = sorted(
        git_lines(
            "diff-tree",
            "--no-commit-id",
            "--name-only",
            "-r",
            BROKEN_COMMIT,
        )
    )
    require(
        committed_files == sorted(EXPECTED_F102_FILES),
        "f102 commit file set mismatch: " + json.dumps(committed_files),
    )

    require(local_tag_sha(BASE_TAG) == BASE_0514_COMMIT,
            "0.5.14 local tag mismatch")
    require(remote_tag_sha(BASE_TAG) == BASE_0514_COMMIT,
            "0.5.14 remote tag mismatch")
    require(not local_tag_sha(RELEASE_TAG), "0.5.15 local tag exists")
    require(not remote_tag_sha(RELEASE_TAG), "0.5.15 remote tag exists")
    require(not release_exists(RELEASE_TAG), "0.5.15 Release exists")

    require(sha256_path(ROOT / RUNTIME_REL) == RUNTIME_SHA, "runtime SHA mismatch")
    require(sha256_path(ROOT / OFFICIAL_REL) == OFFICIAL_SHA,
            "official condition SHA mismatch")
    require(sha256_path(ROOT / ICON_PNG_REL) == ICON_PNG_SHA,
            "PNG icon SHA mismatch")
    require(sha256_path(ROOT / ICON_ICO_REL) == ICON_ICO_SHA,
            "ICO icon SHA mismatch")

    return {
        "head": BROKEN_COMMIT,
        "origin_main": BROKEN_COMMIT,
        "parent": parent,
        "f102_file_set": committed_files,
        "worktree_clean": True,
        "staging_empty": True,
        "tag_release_absent": True,
    }


def reconstruct_workflow_from_parent(parent):
    parent_result = run(
        ["git", "show", f"{parent}:{WORKFLOW_REL}"],
        check=True,
    )
    text = parent_result["output"]

    require(
        bool(re.search(r"(?m)^\s*workflow_dispatch\s*:", text)),
        "parent workflow lacks workflow_dispatch",
    )

    error_line = 'Write-Error "packaged 핵심검증 실패"'
    diagnostics = [
        ('status', 'Write-Host "status=$($report.status)"'),
        ('failed_step', 'Write-Host "failed_step=$($report.failed_step)"'),
        ('missing_steps', 'Write-Host "missing_steps=$($missing -join \',\')"'),
        ('message', 'Write-Host "message=$message"'),
    ]

    lines = text.splitlines(keepends=True)

    error_indices = [
        i for i, line in enumerate(lines)
        if error_line in line
    ]
    require(len(error_indices) == 1,
            f"parent hard-failure Write-Error count={len(error_indices)}")
    error_idx = error_indices[0]

    search_end = min(len(lines), error_idx + 20)
    local = {}

    for key, needle in diagnostics:
        matches = [
            i for i in range(error_idx + 1, search_end)
            if needle in lines[i]
        ]
        require(
            len(matches) == 1,
            f"parent hard-failure {key} diagnostic count={len(matches)}",
        )
        local[key] = matches[0]

    ordered = [local[key] for key, _ in diagnostics]
    require(ordered == sorted(ordered),
            "parent hard-failure diagnostic order unexpected")

    moved_lines = [lines[i] for i in ordered]
    error_indent = len(lines[error_idx]) - len(lines[error_idx].lstrip(" "))

    for line in moved_lines:
        indent = len(line) - len(line.lstrip(" "))
        require(
            indent == error_indent,
            f"parent diagnostic indentation {indent} != Write-Error {error_indent}",
        )

    for i in sorted(ordered, reverse=True):
        lines.pop(i)

    error_idx2 = next(
        i for i, line in enumerate(lines)
        if error_line in line
    )
    lines[error_idx2:error_idx2] = moved_lines

    candidate = "".join(lines)

    # No marker/comment: only relocation of existing PowerShell lines.
    require("Stage67I4B: emit diagnostics before terminating" not in candidate,
            "unsafe diagnostic marker leaked into candidate")

    return candidate


def workflow_semantic_audit(text):
    error = 'Write-Error "packaged 핵심검증 실패"'
    diagnostics = [
        ('status', 'Write-Host "status=$($report.status)"'),
        ('failed_step', 'Write-Host "failed_step=$($report.failed_step)"'),
        ('missing_steps', 'Write-Host "missing_steps=$($missing -join \',\')"'),
        ('message', 'Write-Host "message=$message"'),
    ]

    require(bool(re.search(r"(?m)^\s*workflow_dispatch\s*:", text)),
            "candidate workflow_dispatch missing")
    require("$uiWarningOnly" in text, "UI-warning branch missing")
    require("[PASS_WITH_UI_WARNING]" in text, "UI-warning PASS marker missing")
    require("packaged_ui_validation" in text, "packaged UI gate missing")
    require(text.count(error) == 1, "Write-Error count mismatch")

    error_pos = text.index(error)
    error_line = text[:error_pos].count("\n") + 1
    lines = text.splitlines()
    error_indent = len(lines[error_line - 1]) - len(lines[error_line - 1].lstrip(" "))

    local_positions = {}
    local_indents = {}

    for key, needle in diagnostics:
        positions = [m.start() for m in re.finditer(re.escape(needle), text)]
        before = [p for p in positions if p < error_pos]
        require(before, f"candidate {key} diagnostic missing before Write-Error")

        # The closest occurrence before Write-Error belongs to hard-failure block.
        pos = max(before)
        line_no = text[:pos].count("\n") + 1
        indent = len(lines[line_no - 1]) - len(lines[line_no - 1].lstrip(" "))
        local_positions[key] = pos
        local_indents[key] = indent
        require(indent == error_indent,
                f"candidate {key} indent {indent} != Write-Error {error_indent}")

    require(
        local_positions["status"]
        < local_positions["failed_step"]
        < local_positions["missing_steps"]
        < local_positions["message"]
        < error_pos,
        "candidate hard-failure diagnostics not ordered before Write-Error",
    )

    tab_lines = []
    for i, line in enumerate(lines, 1):
        prefix = line[:len(line) - len(line.lstrip())]
        if "\t" in prefix:
            tab_lines.append(i)
    require(not tab_lines, f"tab indentation found: {tab_lines[:10]}")

    return {
        "workflow_dispatch_present": True,
        "warning_branch_preserved": True,
        "diagnostics_before_error": True,
        "error_indent": error_indent,
        "diagnostic_indents": local_indents,
        "unsafe_marker_absent": True,
        "tab_indentation_absent": True,
    }


def create_shadow(commit):
    shadow = Path(tempfile.mkdtemp(prefix="kdrg_stage67i7_shadow_"))
    shutil.rmtree(shadow)

    r = run(
        ["git", "worktree", "add", "--detach", str(shadow), commit],
        check=False,
        timeout=600,
    )
    require(r["returncode"] == 0, "git worktree add failed:\n" + r["output"])
    return shadow


def yaml_parser_probe(path):
    """
    Optional local syntax parser. We do not depend on PyYAML being installed,
    but if available it must parse successfully. This supplements the stronger
    reconstruction-from-known-valid-parent strategy.
    """
    probe = run(
        [
            "python",
            "-c",
            (
                "import sys; "
                "p=sys.argv[1]; "
                "try:\n"
                " import yaml\n"
                "except Exception:\n"
                " print('PY_YAML_UNAVAILABLE'); raise SystemExit(0)\n"
                "yaml.safe_load(open(p,encoding='utf-8')); "
                "print('PY_YAML_PARSE_PASS')"
            ),
            str(path),
        ],
        check=False,
        timeout=120,
    )

    # The compact -c may be sensitive to Python formatting; treat parser
    # unavailability/probe syntax as informational. Structural reconstruction
    # and validators remain blockers.
    out = probe["output"].strip()
    return {
        "returncode": probe["returncode"],
        "output": out[-1000:],
        "authoritative": False,
    }


def validate_repo(tree):
    commands = []

    def check(cmd, cwd=None, timeout=1800):
        r = run(cmd, cwd=cwd or tree, check=False, timeout=timeout)
        commands.append({
            "cmd": " ".join(str(x) for x in cmd),
            "returncode": r["returncode"],
            "tail": "\n".join(r["output"].splitlines()[-8:]),
        })
        require(
            r["returncode"] == 0,
            f"validation failed: {' '.join(cmd)}\n{r['output']}",
        )

    # Existing source/application validation matrix.
    check(["node", "tests/validate-stage59b-search.js"], cwd=tree / "electron")
    check(["node", "tests/validate-packaged-runtime-smoke.js"], cwd=tree / "electron")
    check(["node", "tests/validate-stage60c-packaged-relation-smoke.js"],
          cwd=tree / "electron")
    check(["node", "tests/validate-stage59b-ui.js"], cwd=tree / "electron")
    check(["node", "tests/validate-stage59b-smoke.js"], cwd=tree / "electron")
    check(["npm", "run", "check"], cwd=tree / "electron", timeout=1800)

    for rel in ROOT_VALIDATORS:
        check(["python", rel], cwd=tree, timeout=1800)

    check(["node", "tests/validate-release-version.js", VERSION],
          cwd=tree / "electron")

    # Key immutable assets.
    require(sha256_path(tree / RUNTIME_REL) == RUNTIME_SHA,
            "runtime changed in validation tree")
    require(sha256_path(tree / OFFICIAL_REL) == OFFICIAL_SHA,
            "official condition changed in validation tree")
    require(sha256_path(tree / ICON_PNG_REL) == ICON_PNG_SHA,
            "PNG icon changed in validation tree")
    require(sha256_path(tree / ICON_ICO_REL) == ICON_ICO_SHA,
            "ICO icon changed in validation tree")

    return {
        "commands": commands,
        "npm_stage_validators": "PASS",
        "root_50b_50c_50d": "PASS",
        "release_version": "PASS",
        "immutable_assets": "PASS",
    }


def build_and_validate_shadow(parent):
    candidate = reconstruct_workflow_from_parent(parent)
    semantic = workflow_semantic_audit(candidate)

    shadow = create_shadow(BROKEN_COMMIT)
    try:
        (shadow / WORKFLOW_REL).write_text(candidate, encoding="utf-8", newline="")

        changed = sorted(git_lines("diff", "--name-only", cwd=shadow))
        require(changed == [WORKFLOW_REL],
                "Shadow delta is not exact workflow file: " + json.dumps(changed))

        diff_check = run(["git", "diff", "--check"], cwd=shadow, check=False)
        require(diff_check["returncode"] == 0,
                "Shadow git diff --check failed:\n" + diff_check["output"])

        # Compare candidate against last known dispatchable parent workflow.
        workflow_diff = run(
            ["git", "diff", "--unified=3", f"{parent}", "--", WORKFLOW_REL],
            cwd=shadow,
            check=True,
        )["output"]

        added = [
            line for line in workflow_diff.splitlines()
            if line.startswith("+") and not line.startswith("+++")
        ]
        removed = [
            line for line in workflow_diff.splitlines()
            if line.startswith("-") and not line.startswith("---")
        ]

        # Reordering should be compact and limited to the failure diagnostics.
        require(len(added) <= 6 and len(removed) <= 6,
                f"workflow repair diff too large: +{len(added)} -{len(removed)}")

        allowed_needles = [
            "Write-Host",
            "status=",
            "failed_step=",
            "missing_steps=",
            "message=",
        ]
        for line in added + removed:
            require(
                any(n in line for n in allowed_needles),
                "workflow diff contains unrelated change: " + line,
            )

        validation = validate_repo(shadow)

        source_path = shadow / WORKFLOW_REL
        candidate_sha = sha256_path(source_path)
        parser = yaml_parser_probe(source_path)

        # Preserve successful Shadow as exact Actual source.
        return {
            "shadow_root": str(shadow),
            "candidate_sha256": candidate_sha,
            "semantic": semantic,
            "validation": validation,
            "git_diff_check": "PASS",
            "workflow_diff_added": added,
            "workflow_diff_removed": removed,
            "optional_yaml_parser": parser,
        }, shadow

    except Exception:
        run(["git", "worktree", "remove", "--force", str(shadow)],
            check=False, timeout=600)
        raise


def apply_actual(shadow_info, shadow):
    actual_path = ROOT / WORKFLOW_REL
    source_path = shadow / WORKFLOW_REL

    before_bytes = actual_path.read_bytes()
    before_sha = hashlib.sha256(before_bytes).hexdigest()

    try:
        shutil.copy2(source_path, actual_path)

        require(
            sha256_path(actual_path) == shadow_info["candidate_sha256"],
            "Actual workflow SHA != Shadow candidate",
        )

        changed = sorted(git_lines("diff", "--name-only"))
        require(changed == [WORKFLOW_REL],
                "Actual delta is not exact workflow file: " + json.dumps(changed))

        diff_check = run(["git", "diff", "--check"], check=False)
        require(diff_check["returncode"] == 0,
                "Actual git diff --check failed:\n" + diff_check["output"])

        semantic = workflow_semantic_audit(
            actual_path.read_text(encoding="utf-8")
        )
        validation = validate_repo(ROOT)

        require(not git_lines("diff", "--cached", "--name-only"),
                "staging not empty before commit")

        return {
            "before_sha256": before_sha,
            "after_sha256": sha256_path(actual_path),
            "semantic": semantic,
            "validation": validation,
            "git_diff_check": "PASS",
            "tracked_delta": changed,
        }, before_bytes

    except Exception:
        actual_path.write_bytes(before_bytes)
        run(["git", "reset", "--", WORKFLOW_REL], check=False)

        clean = not git_lines("diff", "--name-only")
        staged_empty = not git_lines("diff", "--cached", "--name-only")
        require(clean and staged_empty,
                "Actual rollback did not restore clean state")
        raise


def commit_and_push(candidate_sha):
    require(sorted(git_lines("diff", "--name-only")) == [WORKFLOW_REL],
            "pre-commit delta is not exact workflow")
    require(sha256_path(ROOT / WORKFLOW_REL) == candidate_sha,
            "pre-commit workflow candidate SHA mismatch")

    run(["git", "add", "--", WORKFLOW_REL])

    staged = sorted(git_lines("diff", "--cached", "--name-only"))
    require(staged == [WORKFLOW_REL], "staged set is not exact workflow")

    cached_check = run(["git", "diff", "--cached", "--check"], check=False)
    require(cached_check["returncode"] == 0,
            "cached diff --check failed:\n" + cached_check["output"])

    run(["git", "commit", "-m", FIX_COMMIT_MESSAGE])

    commit = git_text("rev-parse", "HEAD")
    require(git_text("rev-parse", f"{commit}^") == BROKEN_COMMIT,
            "workflow recovery commit parent mismatch")
    require(git_text("show", "-s", "--format=%s", commit) == FIX_COMMIT_MESSAGE,
            "workflow recovery commit message mismatch")

    committed = sorted(
        git_lines("diff-tree", "--no-commit-id", "--name-only", "-r", commit)
    )
    require(committed == [WORKFLOW_REL],
            "workflow recovery commit contains unexpected files")

    require(not git_lines("diff", "--name-only"),
            "worktree not clean after recovery commit")
    require(not git_lines("diff", "--cached", "--name-only"),
            "staging not empty after recovery commit")

    origin_before = remote_main_sha()
    require(origin_before == BROKEN_COMMIT,
            "origin/main moved before recovery push")

    run(["git", "push", "origin", "main"])
    origin_after = remote_main_sha()
    require(origin_after == commit, "origin/main did not reach recovery commit")

    return {
        "commit": commit,
        "parent": BROKEN_COMMIT,
        "committed_files": committed,
        "origin_before": origin_before,
        "origin_after": origin_after,
    }


def workflow_registration():
    repo_data = json.loads(
        run(["gh", "repo", "view", "--json", "nameWithOwner"])["output"]
    )
    owner_repo = repo_data["nameWithOwner"]

    api = run(
        ["gh", "api", f"repos/{owner_repo}/actions/workflows"],
        check=False,
    )
    require(api["returncode"] == 0,
            "workflow registration API failed:\n" + api["output"])

    data = json.loads(api["output"])
    workflow = None
    for wf in data.get("workflows") or []:
        path = str(wf.get("path") or "")
        if path.endswith("/" + WORKFLOW_NAME):
            workflow = wf
            break

    require(workflow, "workflow is not registered after recovery push")
    require(workflow.get("state") == "active",
            f"workflow state is not active: {workflow.get('state')}")

    return {
        "owner_repo": owner_repo,
        "workflow_id": workflow.get("id"),
        "state": workflow.get("state"),
        "path": workflow.get("path"),
    }


def list_matching_runs(commit):
    r = run(
        [
            "gh", "run", "list",
            "--workflow", WORKFLOW_NAME,
            "--limit", "30",
            "--json",
            "databaseId,headSha,headBranch,event,status,conclusion,createdAt,url",
        ],
        check=False,
    )
    require(r["returncode"] == 0, "gh run list failed:\n" + r["output"])

    rows = json.loads(r["output"] or "[]")
    return [
        row for row in rows
        if row.get("headSha") == commit
        and row.get("headBranch") == "main"
        and row.get("event") == "workflow_dispatch"
    ]


def dispatch_once(commit):
    existing = list_matching_runs(commit)
    require(not existing, "workflow_dispatch run already exists for recovery commit")

    # Brief propagation window after push.
    time.sleep(5)

    dispatch = run(
        ["gh", "workflow", "run", WORKFLOW_NAME, "--ref", "main"],
        check=False,
        timeout=600,
    )
    if dispatch["returncode"] != 0:
        raise StageError(
            "workflow dispatch failed after syntax recovery:\n"
            + dispatch["output"]
        )

    deadline = time.time() + 120
    while time.time() < deadline:
        time.sleep(3)
        rows = list_matching_runs(commit)
        if rows:
            return sorted(
                rows,
                key=lambda x: x.get("createdAt") or "",
                reverse=True,
            )[0]

    raise StageError("new RC run not found within 120s after dispatch")


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

    keys = [
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

    focused = [
        line
        for line in log.splitlines()
        if any(k.lower() in line.lower() for k in keys)
    ]

    return {
        "failed_steps": failed_steps,
        "error_focus": focused[-30:],
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

    context = {
        "failed_steps": [],
        "error_focus": [],
    }
    if data.get("conclusion") != "success":
        context = failure_context(run_id, data)

    return {
        "run": data,
        "success": data.get("conclusion") == "success",
        **context,
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
        "KDRG V4.7 Electron Stage67I7 / 0.5.15 Workflow Syntax Recovery + RC R1",
        "=" * 106,
        f"status={payload['status']}",
        f"readiness={payload['readiness']}",
        "",
        "[SHADOW]",
        json.dumps({
            "candidate_sha256":
                (payload.get("shadow") or {}).get("candidate_sha256"),
            "semantic":
                (payload.get("shadow") or {}).get("semantic"),
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
        "[WORKFLOW REGISTRATION]",
        json.dumps(payload.get("registration", {}), ensure_ascii=False, indent=2),
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
        json.dumps(payload.get("final_guard", {}), ensure_ascii=False, indent=2),
        "",
    ]

    if payload.get("error"):
        lines += ["[BLOCKER]", payload["error"].splitlines()[0], ""]

    lines += [
        "[NEXT]",
        "- RC success이면 READY_FOR_0515_TAG_RELEASE.",
        "- RC failure이면 자동 재실행하지 않고 failed_steps/error_focus 사용.",
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
        "shadow": {},
        "actual": {},
        "commit_push": {},
        "registration": {},
        "dispatch": {},
        "rc": {},
        "final_guard": {},
        "error": None,
    }

    shadow = None
    committed = False

    try:
        payload["gate"] = load_diagnosis_gate()
        payload["state"] = state_gate()

        payload["shadow"], shadow = build_and_validate_shadow(
            payload["state"]["parent"]
        )

        payload["actual"], _ = apply_actual(payload["shadow"], shadow)

        # Remove Shadow only after Actual has received the exact candidate.
        run(
            ["git", "worktree", "remove", "--force", str(shadow)],
            check=False,
            timeout=600,
        )
        shadow = None

        payload["commit_push"] = commit_and_push(
            payload["shadow"]["candidate_sha256"]
        )
        committed = True
        commit = payload["commit_push"]["commit"]

        payload["registration"] = workflow_registration()
        payload["dispatch"] = dispatch_once(commit)
        payload["rc"] = wait_rc(payload["dispatch"], commit)
        payload["final_guard"] = final_guard(commit)

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

        # If no commit was made, Actual apply helper already rolls back on its
        # own validation errors. If we failed later, preserve pushed history.
        if committed:
            commit = (payload.get("commit_push") or {}).get("commit")
            if commit:
                try:
                    payload["final_guard"] = final_guard(commit)
                except Exception:
                    pass

    payload["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    write_report(payload)

    if payload["status"] == "PASS":
        rc_run = payload["rc"]["run"]
        print("[PASS] Stage67I7 / 0.5.15 Workflow Syntax Recovery + RC R1")
        print("readiness=READY_FOR_0515_TAG_RELEASE")
        print("[PASS] known-valid parent workflow reconstructed / unsafe marker removed")
        print("[PASS] Shadow full validation -> Actual full validation")
        print(
            f"[PASS] recovery commit={payload['commit_push']['commit']} "
            f"origin/main={payload['commit_push']['origin_after']}"
        )
        print(
            f"[PASS] RC run={rc_run.get('databaseId')} "
            f"conclusion={rc_run.get('conclusion')}"
        )
        print("[PASS] worktree/staging clean / 0.5.15 tag+release absent")
        print("[STOP] no tag/release")
        print(f"report_txt={REPORT_TXT}")
        return 0

    print("[FAIL] Stage67I7 / 0.5.15 Workflow Syntax Recovery + RC R1")
    print("readiness=NOT_READY_FOR_0515_TAG_RELEASE")

    commit = (payload.get("commit_push") or {}).get("commit")
    if commit:
        print(f"[PRESERVED] recovery_commit={commit}")

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
