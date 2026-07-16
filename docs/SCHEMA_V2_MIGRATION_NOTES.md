# SCHEMA_V2_MIGRATION_NOTES — v1 → v2 마이그레이션 노트

이 문서는 `kdrg_v47_ui_fixture.json`(v1)에서
`kdrg_v47_pilot_schema_v2.json`(v2)으로의 변환 시 각 필드의 처리 방침을 기록한다.

---

## 1. 최상위 구조 변화

| v1 키 | v2 처리 |
|---|---|
| `meta` | 유지 + 필드 추가(`schema_version`, `effective_date`, `runtime_status` 등) |
| `mdc_master` | 그대로 유지 |
| `tables` | 필드 확장(아래 참조) |
| `rules` | 필드 확장 + `condition_expression` 완성 |
| _(없음)_ | `sources[]` 신설 |
| _(없음)_ | `derived_indexes{}` 신설 |
| _(없음)_ | `validation_summary{}` 신설 |

---

## 2. tables 필드 매핑

| v1 필드 | v2 처리 | 비고 |
|---|---|---|
| `table_id` | **그대로 유지** | |
| `display_label` | **그대로 유지** | |
| `code_type` | **그대로 유지** | |
| `source_page` | → `source_refs[]`로 분해 | 문자열에서 구조화 참조로 |
| _(없음)_ | `owner_adrg` 추가 | |
| _(없음)_ | `printed_label` 추가 | `display_label`의 짧은 원문 표기 |
| _(없음)_ | `table_role` 추가 | |
| _(없음)_ | `member_count` 추가 | |
| _(없음)_ | `derivation` 추가 | null for 파일럿 |
| _(없음)_ | `status` 추가 | `"ACTIVE"` 기본값 |

### member 필드 매핑

| v1 필드 | v2 처리 |
|---|---|
| `code` | **그대로 유지** |
| `name_ko` | → `name_ko_raw` (원문 보존) + `name_ko_effective` (교정 미적용 → 동일값) |
| `name_en` | → `name_en_raw` + `name_en_effective` (동일값) |
| `original_order` | **그대로 유지** |
| _(없음)_ | `source_refs[]` 추가 (파일럿에서는 빈 배열) |
| _(없음)_ | `correction_refs[]` 추가 (파일럿에서는 빈 배열) |
| _(없음)_ | `status` 추가 (`"ACTIVE"` 기본값) |

---

## 3. rules 필드 매핑

| v1 필드 | v2 처리 |
|---|---|
| `adrg` | **그대로 유지** |
| `mdc` | **그대로 유지** |
| `title` | → `title` + `title_raw`(동일) + `title_effective`(동일) |
| `subtitle` | **그대로 유지** |
| `condition_text` | → `condition_text_raw`(원문) + `condition_text_effective`(교정 반영) |
| `source_page` | → `source_refs[]` |
| `condition_summary` | 제거 (UI 표시는 `condition_groups_display`에서) |
| `condition_groups` | → `condition_groups_display`로 이름 변경 |
| `aadrg_mappings` | 확장 (아래 참조) |
| `condition_expression` | 완성 (9개 모두 완전한 node_type 트리) |
| `abc_basis` | `source_refs[]`의 `evidence_type: "ABC_CLASSIFICATION"` 항목으로 통합 |
| _(없음)_ | `correction_refs[]` 추가 |
| _(없음)_ | `notes` 추가 |
| _(없음)_ | `status` 추가 |

### aadrg_mappings 필드 매핑

| v1 필드 | v2 처리 |
|---|---|
| `aadrg` | **그대로 유지** |
| `aadrg_name` | → `aadrg_name_raw` + `aadrg_name_effective` |
| `group_code` | → `abc_classification.group_code`로 이동 |
| `group_name` | → `abc_classification.group_name`으로 이동 |
| `abc_status: "V46_OFFICIAL_SAME_CODE_COMPATIBLE"` | → `abc_classification.status: "OFFICIAL_PDF_EXACT_CODE"` |
| _(없음)_ | `age_or_other_split_text` 추가 (null) |
| _(없음)_ | `source_refs[]` 추가 |

---

## 4. condition_expression 변환 상세

| ADRG | v1 상태 | v2 변환 |
|---|---|---|
| E011 | `op`/`predicate` 키, 구조 있음 | `node_type` 키로 전환, `node_id`/`label`/`source_refs` 추가 |
| E501 | `{}` 빈 객체 | AND(TABLE_MATCH·vent, TABLE_MATCH·rrt, NUMERIC_THRESHOLD≥96h) |
| E502 | `{}` 빈 객체 | AND(TABLE_MATCH·vent, NOT·rrt, NUMERIC_THRESHOLD≥96h) |
| E511 | `{}` 빈 객체 | AND(TABLE_MATCH·vent, TABLE_MATCH·rrt, NOT·NUMERIC_THRESHOLD≥96h) |
| E512 | `{}` 빈 객체 | AND(TABLE_MATCH·vent, NOT·rrt, NOT·NUMERIC_THRESHOLD≥96h) |
| F022 | `op`/`predicate` 키, 구조 있음 | `node_type` 키로 전환, 교정 `correction_refs` 추가 |
| F136 | `op`/`predicate` 키, 구조 있음 | `node_type` 키로 전환, `PRINCIPAL_DIAGNOSIS_EXCLUSION` 적용 |
| F194 | `{}` 빈 객체 | AND(PD, OR(TABLE_CODE_COUNT_AT_LEAST≥2, AND·ADC4J)) |
| F195 | `{}` 빈 객체 | AND(PD, TABLE_MATCH·proc) |

---

## 5. UI 호환 어댑터 항목 (`app/schema_v2_adapter.py`)

v2 JSON을 읽어 현재 `KDRGDataStore`가 기대하는 v1 호환 딕셔너리 구조로 변환한다.
실제 runtime 데이터 파일은 아직 v2로 교체하지 않으므로, 어댑터는 **의미 동일성 검증
전용**으로만 사용한다.

주요 변환 항목:
- `table.source_refs → source_page` (첫 번째 refs의 `printed_page`)
- `member.name_ko_effective → name_ko`, `name_en_effective → name_en`
- `rule.condition_groups_display → condition_groups`
- `rule.aadrg_mappings[].abc_classification.group_code → group_code`
- `rule.aadrg_mappings[].abc_classification.group_name → group_name`
- `rule.aadrg_mappings[].aadrg_name_effective → aadrg_name`
- `abc_classification.status "OFFICIAL_PDF_EXACT_CODE" → abc_status "V46_OFFICIAL_SAME_CODE_COMPATIBLE"`

---

## 6. 전체 MDC 확장 전 남은 위험

| 위험 항목 | 내용 |
|---|---|
| 코드명 미검증 | `name_ko_effective` 값이 V47_PROC_MASTER_XLSX와 대조되지 않음 |
| 교정표 개별 항목 미파싱 | V47_CORR_20260501_HWPX 교정 항목 중 파일럿 9개 외 반영 안 됨 |
| 부록 교차검증 미수행 | V47_APPENDIX_PDF와 비교하지 않음 |
| sha256 미기재 | sources의 sha256 필드가 null |

---

## 7. 다음 단계 권고

1. v2 JSON 구조와 어댑터의 의미 동일성 검증이 PASS 확인 후 UI v0.2.0 준비.
2. 전체 MDC 확장 시 본문 PDF 파서 → 모든 ADRG/TABLE/member 변환 → v2 스키마 검증 순서로 진행.
3. V47_PROC_MASTER_XLSX 읽기 기능을 추가해 `name_ko_effective` 일괄 검증.
4. Runtime 데이터를 v2로 교체할 때 `schema_v2_adapter.py`의 변환 로직을 `KDRGDataStore`에 통합.
