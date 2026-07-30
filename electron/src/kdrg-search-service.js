'use strict';

const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const {
  normalizeSpace,
  normalizeEntityId,
  normalizeQuery,
  queryTokens,
  uniqueStrings,
} = require('./search-normalizer');

const SERVICE_SCHEMA_VERSION = 'kdrg-runtime-search-service-v1';
const RESPONSE_SCHEMA_VERSION = 'kdrg-runtime-search-response-v1';
const RELATION_RESPONSE_SCHEMA_VERSION = 'kdrg-runtime-relation-response-v1';
const SUPPORTED_DATA_SCHEMA = 'kdrg-v47-search-integrated-v2';
const ENTITY_TYPES = Object.freeze(['CODE', 'ADRG', 'AADRG', 'RDRG', 'TABLE']);
const ENTITY_ORDER = Object.freeze(
  Object.fromEntries(ENTITY_TYPES.map((name, index) => [name, index])),
);
const RELATION_LEVEL_ORDER = Object.freeze({ strict: 0, split: 1, partial: 2 });
const RELATION_LEVEL_LABELS = Object.freeze({
  strict: '같은 조건 선택지',
  split: '같은 ADRG · 다른 조건 선택지',
  partial: '일부 코드만 연결',
});
const CODE_TYPE_LABELS = Object.freeze({
  AUTO: '자동판별',
  DIAGNOSIS: '상병코드',
  SECONDARY_DIAGNOSIS: '기타진단코드',
  PROCEDURE: '수술·처치코드',
  TEST: '검사·처치코드',
  ADD_ON: '부가코드',
  OTHER: '기타 조건 코드',
});
const DIAGNOSIS_ROLES = new Set([
  'principal_diagnosis', 'diagnosis', 'secondary_diagnosis', 'principal_or_secondary_diagnosis',
]);
const ADD_ON_ROLES = new Set(['add_on_code']);
const PROCEDURE_ROLES = new Set(['procedure', 'text:procedure_count']);

class KdrgSearchError extends Error {
  constructor(message) {
    super(message);
    this.name = 'KdrgSearchError';
  }
}

function clone(value) {
  if (value === undefined) {
    return undefined;
  }
  return JSON.parse(JSON.stringify(value));
}

function readJson(filePath) {
  let raw;
  try {
    raw = fs.readFileSync(filePath, 'utf8');
  } catch (error) {
    if (error?.code === 'ENOENT') {
      throw new KdrgSearchError(`통합 검색 데이터가 없습니다: ${filePath}`);
    }
    throw new KdrgSearchError(`통합 검색 JSON을 읽을 수 없습니다: ${filePath} | ${error.message}`);
  }
  let payload;
  try {
    payload = JSON.parse(raw);
  } catch (error) {
    throw new KdrgSearchError(`통합 검색 JSON을 읽을 수 없습니다: ${filePath} | ${error.message}`);
  }
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    throw new KdrgSearchError(`통합 검색 JSON 최상위 구조가 object가 아닙니다: ${filePath}`);
  }
  return payload;
}

function canonicalize(value) {
  if (Array.isArray(value)) {
    return value.map(canonicalize);
  }
  if (value && typeof value === 'object') {
    if (value instanceof Set) {
      return [...value].sort();
    }
    return Object.fromEntries(
      Object.keys(value)
        .sort()
        .map((key) => [key, canonicalize(value[key])]),
    );
  }
  return value;
}

function canonicalJson(value) {
  return JSON.stringify(canonicalize(value));
}

function sha256Canonical(value) {
  return crypto.createHash('sha256').update(canonicalJson(value), 'utf8').digest('hex');
}

function pythonFString(value, fallback = '') {
  if (value === undefined) return fallback;
  if (value === null) return 'None';
  return String(value);
}

function compareAscii(left, right) {
  if (left < right) return -1;
  if (left > right) return 1;
  return 0;
}

class KdrgSearchService {
  constructor(dataPath) {
    if (!dataPath) {
      dataPath = path.resolve(__dirname, '..', '..', 'data', 'kdrg_v47_search_integrated.json');
    }
    this.dataPath = path.resolve(String(dataPath));
    this.data = readJson(this.dataPath);
    this.validateData();
    this.meta = this.data.meta;
    this.indexes = this.data.indexes;
    this.runtimeSemanticRules = clone(this.data.runtime_semantic_rules ?? {});
    this.records = Object.freeze({
      ADRG: this.data.adrg_records,
      AADRG: this.data.aadrg_records,
      RDRG: this.data.rdrg_records,
      TABLE: this.data.logical_table_records,
      CODE: this.data.code_records,
    });
    this.idFields = Object.freeze({
      ADRG: 'adrg',
      AADRG: 'aadrg',
      RDRG: 'code',
      TABLE: 'logical_table_id',
      CODE: 'code',
    });
    this.recordMaps = Object.fromEntries(
      Object.entries(this.records).map(([entityType, rows]) => [
        entityType,
        new Map(
          rows.map((row) => [
            normalizeEntityId(row[this.idFields[entityType]], entityType),
            row,
          ]),
        ),
      ]),
    );
    const semantic = this.buildSemanticContextIndex();
    this.semanticContextIndex = semantic.index;
    this.semanticContextSummary = semantic.summary;
    this.astByAdrg = new Map(
      (this.data.condition_ast_records ?? []).map((row) => [String(row.adrg ?? ''), row]),
    );
    this.tableCategoryIndex = this.buildTableCategoryIndex();
    this.codeTypesByCode = this.buildCodeTypeIndex();
    this.conditionGroupsByAdrg = new Map(
      (this.data.adrg_records ?? []).map((row) => {
        const adrg = String(row.adrg ?? '');
        return [adrg, this.buildConditionGroups(adrg, this.astByAdrg.get(adrg) ?? null)];
      }),
    );
    this.searchDocuments = this.buildSearchDocuments();
  }

  validateData() {
    const meta = this.data.meta ?? {};
    const schema = String(meta.schema_version ?? '');
    if (schema !== SUPPORTED_DATA_SCHEMA) {
      throw new KdrgSearchError(
        `지원하지 않는 통합 데이터 schema입니다: ${schema || '<EMPTY>'} | expected=${SUPPORTED_DATA_SCHEMA}`,
      );
    }
    const requiredLists = [
      'adrg_records',
      'aadrg_records',
      'rdrg_records',
      'logical_table_records',
      'condition_ast_records',
      'code_records',
    ];
    const missing = requiredLists.filter((key) => !Array.isArray(this.data[key])).sort();
    if (missing.length) {
      throw new KdrgSearchError(`통합 검색 JSON 필수 배열이 없습니다: ${missing.join(', ')}`);
    }
    if (!this.data.indexes || typeof this.data.indexes !== 'object' || Array.isArray(this.data.indexes)) {
      throw new KdrgSearchError('통합 검색 JSON indexes가 없습니다');
    }
    if (String(this.data.validation?.status ?? '') !== 'PASS') {
      throw new KdrgSearchError('통합 검색 JSON 자체 validation 상태가 PASS가 아닙니다');
    }
  }

  status() {
    return {
      service_schema_version: SERVICE_SCHEMA_VERSION,
      response_schema_version: RESPONSE_SCHEMA_VERSION,
      relation_response_schema_version: RELATION_RESPONSE_SCHEMA_VERSION,
      data_schema_version: this.meta.schema_version ?? null,
      data_version: this.meta.data_version ?? null,
      data_state: this.meta.state ?? null,
      data_path: this.dataPath,
      counts: clone(this.meta.counts ?? {}),
      policies: clone(this.meta.policies ?? {}),
      semantic_context_counts: clone(this.semanticContextSummary),
      ready: true,
    };
  }

  titleSubtitle(entityType, row) {
    if (entityType === 'CODE') {
      const names = (row.names ?? []).map(String).filter(Boolean);
      return [String(row.code ?? ''), names.length ? names.slice(0, 2).join(' / ') : '코드명 원천 미수록'];
    }
    if (entityType === 'ADRG') {
      const title = `${pythonFString(row.adrg)} · ${pythonFString(row.adrg_name)}`.replace(/^[ ·]+|[ ·]+$/g, '');
      return [title, `MDC ${pythonFString(row.mdc, '-')} · AADRG ${pythonFString(row.aadrg_count, 0)}개`];
    }
    if (entityType === 'AADRG') {
      const title = `${pythonFString(row.aadrg)} · ${pythonFString(row.group_name)}`.replace(/^[ ·]+|[ ·]+$/g, '');
      const label = String(row.classification_display_label || '분류 미부여');
      return [title, `ADRG ${pythonFString(row.adrg, '-')} · ${label}`];
    }
    if (entityType === 'RDRG') {
      const title = `${pythonFString(row.code)} · ${pythonFString(row.group_name)}`.replace(/^[ ·]+|[ ·]+$/g, '');
      return [title, `AADRG ${pythonFString(row.aadrg, '-')} · ${row.severity_name || '중증도 명칭 없음'}`];
    }
    return [
      String(row.display_name || row.logical_table_id || ''),
      `코드 ${row.code_count ?? 0}개 · 관련 ADRG ${(row.related_adrgs ?? []).length}개`,
    ];
  }

  buildSearchDocuments() {
    const documents = new Map();
    for (const [entityType, rows] of Object.entries(this.records)) {
      const idField = this.idFields[entityType];
      for (const row of rows) {
        const entityId = String(row[idField] ?? '');
        const [title, subtitle] = this.titleSubtitle(entityType, row);
        const fields = {
          entity_id: [entityId],
          title: [title],
          subtitle: [subtitle],
        };
        if (entityType === 'CODE') {
          fields.name = (row.names ?? []).map(String);
          fields.role = (row.roles ?? []).map(String);
          fields.table = (row.logical_table_ids ?? []).map(String);
          fields.adrg = (row.related_adrgs ?? []).map(String);
        } else if (entityType === 'ADRG') {
          fields.name = [String(row.adrg_name ?? '')];
          fields.aadrg = (row.aadrg_codes ?? []).map(String);
          fields.classification = (row.abc_display_labels ?? []).map(String);
        } else if (entityType === 'AADRG') {
          fields.name = [String(row.group_name ?? '')];
          fields.adrg = [String(row.adrg ?? '')];
          fields.rdrg = (row.rdrg_codes ?? []).map(String);
          fields.classification = [String(row.classification_display_label ?? '')];
        } else if (entityType === 'RDRG') {
          fields.name = [String(row.group_name ?? ''), String(row.severity_name ?? '')];
          fields.aadrg = [String(row.aadrg ?? '')];
          fields.adrg = [String(row.adrg ?? '')];
        } else if (entityType === 'TABLE') {
          fields.name = [String(row.display_name ?? '')];
          fields.type = [String(row.logical_table_type ?? ''), String(row.logical_table_scope ?? '')];
          fields.code = (row.codes ?? []).map(String);
          fields.adrg = (row.related_adrgs ?? []).map(String);
        }
        const normalizedFields = Object.fromEntries(
          Object.entries(fields).map(([key, values]) => [
            key,
            values.filter((value) => normalizeSpace(value)).map(normalizeQuery),
          ]),
        );
        const flatValues = Object.values(normalizedFields).flat();
        documents.set(`${entityType}:${entityId}`, {
          entity_type: entityType,
          entity_id: entityId,
          title,
          subtitle,
          fields: normalizedFields,
          haystack: flatValues.join(' '),
          tokens: new Set(queryTokens(flatValues.join(' '))),
        });
      }
    }
    return documents;
  }

  buildSemanticContextIndex() {
    const output = new Map();
    const summary = new Map();
    const bump = (key) => summary.set(key, (summary.get(key) ?? 0) + 1);
    const occurrenceQualifier = (node, tableIndex) => {
      const nodeType = String(node.node_type ?? '');
      const semanticType = String(node.semantic_type ?? '');
      if (nodeType === 'TABLE_REF') return 'DIRECT_TABLE_MEMBERSHIP';
      if (semanticType === 'optional_table_presence') {
        return tableIndex === 0 ? 'REQUIRED_TABLE' : 'OPTIONAL_COMPANION_TABLE';
      }
      if (semanticType === 'procedure_count') return 'PROCEDURE_COUNT_TABLE';
      if (semanticType === 'major_problem') return 'MAJOR_PROBLEM_TABLE';
      if (semanticType === 'qualified_table_exclusion') return 'QUALIFIED_TABLE_EXCLUSION_TEXT';
      if (semanticType === 'qualified_table_condition') return 'QUALIFIED_TABLE_CONDITION_TEXT';
      return 'SEMANTIC_TEXT_TABLE';
    };
    const positiveLabels = {
      DIRECT_TABLE_MEMBERSHIP: '기본 포함조건',
      REQUIRED_TABLE: '기본 포함조건',
      OPTIONAL_COMPANION_TABLE: '선택적으로 함께 적용',
      PROCEDURE_COUNT_TABLE: '건수 조건 TABLE',
      MAJOR_PROBLEM_TABLE: '진단 건수 조건 TABLE',
      QUALIFIED_TABLE_CONDITION_TEXT: '원문 한정 조건 TABLE',
      QUALIFIED_TABLE_EXCLUSION_TEXT: '원문 한정 조건 TABLE',
      SEMANTIC_TEXT_TABLE: '의미 조건 TABLE',
    };

    for (const ast of this.data.condition_ast_records ?? []) {
      const adrg = String(ast.adrg ?? '');
      const astId = String(ast.condition_ast_id ?? '');
      const nodes = new Map(
        (ast.nodes ?? [])
          .filter((node) => String(node.node_id ?? ''))
          .map((node) => [String(node.node_id), node]),
      );
      const rootId = String(ast.root_node_id ?? '');
      if (!nodes.has(rootId)) {
        throw new KdrgSearchError(`조건 AST root가 없습니다: ${astId} / ${rootId}`);
      }
      const visited = new Set();
      const walk = (nodeId, polarity, operatorPath) => {
        if (visited.has(nodeId)) {
          throw new KdrgSearchError(`조건 AST 중복 순회 또는 cycle: ${astId} / ${nodeId}`);
        }
        visited.add(nodeId);
        const node = nodes.get(nodeId);
        const nodeType = String(node.node_type ?? '');
        const semanticType = String(node.semantic_type ?? '');
        const evaluationMode = String(node.evaluation_mode ?? '');
        const fragment = String(node.source_fragment || node.display_text || '');
        const tableIds = uniqueStrings(node.logical_table_ids ?? []);
        const insideBase = operatorPath.some(
          (segment) => segment.operator === 'EXCLUSION' && segment.branch === 'base',
        );
        const insideExcluded = operatorPath.some(
          (segment) => segment.operator === 'EXCLUSION' && segment.branch === 'excluded',
        );
        tableIds.forEach((tableId, tableIndex) => {
          const qualifier = occurrenceQualifier(node, tableIndex);
          const isPositive = polarity >= 0;
          let context;
          let displayLabel;
          if (isPositive) {
            if (qualifier === 'OPTIONAL_COMPANION_TABLE') {
              context = 'optional_companion_table';
            } else if (nodeType === 'TEXT_CONDITION') {
              context = 'semantic_text_condition';
            } else {
              context = 'positive_required_table';
            }
            displayLabel = positiveLabels[qualifier] ?? '기본 포함조건';
          } else {
            context = 'negative_or_exclusion_reference';
            displayLabel = '제외 대상';
          }
          const key = `${adrg}\u0000${tableId}`;
          if (!output.has(key)) output.set(key, []);
          output.get(key).push({
            context,
            display_label: displayLabel,
            display_role: isPositive ? 'INCLUDE' : 'EXCLUDE',
            polarity_sign: isPositive ? 1 : -1,
            condition_ast_id: astId,
            node_id: nodeId,
            node_type: nodeType,
            source_fragment: fragment,
            semantic_type: semanticType || null,
            evaluation_mode: evaluationMode || null,
            occurrence_qualifier: qualifier,
            operator_path: clone(operatorPath),
            inside_exclusion_base: insideBase,
            inside_exclusion_excluded: insideExcluded,
            legacy_exclusion_ancestor_collapse_would_misclassify: Boolean(
              isPositive && (insideBase || insideExcluded),
            ),
          });
          bump(context);
          bump(isPositive ? 'include_occurrence' : 'exclude_occurrence');
          if (insideBase) bump('exclusion_base_occurrence');
          if (insideExcluded) {
            bump('exclusion_excluded_occurrence');
            if (isPositive) bump('exclusion_excluded_final_include');
          }
          if (isPositive && (insideBase || insideExcluded)) {
            bump('legacy_misclassification_occurrence');
          }
        });
        const children = (node.child_node_ids ?? []).map(String);
        if (nodeType === 'NOT') {
          for (const childId of children) {
            walk(childId, -polarity, operatorPath.concat({
              node_id: nodeId,
              operator: 'NOT',
              branch: 'negated',
              polarity_after: polarity >= 0 ? -1 : 1,
            }));
          }
        } else if (nodeType === 'EXCLUSION') {
          if (children.length !== 2) {
            throw new KdrgSearchError(`EXCLUSION 자식은 정확히 2개여야 합니다: ${astId} / ${nodeId}`);
          }
          walk(children[0], polarity, operatorPath.concat({
            node_id: nodeId,
            operator: 'EXCLUSION',
            branch: 'base',
            polarity_after: polarity >= 0 ? 1 : -1,
          }));
          walk(children[1], -polarity, operatorPath.concat({
            node_id: nodeId,
            operator: 'EXCLUSION',
            branch: 'excluded',
            polarity_after: polarity >= 0 ? -1 : 1,
          }));
        } else {
          for (const childId of children) {
            walk(childId, polarity, operatorPath.concat({
              node_id: nodeId,
              operator: nodeType,
              branch: 'inherit',
              polarity_after: polarity >= 0 ? 1 : -1,
            }));
          }
        }
      };
      walk(rootId, 1, []);
      if (visited.size !== nodes.size) {
        const missing = [...nodes.keys()].filter((nodeId) => !visited.has(nodeId)).sort();
        throw new KdrgSearchError(`조건 AST 미도달 node가 있습니다: ${astId} / ${missing.slice(0, 10)}`);
      }
    }

    for (const [key, values] of output.entries()) {
      values.sort((left, right) =>
        compareAscii(String(left.condition_ast_id ?? ''), String(right.condition_ast_id ?? ''))
        || compareAscii(String(left.node_id ?? ''), String(right.node_id ?? ''))
        || compareAscii(String(left.display_role ?? ''), String(right.display_role ?? '')),
      );
    }
    summary.set('relationship_key_count', output.size);
    summary.set(
      'relationship_occurrence_count',
      [...output.values()].reduce((total, values) => total + values.length, 0),
    );
    return {
      index: output,
      summary: Object.fromEntries([...summary.entries()].sort(([a], [b]) => compareAscii(a, b))),
    };
  }


  static classifyCodeTypeText(...values) {
    const text = values.map((value) => String(value ?? '')).join(' ').toLowerCase();
    if (['secondary', 'other diagnosis', '기타진단', 'other_diagnosis'].some((token) => text.includes(token))) {
      return 'SECONDARY_DIAGNOSIS';
    }
    if (['diagnosis', '진단', 'principal', '주진단'].some((token) => text.includes(token))) {
      return 'DIAGNOSIS';
    }
    if (['add_on', 'addon', 'supplement', '부가', 'additional'].some((token) => text.includes(token))) {
      return 'ADD_ON';
    }
    if (['test', '검사'].some((token) => text.includes(token))) {
      return 'TEST';
    }
    if (['procedure', 'surgery', 'operation', '시술', '수술', '처치'].some((token) => text.includes(token))) {
      return 'PROCEDURE';
    }
    return 'OTHER';
  }

  buildTableCategoryIndex() {
    const evidence = new Map();
    const add = (tableId, value) => {
      if (!evidence.has(tableId)) evidence.set(tableId, new Set());
      evidence.get(tableId).add(value);
    };
    for (const ast of this.data.condition_ast_records ?? []) {
      for (const node of ast.nodes ?? []) {
        const nodeType = String(node.node_type ?? '');
        const semanticType = String(node.semantic_type ?? '');
        const role = String(node.table_role ?? '');
        const evidenceValue = role || (nodeType === 'TEXT_CONDITION' && semanticType ? `text:${semanticType}` : '');
        if (!evidenceValue) continue;
        for (const tableId of uniqueStrings(node.logical_table_ids ?? [])) add(String(tableId), evidenceValue);
      }
    }
    const output = new Map();
    for (const table of this.data.logical_table_records ?? []) {
      const tableId = String(table.logical_table_id ?? '');
      const values = evidence.get(tableId) ?? new Set();
      let category = 'OTHER';
      if ([...values].some((value) => DIAGNOSIS_ROLES.has(value))) category = 'DIAGNOSIS';
      else if ([...values].some((value) => ADD_ON_ROLES.has(value))) category = 'ADD_ON';
      else if ([...values].some((value) => PROCEDURE_ROLES.has(value))) category = 'PROCEDURE';
      else if ([...values].some((value) => String(value).toLowerCase().includes('test'))) category = 'TEST';
      output.set(tableId, category);
    }
    return output;
  }

  buildCodeTypeIndex() {
    const output = new Map();
    for (const row of this.data.code_records ?? []) {
      const normalizedCode = normalizeEntityId(row.code, 'CODE');
      const types = new Set();
      for (const role of row.roles ?? []) types.add(KdrgSearchService.classifyCodeTypeText(role));
      for (const tableId of row.logical_table_ids ?? []) {
        types.add(this.tableCategoryIndex.get(String(tableId)) ?? 'OTHER');
      }
      if (!types.size) types.add('OTHER');
      output.set(normalizedCode, types);
    }
    return output;
  }

  exactTableIdsForCode(code, codeType = 'AUTO') {
    const normalizedCode = normalizeEntityId(code, 'CODE');
    const row = this.recordMaps.CODE.get(normalizedCode);
    if (!row) return [];
    const tableIds = uniqueStrings(row.logical_table_ids ?? []);
    const selectedType = String(codeType ?? 'AUTO').toUpperCase();
    if (selectedType === 'AUTO') return tableIds;
    const codeTypes = this.codeTypesByCode.get(normalizedCode) ?? new Set();
    if (!codeTypes.has(selectedType)) return [];
    return tableIds.filter((tableId) =>
      (this.tableCategoryIndex.get(String(tableId)) ?? 'OTHER') === selectedType
      || codeTypes.has(selectedType),
    );
  }

  descendants(nodeId, nodes) {
    const found = new Set();
    const stack = [String(nodeId ?? '')];
    while (stack.length) {
      const current = stack.pop();
      if (!current || found.has(current)) continue;
      found.add(current);
      const node = nodes.get(current) ?? {};
      for (const childId of node.child_node_ids ?? []) stack.push(String(childId));
    }
    return found;
  }

  buildConditionGroups(adrg, ast) {
    if (!ast) return [];
    const nodeRows = Array.isArray(ast.nodes) ? ast.nodes : [];
    const nodes = new Map(
      nodeRows
        .filter((node) => String(node.node_id ?? ''))
        .map((node) => [String(node.node_id), node]),
    );
    const rootId = String(ast.root_node_id ?? '');
    const root = nodes.get(rootId) ?? {};
    const rootSet = rootId ? this.descendants(rootId, nodes) : new Set(nodes.keys());
    let branchIds = [];
    let shared = new Set();
    if (String(root.node_type ?? '') === 'OR' && (root.child_node_ids ?? []).length >= 2) {
      branchIds = (root.child_node_ids ?? []).map(String);
    } else {
      const directOr = (root.child_node_ids ?? [])
        .map((childId) => nodes.get(String(childId)))
        .find((node) =>
          String(node?.node_type ?? '') === 'OR' && (node?.child_node_ids ?? []).length >= 2,
        );
      if (directOr) {
        const orId = String(directOr.node_id ?? '');
        branchIds = (directOr.child_node_ids ?? []).map(String);
        const orDescendants = this.descendants(orId, nodes);
        shared = new Set([...rootSet].filter((nodeId) => !orDescendants.has(nodeId)));
      }
    }
    const branchSets = branchIds.length
      ? branchIds.map((branchId) => new Set([...this.descendants(branchId, nodes), ...shared]))
      : [rootSet.size ? rootSet : new Set(nodes.keys())];

    return branchSets.map((nodeSet, index) => {
      const includeTableIds = [];
      const excludeTableIds = [];
      const requirements = [];
      const includeSeen = new Set();
      const excludeSeen = new Set();
      const requirementSeen = new Set();
      for (const node of nodeRows) {
        const nodeId = String(node.node_id ?? '');
        if (!nodeSet.has(nodeId)) continue;
        const tableIds = uniqueStrings(node.logical_table_ids ?? []);
        for (const tableId of tableIds) {
          const contexts = this.semanticContextIndex.get(`${adrg}\u0000${tableId}`) ?? [];
          const context = contexts.find((value) => String(value.node_id ?? '') === nodeId) ?? {
            context: 'positive_required_table',
          };
          const negative = String(context.context ?? '') === 'negative_or_exclusion_reference';
          if (negative) {
            if (!excludeSeen.has(tableId)) {
              excludeSeen.add(tableId);
              excludeTableIds.push(tableId);
            }
          } else if (!includeSeen.has(tableId)) {
            includeSeen.add(tableId);
            includeTableIds.push(tableId);
          }
        }
        if (!tableIds.length && String(node.node_type ?? '') === 'TEXT_CONDITION') {
          const text = String(node.display_text || node.source_fragment || '').trim();
          if (text.length >= 2 && text.length <= 180 && !requirementSeen.has(text)) {
            requirementSeen.add(text);
            requirements.push(text);
          }
        }
      }
      return {
        group_no: index + 1,
        group_label: `조건식 ${index + 1}`,
        join_to_next_group: index + 1 < branchSets.length ? 'OR' : '',
        include_table_ids: includeTableIds,
        exclude_table_ids: excludeTableIds,
        requirements: requirements.slice(0, 12),
      };
    });
  }

  relationSearch(conditions, operator = 'AND', options = {}) {
    if (!Array.isArray(conditions) || conditions.length < 2 || conditions.length > 6) {
      throw new KdrgSearchError('복수 코드 관계검색은 2~6개 코드가 필요합니다');
    }
    const relationOperator = String(operator ?? 'AND').toUpperCase();
    if (!['AND', 'OR'].includes(relationOperator)) {
      throw new KdrgSearchError(`지원하지 않는 조건 관계입니다: ${operator}`);
    }
    const mdcFilter = String(options.mdc ?? '').toUpperCase().trim();
    const classFilter = String(options.classification ?? '').toUpperCase().trim();
    const conditionTables = conditions.map((condition) => {
      const code = String(condition.code ?? '').trim();
      const codeType = String(condition.codeType ?? 'AUTO').toUpperCase();
      const normalizedCode = normalizeEntityId(code, 'CODE');
      const tableIds = this.exactTableIdsForCode(code, codeType);
      const actualTypes = [...(this.codeTypesByCode.get(normalizedCode) ?? new Set())].sort(compareAscii);
      return {
        code,
        normalized_code: normalizedCode,
        code_type: codeType,
        code_type_label: CODE_TYPE_LABELS[codeType] ?? codeType,
        actual_code_types: actualTypes,
        exact_code_found: this.recordMaps.CODE.has(normalizedCode),
        table_ids: tableIds,
      };
    });
    const totalCount = conditionTables.length;
    const results = [];
    for (const row of this.data.adrg_records ?? []) {
      const adrg = String(row.adrg ?? '');
      if (mdcFilter && !this.recordMatchesMdc('ADRG', row, mdcFilter)) continue;
      if (classFilter && !this.recordMatchesClassification('ADRG', row, classFilter)) continue;
      const groups = this.conditionGroupsByAdrg.get(adrg) ?? [];
      if (!groups.length) continue;
      const positiveTableIds = new Set(groups.flatMap((group) => group.include_table_ids));
      const exclusionTableIds = new Set(groups.flatMap((group) => group.exclude_table_ids));
      if (conditionTables.some((condition) => condition.table_ids.some((tableId) => exclusionTableIds.has(tableId)))) {
        continue;
      }
      const codeMatches = conditionTables.map((condition) => {
        const matchedTableIds = condition.table_ids.filter((tableId) => positiveTableIds.has(tableId)).sort(compareAscii);
        return {
          ...condition,
          matched_table_ids: matchedTableIds,
          matched_tables: matchedTableIds.map((tableId) => this.summaryEntity('TABLE', tableId)),
        };
      });
      const matchedCount = codeMatches.filter((match) => match.matched_table_ids.length).length;
      if (relationOperator === 'AND' && matchedCount !== totalCount) continue;
      if (relationOperator === 'OR' && matchedCount === 0) continue;

      let strictGroupExists = false;
      const groupMatches = [];
      for (const group of groups) {
        const groupIds = new Set(group.include_table_ids);
        const matches = conditionTables.map((condition) => {
          const matchedTableIds = condition.table_ids.filter((tableId) => groupIds.has(tableId)).sort(compareAscii);
          return {
            code: condition.code,
            code_type: condition.code_type,
            matched_table_ids: matchedTableIds,
            matched_tables: matchedTableIds.map((tableId) => this.summaryEntity('TABLE', tableId)),
          };
        });
        const hitCount = matches.filter((match) => match.matched_table_ids.length).length;
        const allInputs = hitCount === totalCount;
        if (hitCount) {
          groupMatches.push({
            group_no: group.group_no,
            group_label: group.group_label,
            all_inputs: allInputs,
            hit_count: hitCount,
            matches,
            requirements: clone(group.requirements),
            exclude_table_ids: clone(group.exclude_table_ids),
            exclude_tables: group.exclude_table_ids.map((tableId) => this.summaryEntity('TABLE', tableId)),
          });
        }
        strictGroupExists = strictGroupExists || allInputs;
      }
      const relationLevel = matchedCount === totalCount && strictGroupExists
        ? 'strict'
        : matchedCount === totalCount
          ? 'split'
          : 'partial';
      const [title, subtitle] = this.titleSubtitle('ADRG', row);
      const sourceBlock = clone(row.source_block ?? {});
      results.push({
        entity_type: 'ADRG',
        entity_id: adrg,
        title,
        subtitle,
        relation_level: relationLevel,
        relation_level_label: RELATION_LEVEL_LABELS[relationLevel],
        matched_count: matchedCount,
        total_count: totalCount,
        code_matches: codeMatches,
        condition_groups: groupMatches,
        aadrg_records: (row.aadrg_codes ?? []).map((code) => this.summaryEntity('AADRG', code)),
        summary: this.summaryPayload('ADRG', row),
        source_page: sourceBlock.pdf_page_start ?? sourceBlock.pdf_page ?? null,
      });
    }
    results.sort((left, right) =>
      (RELATION_LEVEL_ORDER[left.relation_level] ?? 9) - (RELATION_LEVEL_ORDER[right.relation_level] ?? 9)
      || right.matched_count - left.matched_count
      || compareAscii(left.entity_id, right.entity_id),
    );
    const levelCounts = {};
    for (const result of results) {
      levelCounts[result.relation_level] = (levelCounts[result.relation_level] ?? 0) + 1;
    }
    return {
      schema_version: RELATION_RESPONSE_SCHEMA_VERSION,
      operator: relationOperator,
      filters: { mdc: mdcFilter || null, classification: classFilter || null },
      total_count: results.length,
      level_counts: levelCounts,
      conditions: conditionTables.map((condition) => ({
        code: condition.code,
        normalized_code: condition.normalized_code,
        code_type: condition.code_type,
        code_type_label: condition.code_type_label,
        actual_code_types: condition.actual_code_types,
        exact_code_found: condition.exact_code_found,
        table_ids: clone(condition.table_ids),
      })),
      results,
      disclaimer: '입력 코드가 같은 ADRG·조건식에 연결되는지를 보여주는 관계검색이며 최종 DRG 판정을 의미하지 않습니다.',
    };
  }

  normalizeEntityTypes(entityType) {
    if (entityType == null || entityType === 'ALL') return [...ENTITY_TYPES];
    const values = typeof entityType === 'string' ? [entityType] : [...entityType];
    const output = [];
    for (const value of values) {
      const name = String(value ?? '').toUpperCase();
      if (name === 'ALL') return [...ENTITY_TYPES];
      if (!ENTITY_TYPES.includes(name)) {
        throw new KdrgSearchError(`지원하지 않는 검색 유형입니다: ${value}`);
      }
      if (!output.includes(name)) output.push(name);
    }
    if (!output.length) throw new KdrgSearchError('검색 유형이 비어 있습니다');
    return output;
  }

  matchDocument(document, query, tokens) {
    const entityType = document.entity_type;
    const entityId = document.entity_id;
    const normalizedId = normalizeEntityId(entityId, entityType);
    const normalizedInputId = normalizeEntityId(query, entityType);
    const q = normalizeQuery(query);
    if (normalizedInputId && normalizedInputId === normalizedId) {
      return [1000, 'EXACT_ID', ['entity_id']];
    }
    const matchedFields = [];
    for (const [field, values] of Object.entries(document.fields)) {
      if (q && values.includes(q)) matchedFields.push(field);
    }
    if (matchedFields.length) {
      return [920, 'EXACT_TEXT', [...new Set(matchedFields)].sort()];
    }
    if (normalizedInputId && normalizedId.startsWith(normalizedInputId)) {
      return [840, 'PREFIX_ID', ['entity_id']];
    }
    if (tokens.length && tokens.every((token) => document.tokens.has(token))) {
      const fields = Object.entries(document.fields)
        .filter(([, values]) => {
          const fieldTokens = new Set(queryTokens(values.join(' ')));
          return tokens.some((token) => fieldTokens.has(token));
        })
        .map(([field]) => field);
      return [760, 'ALL_TOKENS', [...new Set(fields)].sort().length ? [...new Set(fields)].sort() : ['text']];
    }
    if (q && document.haystack.includes(q)) {
      const fields = Object.entries(document.fields)
        .filter(([, values]) => values.some((value) => value.includes(q)))
        .map(([field]) => field);
      return [680, 'CONTAINS', [...new Set(fields)].sort().length ? [...new Set(fields)].sort() : ['text']];
    }
    if (tokens.length && tokens.some((token) => document.tokens.has(token))) {
      const matched = tokens.filter((token) => document.tokens.has(token)).length;
      return [500 + Math.min(matched, 20), 'ANY_TOKEN', ['text']];
    }
    return null;
  }

  search(query, entityType = 'ALL', options = {}) {
    const queryText = normalizeSpace(query);
    if (!queryText) throw new KdrgSearchError('검색어를 입력해야 합니다');
    const limit = options.limit ?? 50;
    const offset = options.offset ?? 0;
    if (!Number.isInteger(limit) || limit < 1 || limit > 500) {
      throw new KdrgSearchError('limit은 1~500 범위여야 합니다');
    }
    if (!Number.isInteger(offset) || offset < 0) {
      throw new KdrgSearchError('offset은 0 이상이어야 합니다');
    }
    const entityTypes = this.normalizeEntityTypes(entityType);
    const tokens = queryTokens(queryText);
    const mdcFilter = String(options.mdc ?? '').toUpperCase().trim();
    const classFilter = String(options.classification ?? '').toUpperCase().trim();
    const scored = [];
    for (const document of this.searchDocuments.values()) {
      if (!entityTypes.includes(document.entity_type)) continue;
      const record = this.recordMaps[document.entity_type].get(
        normalizeEntityId(document.entity_id, document.entity_type),
      );
      if (mdcFilter && !this.recordMatchesMdc(document.entity_type, record, mdcFilter)) continue;
      if (classFilter && !this.recordMatchesClassification(document.entity_type, record, classFilter)) continue;
      const match = this.matchDocument(document, queryText, tokens);
      if (!match) continue;
      const [score, matchType, fields] = match;
      scored.push([score, document.entity_type, document.entity_id, fields, matchType]);
    }
    scored.sort((left, right) =>
      right[0] - left[0]
      || ENTITY_ORDER[left[1]] - ENTITY_ORDER[right[1]]
      || compareAscii(normalizeEntityId(left[2], left[1]), normalizeEntityId(right[2], right[1])),
    );
    const totalCount = scored.length;
    const page = scored.slice(offset, offset + limit);
    const results = page.map(([score, typeName, entityId, fields, matchType]) =>
      this.makeSearchResult(typeName, entityId, score, matchType, fields),
    );
    const typeCounts = {};
    for (const [, typeName] of scored) typeCounts[typeName] = (typeCounts[typeName] ?? 0) + 1;
    const orderedTypeCounts = Object.fromEntries(
      Object.entries(typeCounts).sort(([left], [right]) => ENTITY_ORDER[left] - ENTITY_ORDER[right]),
    );
    return {
      schema_version: RESPONSE_SCHEMA_VERSION,
      query: queryText,
      normalized_query: normalizeQuery(queryText),
      filters: {
        entity_types: entityTypes,
        mdc: mdcFilter || null,
        classification: classFilter || null,
      },
      total_count: totalCount,
      type_counts: orderedTypeCounts,
      offset,
      limit,
      has_more: offset + results.length < totalCount,
      results,
    };
  }

  recordMatchesMdc(entityType, record, mdc) {
    if (entityType === 'ADRG' || entityType === 'AADRG') {
      return String(record.mdc ?? '').toUpperCase() === mdc;
    }
    if (entityType === 'RDRG') {
      const parent = this.recordMaps.ADRG.get(normalizeEntityId(record.adrg, 'ADRG'));
      return Boolean(parent && String(parent.mdc ?? '').toUpperCase() === mdc);
    }
    if (entityType === 'TABLE' || entityType === 'CODE') {
      return (record.related_adrgs ?? []).some((code) => this.adrgMdc(code) === mdc);
    }
    return false;
  }

  recordMatchesClassification(entityType, record, classification) {
    const mapping = { 전문: 'A', 일반: 'B', 단순: 'C' };
    const accepted = new Set([classification, mapping[classification] ?? classification]);
    if (entityType === 'AADRG') {
      return accepted.has(String(record.classification_code ?? '').toUpperCase());
    }
    if (entityType === 'ADRG') {
      return (record.abc_classification_codes ?? [])
        .map((value) => String(value).toUpperCase())
        .some((value) => accepted.has(value));
    }
    let aadrgs = [];
    if (entityType === 'RDRG') {
      aadrgs = [String(record.aadrg ?? '')];
    } else if (entityType === 'TABLE') {
      aadrgs = (record.related_adrgs ?? []).flatMap((adrg) => this.adrgAadrgs(String(adrg)));
    } else if (entityType === 'CODE') {
      aadrgs = (record.related_aadrgs ?? []).map(String);
    }
    return aadrgs.some((code) => {
      const row = this.recordMaps.AADRG.get(normalizeEntityId(code, 'AADRG')) ?? {};
      return accepted.has(String(row.classification_code ?? '').toUpperCase());
    });
  }

  adrgMdc(adrg) {
    const row = this.recordMaps.ADRG.get(normalizeEntityId(adrg, 'ADRG'));
    return row ? String(row.mdc ?? '').toUpperCase() : '';
  }

  adrgAadrgs(adrg) {
    const row = this.recordMaps.ADRG.get(normalizeEntityId(adrg, 'ADRG'));
    return row ? (row.aadrg_codes ?? []).map(String) : [];
  }

  makeSearchResult(entityType, entityId, score, matchType, matchedFields) {
    const record = this.recordMaps[entityType].get(normalizeEntityId(entityId, entityType));
    const [title, subtitle] = this.titleSubtitle(entityType, record);
    return {
      entity_type: entityType,
      entity_id: entityId,
      title,
      subtitle,
      score,
      match_type: matchType,
      matched_fields: matchedFields,
      summary: this.summaryPayload(entityType, record),
    };
  }

  summaryPayload(entityType, row) {
    if (entityType === 'CODE') {
      return {
        names: clone(row.names ?? []),
        roles: clone(row.roles ?? []),
        logical_table_count: (row.logical_table_ids ?? []).length,
        source_adrgs: clone(row.source_adrgs ?? []),
        condition_adrgs: clone(row.condition_adrgs ?? []),
        related_adrgs: clone(row.related_adrgs ?? []),
        source_adrg_families: clone(row.source_adrg_families ?? []),
        related_aadrg_count: (row.related_aadrgs ?? []).length,
      };
    }
    if (entityType === 'ADRG') {
      return {
        mdc: row.mdc ?? null,
        aadrg_count: row.aadrg_count ?? null,
        abc_status: row.abc_status ?? null,
        abc_display_labels: clone(row.abc_display_labels ?? []),
        source_table_count: (row.source_logical_table_ids ?? []).length,
        condition_table_count: (row.condition_logical_table_ids ?? []).length,
        related_table_count: (row.logical_table_ids ?? []).length,
        condition_ast_id: row.condition_ast_id ?? null,
      };
    }
    if (entityType === 'AADRG') {
      return {
        adrg: row.adrg ?? null,
        mdc: row.mdc ?? null,
        classification_code: row.classification_code ?? null,
        classification_display_label: row.classification_display_label || '분류 미부여',
        abc_status: row.abc_status ?? null,
        rdrg_count: (row.rdrg_codes ?? []).length,
      };
    }
    if (entityType === 'RDRG') {
      return {
        adrg: row.adrg ?? null,
        aadrg: row.aadrg ?? null,
        severity_name: row.severity_name ?? null,
      };
    }
    return {
      logical_table_type: row.logical_table_type ?? null,
      logical_table_scope: row.logical_table_scope ?? null,
      code_count: row.code_count ?? null,
      source_adrgs: clone(row.source_adrgs ?? []),
      condition_adrgs: clone(row.condition_adrgs ?? []),
      related_adrgs: clone(row.related_adrgs ?? []),
      source_adrg_families: clone(row.source_adrg_families ?? []),
      condition_ast_count: (row.condition_ast_ids ?? []).length,
    };
  }

  getDetail(entityType, entityId) {
    const typeName = String(entityType ?? '').toUpperCase();
    if (!ENTITY_TYPES.includes(typeName)) {
      throw new KdrgSearchError(`지원하지 않는 상세조회 유형입니다: ${entityType}`);
    }
    const normalizedId = normalizeEntityId(entityId, typeName);
    const row = this.recordMaps[typeName].get(normalizedId);
    if (!row) {
      throw new KdrgSearchError(`상세조회 대상을 찾지 못했습니다: ${typeName}:${entityId}`);
    }
    let detail;
    if (typeName === 'CODE') detail = this.codeDetail(row);
    else if (typeName === 'ADRG') detail = this.adrgDetail(row);
    else if (typeName === 'AADRG') detail = this.aadrgDetail(row);
    else if (typeName === 'RDRG') detail = this.rdrgDetail(row);
    else detail = this.tableDetail(row);
    return {
      schema_version: RESPONSE_SCHEMA_VERSION,
      entity_type: typeName,
      entity_id: String(row[this.idFields[typeName]] ?? ''),
      detail,
    };
  }

  semanticContexts(adrg, tableId) {
    return this.semanticContextIndex.get(`${adrg}\u0000${tableId}`) ?? [];
  }

  codeDetail(row) {
    const tableDetails = [];
    for (const tableId of row.logical_table_ids ?? []) {
      const table = this.recordMaps.TABLE.get(normalizeEntityId(tableId, 'TABLE'));
      if (!table) continue;
      const contexts = [];
      for (const adrg of table.condition_adrgs ?? []) {
        contexts.push(...this.semanticContexts(String(adrg), String(tableId)).map((item) => ({
          adrg,
          ...clone(item),
        })));
      }
      tableDetails.push({
        logical_table_id: tableId,
        display_name: table.display_name ?? null,
        logical_table_type: table.logical_table_type ?? null,
        source_adrgs: clone(table.source_adrgs ?? []),
        condition_adrgs: clone(table.condition_adrgs ?? []),
        related_adrgs: clone(table.related_adrgs ?? []),
        source_adrg_families: clone(table.source_adrg_families ?? []),
        runtime_contexts: contexts,
        source_refs: clone(table.source_refs ?? []),
      });
    }
    const adrgSummaries = (row.related_adrgs ?? [])
      .filter((adrg) => this.recordMaps.ADRG.has(normalizeEntityId(adrg, 'ADRG')))
      .map((adrg) => this.summaryEntity('ADRG', adrg));
    const aadrgSummaries = (row.related_aadrgs ?? [])
      .filter((aadrg) => this.recordMaps.AADRG.has(normalizeEntityId(aadrg, 'AADRG')))
      .map((aadrg) => this.summaryEntity('AADRG', aadrg));
    return {
      ...clone(row),
      relation_sections: {
        physical_source: {
          adrgs: clone(row.source_adrgs ?? []),
          aadrgs: clone(row.source_aadrgs ?? []),
          family_refs: clone(row.source_adrg_families ?? []),
          display_label: '원문 TABLE 정의 위치',
        },
        condition_usage: {
          adrgs: clone(row.condition_adrgs ?? []),
          aadrgs: clone(row.condition_aadrgs ?? []),
          display_label: '조건 AST 실제 사용 관계',
        },
        runtime_related: {
          adrgs: clone(row.related_adrgs ?? []),
          aadrgs: clone(row.related_aadrgs ?? []),
          display_label: '검색용 통합 관계',
        },
      },
      logical_tables: tableDetails,
      related_adrg_summaries: adrgSummaries,
      related_aadrg_summaries: aadrgSummaries,
    };
  }

  adrgDetail(row) {
    const aadrgs = (row.aadrg_codes ?? []).map((code) => this.summaryEntity('AADRG', code));
    const tables = (row.logical_table_ids ?? []).map((tableId) => this.summaryEntity('TABLE', tableId));
    let ast = null;
    const astId = String(row.condition_ast_id ?? '');
    if (astId) {
      const found = (this.data.condition_ast_records ?? []).find(
        (item) => String(item.condition_ast_id ?? '') === astId,
      );
      ast = found ? clone(found) : null;
    }
    return { ...clone(row), aadrg_records: aadrgs, logical_tables: tables, condition_ast: ast };
  }

  aadrgDetail(row) {
    return {
      ...clone(row),
      parent_adrg: this.summaryEntity('ADRG', String(row.adrg ?? '')),
      rdrg_records: (row.rdrg_codes ?? []).map((code) => this.summaryEntity('RDRG', code)),
    };
  }

  rdrgDetail(row) {
    return {
      ...clone(row),
      parent_aadrg: this.summaryEntity('AADRG', String(row.aadrg ?? '')),
      parent_adrg: this.summaryEntity('ADRG', String(row.adrg ?? '')),
    };
  }

  tableDetail(row) {
    const contexts = [];
    const tableId = String(row.logical_table_id ?? '');
    for (const adrg of row.condition_adrgs ?? []) {
      contexts.push(...this.semanticContexts(String(adrg), tableId).map((item) => ({
        adrg,
        ...clone(item),
      })));
    }
    return {
      ...clone(row),
      runtime_contexts: contexts,
      source_adrg_summaries: (row.source_adrgs ?? []).map((code) => this.summaryEntity('ADRG', code)),
      condition_adrg_summaries: (row.condition_adrgs ?? []).map((code) => this.summaryEntity('ADRG', code)),
      related_adrg_summaries: (row.related_adrgs ?? []).map((code) => this.summaryEntity('ADRG', code)),
      code_records: (row.codes ?? []).map((code) => this.summaryEntity('CODE', code)),
    };
  }

  summaryEntity(entityType, entityId) {
    const row = this.recordMaps[entityType].get(normalizeEntityId(entityId, entityType));
    if (!row) return { entity_type: entityType, entity_id: entityId, missing: true };
    const [title, subtitle] = this.titleSubtitle(entityType, row);
    return {
      entity_type: entityType,
      entity_id: String(row[this.idFields[entityType]] ?? ''),
      title,
      subtitle,
      summary: this.summaryPayload(entityType, row),
    };
  }

  debugSearchDocumentFingerprint() {
    const rows = [...this.searchDocuments.entries()]
      .sort(([left], [right]) => compareAscii(left, right))
      .map(([key, document]) => ({
        key,
        entity_type: document.entity_type,
        entity_id: document.entity_id,
        title: document.title,
        subtitle: document.subtitle,
        fields: document.fields,
        haystack: document.haystack,
        tokens: [...document.tokens].sort(compareAscii),
      }));
    return { count: rows.length, sha256: sha256Canonical(rows) };
  }

  debugSemanticContextFingerprint() {
    const rows = [...this.semanticContextIndex.entries()]
      .map(([key, contexts]) => {
        const [adrg, tableId] = key.split('\u0000');
        return { adrg, table_id: tableId, contexts: clone(contexts) };
      })
      .sort((left, right) => compareAscii(left.adrg, right.adrg) || compareAscii(left.table_id, right.table_id));
    return {
      key_count: rows.length,
      occurrence_count: rows.reduce((total, row) => total + row.contexts.length, 0),
      sha256: sha256Canonical(rows),
    };
  }

  debugExactIdAudit() {
    const failures = [];
    for (const [key, document] of this.searchDocuments.entries()) {
      const match = this.matchDocument(document, document.entity_id, queryTokens(document.entity_id));
      if (!match || match[0] !== 1000 || match[1] !== 'EXACT_ID') failures.push(key);
    }
    return { checked: this.searchDocuments.size, failures };
  }
}

module.exports = Object.freeze({
  KdrgSearchError,
  KdrgSearchService,
  SERVICE_SCHEMA_VERSION,
  RESPONSE_SCHEMA_VERSION,
  RELATION_RESPONSE_SCHEMA_VERSION,
  SUPPORTED_DATA_SCHEMA,
  ENTITY_TYPES,
  normalizeEntityId,
  normalizeQuery,
  queryTokens,
  canonicalJson,
  sha256Canonical,
});
