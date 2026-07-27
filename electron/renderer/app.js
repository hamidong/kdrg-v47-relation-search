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
};

const TYPE_BADGE_CLASS = Object.freeze({
  CODE: 'badge-code',
  ADRG: 'badge-adrg',
  AADRG: 'badge-aadrg',
  RDRG: 'badge-rdrg',
  TABLE: 'badge-table',
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
  setText('stage-badge', 'Stage 50C');
  setText('data-version', snapshot.dataVersion);
}

function renderTypeCounts(response) {
  const container = byId('type-counts');
  container.replaceChildren();
  const typeCounts = response?.type_counts ?? {};
  for (const type of ['CODE', 'ADRG', 'AADRG', 'RDRG', 'TABLE']) {
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

    const top = create('div', 'result-card-top');
    top.append(makeBadge(result.entity_type));
    const match = makeChip(result.match_type || '검색 일치', 'match-chip');
    match.title = (result.matched_fields ?? []).join(', ');
    top.append(match);

    const title = create('strong', 'result-title', result.title);
    const subtitle = create('p', 'result-subtitle', result.subtitle);
    const chips = create('div', 'chip-row');
    for (const label of Ui.resultSummaryChips(result)) chips.append(makeChip(label));

    button.append(top, title, subtitle, chips);
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
  setText('detail-caption', '기본 TABLE과 추가 분기조건을 구분해 표시합니다.');
}

function makeSection(title, description = '') {
  const section = create('section', 'detail-section');
  const header = create('div', 'section-header');
  const titleWrap = create('div');
  titleWrap.append(create('h3', '', title));
  if (description) titleWrap.append(create('p', '', description));
  header.append(titleWrap);
  section.append(header);
  return section;
}

function makeMetaGrid(rows) {
  const grid = create('dl', 'meta-grid');
  for (const [key, value] of rows) {
    const row = create('div');
    row.append(create('dt', '', key), create('dd', '', Ui.text(value)));
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

function tableCard(summary, options = {}) {
  const card = create('article', `table-card ${options.exclusion ? 'table-card-exclusion' : ''}`.trim());
  const top = create('div', 'table-card-top');
  const open = makeEntityButton(summary, 'table-open-button');
  top.append(open);
  const role = options.exclusion ? '제외 대상' : Ui.roleLabel(summary?.summary?.logical_table_type || summary?.summary?.logical_table_scope);
  top.append(makeChip(role, options.exclusion ? 'exclusion-chip' : 'role-chip'));
  card.append(top);
  const summaryData = summary?.summary ?? {};
  const chips = create('div', 'chip-row');
  chips.append(
    makeChip(`코드 ${Ui.formatNumber(summaryData.code_count ?? 0)}개`),
    makeChip(`관련 ADRG ${Ui.formatNumber((summaryData.related_adrgs ?? []).length)}개`),
  );
  card.append(chips);
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

function renderBasicTables(detail) {
  const section = makeSection(
    '기본 분류 TABLE',
    '분류집 원문에서 이 ADRG 아래에 정의된 TABLE입니다. 이 목록 자체는 포함·제외 논리를 뜻하지 않습니다.',
  );
  const body = create('div', 'table-stack');
  const ids = Ui.uniqueStrings(detail.source_logical_table_ids ?? []);
  const summaryMap = Ui.tableSummaryMap(detail);
  if (!ids.length) body.append(create('p', 'muted', '기본 분류 TABLE이 확인되지 않았습니다.'));
  for (const tableId of ids) body.append(tableCard(resolveTableSummary(tableId, summaryMap)));
  section.append(body);
  return section;
}

function conditionTableRow(leaf, summaryMap, exclusion) {
  const wrapper = create('div', `condition-table ${exclusion ? 'condition-exclusion' : 'condition-include'}`);
  const heading = create('div', 'condition-table-heading');
  heading.append(
    makeChip(exclusion ? '제외 대상' : '기본 포함조건', exclusion ? 'exclusion-chip' : 'include-chip'),
    makeChip(leaf.role || '코드(유형 미확정)', 'role-chip'),
  );
  wrapper.append(heading);
  for (const tableId of leaf.table_ids ?? []) {
    wrapper.append(tableCard(resolveTableSummary(tableId, summaryMap), { exclusion }));
  }
  if (!(leaf.table_ids ?? []).length) wrapper.append(create('p', 'muted', leaf.display_text));
  return wrapper;
}

function renderConditionGroups(detail) {
  const ast = detail.condition_ast;
  const coverage = Ui.conditionCoverage(detail);
  const section = makeSection('추가 분기조건', coverage.summary);
  const body = create('div', 'condition-groups');
  const summaryMap = Ui.tableSummaryMap(detail);
  const groups = Ui.buildConditionGroups(ast);

  if (!ast) {
    const notice = create('div', 'condition-empty');
    notice.append(
      create('strong', '', '별도의 추가 분기조건 없음'),
      create('p', '', '기본 분류 TABLE은 존재하지만 조건 AST가 없는 ADRG입니다. 조건이 없다는 의미를 임의로 확대하지 않습니다.'),
    );
    body.append(notice);
  } else {
    groups.forEach((group, index) => {
      const box = create('article', 'condition-group');
      box.append(create('h4', '', groups.length > 1 ? `조건 선택지 ${index + 1}` : '적용 조건'));

      if (group.includes.length) {
        const includes = create('div', 'condition-block');
        includes.append(create('p', 'condition-label include-label', '다음 조건을 충족'));
        group.includes.forEach((leaf, leafIndex) => {
          if (leafIndex) includes.append(create('div', 'operator-label', '그리고'));
          includes.append(conditionTableRow(leaf, summaryMap, false));
        });
        box.append(includes);
      }

      if (group.excludes.length) {
        const excludes = create('div', 'condition-block exclusion-block');
        excludes.append(create('p', 'condition-label exclude-label', '단, 다음 대상은 제외'));
        group.excludes.forEach((leaf) => excludes.append(conditionTableRow(leaf, summaryMap, true)));
        box.append(excludes);
      }

      if (group.requirements.length) {
        const requirements = create('div', 'requirement-list');
        requirements.append(create('p', 'condition-label', '추가 확인 조건'));
        for (const requirement of group.requirements) {
          const row = create('div', `requirement-row ${requirement.polarity === 'exclude' ? 'requirement-exclusion' : ''}`);
          row.append(create('strong', '', requirement.text));
          if (requirement.semantic_type) row.append(create('small', '', requirement.semantic_type));
          requirements.append(row);
        }
        box.append(requirements);
      }

      if (!group.includes.length && !group.excludes.length && !group.requirements.length) {
        box.append(create('p', 'muted', '표시할 추가 조건이 없습니다.'));
      }
      body.append(box);
      if (index < groups.length - 1) body.append(create('div', 'or-divider', '또는'));
    });

    const technical = create('details', 'technical-details');
    technical.append(create('summary', '', '기술식·원문 근거 보기'));
    technical.append(
      makeMetaGrid([
        ['조건 원문', ast.source_raw_text],
        ['정규화 원문', ast.source_normalized_text],
        ['기술식', ast.canonical_expression],
        ['근거 페이지', ast.page_range?.start_printed_page ? `${ast.page_range.start_printed_page}–${ast.page_range.end_printed_page}` : '-'],
        ['AST ID', ast.condition_ast_id],
      ]),
    );
    body.append(technical);
  }
  section.append(body);
  return section;
}

function renderAdrgDetail(payload) {
  const detail = payload.detail;
  const fragment = document.createDocumentFragment();
  fragment.append(
    makeMetaGrid([
      ['ADRG', detail.adrg],
      ['질병군명', detail.adrg_name],
      ['MDC', detail.mdc ? `MDC ${detail.mdc}` : '-'],
      ['AADRG', `${Ui.formatNumber(detail.aadrg_count ?? 0)}개`],
      ['질병군 분류', Ui.summarizeList(detail.abc_display_labels)],
      ['조건 AST', detail.condition_ast_id || '별도 AST 없음'],
    ]),
  );

  const aadrgSection = makeSection('파생 AADRG', 'ADRG에서 파생되는 AADRG와 질병군 분류를 함께 확인합니다.');
  aadrgSection.append(makeSummaryList(detail.aadrg_records));
  fragment.append(aadrgSection, renderBasicTables(detail), renderConditionGroups(detail));
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
      ['질병군 분류', Ui.classificationLabel(detail.classification_code, detail.classification_display_label)],
      ['RDRG', `${Ui.formatNumber((detail.rdrg_codes ?? []).length)}개`],
    ]),
  );
  const parent = makeSection('상위 ADRG');
  parent.append(makeSummaryList(detail.parent_adrg ? [detail.parent_adrg] : []));
  const rdrg = makeSection('파생 RDRG', '중증도 분기를 포함한 최종 RDRG입니다.');
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
    ]),
  );
  const parents = makeSection('상위 분류 관계');
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
    ]),
  );

  const tables = makeSection('포함 TABLE', '원문 정의 위치·조건 AST 사용 관계·검색용 통합 관계를 구분합니다.');
  const stack = create('div', 'table-stack');
  for (const table of detail.logical_tables ?? []) {
    const summary = {
      entity_type: 'TABLE',
      entity_id: table.logical_table_id,
      title: table.display_name || table.logical_table_id,
      subtitle: `${Ui.roleLabel(table.logical_table_type)} · 관련 ADRG ${(table.related_adrgs ?? []).length}개`,
      summary: {
        logical_table_type: table.logical_table_type,
        related_adrgs: table.related_adrgs,
      },
    };
    const card = tableCard(summary);
    if ((table.runtime_contexts ?? []).length) {
      card.append(makeChip(`조건 사용 ${(table.runtime_contexts ?? []).length}건`, 'context-chip'));
    }
    stack.append(card);
  }
  if (!stack.childNodes.length) stack.append(create('p', 'muted', '연결된 TABLE이 없습니다.'));
  tables.append(stack);

  const adrgs = makeSection('관련 ADRG');
  adrgs.append(makeSummaryList(detail.related_adrg_summaries));
  const aadrgs = makeSection('관련 AADRG');
  aadrgs.append(makeSummaryList(detail.related_aadrg_summaries));
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
  const container = create('div', 'code-grid');
  const limit = 160;
  const rows = Array.isArray(records) ? records : [];
  for (const record of rows.slice(0, limit)) {
    container.append(makeEntityButton(record, 'code-link'));
  }
  if (!rows.length) container.append(create('p', 'muted', 'TABLE 코드가 없습니다.'));
  if (rows.length > limit) {
    container.append(create('p', 'list-limit-note', `화면 성능을 위해 처음 ${Ui.formatNumber(limit)}개만 표시합니다. 나머지 ${Ui.formatNumber(rows.length - limit)}개는 해당 코드로 검색해 확인할 수 있습니다.`));
  }
  return container;
}

function renderTableDetail(payload) {
  const detail = payload.detail;
  const fragment = document.createDocumentFragment();
  fragment.append(
    makeMetaGrid([
      ['TABLE ID', detail.logical_table_id],
      ['TABLE명', detail.display_name],
      ['코드 유형', Ui.roleLabel(detail.logical_table_type || detail.logical_table_scope)],
      ['코드 수', `${Ui.formatNumber(detail.code_count ?? (detail.codes ?? []).length)}개`],
      ['원문 정의 ADRG', Ui.summarizeList(detail.source_adrgs)],
      ['조건 AST ADRG', Ui.summarizeList(detail.condition_adrgs)],
      ['검색용 관련 ADRG', Ui.summarizeList(detail.related_adrgs)],
      ['원문 family 근거', Ui.summarizeList(detail.source_adrg_families)],
    ]),
  );
  const contexts = makeSection('조건 AST 사용 관계', '포함과 제외 polarity를 분리하여 표시합니다.');
  contexts.append(renderRuntimeContexts(detail.runtime_contexts));
  const codes = makeSection('TABLE 코드', '원천에 코드명이 없으면 임의로 생성하지 않습니다.');
  codes.append(renderCodeRecords(detail.code_records));
  const related = makeSection('관련 ADRG');
  related.append(makeSummaryList(detail.related_adrg_summaries));
  fragment.append(contexts, codes, related);
  return fragment;
}

function detailTitle(payload) {
  const detail = payload.detail ?? {};
  if (payload.entity_type === 'ADRG') return `${detail.adrg} · ${detail.adrg_name}`;
  if (payload.entity_type === 'AADRG') return `${detail.aadrg} · ${detail.group_name}`;
  if (payload.entity_type === 'RDRG') return `${detail.code} · ${detail.group_name}`;
  if (payload.entity_type === 'TABLE') return detail.display_name || detail.logical_table_id;
  return detail.code || payload.entity_id;
}

function renderDetail(payload) {
  const panel = byId('detail-content');
  panel.replaceChildren();
  const header = create('div', 'detail-primary');
  header.append(makeBadge(payload.entity_type));
  const copy = create('div');
  copy.append(
    create('h2', '', detailTitle(payload)),
    create('p', '', `${Ui.entityLabel(payload.entity_type)} 상세 · ID ${payload.entity_id}`),
  );
  header.append(copy);
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
    setStatus('error', '검색어를 입력해야 합니다.', '코드·ADRG·AADRG·RDRG·TABLE명 또는 질병군명을 입력하세요.');
    return;
  }
  const sequence = ++state.searchSequence;
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
      `${Ui.formatNumber(response.total_count)}건을 찾았습니다.`,
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
  byId('result-list').replaceChildren();
  byId('type-counts').replaceChildren();
  setText('result-count', '0건');
  setText('result-caption', '검색어를 입력하면 결과가 표시됩니다.');
  setText('page-label', '0–0 / 0');
  byId('page-previous').disabled = true;
  byId('page-next').disabled = true;
  clearDetail();
  setStatus('ready', '검색 준비가 완료됐습니다.', '코드·질병군명·ADRG·AADRG·RDRG·TABLE을 한 번에 검색할 수 있습니다.');
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

  document.addEventListener('click', (event) => {
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
  if (!window.KDRG || typeof window.KDRG.search !== 'function' || typeof window.KDRG.getDetail !== 'function') {
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
  resetSearch();
}

document.addEventListener('DOMContentLoaded', () => {
  initialize().catch((error) => {
    setStatus('error', 'Electron 검색 화면을 준비하지 못했습니다.', error?.message || '알 수 없는 오류');
    clearDetail(error?.message || '초기화 오류');
  });
});
