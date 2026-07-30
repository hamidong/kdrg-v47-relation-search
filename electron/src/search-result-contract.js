'use strict';

const { normalizeSpace, normalizeEntityId } = require('./search-normalizer');

const ENTITY_TYPES = Object.freeze(['CODE', 'ADRG', 'AADRG', 'RDRG', 'TABLE']);
const ENTITY_TYPE_SET = new Set(ENTITY_TYPES);
const RELATION_OPERATORS = Object.freeze(['AND', 'OR']);
const RELATION_CODE_TYPES = Object.freeze([
  'AUTO',
  'DIAGNOSIS',
  'SECONDARY_DIAGNOSIS',
  'PROCEDURE',
  'TEST',
  'ADD_ON',
  'OTHER',
]);
const RELATION_CODE_TYPE_SET = new Set(RELATION_CODE_TYPES);

class SearchContractError extends Error {
  constructor(message) {
    super(message);
    this.name = 'SearchContractError';
  }
}

function normalizeEntityTypes(value) {
  if (value == null || value === 'ALL') {
    return 'ALL';
  }
  const values = Array.isArray(value) ? value : [value];
  if (!values.length) {
    throw new SearchContractError('검색 유형이 비어 있습니다.');
  }
  const output = [];
  for (const item of values) {
    const normalized = String(item ?? '').toUpperCase();
    if (normalized === 'ALL') {
      return 'ALL';
    }
    if (!ENTITY_TYPE_SET.has(normalized)) {
      throw new SearchContractError(`지원하지 않는 검색 유형입니다: ${item}`);
    }
    if (!output.includes(normalized)) {
      output.push(normalized);
    }
  }
  return output;
}

function boundedInteger(value, name, defaultValue, minimum, maximum) {
  if (value == null || value === '') {
    return defaultValue;
  }
  const number = Number(value);
  if (!Number.isInteger(number) || number < minimum || number > maximum) {
    throw new SearchContractError(`${name}은 ${minimum}~${maximum} 범위의 정수여야 합니다.`);
  }
  return number;
}

function normalizeSharedFilters(payload) {
  const mdc = normalizeSpace(payload.mdc).toUpperCase();
  const classification = normalizeSpace(payload.classification).toUpperCase();
  if (mdc.length > 20 || classification.length > 20) {
    throw new SearchContractError('필터 값이 허용 길이를 초과했습니다.');
  }
  return {
    mdc: mdc || null,
    classification: classification || null,
  };
}

function normalizeSearchRequest(payload) {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    throw new SearchContractError('검색 요청 형식이 올바르지 않습니다.');
  }
  const query = normalizeSpace(payload.query);
  if (!query) {
    throw new SearchContractError('검색어를 입력해야 합니다.');
  }
  if (query.length > 200) {
    throw new SearchContractError('검색어는 200자 이하여야 합니다.');
  }
  const filters = normalizeSharedFilters(payload);
  return Object.freeze({
    query,
    entityType: normalizeEntityTypes(payload.entityType),
    limit: boundedInteger(payload.limit, 'limit', 50, 1, 500),
    offset: boundedInteger(payload.offset, 'offset', 0, 0, 1000000),
    ...filters,
  });
}

function normalizeRelationCondition(value, index) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new SearchContractError(`관계검색 ${index + 1}번 조건 형식이 올바르지 않습니다.`);
  }
  const code = normalizeSpace(value.code);
  if (!code) {
    throw new SearchContractError(`관계검색 ${index + 1}번 코드를 입력해야 합니다.`);
  }
  if (code.length > 100) {
    throw new SearchContractError(`관계검색 ${index + 1}번 코드는 100자 이하여야 합니다.`);
  }
  const codeType = String(value.codeType ?? 'AUTO').toUpperCase();
  if (!RELATION_CODE_TYPE_SET.has(codeType)) {
    throw new SearchContractError(`지원하지 않는 관계검색 코드 유형입니다: ${value.codeType ?? ''}`);
  }
  return Object.freeze({
    code,
    normalizedCode: normalizeEntityId(code, 'CODE'),
    codeType,
  });
}

function normalizeRelationRequest(payload) {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    throw new SearchContractError('복수 코드 관계검색 요청 형식이 올바르지 않습니다.');
  }
  if (!Array.isArray(payload.conditions)) {
    throw new SearchContractError('복수 코드 관계검색 조건 배열이 없습니다.');
  }
  if (payload.conditions.length < 2 || payload.conditions.length > 6) {
    throw new SearchContractError('복수 코드 관계검색은 2~6개 코드를 입력해야 합니다.');
  }
  const conditions = payload.conditions.map(normalizeRelationCondition);
  const duplicateCodes = conditions
    .map((item) => item.normalizedCode)
    .filter((code, index, rows) => code && rows.indexOf(code) !== index);
  if (duplicateCodes.length) {
    throw new SearchContractError(`같은 코드를 중복 입력할 수 없습니다: ${duplicateCodes[0]}`);
  }
  const operator = String(payload.operator ?? 'AND').toUpperCase();
  if (!RELATION_OPERATORS.includes(operator)) {
    throw new SearchContractError(`지원하지 않는 조건 관계입니다: ${payload.operator ?? ''}`);
  }
  return Object.freeze({
    operator,
    conditions: Object.freeze(conditions),
    ...normalizeSharedFilters(payload),
  });
}

function normalizeDetailRequest(payload) {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    throw new SearchContractError('상세조회 요청 형식이 올바르지 않습니다.');
  }
  const entityType = String(payload.entityType ?? '').toUpperCase();
  const entityId = normalizeSpace(payload.entityId);
  if (!ENTITY_TYPE_SET.has(entityType)) {
    throw new SearchContractError(`지원하지 않는 상세조회 유형입니다: ${payload.entityType ?? ''}`);
  }
  if (!entityId || entityId.length > 100) {
    throw new SearchContractError('상세조회 ID는 1~100자여야 합니다.');
  }
  return Object.freeze({ entityType, entityId });
}

module.exports = Object.freeze({
  ENTITY_TYPES,
  RELATION_OPERATORS,
  RELATION_CODE_TYPES,
  SearchContractError,
  normalizeSearchRequest,
  normalizeRelationRequest,
  normalizeDetailRequest,
});
