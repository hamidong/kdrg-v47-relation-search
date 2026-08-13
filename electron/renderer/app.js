'use strict';

const Ui = window.KdrgUi;

const state = {
  snapshot: null,
  serviceStatus: null,
  response: null,
  request: null,
  selectedKey: null,
  searchSequence: 0,
  detailSequence: 0,
  relationSequence: 0,
  relationResponse: null,
  activeMode: 'search',
};

const TYPE_BADGE_CLASS = Object.freeze({
  CODE: 'badge-code',
  ADRG: 'badge-adrg',
  AADRG: 'badge-aadrg',
  RDRG: 'badge-rdrg',
  TABLE: 'badge-table',
});

// Stage 56: 일반 사용자 화면에서는 개발·검증 메타데이터를 숨깁니다.
// 개발 시 이 상수를 true로 바꾸면 조건 상태와 원문 근거를 다시 확인할 수 있습니다.
const SHOW_DEVELOPER_METADATA = false;

const CLASSIFICATION_BADGE_META = Object.freeze({
  A: Object.freeze({
    label: '전문',
    className: 'classification-a',
  }),
  B: Object.freeze({
    label: '일반',
    className: 'classification-b',
  }),
  C: Object.freeze({
    label: '단순',
    className: 'classification-c',
  }),
});

function byId(id) {
  return document.getElementById(id);
}

function create(tagName, className = '', textValue = null) {
  const element = document.createElement(tagName);
  if (className) element.className = className;
  if (textValue !== null && textValue !== undefined) {
    element.textContent = String(textValue);
  }
  return element;
}

function setText(id, value) {
  const element = byId(id);
  if (element) element.textContent = String(value);
}

function setStatus(kind, title, detail) {
  document.body.dataset.state = kind;
  setText('status-title', title);
  setText('status-detail', detail);
}

function setBusy(isBusy, label = '처리 중') {
  const submit = byId('search-submit');
  const reset = byId('search-reset');
  const input = byId('search-query');
  submit.disabled = isBusy;
  reset.disabled = isBusy;
  input.setAttribute('aria-busy', String(isBusy));
  submit.textContent = isBusy ? label : '검색';
  const relationSubmit = byId('relation-submit');
  if (relationSubmit) relationSubmit.disabled = isBusy;
}

function makeBadge(entityType) {
  const type = String(entityType ?? '').toUpperCase();
  const badge = create('span', `entity-badge ${TYPE_BADGE_CLASS[type] ?? ''}`, Ui.entityLabel(type));
  badge.dataset.entityType = type;
  return badge;
}

function makeChip(textValue, className = '') {
  return create('span', `chip ${className}`.trim(), textValue);
}
function classificationCode(value) {
  const raw = String(value ?? '').replace(/\s+/g, ' ').trim();
  const upper = raw.toUpperCase();
  if (CLASSIFICATION_BADGE_META[upper]) return upper;
  if (raw.includes('전문')) return 'A';
  if (raw.includes('일반')) return 'B';
  if (raw.includes('단순')) return 'C';
  const parenthesized = raw.match(/(?:^|\()([ABC])(?:\)|$)/i);
  return parenthesized ? parenthesized[1].toUpperCase() : '';
}
function classificationCodes(values) {
  const output = [];
  const seen = new Set();
  for (const value of Array.isArray(values) ? values : [values]) {
    const code = classificationCode(value);
    if (!code || seen.has(code)) continue;
    seen.add(code);
    output.push(code);
  }
  return output;
}
function makeClassificationBadge(value) {
  const code = classificationCode(value);
  const meta = CLASSIFICATION_BADGE_META[code];
  if (!meta) return null;
  const badge = create(
    'span',
    `classification-badge ${meta.className}`,
  );
  badge.dataset.classificationCode = code;
  badge.setAttribute(
    'aria-label',
    `질병군 분류 ${code} ${meta.label}`,
  );
  badge.append(
    create('strong', 'classification-code', code),
    create('span', 'classification-name', meta.label),
  );
  return badge;
}
function appendClassificationBadges(container, values) {
  const codes = classificationCodes(values);
  for (const code of codes) {
    const badge = makeClassificationBadge(code);
    if (badge) container.append(badge);
  }
  return codes.length;
}
function makeClassificationBadgeGroup(values, className = '') {
  const group = create(
    'span',
    `classification-badge-group ${className}`.trim(),
  );
  const count = appendClassificationBadges(
    group,
    values,
  );
  if (!count) {
    group.append(
      makeChip(
        Ui.summarizeList(
          Array.isArray(values) ? values : [values],
        ),
      ),
    );
  }
  return group;
}
function classificationSummaryText(values) {
  const codes = classificationCodes(values);
  if (!codes.length) {
    return Ui.summarizeList(
      Array.isArray(values) ? values : [values],
    );
  }
  return codes
    .map(
      (code) => (
        `${code} ${CLASSIFICATION_BADGE_META[code].label}`
      ),
    )
    .join(', ');
}
function appendResultSummaryMeta(container, result) {
  const summary = result?.summary ?? {};
  const type = String(
    result?.entity_type ?? '',
  ).toUpperCase();
  if (type === 'ADRG') {
    if (summary.mdc) {
      container.append(
        makeChip(`MDC ${summary.mdc}`),
      );
    }
    container.append(
      makeChip(
        `AADRG ${Ui.formatNumber(summary.aadrg_count ?? 0)}개`,
      ),
    );
    return;
  }
  for (
    const label
    of Ui.resultSummaryChips(result)
  ) {
    container.append(
      makeChip(label),
    );
  }
}

function makeEntityButton(summary, className = 'entity-link') {
  const button = create('button', className);
  button.type = 'button';
  button.dataset.entityType = String(summary?.entity_type ?? '');
  button.dataset.entityId = String(summary?.entity_id ?? '');
  button.append(makeBadge(summary?.entity_type));
  const copy = create('span', 'entity-link-copy');
  copy.append(
    create('strong', '', summary?.title || summary?.entity_id || '-'),
    create('small', '', summary?.subtitle || ''),
  );
  button.append(copy);
  return button;
}

function renderMetrics(snapshot) {
  setText('metric-adrg', Ui.formatNumber(snapshot.counts.adrg));
  setText('metric-aadrg', Ui.formatNumber(snapshot.counts.aadrg));
  setText('metric-rdrg', Ui.formatNumber(snapshot.counts.rdrg));
  setText('metric-table', Ui.formatNumber(snapshot.counts.tables));
  setText('metric-code', Ui.formatNumber(snapshot.counts.codes));
  setText('metric-condition', Ui.formatNumber(snapshot.counts.conditionTableOccurrences));
  setText('stage-badge', 'Relation Search');
  setText('data-version', snapshot.dataVersion);
  setText('data-overview-summary', `${Ui.formatNumber(snapshot.counts.codes)}개 코드`);
}

function renderTypeCounts(response) {
  const container = byId('type-counts');
  container.replaceChildren();
  const typeCounts = response?.type_counts ?? {};
  for (const type of ['CODE', 'ADRG']) {
    const count = Number(typeCounts[type] ?? 0);
    if (!count) continue;
    const chip = makeChip(`${Ui.entityLabel(type)} ${Ui.formatNumber(count)}`, 'type-count-chip');
    chip.dataset.entityType = type;
    container.append(chip);
  }
}

function resultAriaLabel(result) {
  return `${Ui.entityLabel(result.entity_type)} ${result.entity_id} ${result.title}`;
}

function renderResults(response) {
  const list = byId('result-list');
  list.replaceChildren();
  state.response = response;
  state.relationResponse = null;
  state.activeMode = 'search';

  setText('result-count', `${Ui.formatNumber(response.total_count)}건`);
  setText(
    'result-caption',
    response.total_count
      ? `${Ui.typeCountText(response.type_counts)} · 최대 ${Ui.formatNumber(response.limit)}건씩 표시`
      : '검색 결과가 없습니다.',
  );
  renderTypeCounts(response);

  if (!response.results.length) {
    const empty = create('div', 'empty-state compact');
    empty.append(
      create('strong', '', '일치하는 결과가 없습니다.'),
      create('p', '', '코드의 점 표기를 빼거나 검색 유형·MDC·질병군 분류 필터를 완화해 보세요.'),
    );
    list.append(empty);
  }

  for (const result of response.results) {
    const key = `${result.entity_type}:${result.entity_id}`;
    const button = create('button', 'result-card');
    button.type = 'button';
    button.dataset.entityType = result.entity_type;
    button.dataset.entityId = result.entity_id;
    button.dataset.resultKey = key;
    button.setAttribute('aria-label', resultAriaLabel(result));
    button.setAttribute('aria-pressed', String(state.selectedKey === key));

    const main = create('div', 'result-card-main');
    main.append(makeBadge(result.entity_type));
    main.append(create('strong', 'result-title', result.title));
    if (String(result.entity_type ?? '').toUpperCase() === 'ADRG') {
      const classification = create(
        'span',
        'classification-badge-group result-card-classification',
      );
      const classificationCount = appendClassificationBadges(
        classification,
        result.summary?.abc_display_labels ?? [],
      );
      if (classificationCount) main.append(classification);
    }
    const subtitle = create('p', 'result-subtitle', result.subtitle);
    const chips = create('div', 'chip-row result-meta-row');
    appendResultSummaryMeta(chips, result);

    button.append(main);
    if (result.subtitle) button.append(subtitle);
    if (chips.childElementCount) button.append(chips);
    list.append(button);
  }

  const previous = byId('page-previous');
  const next = byId('page-next');
  previous.disabled = response.offset <= 0;
  next.disabled = !response.has_more;
  const first = response.total_count ? response.offset + 1 : 0;
  const last = response.offset + response.results.length;
  setText('page-label', `${Ui.formatNumber(first)}–${Ui.formatNumber(last)} / ${Ui.formatNumber(response.total_count)}`);
}

function relationLevelDescription(level) {
  if (level === 'strict') {
    return '입력 코드가 하나 이상의 동일한 조건 선택지 안에서 모두 연결됩니다. 남은 TABLE과 추가 조건은 별도로 확인해야 합니다.';
  }
  if (level === 'split') {
    return '모든 입력 코드가 같은 ADRG에 연결되지만 서로 다른 OR 조건 선택지에 나뉘어 있습니다. 하나의 조합으로 해석하면 안 됩니다.';
  }
  return 'OR 검색에서 입력 코드 중 일부만 이 ADRG의 조건식에 연결됩니다.';
}

function renderRelationCounts(response) {
  const container = byId('type-counts');
  container.replaceChildren();
  const labels = { strict: '같은 선택지', split: '다른 선택지', partial: '일부 연결' };
  for (const level of ['strict', 'split', 'partial']) {
    const count = Number(response?.level_counts?.[level] ?? 0);
    if (count) container.append(makeChip(`${labels[level]} ${Ui.formatNumber(count)}`, `relation-${level}-chip`));
  }
}

function renderRelationResults(response) {
  const list = byId('result-list');
  list.replaceChildren();
  state.response = null;
  state.relationResponse = response;
  state.activeMode = 'relation';
  setText('result-count', `${Ui.formatNumber(response.total_count)}건`);
  setText(
    'result-caption',
    response.total_count
      ? `${response.operator} 관계검색 · 같은 ADRG·조건 선택지 기준`
      : '입력 코드가 연결되는 ADRG 조건식을 찾지 못했습니다.',
  );
  renderRelationCounts(response);
  if (!response.results.length) {
    const empty = create('div', 'empty-state compact');
    empty.append(
      create('strong', '', '공통 관계를 찾지 못했습니다.'),
      create('p', '', '코드 유형·MDC·질병군 분류를 확인하거나 OR 관계로 범위를 넓혀 보세요.'),
    );
    list.append(empty);
  }
  response.results.forEach((result, index) => {
    const key = `RELATION:${result.entity_id}:${index}`;
    const button = create('button', `result-card relation-result-card relation-${result.relation_level}`);
    button.type = 'button';
    button.dataset.relationIndex = String(index);
    button.dataset.resultKey = key;
    button.setAttribute('aria-label', `관계검색 ADRG ${result.entity_id} ${result.relation_level_label}`);
    button.setAttribute('aria-pressed', String(state.selectedKey === key));
    const main = create('div', 'result-card-main');
    main.append(makeBadge('ADRG'));
    main.append(create('strong', 'result-title', result.title));
    main.append(makeChip(result.relation_level_label, `relation-${result.relation_level}-chip result-match-chip`));
    const chips = create('div', 'chip-row result-meta-row');
    chips.append(
      makeChip(`${result.matched_count}/${result.total_count} 코드 연결`),
      makeChip(result.summary?.mdc ? `MDC ${result.summary.mdc}` : 'MDC 미확인'),
    );
    appendClassificationBadges(
      chips,
      result.summary?.abc_display_labels ?? [],
    );
    button.append(main);
    if (result.subtitle) button.append(create('p', 'result-subtitle', result.subtitle));
    button.append(chips);
    list.append(button);
  });
  byId('page-previous').disabled = true;
  byId('page-next').disabled = true;
  setText('page-label', response.total_count ? `1–${Ui.formatNumber(response.total_count)} / ${Ui.formatNumber(response.total_count)}` : '0–0 / 0');
}

function relationMatchCard(match) {
  const card = create('article', 'relation-match-card');
  const head = create('div', 'relation-match-head');
  head.append(
    makeChip(match.code_type_label || match.code_type || '자동판별', 'role-chip'),
    create('strong', '', match.code),
  );
  card.append(head);
  if (!match.exact_code_found) {
    card.append(create('p', 'relation-warning', '통합 검색 데이터에서 정확히 일치하는 코드를 찾지 못했습니다.'));
    return card;
  }
  if (!(match.matched_table_ids ?? []).length) {
    card.append(create('p', 'muted', '이 ADRG의 포함 조건 TABLE과 연결되지 않습니다.'));
    return card;
  }
  const tables = create('div', 'table-stack compact-stack');
  for (const table of match.matched_tables ?? []) tables.append(tableCard(table));
  card.append(tables);
  return card;
}

function renderRelationDetail(candidate, response) {
  const panel = byId('detail-content');
  panel.replaceChildren();
  const header = create('div', 'detail-primary detail-hero relation-detail-primary');
  header.append(makeBadge('ADRG'));
  const copy = create('div');
  copy.append(
    create('h2', '', candidate.title),
    create('p', '', `${candidate.relation_level_label} · ${candidate.matched_count}/${candidate.total_count} 코드 연결`),
  );
  header.append(copy);
  const openAdrg = create('button', 'secondary-button relation-open-adrg', 'ADRG 전체 상세');
  openAdrg.type = 'button';
  openAdrg.dataset.entityType = 'ADRG';
  openAdrg.dataset.entityId = candidate.entity_id;
  header.append(openAdrg);
  panel.append(header);

  const notice = create('div', `relation-level-notice relation-${candidate.relation_level}`);
  notice.append(
    create('strong', '', candidate.relation_level_label),
    create('p', '', relationLevelDescription(candidate.relation_level)),
    create('small', '', response.disclaimer),
  );
  panel.append(notice);
  panel.append(makeMetaGrid([
    ['ADRG', candidate.entity_id],
    ['질병군명', candidate.title.replace(`${candidate.entity_id} · `, '')],
    ['MDC', candidate.summary?.mdc ? `MDC ${candidate.summary.mdc}` : '-'],
    [
      '질병군 분류',
      makeClassificationBadgeGroup(
        candidate.summary?.abc_display_labels ?? [],
      ),
    ],
    ['연결 코드', `${candidate.matched_count}/${candidate.total_count}`],
    ['근거 페이지', candidate.source_page ? `PDF p.${candidate.source_page}` : '-'],
  ], 'detail-overview-grid'));

  const matchesSection = makeSection('입력 코드별 연결 TABLE', '정확한 코드가 포함된 TABLE과 이 ADRG 조건식의 교집합입니다.', { open: true, count: candidate.code_matches.length });
  const matchStack = create('div', 'relation-match-stack');
  for (const match of candidate.code_matches) matchStack.append(relationMatchCard(match));
  matchesSection.append(matchStack);

  const groupsSection = makeSection('조건 선택지별 연결', '같은 조건 선택지인지, 서로 다른 OR 선택지인지 구분합니다.', { open: true, count: candidate.condition_groups.length });
  const groupStack = create('div', 'relation-group-stack');
  for (const group of candidate.condition_groups) {
    const groupCard = create('article', `relation-group-card ${group.all_inputs ? 'is-strict-group' : ''}`);
    const groupHead = create('div', 'relation-group-head');
    groupHead.append(
      create('strong', '', group.group_label),
      makeChip(group.all_inputs ? '모든 입력 코드' : `${group.hit_count}/${candidate.total_count} 코드`, group.all_inputs ? 'relation-strict-chip' : ''),
    );
    groupCard.append(groupHead);
    for (const match of group.matches) {
      const row = create('div', 'relation-group-match');
      row.append(create('strong', '', match.code), create('span', '', Ui.summarizeList(match.matched_table_ids)));
      groupCard.append(row);
    }
    if ((group.exclude_tables ?? []).length) {
      const exclusion = create('div', 'relation-group-exclusion');
      exclusion.append(create('strong', '', '제외 TABLE'));
      const tables = create('div', 'table-stack compact-stack');
      for (const table of group.exclude_tables) tables.append(tableCard(table, { exclusion: true }));
      exclusion.append(tables);
      groupCard.append(exclusion);
    }
    if ((group.requirements ?? []).length) {
      const requirement = create('p', 'relation-requirement', `추가 확인: ${group.requirements.join(' · ')}`);
      groupCard.append(requirement);
    }
    groupStack.append(groupCard);
  }
  if (!candidate.condition_groups.length) groupStack.append(create('p', 'muted', '표시할 조건 선택지 연결이 없습니다.'));
  groupsSection.append(groupStack);

  const aadrgSection = makeSection('파생 AADRG', '질병군 분류(전문/일반/단순)를 함께 표시합니다.', { open: false, count: candidate.aadrg_records.length });
  aadrgSection.append(makeSummaryList(candidate.aadrg_records));
  panel.append(matchesSection, groupsSection, aadrgSection);
  setText('detail-heading', '복수 코드 관계 상세');
  setText('detail-caption', `${response.operator} · ADRG ${candidate.entity_id}`);
  setDetailFoldActions(true);
}

function clearDetail(message = '검색 결과를 선택하면 상세 관계가 표시됩니다.') {
  const panel = byId('detail-content');
  panel.replaceChildren();
  const empty = create('div', 'empty-state');
  empty.append(
    create('div', 'empty-icon', 'KDRG'),
    create('strong', '', '상세 항목을 선택하세요.'),
    create('p', '', message),
  );
  panel.append(empty);
  setText('detail-heading', '상세 정보');
  setText('detail-caption', '검색 결과를 선택하세요.');
  setDetailFoldActions(false);
}

function makeSection(title, description = '', options = {}) {
  const section = create('details', 'detail-section');
  section.open = options.open === true;
  const header = create('summary', 'section-header');
  const titleWrap = create('div');
  const titleRow = create('div', 'section-title-row');
  titleRow.append(create('h3', '', title));
  if (Number.isFinite(Number(options.count))) {
    titleRow.append(makeChip(`${Ui.formatNumber(Number(options.count))}개`, 'section-count-chip'));
  }
  titleWrap.append(titleRow);
  if (description) titleWrap.append(create('p', '', description));
  header.append(titleWrap);
  section.append(header);
  return section;
}

function setDetailFoldActions(visible) {
  const actions = byId('detail-fold-actions');
  if (actions) actions.hidden = !visible;
}

function setAllDetailSections(open) {
  for (const section of document.querySelectorAll('#detail-content details.detail-section, #detail-content details.table-card')) {
    section.open = open;
  }
}

function makeMetaGrid(rows, className = '') {
  const grid = create('dl', `meta-grid ${className}`.trim());
  for (const [key, value] of rows) {
    const row = create('div');
    const term = create('dt', '', key);
    const description = create('dd');
    if (
      value
      && typeof value === 'object'
      && typeof value.nodeType === 'number'
    ) {
      description.append(value);
    } else {
      description.textContent = Ui.text(value);
    }
    row.append(term, description);
    grid.append(row);
  }
  return grid;
}

function makeSummaryList(items, emptyMessage = '표시할 항목이 없습니다.') {
  const container = create('div', 'entity-list');
  if (!Array.isArray(items) || !items.length) {
    container.append(create('p', 'muted', emptyMessage));
    return container;
  }
  for (const item of items) container.append(makeEntityButton(item));
  return container;
}

const INTERNAL_TABLE_ID_PATTERN = /^LT_[A-Z0-9_]+$/i;
const OFFICIAL_TABLE_LABEL_PATTERN = /(주진단명|기타진단명|시술명|수술명|처치명|검사명|부가코드(?:명)?)(?:\s*table\s*\d+)?/gi;

function normalizeOfficialTableLabel(value) {
  return String(value ?? '')
    .replace(/\s+/g, ' ')
    .replace(/table\s*(\d+)/i, 'table$1')
    .trim();
}

function extractOfficialTableLabels(...values) {
  const labels = [];
  const seen = new Set();
  for (const value of values.flat(Infinity)) {
    const text = String(value ?? '');
    OFFICIAL_TABLE_LABEL_PATTERN.lastIndex = 0;
    for (const match of text.matchAll(OFFICIAL_TABLE_LABEL_PATTERN)) {
      const label = normalizeOfficialTableLabel(match[0]);
      if (!label || seen.has(label)) continue;
      seen.add(label);
      labels.push(label);
    }
  }
  return labels;
}

function isInternalTableName(value, tableId = '') {
  const name = String(value ?? '').trim();
  if (!name) return true;
  return name === String(tableId ?? '').trim() || INTERNAL_TABLE_ID_PATTERN.test(name);
}

function tableLabelMapFromAst(ast) {
  const output = new Map();
  for (const node of ast?.nodes ?? []) {
    const tableIds = Ui.uniqueStrings(node.logical_table_ids ?? []);
    if (!tableIds.length) continue;
    const labels = extractOfficialTableLabels(
      node.source_fragment,
      node.display_text,
      node.source_raw_text,
    );
    if (labels.length === tableIds.length) {
      tableIds.forEach((tableId, index) => output.set(tableId, labels[index]));
    } else if (labels.length === 1) {
      tableIds.forEach((tableId) => output.set(tableId, labels[0]));
    }
  }
  return output;
}

function tableUserLabel(summary, options = {}) {
  const tableId = String(summary?.entity_id ?? summary?.logical_table_id ?? '');
  const explicitLabel = normalizeOfficialTableLabel(
    options.displayLabel ?? summary?.user_condition_ref?.display_label,
  );
  if (explicitLabel) return explicitLabel;
  const mapped = options.labelMap?.get(tableId);
  if (mapped) return mapped;
  const summaryData = summary?.summary ?? summary ?? {};
  const contextTexts = (summaryData.runtime_contexts ?? []).flatMap((context) => [
    context.source_fragment,
    context.requirement_label,
    context.display_label,
  ]);
  const labels = extractOfficialTableLabels(
    options.sourceText,
    summary?.title,
    summary?.subtitle,
    summaryData.display_name,
    contextTexts,
  );
  if (labels.length) return labels[0];
  const displayName = String(summaryData.display_name ?? summary?.title ?? '').trim();
  if (!isInternalTableName(displayName, tableId)) return displayName;
  return '원문 TABLE명 미수록';
}

function codeRecordText(record) {
  const code = String(record?.entity_id || record?.summary?.code || '-');
  const name = String(
    record?.summary?.names?.[0]
      || record?.subtitle
      || '코드명 원천 미수록',
  );
  return { code, name };
}
function renderInlineTableCodeList(detail) {
  const body = create('div', 'inline-table-code-list');
  const records = Array.isArray(detail?.code_records) ? detail.code_records : [];
  if (!records.length) {
    body.append(create('p', 'muted', 'TABLE 코드가 없습니다.'));
    return body;
  }

  const toolbar = create('div', 'inline-code-toolbar');
  const resultCount = create('strong', 'inline-code-result-count');
  const search = create('input', 'inline-code-search');
  search.type = 'search';
  search.placeholder = '현재 목록에서 코드 또는 코드명 검색';
  search.setAttribute('aria-label', '현재 TABLE의 코드 또는 코드명 검색');
  toolbar.append(resultCount, search);

  const viewport = create('div', 'inline-code-table-viewport');
  const table = create('table', 'inline-code-table');
  const head = create('thead');
  const headRow = create('tr');
  headRow.append(
    create('th', 'inline-code-column', '코드'),
    create('th', 'inline-code-name-column', '코드명'),
  );
  head.append(headRow);
  const tbody = create('tbody');
  table.append(head, tbody);
  viewport.append(table);

  const normalized = records.map((record) => {
    const values = codeRecordText(record);
    return {
      ...values,
      searchText: `${values.code} ${values.name}`.toUpperCase(),
    };
  });

  function renderRows() {
    const query = String(search.value || '').trim().toUpperCase();
    const filtered = query
      ? normalized.filter((record) => record.searchText.includes(query))
      : normalized;

    tbody.replaceChildren();
    for (const record of filtered) {
      const row = create('tr', 'inline-code-row');
      row.append(
        create('td', 'inline-code-value', record.code),
        create('td', 'inline-code-name', record.name),
      );
      tbody.append(row);
    }
    if (!filtered.length) {
      const row = create('tr', 'inline-code-empty-row');
      const cell = create('td', '', '일치하는 코드 또는 코드명이 없습니다.');
      cell.colSpan = 2;
      row.append(cell);
      tbody.append(row);
    }
    resultCount.textContent = query
      ? `${Ui.formatNumber(filtered.length)} / ${Ui.formatNumber(records.length)}개`
      : `전체 ${Ui.formatNumber(records.length)}개`;
  }

  search.addEventListener('input', renderRows);
  renderRows();
  body.append(toolbar, viewport);
  return body;
}

async function loadInlineTable(card, summary, options = {}) {
  if (card.dataset.loaded === 'true' || card.dataset.loading === 'true') return;
  card.dataset.loading = 'true';
  const content = card.querySelector('.inline-table-content');
  content?.replaceChildren(create('p', 'muted', 'TABLE 코드를 불러오는 중입니다.'));
  try {
    const tableId = String(summary?.entity_id ?? '');
    const payload = await window.KDRG.getDetail({ entityType: 'TABLE', entityId: tableId });
    const label = tableUserLabel({
      entity_id: tableId,
      title: payload.detail?.display_name,
      summary: payload.detail,
    }, options);
    const labelNode = card.querySelector('.table-user-label');
    if (labelNode) labelNode.textContent = label;
    const countNode = card.querySelector('.table-code-count');
    if (countNode) countNode.textContent = `코드 ${Ui.formatNumber((payload.detail?.code_records ?? []).length)}개`;
    const fragment = document.createDocumentFragment();
    fragment.append(renderInlineTableCodeList(payload.detail));
    const actions = create('div', 'inline-table-actions');
    const technical = create('button', 'table-technical-button', 'TABLE 기술 상세');
    technical.type = 'button';
    technical.dataset.entityType = 'TABLE';
    technical.dataset.entityId = tableId;
    actions.append(technical);
    fragment.append(actions);
    content?.replaceChildren(fragment);
    card.dataset.loaded = 'true';
  } catch (error) {
    content?.replaceChildren(create('p', 'error-message', error?.message || 'TABLE 상세를 불러오지 못했습니다.'));
  } finally {
    card.dataset.loading = 'false';
  }
}

function tableCard(summary, options = {}) {
  const tableId = String(summary?.entity_id ?? '');
  const summaryData = summary?.summary ?? {};
  const card = create('details', `table-card inline-table-card ${options.exclusion ? 'table-card-exclusion' : ''}`.trim());
  card.dataset.inlineTableId = tableId;
  const header = create('summary', 'table-card-summary');
  const identity = create('div', 'table-card-identity');
  identity.append(
    options.directCondition
      ? makeChip('코드 목록', 'direct-condition-chip')
      : makeBadge('TABLE'),
    create('strong', 'table-user-label', tableUserLabel(summary, options)),
    create('small', 'table-internal-id', `내부 ID ${tableId}`),
  );
  const meta = create('div', 'table-card-summary-meta');
  const role = options.directCondition
    ? '직접 코드 조건'
    : options.exclusion
      ? '제외 대상'
      : Ui.roleLabel(summaryData.logical_table_type || summaryData.logical_table_scope);
  meta.append(
    makeChip(role, options.exclusion ? 'exclusion-chip' : 'role-chip'),
    makeChip(`코드 ${Ui.formatNumber(summaryData.code_count ?? 0)}개`, 'table-code-count'),
  );
  header.append(identity, meta);
  const content = create('div', 'inline-table-content');
  content.append(create('p', 'muted', 'TABLE을 펼치면 코드가 이 자리에서 표시됩니다.'));
  card.append(header, content);
  card.addEventListener('toggle', () => {
    if (card.open) loadInlineTable(card, summary, options);
  });
  return card;
}

function resolveTableSummary(tableId, summaryMap) {
  return summaryMap.get(String(tableId)) ?? {
    entity_type: 'TABLE',
    entity_id: String(tableId),
    title: String(tableId),
    subtitle: 'TABLE 요약을 찾지 못했습니다.',
    summary: {},
  };
}

const DIRECT_CONDITION_ROLE_PATTERN = /^(주진단명|기타진단명|진단명|시술명|수술명|처치명|검사명|부가코드(?:명)?)$/i;
const DIRECT_CONDITION_NEUTRAL_LABEL = '분류 코드 목록';
function escapeRegExp(value) {
  return String(value ?? '').replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
function directConditionLocalTablePattern(adrg) {
  return new RegExp(`^LT_${escapeRegExp(adrg)}_\\d{3}$`, 'i');
}
function formatUserConditionText(value) {
  return String(value ?? '').replace(/\s+/g, ' ').trim();
}
function renderConditionExpression(value, options = {}) {
  const output = create('p', 'user-condition-text condition-expression');
  const strictOperators = options.strictOperators === true;
  const operatorPattern = strictOperators
    ? /(\bAND\b|\bOR\b|\bWITHOUT\b)/g
    : /(\bAND\b|\bOR\b|\bWITHOUT\b)/g;
  const parts = formatUserConditionText(value).split(operatorPattern);
  const operatorLabels = {
    AND: 'AND',
    OR: 'OR',
    WITHOUT: 'WITHOUT',
  };
  const operatorClasses = {
    AND: 'condition-operator-and',
    OR: 'condition-operator-or',
    WITHOUT: 'condition-operator-without',
  };
  for (const part of parts) {
    const token = String(part || '');
    const operator = token.trim().toUpperCase();
    if (operatorLabels[operator]) {
      output.append(create(
        'strong',
        `condition-operator ${operatorClasses[operator]}`,
        operatorLabels[operator],
      ));
    } else if (token) {
      output.append(document.createTextNode(token));
    }
  }
  return output;
}
function uniqueConditionTerms(values) {
  const output = [];
  const seen = new Set();
  for (const value of values) {
    const text = formatUserConditionText(value);
    if (!text || seen.has(text)) continue;
    seen.add(text);
    output.push(text);
  }
  return output;
}
function conditionLeafText(leaf) {
  const labels = extractOfficialTableLabels(
    leaf?.display_text,
    leaf?.source_fragment,
  );
  if (labels.length) return labels.join(' AND ');
  return formatUserConditionText(
    leaf?.display_text
      || leaf?.source_fragment
      || (leaf?.table_ids ?? []).join(', '),
  );
}
function conditionRefIds(ref) {
  return uniqueConditionTerms([
    ref?.entity_id,
    ref?.logical_table_id,
    ref?.table_id,
    ref?.id,
  ]);
}
function conditionNumberedRefLabels(detail, leaf) {
  const tableIds = new Set(
    uniqueConditionTerms(leaf?.table_ids ?? []),
  );
  if (!tableIds.size) return [];
  const refs = (detail?.user_condition_table_refs ?? [])
    .filter((ref) => (
      conditionRefIds(ref)
        .some((id) => tableIds.has(id))
    ));
  const labels = refs.flatMap((ref) => (
    extractOfficialTableLabels(
      ref?.display_label,
      ref?.display_name,
      ref?.label,
      ref?.source_label,
      ref?.table_name,
      ref?.role_label,
    )
  ));
  return uniqueConditionTerms(labels)
    .filter((label) => /\btable\d+\b/i.test(label));
}
function conditionLeafTableKey(leaf) {
  return uniqueConditionTerms(leaf?.table_ids ?? [])
    .sort()
    .join('|');
}
function conditionDisambiguatedLeafTerms(detail, leaves) {
  const rows = (leaves ?? []).map((leaf) => ({
    leaf,
    text: conditionLeafText(leaf),
    tableKey: conditionLeafTableKey(leaf),
  }));
  return rows.map((row) => {
    const peers = rows.filter(
      (candidate) => candidate.text === row.text,
    );
    const distinctTableKeys = uniqueConditionTerms(
      peers.map((candidate) => candidate.tableKey),
    );
    if (
      peers.length > 1
      && distinctTableKeys.length > 1
    ) {
      const numberedLabels = conditionNumberedRefLabels(
        detail,
        row.leaf,
      );
      if (numberedLabels.length === 1) {
        return numberedLabels[0];
      }
    }
    return row.text;
  });
}
function conditionRequirementText(item) {
  return formatUserConditionText(
    String(
      item?.text
        || item?.display_text
        || '',
    ).replace(/^제외 조건\s*·\s*/i, ''),
  );
}
function conditionGroupExpression(group, detail) {
  const positiveRequirements = (
    group?.requirements ?? []
  ).filter(
    (item) => String(item?.polarity ?? 'include') !== 'exclude',
  );
  const negativeRequirements = (
    group?.requirements ?? []
  ).filter(
    (item) => String(item?.polarity ?? '') === 'exclude',
  );
  const includeTerms = uniqueConditionTerms([
    ...conditionDisambiguatedLeafTerms(
      detail,
      group?.includes ?? [],
    ),
    ...positiveRequirements.map(conditionRequirementText),
  ]);
  const excludeTerms = uniqueConditionTerms([
    ...conditionDisambiguatedLeafTerms(
      detail,
      group?.excludes ?? [],
    ),
    ...negativeRequirements.map(conditionRequirementText),
  ]);
  let expression = includeTerms.join(' AND ');
  if (excludeTerms.length) {
    const excluded = excludeTerms.length > 1
      ? `(${excludeTerms.join(' OR ')})`
      : excludeTerms[0];
    expression = expression
      ? `${expression} WITHOUT ${excluded}`
      : `WITHOUT ${excluded}`;
  }
  return formatUserConditionText(expression);
}
function conditionGroupsExpression(groups, detail) {
  const expressions = uniqueConditionTerms(
    (groups ?? [])
      .map((group) => conditionGroupExpression(group, detail))
      .filter(Boolean),
  );
  const text = expressions
    .map((expression) => (
      expressions.length > 1
      && /\b(?:AND|WITHOUT)\b/i.test(expression)
        ? `(${expression})`
        : expression
    ))
    .join(' OR ');
  if (/\bLT_[A-Z0-9_]+\b/i.test(text)) return '';
  return text;
}

function directConditionTables(detail) {
  const coverage = Ui.userConditionCoverage(detail);
  if (
    coverage.status !== 'NO_EXPLICIT_CONDITION'
    || detail?.condition_ast
    || coverage.table_count
  ) {
    return [];
  }

  const adrg = String(detail?.adrg ?? '').trim();
  const sourceIds = Ui.uniqueStrings(detail?.source_logical_table_ids ?? []);
  if (!adrg || sourceIds.length !== 1) return [];

  const tableId = sourceIds[0];
  if (!directConditionLocalTablePattern(adrg).test(tableId)) return [];

  const summaryMap = Ui.tableSummaryMap(detail);
  const summary = summaryMap.get(tableId);
  if (!summary) return [];

  const summaryData = summary?.summary ?? summary ?? {};
  const codeCount = Number(summaryData.code_count ?? 0);
  if (codeCount <= 0) return [];

  const sourceLabel = tableUserLabel(summary);
  const hasOfficialRoleLabel = DIRECT_CONDITION_ROLE_PATTERN.test(sourceLabel);
  const label = hasOfficialRoleLabel
    ? sourceLabel
    : DIRECT_CONDITION_NEUTRAL_LABEL;

  return [{
    tableId,
    summary,
    label,
    codeCount,
    hasOfficialRoleLabel,
  }];
}
function conditionPresentation(detail) {
  const coverage = Ui.userConditionCoverage(detail);
  const directTables = directConditionTables(detail);
  const groups = Ui.buildConditionGroups(detail?.condition_ast);
  if (directTables.length) {
    const text = directTables.every((item) => item.hasOfficialRoleLabel)
      ? directTables
          .map((item) => `${item.label} 코드가 아래 목록에 포함`)
          .join(' 그리고 ')
      : '아래 코드 목록 자체가 이 ADRG의 분류 조건입니다.';
    return {
      ...coverage,
      status: 'DIRECT_CODE_CONDITION',
      summary: `TABLE 번호 없는 직접 코드조건 ${Ui.formatNumber(directTables.length)}개`,
      text,
      has_text: true,
      direct_tables: directTables,
      groups: [],
    };
  }
  const structuralText = conditionGroupsExpression(groups, detail);
  const text = structuralText || coverage.text;
  return {
    ...coverage,
    text,
    has_text: Boolean(text),
    structural_text: Boolean(structuralText),
    direct_tables: [],
    groups,
  };
}

function userConditionStatusLabel(status) {
  const labels = {
    RESOLVED_AST: '조건 TABLE 연결 완료',
    RESOLVED_SOURCE_LABELS: '조건 TABLE 연결 완료',
    DIRECT_CODE_CONDITION: '직접 코드 조건',
    TEXT_ONLY: '조건 문구만 확인',
    UNRESOLVED_TABLE_LINK: 'TABLE 연결 검토 필요',
    NO_EXPLICIT_CONDITION: '명시적 조건 없음',
  };
  return labels[String(status ?? '')] || '조건 상태 미확인';
}

function renderUserConditionSummary(detail) {
  const coverage = conditionPresentation(detail);
  const description = coverage.needs_review
    ? '일부 조건 TABLE 연결은 검토가 필요합니다.'
    : 'ADRG 분류에 적용되는 조건입니다.';
  const section = makeSection('분류 조건', description, {
    open: true,
    count: coverage.has_text || coverage.groups.length ? 1 : 0,
  });
  const body = create('div', 'user-condition-summary');
  if (
    SHOW_DEVELOPER_METADATA
    || coverage.needs_review
  ) {
    body.append(makeChip(
      userConditionStatusLabel(coverage.status),
      coverage.needs_review ? 'exclusion-chip' : 'role-chip',
    ));
  }
  if (coverage.status === 'DIRECT_CODE_CONDITION') {
    body.append(create('p', 'user-condition-text direct-condition-text', coverage.text));
  } else if (coverage.has_text) {
    body.append(renderConditionExpression(coverage.text, {
      strictOperators: coverage.structural_text === true,
    }));
  } else if (coverage.status === 'NO_EXPLICIT_CONDITION') {
    body.append(create('p', 'user-condition-empty', '분류집에서 별도의 분류 조건과 직접 코드 목록을 확인하지 못했습니다.'));
  } else {
    body.append(create('p', 'user-condition-empty', '표시할 분류 조건 문구가 없습니다.'));
  }
  if (coverage.needs_review) {
    body.append(create('p', 'user-condition-warning', '조건 문구는 확인되지만 연결할 TABLE 근거가 유일하지 않아 TABLE을 추정 표시하지 않습니다.'));
  }
  section.append(body);
  return section;
}

function renderConditionLeafTables(container, leaves, summaryMap, options = {}) {
  for (const leaf of leaves) {
    for (const tableId of leaf.table_ids ?? []) {
      container.append(tableCard(resolveTableSummary(tableId, summaryMap), {
        displayLabel: leaf.display_text,
        sourceText: leaf.source_fragment || leaf.display_text,
        exclusion: options.exclusion === true,
      }));
    }
  }
}
function renderConditionGroup(group, index, total, summaryMap) {
  const article = create('article', 'condition-logic-group');
  const header = create('div', 'condition-logic-header');
  const operator = group.excludes.length
    ? 'WITHOUT 조건'
    : total > 1
      ? 'OR 선택지'
      : group.includes.length > 1
        ? 'AND 조건'
        : '포함 조건';
  header.append(
    create('strong', '', total > 1 ? `조건 선택지 ${index + 1}` : '조건 구조'),
    makeChip(operator, group.excludes.length ? 'exclusion-chip' : 'role-chip'),
  );
  article.append(header);

  if (group.includes.length) {
    const includeBlock = create('div', 'condition-logic-block condition-include-block');
    includeBlock.append(
      create('strong', 'condition-logic-title', '포함 조건'),
      create('p', '', '아래 TABLE 조건을 충족해야 합니다.'),
    );
    const stack = create('div', 'table-stack');
    renderConditionLeafTables(stack, group.includes, summaryMap);
    includeBlock.append(stack);
    article.append(includeBlock);
  }

  if (group.excludes.length) {
    const excludeBlock = create('div', 'condition-logic-block condition-exclude-block');
    excludeBlock.append(
      create('strong', 'condition-logic-title', '제외 조건 · WITHOUT'),
      create('p', '', '아래 TABLE에 해당하면 이 ADRG에서 제외됩니다.'),
    );
    const stack = create('div', 'table-stack');
    renderConditionLeafTables(stack, group.excludes, summaryMap, { exclusion: true });
    excludeBlock.append(stack);
    article.append(excludeBlock);
  }

  if (group.requirements.length) {
    const requirements = create('div', 'condition-requirement-block');
    requirements.append(create('strong', '', '추가 확인 조건'));
    for (const item of group.requirements) {
      requirements.append(create('p', '', item.text || item.display_text || '-'));
    }
    article.append(requirements);
  }
  return article;
}
function renderUserConditionTables(detail) {
  const coverage = conditionPresentation(detail);
  const tables = Array.isArray(detail.user_condition_tables) ? detail.user_condition_tables : [];
  const count = coverage.groups.length
    || coverage.direct_tables.length
    || tables.length;
  const section = makeSection(
    '조건 상세',
    'AND·OR·WITHOUT와 직접 코드조건을 구분해 표시합니다. 목록을 펼치면 코드·코드명 검색이 가능합니다.',
    { open: true, count },
  );
  const body = create('div', 'table-stack user-condition-table-stack');
  const summaryMap = Ui.tableSummaryMap(detail);

  if (coverage.groups.length) {
    coverage.groups.forEach((group, index) => {
      body.append(renderConditionGroup(group, index, coverage.groups.length, summaryMap));
    });
  } else if (coverage.direct_tables.length) {
    const block = create('div', 'condition-logic-block direct-condition-block');
    block.append(
      create('strong', 'condition-logic-title', '직접 코드 조건'),
      create('p', '', '원문에 table 번호가 없으며 아래 코드 목록 자체가 분류 조건입니다.'),
    );
    const stack = create('div', 'table-stack');
    for (const item of coverage.direct_tables) {
      stack.append(tableCard(item.summary, {
        displayLabel: item.label,
        sourceText: item.label,
        directCondition: true,
      }));
    }
    block.append(stack);
    body.append(block);
  } else {
    for (const summary of tables) {
      body.append(tableCard(summary, {
        displayLabel: summary?.user_condition_ref?.display_label,
        sourceText: summary?.user_condition_ref?.display_label,
      }));
    }
  }

  if (!count) {
    body.append(create('p', 'user-condition-empty', coverage.needs_review
      ? '공식 근거가 유일하지 않아 TABLE 카드를 생성하지 않았습니다.'
      : '표시할 조건 TABLE 또는 직접 코드 목록이 없습니다.'));
  }
  section.append(body);
  return section;
}

function renderUserConditionEvidence(detail) {
  const coverage = conditionPresentation(detail);
  const ast = detail.condition_ast;
  const page = detail.user_condition_page ?? ast?.page_range?.start_printed_page ?? null;
  const section = makeSection('원문 근거', '사용자 표시 조건의 출처와 기술 근거를 확인합니다.', {
    open: false,
    count: detail.user_condition_source || coverage.direct_tables.length ? 1 : 0,
  });
  const body = create('div', 'user-condition-evidence');
  body.append(makeMetaGrid([
    ['조건 상태', userConditionStatusLabel(coverage.status)],
    ['조건 원문', detail.user_condition_text || coverage.text || '명시적 조건 없음'],
    ['근거 출처', detail.user_condition_source || (coverage.direct_tables.length ? 'ADRG 원천 코드 목록' : '-')],
    ['근거 페이지', page || '-'],
    ['조건 AST', detail.condition_ast_id || '별도 AST 없음'],
    ['기술식', ast?.canonical_expression || '-'],
  ]));
  section.append(body);
  return section;
}

function renderDerivedAadrgList(records) {
  const container = create('div', 'derived-aadrg-list');
  if (!Array.isArray(records) || !records.length) {
    container.append(create('p', 'muted', '파생 AADRG가 없습니다.'));
    return container;
  }
  for (const record of records) {
    const row = create('article', 'derived-aadrg-row');
    const main = create('div', 'derived-aadrg-main');
    main.append(
      makeBadge('AADRG'),
      create('strong', '', record.entity_id || '-'),
      create('span', '', String(record.title || '').replace(`${record.entity_id} · `, '')),
    );
    const meta = create('div', 'chip-row');
    const summary = record.summary ?? {};
    appendClassificationBadges(
      meta,
      [
        summary.classification_code
          || summary.classification_display_label,
      ],
    );
    if (Number.isFinite(Number(summary.rdrg_count))) meta.append(makeChip(`RDRG ${Ui.formatNumber(summary.rdrg_count)}개`));
    row.append(main, meta);
    container.append(row);
  }
  return container;
}


function displayNameText(value, fallback = '명칭 미수록') {
  const text = String(value ?? '').replace(/\s+/g, ' ').trim();
  if (!text || /^(null|none|undefined)$/i.test(text)) return fallback;
  return text;
}

function adrgDisplayName(detail) {
  return displayNameText(detail?.adrg_name);
}

function renderAdrgDetail(payload) {
  const detail = payload.detail;
  const fragment = document.createDocumentFragment();
  fragment.append(
    makeMetaGrid([
      ['ADRG', detail.adrg],
      ['질병군명', adrgDisplayName(detail)],
      ['MDC', detail.mdc ? `MDC ${detail.mdc}` : '-'],
      ['AADRG', `${Ui.formatNumber(detail.aadrg_count ?? 0)}개`],
      [
        '질병군 분류',
        makeClassificationBadgeGroup(
          (detail.abc_classification_codes ?? []).length
            ? detail.abc_classification_codes
            : detail.abc_display_labels,
        ),
      ],
      ...(SHOW_DEVELOPER_METADATA
        ? [[
          '조건 상태',
          userConditionStatusLabel(
            conditionPresentation(detail).status,
          ),
        ]]
        : []),
    ], 'detail-overview-grid'),
  );

  const aadrgSection = makeSection('파생 AADRG', 'ADRG에서 파생되는 AADRG와 질병군 분류를 함께 확인합니다.', { open: false, count: (detail.aadrg_records ?? []).length });
  aadrgSection.append(renderDerivedAadrgList(detail.aadrg_records));
  fragment.append(
    aadrgSection,
    renderUserConditionSummary(detail),
    renderUserConditionTables(detail),
    ...(SHOW_DEVELOPER_METADATA
      ? [renderUserConditionEvidence(detail)]
      : []),
  );
  return fragment;
}

function renderAadrgDetail(payload) {
  const detail = payload.detail;
  const fragment = document.createDocumentFragment();
  fragment.append(
    makeMetaGrid([
      ['AADRG', detail.aadrg],
      ['질병군명', detail.group_name],
      ['상위 ADRG', detail.adrg],
      ['MDC', detail.mdc ? `MDC ${detail.mdc}` : '-'],
      [
        '질병군 분류',
        makeClassificationBadgeGroup([
          detail.classification_code
            || detail.classification_display_label,
        ]),
      ],
      ['RDRG', `${Ui.formatNumber((detail.rdrg_codes ?? []).length)}개`],
    ], 'detail-overview-grid'),
  );
  const parent = makeSection('상위 ADRG', '', { open: true, count: detail.parent_adrg ? 1 : 0 });
  parent.append(makeSummaryList(detail.parent_adrg ? [detail.parent_adrg] : []));
  const rdrg = makeSection('파생 RDRG', '중증도 분기를 포함한 최종 RDRG입니다.', { open: false, count: (detail.rdrg_records ?? []).length });
  rdrg.append(makeSummaryList(detail.rdrg_records));
  fragment.append(parent, rdrg);
  return fragment;
}

function renderRdrgDetail(payload) {
  const detail = payload.detail;
  const fragment = document.createDocumentFragment();
  fragment.append(
    makeMetaGrid([
      ['RDRG', detail.code],
      ['질병군명', detail.group_name],
      ['중증도', detail.severity_name],
      ['상위 AADRG', detail.aadrg],
      ['상위 ADRG', detail.adrg],
    ], 'detail-overview-grid'),
  );
  const parents = makeSection('상위 분류 관계', '', { open: true, count: [detail.parent_aadrg, detail.parent_adrg].filter(Boolean).length });
  parents.append(makeSummaryList([detail.parent_aadrg, detail.parent_adrg].filter(Boolean)));
  fragment.append(parents);
  return fragment;
}

function renderCodeDetail(payload) {
  const detail = payload.detail;
  const fragment = document.createDocumentFragment();
  fragment.append(
    makeMetaGrid([
      ['코드', detail.code],
      ['코드명', Ui.summarizeList(detail.names)],
      ['코드 역할', Ui.summarizeList((detail.roles ?? []).map(Ui.roleLabel))],
      ['연결 TABLE', `${Ui.formatNumber((detail.logical_table_ids ?? []).length)}개`],
      ['관련 ADRG', `${Ui.formatNumber((detail.related_adrgs ?? []).length)}개`],
      ['관련 AADRG', `${Ui.formatNumber((detail.related_aadrgs ?? []).length)}개`],
    ], 'detail-overview-grid'),
  );

  const tables = makeSection('포함 TABLE', '원문 정의 위치·조건 AST 사용 관계·검색용 통합 관계를 구분합니다.', { open: true, count: (detail.logical_tables ?? []).length });
  const stack = create('div', 'table-stack');
  for (const table of detail.logical_tables ?? []) {
    const summary = {
      entity_type: 'TABLE',
      entity_id: table.logical_table_id,
      title: table.display_name || table.logical_table_id,
      subtitle: `${Ui.roleLabel(table.logical_table_type)} · 관련 ADRG ${(table.related_adrgs ?? []).length}개`,
      summary: {
        display_name: table.display_name,
        logical_table_type: table.logical_table_type,
        related_adrgs: table.related_adrgs,
        code_count: table.code_count,
        runtime_contexts: table.runtime_contexts,
      },
    };
    stack.append(tableCard(summary, {
      sourceText: (table.runtime_contexts ?? []).map((context) => context.source_fragment),
    }));
  }
  if (!stack.childNodes.length) stack.append(create('p', 'muted', '연결된 TABLE이 없습니다.'));
  tables.append(stack);

  const adrgs = makeSection('관련 ADRG', '', { open: false, count: (detail.related_adrg_summaries ?? []).length });
  adrgs.append(makeSummaryList(detail.related_adrg_summaries));
  const aadrgs = makeSection('관련 AADRG', '검색 결과로 분리하지 않고 ADRG의 파생정보로만 표시합니다.', { open: false, count: (detail.related_aadrg_summaries ?? []).length });
  aadrgs.append(renderDerivedAadrgList(detail.related_aadrg_summaries));
  fragment.append(tables, adrgs, aadrgs);
  return fragment;
}

function renderRuntimeContexts(contexts) {
  const container = create('div', 'context-list');
  if (!Array.isArray(contexts) || !contexts.length) {
    container.append(create('p', 'muted', '조건 AST 사용 관계가 없습니다.'));
    return container;
  }
  for (const context of contexts) {
    const card = create('article', `context-card ${context.polarity === 'exclude' ? 'context-exclude' : 'context-include'}`);
    const top = create('div', 'context-card-top');
    top.append(
      makeChip(context.polarity === 'exclude' ? '제외' : '포함', context.polarity === 'exclude' ? 'exclusion-chip' : 'include-chip'),
      makeChip(context.adrg ? `ADRG ${context.adrg}` : 'ADRG 미확인'),
    );
    card.append(top);
    card.append(
      create('strong', '', context.requirement_label || context.display_label || context.occurrence_qualifier || '조건 TABLE 관계'),
      create('p', '', context.source_fragment || context.reference_context_text || '-'),
    );
    container.append(card);
  }
  return container;
}

function renderCodeRecords(records) {
  return renderInlineTableCodeList({
    code_records: Array.isArray(records) ? records : [],
  });
}

function tableDetailUserLabel(detail) {
  return tableUserLabel({
    entity_id: detail.logical_table_id,
    title: detail.display_name,
    summary: detail,
  }, {
    sourceText: (detail.runtime_contexts ?? []).map((context) => context.source_fragment),
  });
}

function renderTableDetail(payload) {
  const detail = payload.detail;
  const fragment = document.createDocumentFragment();
  fragment.append(
    makeMetaGrid([
      ['원문 TABLE명', tableDetailUserLabel(detail)],
      ['내부 TABLE ID', detail.logical_table_id],
      ['코드 구분', Ui.roleLabel(detail.logical_table_type || detail.logical_table_scope)],
      ['코드 수', `${Ui.formatNumber(detail.code_count ?? (detail.codes ?? []).length)}개`],
      ['원문 정의 ADRG', Ui.summarizeList(detail.source_adrgs)],
      ['조건 AST ADRG', Ui.summarizeList(detail.condition_adrgs)],
      ['검색용 관련 ADRG', Ui.summarizeList(detail.related_adrgs)],
      ['원문 family 근거', Ui.summarizeList(detail.source_adrg_families)],
    ], 'detail-overview-grid'),
  );
  const contexts = makeSection('조건 AST 사용 관계', '포함과 제외 polarity를 분리하여 표시합니다.', { open: (detail.runtime_contexts ?? []).length > 0, count: (detail.runtime_contexts ?? []).length });
  contexts.append(renderRuntimeContexts(detail.runtime_contexts));
  const codes = makeSection('TABLE 코드', '원천에 코드명이 없으면 임의로 생성하지 않습니다.', { open: false, count: (detail.code_records ?? []).length });
  codes.append(renderCodeRecords(detail.code_records));
  const related = makeSection('관련 ADRG', '', { open: false, count: (detail.related_adrg_summaries ?? []).length });
  related.append(makeSummaryList(detail.related_adrg_summaries));
  fragment.append(contexts, codes, related);
  return fragment;
}

function detailSummaryLine(payload) {
  const detail = payload.detail ?? {};
  if (payload.entity_type === 'ADRG') {
    return [
      detail.mdc ? `MDC ${detail.mdc}` : '',
      Number.isFinite(Number(detail.aadrg_count)) ? `AADRG ${Ui.formatNumber(detail.aadrg_count)}개` : '',
    ].filter(Boolean).join(' · ');
  }
  if (payload.entity_type === 'AADRG') {
    return [
      detail.adrg ? `상위 ADRG ${detail.adrg}` : '',
      detail.mdc ? `MDC ${detail.mdc}` : '',
      Ui.classificationLabel(detail.classification_code, detail.classification_display_label),
    ].filter(Boolean).join(' · ');
  }
  if (payload.entity_type === 'RDRG') {
    return [detail.severity_name, detail.aadrg ? `상위 AADRG ${detail.aadrg}` : ''].filter(Boolean).join(' · ');
  }
  if (payload.entity_type === 'TABLE') {
    return [
      `코드 ${Ui.formatNumber(detail.code_count ?? (detail.codes ?? []).length)}개`,
      `관련 ADRG ${Ui.formatNumber((detail.related_adrgs ?? []).length)}개`,
    ].join(' · ');
  }
  return [
    `연결 TABLE ${Ui.formatNumber((detail.logical_table_ids ?? []).length)}개`,
    `관련 ADRG ${Ui.formatNumber((detail.related_adrgs ?? []).length)}개`,
  ].join(' · ');
}

function detailTitle(payload) {
  const detail = payload.detail ?? {};
  if (payload.entity_type === 'ADRG') return `${detail.adrg} · ${adrgDisplayName(detail)}`;
  if (payload.entity_type === 'AADRG') return `${detail.aadrg} · ${detail.group_name}`;
  if (payload.entity_type === 'RDRG') return `${detail.code} · ${detail.group_name}`;
  if (payload.entity_type === 'TABLE') return tableDetailUserLabel(detail);
  return detail.code || payload.entity_id;
}

function renderDetail(payload) {
  const panel = byId('detail-content');
  panel.replaceChildren();
  const header = create('div', 'detail-primary detail-hero');
  header.append(makeBadge(payload.entity_type));
  const copy = create('div', 'detail-hero-copy');
  copy.append(
    create('h2', '', detailTitle(payload)),
    create('p', '', detailSummaryLine(payload) || `${Ui.entityLabel(payload.entity_type)} · ${payload.entity_id}`),
  );
  header.append(copy);
  if (payload.entity_type === 'ADRG') {
    header.append(
      makeClassificationBadgeGroup(
        (payload.detail?.abc_classification_codes ?? []).length
          ? payload.detail.abc_classification_codes
          : payload.detail?.abc_display_labels,
        'detail-hero-classification',
      ),
    );
  }
  panel.append(header);

  let content;
  if (payload.entity_type === 'ADRG') content = renderAdrgDetail(payload);
  else if (payload.entity_type === 'AADRG') content = renderAadrgDetail(payload);
  else if (payload.entity_type === 'RDRG') content = renderRdrgDetail(payload);
  else if (payload.entity_type === 'TABLE') content = renderTableDetail(payload);
  else content = renderCodeDetail(payload);
  panel.append(content);

  setText('detail-heading', `${Ui.entityLabel(payload.entity_type)} 상세`);
  setText('detail-caption', payload.entity_id);
  setDetailFoldActions(true);
}

function markSelected(key) {
  state.selectedKey = key;
  for (const card of document.querySelectorAll('.result-card')) {
    const selected = card.dataset.resultKey === key;
    card.classList.toggle('is-selected', selected);
    card.setAttribute('aria-pressed', String(selected));
  }
}

async function openDetail(entityType, entityId) {
  const sequence = ++state.detailSequence;
  const key = `${entityType}:${entityId}`;
  markSelected(key);
  setText('detail-heading', '상세 정보를 불러오는 중');
  setText('detail-caption', key);
  try {
    const payload = await window.KDRG.getDetail({ entityType, entityId });
    if (sequence !== state.detailSequence) return;
    renderDetail(payload);
  } catch (error) {
    if (sequence !== state.detailSequence) return;
    clearDetail(error?.message || '상세조회 중 오류가 발생했습니다.');
  }
}


const RELATION_CODE_TYPE_OPTIONS = Object.freeze([
  ['AUTO', '자동판별'],
  ['DIAGNOSIS', '상병코드'],
  ['SECONDARY_DIAGNOSIS', '기타진단코드'],
  ['PROCEDURE', '수술·처치코드'],
  ['TEST', '검사·처치코드'],
  ['ADD_ON', '부가코드'],
  ['OTHER', '기타 조건 코드'],
]);

function updateRelationRowControls() {
  const rows = [...document.querySelectorAll('[data-relation-condition]')];
  rows.forEach((row, index) => {
    const label = row.querySelector('.relation-condition-number');
    if (label) label.textContent = `검색 ${index + 1}`;
    const remove = row.querySelector('[data-relation-remove]');
    if (remove) remove.disabled = rows.length <= 2;
  });
  byId('relation-add').disabled = rows.length >= 6;
}

function createRelationConditionRow(value = {}) {
  const row = create('div', 'relation-condition-row');
  row.dataset.relationCondition = 'true';
  row.append(create('strong', 'relation-condition-number', '검색'));
  const type = create('select', 'relation-code-type');
  type.setAttribute('aria-label', '관계검색 코드 유형');
  for (const [optionValue, label] of RELATION_CODE_TYPE_OPTIONS) {
    const option = create('option', '', label);
    option.value = optionValue;
    if (optionValue === String(value.codeType ?? 'AUTO')) option.selected = true;
    type.append(option);
  }
  const input = create('input', 'relation-code-input');
  input.type = 'search';
  input.maxLength = 100;
  input.placeholder = '정확한 코드 입력 · 예: O1311';
  input.value = String(value.code ?? '');
  input.setAttribute('aria-label', '관계검색 정확한 코드');
  const remove = create('button', 'relation-remove-button', '삭제');
  remove.type = 'button';
  remove.dataset.relationRemove = 'true';
  row.append(type, input, remove);
  return row;
}

function addRelationCondition(value = {}) {
  const container = byId('relation-condition-list');
  if (container.childElementCount >= 6) return;
  container.append(createRelationConditionRow(value));
  updateRelationRowControls();
}

function resetRelationForm(options = {}) {
  const container = byId('relation-condition-list');
  container.replaceChildren();
  addRelationCondition();
  addRelationCondition();
  byId('relation-operator').value = 'AND';
  state.relationResponse = null;
  if (options.clearResults !== false && state.activeMode === 'relation') {
    byId('result-list').replaceChildren();
    byId('type-counts').replaceChildren();
    setText('result-count', '0건');
    setText('result-caption', '복수 코드를 입력하면 관계검색 결과가 표시됩니다.');
    setText('page-label', '0–0 / 0');
    clearDetail('복수 코드 관계검색 결과를 선택하면 연결 구조가 표시됩니다.');
  }
}

function currentRelationRequest() {
  const conditions = [...document.querySelectorAll('[data-relation-condition]')].map((row) => ({
    codeType: row.querySelector('.relation-code-type').value,
    code: row.querySelector('.relation-code-input').value,
  }));
  return {
    conditions,
    operator: byId('relation-operator').value,
    mdc: byId('filter-mdc').value,
    classification: byId('filter-classification').value,
  };
}

function setRelationBusy(isBusy) {
  byId('relation-submit').disabled = isBusy;
  byId('relation-reset').disabled = isBusy;
  byId('relation-add').disabled = isBusy || document.querySelectorAll('[data-relation-condition]').length >= 6;
  for (const element of document.querySelectorAll('.relation-code-type, .relation-code-input, [data-relation-remove], #relation-operator')) {
    element.disabled = isBusy || (element.matches('[data-relation-remove]') && document.querySelectorAll('[data-relation-condition]').length <= 2);
  }
  for (const id of ['search-submit', 'search-reset', 'search-query', 'filter-type', 'filter-mdc', 'filter-classification']) {
    const element = byId(id);
    if (element) element.disabled = isBusy;
  }
  byId('relation-submit').textContent = isBusy ? '관계 검색 중' : '공통 관련 ADRG 검색';
}

async function runRelationSearch() {
  const request = currentRelationRequest();
  const emptyIndex = request.conditions.findIndex((condition) => !String(condition.code ?? '').trim());
  if (emptyIndex >= 0) {
    const input = document.querySelectorAll('.relation-code-input')[emptyIndex];
    input?.focus();
    setStatus('error', '복수 코드 관계검색 입력을 확인하세요.', `${emptyIndex + 1}번 코드를 입력해야 합니다.`);
    return;
  }
  const sequence = ++state.relationSequence;
  setRelationBusy(true);
  setStatus('loading', '복수 코드 관계를 확인하는 중입니다.', `${request.conditions.length}개 코드 · ${request.operator} 조건`);
  try {
    const response = await window.KDRG.relationSearch(request);
    if (sequence !== state.relationSequence) return;
    state.selectedKey = null;
    renderRelationResults(response);
    setStatus(
      'ready',
      `${Ui.formatNumber(response.total_count)}개 ADRG`,
      response.total_count ? response.disclaimer : '코드 유형·MDC·질병군 분류 또는 AND/OR 조건을 조정하세요.',
    );
    if (response.results.length) {
      const first = response.results[0];
      markSelected(`RELATION:${first.entity_id}:0`);
      renderRelationDetail(first, response);
    } else {
      clearDetail('복수 코드가 연결되는 ADRG 조건식을 찾지 못했습니다.');
    }
  } catch (error) {
    if (sequence !== state.relationSequence) return;
    setStatus('error', '복수 코드 관계검색을 완료하지 못했습니다.', error?.message || '알 수 없는 오류');
    byId('result-list').replaceChildren(create('p', 'error-message', error?.message || '관계검색 오류'));
  } finally {
    if (sequence === state.relationSequence) setRelationBusy(false);
  }
}

function currentRequest(offset = 0) {
  return {
    query: byId('search-query').value,
    entityType: byId('filter-type').value,
    mdc: byId('filter-mdc').value,
    classification: byId('filter-classification').value,
    limit: 50,
    offset,
  };
}

async function runSearch(request, options = {}) {
  const query = String(request.query ?? '').trim();
  if (!query) {
    byId('search-query').focus();
    setStatus('error', '검색어를 입력해야 합니다.', '코드·ADRG 또는 질병군명을 입력하세요.');
    return;
  }
  const sequence = ++state.searchSequence;
  state.activeMode = 'search';
  state.request = { ...request, query };
  setBusy(true, '검색 중');
  setStatus('loading', '검색 중입니다.', `${query} · 검색 서비스에서 결과를 확인하고 있습니다.`);
  try {
    const response = await window.KDRG.search(state.request);
    if (sequence !== state.searchSequence) return;
    state.selectedKey = null;
    renderResults(response);
    setStatus(
      'ready',
      `${Ui.formatNumber(response.total_count)}건`,
      response.total_count ? Ui.typeCountText(response.type_counts) : '필터를 조정하거나 다른 검색어를 입력하세요.',
    );
    if (response.results.length && options.openFirst !== false) {
      const first = response.results[0];
      await openDetail(first.entity_type, first.entity_id);
    } else if (!response.results.length) {
      clearDetail('검색 결과가 없어 상세 항목을 표시할 수 없습니다.');
    }
  } catch (error) {
    if (sequence !== state.searchSequence) return;
    setStatus('error', '검색을 완료하지 못했습니다.', error?.message || '알 수 없는 오류');
    const list = byId('result-list');
    list.replaceChildren(create('p', 'error-message', error?.message || '검색 오류'));
  } finally {
    if (sequence === state.searchSequence) setBusy(false);
  }
}

function resetSearch() {
  byId('search-form').reset();
  state.response = null;
  state.request = null;
  state.selectedKey = null;
  state.relationResponse = null;
  state.activeMode = 'search';
  byId('result-list').replaceChildren();
  byId('type-counts').replaceChildren();
  setText('result-count', '0건');
  setText('result-caption', '검색어를 입력하면 결과가 표시됩니다.');
  setText('page-label', '0–0 / 0');
  byId('page-previous').disabled = true;
  byId('page-next').disabled = true;
  clearDetail();
  setStatus('ready', '검색 준비', '코드·ADRG·질병군명 검색');
  byId('search-query').focus();
}

function bindEvents() {
  byId('search-form').addEventListener('submit', (event) => {
    event.preventDefault();
    runSearch(currentRequest(0));
  });
  byId('search-reset').addEventListener('click', resetSearch);
  byId('page-previous').addEventListener('click', () => {
    if (!state.response || !state.request) return;
    runSearch({ ...state.request, offset: Math.max(0, state.response.offset - state.response.limit) }, { openFirst: true });
  });
  byId('page-next').addEventListener('click', () => {
    if (!state.response || !state.request || !state.response.has_more) return;
    runSearch({ ...state.request, offset: state.response.offset + state.response.limit }, { openFirst: true });
  });
  byId('relation-form').addEventListener('submit', (event) => {
    event.preventDefault();
    runRelationSearch();
  });
  byId('relation-add').addEventListener('click', () => addRelationCondition());
  byId('relation-reset').addEventListener('click', () => resetRelationForm());
  byId('detail-expand-all').addEventListener('click', () => setAllDetailSections(true));
  byId('detail-collapse-all').addEventListener('click', () => setAllDetailSections(false));

  document.addEventListener('click', (event) => {
    const removeCondition = event.target.closest('[data-relation-remove]');
    if (removeCondition) {
      const rows = document.querySelectorAll('[data-relation-condition]');
      if (rows.length > 2) removeCondition.closest('[data-relation-condition]')?.remove();
      updateRelationRowControls();
      return;
    }
    const relationCard = event.target.closest('[data-relation-index]');
    if (relationCard && state.relationResponse) {
      const index = Number(relationCard.dataset.relationIndex);
      const candidate = state.relationResponse.results[index];
      if (candidate) {
        markSelected(`RELATION:${candidate.entity_id}:${index}`);
        renderRelationDetail(candidate, state.relationResponse);
      }
      return;
    }
    const entityButton = event.target.closest('[data-entity-type][data-entity-id]');
    if (entityButton) {
      openDetail(entityButton.dataset.entityType, entityButton.dataset.entityId);
      return;
    }
    const sample = event.target.closest('[data-sample-query]');
    if (sample) {
      byId('search-query').value = sample.dataset.sampleQuery;
      runSearch(currentRequest(0));
    }
  });
}

async function initialize() {
  if (!Ui) throw new Error('UI formatter 모듈을 찾을 수 없습니다.');
  if (!window.KDRG || typeof window.KDRG.search !== 'function' || typeof window.KDRG.relationSearch !== 'function' || typeof window.KDRG.getDetail !== 'function') {
    throw new Error('보안 preload 검색 bridge를 찾을 수 없습니다.');
  }

  setStatus('loading', '통합 데이터를 확인하는 중입니다.', 'SHA256·schema·검색 서비스 준비 상태를 점검합니다.');
  const [snapshot, serviceStatus] = await Promise.all([
    window.KDRG.getBootstrapSnapshot(),
    window.KDRG.getSearchStatus(),
  ]);
  if (!snapshot || snapshot.status !== 'ready' || !serviceStatus?.ready) {
    throw new Error('통합 데이터 또는 검색 서비스 준비 상태가 올바르지 않습니다.');
  }
  state.snapshot = snapshot;
  state.serviceStatus = serviceStatus;
  renderMetrics(snapshot);
  bindEvents();
  resetRelationForm({ clearResults: false });
  resetSearch();
}

document.addEventListener('DOMContentLoaded', () => {
  initialize().catch((error) => {
    setStatus('error', 'Electron 검색 화면을 준비하지 못했습니다.', error?.message || '알 수 없는 오류');
    clearDetail(error?.message || '초기화 오류');
  });
});
