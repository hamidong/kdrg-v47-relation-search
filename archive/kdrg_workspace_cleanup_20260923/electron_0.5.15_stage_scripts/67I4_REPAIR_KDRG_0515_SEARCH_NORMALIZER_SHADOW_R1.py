#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KDRG V4.7 Electron Stage67I4 / 0.5.15 Search Normalizer Repair Shadow R1

Confirmed diagnosis
-------------------
Second 0.5.15 RC:
  packaged_ui_validation
  B018 result ready timeout: 30000ms

Read-only path diagnosis:
  fixture query B018 / ADRG filter / ADRG selector = OK
  direct service search B018 + ADRG = OK
  normalizeSearchRequest = ADRG dropped

Therefore the remaining failure is before service.search:
the public request normalizer still carries the old AADRG-era allow-list.

This stage:
- creates a detached Shadow from the CURRENT pushed fix commit
- repairs normalizeSearchRequest generically to use SEARCH_ENTITY_TYPES
- adds permanent regression checks to validate-stage59b-search.js
- verifies normalized request -> service.search -> ADRG B018 exact result
- reruns full 0.5.15 source validations
- leaves Actual completely untouched

No Actual apply / commit / push / RC / tag / release.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import traceback
import hashlib


ROOT = Path.cwd().resolve()
ELECTRON = ROOT / "electron"

DIAG_R3 = ROOT / "stage67i3d_0515_b018_renderer_path_diagnosis_r3.json"

REPORT_TXT = ROOT / "stage67i4_0515_search_normalizer_shadow_r1.txt"
REPORT_JSON = ROOT / "stage67i4_0515_search_normalizer_shadow_r1.json"
MANIFEST_JSON = ROOT / "stage67i4_0515_search_normalizer_apply_manifest_r1.json"

BASE_0514_COMMIT = "4b79e02e8a45a8cabc88b63bc373d95cc21b6d9c"
BASE_TAG = "electron-v0.5.14"
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

TARGETS = [
    "electron/src/search-result-contract.js",
    "electron/tests/validate-stage59b-search.js",
]

ROOT_VALIDATORS = [
    "50B_validate_kdrg_electron_search_service.py",
    "50C_validate_kdrg_electron_renderer_ui.py",
    "50D_validate_kdrg_electron_windows_packaging.py",
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


def read_preserved(path):
    return Path(path).read_bytes().decode("utf-8")


def write_preserved(path, text):
    Path(path).write_bytes(text.encode("utf-8"))


def load_gate():
    require(DIAG_R3.is_file(), "Stage67I3D R3 diagnosis JSON missing")
    data = json.loads(DIAG_R3.read_text(encoding="utf-8"))

    require(data.get("status") == "PASS", "Stage67I3D R3 is not PASS")

    gate = data.get("gate") or {}
    fixture = data.get("fixture") or {}
    service = data.get("service") or {}
    classification = data.get("classification") or {}
    signals = set(classification.get("signals") or [])

    commit = gate.get("fix_commit")
    require(commit, "diagnosed fix commit missing")
    require(
        gate.get("error_message") == "B018 result ready timeout: 30000ms",
        "diagnosed RC error changed",
    )
    require(fixture.get("b018_search_query") == "B018", "B018 fixture query mismatch")
    require(fixture.get("filter_adrg") is True, "packaged ADRG filter missing")
    require(fixture.get("result_selector_adrg") is True, "packaged ADRG selector missing")
    require(bool(service.get("exact_b018")), "direct service B018 is not exact")
    require(
        "NORMALIZE_REQUEST_DROPS_ADRG" in signals,
        "normalizer root-cause signal missing",
    )

    return {
        "fix_commit": commit,
        "run_id": gate.get("run_id"),
        "signals": sorted(signals),
    }


def preflight(gate):
    commit = gate["fix_commit"]

    require(git_text("rev-parse", "HEAD") == commit, "HEAD mismatch")
    require(remote_main_sha() == commit, "origin/main mismatch")
    require(git_text("branch", "--show-current") == "main", "branch mismatch")
    require(not git_lines("diff", "--name-only"), "tracked worktree not clean")
    require(not git_lines("diff", "--cached", "--name-only"), "staging not empty")

    require(local_tag_sha(BASE_TAG) == BASE_0514_COMMIT, "0.5.14 local tag mismatch")
    require(remote_tag_sha(BASE_TAG) == BASE_0514_COMMIT, "0.5.14 remote tag mismatch")
    require(not local_tag_sha(RELEASE_TAG), "0.5.15 local tag already exists")
    require(not remote_tag_sha(RELEASE_TAG), "0.5.15 remote tag already exists")
    require(not release_exists(RELEASE_TAG), "0.5.15 GitHub Release already exists")

    require(sha256_path(ROOT / RUNTIME_REL) == RUNTIME_SHA, "runtime SHA mismatch")
    require(sha256_path(ROOT / OFFICIAL_REL) == OFFICIAL_SHA,
            "official-condition SHA mismatch")
    require(sha256_path(ROOT / ICON_PNG_REL) == ICON_PNG_SHA,
            "PNG icon SHA mismatch")
    require(sha256_path(ROOT / ICON_ICO_REL) == ICON_ICO_SHA,
            "ICO icon SHA mismatch")

    package = json.loads((ELECTRON / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((ELECTRON / "package-lock.json").read_text(encoding="utf-8"))
    require(package.get("version") == VERSION, "package version mismatch")
    require(lock.get("version") == VERSION, "package-lock version mismatch")

    before_sha = {}
    for rel in TARGETS:
        path = ROOT / rel
        require(path.is_file(), f"target missing: {rel}")
        before_sha[rel] = sha256_path(path)

    return {
        "head": commit,
        "origin_main": commit,
        "branch": "main",
        "before_sha256": before_sha,
        "release_tag_absent": True,
        "release_absent": True,
        "runtime_unchanged": True,
    }


def extract_function_span(text, function_name):
    token = f"function {function_name}("
    start = text.find(token)
    require(start >= 0, f"{function_name} function not found")

    brace = text.find("{", start)
    require(brace >= 0, f"{function_name} opening brace not found")

    depth = 0
    quote = None
    escape = False
    template_expr_depth = 0

    for i in range(brace, len(text)):
        ch = text[i]

        if quote:
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if quote == "`":
                if ch == "`" and template_expr_depth == 0:
                    quote = None
                continue
            if ch == quote:
                quote = None
            continue

        if ch in ("'", '"', "`"):
            quote = ch
            continue

        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return start, i + 1

    raise StageError(f"{function_name} closing brace not found")


def patch_contract(path):
    text = read_preserved(path)

    require(
        "const SEARCH_ENTITY_TYPES = Object.freeze(['CODE', 'ADRG']);" in text,
        "public SEARCH_ENTITY_TYPES is not CODE/ADRG",
    )

    start, end = extract_function_span(text, "normalizeSearchRequest")
    body = text[start:end]
    before_body = body

    # Find only an old public allow-list used by `.includes(...)`.
    array_pattern = re.compile(
        r"\[(?P<items>(?:\s*['\"][A-Z]+['\"]\s*,?)+)\]\.includes\((?P<expr>[^)]+)\)"
    )

    candidates = []
    for m in array_pattern.finditer(body):
        values = re.findall(r"['\"]([A-Z]+)['\"]", m.group("items"))
        if set(values) == {"ALL", "CODE", "AADRG"} and len(values) == 3:
            candidates.append(m)

    require(
        len(candidates) == 1,
        f"old normalizeSearchRequest allow-list expected 1, found {len(candidates)}",
    )

    m = candidates[0]
    replacement = f"['ALL', ...SEARCH_ENTITY_TYPES].includes({m.group('expr')})"
    body = body[:m.start()] + replacement + body[m.end():]

    require(body != before_body, "normalizer body did not change")
    require(
        "['ALL', ...SEARCH_ENTITY_TYPES].includes(" in body,
        "SEARCH_ENTITY_TYPES normalizer repair missing",
    )

    text = text[:start] + body + text[end:]
    write_preserved(path, text)

    return {
        "repair": "legacy ALL/CODE/AADRG allow-list -> ALL + SEARCH_ENTITY_TYPES",
        "old_allowlist_count": 1,
        "uses_public_search_entity_types": True,
    }


def patch_search_validator(path):
    text = read_preserved(path)
    marker = "normalizeSearchRequest ADRG bridge"
    require(marker not in text, "normalizer bridge validator already present")

    newline = "\r\n" if "\r\n" in text else "\n"

    addition = newline.join([
        "",
        "// Stage67I4: packaged renderer request must preserve public ADRG filter.",
        f"check('{marker}', () => {{",
        "  const { normalizeSearchRequest } = require('../src/search-result-contract');",
        "  const normalized = normalizeSearchRequest({",
        "    query: 'B018',",
        "    entityType: 'ADRG',",
        "    limit: 100,",
        "    offset: 0,",
        "  });",
        "  assert.equal(normalized.entityType, 'ADRG');",
        "  const response = service.search(",
        "    normalized.query,",
        "    normalized.entityType,",
        "    {",
        "      limit: normalized.limit,",
        "      offset: normalized.offset,",
        "      mdc: normalized.mdc,",
        "      classification: normalized.classification,",
        "    },",
        "  );",
        "  assert.ok(response.results.some(",
        "    (row) => row.entity_type === 'ADRG' && row.entity_id === 'B018',",
        "  ));",
        "});",
        "",
        "check('normalizeSearchRequest public type guards', () => {",
        "  const { normalizeSearchRequest } = require('../src/search-result-contract');",
        "  assert.equal(normalizeSearchRequest({ query: 'X', entityType: 'CODE' }).entityType, 'CODE');",
        "  assert.equal(normalizeSearchRequest({ query: 'X', entityType: 'ADRG' }).entityType, 'ADRG');",
        "  assert.equal(normalizeSearchRequest({ query: 'X', entityType: 'ALL' }).entityType, 'ALL');",
        "  assert.equal(normalizeSearchRequest({ query: 'X', entityType: 'AADRG' }).entityType, 'ALL');",
        "  assert.equal(normalizeSearchRequest({ query: 'X', entityType: 'INVALID' }).entityType, 'ALL');",
        "});",
        "",
    ])

    if text.endswith("\r\n") or text.endswith("\n"):
        text = text.rstrip("\r\n") + newline + addition
    else:
        text = text + newline + addition

    write_preserved(path, text)

    final = read_preserved(path)
    require(final.count(marker) == 1, "validator marker insertion mismatch")
    return {
        "bridge_check_added": True,
        "public_type_guard_added": True,
    }


def create_shadow(commit):
    shadow = Path(tempfile.mkdtemp(prefix="kdrg_stage67i4_shadow_"))
    shutil.rmtree(shadow)

    r = run(
        ["git", "worktree", "add", "--detach", str(shadow), commit],
        check=False,
        timeout=600,
    )
    require(r["returncode"] == 0, "git worktree add failed:\n" + r["output"])
    return shadow


def normalized_bridge_probe(tree):
    js = r"""
'use strict';
const path = require('node:path');
const {
  normalizeSearchRequest,
  SEARCH_ENTITY_TYPES,
} = require('./src/search-result-contract');
const { KdrgSearchService } = require('./src/kdrg-search-service');

const service = new KdrgSearchService(
  path.resolve('..','data','kdrg_v47_search_integrated_v3.json')
);

const normalized = normalizeSearchRequest({
  query:'B018',
  entityType:'ADRG',
  limit:100,
  offset:0
});

const response = service.search(
  normalized.query,
  normalized.entityType,
  {
    limit: normalized.limit,
    offset: normalized.offset,
    mdc: normalized.mdc,
    classification: normalized.classification
  }
);

const exact = (response.results || []).filter(
  x => x.entity_type === 'ADRG' && x.entity_id === 'B018'
);

console.log(JSON.stringify({
  public_types: SEARCH_ENTITY_TYPES,
  normalized_entity_type: normalized.entityType,
  total_count: response.total_count,
  exact_count: exact.length,
  first_results:(response.results || []).slice(0,5).map(
    x => `${x.entity_type}:${x.entity_id}`
  ),
  guards:{
    CODE: normalizeSearchRequest({query:'X',entityType:'CODE'}).entityType,
    ADRG: normalizeSearchRequest({query:'X',entityType:'ADRG'}).entityType,
    ALL: normalizeSearchRequest({query:'X',entityType:'ALL'}).entityType,
    AADRG: normalizeSearchRequest({query:'X',entityType:'AADRG'}).entityType,
    INVALID: normalizeSearchRequest({query:'X',entityType:'INVALID'}).entityType
  }
}));
"""
    r = run(["node", "-e", js], cwd=tree / "electron", check=False, timeout=600)
    require(r["returncode"] == 0, "normalized bridge probe failed:\n" + r["output"])
    data = json.loads(r["output"].strip().splitlines()[-1])

    require(data.get("public_types") == ["CODE", "ADRG"], "public type list mismatch")
    require(data.get("normalized_entity_type") == "ADRG",
            "normalizeSearchRequest still drops ADRG")
    require(data.get("exact_count", 0) >= 1,
            "normalized request does not reach exact ADRG B018")
    require(
        data.get("guards") == {
            "CODE": "CODE",
            "ADRG": "ADRG",
            "ALL": "ALL",
            "AADRG": "ALL",
            "INVALID": "ALL",
        },
        "normalizer public type guards mismatch",
    )
    return data


def namespace_audit(tree):
    js = r"""
'use strict';
const path = require('node:path');
const { KdrgSearchService } = require('./src/kdrg-search-service');

const service = new KdrgSearchService(
  path.resolve('..','data','kdrg_v47_search_integrated_v3.json')
);

const ids = [...service.recordMaps.ADRG.keys()].map(String).sort();
const codeIds = new Set([...service.recordMaps.CODE.keys()].map(String));
const collisions = ids.filter(x => codeIds.has(x));
let failures = 0;
let noncollision = 0;

for (const id of ids) {
  const r = service.search(id,'ADRG',{limit:500,offset:0});
  const ok = (r.results || []).some(
    x => x.entity_type === 'ADRG' && x.entity_id === id
  );
  if (!ok) {
    failures++;
    if (!codeIds.has(id)) noncollision++;
  }
}

console.log(JSON.stringify({
  adrg_count:ids.length,
  collision_count:collisions.length,
  failure_count:failures,
  noncollision_failure_count:noncollision
}));
"""
    r = run(["node", "-e", js], cwd=tree / "electron", check=False, timeout=1800)
    require(r["returncode"] == 0, "ADRG namespace audit failed:\n" + r["output"])
    data = json.loads(r["output"].strip().splitlines()[-1])
    require(data == {
        "adrg_count": 1132,
        "collision_count": 471,
        "failure_count": 0,
        "noncollision_failure_count": 0,
    }, "ADRG namespace audit mismatch")
    return data


def official_regression(tree):
    js = r"""
'use strict';
const path = require('node:path');
const official = require('./renderer/official-condition-text.js');
const { KdrgSearchService } = require('./src/kdrg-search-service');

const service = new KdrgSearchService(
  path.resolve('..','data','kdrg_v47_search_integrated_v3.json')
);

const p651 = official.byAdrg?.P651?.text || '';
if (!p651.includes('시술명 table2을 제외한 OR procedure')) {
  throw new Error('P651 official wording regression');
}

const f022 = official.byAdrg?.F022;
if (!f022
  || f022.source_kind !== 'OFFICIAL_CORRECTION_20260731'
  || f022.text !== '(시술명 table2 and 시술명 table 3) or 시술명 table6') {
  throw new Error('F022 official correction regression');
}

const f2120 = service.getDetail('AADRG','F2120')?.detail;
if (!f2120 || f2120.adrg !== 'F212') {
  throw new Error('internal F2120 AADRG regression');
}

console.log('[PASS] official-source + internal AADRG regression');
"""
    r = run(["node", "-e", js], cwd=tree / "electron", check=False, timeout=600)
    require(r["returncode"] == 0, "official regression failed:\n" + r["output"])


def validate_shadow(shadow):
    commands = []

    def check(cmd, cwd=None, timeout=1800):
        r = run(cmd, cwd=cwd or shadow, check=False, timeout=timeout)
        commands.append(r)
        require(
            r["returncode"] == 0,
            f"validation failed: {' '.join(cmd)}\n{r['output']}",
        )

    for rel in TARGETS:
        check(["node", "--check", str(Path(rel).relative_to("electron"))],
              cwd=shadow / "electron")

    bridge = normalized_bridge_probe(shadow)
    namespace = namespace_audit(shadow)

    check(["node", "tests/validate-stage59b-search.js"], cwd=shadow / "electron")
    check(["node", "tests/validate-packaged-runtime-smoke.js"], cwd=shadow / "electron")
    check(
        ["node", "tests/validate-stage60c-packaged-relation-smoke.js"],
        cwd=shadow / "electron",
    )
    check(["node", "tests/validate-stage59b-ui.js"], cwd=shadow / "electron")
    check(["node", "tests/validate-stage59b-smoke.js"], cwd=shadow / "electron")
    check(["npm", "run", "check"], cwd=shadow / "electron", timeout=1800)

    for rel in ROOT_VALIDATORS:
        check(["python", rel], cwd=shadow, timeout=1800)

    check(
        ["node", "tests/validate-release-version.js", VERSION],
        cwd=shadow / "electron",
        timeout=600,
    )

    official_regression(shadow)

    require(sha256_path(shadow / RUNTIME_REL) == RUNTIME_SHA, "Shadow runtime changed")
    require(sha256_path(shadow / OFFICIAL_REL) == OFFICIAL_SHA,
            "Shadow official-condition changed")
    require(sha256_path(shadow / ICON_PNG_REL) == ICON_PNG_SHA,
            "Shadow PNG icon changed")
    require(sha256_path(shadow / ICON_ICO_REL) == ICON_ICO_SHA,
            "Shadow ICO icon changed")

    changed = sorted(git_lines("diff", "--name-only", cwd=shadow))
    require(changed == sorted(TARGETS),
            "Shadow delta is not exact 2-file normalizer repair")

    diff_check = run(["git", "diff", "--check"], cwd=shadow, check=False)
    require(diff_check["returncode"] == 0,
            "Shadow git diff --check failed:\n" + diff_check["output"])

    return {
        "bridge": bridge,
        "namespace": namespace,
        "npm_run_check": "PASS",
        "root_50b_50c_50d": "PASS",
        "release_version": "PASS",
        "official_regression": "PASS",
        "tracked_diff_files": changed,
        "git_diff_check": "PASS",
        "commands": commands,
    }


def actual_guard(commit, before_sha):
    require(git_text("rev-parse", "HEAD") == commit, "Actual HEAD changed")
    require(remote_main_sha() == commit, "Actual origin/main changed")
    require(not git_lines("diff", "--name-only"), "Actual worktree changed")
    require(not git_lines("diff", "--cached", "--name-only"), "Actual staging changed")

    for rel, expected in before_sha.items():
        require(sha256_path(ROOT / rel) == expected,
                f"Actual target changed during Shadow: {rel}")

    require(sha256_path(ROOT / RUNTIME_REL) == RUNTIME_SHA, "Actual runtime changed")
    require(not local_tag_sha(RELEASE_TAG), "0.5.15 local tag appeared")
    require(not remote_tag_sha(RELEASE_TAG), "0.5.15 remote tag appeared")
    require(not release_exists(RELEASE_TAG), "0.5.15 Release appeared")

    return {
        "head": commit,
        "origin_main": commit,
        "worktree_clean": True,
        "staging_empty": True,
        "targets_unchanged": True,
        "runtime_unchanged": True,
        "release_tag_absent": True,
        "release_absent": True,
    }


def cleanup_shadow(shadow):
    if not shadow:
        return
    run(
        ["git", "worktree", "remove", "--force", str(shadow)],
        check=False,
        timeout=600,
    )


def write_report(payload):
    REPORT_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    validation = payload.get("validation") or {}
    bridge = validation.get("bridge") or {}
    namespace = validation.get("namespace") or {}

    lines = [
        "KDRG V4.7 Electron Stage67I4 / 0.5.15 Search Normalizer Repair Shadow R1",
        "=" * 100,
        f"status={payload['status']}",
        f"readiness={payload['readiness']}",
        "",
        "[PREFLIGHT]",
        json.dumps(payload.get("preflight", {}), ensure_ascii=False, indent=2),
        "",
        "[REPAIR]",
        json.dumps(payload.get("repair", {}), ensure_ascii=False, indent=2),
        "",
        "[VALIDATION SUMMARY]",
        json.dumps({
            "normalized_entity_type": bridge.get("normalized_entity_type"),
            "bridge_exact_count": bridge.get("exact_count"),
            "normalizer_guards": bridge.get("guards"),
            "adrg_count": namespace.get("adrg_count"),
            "collision_count": namespace.get("collision_count"),
            "failure_count": namespace.get("failure_count"),
            "npm_run_check": validation.get("npm_run_check"),
            "root_50b_50c_50d": validation.get("root_50b_50c_50d"),
            "release_version": validation.get("release_version"),
            "git_diff_check": validation.get("git_diff_check"),
        }, ensure_ascii=False, indent=2),
        "",
        "[ACTUAL GUARD]",
        json.dumps(payload.get("actual_guard", {}), ensure_ascii=False, indent=2),
        "",
    ]

    if payload.get("error"):
        lines += ["[BLOCKER]", payload["error"].splitlines()[0], ""]

    lines += [
        "[NEXT]",
        "- PASS이면 normalizeSearchRequest의 ADRG 전달 오류가 Shadow에서 일반화 수정됨.",
        "- 다음 Stage67I5에서 manifest의 정확한 2개만 Actual 적용 후 전체검증.",
        "- Actual PASS 후 새 fix commit을 추가하고 그 새 commit으로 RC를 다시 실행.",
        "- RC success 전 electron-v0.5.15 tag/release 금지.",
        "",
        f"manifest={MANIFEST_JSON}",
        f"report_json={REPORT_JSON}",
    ]
    REPORT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    payload = {
        "status": "FAIL",
        "readiness": "NOT_READY_FOR_0515_NORMALIZER_ACTUAL_APPLY",
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "gate": {},
        "preflight": {},
        "repair": {},
        "validation": {},
        "actual_guard": {},
        "error": None,
    }

    shadow = None

    try:
        payload["gate"] = load_gate()
        payload["preflight"] = preflight(payload["gate"])

        commit = payload["gate"]["fix_commit"]
        shadow = create_shadow(commit)

        contract_repair = patch_contract(
            shadow / "electron/src/search-result-contract.js"
        )
        validator_repair = patch_search_validator(
            shadow / "electron/tests/validate-stage59b-search.js"
        )

        payload["repair"] = {
            "contract": contract_repair,
            "validator": validator_repair,
            "target_files": TARGETS,
        }

        payload["validation"] = validate_shadow(shadow)
        payload["actual_guard"] = actual_guard(
            commit,
            payload["preflight"]["before_sha256"],
        )

        manifest = {
            "schema_version": "kdrg-0515-search-normalizer-repair-v1",
            "status": "PASS",
            "readiness": "READY_FOR_0515_NORMALIZER_ACTUAL_APPLY",
            "base_commit": commit,
            "target_version": VERSION,
            "apply_file_count": 2,
            "repair_contract": {
                "normalize_adrg_preserved": True,
                "normalize_aadrg_public_rejected_to_all": True,
                "b018_normalized_bridge_exact": True,
                "all_1132_adrg_exact_ids_pass": True,
            },
            "apply_files": [],
        }

        for rel in TARGETS:
            source = shadow / rel
            manifest["apply_files"].append({
                "path": rel,
                "source": str(source),
                "actual_before_sha256":
                    payload["preflight"]["before_sha256"][rel],
                "shadow_apply_sha256": sha256_path(source),
            })

        MANIFEST_JSON.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        payload["status"] = "PASS"
        payload["readiness"] = "READY_FOR_0515_NORMALIZER_ACTUAL_APPLY"

        # Keep Shadow because the manifest points to its exact files.
        shadow = None

    except Exception as exc:
        payload["error"] = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"

    finally:
        if shadow is not None:
            cleanup_shadow(shadow)

    payload["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    write_report(payload)

    if payload["status"] == "PASS":
        b = payload["validation"]["bridge"]
        n = payload["validation"]["namespace"]
        print("[PASS] Stage67I4 / 0.5.15 Search Normalizer Repair Shadow R1")
        print("readiness=READY_FOR_0515_NORMALIZER_ACTUAL_APPLY")
        print(
            f"[PASS] normalize ADRG -> {b['normalized_entity_type']} / "
            f"B018 exact={b['exact_count']}"
        )
        print(
            f"[PASS] ADRG audit={n['adrg_count']} / "
            f"collisions={n['collision_count']} / failures={n['failure_count']}"
        )
        print("[PASS] exact Shadow delta=2 files")
        print("[PASS] npm run check + 50B/50C/50D + release-version")
        print("[PASS] Actual untouched / 0.5.15 tag+release absent")
        print("[STOP] no Actual apply/commit/push/RC/tag/release")
        print(f"report_txt={REPORT_TXT}")
        print(f"manifest={MANIFEST_JSON}")
        return 0

    print("[FAIL] Stage67I4 / 0.5.15 Search Normalizer Repair Shadow R1")
    print("readiness=NOT_READY_FOR_0515_NORMALIZER_ACTUAL_APPLY")
    if payload.get("error"):
        print("[BLOCKER] " + payload["error"].splitlines()[0])
    print("[STOP] no Actual apply/commit/push/RC/tag/release")
    print(f"report_txt={REPORT_TXT}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
