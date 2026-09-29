#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KDRG V4.7 Electron Stage67I4B
0.5.15 Full Search Pipeline Repair Shadow R1

Confirmed by Stage67I4A comprehensive audit
-------------------------------------------
- normalizeSearchRequest definition count: 1
- object ADRG request returns entityType as ['ADRG'] (array, not scalar)
- direct service B018 + ADRG: PASS
- all 1132 ADRG direct exact-id searches: PASS
- 471 ADRG/CODE namespace collisions: service layer PASS
- packaged fixtures/query/filter/selector: PASS
- baseline validators: 10 PASS / 0 FAIL
- remaining RC failure: packaged UI B018 result ready timeout

The remaining mismatch is therefore not "ADRG missing"; it is a request-shape
mismatch between normalizeSearchRequest() and service.search(), whose public
entityType parameter is scalar.

This Shadow stage fixes that contract generically and simultaneously hardens
the next likely failure points:
1) normalizeSearchRequest public entityType becomes scalar:
   CODE -> CODE
   ADRG -> ADRG
   ALL -> ALL
   hidden/invalid type -> ALL
2) validate-stage59b-search gets normalized-request -> service bridge tests.
3) validate-packaged-runtime-smoke gets the same scalar request guard.
4) GitHub Actions packaged failure diagnostics are reordered so status,
   failed_step and message are printed BEFORE Write-Error, preventing another
   opaque RC failure.

Then it validates:
- all 1132 ADRG ids through NORMALIZER -> service, not direct service only
- all 471 namespace collisions preserve CODE and ALL direct-service behavior
- all six packaged ADRG fixtures through normalizer -> service
- current renderer/preload/main static wiring
- npm run check / stage59b / stage60c / packaged contract
- 50B / 50C / 50D / release version
- F022 / P651 / F212
- workflow diagnostic ordering
- runtime / official-condition / icon immutability
- Actual worktree remains untouched

No Actual apply / commit / push / RC / tag / release.
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

AUDIT_R1 = ROOT / "stage67i4a_0515_normalizer_full_pipeline_audit_r1.json"
R3_DIAG = ROOT / "stage67i3d_0515_b018_renderer_path_diagnosis_r3.json"

REPORT_TXT = ROOT / "stage67i4b_0515_full_pipeline_shadow_r1.txt"
REPORT_JSON = ROOT / "stage67i4b_0515_full_pipeline_shadow_r1.json"
MANIFEST_JSON = ROOT / "stage67i4b_0515_full_pipeline_apply_manifest_r1.json"

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

WORKFLOW_REL = ".github/workflows/build-electron-windows.yml"

TARGETS = [
    "electron/src/search-result-contract.js",
    "electron/tests/validate-stage59b-search.js",
    "electron/tests/validate-packaged-runtime-smoke.js",
    WORKFLOW_REL,
]

ROOT_VALIDATORS = [
    "50B_validate_kdrg_electron_search_service.py",
    "50C_validate_kdrg_electron_renderer_ui.py",
    "50D_validate_kdrg_electron_windows_packaging.py",
]

FIXTURES = ["B013", "B014", "B018", "B022", "L033", "9610"]


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


def load_gate():
    require(AUDIT_R1.is_file(), "Stage67I4A audit JSON missing")
    require(R3_DIAG.is_file(), "Stage67I3D R3 diagnosis JSON missing")

    audit = json.loads(AUDIT_R1.read_text(encoding="utf-8"))
    diag = json.loads(R3_DIAG.read_text(encoding="utf-8"))

    require(audit.get("status") == "PASS", "Stage67I4A audit is not PASS")
    require(diag.get("status") == "PASS", "Stage67I3D R3 is not PASS")

    state = audit.get("state") or {}
    service = audit.get("service_probe") or {}
    fixture = audit.get("packaged_fixture") or {}
    baseline = audit.get("baseline") or {}
    locations = audit.get("normalizer_locations") or {}
    classification = audit.get("classification") or {}

    commit = state.get("head")
    require(commit, "audit HEAD missing")
    require(state.get("origin_main") == commit, "audit HEAD/origin mismatch")
    require(locations.get("definition_count") == 1, "normalizer definition not unique")
    require(service.get("b018_exact_count") == 1, "direct service B018 exact mismatch")
    require(service.get("adrg_count") == 1132, "direct ADRG count mismatch")
    require(service.get("collision_count") == 471, "collision count mismatch")
    require(service.get("failure_count") == 0, "direct ADRG failures remain")
    require(fixture.get("all_search_query_equals_adrg") is True,
            "packaged fixture query mismatch")
    require(fixture.get("filter_adrg") is True, "packaged ADRG filter mismatch")
    require(fixture.get("selector_adrg") is True, "packaged ADRG selector mismatch")
    require(baseline.get("fail_count") == 0, "baseline validations are not all PASS")

    diag_gate = diag.get("gate") or {}
    require(diag_gate.get("fix_commit") == commit,
            "R3 diagnosed commit differs from audit HEAD")
    require(
        diag_gate.get("error_message") == "B018 result ready timeout: 30000ms",
        "R3 packaged UI error mismatch",
    )

    return {
        "commit": commit,
        "audit_readiness": classification.get("readiness"),
        "baseline_pass_count": baseline.get("pass_count"),
        "direct_service": {
            "b018_exact_count": service.get("b018_exact_count"),
            "adrg_count": service.get("adrg_count"),
            "collision_count": service.get("collision_count"),
            "failure_count": service.get("failure_count"),
        },
    }


def preflight(gate):
    commit = gate["commit"]

    require(git_text("rev-parse", "HEAD") == commit, "HEAD changed since audit")
    require(remote_main_sha() == commit, "origin/main changed since audit")
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
            "official condition SHA mismatch")
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
        p = ROOT / rel
        require(p.is_file(), f"target missing: {rel}")
        before_sha[rel] = sha256_path(p)

    return {
        "head": commit,
        "origin_main": commit,
        "before_sha256": before_sha,
        "release_tag_absent": True,
        "release_absent": True,
    }


def create_shadow(commit):
    shadow = Path(tempfile.mkdtemp(prefix="kdrg_stage67i4b_shadow_"))
    shutil.rmtree(shadow)

    r = run(
        ["git", "worktree", "add", "--detach", str(shadow), commit],
        check=False,
        timeout=600,
    )
    require(r["returncode"] == 0, "git worktree add failed:\n" + r["output"])
    return shadow


def contract_probe(tree):
    js = r"""
'use strict';
const c = require('./src/search-result-contract');
const fn = c.normalizeSearchRequest;

function safe(type) {
  try {
    const v = fn({query:'B018',entityType:type,limit:100,offset:0});
    return {
      ok:true,
      value:v,
      entityType:v?.entityType,
      entityTypeType:Array.isArray(v?.entityType) ? 'array' : typeof v?.entityType
    };
  } catch (e) {
    return {ok:false,error:String(e && e.message || e)};
  }
}

console.log(JSON.stringify({
  exports:Object.keys(c).sort(),
  public_types:c.SEARCH_ENTITY_TYPES,
  fn_type:typeof fn,
  fn_length:typeof fn === 'function' ? fn.length : null,
  fn_source:typeof fn === 'function' ? String(fn) : null,
  CODE:safe('CODE'),
  ADRG:safe('ADRG'),
  ALL:safe('ALL'),
  AADRG:safe('AADRG'),
  INVALID:safe('INVALID')
}));
"""
    r = run(["node", "-e", js], cwd=tree / "electron", check=False, timeout=600)
    require(r["returncode"] == 0, "contract probe failed:\n" + r["output"])
    return json.loads(r["output"].strip().splitlines()[-1])


def find_unique_definition(text):
    patterns = [
        (
            "function_declaration",
            re.compile(r"\bfunction\s+normalizeSearchRequest\s*\("),
        ),
        (
            "const_assignment",
            re.compile(r"\bconst\s+normalizeSearchRequest\s*="),
        ),
        (
            "let_assignment",
            re.compile(r"\blet\s+normalizeSearchRequest\s*="),
        ),
        (
            "var_assignment",
            re.compile(r"\bvar\s+normalizeSearchRequest\s*="),
        ),
    ]

    hits = []
    for kind, pattern in patterns:
        for m in pattern.finditer(text):
            hits.append((kind, m.start(), m.group(0)))

    require(len(hits) == 1,
            f"normalizeSearchRequest source definition expected 1, found {len(hits)}")
    return hits[0]


def patch_contract(path, before):
    raw = path.read_bytes()
    text = raw.decode("utf-8")

    require(before.get("public_types") == ["CODE", "ADRG"],
            "SEARCH_ENTITY_TYPES != CODE/ADRG")

    adrg_before = ((before.get("ADRG") or {}).get("entityType"))
    require(
        isinstance(adrg_before, list) and adrg_before == ["ADRG"],
        "expected current ADRG entityType array ['ADRG']; source contract changed",
    )

    all_before = ((before.get("ALL") or {}).get("entityType"))
    require(
        isinstance(all_before, list),
        "expected current ALL entityType to be array; source contract changed",
    )

    kind, _, _ = find_unique_definition(text)

    if kind == "function_declaration":
        text2, count = re.subn(
            r"\bfunction\s+normalizeSearchRequest\s*\(",
            "function normalizeSearchRequestLegacy(",
            text,
            count=1,
        )
    else:
        keyword = kind.split("_", 1)[0]
        text2, count = re.subn(
            rf"\b{keyword}\s+normalizeSearchRequest\s*=",
            f"{keyword} normalizeSearchRequestLegacy =",
            text,
            count=1,
        )

    require(count == 1, "failed to rename legacy normalizer")

    export_match = re.search(r"\bmodule\.exports\s*=", text2)
    require(export_match, "module.exports anchor missing")

    nl = "\r\n" if "\r\n" in text2 else "\n"

    wrapper = nl.join([
        "",
        "/* Stage67I4B: public search service requires scalar entityType. */",
        "function normalizeSearchRequest(payload = {}) {",
        "  const normalized = normalizeSearchRequestLegacy(payload);",
        "  const rawType = (payload && typeof payload === 'object' && !Array.isArray(payload))",
        "    ? (payload.entityType ?? payload.entity_type ?? 'ALL')",
        "    : 'ALL';",
        "  const candidate = Array.isArray(rawType)",
        "    ? (rawType.length === 1 ? rawType[0] : 'ALL')",
        "    : rawType;",
        "  const requested = String(candidate ?? 'ALL').trim().toUpperCase() || 'ALL';",
        "  const entityType = requested === 'ALL'",
        "    ? 'ALL'",
        "    : (SEARCH_ENTITY_TYPES.includes(requested) ? requested : 'ALL');",
        "  return { ...normalized, entityType };",
        "}",
        "",
    ])

    text3 = text2[:export_match.start()] + wrapper + text2[export_match.start():]
    path.write_bytes(text3.encode("utf-8"))

    final = path.read_text(encoding="utf-8")
    require(final.count("normalizeSearchRequestLegacy") >= 2,
            "legacy normalizer rename/wrapper link missing")
    require(final.count("function normalizeSearchRequest(payload = {})") == 1,
            "new scalar normalizer wrapper count mismatch")

    return {
        "definition_kind": kind,
        "strategy": "legacy normalizer + scalar public entityType wrapper",
        "before_ADRG_entityType": adrg_before,
        "before_ALL_entityType": all_before,
    }


def append_validator_block(path, marker, packaged=False):
    text = path.read_text(encoding="utf-8")
    require(marker not in text, f"validator marker already exists: {marker}")

    nl = "\r\n" if "\r\n" in text else "\n"
    prefix = "" if text.endswith(("\n", "\r")) else nl

    lines = [
        "",
        f"// {marker}",
        "{",
        "  const assert67I4B = require('node:assert/strict');",
        "  const path67I4B = require('node:path');",
        "  const {",
        "    normalizeSearchRequest: normalizeSearchRequest67I4B,",
        "  } = require('../src/search-result-contract');",
        "  const {",
        "    KdrgSearchService: KdrgSearchService67I4B,",
        "  } = require('../src/kdrg-search-service');",
        "",
        "  const normalize67I4B = (type, query = 'B018') =>",
        "    normalizeSearchRequest67I4B({",
        "      query,",
        "      entityType: type,",
        "      limit: 500,",
        "      offset: 0,",
        "    });",
        "",
        "  assert67I4B.equal(normalize67I4B('CODE').entityType, 'CODE');",
        "  assert67I4B.equal(normalize67I4B('ADRG').entityType, 'ADRG');",
        "  assert67I4B.equal(normalize67I4B('ALL').entityType, 'ALL');",
        "  assert67I4B.equal(normalize67I4B('AADRG').entityType, 'ALL');",
        "  assert67I4B.equal(normalize67I4B('RDRG').entityType, 'ALL');",
        "  assert67I4B.equal(normalize67I4B('TABLE').entityType, 'ALL');",
        "  assert67I4B.equal(normalize67I4B('INVALID').entityType, 'ALL');",
        "",
        "  const service67I4B = new KdrgSearchService67I4B(",
        "    path67I4B.resolve(",
        "      '..',",
        "      'data',",
        "      'kdrg_v47_search_integrated_v3.json',",
        "    ),",
        "  );",
        "  const request67I4B = normalize67I4B('ADRG');",
        "  const response67I4B = service67I4B.search(",
        "    request67I4B.query,",
        "    request67I4B.entityType,",
        "    {",
        "      limit: request67I4B.limit,",
        "      offset: request67I4B.offset,",
        "      mdc: request67I4B.mdc,",
        "      classification: request67I4B.classification,",
        "    },",
        "  );",
        "  assert67I4B.ok(response67I4B.results.some(",
        "    (row) => row.entity_type === 'ADRG' && row.entity_id === 'B018',",
        "  ));",
        f"  console.log('[PASS] {marker}');",
        "}",
        "",
    ]

    if packaged:
        lines.insert(
            -2,
            "  assert67I4B.equal(typeof request67I4B.entityType, 'string');",
        )

    new_text = text.rstrip("\r\n") + nl + nl.join(lines)
    path.write_text(new_text, encoding="utf-8", newline="")

    final = path.read_text(encoding="utf-8")
    require(final.count(marker) == 2,
            f"validator marker count mismatch after insertion: {marker}")

    return {
        "marker": marker,
        "scalar_public_types": True,
        "normalized_B018_bridge": True,
    }


def patch_workflow(path):
    text = path.read_text(encoding="utf-8")

    error_line = 'Write-Error "packaged 핵심검증 실패"'
    status_line = 'Write-Host "status=$($report.status)"'
    failed_line = 'Write-Host "failed_step=$($report.failed_step)"'
    missing_line = 'Write-Host "missing_steps=$($missing -join \',\')"'
    message_line = 'Write-Host "message=$message"'

    require(text.count(error_line) == 1, "workflow packaged failure Write-Error count mismatch")
    require(text.count(status_line) == 1, "workflow status diagnostic count mismatch")
    require(text.count(failed_line) == 1, "workflow failed_step diagnostic count mismatch")
    require(text.count(missing_line) == 1, "workflow missing_steps diagnostic count mismatch")
    require(text.count(message_line) == 1, "workflow message diagnostic count mismatch")

    old_positions = {
        "error": text.index(error_line),
        "status": text.index(status_line),
        "failed": text.index(failed_line),
        "missing": text.index(missing_line),
        "message": text.index(message_line),
    }

    require(
        old_positions["error"] < old_positions["status"] < old_positions["message"],
        "workflow diagnostic order no longer matches diagnosed opaque-failure pattern",
    )

    lines = text.splitlines(keepends=True)

    error_idx = next(i for i, line in enumerate(lines) if error_line in line)
    error_full = lines.pop(error_idx)

    message_idx = next(i for i, line in enumerate(lines) if message_line in line)
    lines.insert(message_idx + 1, error_full)

    fixed = "".join(lines)
    path.write_text(fixed, encoding="utf-8", newline="")

    new_positions = {
        "status": fixed.index(status_line),
        "failed": fixed.index(failed_line),
        "missing": fixed.index(missing_line),
        "message": fixed.index(message_line),
        "error": fixed.index(error_line),
    }

    require(
        new_positions["status"]
        < new_positions["failed"]
        < new_positions["missing"]
        < new_positions["message"]
        < new_positions["error"],
        "workflow diagnostics are not before Write-Error after patch",
    )

    return {
        "strategy": "emit packaged status/failed_step/missing/message before Write-Error",
        "old_positions": old_positions,
        "new_positions": new_positions,
        "failure_semantics_preserved": True,
    }


def post_contract_probe(tree):
    data = contract_probe(tree)

    require(data.get("public_types") == ["CODE", "ADRG"],
            "public SEARCH_ENTITY_TYPES changed")

    expected = {
        "CODE": "CODE",
        "ADRG": "ADRG",
        "ALL": "ALL",
        "AADRG": "ALL",
        "INVALID": "ALL",
    }

    actual = {}
    for key in expected:
        item = data.get(key) or {}
        require(item.get("ok") is True, f"normalizer {key} probe failed: {item}")
        actual[key] = item.get("entityType")
        require(actual[key] == expected[key],
                f"normalizer {key}: {actual[key]} != {expected[key]}")
        require(item.get("entityTypeType") == "string",
                f"normalizer {key} is not scalar string")

    return {
        "expected": expected,
        "actual": actual,
        "all_scalar_string": True,
    }


def normalized_full_audit(tree):
    fixture_json = json.dumps(FIXTURES)

    js = rf"""
'use strict';
const path = require('node:path');
const {{
  normalizeSearchRequest,
}} = require('./src/search-result-contract');
const {{
  KdrgSearchService,
}} = require('./src/kdrg-search-service');

const s = new KdrgSearchService(
  path.resolve('..','data','kdrg_v47_search_integrated_v3.json')
);

const ids = [...s.recordMaps.ADRG.keys()].map(String).sort();
const codeIds = new Set([...s.recordMaps.CODE.keys()].map(String));
const collisions = ids.filter(x => codeIds.has(x));
const fixtures = {fixture_json};

function idsOf(r) {{
  return (r.results || []).map(x => `${{x.entity_type}}:${{x.entity_id}}`);
}}

let failures = [];
for (const id of ids) {{
  const req = normalizeSearchRequest({{
    query:id,
    entityType:'ADRG',
    limit:500,
    offset:0
  }});
  if (req.entityType !== 'ADRG' || Array.isArray(req.entityType)) {{
    failures.push({{id,reason:'NORMALIZER_TYPE',entityType:req.entityType}});
    continue;
  }}
  const r = s.search(
    req.query,
    req.entityType,
    {{
      limit:req.limit,
      offset:req.offset,
      mdc:req.mdc,
      classification:req.classification
    }}
  );
  const ok = (r.results || []).some(
    x => x.entity_type === 'ADRG' && x.entity_id === id
  );
  if (!ok) failures.push({{id,reason:'EXACT_ADRG_MISSING'}});
}}

let collisionBehaviorChanges = [];
for (const id of collisions) {{
  for (const type of ['CODE','ALL']) {{
    const req = normalizeSearchRequest({{
      query:id,
      entityType:type,
      limit:500,
      offset:0
    }});
    if (req.entityType !== type) {{
      collisionBehaviorChanges.push({{id,type,reason:'NORMALIZER',actual:req.entityType}});
      continue;
    }}
    const via = s.search(
      req.query,
      req.entityType,
      {{
        limit:req.limit,
        offset:req.offset,
        mdc:req.mdc,
        classification:req.classification
      }}
    );
    const direct = s.search(id,type,{{limit:500,offset:0}});
    if (JSON.stringify(idsOf(via)) !== JSON.stringify(idsOf(direct))) {{
      collisionBehaviorChanges.push({{id,type,reason:'RESULTS'}});
    }}
  }}
}}

let fixtureFailures = [];
for (const id of fixtures) {{
  const req = normalizeSearchRequest({{
    query:id,
    entityType:'ADRG',
    limit:500,
    offset:0
  }});
  const r = s.search(
    req.query,
    req.entityType,
    {{
      limit:req.limit,
      offset:req.offset,
      mdc:req.mdc,
      classification:req.classification
    }}
  );
  if (!(r.results || []).some(
    x => x.entity_type === 'ADRG' && x.entity_id === id
  )) {{
    fixtureFailures.push(id);
  }}
}}

console.log(JSON.stringify({{
  adrg_count:ids.length,
  collision_count:collisions.length,
  normalized_adrg_failure_count:failures.length,
  normalized_adrg_failure_sample:failures.slice(0,20),
  collision_behavior_change_count:collisionBehaviorChanges.length,
  collision_behavior_change_sample:collisionBehaviorChanges.slice(0,20),
  fixture_failure_count:fixtureFailures.length,
  fixture_failures:fixtureFailures
}}));
"""

    r = run(["node", "-e", js], cwd=tree / "electron", check=False, timeout=2400)
    require(r["returncode"] == 0, "normalized full audit failed:\n" + r["output"])
    data = json.loads(r["output"].strip().splitlines()[-1])

    require(data.get("adrg_count") == 1132, "normalized ADRG count mismatch")
    require(data.get("collision_count") == 471, "normalized collision count mismatch")
    require(data.get("normalized_adrg_failure_count") == 0,
            "normalized ADRG failures remain")
    require(data.get("collision_behavior_change_count") == 0,
            "normalized CODE/ALL collision behavior changed")
    require(data.get("fixture_failure_count") == 0,
            "packaged fixture bridge failures remain")

    return data


def static_wiring_audit(tree):
    package = json.loads((tree / "electron/package.json").read_text(encoding="utf-8"))
    main_path = tree / "electron" / package["main"]
    main = main_path.read_text(encoding="utf-8")
    app = (tree / "electron/renderer/app.js").read_text(encoding="utf-8")
    packaged = (tree / "electron/src/packaged-runtime-smoke.js").read_text(encoding="utf-8")

    preload_candidates = [
        tree / "electron/src/preload.js",
        tree / "electron/preload.js",
        main_path.parent / "preload.js",
    ]
    preload_path = next((p for p in preload_candidates if p.is_file()), None)
    preload = preload_path.read_text(encoding="utf-8") if preload_path else ""

    # Avoid brittle exact variable names. Prove semantic markers instead.
    main_search_calls = re.findall(
        r"([A-Za-z_$][\w$]*)\.search\s*\(",
        main,
    )

    checks = {
        "renderer_calls_window_search": "window.KDRG.search" in app,
        "renderer_has_entity_type_request":
            "entityType" in app or "entity_type" in app,
        "preload_kdrg_search":
            "ipcRenderer.invoke" in preload and "kdrg:search" in preload,
        "main_kdrg_search_handler":
            "ipcMain.handle" in main and "kdrg:search" in main,
        "main_normalizeSearchRequest":
            "normalizeSearchRequest" in main,
        "main_has_any_search_method_call":
            bool(main_search_calls),
        "main_uses_request_entity_type":
            "request.entityType" in main or "request.entity_type" in main,
        "packaged_filter_adrg":
            "filter.value = 'ADRG';" in packaged,
        "packaged_query_fixture":
            "fixture.search_query" in packaged,
        "packaged_selector_adrg":
            'data-entity-type="ADRG"' in packaged and "fixture.adrg" in packaged,
    }

    require(all(checks.values()),
            "static wiring audit failed: "
            + json.dumps({k:v for k,v in checks.items() if not v}))

    return {
        "checks": checks,
        "main_search_receivers": sorted(set(main_search_calls)),
        "main_path": str(main_path.relative_to(tree)),
        "preload_path": (
            str(preload_path.relative_to(tree))
            if preload_path
            else None
        ),
    }


def workflow_audit(tree):
    text = (tree / WORKFLOW_REL).read_text(encoding="utf-8")

    status = 'Write-Host "status=$($report.status)"'
    failed = 'Write-Host "failed_step=$($report.failed_step)"'
    missing = 'Write-Host "missing_steps=$($missing -join \',\')"'
    message = 'Write-Host "message=$message"'
    error = 'Write-Error "packaged 핵심검증 실패"'

    positions = {
        "status": text.index(status),
        "failed": text.index(failed),
        "missing": text.index(missing),
        "message": text.index(message),
        "error": text.index(error),
    }

    require(
        positions["status"]
        < positions["failed"]
        < positions["missing"]
        < positions["message"]
        < positions["error"],
        "workflow failure diagnostics still occur after Write-Error",
    )

    require("packaged_ui_validation" in text,
            "workflow packaged UI failure gate missing")

    return {
        "diagnostics_before_error": True,
        "positions": positions,
        "packaged_ui_gate_present": True,
    }


def official_regression(tree):
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
  throw new Error('F2120 internal AADRG regression');
}

console.log('[PASS] F022/P651/F212 regression');
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

    check(["node", "--check", "src/search-result-contract.js"],
          cwd=shadow / "electron")
    check(["node", "--check", "tests/validate-stage59b-search.js"],
          cwd=shadow / "electron")
    check(["node", "--check", "tests/validate-packaged-runtime-smoke.js"],
          cwd=shadow / "electron")

    contract = post_contract_probe(shadow)
    full = normalized_full_audit(shadow)
    wiring = static_wiring_audit(shadow)
    workflow = workflow_audit(shadow)

    check(["node", "tests/validate-stage59b-search.js"],
          cwd=shadow / "electron")
    check(["node", "tests/validate-packaged-runtime-smoke.js"],
          cwd=shadow / "electron")
    check(["node", "tests/validate-stage60c-packaged-relation-smoke.js"],
          cwd=shadow / "electron")
    check(["node", "tests/validate-stage59b-ui.js"],
          cwd=shadow / "electron")
    check(["node", "tests/validate-stage59b-smoke.js"],
          cwd=shadow / "electron")
    check(["npm", "run", "check"],
          cwd=shadow / "electron", timeout=1800)

    for rel in ROOT_VALIDATORS:
        check(["python", rel], cwd=shadow, timeout=1800)

    check(["node", "tests/validate-release-version.js", VERSION],
          cwd=shadow / "electron", timeout=600)

    official_regression(shadow)

    require(sha256_path(shadow / RUNTIME_REL) == RUNTIME_SHA,
            "Shadow runtime changed")
    require(sha256_path(shadow / OFFICIAL_REL) == OFFICIAL_SHA,
            "Shadow official condition changed")
    require(sha256_path(shadow / ICON_PNG_REL) == ICON_PNG_SHA,
            "Shadow PNG icon changed")
    require(sha256_path(shadow / ICON_ICO_REL) == ICON_ICO_SHA,
            "Shadow ICO icon changed")

    changed = sorted(git_lines("diff", "--name-only", cwd=shadow))
    require(changed == sorted(TARGETS),
            "Shadow delta is not exact 4-file full-pipeline repair: "
            + json.dumps(changed))

    diff_check = run(["git", "diff", "--check"],
                     cwd=shadow, check=False)
    require(diff_check["returncode"] == 0,
            "Shadow git diff --check failed:\n" + diff_check["output"])

    return {
        "contract": contract,
        "normalized_full_audit": full,
        "static_wiring": wiring,
        "workflow": workflow,
        "npm_run_check": "PASS",
        "stage59b_stage60c_packaged": "PASS",
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

    require(sha256_path(ROOT / RUNTIME_REL) == RUNTIME_SHA,
            "Actual runtime changed")
    require(sha256_path(ROOT / OFFICIAL_REL) == OFFICIAL_SHA,
            "Actual official condition changed")
    require(sha256_path(ROOT / ICON_PNG_REL) == ICON_PNG_SHA,
            "Actual PNG icon changed")
    require(sha256_path(ROOT / ICON_ICO_REL) == ICON_ICO_SHA,
            "Actual ICO icon changed")

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
        "official_condition_unchanged": True,
        "icon_unchanged": True,
        "release_tag_absent": True,
        "release_absent": True,
    }


def cleanup_shadow(shadow):
    if shadow is None:
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

    before = payload.get("contract_before") or {}
    validation = payload.get("validation") or {}
    full = validation.get("normalized_full_audit") or {}
    contract = validation.get("contract") or {}
    workflow = validation.get("workflow") or {}

    before_adrg = (before.get("ADRG") or {}).get("entityType")
    before_all = (before.get("ALL") or {}).get("entityType")

    lines = [
        "KDRG V4.7 Electron Stage67I4B / 0.5.15 Full Search Pipeline Repair Shadow R1",
        "=" * 106,
        f"status={payload['status']}",
        f"readiness={payload['readiness']}",
        "",
        "[CONFIRMED ROOT CAUSE]",
        json.dumps({
            "before_ADRG_entityType": before_adrg,
            "before_ALL_entityType": before_all,
            "after_public_types": contract.get("actual"),
            "all_scalar_string": contract.get("all_scalar_string"),
        }, ensure_ascii=False, indent=2),
        "",
        "[FULL PIPELINE VALIDATION]",
        json.dumps({
            "ADRG_count": full.get("adrg_count"),
            "collision_count": full.get("collision_count"),
            "normalized_ADRG_failures":
                full.get("normalized_adrg_failure_count"),
            "CODE_ALL_collision_changes":
                full.get("collision_behavior_change_count"),
            "fixture_failures":
                full.get("fixture_failure_count"),
            "static_wiring":
                (validation.get("static_wiring") or {}).get("checks"),
            "workflow_diagnostics_before_error":
                workflow.get("diagnostics_before_error"),
            "npm_run_check": validation.get("npm_run_check"),
            "stage59b_stage60c_packaged":
                validation.get("stage59b_stage60c_packaged"),
            "root_50b_50c_50d":
                validation.get("root_50b_50c_50d"),
            "release_version":
                validation.get("release_version"),
            "official_regression":
                validation.get("official_regression"),
            "git_diff_check":
                validation.get("git_diff_check"),
        }, ensure_ascii=False, indent=2),
        "",
        "[SHADOW DELTA]",
        json.dumps(
            validation.get("tracked_diff_files") or [],
            ensure_ascii=False,
            indent=2,
        ),
        "",
        "[ACTUAL GUARD]",
        json.dumps(payload.get("actual_guard", {}),
                   ensure_ascii=False, indent=2),
        "",
    ]

    if payload.get("error"):
        lines += ["[BLOCKER]", payload["error"].splitlines()[0], ""]

    lines += [
        "[NEXT]",
        "- PASS이면 단순 B018 보정이 아니라 normalizer→service→renderer/packaged 경로 전체가 Shadow에서 검증됨.",
        "- 다음 Stage67I5에서 manifest의 정확한 4개만 Actual 적용 후 동일 전수검증.",
        "- Actual PASS 후 새 fix commit/push + 새 workflow_dispatch RC.",
        "- 새 RC success 후에만 electron-v0.5.15 tag/release.",
        "",
        f"manifest={MANIFEST_JSON}",
        f"report_json={REPORT_JSON}",
    ]

    REPORT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    payload = {
        "status": "FAIL",
        "readiness": "NOT_READY_FOR_0515_FULL_PIPELINE_ACTUAL_APPLY",
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "gate": {},
        "preflight": {},
        "contract_before": {},
        "repair": {},
        "validation": {},
        "actual_guard": {},
        "error": None,
    }

    shadow = None

    try:
        payload["gate"] = load_gate()
        payload["preflight"] = preflight(payload["gate"])

        shadow = create_shadow(payload["gate"]["commit"])

        payload["contract_before"] = contract_probe(shadow)

        payload["repair"] = {
            "contract": patch_contract(
                shadow / "electron/src/search-result-contract.js",
                payload["contract_before"],
            ),
            "stage59b_search_validator": append_validator_block(
                shadow / "electron/tests/validate-stage59b-search.js",
                "Stage67I4B normalized request bridge",
                packaged=False,
            ),
            "packaged_validator": append_validator_block(
                shadow / "electron/tests/validate-packaged-runtime-smoke.js",
                "Stage67I4B packaged normalized request bridge",
                packaged=True,
            ),
            "workflow_observability": patch_workflow(
                shadow / WORKFLOW_REL
            ),
            "target_files": TARGETS,
        }

        payload["validation"] = validate_shadow(shadow)
        payload["actual_guard"] = actual_guard(
            payload["gate"]["commit"],
            payload["preflight"]["before_sha256"],
        )

        manifest = {
            "schema_version": "kdrg-0515-full-pipeline-repair-v1",
            "status": "PASS",
            "readiness": "READY_FOR_0515_FULL_PIPELINE_ACTUAL_APPLY",
            "base_commit": payload["gate"]["commit"],
            "target_version": VERSION,
            "apply_file_count": 4,
            "repair_contract": {
                "public_entityType_scalar": True,
                "CODE_to_CODE": True,
                "ADRG_to_ADRG": True,
                "ALL_to_ALL": True,
                "hidden_invalid_to_ALL": True,
                "all_1132_normalized_ADRG_exact_ids_pass": True,
                "all_471_collision_CODE_ALL_behavior_unchanged": True,
                "all_6_packaged_fixture_bridges_pass": True,
                "workflow_failure_diagnostics_visible_before_error": True,
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
        payload["readiness"] = "READY_FOR_0515_FULL_PIPELINE_ACTUAL_APPLY"

        # Keep successful Shadow because manifest points to exact files.
        shadow = None

    except Exception as exc:
        payload["error"] = (
            f"{type(exc).__name__}: {exc}\n"
            f"{traceback.format_exc()}"
        )

    finally:
        if shadow is not None:
            cleanup_shadow(shadow)

    payload["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    write_report(payload)

    if payload["status"] == "PASS":
        before = payload["contract_before"]
        v = payload["validation"]
        full = v["normalized_full_audit"]

        print("[PASS] Stage67I4B / 0.5.15 Full Search Pipeline Repair Shadow R1")
        print("readiness=READY_FOR_0515_FULL_PIPELINE_ACTUAL_APPLY")
        print(
            f"[PASS] entityType shape: ADRG "
            f"{(before.get('ADRG') or {}).get('entityType')} -> ADRG scalar"
        )
        print(
            f"[PASS] normalized ADRG audit={full['adrg_count']} / "
            f"collisions={full['collision_count']} / "
            f"failures={full['normalized_adrg_failure_count']}"
        )
        print(
            f"[PASS] CODE/ALL collision behavior changes="
            f"{full['collision_behavior_change_count']} / "
            f"fixture failures={full['fixture_failure_count']}"
        )
        print("[PASS] renderer/preload/main/packaged static wiring")
        print("[PASS] workflow failure diagnostics visible before Write-Error")
        print("[PASS] npm + stage59b/stage60c + 50B/50C/50D + release-version")
        print("[PASS] F022/P651/F212 + runtime/icon/official-condition")
        print("[PASS] exact Shadow delta=4 files / Actual untouched")
        print("[STOP] no Actual apply/commit/push/RC/tag/release")
        print(f"report_txt={REPORT_TXT}")
        print(f"manifest={MANIFEST_JSON}")
        return 0

    print("[FAIL] Stage67I4B / 0.5.15 Full Search Pipeline Repair Shadow R1")
    print("readiness=NOT_READY_FOR_0515_FULL_PIPELINE_ACTUAL_APPLY")
    if payload.get("error"):
        print("[BLOCKER] " + payload["error"].splitlines()[0])
    print("[STOP] no Actual apply/commit/push/RC/tag/release")
    print(f"report_txt={REPORT_TXT}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
