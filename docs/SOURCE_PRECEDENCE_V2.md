# SOURCE_PRECEDENCE_V2 — KDRG V4.7 원천자료 우선순위 (Schema v2 기준)

Schema v2부터 모든 원천자료는 `sources[]` 배열에서 `source_id`로 관리되며,
모든 데이터 항목(rule, table, member, abc_classification 등)은 `source_refs[]`를
통해 구체적인 원천자료·페이지·증거 유형을 기록한다.

---

## 1. 조건식(condition_expression) 및 TABLE 소속 우선순위

| 우선순위 | source_id | 자료 |
|---|---|---|
| 1 | `V47_CORR_20260501_HWPX` | KDRG 일반용(V4.7) 교정표 2026-05-01 |
| 2 | `V47_CORR_20260301_HWPX` | KDRG 일반용(V4.7) 교정표 2026-03-01 |
| 3 | `V47_MAIN_PDF` | KDRG V4.7 분류집 본문 PDF |

교정표와 본문 내용이 충돌할 경우 **교정표가 항상 우선**한다.  
`source_refs[].evidence_type = "CORRECTION"` 항목은 교정 적용일도 함께 기록한다.

---

## 2. 시술·처치 코드의 존재 및 공식 명칭

| 우선순위 | source_id | 자료 | 주의사항 |
|---|---|---|---|
| 1 | `V47_PROC_MASTER_XLSX` | 시술 등 목록(V4.7) XLSX | **TABLE 소속 판단에 이 자료만으로 사용 금지** |

이 XLSX는 코드 존재 여부와 공식 명칭(`name_ko_effective`, `name_en_effective`)의
교차검증에만 사용한다. 특정 코드가 특정 TABLE에 속한다는 근거를 이 파일에서
**단독으로** 도출하지 않는다.

---

## 3. ADRG / AADRG / RDRG 계층 및 명칭

| 우선순위 | source_id | 자료 |
|---|---|---|
| 1 | `V47_GROUP_NAME_XLSX` | 질병군명칭(V4.7) XLSX |

`aadrg_name_effective` 값은 이 XLSX를 참조한다.  
명칭 변동이 없는 경우 `aadrg_name_raw == aadrg_name_effective`.

---

## 4. A/B/C 질병군 분류

| 우선순위 | source_id | 자료 |
|---|---|---|
| **유일 공식** | `V47_ABC_PDF` | [별표 1] 입원환자의 질병군별 질병의 종류 최신 고시본 |

### 적용 원칙

1. **AADRG 코드 정확일치**만 공식 적용한다.
   - 예) 별표1 PDF에 "E0110"이 A군으로 명시된 경우에만 `OFFICIAL_PDF_EXACT_CODE`.
2. 명칭 유사도나 과거 코드 코드 승계로 자동 확정 **금지**.
3. XLSX, 분류집 부록, 분류집 본문에서 A/B/C를 추정하는 것 **금지**.
4. 별표1 PDF에 코드가 없으면 `abc_classification.status = "NOT_LISTED_IN_OFFICIAL_PDF"`.
5. 코드가 복수 원천에서 합산·병합된 경우 `"MERGED_FROM_MULTIPLE_PREDECESSORS"`.

### 금지 status

- `"PROVISIONAL_INTERNAL_ONLY"` — 내부 검토 목적의 임시값. 사용자 화면에 공식값처럼 **표시 금지**.

---

## 5. 코드 → MDC/ADRG 역색인

| 우선순위 | source_id | 역할 |
|---|---|---|
| 교차검증 | `V47_APPENDIX_PDF` | 분류집 부록 |

- 본문 TABLE 소속을 부록만으로 **새로 만들지 않는다**.
- 부록은 기존 본문 기반 TABLE 소속의 교차검증 증거로만 기록한다
  (`evidence_type = "CROSS_VALIDATION"`).

---

## 6. raw와 effective 값 보존 원칙

| 원칙 | 설명 |
|---|---|
| 원문값 삭제 금지 | `_raw` 필드는 원천자료 그대로의 값을 보존 |
| 교정 후 값 분리 | 교정이 적용된 경우 `_effective` 필드에 별도 기록 |
| 교정 미적용 시 동일 | 교정이 없으면 `_raw == _effective` |

---

## 7. 이번 파일럿(schema v2 병렬검증) 적용 범위

이번 단계에서 v2로 변환한 9개 ADRG(E011/E501/E502/E511/E512/F022/F136/F194/F195)는
전체 분류집 파싱 없이 기존 파일럿 데이터를 v2 스키마로 변환한 것이다.
따라서 아래 자료들은 **향후 전체 확장 시** 반영한다.

- V47_MAIN_PDF 전체 파싱 → 미적용
- V47_CORR_20260501_HWPX 개별 항목 파싱 → 미적용
- V47_PROC_MASTER_XLSX 코드명 정합 → 미적용
- V47_GROUP_NAME_XLSX 전체 명칭 → 미적용
- V47_APPENDIX_PDF 교차검증 → 미적용
