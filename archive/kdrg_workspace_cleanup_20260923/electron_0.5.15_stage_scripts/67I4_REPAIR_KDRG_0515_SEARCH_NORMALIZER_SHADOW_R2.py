#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KDRG V4.7 Electron Stage67I4 / 0.5.15 Search Normalizer Repair Shadow R2

R1 safe-failed because it assumed the stale normalizer used an array `.includes`
expression. The actual normalizeSearchRequest() uses a different source shape.

R2 does not assume that syntax. It first proves the current runtime behavior:
  CODE -> CODE
  ADRG -> NOT ADRG
  AADRG -> legacy public value or fallback
Then it inspects only normalizeSearchRequest() and replaces the stale public
'AADRG' string literal with 'ADRG' when that stale literal is uniquely
identifiable inside the function.

After patch:
  CODE -> CODE
  ADRG -> ADRG
  ALL  -> ALL
  AADRG -> ALL
  INVALID -> ALL

Then it verifies:
  normalizeSearchRequest(B018, ADRG)
  -> service.search(...)
  -> exact ADRG B018

and reruns the full source validation set.

Shadow only. No Actual apply / commit / push / RC / tag / release.
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

DIAG_R3 = ROOT / "stage67i3d_0515_b018_renderer_path_diagnosis_r3.json"

REPORT_TXT = ROOT / "stage67i4_0515_search_normalizer_shadow_r2.txt"
REPORT_JSON = ROOT / "stage67i4_0515_search_normalizer_shadow_r2.json"
MANIFEST_JSON = ROOT / "stage67i4_0515_search_normalizer_apply_manifest_r2.json"

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
        line
        for line in run(["git", *args], cwd=cwd)["output"].splitlines()
        if line
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
    require(DIAG_R3.is_file(), "Stage67I3D R3 diagnosis JSON missing")
    data = json.loads(DIAG_R3.read_text(encoding="utf-8"))
    require(data.get("status") == "PASS", "Stage67I3D R3 is not PASS")

    gate = data.get("gate") or {}
    fixture = data.get("fixture") or {}
    service = data.get("service") or {}
    signals = set((data.get("classification") or {}).get("signals") or [])

    commit = gate.get("fix_commit")
    require(commit, "diagnosed fix commit missing")
    require(
        gate.get("error_message") == "B018 result ready timeout: 30000ms",
        "diagnosed RC error mismatch",
    )
    require(fixture.get("b018_search_query") == "B018", "B018 fixture query mismatch")
    require(fixture.get("filter_adrg") is True, "packaged ADRG filter missing")
    require(fixture.get("result_selector_adrg") is True, "packaged ADRG selector missing")
    require(bool(service.get("exact_b018")), "direct service B018 exact result missing")
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
        require((ROOT / rel).is_file(), f"target missing: {rel}")
        before_sha[rel] = sha256_path(ROOT / rel)

    return {
        "head": commit,
        "origin_main": commit,
        "before_sha256": before_sha,
        "release_tag_absent": True,
        "release_absent": True,
    }


def extract_function_span(text, name):
    token = f"function {name}("
    start = text.find(token)
    require(start >= 0, f"{name} not found")

    brace = text.find("{", start)
    require(brace >= 0, f"{name} opening brace not found")

    depth = 0
    quote = None
    escape = False

    for i in range(brace, len(text)):
        ch = text[i]

        if quote is not None:
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
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

    raise StageError(f"{name} closing brace not found")


def normalizer_probe(tree):
    js = r"""
'use strict';
const {
  normalizeSearchRequest,
  SEARCH_ENTITY_TYPES,
} = require('./src/search-result-contract');

function out(type) {
  const r = normalizeSearchRequest({
    query:'B018',
    entityType:type,
    limit:100,
    offset:0
  });
  return r.entityType;
}

console.log(JSON.stringify({
  public_types: SEARCH_ENTITY_TYPES,
  CODE: out('CODE'),
  ADRG: out('ADRG'),
  ALL: out('ALL'),
  AADRG: out('AADRG'),
  INVALID: out('INVALID')
}));
"""
    r = run(["node", "-e", js], cwd=tree / "electron", check=False, timeout=600)
    require(r["returncode"] == 0, "normalizer probe failed:\n" + r["output"])
    return json.loads(r["output"].strip().splitlines()[-1])


def patch_contract(path, before_probe):
    raw = path.read_bytes()
    text = raw.decode("utf-8")

    require(
        before_probe.get("public_types") == ["CODE", "ADRG"],
        "SEARCH_ENTITY_TYPES is not CODE/ADRG",
    )
    require(before_probe.get("CODE") == "CODE", "CODE normalization already broken")
    require(before_probe.get("ADRG") != "ADRG", "ADRG is already preserved; diagnosis changed")

    start, end = extract_function_span(text, "normalizeSearchRequest")
    body = text[start:end]

    aadrg_literals = list(re.finditer(r"(['\"])AADRG\1", body))
    adrg_literals = list(re.finditer(r"(['\"])ADRG\1", body))

    require(
        len(aadrg_literals) == 1,
        "normalizeSearchRequest stale AADRG literal expected 1, "
        f"found {len(aadrg_literals)}",
    )
    require(
        len(adrg_literals) == 0,
        "normalizeSearchRequest already contains an ADRG literal; "
        "refusing ambiguous patch",
    )

    stale = aadrg_literals[0]
    quote = stale.group(1)
    fixed_body = body[:stale.start()] + f"{quote}ADRG{quote}" + body[stale.end():]

    require(fixed_body != body, "normalizer function did not change")
    require(len(re.findall(r"(['\"])AADRG\1", fixed_body)) == 0,
            "stale AADRG literal remains in normalizer")
    require(len(re.findall(r"(['\"])ADRG\1", fixed_body)) == 1,
            "ADRG literal repair count mismatch")

    new_text = text[:start] + fixed_body + text[end:]
    path.write_bytes(new_text.encode("utf-8"))

    return {
        "strategy": "unique stale public AADRG literal -> ADRG",
        "aadrg_literal_before": 1,
        "adrg_literal_before": 0,
        "aadrg_literal_after": 0,
        "adrg_literal_after": 1,
    }


def patch_validator(path):
    text = path.read_text(encoding="utf-8")
    marker = "Stage67I4 normalizer bridge"
    require(marker not in text, "Stage67I4 validator already present")

    nl = "\r\n" if "\r\n" in text else "\n"
    block = nl.join([
        "",
        f"// {marker}",
        "{",
        "  const assert67I4 = require('node:assert/strict');",
        "  const path67I4 = require('node:path');",
        "  const {",
        "    normalizeSearchRequest: normalizeSearchRequest67I4,",
        "  } = require('../src/search-result-contract');",
        "  const {",
        "    KdrgSearchService: KdrgSearchService67I4,",
        "  } = require('../src/kdrg-search-service');",
        "",
        "  const normalize67I4 = (type) => normalizeSearchRequest67I4({",
        "    query: 'B018',",
        "    entityType: type,",
        "    limit: 100,",
        "    offset: 0,",
        "  });",
        "",
        "  assert67I4.equal(normalize67I4('CODE').entityType, 'CODE');",
        "  assert67I4.equal(normalize67I4('ADRG').entityType, 'ADRG');",
        "  assert67I4.equal(normalize67I4('ALL').entityType, 'ALL');",
        "  assert67I4.equal(normalize67I4('AADRG').entityType, 'ALL');",
        "  assert67I4.equal(normalize67I4('INVALID').entityType, 'ALL');",
        "",
        "  const request67I4 = normalize67I4('ADRG');",
        "  const service67I4 = new KdrgSearchService67I4(",
        "    path67I4.resolve(",
        "      '..',",
        "      'data',",
        "      'kdrg_v47_search_integrated_v3.json',",
        "    ),",
        "  );",
        "  const response67I4 = service67I4.search(",
        "    request67I4.query,",
        "    request67I4.entityType,",
        "    {",
        "      limit: request67I4.limit,",
        "      offset: request67I4.offset,",
        "      mdc: request67I4.mdc,",
        "      classification: request67I4.classification,",
        "    },",
        "  );",
        "  assert67I4.ok(response67I4.results.some(",
        "    (row) => row.entity_type === 'ADRG' && row.entity_id === 'B018',",
        "  ));",
        "  console.log('[PASS] Stage67I4 normalizer bridge ADRG -> B018');",
        "}",
        "",
    ])

    new_text = text.rstrip("\r\n") + nl + block
    path.write_text(new_text, encoding="utf-8", newline="")

    final = path.read_text(encoding="utf-8")
    require(final.count(marker) == 1, "Stage67I4 validator marker mismatch")

    return {
        "normalizer_type_guards": True,
        "normalized_B018_service_bridge": True,
    }


def create_shadow(commit):
    shadow = Path(tempfile.mkdtemp(prefix="kdrg_stage67i4_r2_shadow_"))
    shutil.rmtree(shadow)

    r = run(
        ["git", "worktree", "add", "--detach", str(shadow), commit],
        check=False,
        timeout=600,
    )
    require(r["returncode"] == 0, "git worktree add failed:\n" + r["output"])
    return shadow


def bridge_probe(tree):
    js = r"""
'use strict';
const path = require('node:path');
const {
  normalizeSearchRequest,
} = require('./src/search-result-contract');
const {
  KdrgSearchService,
} = require('./src/kdrg-search-service');

const request = normalizeSearchRequest({
  query:'B018',
  entityType:'ADRG',
  limit:100,
  offset:0
});

const service = new KdrgSearchService(
  path.resolve('..','data','kdrg_v47_search_integrated_v3.json')
);

const response = service.search(
  request.query,
  request.entityType,
  {
    limit:request.limit,
    offset:request.offset,
    mdc:request.mdc,
    classification:request.classification
  }
);

const exact = (response.results || []).filter(
  x => x.entity_type === 'ADRG' && x.entity_id === 'B018'
);

console.log(JSON.stringify({
  normalized_entity_type:request.entityType,
  total_count:response.total_count,
  exact_count:exact.length
}));
"""
    r = run(["node", "-e", js], cwd=tree / "electron", check=False, timeout=600)
    require(r["returncode"] == 0, "B018 bridge probe failed:\n" + r["output"])
    data = json.loads(r["output"].strip().splitlines()[-1])
    require(data.get("normalized_entity_type") == "ADRG",
            "normalized ADRG still not preserved")
    require(data.get("exact_count", 0) >= 1,
            "normalized ADRG request does not return B018")
    return data


def namespace_audit(tree):
    js = r"""
'use strict';
const path = require('node:path');
const { KdrgSearchService } = require('./src/kdrg-search-service');

const s = new KdrgSearchService(
  path.resolve('..','data','kdrg_v47_search_integrated_v3.json')
);

const ids = [...s.recordMaps.ADRG.keys()].map(String).sort();
const codeIds = new Set([...s.recordMaps.CODE.keys()].map(String));
const collisions = ids.filter(x => codeIds.has(x));
let failures = 0;
let noncollision = 0;

for (const id of ids) {
  const r = s.search(id,'ADRG',{limit:500,offset:0});
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
    require(r["returncode"] == 0, "namespace audit failed:\n" + r["output"])
    data = json.loads(r["output"].strip().splitlines()[-1])
    require(data == {
        "adrg_count": 1132,
        "collision_count": 471,
        "failure_count": 0,
        "noncollision_failure_count": 0,
    }, "namespace audit mismatch")
    return data


def official_probe(tree):
    js = r"""
'use strict';
const path = require('node:path');
const official = require('./renderer/official-condition-text.js');
const { KdrgSearchService } = require('./src/kdrg-search-service');

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

const s = new KdrgSearchService(
  path.resolve('..','data','kdrg_v47_search_integrated_v3.json')
);
const f2120 = s.getDetail('AADRG','F2120')?.detail;
if (!f2120 || f2120.adrg !== 'F212') {
  throw new Error('internal AADRG F2120 regression');
}

console.log('[PASS] official source + internal AADRG');
"""
    r = run(["node", "-e", js], cwd=tree / "electron", check=False, timeout=600)
    require(r["returncode"] == 0, "official probe failed:\n" + r["output"])


def validate_shadow(shadow):
    commands = []

    def check(cmd, cwd=None, timeout=1800):
        r = run(cmd, cwd=cwd or shadow, check=False, timeout=timeout)
        commands.append(r)
        require(r["returncode"] == 0,
                f"validation failed: {' '.join(cmd)}\n{r['output']}")

    check(["node", "--check", "src/search-result-contract.js"], cwd=shadow / "electron")
    check(["node", "--check", "tests/validate-stage59b-search.js"], cwd=shadow / "electron")

    after_probe = normalizer_probe(shadow)
    require(after_probe == {
        "public_types": ["CODE", "ADRG"],
        "CODE": "CODE",
        "ADRG": "ADRG",
        "ALL": "ALL",
        "AADRG": "ALL",
        "INVALID": "ALL",
    }, "normalizer post-patch guard mismatch")

    bridge = bridge_probe(shadow)
    namespace = namespace_audit(shadow)

    check(["node", "tests/validate-stage59b-search.js"], cwd=shadow / "electron")
    check(["node", "tests/validate-packaged-runtime-smoke.js"], cwd=shadow / "electron")
    check(["node", "tests/validate-stage60c-packaged-relation-smoke.js"],
          cwd=shadow / "electron")
    check(["node", "tests/validate-stage59b-ui.js"], cwd=shadow / "electron")
    check(["node", "tests/validate-stage59b-smoke.js"], cwd=shadow / "electron")
    check(["npm", "run", "check"], cwd=shadow / "electron", timeout=1800)

    for rel in ROOT_VALIDATORS:
        check(["python", rel], cwd=shadow, timeout=1800)

    check(["node", "tests/validate-release-version.js", VERSION],
          cwd=shadow / "electron", timeout=600)

    official_probe(shadow)

    changed = sorted(git_lines("diff", "--name-only", cwd=shadow))
    require(changed == sorted(TARGETS),
            "Shadow delta is not exact 2-file normalizer repair")

    diff_check = run(["git", "diff", "--check"], cwd=shadow, check=False)
    require(diff_check["returncode"] == 0,
            "Shadow git diff --check failed:\n" + diff_check["output"])

    require(sha256_path(shadow / RUNTIME_REL) == RUNTIME_SHA, "Shadow runtime changed")
    require(sha256_path(shadow / OFFICIAL_REL) == OFFICIAL_SHA,
            "Shadow official-condition changed")
    require(sha256_path(shadow / ICON_PNG_REL) == ICON_PNG_SHA,
            "Shadow PNG icon changed")
    require(sha256_path(shadow / ICON_ICO_REL) == ICON_ICO_SHA,
            "Shadow ICO icon changed")

    return {
        "normalizer_after": after_probe,
        "bridge": bridge,
        "namespace": namespace,
        "npm_run_check": "PASS",
        "root_50b_50c_50d": "PASS",
        "release_version": "PASS",
        "git_diff_check": "PASS",
        "tracked_diff_files": changed,
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

    require(not local_tag_sha(RELEASE_TAG), "0.5.15 local tag appeared")
    require(not remote_tag_sha(RELEASE_TAG), "0.5.15 remote tag appeared")
    require(not release_exists(RELEASE_TAG), "0.5.15 Release appeared")

    return {
        "head": commit,
        "origin_main": commit,
        "worktree_clean": True,
        "staging_empty": True,
        "targets_unchanged": True,
        "release_tag_absent": True,
        "release_absent": True,
    }


def cleanup_shadow(shadow):
    if shadow is None:
        return
    run(["git", "worktree", "remove", "--force", str(shadow)],
        check=False, timeout=600)


def write_report(payload):
    REPORT_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    validation = payload.get("validation") or {}
    ns = validation.get("namespace") or {}
    bridge = validation.get("bridge") or {}

    lines = [
        "KDRG V4.7 Electron Stage67I4 / 0.5.15 Search Normalizer Repair Shadow R2",
        "=" * 100,
        f"status={payload['status']}",
        f"readiness={payload['readiness']}",
        "",
        "[PREFLIGHT]",
        json.dumps(payload.get("preflight", {}), ensure_ascii=False, indent=2),
        "",
        "[NORMALIZER BEFORE]",
        json.dumps(payload.get("normalizer_before", {}), ensure_ascii=False, indent=2),
        "",
        "[REPAIR]",
        json.dumps(payload.get("repair", {}), ensure_ascii=False, indent=2),
        "",
        "[VALIDATION SUMMARY]",
        json.dumps({
            "normalizer_after": validation.get("normalizer_after"),
            "bridge_entity_type": bridge.get("normalized_entity_type"),
            "bridge_exact_count": bridge.get("exact_count"),
            "adrg_count": ns.get("adrg_count"),
            "collision_count": ns.get("collision_count"),
            "failure_count": ns.get("failure_count"),
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
        "- PASS이면 실제 normalizer source shape 기준 ADRG 전달 수정이 Shadow에서 확정.",
        "- 다음 Stage67I5에서 manifest의 정확한 2개만 Actual 적용 후 전체검증.",
        "- 그 다음 새 fix commit/push 후 새 RC.",
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
        "normalizer_before": {},
        "repair": {},
        "validation": {},
        "actual_guard": {},
        "error": None,
    }

    shadow = None

    try:
        payload["gate"] = load_gate()
        payload["preflight"] = preflight(payload["gate"])

        shadow = create_shadow(payload["gate"]["fix_commit"])

        payload["normalizer_before"] = normalizer_probe(shadow)

        payload["repair"] = {
            "contract": patch_contract(
                shadow / "electron/src/search-result-contract.js",
                payload["normalizer_before"],
            ),
            "validator": patch_validator(
                shadow / "electron/tests/validate-stage59b-search.js"
            ),
            "target_files": TARGETS,
        }

        payload["validation"] = validate_shadow(shadow)
        payload["actual_guard"] = actual_guard(
            payload["gate"]["fix_commit"],
            payload["preflight"]["before_sha256"],
        )

        manifest = {
            "schema_version": "kdrg-0515-search-normalizer-repair-v2",
            "status": "PASS",
            "readiness": "READY_FOR_0515_NORMALIZER_ACTUAL_APPLY",
            "base_commit": payload["gate"]["fix_commit"],
            "target_version": VERSION,
            "apply_file_count": 2,
            "repair_contract": {
                "normalize_CODE_preserved": True,
                "normalize_ADRG_preserved": True,
                "normalize_ALL_preserved": True,
                "normalize_AADRG_public_fallback_ALL": True,
                "normalize_INVALID_fallback_ALL": True,
                "B018_normalized_bridge_exact": True,
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

        # Preserve successful Shadow because the apply manifest points to it.
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
        ns = payload["validation"]["namespace"]
        print("[PASS] Stage67I4 / 0.5.15 Search Normalizer Repair Shadow R2")
        print("readiness=READY_FOR_0515_NORMALIZER_ACTUAL_APPLY")
        print(
            f"[PASS] normalize ADRG -> {b['normalized_entity_type']} / "
            f"B018 exact={b['exact_count']}"
        )
        print(
            f"[PASS] ADRG audit={ns['adrg_count']} / "
            f"collisions={ns['collision_count']} / failures={ns['failure_count']}"
        )
        print("[PASS] exact Shadow delta=2 files")
        print("[PASS] npm run check + 50B/50C/50D + release-version")
        print("[PASS] Actual untouched / 0.5.15 tag+release absent")
        print("[STOP] no Actual apply/commit/push/RC/tag/release")
        print(f"report_txt={REPORT_TXT}")
        print(f"manifest={MANIFEST_JSON}")
        return 0

    print("[FAIL] Stage67I4 / 0.5.15 Search Normalizer Repair Shadow R2")
    print("readiness=NOT_READY_FOR_0515_NORMALIZER_ACTUAL_APPLY")
    if payload.get("error"):
        print("[BLOCKER] " + payload["error"].splitlines()[0])
    print("[STOP] no Actual apply/commit/push/RC/tag/release")
    print(f"report_txt={REPORT_TXT}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
