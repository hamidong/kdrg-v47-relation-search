'use strict';

(function attachKdrgUi(root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) {
    module.exports = api;
  }
  if (root && typeof root === 'object') {
    root.KdrgUi = api;
  }
})(typeof globalThis === 'object' ? globalThis : this, function createKdrgUi() {
  const ENTITY_LABELS = Object.freeze({
    CODE: '코드',
    ADRG: 'ADRG',
    AADRG: 'AADRG',
    RDRG: 'RDRG',
    TABLE: 'TABLE',
  });

  const ROLE_LABELS = Object.freeze({
    diagnosis: '상병코드',
    principal_diagnosis: '주진단코드',
    procedure: '수술·처치코드',
    add_on_code: '부가코드',
    optional_semantic: '선택 조건 TABLE',
    other_semantic: '기타 조건 TABLE',
    unknown: '코드(유형 미확정)',
  });

  function text(value, fallback = '-') {
    if (value === null || value === undefined) return fallback;
    const output = String(value).trim();
    return output || fallback;
  }

  function formatNumber(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) return '-';
    return number.toLocaleString('ko-KR');
  }

  function uniqueStrings(values) {
    const output = [];
    const seen = new Set();
    for (const value of Array.isArray(values) ? values : []) {
      const normalized = String(value ?? '').trim();
      if (!normalized || seen.has(normalized)) continue;
      seen.add(normalized);
      output.push(normalized);
    }
    return output;
  }

  function entityLabel(entityType) {
    return ENTITY_LABELS[String(entityType ?? '').toUpperCase()] ?? text(entityType, '항목');
  }

  function roleLabel(value) {
    const key = String(value ?? '').toLowerCase();
    return ROLE_LABELS[key] ?? text(value, '코드(유형 미확정)');
  }

  function classificationLabel(code, displayLabel) {
    if (displayLabel) return String(displayLabel);
    const mapping = {
      A: '질병군 분류(전문)',
      B: '질병군 분류(일반)',
      C: '질병군 분류(단순)',
    };
    return mapping[String(code ?? '').toUpperCase()] ?? '분류 미부여';
  }

  function summarizeList(values, limit = 8) {
    const items = uniqueStrings(values);
    if (!items.length) return '-';
    if (items.length <= limit) return items.join(', ');
    return `${items.slice(0, limit).join(', ')} 외 ${formatNumber(items.length - limit)}개`;
  }

  function typeCountText(typeCounts) {
    const ordered = ['CODE', 'ADRG', 'AADRG', 'RDRG', 'TABLE'];
    return ordered
      .filter((key) => Number(typeCounts?.[key] ?? 0) > 0)
      .map((key) => `${entityLabel(key)} ${formatNumber(typeCounts[key])}건`)
      .join(' · ');
  }

  function resultSummaryChips(result) {
    const summary = result?.summary ?? {};
    const type = String(result?.entity_type ?? '').toUpperCase();
    if (type === 'ADRG') {
      return uniqueStrings([
        summary.mdc ? `MDC ${summary.mdc}` : '',
        ...(summary.abc_display_labels ?? []),
        `AADRG ${formatNumber(summary.aadrg_count ?? 0)}개`,
      ]);
    }
    if (type === 'AADRG') {
      return uniqueStrings([
        summary.adrg ? `ADRG ${summary.adrg}` : '',
        classificationLabel(summary.classification_code, summary.classification_display_label),
        `RDRG ${formatNumber(summary.rdrg_count ?? 0)}개`,
      ]);
    }
    if (type === 'RDRG') {
      return uniqueStrings([
        summary.aadrg ? `AADRG ${summary.aadrg}` : '',
        summary.severity_name ? `중증도 ${summary.severity_name}` : '',
      ]);
    }
    if (type === 'TABLE') {
      return uniqueStrings([
        roleLabel(summary.logical_table_type || summary.logical_table_scope),
        `코드 ${formatNumber(summary.code_count ?? 0)}개`,
        `관련 ADRG ${formatNumber((summary.related_adrgs ?? []).length)}개`,
      ]);
    }
    return uniqueStrings([
      ...(summary.roles ?? []).map(roleLabel),
      `TABLE ${formatNumber(summary.logical_table_count ?? 0)}개`,
      `관련 ADRG ${formatNumber((summary.related_adrgs ?? []).length)}개`,
    ]);
  }

  function cloneGroup(group) {
    return {
      includes: [...group.includes],
      excludes: [...group.excludes],
      requirements: [...group.requirements],
    };
  }

  function mergeGroups(left, right) {
    return {
      includes: [...left.includes, ...right.includes],
      excludes: [...left.excludes, ...right.excludes],
      requirements: [...left.requirements, ...right.requirements],
    };
  }

  function combineGroupSets(leftGroups, rightGroups) {
    const left = leftGroups.length ? leftGroups : [{ includes: [], excludes: [], requirements: [] }];
    const right = rightGroups.length ? rightGroups : [{ includes: [], excludes: [], requirements: [] }];
    const output = [];
    for (const leftGroup of left) {
      for (const rightGroup of right) {
        output.push(mergeGroups(leftGroup, rightGroup));
      }
    }
    return output;
  }

  function tableLeaf(node, polarity) {
    const tableIds = uniqueStrings(node?.logical_table_ids ?? []);
    const leaf = {
      table_ids: tableIds,
      display_text: text(node?.display_text || node?.source_fragment, tableIds.join(', ')),
      role: roleLabel(node?.table_role),
      source_fragment: text(node?.source_fragment, ''),
      node_id: text(node?.node_id, ''),
    };
    const group = { includes: [], excludes: [], requirements: [] };
    if (polarity >= 0) group.includes.push(leaf);
    else group.excludes.push(leaf);
    return [group];
  }

  function requirementLeaf(node, polarity) {
    const prefix = polarity >= 0 ? '' : '제외 조건 · ';
    return [{
      includes: [],
      excludes: [],
      requirements: [{
        text: `${prefix}${text(node?.display_text || node?.source_fragment, '조건 원문 확인')}`,
        semantic_type: text(node?.semantic_type, ''),
        structured_condition: node?.structured_condition ?? null,
        node_id: text(node?.node_id, ''),
        polarity: polarity >= 0 ? 'include' : 'exclude',
      }],
    }];
  }

  function normalizeGroups(groups) {
    return groups.map((group) => {
      const normalized = cloneGroup(group);
      const dedupeBy = (values, keyBuilder) => {
        const output = [];
        const seen = new Set();
        for (const value of values) {
          const key = keyBuilder(value);
          if (seen.has(key)) continue;
          seen.add(key);
          output.push(value);
        }
        return output;
      };
      normalized.includes = dedupeBy(
        normalized.includes,
        (value) => `I:${value.table_ids.join('|')}:${value.node_id}`,
      );
      normalized.excludes = dedupeBy(
        normalized.excludes,
        (value) => `E:${value.table_ids.join('|')}:${value.node_id}`,
      );
      normalized.requirements = dedupeBy(
        normalized.requirements,
        (value) => `R:${value.text}:${value.node_id}`,
      );
      return normalized;
    });
  }

  function buildConditionGroups(ast) {
    if (!ast || !Array.isArray(ast.nodes) || !ast.root_node_id) return [];
    const nodeMap = new Map(ast.nodes.map((node) => [String(node.node_id), node]));

    function walk(nodeId, polarity = 1) {
      const node = nodeMap.get(String(nodeId));
      if (!node) return [];
      const type = String(node.node_type ?? '').toUpperCase();
      const children = Array.isArray(node.child_node_ids) ? node.child_node_ids : [];

      if (type === 'TABLE_REF') return tableLeaf(node, polarity);
      if (type === 'TEXT_CONDITION') return requirementLeaf(node, polarity);
      if (type === 'NOT') {
        return children.length ? walk(children[0], -polarity) : requirementLeaf(node, polarity);
      }
      if (type === 'EXCLUSION') {
        if (children.length < 2) return requirementLeaf(node, polarity);
        if (polarity >= 0) {
          return combineGroupSets(walk(children[0], 1), walk(children[1], -1));
        }
        return [...walk(children[0], -1), ...walk(children[1], 1)];
      }
      if (type === 'AND') {
        if (polarity < 0) {
          return children.flatMap((childId) => walk(childId, -1));
        }
        return children.reduce(
          (groups, childId) => combineGroupSets(groups, walk(childId, 1)),
          [{ includes: [], excludes: [], requirements: [] }],
        );
      }
      if (type === 'OR') {
        if (polarity < 0) {
          return children.reduce(
            (groups, childId) => combineGroupSets(groups, walk(childId, -1)),
            [{ includes: [], excludes: [], requirements: [] }],
          );
        }
        return children.flatMap((childId) => walk(childId, 1));
      }
      if (children.length) {
        return children.reduce(
          (groups, childId) => combineGroupSets(groups, walk(childId, polarity)),
          [{ includes: [], excludes: [], requirements: [] }],
        );
      }
      return requirementLeaf(node, polarity);
    }

    return normalizeGroups(walk(ast.root_node_id, 1));
  }

  function tableSummaryMap(detail) {
    return new Map(
      (detail?.logical_tables ?? []).map((item) => [String(item.entity_id), item]),
    );
  }

  function userConditionCoverage(detail) {
    const status = text(detail?.user_condition_status);
    const conditionText = text(detail?.user_condition_text);
    const tableIds = uniqueStrings(detail?.user_condition_table_ids ?? []);
    const tableRefs = Array.isArray(detail?.user_condition_table_refs)
      ? detail.user_condition_table_refs
      : [];
    const summaries = {
      RESOLVED_AST: `분류 조건 TABLE ${formatNumber(tableIds.length)}개 연결`,
      RESOLVED_SOURCE_LABELS: `분류 조건 TABLE ${formatNumber(tableIds.length)}개 연결`,
      TEXT_ONLY: '분류 조건 문구만 확인됨',
      UNRESOLVED_TABLE_LINK: '분류 조건은 확인됐으나 TABLE 연결 검토 필요',
      NO_EXPLICIT_CONDITION: '별도의 명시적 분류 조건이 확인되지 않음',
    };
    return {
      status,
      text: conditionText,
      table_ids: tableIds,
      table_refs: tableRefs,
      table_count: tableIds.length,
      has_text: Boolean(conditionText),
      has_tables: tableIds.length > 0,
      needs_review: status === 'UNRESOLVED_TABLE_LINK',
      summary: summaries[status] || '분류 조건 상태 미확인',
    };
  }

  return Object.freeze({
    ENTITY_LABELS,
    ROLE_LABELS,
    text,
    formatNumber,
    uniqueStrings,
    entityLabel,
    roleLabel,
    classificationLabel,
    summarizeList,
    typeCountText,
    resultSummaryChips,
    buildConditionGroups,
    tableSummaryMap,
    userConditionCoverage,
  });
});
