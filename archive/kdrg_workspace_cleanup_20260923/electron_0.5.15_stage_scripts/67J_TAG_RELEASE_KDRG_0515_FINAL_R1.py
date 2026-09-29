#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KDRG V4.7 Electron Stage67J
0.5.15 Final Tag + Release Verification R1

Gate
----
Requires Stage67I7 R2 PASS:
  readiness=READY_FOR_0515_TAG_RELEASE
  final commit=6e0bc2857ebf6abb482428b90f452d5e07c486ac
  RC run=35811340221
  RC conclusion=success

Flow
----
1) Final preflight: HEAD/origin/worktree/staging/version/runtime/official/icon.
2) Re-verify exact successful workflow_dispatch RC.
3) Verify immutable previous release tags.
4) Detect previous tag object type from electron-v0.5.14.
5) Create electron-v0.5.15 tag only if absent, using same tag type.
6) Push exact tag only.
7) Find/watch exact tag-triggered workflow for the exact tag+commit.
8) Never auto-rerun a failed tag workflow.
9) Wait for GitHub Release electron-v0.5.15.
10) Verify exact Portable EXE asset, download to temp, compute SHA256.
11) Verify final tag/release/HEAD/origin and old tag immutability.
12) Print concise final release summary.

Re-entry safe:
- exact existing local/remote tag is reused
- exact existing successful tag workflow is reused
- exact existing Release/asset is reused
- any tag mismatch or failed tag workflow stops safely

This stage does NOT move/delete/repoint any existing tag/release.
"""

from __future__ import annotations

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

GATE_JSON = ROOT / "stage67i7_0515_workflow_recovery_rc_r2.json"

REPORT_TXT = ROOT / "stage67j_0515_tag_release_final_r1.txt"
REPORT_JSON = ROOT / "stage67j_0515_tag_release_final_r1.json"

WORKFLOW = "build-electron-windows.yml"
TAG = "electron-v0.5.15"
VERSION = "0.5.15"

FINAL_COMMIT = "6e0bc2857ebf6abb482428b90f452d5e07c486ac"
RC_RUN_ID = 35811340221

ASSET_NAME = "KDRG_V47_Relation_Search_Electron_0.5.15_Portable.exe"

IMMUTABLE_TAGS = {
    "electron-v0.5.12": "1ab52cf1bbfe158d6ab88247a47074e79db9ad9c",
    "electron-v0.5.13": "2f00202a2fa9589bb5f05cf615b962537ad58fbc",
    "electron-v0.5.14": "4b79e02e8a45a8cabc88b63bc373d95cc21b6d9c",
}

RUNTIME_REL = "data/kdrg_v47_search_integrated_v3.json"
RUNTIME_SHA = "1a3d50400567ecaad9695b7be8e7c0382131f8652f398e010cf01f4d8dda6c58"

OFFICIAL_REL = "electron/renderer/official-condition-text.js"
OFFICIAL_SHA = "6f8dcef30a2eb54ce4b36d918bd5d7949712979fd0f880f1990ffc43e915581e"

ICON_PNG_REL = "electron/renderer/assets/icon-kdrg-v47.png"
ICON_PNG_SHA = "6ddc9f093a82cf9c5f1cc910fce1a0b101352305c71fbc38ae578e11bf93a79d"

ICON_ICO_REL = "electron/renderer/assets/icon-kdrg-v47.ico"
ICON_ICO_SHA = "2321ec9bd820e50e8da73d6faf63f7b15d3a4ceb02da2ed54f4d9332a66a8c45"


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


def local_tag_commit(tag):
    r = run(
        ["git", "rev-list", "-n", "1", tag],
        check=False,
    )
    return r["output"].strip() if r["returncode"] == 0 else ""


def local_tag_type(tag):
    r = run(
        ["git", "cat-file", "-t", f"refs/tags/{tag}"],
        check=False,
    )
    return r["output"].strip() if r["returncode"] == 0 else ""


def remote_tag_commit(tag):
    """
    Dereference annotated tag when needed.
    For lightweight tags, direct ref is the commit.
    """
    out = run(
        [
            "git", "ls-remote", "--tags", "origin",
            f"refs/tags/{tag}",
            f"refs/tags/{tag}^{{}}",
        ]
    )["output"].splitlines()

    direct = ""
    peeled = ""
    for line in out:
        parts = line.split()
        if len(parts) < 2:
            continue
        sha, ref = parts[0], parts[1]
        if ref == f"refs/tags/{tag}":
            direct = sha
        elif ref == f"refs/tags/{tag}^{{}}":
            peeled = sha

    return peeled or direct


def release_view(tag):
    r = run(
        [
            "gh", "release", "view", tag,
            "--json",
            "tagName,name,isDraft,isPrerelease,assets,url,targetCommitish",
        ],
        check=False,
        timeout=600,
    )
    if r["returncode"] != 0:
        return None
    return json.loads(r["output"])


def sha256_path(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_gate():
    require(GATE_JSON.is_file(), "Stage67I7 R2 report JSON missing")
    data = json.loads(GATE_JSON.read_text(encoding="utf-8"))

    require(data.get("status") == "PASS", "Stage67I7 R2 is not PASS")
    require(
        data.get("readiness") == "READY_FOR_0515_TAG_RELEASE",
        "Stage67I7 R2 readiness mismatch",
    )

    commit_push = data.get("commit_push") or {}
    rc = data.get("rc") or {}
    run_data = rc.get("run") or {}
    final_guard = data.get("final_guard") or {}

    require(commit_push.get("commit") == FINAL_COMMIT,
            "Stage67I7 final commit mismatch")
    require(commit_push.get("origin_after") == FINAL_COMMIT,
            "Stage67I7 origin/main mismatch")
    require(run_data.get("databaseId") == RC_RUN_ID,
            "Stage67I7 RC run id mismatch")
    require(run_data.get("headSha") == FINAL_COMMIT,
            "Stage67I7 RC head SHA mismatch")
    require(run_data.get("headBranch") == "main",
            "Stage67I7 RC branch mismatch")
    require(run_data.get("event") == "workflow_dispatch",
            "Stage67I7 RC event mismatch")
    require(run_data.get("status") == "completed",
            "Stage67I7 RC not completed")
    require(run_data.get("conclusion") == "success",
            "Stage67I7 RC not successful")
    require(final_guard.get("release_tag_absent") is True,
            "Stage67I7 release tag guard mismatch")
    require(final_guard.get("release_absent") is True,
            "Stage67I7 release guard mismatch")

    return {
        "final_commit": FINAL_COMMIT,
        "rc_run_id": RC_RUN_ID,
        "rc_url": run_data.get("url"),
    }


def package_guard():
    package = json.loads((ELECTRON / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((ELECTRON / "package-lock.json").read_text(encoding="utf-8"))

    require(package.get("version") == VERSION,
            "package.json version mismatch")
    require(lock.get("version") == VERSION,
            "package-lock top version mismatch")
    require(
        (lock.get("packages") or {}).get("", {}).get("version") == VERSION,
        "package-lock root version mismatch",
    )

    return {
        "package_version": package.get("version"),
        "lock_version": lock.get("version"),
        "lock_root_version":
            (lock.get("packages") or {}).get("", {}).get("version"),
    }


def verify_rc_again():
    r = run(
        [
            "gh", "run", "view", str(RC_RUN_ID),
            "--json",
            "databaseId,headSha,headBranch,event,status,conclusion,url",
        ],
        check=False,
        timeout=600,
    )
    require(r["returncode"] == 0, "RC recheck failed:\n" + r["output"])

    data = json.loads(r["output"])
    require(data.get("databaseId") == RC_RUN_ID, "RC id mismatch")
    require(data.get("headSha") == FINAL_COMMIT, "RC commit mismatch")
    require(data.get("headBranch") == "main", "RC branch mismatch")
    require(data.get("event") == "workflow_dispatch", "RC event mismatch")
    require(data.get("status") == "completed", "RC is not completed")
    require(data.get("conclusion") == "success", "RC is not success")
    return data


def verify_immutable_tags():
    # Refresh only tag refs; does not alter worktree/history.
    run(["git", "fetch", "origin", "--tags"])

    results = {}
    for tag, expected in IMMUTABLE_TAGS.items():
        remote = remote_tag_commit(tag)
        require(remote == expected,
                f"immutable remote tag mismatch: {tag} {remote} != {expected}")

        local = local_tag_commit(tag)
        if local:
            require(local == expected,
                    f"immutable local tag mismatch: {tag} {local} != {expected}")

        results[tag] = {
            "expected_commit": expected,
            "remote_commit": remote,
            "local_commit": local or None,
        }

    return results


def preflight():
    require(git_text("branch", "--show-current") == "main", "branch != main")
    require(git_text("rev-parse", "HEAD") == FINAL_COMMIT,
            "HEAD != final release commit")
    require(remote_main_sha() == FINAL_COMMIT,
            "origin/main != final release commit")
    require(not git_lines("diff", "--name-only"),
            "tracked worktree not clean")
    require(not git_lines("diff", "--cached", "--name-only"),
            "staging not empty")

    package = package_guard()

    require(sha256_path(ROOT / RUNTIME_REL) == RUNTIME_SHA,
            "runtime SHA mismatch")
    require(sha256_path(ROOT / OFFICIAL_REL) == OFFICIAL_SHA,
            "official condition SHA mismatch")
    require(sha256_path(ROOT / ICON_PNG_REL) == ICON_PNG_SHA,
            "PNG icon SHA mismatch")
    require(sha256_path(ROOT / ICON_ICO_REL) == ICON_ICO_SHA,
            "ICO icon SHA mismatch")

    rc = verify_rc_again()
    immutable = verify_immutable_tags()

    return {
        "head": FINAL_COMMIT,
        "origin_main": FINAL_COMMIT,
        "worktree_clean": True,
        "staging_empty": True,
        "package": package,
        "runtime_unchanged": True,
        "official_condition_unchanged": True,
        "icons_unchanged": True,
        "rc": rc,
        "immutable_tags": immutable,
    }


def previous_tag_pattern():
    previous = "electron-v0.5.14"
    tag_type = local_tag_type(previous)

    if not tag_type:
        # fetch should have created remote-tracking tag locally; retry once.
        run(["git", "fetch", "origin", "tag", previous])
        tag_type = local_tag_type(previous)

    require(tag_type in ("commit", "tag"),
            f"unsupported previous tag object type: {tag_type}")

    return {
        "previous_tag": previous,
        "object_type": tag_type,
        "creation_style": "lightweight" if tag_type == "commit" else "annotated",
    }


def create_or_reuse_tag(pattern):
    local_commit = local_tag_commit(TAG)
    remote_commit = remote_tag_commit(TAG)

    if local_commit:
        require(local_commit == FINAL_COMMIT,
                f"existing local {TAG} points to {local_commit}")

    if remote_commit:
        require(remote_commit == FINAL_COMMIT,
                f"existing remote {TAG} points to {remote_commit}")

    created_local = False
    pushed_remote = False

    if not local_commit:
        if pattern["object_type"] == "commit":
            run(["git", "tag", TAG, FINAL_COMMIT])
        else:
            run([
                "git", "tag", "-a", TAG, FINAL_COMMIT,
                "-m", f"KDRG Electron {VERSION}",
            ])
        created_local = True

    require(local_tag_commit(TAG) == FINAL_COMMIT,
            "local release tag does not point to final commit")
    require(local_tag_type(TAG) == pattern["object_type"],
            "release tag object type differs from previous release")

    remote_commit = remote_tag_commit(TAG)
    if not remote_commit:
        run(["git", "push", "origin", f"refs/tags/{TAG}"])
        pushed_remote = True

    require(remote_tag_commit(TAG) == FINAL_COMMIT,
            "remote release tag does not point to final commit")

    return {
        "tag": TAG,
        "commit": FINAL_COMMIT,
        "object_type": pattern["object_type"],
        "created_local": created_local,
        "pushed_remote": pushed_remote,
    }


def prior_tag_workflow_pattern():
    previous_tag = "electron-v0.5.14"
    previous_commit = IMMUTABLE_TAGS[previous_tag]

    r = run(
        [
            "gh", "run", "list",
            "--workflow", WORKFLOW,
            "--limit", "60",
            "--json",
            "databaseId,headSha,headBranch,event,status,conclusion,createdAt,url",
        ],
        check=False,
        timeout=600,
    )
    require(r["returncode"] == 0,
            "historical tag workflow lookup failed:\n" + r["output"])

    rows = json.loads(r["output"] or "[]")
    matches = [
        row for row in rows
        if row.get("headSha") == previous_commit
        and row.get("headBranch") == previous_tag
        and row.get("status") == "completed"
        and row.get("conclusion") == "success"
    ]
    require(matches, "successful 0.5.14 tag workflow history not found")

    newest = sorted(
        matches,
        key=lambda x: x.get("createdAt") or "",
        reverse=True,
    )[0]

    require(newest.get("event"),
            "previous tag workflow event missing")

    return {
        "previous_tag": previous_tag,
        "previous_commit": previous_commit,
        "event": newest.get("event"),
        "run_id": newest.get("databaseId"),
        "url": newest.get("url"),
    }


def list_tag_runs(pattern):
    r = run(
        [
            "gh", "run", "list",
            "--workflow", WORKFLOW,
            "--limit", "60",
            "--json",
            "databaseId,headSha,headBranch,event,status,conclusion,createdAt,url",
        ],
        check=False,
        timeout=600,
    )
    require(r["returncode"] == 0,
            "tag workflow list failed:\n" + r["output"])

    rows = json.loads(r["output"] or "[]")
    return [
        row for row in rows
        if row.get("headSha") == FINAL_COMMIT
        and row.get("headBranch") == TAG
        and row.get("event") == pattern["event"]
    ]


def wait_for_tag_run(pattern, timeout=180):
    deadline = time.time() + timeout

    while time.time() < deadline:
        matches = list_tag_runs(pattern)

        if matches:
            newest = sorted(
                matches,
                key=lambda x: x.get("createdAt") or "",
                reverse=True,
            )[0]

            # If the exact tag workflow already failed, never rerun it.
            if (
                newest.get("status") == "completed"
                and newest.get("conclusion") != "success"
            ):
                return {
                    "run": newest,
                    "reused": True,
                    "failed_existing": True,
                }

            return {
                "run": newest,
                "reused": True,
                "failed_existing": False,
            }

        time.sleep(4)

    raise StageError("exact tag-triggered workflow not found within 180s")


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
    require(r["returncode"] == 0,
            "tag workflow view failed:\n" + r["output"])
    return json.loads(r["output"])


def failed_context(run_id, data):
    failed_steps = []
    for job in data.get("jobs") or []:
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
        "release",
        "asset",
        "process completed with exit code",
    ]

    focus = [
        line
        for line in log.splitlines()
        if any(k in line.lower() for k in keywords)
    ]

    return {
        "failed_steps": failed_steps,
        "error_focus": focus[-30:],
    }


def watch_tag_run(tag_run, pattern):
    row = tag_run["run"]
    run_id = row.get("databaseId")
    require(run_id, "tag workflow run id missing")

    data = refresh_run(run_id)

    require(data.get("headSha") == FINAL_COMMIT,
            "tag workflow commit mismatch")
    require(data.get("headBranch") == TAG,
            "tag workflow headBranch mismatch")
    require(data.get("event") == pattern["event"],
            "tag workflow event mismatch")

    if data.get("status") != "completed":
        run(
            ["gh", "run", "watch", str(run_id), "--exit-status"],
            check=False,
            timeout=3600,
        )
        data = refresh_run(run_id)

    require(data.get("status") == "completed",
            "tag workflow did not complete")

    context = {
        "failed_steps": [],
        "error_focus": [],
    }

    if data.get("conclusion") != "success":
        context = failed_context(run_id, data)

    return {
        "run": data,
        "success": data.get("conclusion") == "success",
        **context,
    }


def wait_release(timeout=300):
    deadline = time.time() + timeout
    last = None

    while time.time() < deadline:
        last = release_view(TAG)
        if last:
            assets = last.get("assets") or []
            names = [x.get("name") for x in assets]
            if ASSET_NAME in names:
                return last
        time.sleep(5)

    raise StageError(
        "GitHub Release/Portable asset not available within 300s; "
        + json.dumps(last, ensure_ascii=False)
    )


def verify_release(release):
    require(release.get("tagName") == TAG, "Release tagName mismatch")
    require(release.get("isDraft") is False, "Release is draft")
    require(release.get("isPrerelease") is False, "Release is prerelease")

    assets = release.get("assets") or []
    named = [x for x in assets if x.get("name") == ASSET_NAME]
    require(len(named) == 1,
            f"Portable EXE asset count != 1: {len(named)}")

    return {
        "tagName": release.get("tagName"),
        "name": release.get("name"),
        "isDraft": release.get("isDraft"),
        "isPrerelease": release.get("isPrerelease"),
        "url": release.get("url"),
        "targetCommitish": release.get("targetCommitish"),
        "asset": named[0],
    }


def download_asset_and_hash():
    temp_dir = Path(tempfile.mkdtemp(prefix="kdrg_0515_release_asset_"))

    try:
        r = run(
            [
                "gh", "release", "download", TAG,
                "--pattern", ASSET_NAME,
                "--dir", str(temp_dir),
            ],
            check=False,
            timeout=1200,
        )
        require(r["returncode"] == 0,
                "Release asset download failed:\n" + r["output"])

        path = temp_dir / ASSET_NAME
        require(path.is_file(), "downloaded Portable EXE missing")
        require(path.stat().st_size > 0, "downloaded Portable EXE is empty")

        return {
            "asset_name": ASSET_NAME,
            "size_bytes": path.stat().st_size,
            "sha256": sha256_path(path),
        }
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def final_guard(tag_workflow, release_verified, asset_hash):
    require(git_text("rev-parse", "HEAD") == FINAL_COMMIT,
            "final HEAD changed")
    require(remote_main_sha() == FINAL_COMMIT,
            "final origin/main changed")
    require(not git_lines("diff", "--name-only"),
            "final worktree not clean")
    require(not git_lines("diff", "--cached", "--name-only"),
            "final staging not empty")

    require(local_tag_commit(TAG) == FINAL_COMMIT,
            "final local release tag mismatch")
    require(remote_tag_commit(TAG) == FINAL_COMMIT,
            "final remote release tag mismatch")

    require(
        (tag_workflow.get("run") or {}).get("conclusion") == "success",
        "final tag workflow not successful",
    )
    require(release_verified.get("tagName") == TAG,
            "final Release mismatch")
    require(asset_hash.get("sha256"),
            "final EXE SHA missing")

    immutable = verify_immutable_tags()

    return {
        "head": FINAL_COMMIT,
        "origin_main": FINAL_COMMIT,
        "tag": TAG,
        "tag_commit": FINAL_COMMIT,
        "worktree_clean": True,
        "staging_empty": True,
        "tag_workflow_success": True,
        "release_present": True,
        "asset_present": True,
        "immutable_previous_tags": immutable,
    }


def write_report(payload):
    REPORT_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    tag_run = ((payload.get("tag_workflow") or {}).get("run") or {})

    lines = [
        "KDRG V4.7 Electron Stage67J / 0.5.15 Final Tag + Release Verification R1",
        "=" * 106,
        f"status={payload['status']}",
        f"readiness={payload['readiness']}",
        "",
        "[PREFLIGHT]",
        json.dumps(payload.get("preflight", {}), ensure_ascii=False, indent=2),
        "",
        "[TAG]",
        json.dumps(payload.get("tag", {}), ensure_ascii=False, indent=2),
        "",
        "[TAG WORKFLOW]",
        json.dumps({
            "databaseId": tag_run.get("databaseId"),
            "headSha": tag_run.get("headSha"),
            "headBranch": tag_run.get("headBranch"),
            "event": tag_run.get("event"),
            "status": tag_run.get("status"),
            "conclusion": tag_run.get("conclusion"),
            "url": tag_run.get("url"),
            "failed_steps":
                (payload.get("tag_workflow") or {}).get("failed_steps"),
            "error_focus":
                (payload.get("tag_workflow") or {}).get("error_focus"),
        }, ensure_ascii=False, indent=2),
        "",
        "[RELEASE]",
        json.dumps(payload.get("release", {}), ensure_ascii=False, indent=2),
        "",
        "[PORTABLE EXE]",
        json.dumps(payload.get("asset_hash", {}), ensure_ascii=False, indent=2),
        "",
        "[FINAL GUARD]",
        json.dumps(payload.get("final_guard", {}), ensure_ascii=False, indent=2),
        "",
    ]

    if payload.get("error"):
        lines += ["[BLOCKER]", payload["error"].splitlines()[0], ""]

    lines += [
        "[FINAL]",
        "- PASS이면 electron-v0.5.15 tag / GitHub Release / Portable EXE 검증 완료.",
        "- 기존 0.5.12 / 0.5.13 / 0.5.14 tag는 변경하지 않음.",
        f"report_json={REPORT_JSON}",
    ]

    REPORT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    payload = {
        "status": "FAIL",
        "readiness": "NOT_RELEASED_0515_FINAL",
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "gate": {},
        "preflight": {},
        "tag_pattern": {},
        "tag": {},
        "tag_workflow_pattern": {},
        "tag_workflow": {},
        "release": {},
        "asset_hash": {},
        "final_guard": {},
        "error": None,
    }

    try:
        payload["gate"] = load_gate()
        payload["preflight"] = preflight()

        payload["tag_pattern"] = previous_tag_pattern()
        payload["tag_workflow_pattern"] = prior_tag_workflow_pattern()

        payload["tag"] = create_or_reuse_tag(payload["tag_pattern"])

        tag_run_row = wait_for_tag_run(
            payload["tag_workflow_pattern"],
            timeout=180,
        )
        payload["tag_workflow"] = watch_tag_run(
            tag_run_row,
            payload["tag_workflow_pattern"],
        )

        if not payload["tag_workflow"]["success"]:
            raise StageError(
                "tag-triggered workflow conclusion is not success: "
                + str(
                    (payload["tag_workflow"].get("run") or {}).get("conclusion")
                )
            )

        release = wait_release(timeout=300)
        payload["release"] = verify_release(release)
        payload["asset_hash"] = download_asset_and_hash()

        payload["final_guard"] = final_guard(
            payload["tag_workflow"],
            payload["release"],
            payload["asset_hash"],
        )

        payload["status"] = "PASS"
        payload["readiness"] = "RELEASE_0515_FINAL"

    except Exception as exc:
        payload["error"] = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"

    payload["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    write_report(payload)

    if payload["status"] == "PASS":
        tag_run = payload["tag_workflow"]["run"]

        print("[PASS] Stage67J / 0.5.15 Final Tag + Release Verification R1")
        print("readiness=RELEASE_0515_FINAL")
        print(f"[PASS] tag={TAG} commit={FINAL_COMMIT}")
        print(
            f"[PASS] tag workflow run={tag_run.get('databaseId')} "
            f"conclusion={tag_run.get('conclusion')}"
        )
        print(f"[PASS] Release={TAG}")
        print(
            f"[PASS] EXE={payload['asset_hash']['asset_name']} "
            f"size={payload['asset_hash']['size_bytes']}"
        )
        print(f"[PASS] EXE_SHA256={payload['asset_hash']['sha256']}")
        print("[PASS] 0.5.12 / 0.5.13 / 0.5.14 immutable")
        print(f"report_txt={REPORT_TXT}")
        return 0

    print("[FAIL] Stage67J / 0.5.15 Final Tag + Release Verification R1")
    print("readiness=NOT_RELEASED_0515_FINAL")

    tag_run = (payload.get("tag_workflow") or {}).get("run") or {}
    if tag_run.get("databaseId"):
        print(
            f"[TAG WORKFLOW] run={tag_run.get('databaseId')} "
            f"conclusion={tag_run.get('conclusion')}"
        )

    for row in (payload.get("tag_workflow") or {}).get("failed_steps") or []:
        print(
            "[FAIL STEP] "
            f"job={row.get('job')} "
            f"step={row.get('step_number')} "
            f"name={row.get('step_name')}"
        )

    focus = (payload.get("tag_workflow") or {}).get("error_focus") or []
    if focus:
        print("[ERROR FOCUS]")
        for line in focus[-20:]:
            print(line)

    if payload.get("error"):
        print("[BLOCKER] " + payload["error"].splitlines()[0])

    print("[STOP] existing tag/release is never moved/deleted/repointed")
    print(f"report_txt={REPORT_TXT}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
