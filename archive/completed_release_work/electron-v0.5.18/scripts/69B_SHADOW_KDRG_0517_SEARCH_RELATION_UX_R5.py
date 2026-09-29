from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path.cwd()
REPORT_DIR = ROOT / "reports" / "stage69b_0517_search_relation_ux_shadow_r5"
SHADOW = REPORT_DIR / "shadow"
REPORT_JSON = REPORT_DIR / "shadow.json"
REPORT_TXT = REPORT_DIR / "shadow_summary.txt"

BASE_COMMIT = "d1c1b126fee9f7bd3e226d4cfcee77e863baec0c"
BASE_VERSION = "0.5.16"
RUNTIME_SHA = "1a3d50400567ecaad9695b7be8e7c0382131f8652f398e010cf01f4d8dda6c58"

SERVICE_REL = Path("electron/src/kdrg-search-service.js")
APP_REL = Path("electron/renderer/app.js")
SEARCH_VALIDATOR_REL = Path("electron/tests/validate-stage59b-search.js")
NEW_VALIDATOR_REL = Path("electron/tests/validate-stage69b-0517-search-relation-ux.js")
RUNTIME_REL = Path("data/kdrg_v47_search_integrated_v3.json")

SERVICE_MARKER = "STAGE69B_EXACT_SHARED_PUBLIC_ID_V1"
APP_CLASS_MARKER = "STAGE69B_RELATION_RESULT_CLASSIFICATION_TITLE_ROW"
APP_CONDITION_MARKER = "loadRelationOfficialAdrgConditions"

SERVICE_PATCH = "\n/* STAGE69B_EXACT_SHARED_PUBLIC_ID_V1 */\nconst STAGE69B_ORIGINAL_SEARCH = KdrgSearchService.prototype.search;\n\nKdrgSearchService.prototype.search = function stage69bExactSharedPublicIdSearch(\n  query,\n  entityType = 'ALL',\n  options = {},\n) {\n  const base = STAGE69B_ORIGINAL_SEARCH.call(this, query, entityType, options);\n  const requestedType = String(entityType ?? 'ALL').trim().toUpperCase();\n  if (requestedType !== 'ALL' || !base || typeof base.then === 'function') return base;\n\n  const rawQuery = String(query ?? '').trim();\n  if (!rawQuery) return base;\n\n  const codeId = normalizeEntityId(rawQuery, 'CODE');\n  const adrgId = normalizeEntityId(rawQuery, 'ADRG');\n  const isSharedExactId = Boolean(\n    codeId\n    && adrgId\n    && this.recordMaps?.CODE?.has(codeId)\n    && this.recordMaps?.ADRG?.has(adrgId)\n  );\n  if (!isSharedExactId) return base;\n\n  const probeOptions = {\n    ...(options ?? {}),\n    offset: 0,\n    limit: 5000,\n  };\n  const codeResponse = STAGE69B_ORIGINAL_SEARCH.call(this, rawQuery, 'CODE', probeOptions);\n  const adrgResponse = STAGE69B_ORIGINAL_SEARCH.call(this, rawQuery, 'ADRG', probeOptions);\n\n  const exactCode = (codeResponse?.results ?? []).find(\n    (row) => String(row?.entity_type ?? '').toUpperCase() === 'CODE'\n      && normalizeEntityId(row?.entity_id, 'CODE') === codeId,\n  );\n  const exactAdrg = (adrgResponse?.results ?? []).find(\n    (row) => String(row?.entity_type ?? '').toUpperCase() === 'ADRG'\n      && normalizeEntityId(row?.entity_id, 'ADRG') === adrgId,\n  );\n\n  if (!exactCode || !exactAdrg) return base;\n\n  const exactResults = [exactCode, exactAdrg];\n  const offset = Number.isFinite(Number(base.offset))\n    ? Math.max(0, Number(base.offset))\n    : Math.max(0, Number(options?.offset) || 0);\n  const limit = Number.isFinite(Number(base.limit))\n    ? Math.max(1, Number(base.limit))\n    : Math.max(1, Number(options?.limit) || 50);\n\n  const typeCounts = {};\n  for (const key of Object.keys(base.type_counts ?? {})) typeCounts[key] = 0;\n  typeCounts.CODE = 1;\n  typeCounts.ADRG = 1;\n\n  return {\n    ...base,\n    total_count: exactResults.length,\n    type_counts: typeCounts,\n    results: exactResults.slice(offset, offset + limit),\n  };\n};\n"
APP_HELPER = "\nasync function loadRelationOfficialAdrgConditions(candidate, host) {\n  host.replaceChildren(\n    create('p', 'muted', 'ADRG 분류 조건을 불러오는 중입니다.'),\n  );\n  try {\n    const payload = await window.KDRG.getDetail({\n      entityType: 'ADRG',\n      entityId: candidate.entity_id,\n    });\n    if (!host.isConnected) return;\n\n    const detail = payload?.detail;\n    if (!detail) {\n      throw new Error(`ADRG ${candidate.entity_id} 상세정보 없음`);\n    }\n\n    const fragment = document.createDocumentFragment();\n    fragment.append(\n      renderUserConditionSummary(detail),\n      renderUserConditionTables(detail),\n    );\n    if (SHOW_DEVELOPER_METADATA) {\n      fragment.append(renderUserConditionEvidence(detail));\n    }\n    host.replaceChildren(fragment);\n  } catch (error) {\n    if (!host.isConnected) return;\n    host.replaceChildren(\n      create(\n        'p',\n        'error-message',\n        error?.message || 'ADRG 분류 조건을 불러오지 못했습니다.',\n      ),\n    );\n  }\n}\n"
NEW_VALIDATOR = "'use strict';\n\nconst assert = require('node:assert/strict');\nconst fs = require('node:fs');\nconst path = require('node:path');\nconst { KdrgSearchService } = require('../src/kdrg-search-service');\n\nconst ROOT = path.resolve(__dirname, '..', '..');\nconst service = new KdrgSearchService(\n  path.join(ROOT, 'data', 'kdrg_v47_search_integrated_v3.json'),\n);\nconst app = fs.readFileSync(\n  path.join(ROOT, 'electron', 'renderer', 'app.js'),\n  'utf8',\n);\n\nlet pass = 0;\nconst failures = [];\n\nfunction check(name, fn) {\n  try {\n    fn();\n    pass += 1;\n  } catch (error) {\n    failures.push(`${name}: ${error.message}`);\n  }\n}\n\nconst shared = [...service.recordMaps.CODE.keys()]\n  .filter((id) => service.recordMaps.ADRG.has(id))\n  .sort();\n\ncheck('shared namespace count remains 471', () => {\n  assert.equal(shared.length, 471);\n});\n\nfor (const id of shared) {\n  check(`exact shared ALL ${id}`, () => {\n    const response = service.search(id, 'ALL', { limit: 500, offset: 0 });\n    const keys = response.results.map(\n      (row) => `${row.entity_type}:${row.entity_id}`,\n    );\n    assert.deepEqual(keys, [`CODE:${id}`, `ADRG:${id}`]);\n    assert.equal(response.total_count, 2);\n    assert.equal(response.type_counts?.CODE, 1);\n    assert.equal(response.type_counts?.ADRG, 1);\n  });\n}\n\ncheck('F022 exact pair only', () => {\n  const response = service.search('F022', 'ALL', { limit: 500, offset: 0 });\n  assert.deepEqual(\n    response.results.map((row) => `${row.entity_type}:${row.entity_id}`),\n    ['CODE:F022', 'ADRG:F022'],\n  );\n  assert.ok(\n    !response.results.some((row) => row.entity_id === 'U602'),\n    'U602 must not leak into exact shared-ID search',\n  );\n});\n\ncheck('F022 CODE filter preserved', () => {\n  const response = service.search('F022', 'CODE', { limit: 500, offset: 0 });\n  assert.ok(response.results.some(\n    (row) => row.entity_type === 'CODE' && row.entity_id === 'F022',\n  ));\n});\n\ncheck('F022 ADRG filter preserved', () => {\n  const response = service.search('F022', 'ADRG', { limit: 500, offset: 0 });\n  assert.ok(response.results.some(\n    (row) => row.entity_type === 'ADRG' && row.entity_id === 'F022',\n  ));\n});\n\nconst relationFixture = service.relationSearch(\n  [\n    { code: 'I214', codeType: 'AUTO' },\n    { code: 'M6566', codeType: 'AUTO' },\n  ],\n  'AND',\n);\n\ncheck('relation fixture returns expected comparison ADRGs', () => {\n  const ids = new Set(relationFixture.results.map((row) => row.entity_id));\n  for (const id of ['F111', 'F112', 'F121', 'F122']) {\n    assert.ok(ids.has(id), `missing ${id}`);\n  }\n});\n\ncheck('relation fixture carries abc display labels', () => {\n  for (const id of ['F111', 'F112', 'F121', 'F122']) {\n    const row = relationFixture.results.find((item) => item.entity_id === id);\n    assert.ok(row, `missing ${id}`);\n    assert.ok(\n      Array.isArray(row.summary?.abc_display_labels)\n        && row.summary.abc_display_labels.length > 0,\n      `${id} abc_display_labels missing`,\n    );\n  }\n});\n\ncheck('relation result uses abc labels with legacy fallback', () => {\n  assert.match(\n    app,\n    /STAGE69B_RELATION_RESULT_CLASSIFICATION_TITLE_ROW/,\n  );\n  assert.match(\n    app,\n    /result\\.summary\\?\\.abc_display_labels/,\n  );\n  assert.match(\n    app,\n    /result\\.summary\\?\\.classification_code\\s*\\|\\|\\s*result\\.summary\\?\\.classification_display_label/,\n  );\n  assert.match(\n    app,\n    /appendClassificationBadges\\(\\s*relationClassification/,\n  );\n  assert.match(\n    app,\n    /main\\.append\\(relationClassification\\)/,\n  );\n});\n\ncheck('relation detail loads official ADRG detail', () => {\n  assert.match(\n    app,\n    /async function loadRelationOfficialAdrgConditions/,\n  );\n  assert.match(\n    app,\n    /window\\.KDRG\\.getDetail\\(\\{[\\s\\S]*entityType:\\s*'ADRG'[\\s\\S]*candidate\\.entity_id/,\n  );\n});\n\ncheck('relation detail reuses normal ADRG condition renderers', () => {\n  assert.match(app, /renderUserConditionSummary\\(detail\\)/);\n  assert.match(app, /renderUserConditionTables\\(detail\\)/);\n  assert.match(app, /SHOW_DEVELOPER_METADATA[\\s\\S]*renderUserConditionEvidence\\(detail\\)/);\n  assert.match(app, /STAGE69B_RELATION_OFFICIAL_CONDITIONS/);\n});\n\ncheck('normal ADRG detail condition renderers remain present', () => {\n  assert.match(\n    app,\n    /function renderAdrgDetail\\(payload\\)[\\s\\S]*renderUserConditionSummary\\(detail\\)[\\s\\S]*renderUserConditionTables\\(detail\\)/,\n  );\n});\n\nconsole.log(\n  `[${failures.length ? 'FAIL' : 'PASS'}] Stage69B R3 0.5.17 search/relation UX validator: ${pass} PASS / ${failures.length} FAIL`,\n);\nfor (const failure of failures) console.log(`- ${failure}`);\nif (failures.length) process.exitCode = 1;\n"


class Stop(RuntimeError):
    pass


def run(cmd, cwd=ROOT, timeout=1200):
    p = subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    return p.returncode, p.stdout


def require(ok, message):
    if not ok:
        raise Stop(message)


def git_text(*args):
    rc, out = run(["git", *args], timeout=120)
    require(rc == 0, f"git {' '.join(args)} 실패\n{out[-3000:]}")
    return out.strip()


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def node_check(path, cwd):
    rc, out = run(["node", "--check", str(path)], cwd=cwd, timeout=120)
    require(rc == 0, f"node --check FAIL: {path}\n{out[-3000:]}")


def function_span(source, name):
    m = re.search(rf"\bfunction\s+{re.escape(name)}\s*\(", source)
    require(m is not None, f"{name} 함수를 찾지 못함")
    brace = source.find("{", m.end())
    require(brace >= 0, f"{name} 시작 중괄호를 찾지 못함")
    depth = 0
    quote = None
    escape = False
    i = brace
    while i < len(source):
        ch = source[i]
        if quote:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote:
                quote = None
        else:
            if ch in ("'", '"', "`"):
                quote = ch
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return m.start(), i + 1
        i += 1
    raise Stop(f"{name} 함수 끝을 찾지 못함")


def patch_service(source):
    require(SERVICE_MARKER not in source, "Stage69B service marker가 이미 존재함")
    require("class KdrgSearchService" in source, "KdrgSearchService class 없음")
    require("normalizeEntityId" in source, "normalizeEntityId 없음")
    require("module.exports" in source, "module.exports 없음")
    return source.rstrip() + "\n\n" + SERVICE_PATCH.strip() + "\n"


def patch_relation_results(source):
    start, end = function_span(source, "renderRelationResults")
    block = source[start:end]

    require(
        "STAGE69B_RELATION_RESULT_CLASSIFICATION_TITLE_ROW" not in block,
        "관계검색 결과 분류 title-row marker가 이미 존재함",
    )

    exact_old = (
        "appendClassificationBadges(chips, "
        "[result.summary?.classification_code || "
        "result.summary?.classification_display_label]);"
    )
    require(
        block.count(exact_old) == 1,
        "현재 0.5.16 관계검색 결과 분류 anchor 불일치: "
        f"count={block.count(exact_old)}",
    )

    replacement = (
        "/* STAGE69B_RELATION_RESULT_CLASSIFICATION_TITLE_ROW */ "
        "const relationClassificationValues = "
        "(result.summary?.abc_display_labels ?? []).length "
        "? result.summary.abc_display_labels "
        ": [result.summary?.classification_code || "
        "result.summary?.classification_display_label]; "
        "const relationClassification = create("
        "'span', "
        "'classification-badge-group result-card-classification'"
        "); "
        "const relationClassificationCount = appendClassificationBadges("
        "relationClassification, relationClassificationValues"
        "); "
        "if (relationClassificationCount) main.append(relationClassification);"
    )

    block = block.replace(exact_old, replacement, 1)

    require(
        "result.summary?.abc_display_labels" in block,
        "abc_display_labels fallback 삽입 실패",
    )
    require(
        "main.append(relationClassification)" in block,
        "분류 badge title-row 삽입 실패",
    )
    require(
        exact_old not in block,
        "기존 chips 단일분류 렌더링이 남아 있음",
    )

    return source[:start] + block + source[end:]

def patch_relation_detail(source):
    require(
        APP_CONDITION_MARKER not in source,
        "Stage69B condition helper가 이미 존재함",
    )

    marker = "function renderRelationDetail(candidate, response, options = {}) {"
    require(
        source.count(marker) == 1,
        f"현재 renderRelationDetail 함수 anchor 불일치: {source.count(marker)}",
    )

    source = source.replace(
        marker,
        APP_HELPER.strip() + "\n\n" + marker,
        1,
    )

    exact_anchor = (
        "const matches = makeSection("
        "'입력 코드별 연결 조건', "
        "'입력 코드가 분류조건의 어떤 코드집합과 연결되는지 확인합니다.', "
        "{ open: true, count: candidate.code_matches.length });"
    )
    require(
        source.count(exact_anchor) == 1,
        "현재 0.5.16 입력 코드별 연결 조건 anchor 불일치: "
        f"count={source.count(exact_anchor)}",
    )

    insertion = (
        "/* STAGE69B_RELATION_OFFICIAL_CONDITIONS */ "
        "const officialConditionHost = create("
        "'div', 'relation-official-condition-host'"
        "); "
        "panel.append(officialConditionHost); "
        "loadRelationOfficialAdrgConditions("
        "candidate, officialConditionHost"
        "); "
        + exact_anchor
    )

    source = source.replace(exact_anchor, insertion, 1)

    require(
        "STAGE69B_RELATION_OFFICIAL_CONDITIONS" in source,
        "관계검색 공식 ADRG 조건 section 삽입 실패",
    )
    require(
        "loadRelationOfficialAdrgConditions(candidate, officialConditionHost)"
        in source,
        "관계검색 공식 ADRG 조건 loader 연결 실패",
    )

    return source


def patch_old_search_validator(source):
    """
    기존 validator가 exact CODE 검색에서 관련 ADRG 확장을 강제하는 경우,
    shared CODE/ADRG ID에만 새 exact-pair 계약을 적용한다.
    anchor가 없으면 원문을 유지한다.
    """
    old_patterns = [
        "const expected = new Set([`CODE:${code}`, ...(row.related_adrgs||[]).map(x=>`ADRG:${x}`)]);",
        "const expected = new Set([`CODE:${code}`, ...(row.related_adrgs || []).map(x => `ADRG:${x}`)]);",
    ]
    replacement = (
        "const expected = service.recordMaps.ADRG.has(code)\n"
        "    ? new Set([`CODE:${code}`, `ADRG:${code}`])\n"
        "    : new Set([`CODE:${code}`, ...(row.related_adrgs || []).map(x => `ADRG:${x}`)]);"
    )
    for old in old_patterns:
        if old in source:
            return source.replace(old, replacement, 1), True
    return source, False


def main():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "stage": "69B_R5",
        "status": "FAIL",
        "actual_performed": False,
    }

    try:
        head = git_text("rev-parse", "HEAD")
        branch = git_text("branch", "--show-current")
        tracked = [x for x in git_text("diff", "--name-only", "HEAD").splitlines() if x]
        staged = [x for x in git_text("diff", "--cached", "--name-only").splitlines() if x]
        package = json.loads((ROOT / "electron/package.json").read_text(encoding="utf-8"))

        require(head == BASE_COMMIT, f"기준커밋 불일치: {head}")
        require(branch == "main", f"branch 불일치: {branch}")
        require(package.get("version") == BASE_VERSION, f"version 불일치: {package.get('version')}")
        require(not tracked, f"tracked worktree 변경 있음: {tracked}")
        require(not staged, f"staging 변경 있음: {staged}")

        # 하드코딩 SHA 대신 현재 0.5.16 HEAD의 실제 Git blob과 worktree 바이트를 직접 비교한다.
        for rel in (APP_REL, SERVICE_REL):
            rc, head_bytes = subprocess.getstatusoutput(
                f"git show HEAD:{rel.as_posix()}"
            )
            require(rc == 0, f"HEAD blob 읽기 실패: {rel}")
            worktree_text = (ROOT / rel).read_text(encoding="utf-8").rstrip("\n")
            require(
                worktree_text == head_bytes.rstrip("\n"),
                f"HEAD와 worktree 바이트 불일치: {rel}",
            )
        require(
            sha256(ROOT / RUNTIME_REL) == RUNTIME_SHA,
            "운영 JSON SHA 불일치",
        )

        current_app = (ROOT / APP_REL).read_text(encoding="utf-8")
        require(
            current_app.count("function renderRelationResults(response) {") == 1,
            "현재 renderRelationResults 함수 구조 불일치",
        )
        require(
            current_app.count(
                "function renderRelationDetail(candidate, response, options = {}) {"
            ) == 1,
            "현재 renderRelationDetail 함수 구조 불일치",
        )
        require(
            current_app.count(
                "appendClassificationBadges(chips, "
                "[result.summary?.classification_code || "
                "result.summary?.classification_display_label]);"
            ) == 1,
            "현재 관계검색 결과 분류 anchor 불일치",
        )
        require(
            current_app.count(
                "const matches = makeSection("
                "'입력 코드별 연결 조건', "
                "'입력 코드가 분류조건의 어떤 코드집합과 연결되는지 확인합니다.', "
                "{ open: true, count: candidate.code_matches.length });"
            ) == 1,
            "현재 관계검색 상세 조건 anchor 불일치",
        )

        if SHADOW.exists():
            shutil.rmtree(SHADOW)

        rc, out = run(
            ["git", "clone", "--quiet", "--no-hardlinks", "--local", str(ROOT), str(SHADOW)],
            timeout=600,
        )
        require(rc == 0, "Shadow local clone 실패\n" + out[-3000:])
        require(
            run(["git", "rev-parse", "HEAD"], cwd=SHADOW, timeout=120)[1].strip() == BASE_COMMIT,
            "Shadow HEAD 불일치",
        )

        service_path = SHADOW / SERVICE_REL
        app_path = SHADOW / APP_REL
        old_validator_path = SHADOW / SEARCH_VALIDATOR_REL
        new_validator_path = SHADOW / NEW_VALIDATOR_REL

        service_source = service_path.read_text(encoding="utf-8")
        app_source = app_path.read_text(encoding="utf-8")
        old_validator_source = old_validator_path.read_text(encoding="utf-8")

        service_candidate = patch_service(service_source)
        app_candidate = patch_relation_results(app_source)
        app_candidate = patch_relation_detail(app_candidate)
        old_validator_candidate, old_validator_changed = patch_old_search_validator(
            old_validator_source
        )

        service_path.write_text(service_candidate, encoding="utf-8")
        app_path.write_text(app_candidate, encoding="utf-8")
        if old_validator_changed:
            old_validator_path.write_text(old_validator_candidate, encoding="utf-8")
        new_validator_path.write_text(NEW_VALIDATOR, encoding="utf-8")

        node_check(SERVICE_REL, SHADOW)
        node_check(APP_REL, SHADOW)
        node_check(NEW_VALIDATOR_REL, SHADOW)
        if old_validator_changed:
            node_check(SEARCH_VALIDATOR_REL, SHADOW)

        checks = [
            ("stage69b_validator", ["node", "tests/validate-stage69b-0517-search-relation-ux.js"], SHADOW / "electron"),
            ("stage68d_validator", ["node", "tests/validate-stage68d-0516-classification-derived-aadrg.js"], SHADOW / "electron"),
            ("npm_check", ["npm", "run", "check"], SHADOW / "electron"),
            ("50B", ["python", "50B_validate_kdrg_electron_search_service.py"], SHADOW),
            ("50C", ["python", "50C_validate_kdrg_electron_renderer_ui.py"], SHADOW),
            ("50D", ["python", "50D_validate_kdrg_electron_windows_packaging.py"], SHADOW),
            ("release_version", ["node", "tests/validate-release-version.js", BASE_VERSION], SHADOW / "electron"),
        ]

        # 각 검증 명령의 cwd 기준 경로를 사전에 확인한다.
        # R4처럼 cwd=electron인데 electron/tests/...를 다시 붙이는 오류를 여기서 차단한다.
        command_path_guards = [
            ("stage69b_validator", SHADOW / "electron" / "tests" / "validate-stage69b-0517-search-relation-ux.js"),
            ("stage68d_validator", SHADOW / "electron" / "tests" / "validate-stage68d-0516-classification-derived-aadrg.js"),
            ("npm_package", SHADOW / "electron" / "package.json"),
            ("50B", SHADOW / "50B_validate_kdrg_electron_search_service.py"),
            ("50C", SHADOW / "50C_validate_kdrg_electron_renderer_ui.py"),
            ("50D", SHADOW / "50D_validate_kdrg_electron_windows_packaging.py"),
            ("release_version", SHADOW / "electron" / "tests" / "validate-release-version.js"),
        ]
        for guard_name, guard_path in command_path_guards:
            require(
                guard_path.is_file(),
                f"검증 명령 경로 없음: {guard_name} -> {guard_path}",
            )

        results = []
        for name, cmd, cwd in checks:
            rc, out = run(cmd, cwd=cwd, timeout=1200)
            results.append({
                "name": name,
                "rc": rc,
                "status": "PASS" if rc == 0 else "FAIL",
                "tail": out[-8000:],
            })
            if rc != 0:
                raise Stop(f"{name} FAIL\n{out[-5000:]}")

        rc, status_out = run(["git", "status", "--short"], cwd=SHADOW, timeout=120)
        require(rc == 0, "Shadow git status 실패")
        changed = []
        for line in status_out.splitlines():
            if not line.strip():
                continue
            path = line[3:].strip()
            if " -> " in path:
                path = path.split(" -> ", 1)[1]
            changed.append(path)
        changed = sorted(changed)

        expected = sorted([
            str(SERVICE_REL),
            str(APP_REL),
            str(NEW_VALIDATOR_REL),
        ] + ([str(SEARCH_VALIDATOR_REL)] if old_validator_changed else []))
        require(changed == expected, f"Shadow 변경파일 불일치: actual={changed}, expected={expected}")

        # 운영 JSON이 Shadow에서도 동일한지 최종 확인.
        require(sha256(SHADOW / RUNTIME_REL) == RUNTIME_SHA, "Shadow 운영 JSON 변경됨")

        report.update({
            "status": "PASS",
            "readiness": "READY_FOR_69C_ACTUAL",
            "head": head,
            "base_app_sha256": sha256(ROOT / APP_REL),
            "base_service_sha256": sha256(ROOT / SERVICE_REL),
            "old_search_validator_changed": old_validator_changed,
            "shadow_changed_files": changed,
            "service_sha256": sha256(service_path),
            "app_sha256": sha256(app_path),
            "new_validator_sha256": sha256(new_validator_path),
            "checks": results,
            "runtime_json": "UNCHANGED",
        })
        REPORT_JSON.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        lines = [
            "[PASS] Stage69B R5 / 0.5.17 Search + Relation UX Shadow",
            "base_head_blob_guard=PASS",
            "validation_command_paths=PASS",
            "F022_exact=CODE:F022,ADRG:F022",
            "shared_CODE_ADRG_471=PASS",
            "shared_exact_pollution=0",
            "relation_fixture_classification=PASS",
            "relation_result_classification=TITLE_ROW",
            "relation_full_conditions=PASS",
            f"old_search_validator_changed={'YES' if old_validator_changed else 'NO'}",
            f"shadow_changed_files={len(changed)}",
            "stage69b_validator=PASS",
            "stage68d_validator=PASS",
            "npm_check=PASS",
            "50B_50C_50D=PASS",
            "release_version_0.5.16=PASS",
            "runtime_json=UNCHANGED",
            "actual=NOT_PERFORMED",
            "readiness=READY_FOR_69C_ACTUAL",
            f"report={REPORT_TXT.relative_to(ROOT)}",
            f"json={REPORT_JSON.relative_to(ROOT)}",
        ]
        REPORT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("\n".join(lines))
        return 0

    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        REPORT_JSON.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        REPORT_TXT.write_text(
            "[FAIL] Stage69B R5 / 0.5.17 Search + Relation UX Shadow\n"
            + report["error"] + "\n",
            encoding="utf-8",
        )
        print("[FAIL] Stage69B Shadow — Actual 미수행")
        print(str(exc))
        print(f"report={REPORT_TXT.relative_to(ROOT)}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
