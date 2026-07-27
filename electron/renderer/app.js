'use strict';

function setText(id, value) {
  const element = document.getElementById(id);
  if (element) {
    element.textContent = String(value);
  }
}

function formatNumber(value) {
  return Number(value).toLocaleString('ko-KR');
}

function shortHash(value) {
  return `${String(value).slice(0, 12)}…`;
}

function renderFileList(files) {
  const container = document.getElementById('file-list');
  container.replaceChildren();

  for (const file of Object.values(files)) {
    const row = document.createElement('div');
    row.className = 'file-row';

    const name = document.createElement('strong');
    name.textContent = file.fileName;

    const meta = document.createElement('span');
    meta.textContent = `${file.schema} · ${formatNumber(file.sizeBytes)} bytes · ${shortHash(file.sha256)}`;

    row.append(name, meta);
    container.append(row);
  }
}

function renderReady(snapshot) {
  document.body.dataset.state = 'ready';
  setText('status-title', 'Electron 기반과 통합 데이터 연결이 정상입니다.');
  setText(
    'status-detail',
    'SHA256와 schema가 확인됐으며, renderer에는 요약 정보만 전달됐습니다.',
  );
  setText('data-version', snapshot.dataVersion);
  setText('count-adrg', formatNumber(snapshot.counts.adrg));
  setText('count-aadrg', formatNumber(snapshot.counts.aadrg));
  setText('count-rdrg', formatNumber(snapshot.counts.rdrg));
  setText('count-tables', formatNumber(snapshot.counts.tables));
  setText('count-codes', formatNumber(snapshot.counts.codes));
  setText('count-ast', formatNumber(snapshot.counts.conditionAst));
  setText('count-occurrences', formatNumber(snapshot.counts.conditionTableOccurrences));
  setText('count-includes', formatNumber(snapshot.displayContract.includeOccurrences));
  setText('count-excludes', formatNumber(snapshot.displayContract.excludeOccurrences));
  setText('count-unknown', formatNumber(snapshot.displayContract.unknownTableCount));
  renderFileList(snapshot.files);
}

function renderError(error) {
  document.body.dataset.state = 'error';
  setText('status-title', 'Electron 기반 데이터 연결을 완료하지 못했습니다.');
  setText('status-detail', error?.message ?? '알 수 없는 오류');
}

async function initialize() {
  if (!window.KDRG || typeof window.KDRG.getBootstrapSnapshot !== 'function') {
    throw new Error('보안 preload bridge를 찾을 수 없습니다.');
  }

  const snapshot = await window.KDRG.getBootstrapSnapshot();
  if (!snapshot || snapshot.status !== 'ready') {
    throw new Error('통합 데이터 준비 상태가 올바르지 않습니다.');
  }
  renderReady(snapshot);
}

document.addEventListener('DOMContentLoaded', () => {
  initialize().catch(renderError);
});
