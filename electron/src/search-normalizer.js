'use strict';

const TOKEN_RE = /[0-9A-Za-z가-힣_]+/g;

function normalizeSpace(value) {
  return String(value ?? '').replace(/\s+/g, ' ').trim();
}

function normalizeEntityId(value, entityType = null) {
  const text = normalizeSpace(value).toUpperCase();
  if (entityType === 'TABLE' || text.startsWith('LT_')) {
    return text.replace(/[^A-Z0-9_]/g, '');
  }
  return text.replace(/[^A-Z0-9]/g, '');
}

function normalizeQuery(value) {
  return normalizeSpace(value).toLowerCase();
}

function queryTokens(value) {
  const input = normalizeSpace(value);
  const matches = input.match(TOKEN_RE) ?? [];
  const output = [];
  const seen = new Set();
  for (const token of matches) {
    const normalized = token.toLowerCase();
    if (normalized && !seen.has(normalized)) {
      seen.add(normalized);
      output.push(normalized);
    }
  }
  return output;
}

function uniqueStrings(values) {
  const output = [];
  const seen = new Set();
  for (const value of values ?? []) {
    const text = String(value ?? '');
    if (text && !seen.has(text)) {
      seen.add(text);
      output.push(text);
    }
  }
  return output;
}

module.exports = Object.freeze({
  normalizeSpace,
  normalizeEntityId,
  normalizeQuery,
  queryTokens,
  uniqueStrings,
});
