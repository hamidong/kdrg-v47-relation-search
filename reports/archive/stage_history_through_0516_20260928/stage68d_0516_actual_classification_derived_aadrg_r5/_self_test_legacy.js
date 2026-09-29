
'use strict';
function makeClassificationBadgeGroup(x) { return x; }
function renderRelationDetail(candidate, response) {
  const panel = byId('detail-content');
  panel.append(makeMetaGrid([
    ['ADRG', candidate.entity_id],
    ['질병군명', candidate.title],
    ['MDC', candidate.summary?.mdc ? `MDC ${candidate.summary.mdc}` : '-'],
    [
      '질병군 분류',
      makeClassificationBadgeGroup(
        candidate.summary?.abc_display_labels ?? [],
      ),
    ],
    ['연결 코드', `${candidate.matched_count}/${candidate.total_count}`],
  ], 'detail-overview-grid'));
}
function clearDetail() {}
function renderDerivedAadrgList(records) {
  for (const record of records) {
    const summary = record.summary ?? {};
    meta.append(makeChip(summary.classification_code || summary.classification_display_label));
  }
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
    ], 'detail-overview-grid'),
  );

  const aadrgSection = makeSection(
    '파생 AADRG',
    'ADRG에서 파생되는 AADRG와 질병군 분류를 함께 확인합니다.',
    { open: false, count: (detail.aadrg_records ?? []).length },
  );
  aadrgSection.append(renderDerivedAadrgList(detail.aadrg_records));

  fragment.append(
    aadrgSection,
    renderUserConditionSummary(detail),
    renderUserConditionTables(detail),
    renderUserConditionEvidence(detail),
  );
  return fragment;
}
function renderAadrgDetail(payload) {}
