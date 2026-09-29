from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path.cwd()
REPORT_DIR = ROOT / "reports" / "stage69b_0517_search_relation_ux_shadow_r12"
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
ROOT_50B_REL = Path("50B_validate_kdrg_electron_search_service.py")

SERVICE_MARKER = "STAGE69B_EXACT_PUBLIC_ID_V2"
APP_CLASS_MARKER = "STAGE69B_RELATION_RESULT_CLASSIFICATION_TITLE_ROW"
APP_CONDITION_MARKER = "loadRelationOfficialAdrgConditions"

SERVICE_PATCH = "/* STAGE69B_EXACT_PUBLIC_ID_V2 */\nconst STAGE69B_ORIGINAL_SEARCH = KdrgSearchService.prototype.search;\n\nKdrgSearchService.prototype.search = function stage69bExactPublicIdSearch(\n  query,\n  entityType = 'ALL',\n  options = {},\n) {\n  const requestedType = String(entityType ?? 'ALL').trim().toUpperCase();\n  if (requestedType !== 'ALL') {\n    return STAGE69B_ORIGINAL_SEARCH.call(this, query, entityType, options);\n  }\n\n  const queryText = normalizeSpace(query);\n  if (!queryText) {\n    throw new KdrgSearchError('검색어를 입력해야 합니다');\n  }\n\n  const limit = options?.limit ?? 50;\n  const offset = options?.offset ?? 0;\n  if (!Number.isInteger(limit) || limit < 1 || limit > 500) {\n    throw new KdrgSearchError('limit은 1~500 범위여야 합니다');\n  }\n  if (!Number.isInteger(offset) || offset < 0) {\n    throw new KdrgSearchError('offset은 0 이상이어야 합니다');\n  }\n\n  const entityTypes = this.normalizeEntityTypes(entityType);\n  const codeId = normalizeEntityId(queryText, 'CODE');\n  const adrgId = normalizeEntityId(queryText, 'ADRG');\n  const hasCode = Boolean(codeId && this.recordMaps?.CODE?.has(codeId));\n  const hasAdrg = Boolean(adrgId && this.recordMaps?.ADRG?.has(adrgId));\n\n  if (!hasCode && !hasAdrg) {\n    return STAGE69B_ORIGINAL_SEARCH.call(this, query, entityType, options);\n  }\n\n  const mdcFilter = String(options?.mdc ?? '').toUpperCase().trim();\n  const classFilter = String(options?.classification ?? '').toUpperCase().trim();\n  const rows = [];\n\n  const addExact = (typeName, entityId) => {\n    if (!entityTypes.includes(typeName)) return;\n    const record = this.recordMaps[typeName].get(\n      normalizeEntityId(entityId, typeName),\n    );\n    if (!record) return;\n    if (mdcFilter && !this.recordMatchesMdc(typeName, record, mdcFilter)) return;\n    if (\n      classFilter\n      && !this.recordMatchesClassification(typeName, record, classFilter)\n    ) return;\n    rows.push(\n      this.makeSearchResult(\n        typeName,\n        String(entityId),\n        1000,\n        'EXACT_ID',\n        ['entity_id'],\n      ),\n    );\n  };\n\n  if (hasCode) addExact('CODE', codeId);\n  if (hasAdrg) addExact('ADRG', adrgId);\n\n  const typeCounts = {};\n  for (const row of rows) {\n    typeCounts[row.entity_type] = (typeCounts[row.entity_type] ?? 0) + 1;\n  }\n\n  return {\n    schema_version: RESPONSE_SCHEMA_VERSION,\n    query: queryText,\n    normalized_query: normalizeQuery(queryText),\n    filters: {\n      entity_types: entityTypes,\n      mdc: mdcFilter || null,\n      classification: classFilter || null,\n    },\n    total_count: rows.length,\n    type_counts: typeCounts,\n    offset,\n    limit,\n    has_more: offset + limit < rows.length,\n    results: rows.slice(offset, offset + limit),\n  };\n};\n"
APP_HELPER = "\nasync function loadRelationOfficialAdrgConditions(candidate, host) {\n  host.replaceChildren(\n    create('p', 'muted', 'ADRG 분류 조건을 불러오는 중입니다.'),\n  );\n  try {\n    const payload = await window.KDRG.getDetail({\n      entityType: 'ADRG',\n      entityId: candidate.entity_id,\n    });\n    if (!host.isConnected) return;\n\n    const detail = payload?.detail;\n    if (!detail) {\n      throw new Error(`ADRG ${candidate.entity_id} 상세정보 없음`);\n    }\n\n    const fragment = document.createDocumentFragment();\n    fragment.append(\n      renderUserConditionSummary(detail),\n      renderUserConditionTables(detail),\n    );\n    if (SHOW_DEVELOPER_METADATA) {\n      fragment.append(renderUserConditionEvidence(detail));\n    }\n    host.replaceChildren(fragment);\n  } catch (error) {\n    if (!host.isConnected) return;\n    host.replaceChildren(\n      create(\n        'p',\n        'error-message',\n        error?.message || 'ADRG 분류 조건을 불러오지 못했습니다.',\n      ),\n    );\n  }\n}\n"
NEW_VALIDATOR = "'use strict';\n\nconst assert = require('node:assert/strict');\nconst fs = require('node:fs');\nconst path = require('node:path');\nconst { KdrgSearchService } = require('../src/kdrg-search-service');\n\nconst ROOT = path.resolve(__dirname, '..', '..');\nconst service = new KdrgSearchService(\n  path.join(ROOT, 'data', 'kdrg_v47_search_integrated_v3.json'),\n);\nconst app = fs.readFileSync(\n  path.join(ROOT, 'electron', 'renderer', 'app.js'),\n  'utf8',\n);\n\nlet pass = 0;\nconst failures = [];\n\nfunction check(name, fn) {\n  try {\n    fn();\n    pass += 1;\n  } catch (error) {\n    failures.push(`${name}: ${error.message}`);\n  }\n}\n\nconst codeIds = [...service.recordMaps.CODE.keys()].sort();\nconst adrgIds = [...service.recordMaps.ADRG.keys()].sort();\nconst shared = codeIds.filter((id) => service.recordMaps.ADRG.has(id));\nconst codeOnly = codeIds.filter((id) => !service.recordMaps.ADRG.has(id));\nconst adrgOnly = adrgIds.filter((id) => !service.recordMaps.CODE.has(id));\nconst publicIds = [...new Set([...codeIds, ...adrgIds])].sort();\n\ncheck('public namespace counts', () => {\n  assert.equal(codeIds.length, 16571);\n  assert.equal(adrgIds.length, 1132);\n  assert.equal(shared.length, 471);\n  assert.equal(codeOnly.length, 16100);\n  assert.equal(adrgOnly.length, 661);\n  assert.equal(publicIds.length, 17232);\n});\n\ncheck('all 17232 public exact IDs return exact public entities only', () => {\n  let mismatchCount = 0;\n  const examples = [];\n\n  for (const id of publicIds) {\n    const expected = [];\n    if (service.recordMaps.CODE.has(id)) expected.push(`CODE:${id}`);\n    if (service.recordMaps.ADRG.has(id)) expected.push(`ADRG:${id}`);\n\n    const response = service.search(id, 'ALL', { limit: 10, offset: 0 });\n    const actual = response.results.map(\n      (row) => `${row.entity_type}:${row.entity_id}`,\n    );\n\n    const typeCountExpected = {\n      CODE: service.recordMaps.CODE.has(id) ? 1 : 0,\n      ADRG: service.recordMaps.ADRG.has(id) ? 1 : 0,\n    };\n\n    const ok = JSON.stringify(actual) === JSON.stringify(expected)\n      && response.total_count === expected.length\n      && Number(response.type_counts?.CODE ?? 0) === typeCountExpected.CODE\n      && Number(response.type_counts?.ADRG ?? 0) === typeCountExpected.ADRG;\n\n    if (!ok) {\n      mismatchCount += 1;\n      if (examples.length < 20) {\n        examples.push({\n          id,\n          expected,\n          actual,\n          total_count: response.total_count,\n          type_counts: response.type_counts,\n        });\n      }\n    }\n  }\n\n  assert.equal(\n    mismatchCount,\n    0,\n    `mismatch=${mismatchCount} examples=${JSON.stringify(examples)}`,\n  );\n});\n\ncheck('F022 exact pair only', () => {\n  const response = service.search('F022', 'ALL', { limit: 10, offset: 0 });\n  assert.deepEqual(\n    response.results.map((row) => `${row.entity_type}:${row.entity_id}`),\n    ['CODE:F022', 'ADRG:F022'],\n  );\n  assert.ok(\n    !response.results.some((row) => row.entity_id === 'U602'),\n    'U602 must not leak into exact public-ID search',\n  );\n});\n\ncheck('CODE-only exact ID suppresses relation expansion', () => {\n  const id = codeOnly[0];\n  assert.ok(id, 'CODE-only fixture missing');\n  const response = service.search(id, 'ALL', { limit: 10, offset: 0 });\n  assert.deepEqual(\n    response.results.map((row) => `${row.entity_type}:${row.entity_id}`),\n    [`CODE:${id}`],\n  );\n});\n\ncheck('ADRG-only exact ID suppresses broad matches', () => {\n  const id = adrgOnly[0];\n  assert.ok(id, 'ADRG-only fixture missing');\n  const response = service.search(id, 'ALL', { limit: 10, offset: 0 });\n  assert.deepEqual(\n    response.results.map((row) => `${row.entity_type}:${row.entity_id}`),\n    [`ADRG:${id}`],\n  );\n});\n\ncheck('non-exact text search remains broad', () => {\n  const response = service.search('조기 사망', 'ALL', { limit: 20, offset: 0 });\n  assert.ok(response.total_count > 0);\n  assert.ok(response.results.length > 0);\n});\n\ncheck('type-specific F022 searches remain unchanged', () => {\n  const code = service.search('F022', 'CODE', { limit: 10, offset: 0 });\n  const adrg = service.search('F022', 'ADRG', { limit: 10, offset: 0 });\n  assert.ok(code.results.some(\n    (row) => row.entity_type === 'CODE' && row.entity_id === 'F022',\n  ));\n  assert.ok(adrg.results.some(\n    (row) => row.entity_type === 'ADRG' && row.entity_id === 'F022',\n  ));\n});\n\ncheck('shared exact pagination contract', () => {\n  const first = service.search('F022', 'ALL', { limit: 1, offset: 0 });\n  const second = service.search('F022', 'ALL', { limit: 1, offset: 1 });\n  assert.equal(first.total_count, 2);\n  assert.equal(first.results.length, 1);\n  assert.equal(first.has_more, true);\n  assert.deepEqual(\n    first.results.map((row) => `${row.entity_type}:${row.entity_id}`),\n    ['CODE:F022'],\n  );\n  assert.equal(second.total_count, 2);\n  assert.equal(second.results.length, 1);\n  assert.equal(second.has_more, false);\n  assert.deepEqual(\n    second.results.map((row) => `${row.entity_type}:${row.entity_id}`),\n    ['ADRG:F022'],\n  );\n});\n\nconst relationFixture = service.relationSearch(\n  [\n    { code: 'I214', codeType: 'AUTO' },\n    { code: 'M6566', codeType: 'AUTO' },\n  ],\n  'AND',\n);\n\ncheck('relation fixture returns expected comparison ADRGs', () => {\n  const ids = new Set(relationFixture.results.map((row) => row.entity_id));\n  for (const id of ['F111', 'F112', 'F121', 'F122']) {\n    assert.ok(ids.has(id), `missing ${id}`);\n  }\n});\n\ncheck('relation fixture carries abc display labels', () => {\n  for (const id of ['F111', 'F112', 'F121', 'F122']) {\n    const row = relationFixture.results.find((item) => item.entity_id === id);\n    assert.ok(row, `missing ${id}`);\n    assert.ok(\n      Array.isArray(row.summary?.abc_display_labels)\n        && row.summary.abc_display_labels.length > 0,\n      `${id} abc_display_labels missing`,\n    );\n  }\n});\n\ncheck('relation result uses abc labels with legacy fallback', () => {\n  assert.match(\n    app,\n    /STAGE69B_RELATION_RESULT_CLASSIFICATION_TITLE_ROW/,\n  );\n  assert.match(\n    app,\n    /result\\.summary\\?\\.abc_display_labels/,\n  );\n  assert.match(\n    app,\n    /result\\.summary\\?\\.classification_code\\s*\\|\\|\\s*result\\.summary\\?\\.classification_display_label/,\n  );\n  assert.match(\n    app,\n    /appendClassificationBadges\\(\\s*relationClassification/,\n  );\n  assert.match(\n    app,\n    /main\\.append\\(relationClassification\\)/,\n  );\n});\n\ncheck('relation detail loads official ADRG detail', () => {\n  assert.match(\n    app,\n    /async function loadRelationOfficialAdrgConditions/,\n  );\n  assert.match(\n    app,\n    /window\\.KDRG\\.getDetail\\(\\{[\\s\\S]*entityType:\\s*'ADRG'[\\s\\S]*candidate\\.entity_id/,\n  );\n});\n\ncheck('relation detail reuses normal ADRG condition renderers', () => {\n  assert.match(app, /renderUserConditionSummary\\(detail\\)/);\n  assert.match(app, /renderUserConditionTables\\(detail\\)/);\n  assert.match(\n    app,\n    /SHOW_DEVELOPER_METADATA[\\s\\S]*renderUserConditionEvidence\\(detail\\)/,\n  );\n  assert.match(app, /STAGE69B_RELATION_OFFICIAL_CONDITIONS/);\n});\n\ncheck('normal ADRG detail condition renderers remain present', () => {\n  assert.match(\n    app,\n    /function renderAdrgDetail\\(payload\\)[\\s\\S]*renderUserConditionSummary\\(detail\\)[\\s\\S]*renderUserConditionTables\\(detail\\)/,\n  );\n});\n\nconsole.log(\n  `[${failures.length ? 'FAIL' : 'PASS'}] Stage69B R11 0.5.17 exact-public-ID/relation UX validator: ${pass} PASS / ${failures.length} FAIL`,\n);\nconsole.log(\n  `public_ids=${publicIds.length} code_only=${codeOnly.length} adrg_only=${adrgOnly.length} shared=${shared.length}`,\n);\nfor (const failure of failures) console.log(`- ${failure}`);\nif (failures.length) process.exitCode = 1;\n"


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
    for token in (
        "normalizeEntityId",
        "normalizeSpace",
        "normalizeQuery",
        "KdrgSearchError",
        "RESPONSE_SCHEMA_VERSION",
        "normalizeEntityTypes",
        "recordMatchesMdc",
        "recordMatchesClassification",
        "makeSearchResult",
        "module.exports",
    ):
        require(token in source, f"0.5.16 search-service 필수 계약 없음: {token}")
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
    기존 Stage59 검색 validator의 exact CODE -> 관련 ADRG 확장 기대값을
    0.5.17 public exact-ID 계약으로 갱신한다.
    R12: 생성 JS에는 실제 줄바꿈을 넣고 literal \\n은 넣지 않는다.
    """
    old_patterns = [
        "const expected = new Set([`CODE:${code}`, ...(row.related_adrgs||[]).map(x=>`ADRG:${x}`)]);",
        "const expected = new Set([`CODE:${code}`, ...(row.related_adrgs || []).map(x => `ADRG:${x}`)]);",
    ]
    replacement = (
        "const expected = new Set([\n"
        "    ...(service.recordMaps.CODE.has(code) ? [`CODE:${code}`] : []),\n"
        "    ...(service.recordMaps.ADRG.has(code) ? [`ADRG:${code}`] : []),\n"
        "  ]);"
    )
    for old in old_patterns:
        if old in source:
            candidate = source.replace(old, replacement, 1)
            expected_slice = candidate.split(
                "const expected = new Set([", 1
            )[1].split("const actual", 1)[0]
            require(
                "related_adrgs" not in expected_slice,
                "Stage59 exact validator에 legacy relation expansion이 남아 있음",
            )
            require(
                "\\n" not in expected_slice,
                "Stage59 exact validator에 literal \\\\n이 남아 있음",
            )
            return candidate, True
    return source, False


def patch_root_50b_validator(source):
    """
    50B runtime probe를 0.5.17 public exact-ID 계약으로 갱신한다.
    KdrgSearchService 인스턴스 변수명과 줄바꿈 형식은 실제 probe에서 읽는다.
    R12: 생성 JS probe에는 실제 줄바꿈을 넣고 literal \\n은 넣지 않는다.
    """
    probe_match = re.search(
        r'(?ms)(?P<prefix>^\s*probe\s*=\s*r?""")(?P<body>.*?)(?P<suffix>^\s*""")',
        source,
    )
    require(probe_match is not None, "50B runtime probe 블록을 찾지 못함")
    body = probe_match.group("body")

    instance_matches = re.findall(
        r'\bconst\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*new\s+KdrgSearchService\s*\(',
        body,
    )
    require(
        len(instance_matches) == 1,
        f"50B KdrgSearchService 인스턴스 변수 개수 불일치: {instance_matches}",
    )
    service_var = instance_matches[0]

    require(
        re.search(r'for\s*\(\s*const\s+code\s+of\s+', body) is not None,
        "50B probe의 `for (const code of ...)` 구조를 찾지 못함",
    )

    expected_matches = list(re.finditer(r'\bconst\s+expected\s*=', body))
    require(
        len(expected_matches) == 1,
        f"50B probe const expected anchor 개수 불일치: {len(expected_matches)}",
    )
    expected_start = expected_matches[0].start()

    actual_match = re.search(r'\bconst\s+actual\s*=', body[expected_start:])
    require(actual_match is not None, "50B probe const actual anchor를 찾지 못함")
    actual_start = expected_start + actual_match.start()

    expected_block = body[expected_start:actual_start]
    require(
        expected_block.strip().endswith(";"),
        "50B expected 계약 블록 종결 세미콜론을 확인하지 못함",
    )

    line_start = body.rfind("\n", 0, expected_start) + 1
    indent_text = body[line_start:expected_start]
    indent_match = re.match(r"[ \t]*", indent_text)
    indent = indent_match.group(0) if indent_match else ""

    replacement = (
        f"{indent}const expected = new Set([\n"
        f"{indent}  ...({service_var}.recordMaps.CODE.has(code) ? ['CODE:' + code] : []),\n"
        f"{indent}  ...({service_var}.recordMaps.ADRG.has(code) ? ['ADRG:' + code] : []),\n"
        f"{indent}]);\n"
    )

    body = body[:expected_start] + replacement + body[actual_start:]

    require(
        f"{service_var}.recordMaps.CODE.has(code)" in body,
        "50B CODE exact 계약 삽입 실패",
    )
    require(
        f"{service_var}.recordMaps.ADRG.has(code)" in body,
        "50B ADRG exact 계약 삽입 실패",
    )

    migrated_expected = body[
        body.index("const expected = new Set(["):body.index("const actual")
    ]
    require(
        "\\n" not in migrated_expected,
        "50B runtime probe에 literal \\\\n이 남아 있음",
    )

    candidate = (
        source[:probe_match.start("body")]
        + body
        + source[probe_match.end("body"):]
    )

    replacements = [
        (
            'check("0.5.10 runtime probe",',
            'check("0.5.17 exact public-ID runtime probe",',
        ),
        (
            'check("0.5.17 exact shared-ID runtime probe",',
            'check("0.5.17 exact public-ID runtime probe",',
        ),
        (
            "console.log('[PASS] Stage50B 0.5.10 current runtime contract');",
            "console.log('[PASS] Stage50B 0.5.17 exact public-ID runtime contract');",
        ),
        (
            "console.log('[PASS] Stage50B 0.5.10 runtime contract');",
            "console.log('[PASS] Stage50B 0.5.17 exact public-ID runtime contract');",
        ),
        (
            "KDRG V4.7 Stage50B Electron Search Validator - 0.5.10 Current Contract",
            "KDRG V4.7 Stage50B Electron Search Validator - 0.5.17 Exact Public-ID Contract",
        ),
        (
            "KDRG V4.7 Stage 50B Electron 검색 service 독립검증 - 0.5.10",
            "KDRG V4.7 Stage 50B Electron 검색 service 독립검증 - 0.5.17 exact public-ID",
        ),
    ]
    for old, new in replacements:
        if old in candidate:
            candidate = candidate.replace(old, new, 1)

    return candidate, True


def main():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "stage": "69B_R12",
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

        root_50b_path = SHADOW / ROOT_50B_REL
        root_50b_source = root_50b_path.read_text(encoding="utf-8")
        root_50b_candidate, root_50b_changed = patch_root_50b_validator(
            root_50b_source
        )

        service_path.write_text(service_candidate, encoding="utf-8")
        app_path.write_text(app_candidate, encoding="utf-8")
        if old_validator_changed:
            old_validator_path.write_text(old_validator_candidate, encoding="utf-8")
        if root_50b_changed:
            root_50b_path.write_text(root_50b_candidate, encoding="utf-8")
        new_validator_path.write_text(NEW_VALIDATOR, encoding="utf-8")

        node_check(SERVICE_REL, SHADOW)
        node_check(APP_REL, SHADOW)
        node_check(NEW_VALIDATOR_REL, SHADOW)
        if old_validator_changed:
            node_check(SEARCH_VALIDATOR_REL, SHADOW)

        rc, out = run(
            ["python", "-m", "py_compile", str(ROOT_50B_REL)],
            cwd=SHADOW,
            timeout=120,
        )
        require(rc == 0, f"50B Python compile FAIL\n{out[-3000:]}")

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
        validation_failures = []
        for name, cmd, cwd in checks:
            rc, out = run(cmd, cwd=cwd, timeout=1200)
            results.append({
                "name": name,
                "rc": rc,
                "status": "PASS" if rc == 0 else "FAIL",
                "tail": out[-8000:],
            })
            if rc != 0:
                extra = ""
                if name == "50B":
                    report_50b = SHADOW / "reports" / "electron_stage50b_validation_report.txt"
                    if report_50b.is_file():
                        extra = (
                            "\n\n[50B detailed report tail]\n"
                            + report_50b.read_text(
                                encoding="utf-8",
                                errors="replace",
                            )[-8000:]
                        )
                validation_failures.append(
                    f"{name} FAIL\n{out[-5000:]}{extra}"
                )

        if validation_failures:
            raise Stop(
                "검증 실패를 전체 실행 후 수집함\n\n"
                + "\n\n".join(validation_failures)
            )

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

        expected_product_changes = sorted([
            str(SERVICE_REL),
            str(APP_REL),
            str(NEW_VALIDATOR_REL),
            str(ROOT_50B_REL),
        ] + ([str(SEARCH_VALIDATOR_REL)] if old_validator_changed else []))

        # 50B/50C/50D 독립검증이 정상적으로 생성하는 보고서는 제품 변경이 아니다.
        expected_generated_reports = sorted([
            "reports/electron_stage50b_validation_report.json",
            "reports/electron_stage50b_validation_report.txt",
            "reports/electron_stage50c_validation_report.json",
            "reports/electron_stage50c_validation_report.txt",
            "reports/electron_stage50d_validation_report.json",
            "reports/electron_stage50d_validation_report.txt",
        ])

        product_changed = sorted([
            path for path in changed
            if path not in expected_generated_reports
        ])
        generated_reports = sorted([
            path for path in changed
            if path in expected_generated_reports
        ])

        require(
            product_changed == expected_product_changes,
            "Shadow 제품 변경파일 불일치: "
            f"actual={product_changed}, expected={expected_product_changes}",
        )
        require(
            generated_reports == expected_generated_reports,
            "Shadow 검증 report 산출물 불일치: "
            f"actual={generated_reports}, expected={expected_generated_reports}",
        )

        unexpected_report_paths = sorted([
            path for path in changed
            if path.startswith("reports/")
            and path not in expected_generated_reports
        ])
        require(
            not unexpected_report_paths,
            f"예상하지 못한 Shadow report 변경: {unexpected_report_paths}",
        )

        # 운영 JSON이 Shadow에서도 동일한지 최종 확인.
        require(sha256(SHADOW / RUNTIME_REL) == RUNTIME_SHA, "Shadow 운영 JSON 변경됨")

        report.update({
            "status": "PASS",
            "readiness": "READY_FOR_69C_ACTUAL",
            "head": head,
            "base_app_sha256": sha256(ROOT / APP_REL),
            "base_service_sha256": sha256(ROOT / SERVICE_REL),
            "old_search_validator_changed": old_validator_changed,
            "root_50b_validator_changed": root_50b_changed,
            "shadow_changed_files": changed,
            "shadow_product_changed_files": product_changed,
            "shadow_generated_reports": generated_reports,
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
            "[PASS] Stage69B R12 / 0.5.17 Search + Relation UX Shadow",
            "base_head_blob_guard=PASS",
            "validation_command_paths=PASS",
            "F022_exact=CODE:F022,ADRG:F022",
            "public_exact_ids_17232=PASS",
            "code_only_exact_16100=PASS",
            "adrg_only_exact_661=PASS",
            "shared_CODE_ADRG_471=PASS",
            "shared_exact_pollution=0",
            "public_exact_pollution=0",
            "relation_fixture_classification=PASS",
            "relation_result_classification=TITLE_ROW",
            "relation_full_conditions=PASS",
            f"old_search_validator_changed={'YES' if old_validator_changed else 'NO'}",
            f"root_50b_validator_changed={'YES' if root_50b_changed else 'NO'}",
            "all_validations_collected_before_stop=YES",
            "50B_exact_contract=ALL_PUBLIC_CODE_ADRG_IDS",
            f"shadow_product_changed_files={len(product_changed)}",
            f"shadow_generated_reports={len(generated_reports)}",
            "shadow_change_scope=PRODUCT_5_PLUS_VALIDATION_REPORTS_6",
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
            "[FAIL] Stage69B R12 / 0.5.17 Search + Relation UX Shadow\n"
            + report["error"] + "\n",
            encoding="utf-8",
        )
        print("[FAIL] Stage69B Shadow — Actual 미수행")
        print(str(exc))
        print(f"report={REPORT_TXT.relative_to(ROOT)}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
