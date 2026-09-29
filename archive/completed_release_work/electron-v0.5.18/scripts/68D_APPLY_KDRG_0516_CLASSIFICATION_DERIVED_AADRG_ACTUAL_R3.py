#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage68D — KDRG 0.5.16 Actual Apply R3 R3
- relation 상세의 질병군 분류 표시 복원
- ADRG 상세의 파생 AADRG 섹션 복원
- 파생 AADRG별 질병군 분류 표시 회귀방지
- 전용 영구 validator 추가
- 실패 시 exact target만 rollback

변경 대상
1) electron/renderer/app.js
2) electron/tests/validate-stage68d-0516-classification-derived-aadrg.js

변경하지 않음
- data/kdrg_v47_search_integrated_v3.json
- electron/src/kdrg-search-service.js
- electron/renderer/styles.css
"""

from __future__ import annotations
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
STAGE = "stage68d_0516_actual_classification_derived_aadrg"
REPORT_DIR = ROOT / "reports" / STAGE
REPORT_DIR.mkdir(parents=True, exist_ok=True)

APP = ROOT / "electron" / "renderer" / "app.js"
VALIDATOR = ROOT / "electron" / "tests" / "validate-stage68d-0516-classification-derived-aadrg.js"
DATA = ROOT / "data" / "kdrg_v47_search_integrated_v3.json"

EXPECTED_HEAD = "6e0bc2857ebf6abb482428b90f452d5e07c486ac"
EXPECTED_TAG = "electron-v0.5.15"
EXPECTED_DATA_SHA = "1a3d50400567ecaad9695b7be8e7c0382131f8652f398e010cf01f4d8dda6c58"

REPORT_JSON = REPORT_DIR / "apply.json"
REPORT_TXT = REPORT_DIR / "apply_summary.txt"

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def run(args, timeout=240, cwd=None):
    p = subprocess.run(
        args,
        cwd=(cwd or ROOT),
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    return p.returncode, (p.stdout or "") + (("\n" + p.stderr) if p.stderr else "")

def git(*args):
    return run(["git", *args], timeout=120)

def replace_function_segment(text: str, func_name: str, next_func_name: str, transform):
    start = re.search(rf"(?m)^(?:async\s+)?function\s+{re.escape(func_name)}\s*\(", text)
    if not start:
        raise RuntimeError(f"{func_name} 함수 시작을 찾지 못함")
    nxt = re.search(rf"(?m)^(?:async\s+)?function\s+{re.escape(next_func_name)}\s*\(", text[start.end():])
    if not nxt:
        raise RuntimeError(f"{func_name} 다음 함수 {next_func_name}를 찾지 못함")
    seg_start = start.start()
    seg_end = start.end() + nxt.start()
    old = text[seg_start:seg_end]
    new = transform(old)
    if new == old:
        raise RuntimeError(f"{func_name} 수정이 적용되지 않음")
    return text[:seg_start] + new + text[seg_end:]

def patch_relation(segment: str) -> str:
    if (
        "candidate.summary?.abc_display_labels" in segment
        or "candidate.summary.abc_display_labels" in segment
    ):
        return segment

    # meta grid 내부 MDC 행 바로 뒤에 삽입.
    pattern = re.compile(
        r"(?P<indent>[ \t]*)\['MDC',\s*candidate\.summary\?\.mdc\s*\?\s*`MDC \$\{candidate\.summary\.mdc\}`\s*:\s*'-'\],\s*\n"
    )
    m = pattern.search(segment)
    if m:
        insert = (
            m.group(0)
            + f"{m.group('indent')}['질병군 분류', Ui.summarizeList(candidate.summary?.abc_display_labels)],\n"
        )
        return segment[:m.start()] + insert + segment[m.end():]

    # 문법 모양이 약간 달라도 MDC 행 다음에 추가.
    lines = segment.splitlines(True)
    for i, line in enumerate(lines):
        if "['MDC'," in line and "candidate" in line:
            indent = re.match(r"\s*", line).group(0)
            lines.insert(
                i + 1,
                f"{indent}['질병군 분류', Ui.summarizeList(candidate.summary?.abc_display_labels)],\n",
            )
            return "".join(lines)

    raise RuntimeError("renderRelationDetail에서 MDC meta row를 찾지 못함")

def patch_adrg(segment: str) -> str:
    if "renderDerivedAadrgList(detail.aadrg_records)" in segment:
        return segment

    # 조건 섹션을 append하기 직전에 기존 derived renderer를 연결.
    anchor = re.search(
        r"(?m)^(?P<indent>\s*)fragment\.append\(\s*\n(?P<childindent>\s*)renderUserConditionSummary\(detail\),",
        segment,
    )
    if not anchor:
        # 한 줄/다른 공백 형태 대응.
        anchor = re.search(
            r"(?P<indent>\s*)fragment\.append\(\s*renderUserConditionSummary\(detail\),",
            segment,
        )
        if not anchor:
            raise RuntimeError("renderAdrgDetail의 조건 section append anchor를 찾지 못함")
        indent = anchor.group("indent")
        block = (
            f"{indent}const aadrgSection = makeSection(\n"
            f"{indent}  '파생 AADRG',\n"
            f"{indent}  'ADRG에서 파생되는 AADRG와 질병군 분류를 함께 확인합니다.',\n"
            f"{indent}  {{ open: false, count: (detail.aadrg_records ?? []).length }},\n"
            f"{indent});\n"
            f"{indent}aadrgSection.append(renderDerivedAadrgList(detail.aadrg_records));\n"
            f"{indent}fragment.append(\n"
            f"{indent}  aadrgSection,\n"
            f"{indent}  renderUserConditionSummary(detail),"
        )
        return segment[:anchor.start()] + block + segment[anchor.end():]

    indent = anchor.group("indent")
    childindent = anchor.group("childindent")
    block = (
        f"{indent}const aadrgSection = makeSection(\n"
        f"{indent}  '파생 AADRG',\n"
        f"{indent}  'ADRG에서 파생되는 AADRG와 질병군 분류를 함께 확인합니다.',\n"
        f"{indent}  {{ open: false, count: (detail.aadrg_records ?? []).length }},\n"
        f"{indent});\n"
        f"{indent}aadrgSection.append(renderDerivedAadrgList(detail.aadrg_records));\n"
        f"{indent}fragment.append(\n"
        f"{childindent}aadrgSection,\n"
        f"{childindent}renderUserConditionSummary(detail),"
    )
    return segment[:anchor.start()] + block + segment[anchor.end():]

VALIDATOR_JS = r"""'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const ELECTRON_ROOT = path.resolve(__dirname, '..');
const { resolveDataFiles } = require('../src/data-paths');
const {
  KdrgSearchService,
  normalizeEntityId,
} = require('../src/kdrg-search-service');
const {
  SEARCH_ENTITY_TYPES,
} = require('../src/search-result-contract');

const appPath = path.join(ELECTRON_ROOT, 'renderer', 'app.js');
const appText = fs.readFileSync(appPath, 'utf8');

const dataFiles = resolveDataFiles({
  isPackaged: false,
  resourcesPath: null,
  moduleDirectory: path.join(ELECTRON_ROOT, 'src'),
});
const service = new KdrgSearchService(dataFiles.integrated);

let pass = 0;
const failures = [];

function check(name, fn) {
  try {
    fn();
    pass += 1;
  } catch (error) {
    failures.push(`${name}: ${error.message}`);
  }
}

function sameSet(a, b) {
  const left = [...new Set((a ?? []).map(String))].sort();
  const right = [...new Set((b ?? []).map(String))].sort();
  return JSON.stringify(left) === JSON.stringify(right);
}

function functionSlice(name, nextName) {
  const start = appText.indexOf(`function ${name}(`);
  assert.ok(start >= 0, `${name} 없음`);
  const end = appText.indexOf(`function ${nextName}(`, start + 1);
  assert.ok(end > start, `${nextName} 경계 없음`);
  return appText.slice(start, end);
}

function codesForTables(tableIds) {
  const output = [];
  const seen = new Set();
  for (const tableId of tableIds ?? []) {
    const table = service.recordMaps.TABLE.get(String(tableId));
    for (const code of table?.codes ?? []) {
      const normalized = normalizeEntityId(code, 'CODE');
      if (!normalized || seen.has(normalized)) continue;
      seen.add(normalized);
      output.push(String(code));
    }
  }
  return output;
}

function findF111RelationFixture() {
  const groups = service.conditionGroupsByAdrg.get('F111') ?? [];

  for (const group of groups) {
    const codes = codesForTables(group.include_table_ids).slice(0, 80);
    for (let i = 0; i < codes.length; i += 1) {
      for (let j = i + 1; j < codes.length; j += 1) {
        if (normalizeEntityId(codes[i], 'CODE') === normalizeEntityId(codes[j], 'CODE')) continue;
        const response = service.relationSearch([
          { code: codes[i], codeType: 'AUTO' },
          { code: codes[j], codeType: 'AUTO' },
        ], 'AND');
        const candidate = response.results.find((row) => row.entity_id === 'F111');
        if (candidate) return { codes: [codes[i], codes[j]], operator: 'AND', candidate };
      }
    }
  }

  const all = [];
  const seen = new Set();
  for (const group of groups) {
    for (const code of codesForTables(group.include_table_ids)) {
      const normalized = normalizeEntityId(code, 'CODE');
      if (!normalized || seen.has(normalized)) continue;
      seen.add(normalized);
      all.push(code);
      if (all.length >= 80) break;
    }
    if (all.length >= 80) break;
  }
  for (let i = 0; i < all.length; i += 1) {
    for (let j = i + 1; j < all.length; j += 1) {
      const response = service.relationSearch([
        { code: all[i], codeType: 'AUTO' },
        { code: all[j], codeType: 'AUTO' },
      ], 'OR');
      const candidate = response.results.find((row) => row.entity_id === 'F111');
      if (candidate) return { codes: [all[i], all[j]], operator: 'OR', candidate };
    }
  }
  return null;
}

check('public search entity types CODE/ADRG only', () => {
  assert.deepEqual(Array.from(SEARCH_ENTITY_TYPES), ['CODE', 'ADRG']);
});

check('service counts ADRG/AADRG', () => {
  const status = service.status();
  assert.equal(status.counts.adrg_records, 1132);
  assert.equal(status.counts.aadrg_records, 1233);
});

const f111Direct = service.search('F111', 'ADRG', { limit: 50 })
  .results.find((row) => row.entity_type === 'ADRG' && row.entity_id === 'F111');
const f111Detail = service.getDetail('ADRG', 'F111');

check('F111 direct classification 전문', () => {
  assert.ok(f111Direct);
  assert.deepEqual(f111Direct.summary?.abc_display_labels, ['질병군 분류(전문)']);
});

check('F111 detail classification 전문', () => {
  assert.deepEqual(f111Detail.detail?.abc_display_labels, ['질병군 분류(전문)']);
});

check('F111 derived AADRG F1110 classification', () => {
  const child = (f111Detail.detail?.aadrg_records ?? []).find((row) => row.entity_id === 'F1110');
  assert.ok(child, 'F1110 없음');
  assert.equal(child.summary?.classification_code, 'A');
  assert.equal(child.summary?.classification_display_label, '질병군 분류(전문)');
});

const f111RelationFixture = findF111RelationFixture();

check('F111 valid relation fixture discovered', () => {
  assert.ok(f111RelationFixture, 'F111 relation fixture를 만들 수 없음');
});

check('F111 relation classification equals direct/detail', () => {
  assert.ok(f111RelationFixture);
  const relationLabels = f111RelationFixture.candidate.summary?.abc_display_labels ?? [];
  assert.ok(relationLabels.length > 0, 'relation classification 누락');
  assert.ok(sameSet(relationLabels, f111Direct.summary?.abc_display_labels));
  assert.ok(sameSet(relationLabels, f111Detail.detail?.abc_display_labels));
});

check('all ADRG derived AADRG display label complete', () => {
  let scanned = 0;
  let children = 0;
  const missing = [];
  for (const adrg of service.recordMaps.ADRG.keys()) {
    scanned += 1;
    const detail = service.getDetail('ADRG', adrg).detail;
    for (const child of detail.aadrg_records ?? []) {
      children += 1;
      if (!child?.entity_id || !String(child?.summary?.classification_display_label ?? '').trim()) {
        missing.push({
          adrg,
          aadrg: child?.entity_id ?? null,
          label: child?.summary?.classification_display_label ?? null,
        });
      }
    }
  }
  assert.equal(scanned, 1132);
  assert.equal(children, 1233);
  assert.deepEqual(missing, []);
});

const relationFn = functionSlice('renderRelationDetail', 'clearDetail');
const derivedFn = functionSlice('renderDerivedAadrgList', 'renderAdrgDetail');
const adrgFn = functionSlice('renderAdrgDetail', 'renderAadrgDetail');

check('relation detail classification UI contract', () => {
  assert.ok(relationFn.includes('질병군 분류'));
  assert.ok(
    relationFn.includes('candidate.summary?.abc_display_labels')
    || relationFn.includes('candidate.summary.abc_display_labels')
  );
});

check('derived AADRG renderer classification UI contract', () => {
  assert.ok(derivedFn.includes('summary.classification_code'));
  assert.ok(derivedFn.includes('summary.classification_display_label'));
  assert.ok(derivedFn.includes('makeChip('), '파생 AADRG 분류 badge/chip 생성 계약 누락');
});

check('ADRG detail derived AADRG section contract', () => {
  assert.ok(adrgFn.includes('파생 AADRG'));
  assert.ok(adrgFn.includes('renderDerivedAadrgList(detail.aadrg_records)'));
  assert.ok(/open\s*:\s*false/.test(adrgFn));
});

console.log(`stage68d_0516: ${pass} PASS / ${failures.length} FAIL`);
if (f111RelationFixture) {
  console.log(`F111 relation fixture=${f111RelationFixture.codes.join(' + ')} / ${f111RelationFixture.operator}`);
}
if (failures.length) {
  for (const failure of failures) console.log(`- ${failure}`);
  process.exitCode = 1;
}
"""

def main():
    if not APP.exists() or not DATA.exists():
        print("[FAIL] app.js 또는 운영 JSON 없음")
        return 1

    # immutable release baseline 확인
    rc, head_out = git("rev-parse", "HEAD")
    head = head_out.strip() if rc == 0 else ""
    rc, tag_out = git("rev-parse", EXPECTED_TAG)
    tag_commit = tag_out.strip() if rc == 0 else ""
    data_sha = sha256(DATA)

    if head != EXPECTED_HEAD:
        print(f"[FAIL] HEAD 불일치: {head}")
        return 1
    if tag_commit != EXPECTED_HEAD:
        print(f"[FAIL] {EXPECTED_TAG} 불일치: {tag_commit}")
        return 1
    if data_sha != EXPECTED_DATA_SHA:
        print(f"[FAIL] 운영 JSON SHA256 불일치: {data_sha}")
        return 1

    # 대상 app.js는 0.5.15 tag와 동일해야 함.
    rc, diff_out = git("diff", "--no-ext-diff", "--quiet", EXPECTED_TAG, "--", str(APP.relative_to(ROOT)))
    if rc != 0:
        print("[FAIL] app.js가 0.5.15 tag와 이미 다름. Actual 중단")
        return 1

    original_app = APP.read_text(encoding="utf-8")
    original_validator = VALIDATOR.read_text(encoding="utf-8") if VALIDATOR.exists() else None

    (REPORT_DIR / "before_app.js").write_text(original_app, encoding="utf-8")

    # 기존 renderer는 반드시 살아 있어야 함.
    required_existing = [
        "function renderDerivedAadrgList(",
        "summary.classification_code",
        "summary.classification_display_label",
        "Ui.classificationLabel",
    ]
    missing_existing = [x for x in required_existing if x not in original_app]
    if missing_existing:
        print(f"[FAIL] 기존 derived renderer 계약 누락: {missing_existing}")
        return 1

    try:
        patched = replace_function_segment(
            original_app, "renderRelationDetail", "clearDetail", patch_relation
        )
        patched = replace_function_segment(
            patched, "renderAdrgDetail", "renderAadrgDetail", patch_adrg
        )

        # 중복/의도치 않은 삽입 방지
        if patched.count("renderDerivedAadrgList(detail.aadrg_records)") != 1:
            raise RuntimeError("ADRG derived renderer 호출 개수가 1이 아님")
        if patched.count("candidate.summary?.abc_display_labels") != 1:
            raise RuntimeError("relation classification 참조 개수가 1이 아님")

        APP.write_text(patched, encoding="utf-8")
        VALIDATOR.write_text(VALIDATOR_JS, encoding="utf-8")

        # Actual 후 전용 validator
        validations = []
        electron_root = ROOT / "electron"

        commands = [
            # Electron validator는 0.5.15 릴리스 당시와 동일하게 electron/을 cwd로 사용한다.
            (["node", "--check", "renderer/app.js"], electron_root, True),
            (["node", "--check", "tests/validate-stage68d-0516-classification-derived-aadrg.js"], electron_root, True),
            (["node", "tests/validate-stage68d-0516-classification-derived-aadrg.js"], electron_root, True),
            (["node", "tests/validate-stage59b-search.js"], electron_root, True),
            (["node", "tests/validate-stage59b-ui.js"], electron_root, True),
            (["node", "tests/validate-stage59b-smoke.js"], electron_root, True),
            (["node", "tests/validate-packaged-runtime-smoke.js"], electron_root, False),
            (["node", "tests/validate-stage60c-packaged-relation-smoke.js"], electron_root, False),

            # Python validator는 repository root 기준으로 실행한다.
            (["python", "50B_validate_kdrg_electron_search_service.py"], ROOT, False),
            (["python", "50C_validate_kdrg_electron_renderer_ui.py"], ROOT, False),
        ]

        for cmd, command_cwd, required in commands:
            target = cmd[-1]
            if cmd[0] == "node":
                # --check의 마지막 인자도 electron_root 기준
                cmd_path = command_cwd / target
            else:
                cmd_path = command_cwd / target

            if not cmd_path.exists():
                if required:
                    raise RuntimeError(f"필수 validator 누락: {target}")
                validations.append({
                    "command": " ".join(cmd),
                    "cwd": str(command_cwd),
                    "status": "SKIP_NOT_FOUND",
                })
                continue

            vrc, output = run(cmd, timeout=300, cwd=command_cwd)
            validations.append({
                "command": " ".join(cmd),
                "cwd": str(command_cwd),
                "status": "PASS" if vrc == 0 else "FAIL",
                "returncode": vrc,
                "output_tail": output[-4000:],
            })
            if vrc != 0:
                raise RuntimeError(
                    f"검증 실패: cwd={command_cwd} cmd={' '.join(cmd)}\n{output[-1800:]}"
                )

        after_app_sha = sha256(APP)
        validator_sha = sha256(VALIDATOR)

        rc, status_out = git(
            "status",
            "--short",
            "--",
            str(APP.relative_to(ROOT)),
            str(VALIDATOR.relative_to(ROOT)),
        )

        result = {
            "stage": "68D",
            "actual": True,
            "pass": True,
            "baseline": {
                "head": head,
                "tag": EXPECTED_TAG,
                "tag_commit": tag_commit,
                "operating_json_sha256": data_sha,
            },
            "modified_files": [
                str(APP.relative_to(ROOT)),
                str(VALIDATOR.relative_to(ROOT)),
            ],
            "not_modified": [
                "data/kdrg_v47_search_integrated_v3.json",
                "electron/src/kdrg-search-service.js",
                "electron/renderer/styles.css",
            ],
            "app_sha256_after": after_app_sha,
            "validator_sha256": validator_sha,
            "validations": validations,
            "git_status_targets": status_out.splitlines(),
        }
        REPORT_JSON.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        lines = [
            "Stage68D — KDRG 0.5.16 Actual Apply",
            "=" * 52,
            "result=PASS",
            f"HEAD={head}",
            f"data_sha256={data_sha}",
            "",
            "[modified]",
            str(APP.relative_to(ROOT)),
            str(VALIDATOR.relative_to(ROOT)),
            "",
            f"app_sha256={after_app_sha}",
            f"validator_sha256={validator_sha}",
            "",
            "[validation]",
        ]
        for v in validations:
            lines.append(f"{v['status']}: {v['command']}")
        lines += [
            "",
            "[target git status]",
            *status_out.splitlines(),
            "",
            "운영 JSON / search service / CSS 변경 없음.",
        ]
        REPORT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")

        print("[PASS] Stage68D 0.5.16 Actual apply")
        print("modified=electron/renderer/app.js")
        print("added=electron/tests/validate-stage68d-0516-classification-derived-aadrg.js")
        print("operating_json=UNCHANGED")
        print("search_service=UNCHANGED")
        print("styles=UNCHANGED")
        for v in validations:
            print(f"{v['status']} {v['command']}")
        print(f"app_sha256={after_app_sha}")
        print(f"validator_sha256={validator_sha}")
        print(f"report={REPORT_TXT.relative_to(ROOT)}")
        print(f"json={REPORT_JSON.relative_to(ROOT)}")
        return 0

    except Exception as exc:
        # exact target rollback
        APP.write_text(original_app, encoding="utf-8")
        if original_validator is None:
            if VALIDATOR.exists():
                VALIDATOR.unlink()
        else:
            VALIDATOR.write_text(original_validator, encoding="utf-8")

        failure = {
            "stage": "68D",
            "actual": True,
            "pass": False,
            "rolled_back": True,
            "error": str(exc),
        }
        REPORT_JSON.write_text(
            json.dumps(failure, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        REPORT_TXT.write_text(
            "[FAIL] Stage68D\nrollback=YES\n" + str(exc) + "\n",
            encoding="utf-8",
        )
        print("[FAIL] Stage68D Actual — exact targets rollback 완료")
        print(str(exc).splitlines()[0][:500])
        print(f"report={REPORT_TXT.relative_to(ROOT)}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
