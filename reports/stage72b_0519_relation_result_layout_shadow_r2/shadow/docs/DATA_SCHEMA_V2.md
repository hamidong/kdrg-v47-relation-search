# DATA_SCHEMA_V2 — KDRG V4.7 관계 데이터 스키마 v2 명세

이 문서는 `data/kdrg_v47_pilot_schema_v2.json` 및 향후 전체 데이터 파일에서
사용하는 스키마 v2의 전체 필드 명세를 기록한다.

---

## 최상위 구조

```json
{
  "meta":             {},
  "sources":          [],
  "mdc_master":       [],
  "tables":           [],
  "rules":            [],
  "derived_indexes":  {},
  "validation_summary": {}
}
```

---

## 1. meta

| 필드 | 유형 | 설명 |
|---|---|---|
| `schema_version` | string | `"2"` — 스키마 버전 |
| `dataset_version` | string | 날짜_내용 형식 식별자 |
| `kdrg_version` | string | `"KDRG V4.7"` |
| `effective_date` | string | ISO 날짜(데이터 유효 시작일) |
| `correction_cutoff_date` | string | 반영된 교정표 최신 날짜 |
| `data_scope` | string | 데이터 범위 설명 |
| `generated_at` | string | ISO datetime |
| `generated_by` | string | 생성 주체 |
| `source_manifest_version` | string | 원천자료 목록 버전 |
| `runtime_status` | string | `PILOT_PARALLEL_VALIDATION` \| `MDC_PARTIAL` \| `FULL_BETA` \| `FULL_RELEASE` |
| `notes` | string | 자유 기재 |

---

## 2. sources

원천자료를 `source_id`로 관리. 모든 필드의 `source_refs[]`는 여기 선언된 `source_id`만 참조한다.

| 필드 | 유형 |
|---|---|
| `source_id` | string (고유) |
| `source_type` | enum: `BASE_MANUAL_PDF` \| `APPENDIX_PDF` \| `CORRECTION_HWPX` \| `PROCEDURE_MASTER_XLSX` \| `GROUP_NAME_MASTER_XLSX` \| `ABC_REGULATION_PDF` |
| `file_name` | string |
| `title` | string |
| `effective_date` | string |
| `correction_cutoff_date` | string \| null |
| `authority` | string |
| `usage_scope` | string |
| `sha256` | string \| null |
| `included_in_runtime` | boolean — false이면 검증용 참조에만 사용 |
| `notes` | string \| null |

---

## 3. mdc_master

v1과 동일. `mdc`, `name`, `aliases[]`.

---

## 4. tables

| 필드 | 유형 | 비고 |
|---|---|---|
| `table_id` | string | 전역 고유키. 표 번호는 지역 번호이므로 사용 불가 |
| `owner_adrg` | string | 이 TABLE을 조건식에서 사용하는 ADRG |
| `printed_label` | string | 원문 인쇄 표기(예: "시술명 table1") |
| `display_label` | string | UI 표시용 레이블(추가 설명 포함 가능) |
| `table_role` | enum | `PRINCIPAL_DIAGNOSIS` \| `SECONDARY_DIAGNOSIS` \| `PROCEDURE` \| `TEST_OR_PROCEDURE` \| `ADD_ON_CODE` \| `EXCLUSION_SET` \| `DERIVED_SET` \| `OTHER` |
| `code_type` | string | 코드 유형 한글 레이블 |
| `source_refs` | array | 페이지·증거 참조 |
| `member_count` | integer | `members` 개수와 항상 일치 |
| `members` | array | 아래 member 구조 참조 |
| `derivation` | string \| null | DERIVED_SET인 경우 파생 근거 설명 |
| `status` | string | `ACTIVE` \| `CORRECTION_UPDATED` \| `DEPRECATED` |

### member 필드

| 필드 | 유형 |
|---|---|
| `code` | string |
| `name_ko_raw` | string — 원문 명칭 |
| `name_ko_effective` | string — 교정 후 명칭(교정 없으면 raw와 동일) |
| `name_en_raw` | string |
| `name_en_effective` | string |
| `original_order` | integer |
| `source_refs` | array |
| `correction_refs` | array — 교정 적용 항목에만 기재 |
| `status` | string: `ACTIVE` \| `CORRECTION_ADDED` \| `DEPRECATED` |

---

## 5. rules

| 필드 | 유형 | 비고 |
|---|---|---|
| `adrg` | string | |
| `mdc` | string | |
| `title` | string | |
| `subtitle` | string | |
| `title_raw` | string | 원문 표기 |
| `title_effective` | string | 교정 후 표기 |
| `aadrg_mappings` | array | 아래 참조 |
| `condition_text_raw` | string | 원문 조건 텍스트 |
| `condition_text_effective` | string | 교정 반영 조건 텍스트 |
| `condition_expression` | object | 논리 원본(node_type 트리) |
| `condition_groups_display` | array | UI 표시용 파생 데이터 — v1 `condition_groups` 계승 |
| `source_refs` | array | |
| `correction_refs` | array | 교정 적용 시 |
| `notes` | string \| null | |
| `status` | string | `ACTIVE` \| `CORRECTION_UPDATED` \| `DEPRECATED` |

### aadrg_mappings 항목

| 필드 | 유형 |
|---|---|
| `aadrg` | string |
| `aadrg_name_raw` | string |
| `aadrg_name_effective` | string |
| `abc_classification` | object — 아래 참조 |
| `age_or_other_split_text` | string \| null |
| `source_refs` | array |

### abc_classification

| 필드 | 유형 |
|---|---|
| `group_code` | string: `"A"` \| `"B"` \| `"C"` |
| `group_name` | string |
| `status` | enum: 아래 허용 값 참조 |
| `source_id` | string |
| `source_page` | string \| null |
| `exact_code_match` | boolean |
| `notes` | string \| null |

**허용 status 값**

| 값 | 의미 |
|---|---|
| `OFFICIAL_PDF_EXACT_CODE` | 별표1 PDF에서 AADRG 코드 정확일치로 확인 |
| `NOT_LISTED_IN_OFFICIAL_PDF` | 별표1 PDF에 해당 코드 없음 |
| `V47_CLASSIFICATION_UNRESOLVED` | 분류 미확정 |
| `MERGED_FROM_MULTIPLE_PREDECESSORS` | 복수 이전 코드에서 병합 |
| `PROVISIONAL_INTERNAL_ONLY` | 내부 검토용 — **사용자 화면 표시 금지** |

---

## 6. condition_expression 노드 구조

`schemas/condition_expression_schema_v2.json` 참조.

핵심 허용 `node_type`:

- 논리 결합: `AND`, `OR`, `NOT`
- 코드/TABLE 조건: `TABLE_MATCH`, `CODE_PRESENT`, `CODE_ABSENT`
- 집계 조건: `TABLE_CODE_COUNT_AT_LEAST`
- 수치 조건: `NUMERIC_THRESHOLD`, `AGE_RANGE`, `WEIGHT_RANGE`, `LENGTH_OF_STAY`
- 특수: `PRINCIPAL_DIAGNOSIS_EXCLUSION`, `OTHER_TEXT_CONDITION`

**중요 해석 원칙**

1. 같은 TABLE 안의 여러 코드는 기본적으로 대안(`ANY_ONE_CODE`)이다.
2. 공식으로 2개 이상이 명시된 경우에만 `TABLE_CODE_COUNT_AT_LEAST`를 사용한다.
3. 서로 다른 OR 가지의 코드를 하나의 충족조건으로 합치지 않는다.
4. 미포함/제외조건은 양의 포함관계 노드와 분리한다(`NOT` 래핑).
5. 시간·연령·재원일수 등 코드로만 입력받을 수 없는 조건은 `OTHER_TEXT_CONDITION`
   (`machine_evaluable: false`)으로 표현하거나 `NUMERIC_THRESHOLD`로 임계값만 보존한다.

---

## 7. derived_indexes

런타임 성능용 역색인. 생성 스크립트 또는 데이터 로더가 자동 계산한다.

```json
{
  "code_to_table_ids": { "O1311": ["V47_E04_E011_PROC_1"], ... },
  "table_id_to_adrg_ids": { "V47_E04_E011_PROC_1": ["E011"], ... },
  "exclusion_table_id_to_adrg_ids": {}
}
```

---

## 8. validation_summary

데이터 파일 생성 시 검증 결과를 요약 기록한다.

```json
{
  "generated_at": "...",
  "adrg_count": 9,
  "table_count": 15,
  "total_member_count": 133,
  "source_integrity": "PASS",
  "condition_expression_completeness": "PASS",
  "abc_classification_status": "ALL_OFFICIAL_PDF_EXACT_CODE",
  "errors": [],
  "warnings": []
}
```
