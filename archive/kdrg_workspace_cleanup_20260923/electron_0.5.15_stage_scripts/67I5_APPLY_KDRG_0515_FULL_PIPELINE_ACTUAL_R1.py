#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KDRG V4.7 Electron Stage67I5
0.5.15 Full Search Pipeline Actual Apply R1

Gate
----
Requires Stage67I4B Shadow R4 PASS:
  READY_FOR_0515_FULL_PIPELINE_ACTUAL_APPLY

Applies exactly four files from the verified Shadow manifest:
1. .github/workflows/build-electron-windows.yml
2. electron/src/search-result-contract.js
3. electron/tests/validate-packaged-runtime-smoke.js
4. electron/tests/validate-stage59b-search.js

Then repeats the important semantic/full-pipeline validations on Actual:
- public normalizer CODE/ADRG/ALL -> scalar strings
- AADRG/RDRG/TABLE/INVALID rejection preserved
- all 1132 ADRG exact IDs through normalizer -> service
- all 471 ADRG/CODE collisions preserve CODE/ALL behavior
- packaged fixtures B013/B014/B018/B022/L033/9610
- renderer/preload/main/packaged stable wiring
- workflow failure diagnostics before Write-Error
- stage59b/stage60c/packaged tests + npm run check
- 50B / 50C / 50D
- release version 0.5.15
- F022 / P651 / F212
- runtime / official-condition / icon immutability
- exact four-file tracked delta, staging empty, tag/release absent

On any failure after copy, all four files are restored to the exact pre-apply bytes.

NO commit / push / RC / tag / release.
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

SHADOW_REPORT = ROOT / "stage67i4b_0515_full_pipeline_shadow_r4.json"
MANIFEST_JSON = ROOT / "stage67i4b_0515_full_pipeline_apply_manifest_r4.json"

REPORT_TXT = ROOT / "stage67i5_0515_full_pipeline_actual_r1.txt"
REPORT_JSON = ROOT / "stage67i5_0515_full_pipeline_actual_r1.json"

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
    WORKFLOW_REL,
    "electron/src/search-result-contract.js",
    "electron/tests/validate-packaged-runtime-smoke.js",
    "electron/tests/validate-stage59b-search.js",
]

FIXTURES = ["B013", "B014", "B018", "B022", "L033", "9610"]

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
    require(SHADOW_REPORT.is_file(), "Stage67I4B Shadow R4 report JSON missing")
    require(MANIFEST_JSON.is_file(), "Stage67I4B Shadow R4 manifest missing")

    report = json.loads(SHADOW_REPORT.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST_JSON.read_text(encoding="utf-8"))

    require(report.get("status") == "PASS", "Shadow R4 report is not PASS")
    require(
        report.get("readiness") == "READY_FOR_0515_FULL_PIPELINE_ACTUAL_APPLY",
        "Shadow R4 readiness mismatch",
    )
    require(manifest.get("status") == "PASS", "Shadow manifest is not PASS")
    require(
        manifest.get("readiness") == "READY_FOR_0515_FULL_PIPELINE_ACTUAL_APPLY",
        "Shadow manifest readiness mismatch",
    )
    require(
        manifest.get("schema_version") == "kdrg-0515-full-pipeline-repair-v4",
        "Shadow manifest schema mismatch",
    )
    require(manifest.get("target_version") == VERSION, "target version mismatch")
    require(manifest.get("apply_file_count") == 4, "apply file count mismatch")

    entries = manifest.get("apply_files") or []
    require(len(entries) == 4, "manifest apply_files count mismatch")

    by_path = {str(x.get("path")): x for x in entries}
    require(
        sorted(by_path) == sorted(TARGETS),
        "manifest target set mismatch",
    )

    base_commit = manifest.get("base_commit")
    require(base_commit, "manifest base commit missing")

    return {
        "base_commit": base_commit,
        "entries": by_path,
        "repair_contract": manifest.get("repair_contract") or {},
    }


def preflight(gate):
    base = gate["base_commit"]

    require(git_text("rev-parse", "HEAD") == base, "HEAD != manifest base commit")
    require(remote_main_sha() == base, "origin/main != manifest base commit")
    require(git_text("branch", "--show-current") == "main", "branch != main")
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

    before = {}

    for rel in TARGETS:
        entry = gate["entries"][rel]
        actual = ROOT / rel
        source = Path(str(entry.get("source") or ""))

        require(actual.is_file(), f"Actual target missing: {rel}")
        require(source.is_file(), f"Shadow source missing: {source}")

        actual_sha = sha256_path(actual)
        source_sha = sha256_path(source)

        require(
            actual_sha == entry.get("actual_before_sha256"),
            f"Actual pre-apply SHA mismatch: {rel}",
        )
        require(
            source_sha == entry.get("shadow_apply_sha256"),
            f"Shadow source SHA mismatch: {rel}",
        )
        require(
            actual_sha != source_sha,
            f"target already equals Shadow candidate: {rel}",
        )

        before[rel] = {
            "actual_before_sha256": actual_sha,
            "shadow_apply_sha256": source_sha,
            "shadow_source": str(source),
        }

    return {
        "head": base,
        "origin_main": base,
        "target_count": 4,
        "sha_contract": before,
        "worktree_clean": True,
        "staging_empty": True,
        "release_tag_absent": True,
        "release_absent": True,
    }


def create_backups():
    backup_root = Path(tempfile.mkdtemp(prefix="kdrg_stage67i5_backup_"))
    mapping = {}
    for rel in TARGETS:
        src = ROOT / rel
        dst = backup_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        mapping[rel] = str(dst)
    return backup_root, mapping


def apply_exact(gate):
    applied = {}
    for rel in TARGETS:
        entry = gate["entries"][rel]
        source = Path(entry["source"])
        target = ROOT / rel

        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

        actual_sha = sha256_path(target)
        expected = entry["shadow_apply_sha256"]
        require(actual_sha == expected, f"post-copy SHA mismatch: {rel}")
        applied[rel] = actual_sha

    changed = sorted(git_lines("diff", "--name-only"))
    require(changed == sorted(TARGETS),
            "Actual tracked delta is not exact 4 files: " + json.dumps(changed))

    require(not git_lines("diff", "--cached", "--name-only"), "staging is not empty")

    diff_check = run(["git", "diff", "--check"], check=False)
    require(diff_check["returncode"] == 0,
            "Actual git diff --check failed:\n" + diff_check["output"])

    return {
        "applied_sha256": applied,
        "tracked_diff_files": changed,
        "git_diff_check": "PASS",
    }


def contract_probe():
    js = r"""
'use strict';
const c = require('./src/search-result-contract');
const fn = c.normalizeSearchRequest;

function safe(type) {
  try {
    const v = fn({query:'B018',entityType:type,limit:100,offset:0});
    return {
      ok:true,
      entityType:v?.entityType,
      entityTypeType:Array.isArray(v?.entityType) ? 'array' : typeof v?.entityType
    };
  } catch (e) {
    return {ok:false,error:String(e && e.message || e)};
  }
}

console.log(JSON.stringify({
  public_types:c.SEARCH_ENTITY_TYPES,
  CODE:safe('CODE'),
  ADRG:safe('ADRG'),
  ALL:safe('ALL'),
  AADRG:safe('AADRG'),
  RDRG:safe('RDRG'),
  TABLE:safe('TABLE'),
  INVALID:safe('INVALID')
}));
"""
    r = run(["node", "-e", js], cwd=ELECTRON, check=False, timeout=600)
    require(r["returncode"] == 0, "contract probe failed:\n" + r["output"])
    data = json.loads(r["output"].strip().splitlines()[-1])

    require(data.get("public_types") == ["CODE", "ADRG"], "public type list changed")

    for key in ["CODE", "ADRG", "ALL"]:
        item = data.get(key) or {}
        require(item.get("ok") is True, f"{key} normalizer failed: {item}")
        require(item.get("entityType") == key, f"{key} scalar value mismatch")
        require(item.get("entityTypeType") == "string", f"{key} is not scalar string")

    for key in ["AADRG", "RDRG", "TABLE", "INVALID"]:
        item = data.get(key) or {}
        require(item.get("ok") is False, f"{key} should be rejected")
        require(
            "사용자 검색에서 지원하지 않는 유형입니다"
            in str(item.get("error") or ""),
            f"{key} rejection message changed",
        )

    return data


def normalized_full_audit():
    fixtures = json.dumps(FIXTURES)

    js = rf"""
'use strict';
const path = require('node:path');
const {{ normalizeSearchRequest }} = require('./src/search-result-contract');
const {{ KdrgSearchService }} = require('./src/kdrg-search-service');

const s = new KdrgSearchService(
  path.resolve('..','data','kdrg_v47_search_integrated_v3.json')
);

const ids = [...s.recordMaps.ADRG.keys()].map(String).sort();
const codeIds = new Set([...s.recordMaps.CODE.keys()].map(String));
const collisions = ids.filter(x => codeIds.has(x));
const fixtures = {fixtures};

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
    failures.push({{id,reason:'NORMALIZER_TYPE',actual:req.entityType}});
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

let collisionChanges = [];
for (const id of collisions) {{
  for (const type of ['CODE','ALL']) {{
    const req = normalizeSearchRequest({{
      query:id,
      entityType:type,
      limit:500,
      offset:0
    }});
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
      collisionChanges.push({{id,type}});
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
  const ok = (r.results || []).some(
    x => x.entity_type === 'ADRG' && x.entity_id === id
  );
  if (!ok) fixtureFailures.push(id);
}}

console.log(JSON.stringify({{
  adrg_count:ids.length,
  collision_count:collisions.length,
  normalized_adrg_failure_count:failures.length,
  normalized_adrg_failure_sample:failures.slice(0,20),
  collision_behavior_change_count:collisionChanges.length,
  collision_behavior_change_sample:collisionChanges.slice(0,20),
  fixture_failure_count:fixtureFailures.length,
  fixture_failures:fixtureFailures
}}));
"""

    r = run(["node", "-e", js], cwd=ELECTRON, check=False, timeout=2400)
    require(r["returncode"] == 0, "normalized full audit failed:\n" + r["output"])
    data = json.loads(r["output"].strip().splitlines()[-1])

    require(data.get("adrg_count") == 1132, "ADRG count mismatch")
    require(data.get("collision_count") == 471, "collision count mismatch")
    require(data.get("normalized_adrg_failure_count") == 0,
            "normalized ADRG failures remain")
    require(data.get("collision_behavior_change_count") == 0,
            "CODE/ALL collision behavior changed")
    require(data.get("fixture_failure_count") == 0,
            "packaged fixture bridge failures remain")

    return data


def stable_wiring_audit():
    package = json.loads((ELECTRON / "package.json").read_text(encoding="utf-8"))
    main_path = ELECTRON / package["main"]
    main = main_path.read_text(encoding="utf-8")
    app = (ELECTRON / "renderer/app.js").read_text(encoding="utf-8")
    packaged = (ELECTRON / "src/packaged-runtime-smoke.js").read_text(encoding="utf-8")

    preload_candidates = [
        ELECTRON / "src/preload.js",
        ELECTRON / "preload.js",
        main_path.parent / "preload.js",
    ]
    preload_path = next((p for p in preload_candidates if p.is_file()), None)
    require(preload_path is not None, "preload source missing")
    preload = preload_path.read_text(encoding="utf-8")

    checks = {
        "renderer_calls_window_search": "window.KDRG.search" in app,
        "renderer_carries_entity_type": "entityType" in app or "entity_type" in app,
        "preload_invokes_kdrg_search":
            "ipcRenderer.invoke" in preload and "kdrg:search" in preload,
        "main_handles_kdrg_search":
            "ipcMain.handle" in main and "kdrg:search" in main,
        "main_uses_normalizeSearchRequest":
            "normalizeSearchRequest" in main,
        "packaged_filter_adrg":
            "filter.value = 'ADRG';" in packaged,
        "packaged_uses_fixture_query":
            "fixture.search_query" in packaged,
        "packaged_selector_adrg":
            'data-entity-type="ADRG"' in packaged and "fixture.adrg" in packaged,
    }
    missing = [k for k, v in checks.items() if not v]
    require(not missing, "stable wiring failed: " + json.dumps(missing))
    return checks


def workflow_audit():
    text = (ROOT / WORKFLOW_REL).read_text(encoding="utf-8")

    error = 'Write-Error "packaged 핵심검증 실패"'
    marker = "Stage67I4B: emit diagnostics before terminating"
    diagnostics = [
        ('status', 'Write-Host "status=$($report.status)"'),
        ('failed_step', 'Write-Host "failed_step=$($report.failed_step)"'),
        ('missing_steps', 'Write-Host "missing_steps=$($missing -join \',\')"'),
        ('message', 'Write-Host "message=$message"'),
    ]

    require(text.count(error) == 1, "workflow hard-failure Write-Error count mismatch")
    require(text.count(marker) == 1, "workflow diagnostic marker count mismatch")
    require("$uiWarningOnly" in text, "workflow UI-warning branch missing")
    require("[PASS_WITH_UI_WARNING]" in text, "workflow UI-warning marker missing")
    require("packaged_ui_validation" in text, "workflow packaged UI gate missing")

    marker_pos = text.index(marker)
    error_pos = text.index(error)
    positions = {}

    for key, needle in diagnostics:
        positions_all = [m.start() for m in re.finditer(re.escape(needle), text)]
        local = [p for p in positions_all if marker_pos < p < error_pos]
        require(len(local) == 1, f"workflow local {key} diagnostic mismatch")
        positions[key] = local[0]

    require(
        marker_pos
        < positions["status"]
        < positions["failed_step"]
        < positions["missing_steps"]
        < positions["message"]
        < error_pos,
        "workflow diagnostics are not before Write-Error",
    )

    return {
        "diagnostics_before_error": True,
        "warning_branch_preserved": True,
        "packaged_ui_gate_present": True,
    }


def official_regression():
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
    r = run(["node", "-e", js], cwd=ELECTRON, check=False, timeout=600)
    require(r["returncode"] == 0, "official regression failed:\n" + r["output"])


def validate_actual():
    commands = []

    def check(cmd, cwd=None, timeout=1800):
        r = run(cmd, cwd=cwd or ROOT, check=False, timeout=timeout)
        commands.append(r)
        require(
            r["returncode"] == 0,
            f"validation failed: {' '.join(cmd)}\n{r['output']}",
        )

    check(["node", "--check", "src/search-result-contract.js"], cwd=ELECTRON)
    check(["node", "--check", "tests/validate-stage59b-search.js"], cwd=ELECTRON)
    check(["node", "--check", "tests/validate-packaged-runtime-smoke.js"], cwd=ELECTRON)

    contract = contract_probe()
    full = normalized_full_audit()
    wiring = stable_wiring_audit()
    workflow = workflow_audit()

    check(["node", "tests/validate-stage59b-search.js"], cwd=ELECTRON)
    check(["node", "tests/validate-packaged-runtime-smoke.js"], cwd=ELECTRON)
    check(["node", "tests/validate-stage60c-packaged-relation-smoke.js"], cwd=ELECTRON)
    check(["node", "tests/validate-stage59b-ui.js"], cwd=ELECTRON)
    check(["node", "tests/validate-stage59b-smoke.js"], cwd=ELECTRON)
    check(["npm", "run", "check"], cwd=ELECTRON, timeout=1800)

    for rel in ROOT_VALIDATORS:
        check(["python", rel], cwd=ROOT, timeout=1800)

    check(["node", "tests/validate-release-version.js", VERSION],
          cwd=ELECTRON, timeout=600)

    official_regression()

    require(sha256_path(ROOT / RUNTIME_REL) == RUNTIME_SHA, "runtime changed")
    require(sha256_path(ROOT / OFFICIAL_REL) == OFFICIAL_SHA,
            "official condition changed")
    require(sha256_path(ROOT / ICON_PNG_REL) == ICON_PNG_SHA,
            "PNG icon changed")
    require(sha256_path(ROOT / ICON_ICO_REL) == ICON_ICO_SHA,
            "ICO icon changed")

    changed = sorted(git_lines("diff", "--name-only"))
    require(changed == sorted(TARGETS), "Actual delta changed during validation")
    require(not git_lines("diff", "--cached", "--name-only"), "staging not empty")

    diff_check = run(["git", "diff", "--check"], check=False)
    require(diff_check["returncode"] == 0,
            "final git diff --check failed:\n" + diff_check["output"])

    return {
        "contract": contract,
        "normalized_full_audit": full,
        "stable_wiring": wiring,
        "workflow": workflow,
        "npm_run_check": "PASS",
        "stage59b_stage60c_packaged": "PASS",
        "root_50b_50c_50d": "PASS",
        "release_version": "PASS",
        "official_regression": "PASS",
        "git_diff_check": "PASS",
        "commands": commands,
    }


def final_guard(gate):
    base = gate["base_commit"]

    require(git_text("rev-parse", "HEAD") == base, "HEAD changed during Actual apply")
    require(remote_main_sha() == base, "origin/main changed during Actual apply")
    require(git_text("branch", "--show-current") == "main", "branch changed")

    changed = sorted(git_lines("diff", "--name-only"))
    require(changed == sorted(TARGETS), "final tracked delta is not exact 4 files")
    require(not git_lines("diff", "--cached", "--name-only"), "final staging not empty")

    for rel in TARGETS:
        expected = gate["entries"][rel]["shadow_apply_sha256"]
        require(sha256_path(ROOT / rel) == expected, f"final candidate SHA mismatch: {rel}")

    require(not local_tag_sha(RELEASE_TAG), "0.5.15 local tag appeared")
    require(not remote_tag_sha(RELEASE_TAG), "0.5.15 remote tag appeared")
    require(not release_exists(RELEASE_TAG), "0.5.15 Release appeared")

    return {
        "head": base,
        "origin_main": base,
        "tracked_delta": changed,
        "staging_empty": True,
        "candidate_sha_exact": True,
        "release_tag_absent": True,
        "release_absent": True,
    }


def rollback(backup_map, base_commit):
    result = {
        "performed": False,
        "restored_files": [],
        "clean_after_restore": False,
        "staging_empty_after_restore": False,
        "head_preserved": False,
        "origin_preserved": False,
    }

    if not backup_map:
        return result

    for rel, backup in backup_map.items():
        shutil.copy2(backup, ROOT / rel)
        result["restored_files"].append(rel)

    # Never use reset --hard. Only exact files are restored.
    run(["git", "reset", "--", *TARGETS], check=False)

    result["performed"] = True
    result["clean_after_restore"] = not bool(git_lines("diff", "--name-only"))
    result["staging_empty_after_restore"] = not bool(
        git_lines("diff", "--cached", "--name-only")
    )
    result["head_preserved"] = git_text("rev-parse", "HEAD") == base_commit
    result["origin_preserved"] = remote_main_sha() == base_commit

    return result


def write_report(payload):
    REPORT_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    validation = payload.get("validation") or {}
    full = validation.get("normalized_full_audit") or {}

    lines = [
        "KDRG V4.7 Electron Stage67I5 / 0.5.15 Full Search Pipeline Actual Apply R1",
        "=" * 104,
        f"status={payload['status']}",
        f"readiness={payload['readiness']}",
        "",
        "[APPLY]",
        json.dumps(payload.get("apply", {}), ensure_ascii=False, indent=2),
        "",
        "[VALIDATION SUMMARY]",
        json.dumps({
            "ADRG_count": full.get("adrg_count"),
            "collision_count": full.get("collision_count"),
            "normalized_ADRG_failures":
                full.get("normalized_adrg_failure_count"),
            "CODE_ALL_collision_changes":
                full.get("collision_behavior_change_count"),
            "fixture_failures":
                full.get("fixture_failure_count"),
            "npm_run_check":
                validation.get("npm_run_check"),
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
        "- PASS이면 정확한 4개 Actual 변경만 남고 아직 staging/commit/push 없음.",
        "- 다음 단계는 exact 4-file fix commit + push + 새 workflow_dispatch RC.",
        "- RC success 전 electron-v0.5.15 tag/release 금지.",
        "",
        f"report_json={REPORT_JSON}",
    ]

    REPORT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    payload = {
        "status": "FAIL",
        "readiness": "NOT_READY_FOR_0515_FIX_COMMIT_PUSH_RC",
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "gate": {},
        "preflight": {},
        "apply": {},
        "validation": {},
        "final_guard": {},
        "rollback": {"performed": False},
        "error": None,
    }

    backup_root = None
    backup_map = {}
    base_commit = None
    copied = False

    try:
        payload["gate"] = load_gate()
        base_commit = payload["gate"]["base_commit"]

        payload["preflight"] = preflight(payload["gate"])

        backup_root, backup_map = create_backups()
        payload["apply"] = apply_exact(payload["gate"])
        copied = True

        payload["validation"] = validate_actual()
        payload["final_guard"] = final_guard(payload["gate"])

        payload["status"] = "PASS"
        payload["readiness"] = "READY_FOR_0515_FIX_COMMIT_PUSH_RC"

    except Exception as exc:
        payload["error"] = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"

        if copied and base_commit and backup_map:
            try:
                payload["rollback"] = rollback(backup_map, base_commit)
            except Exception as rollback_exc:
                payload["rollback"] = {
                    "performed": True,
                    "rollback_error":
                        f"{type(rollback_exc).__name__}: {rollback_exc}",
                }

    finally:
        if backup_root and backup_root.exists():
            shutil.rmtree(backup_root, ignore_errors=True)

    payload["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    write_report(payload)

    if payload["status"] == "PASS":
        full = payload["validation"]["normalized_full_audit"]
        print("[PASS] Stage67I5 / 0.5.15 Full Search Pipeline Actual Apply R1")
        print("readiness=READY_FOR_0515_FIX_COMMIT_PUSH_RC")
        print("[PASS] exact 4-file Actual apply / git diff --check")
        print(
            f"[PASS] normalized ADRG audit={full['adrg_count']} / "
            f"collisions={full['collision_count']} / "
            f"failures={full['normalized_adrg_failure_count']}"
        )
        print(
            f"[PASS] CODE/ALL collision changes="
            f"{full['collision_behavior_change_count']} / "
            f"fixture failures={full['fixture_failure_count']}"
        )
        print("[PASS] supported entityType scalar / hidden types rejection preserved")
        print("[PASS] workflow diagnostic ordering + stable wiring")
        print("[PASS] npm + stage59b/stage60c + 50B/50C/50D + release-version")
        print("[PASS] F022/P651/F212 + runtime/icon/official-condition")
        print("[PASS] staging empty / 0.5.15 tag+release absent")
        print("[STOP] no commit/push/RC/tag/release")
        print(f"report_txt={REPORT_TXT}")
        return 0

    print("[FAIL] Stage67I5 / 0.5.15 Full Search Pipeline Actual Apply R1")
    print("readiness=NOT_READY_FOR_0515_FIX_COMMIT_PUSH_RC")
    if payload.get("error"):
        print("[BLOCKER] " + payload["error"].splitlines()[0])

    rb = payload.get("rollback") or {}
    if rb.get("performed"):
        print(
            "[ROLLBACK] "
            f"clean={rb.get('clean_after_restore')} "
            f"staging_empty={rb.get('staging_empty_after_restore')} "
            f"head_preserved={rb.get('head_preserved')} "
            f"origin_preserved={rb.get('origin_preserved')}"
        )

    print("[STOP] no commit/push/RC/tag/release")
    print(f"report_txt={REPORT_TXT}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
