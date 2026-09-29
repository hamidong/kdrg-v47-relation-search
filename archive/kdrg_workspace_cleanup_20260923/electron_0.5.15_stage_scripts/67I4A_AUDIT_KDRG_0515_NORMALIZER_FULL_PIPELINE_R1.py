#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KDRG V4.7 Electron Stage67I4A
0.5.15 Normalizer + Renderer + Packaged UI Full Pipeline Audit R1

Why this audit exists
---------------------
Stage67I4 R1/R2 both stopped before any Actual modification because the repair
scripts assumed a source shape that did not match the real normalizeSearchRequest
implementation.

This audit deliberately makes NO repair.

It inspects the whole current 0.5.15 search path and downstream validators:

renderer
 -> preload
 -> main IPC
 -> normalizeSearchRequest
 -> KdrgSearchService.search
 -> renderer result card
 -> packaged UI smoke
 -> packaged validators
 -> release validators / workflow

It also checks the likely *next* failure points before another repair is written.

READ-ONLY with respect to tracked product files.
No add/commit/push/workflow rerun/tag/release.
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
ELECTRON = ROOT / "electron"

REPORT_TXT = ROOT / "stage67i4a_0515_normalizer_full_pipeline_audit_r1.txt"
REPORT_JSON = ROOT / "stage67i4a_0515_normalizer_full_pipeline_audit_r1.json"

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

R3_DIAG = ROOT / "stage67i3d_0515_b018_renderer_path_diagnosis_r3.json"

BASELINE_COMMANDS = [
    (["node", "tests/validate-stage59b-search.js"], ELECTRON),
    (["node", "tests/validate-packaged-runtime-smoke.js"], ELECTRON),
    (["node", "tests/validate-stage60c-packaged-relation-smoke.js"], ELECTRON),
    (["node", "tests/validate-stage59b-ui.js"], ELECTRON),
    (["node", "tests/validate-stage59b-smoke.js"], ELECTRON),
    (["npm", "run", "check"], ELECTRON),
    (["python", "50B_validate_kdrg_electron_search_service.py"], ROOT),
    (["python", "50C_validate_kdrg_electron_renderer_ui.py"], ROOT),
    (["python", "50D_validate_kdrg_electron_windows_packaging.py"], ROOT),
    (["node", "tests/validate-release-version.js", VERSION], ELECTRON),
]


class AuditError(RuntimeError):
    pass


def require(value, message):
    if not value:
        raise AuditError(message)


def run(cmd, cwd=None, check=False, timeout=1800):
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
        raise AuditError(
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


def local_tag_sha(tag):
    r = run(["git", "rev-parse", "-q", "--verify", f"refs/tags/{tag}"])
    return r["output"].strip() if r["returncode"] == 0 else ""


def remote_tag_sha(tag):
    r = run(["git", "ls-remote", "--tags", "origin", f"refs/tags/{tag}"], check=True)
    return r["output"].strip().split()[0] if r["output"].strip() else ""


def release_exists(tag):
    r = run(["gh", "release", "view", tag, "--json", "tagName"])
    return r["returncode"] == 0


def sha256_path(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_text(path):
    return Path(path).read_text(encoding="utf-8", errors="replace")


def short_output(text, max_lines=8):
    lines = text.splitlines()
    return "\n".join(lines[-max_lines:])


def repo_state():
    head = git_text("rev-parse", "HEAD")
    origin = remote_main_sha()
    branch = git_text("branch", "--show-current")
    tracked = git_lines("diff", "--name-only")
    staged = git_lines("diff", "--cached", "--name-only")

    require(branch == "main", f"branch is not main: {branch}")
    require(head == origin, f"HEAD/origin mismatch: {head} / {origin}")
    require(not tracked, f"tracked worktree not clean: {tracked}")
    require(not staged, f"staging not empty: {staged}")

    require(local_tag_sha(BASE_TAG) == BASE_0514_COMMIT, "0.5.14 local tag mismatch")
    require(remote_tag_sha(BASE_TAG) == BASE_0514_COMMIT, "0.5.14 remote tag mismatch")
    require(not local_tag_sha(RELEASE_TAG), "0.5.15 local tag already exists")
    require(not remote_tag_sha(RELEASE_TAG), "0.5.15 remote tag already exists")
    require(not release_exists(RELEASE_TAG), "0.5.15 GitHub Release already exists")

    require(sha256_path(ROOT / RUNTIME_REL) == RUNTIME_SHA, "runtime SHA mismatch")
    require(sha256_path(ROOT / OFFICIAL_REL) == OFFICIAL_SHA, "official condition SHA mismatch")
    require(sha256_path(ROOT / ICON_PNG_REL) == ICON_PNG_SHA, "PNG icon SHA mismatch")
    require(sha256_path(ROOT / ICON_ICO_REL) == ICON_ICO_SHA, "ICO icon SHA mismatch")

    package = json.loads((ELECTRON / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((ELECTRON / "package-lock.json").read_text(encoding="utf-8"))
    require(package.get("version") == VERSION, "package version mismatch")
    require(lock.get("version") == VERSION, "package-lock version mismatch")

    diag = {}
    if R3_DIAG.is_file():
        try:
            d = json.loads(R3_DIAG.read_text(encoding="utf-8"))
            diag = {
                "status": d.get("status"),
                "diagnosed_fix_commit": (d.get("gate") or {}).get("fix_commit"),
                "failed_step": (d.get("gate") or {}).get("failed_step"),
                "error_message": (d.get("gate") or {}).get("error_message"),
                "signals": (d.get("classification") or {}).get("signals"),
            }
        except Exception as exc:
            diag = {"read_error": str(exc)}

    return {
        "head": head,
        "origin_main": origin,
        "branch": branch,
        "tracked_clean": True,
        "staging_empty": True,
        "package_version": VERSION,
        "runtime_unchanged": True,
        "official_condition_unchanged": True,
        "icon_unchanged": True,
        "base_tag_immutable": True,
        "release_tag_absent": True,
        "release_absent": True,
        "previous_diagnosis": diag,
    }


def tracked_files():
    return [ROOT / rel for rel in git_lines("ls-files")]


def scan_normalizer_locations():
    patterns = [
        re.compile(r"\bfunction\s+normalizeSearchRequest\s*\("),
        re.compile(r"\b(?:const|let|var)\s+normalizeSearchRequest\s*="),
        re.compile(r"\bnormalizeSearchRequest\s*:\s*"),
    ]

    defs = []
    uses = []

    for path in tracked_files():
        if path.suffix.lower() not in {".js", ".mjs", ".cjs", ".ts", ".py", ".yml", ".yaml", ".html"}:
            continue
        text = read_text(path)
        rel = str(path.relative_to(ROOT))
        for no, line in enumerate(text.splitlines(), 1):
            if "normalizeSearchRequest" not in line:
                continue
            item = {"path": rel, "line": no, "text": line.strip()[:500]}
            if any(p.search(line) for p in patterns):
                defs.append(item)
            else:
                uses.append(item)

    return {
        "definitions": defs,
        "uses": uses[:100],
        "definition_count": len(defs),
        "use_count": len(uses),
    }


def contract_runtime_probe():
    js = r"""
'use strict';

function safe(fn) {
  try {
    return { ok:true, value:fn() };
  } catch (e) {
    return {
      ok:false,
      error:String(e && e.message || e),
      stack:String(e && e.stack || '').split('\n').slice(0,4).join('\n')
    };
  }
}

const c = require('./src/search-result-contract');
const fn = c.normalizeSearchRequest;

const out = {
  exports:Object.keys(c).sort(),
  search_entity_types:c.SEARCH_ENTITY_TYPES || null,
  normalize_type:typeof fn,
  normalize_length:typeof fn === 'function' ? fn.length : null,
  normalize_source:typeof fn === 'function' ? String(fn) : null,
  probes:{}
};

if (typeof fn === 'function') {
  for (const type of ['CODE','ADRG','ALL','AADRG','INVALID']) {
    out.probes['object_' + type] = safe(() => fn({
      query:'B018',
      entityType:type,
      limit:100,
      offset:0
    }));
  }

  out.probes.object_entity_type_ADRG = safe(() => fn({
    query:'B018',
    entity_type:'ADRG',
    limit:100,
    offset:0
  }));

  out.probes.positional_B018_ADRG = safe(() => fn('B018','ADRG',{
    limit:100,
    offset:0
  }));
}

console.log(JSON.stringify(out));
"""
    r = run(["node", "-e", js], cwd=ELECTRON, timeout=600)
    require(r["returncode"] == 0, "contract runtime probe failed:\n" + r["output"])
    return json.loads(r["output"].strip().splitlines()[-1])


def service_runtime_probe():
    js = r"""
'use strict';
const path = require('node:path');
const { KdrgSearchService } = require('./src/kdrg-search-service');

const s = new KdrgSearchService(
  path.resolve('..','data','kdrg_v47_search_integrated_v3.json')
);

function ids(r) {
  return (r.results || []).map(x => `${x.entity_type}:${x.entity_id}`);
}

const b018 = s.search('B018','ADRG',{limit:500,offset:0});
const exact = (b018.results || []).filter(
  x => x.entity_type === 'ADRG' && x.entity_id === 'B018'
);

const adrgIds = [...s.recordMaps.ADRG.keys()].map(String).sort();
const codeIds = new Set([...s.recordMaps.CODE.keys()].map(String));
const collisions = adrgIds.filter(x => codeIds.has(x));

let failures = 0;
let noncollision = 0;
for (const id of adrgIds) {
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
  b018_total_count:b018.total_count,
  b018_exact_count:exact.length,
  b018_first_results:ids(b018).slice(0,10),
  adrg_count:adrgIds.length,
  collision_count:collisions.length,
  failure_count:failures,
  noncollision_failure_count:noncollision
}));
"""
    r = run(["node", "-e", js], cwd=ELECTRON, timeout=1800)
    require(r["returncode"] == 0, "service runtime probe failed:\n" + r["output"])
    return json.loads(r["output"].strip().splitlines()[-1])


def package_paths():
    package = json.loads((ELECTRON / "package.json").read_text(encoding="utf-8"))
    main_rel = package.get("main")
    require(main_rel, "package main missing")
    main_path = ELECTRON / main_rel
    require(main_path.is_file(), f"main source missing: {main_path}")

    main = read_text(main_path)

    preload_candidates = []
    for m in re.finditer(
        r"preload\s*:\s*path\.join\(\s*__dirname\s*,\s*['\"]([^'\"]+)['\"]",
        main,
    ):
        preload_candidates.append((main_path.parent / m.group(1)).resolve())

    for p in [
        ELECTRON / "src/preload.js",
        ELECTRON / "preload.js",
        main_path.parent / "preload.js",
    ]:
        if p.is_file():
            preload_candidates.append(p.resolve())

    preload_path = next((p for p in preload_candidates if p.is_file()), None)

    return {
        "main_path": str(main_path.relative_to(ROOT)),
        "preload_path": str(preload_path.relative_to(ROOT)) if preload_path else None,
    }


def source_context(path, needles, radius=4):
    if not path or not Path(path).is_file():
        return []
    lines = read_text(path).splitlines()
    rows = []
    seen = set()

    for i, line in enumerate(lines):
        if not any(n.lower() in line.lower() for n in needles):
            continue
        for j in range(max(0, i-radius), min(len(lines), i+radius+1)):
            key = (j, lines[j])
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "line": j+1,
                "text": lines[j][:800],
            })

    return rows[:120]


def trace_search_path(paths):
    main_path = ROOT / paths["main_path"]
    preload_path = ROOT / paths["preload_path"] if paths.get("preload_path") else None

    app_path = ELECTRON / "renderer/app.js"
    packaged_path = ELECTRON / "src/packaged-runtime-smoke.js"
    contract_path = ELECTRON / "src/search-result-contract.js"

    main = read_text(main_path)
    preload = read_text(preload_path) if preload_path else ""
    app = read_text(app_path)
    packaged = read_text(packaged_path)
    contract = read_text(contract_path)

    signals = {
        "renderer_calls_window_KDRG_search":
            "window.KDRG.search" in app,
        "renderer_mentions_search_type":
            "search-type" in app or "searchType" in app,
        "preload_invokes_kdrg_search":
            "ipcRenderer.invoke" in preload and "kdrg:search" in preload,
        "main_handles_kdrg_search":
            "ipcMain.handle" in main and "kdrg:search" in main,
        "main_uses_normalizeSearchRequest":
            "normalizeSearchRequest" in main,
        "main_calls_service_search":
            "service.search" in main,
        "packaged_sets_ADRG_filter":
            "filter.value = 'ADRG';" in packaged,
        "packaged_queries_fixture_search_query":
            "fixture.search_query" in packaged,
        "packaged_waits_ADRG_result":
            'data-entity-type="ADRG"' in packaged
            and "fixture.adrg" in packaged
            and "result ready" in packaged,
        "contract_public_types_CODE_ADRG":
            bool(re.search(
                r"SEARCH_ENTITY_TYPES\s*=\s*Object\.freeze\(\s*\[\s*['\"]CODE['\"]\s*,\s*['\"]ADRG['\"]\s*\]\s*\)",
                contract,
            )),
    }

    contexts = {
        "renderer": source_context(
            app_path,
            ["window.KDRG.search", "search-type", "entityType"],
            radius=5,
        ),
        "preload": source_context(
            preload_path,
            ["kdrg:search", "ipcRenderer.invoke"],
            radius=5,
        ) if preload_path else [],
        "main": source_context(
            main_path,
            ["normalizeSearchRequest", "kdrg:search", "service.search"],
            radius=6,
        ),
        "contract": source_context(
            contract_path,
            ["SEARCH_ENTITY_TYPES", "normalizeSearchRequest"],
            radius=8,
        ),
        "packaged": source_context(
            packaged_path,
            ["filter.value = 'ADRG'", "fixture.search_query", "result ready"],
            radius=7,
        ),
    }

    return {
        "signals": signals,
        "contexts": contexts,
    }


def scan_stale_public_refs(paths):
    tracked = [
        p for p in tracked_files()
        if p.suffix.lower() in {".js", ".py", ".yml", ".yaml", ".html"}
    ]

    suspicious_patterns = [
        ("PUBLIC_TYPES_AADRG", re.compile(
            r"(SEARCH_ENTITY_TYPES|public types|public type).*AADRG", re.I
        )),
        ("FILTER_AADRG", re.compile(
            r"(filter\.value|search-type|entityType).*AADRG", re.I
        )),
        ("NORMALIZER_AADRG", re.compile(
            r"normalizeSearchRequest.*AADRG|AADRG.*normalizeSearchRequest", re.I
        )),
        ("PUBLIC_RESULT_AADRG", re.compile(
            r"(public result|result selector|data-entity-type).*AADRG", re.I
        )),
    ]

    rows = []
    for path in tracked:
        rel = str(path.relative_to(ROOT))
        text = read_text(path)
        for no, line in enumerate(text.splitlines(), 1):
            if "AADRG" not in line:
                continue
            for kind, pattern in suspicious_patterns:
                if pattern.search(line):
                    rows.append({
                        "kind": kind,
                        "path": rel,
                        "line": no,
                        "text": line.strip()[:500],
                    })
                    break

    # Internal AADRG is intentionally preserved, so this is only a candidate list.
    return {
        "candidate_count": len(rows),
        "candidates": rows[:120],
    }


def packaged_fixture_audit():
    path = ELECTRON / "src/packaged-runtime-smoke.js"
    text = read_text(path)

    expected = ["B013", "B014", "B018", "B022", "L033", "9610"]
    fixtures = []

    for adrg in expected:
        m = re.search(
            rf"adrg:\s*['\"]{re.escape(adrg)}['\"].*?"
            r"search_query:\s*['\"]([^'\"]+)['\"]",
            text,
            flags=re.S,
        )
        fixtures.append({
            "adrg": adrg,
            "search_query": m.group(1) if m else None,
        })

    return {
        "fixtures": fixtures,
        "all_search_query_equals_adrg":
            all(x["search_query"] == x["adrg"] for x in fixtures),
        "filter_adrg": "filter.value = 'ADRG';" in text,
        "selector_adrg":
            'data-entity-type="ADRG"' in text and "fixture.adrg" in text,
    }


def validator_future_risk_audit():
    checks = {}

    def has(path, *needles):
        text = read_text(ROOT / path)
        return all(n in text for n in needles)

    checks["stage59b_search_public_ADRG"] = has(
        "electron/tests/validate-stage59b-search.js",
        "SEARCH_ENTITY_TYPES",
        "ADRG",
    )
    checks["packaged_validator_ADRG_filter"] = has(
        "electron/tests/validate-packaged-runtime-smoke.js",
        "ADRG",
        "search_query",
    )
    checks["stage59b_ui_ADRG"] = has(
        "electron/tests/validate-stage59b-ui.js",
        "ADRG",
    )
    checks["stage60c_packaged_relation_ADRG"] = has(
        "electron/tests/validate-stage60c-packaged-relation-smoke.js",
        "ADRG",
    )

    # Workflow still runs the packaged smoke; verify the gate exists.
    workflow = ROOT / ".github/workflows/build-electron-windows.yml"
    if workflow.is_file():
        w = read_text(workflow)
        checks["workflow_packaged_smoke_gate"] = (
            "packaged 핵심검증" in w
            and "packaged_ui_validation" in w
        )
    else:
        checks["workflow_packaged_smoke_gate"] = False

    return checks


def baseline_validations():
    results = []
    for cmd, cwd in BASELINE_COMMANDS:
        r = run(cmd, cwd=cwd, timeout=1800)
        results.append({
            "cmd": " ".join(cmd),
            "cwd": str(Path(cwd).relative_to(ROOT)) if Path(cwd) != ROOT else ".",
            "returncode": r["returncode"],
            "tail": short_output(r["output"], 5),
        })

    # Validators may write ignored reports. They must not alter tracked files.
    tracked_after = git_lines("diff", "--name-only")
    staged_after = git_lines("diff", "--cached", "--name-only")
    require(not tracked_after, f"baseline validation changed tracked files: {tracked_after}")
    require(not staged_after, f"baseline validation staged files: {staged_after}")

    return {
        "pass_count": sum(x["returncode"] == 0 for x in results),
        "fail_count": sum(x["returncode"] != 0 for x in results),
        "results": results,
        "tracked_files_unchanged": True,
    }


def classify(audit):
    signals = audit["trace"]["signals"]
    contract = audit["contract_probe"]
    service = audit["service_probe"]
    fixture = audit["packaged_fixture"]
    baseline = audit["baseline"]
    defs = audit["normalizer_locations"]["definitions"]

    reasons = []
    blockers = []

    if service.get("b018_exact_count", 0) >= 1 and service.get("failure_count") == 0:
        reasons.append("SERVICE_LAYER_HEALTHY")
    else:
        blockers.append("SERVICE_LAYER_NOT_HEALTHY")

    if fixture.get("all_search_query_equals_adrg") and fixture.get("filter_adrg") and fixture.get("selector_adrg"):
        reasons.append("PACKAGED_FIXTURE_ADRG_CONTRACT_HEALTHY")
    else:
        blockers.append("PACKAGED_FIXTURE_CONTRACT_MISMATCH")

    probe = (contract.get("probes") or {}).get("object_ADRG") or {}
    normalized_type = None
    if probe.get("ok") and isinstance(probe.get("value"), dict):
        normalized_type = (
            probe["value"].get("entityType")
            or probe["value"].get("entity_type")
        )

    if normalized_type == "ADRG":
        reasons.append("NORMALIZER_OBJECT_ADRG_HEALTHY")
    else:
        blockers.append("NORMALIZER_OBJECT_ADRG_NOT_PRESERVED")

    if len(defs) == 1:
        reasons.append("NORMALIZER_DEFINITION_UNIQUE")
    elif len(defs) == 0:
        blockers.append("NORMALIZER_DEFINITION_NOT_FOUND")
    else:
        blockers.append("MULTIPLE_NORMALIZER_DEFINITIONS")

    if all(signals.values()):
        reasons.append("RENDERER_PRELOAD_MAIN_PACKAGED_STATIC_PATH_COMPLETE")
    else:
        missing = [k for k, v in signals.items() if not v]
        blockers.append("STATIC_PATH_GAPS:" + ",".join(missing))

    if baseline.get("fail_count") == 0:
        reasons.append("CURRENT_SOURCE_BASELINE_VALIDATORS_PASS")
    else:
        blockers.append(f"BASELINE_VALIDATOR_FAILURES:{baseline.get('fail_count')}")

    # Determine what another repair must cover BEFORE it is written.
    required_scope = []
    for d in defs:
        required_scope.append(d["path"])
    required_scope.append("electron/tests/validate-stage59b-search.js")
    required_scope = sorted(set(required_scope))

    # Downstream revalidation scope is deliberately broader than modified files.
    downstream = [
        "node tests/validate-stage59b-search.js",
        "node tests/validate-packaged-runtime-smoke.js",
        "node tests/validate-stage60c-packaged-relation-smoke.js",
        "node tests/validate-stage59b-ui.js",
        "node tests/validate-stage59b-smoke.js",
        "npm run check",
        "50B / 50C / 50D",
        "validate-release-version.js 0.5.15",
        "1132 ADRG exact-id audit",
        "B018 renderer request normalizer bridge",
        "F022 / P651 / F212 official-source regression",
        "Actual tracked diff guard",
        "new fix commit only after Shadow+Actual PASS",
        "new workflow_dispatch RC",
        "tag/release only after RC success",
    ]

    if (
        blockers == ["NORMALIZER_OBJECT_ADRG_NOT_PRESERVED"]
        and len(defs) == 1
    ):
        readiness = "READY_FOR_GENERALIZED_NORMALIZER_REPAIR_DESIGN"
    elif (
        "NORMALIZER_OBJECT_ADRG_NOT_PRESERVED" in blockers
        and len(defs) == 1
        and all(not b.startswith(("SERVICE_LAYER", "PACKAGED_FIXTURE", "STATIC_PATH")) for b in blockers if b != "NORMALIZER_OBJECT_ADRG_NOT_PRESERVED")
    ):
        readiness = "READY_FOR_GENERALIZED_NORMALIZER_REPAIR_DESIGN_WITH_BASELINE_REVIEW"
    else:
        readiness = "NEEDS_MULTI_LAYER_REPAIR_DESIGN"

    return {
        "normalized_object_ADRG_result": normalized_type,
        "reasons": reasons,
        "blockers": blockers,
        "required_repair_file_scope": required_scope,
        "required_downstream_validation_scope": downstream,
        "readiness": readiness,
    }


def write_report(payload):
    REPORT_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    c = payload.get("classification") or {}
    s = payload.get("service_probe") or {}
    cp = payload.get("contract_probe") or {}
    pf = payload.get("packaged_fixture") or {}
    baseline = payload.get("baseline") or {}
    locations = payload.get("normalizer_locations") or {}

    # Keep TXT/Shell compact. Full contexts/source are in JSON.
    probe = (cp.get("probes") or {}).get("object_ADRG") or {}
    probe_value = probe.get("value") if probe.get("ok") else None

    lines = [
        "KDRG V4.7 Electron Stage67I4A / 0.5.15 Full Pipeline Audit R1",
        "=" * 92,
        f"status={payload['status']}",
        f"readiness={c.get('readiness', '')}",
        "",
        "[STATE]",
        json.dumps({
            "head": (payload.get("state") or {}).get("head"),
            "origin_main": (payload.get("state") or {}).get("origin_main"),
            "tracked_clean": (payload.get("state") or {}).get("tracked_clean"),
            "staging_empty": (payload.get("state") or {}).get("staging_empty"),
            "release_tag_absent": (payload.get("state") or {}).get("release_tag_absent"),
            "release_absent": (payload.get("state") or {}).get("release_absent"),
        }, ensure_ascii=False, indent=2),
        "",
        "[NORMALIZER]",
        json.dumps({
            "definition_count": locations.get("definition_count"),
            "definitions": locations.get("definitions"),
            "exports": cp.get("exports"),
            "function_type": cp.get("normalize_type"),
            "function_length": cp.get("normalize_length"),
            "object_ADRG_probe_ok": probe.get("ok"),
            "object_ADRG_probe_value": probe_value,
            "object_ADRG_probe_error": probe.get("error"),
        }, ensure_ascii=False, indent=2),
        "",
        "[SERVICE / PACKAGED]",
        json.dumps({
            "B018_exact_count": s.get("b018_exact_count"),
            "ADRG_count": s.get("adrg_count"),
            "collision_count": s.get("collision_count"),
            "ADRG_failure_count": s.get("failure_count"),
            "fixture_all_query_equals_adrg": pf.get("all_search_query_equals_adrg"),
            "fixture_filter_adrg": pf.get("filter_adrg"),
            "fixture_selector_adrg": pf.get("selector_adrg"),
        }, ensure_ascii=False, indent=2),
        "",
        "[BASELINE]",
        json.dumps({
            "pass_count": baseline.get("pass_count"),
            "fail_count": baseline.get("fail_count"),
            "failed_commands": [
                x["cmd"]
                for x in baseline.get("results", [])
                if x.get("returncode") != 0
            ],
        }, ensure_ascii=False, indent=2),
        "",
        "[CLASSIFICATION]",
        json.dumps({
            "normalized_object_ADRG_result": c.get("normalized_object_ADRG_result"),
            "reasons": c.get("reasons"),
            "blockers": c.get("blockers"),
            "required_repair_file_scope": c.get("required_repair_file_scope"),
            "required_downstream_validation_count":
                len(c.get("required_downstream_validation_scope") or []),
        }, ensure_ascii=False, indent=2),
        "",
    ]

    if payload.get("error"):
        lines += ["[BLOCKER]", payload["error"].splitlines()[0], ""]

    lines += [
        "[STOP]",
        "audit only; no repair / Actual apply / commit / push / RC / tag / release",
        f"report_json={REPORT_JSON}",
    ]

    REPORT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    payload = {
        "status": "FAIL",
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "state": {},
        "normalizer_locations": {},
        "contract_probe": {},
        "service_probe": {},
        "paths": {},
        "trace": {},
        "stale_public_refs": {},
        "packaged_fixture": {},
        "future_risk_validators": {},
        "baseline": {},
        "classification": {},
        "error": None,
    }

    try:
        payload["state"] = repo_state()
        payload["normalizer_locations"] = scan_normalizer_locations()
        payload["contract_probe"] = contract_runtime_probe()
        payload["service_probe"] = service_runtime_probe()
        payload["paths"] = package_paths()
        payload["trace"] = trace_search_path(payload["paths"])
        payload["stale_public_refs"] = scan_stale_public_refs(payload["paths"])
        payload["packaged_fixture"] = packaged_fixture_audit()
        payload["future_risk_validators"] = validator_future_risk_audit()
        payload["baseline"] = baseline_validations()

        # Final tracked-state guard after every validator.
        require(not git_lines("diff", "--name-only"), "audit changed tracked worktree")
        require(not git_lines("diff", "--cached", "--name-only"), "audit changed staging")

        payload["classification"] = classify(payload)
        payload["status"] = "PASS"

    except Exception as exc:
        payload["error"] = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"

    payload["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    write_report(payload)

    if payload["status"] == "PASS":
        c = payload["classification"]
        s = payload["service_probe"]
        cp = payload["contract_probe"]
        probe = (cp.get("probes") or {}).get("object_ADRG") or {}
        value = probe.get("value") if probe.get("ok") else {}
        normalized = None
        if isinstance(value, dict):
            normalized = value.get("entityType") or value.get("entity_type")

        print("[PASS] Stage67I4A / 0.5.15 Full Pipeline Audit R1")
        print(f"readiness={c['readiness']}")
        print(
            f"normalizer_defs={payload['normalizer_locations']['definition_count']} "
            f"object_ADRG={normalized or probe.get('error')}"
        )
        print(
            f"service_B018_exact={s.get('b018_exact_count')} "
            f"ADRG_audit={s.get('adrg_count')}/"
            f"{s.get('failure_count')}fail "
            f"collisions={s.get('collision_count')}"
        )
        print(
            f"packaged_fixture="
            f"query:{payload['packaged_fixture'].get('all_search_query_equals_adrg')} "
            f"filter:{payload['packaged_fixture'].get('filter_adrg')} "
            f"selector:{payload['packaged_fixture'].get('selector_adrg')}"
        )
        print(
            f"baseline_validations="
            f"{payload['baseline'].get('pass_count')}PASS/"
            f"{payload['baseline'].get('fail_count')}FAIL"
        )
        print(
            "repair_scope="
            + ",".join(c.get("required_repair_file_scope") or [])
        )
        print(
            "blockers="
            + (";".join(c.get("blockers") or []) or "NONE")
        )
        print("[STOP] comprehensive audit only; no repair/RC/tag/release")
        print(f"report_txt={REPORT_TXT}")
        print(f"report_json={REPORT_JSON}")
        return 0

    print("[FAIL] Stage67I4A / 0.5.15 Full Pipeline Audit R1")
    if payload.get("error"):
        print("[BLOCKER] " + payload["error"].splitlines()[0])
    print("[STOP] audit only; no repair/RC/tag/release")
    print(f"report_txt={REPORT_TXT}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
