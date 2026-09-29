#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KDRG V4.7 Stage 52 Electron 실행화면 검증기 V1

검증 대상
- ADRG 9610: TABLE 번호 없는 직접 코드조건
- ADRG 9620: 포함 TABLE과 WITHOUT 제외 TABLE 분리
- ADRG O602: 기존 명시적 '주진단명 table2' 유지
- 인라인 TABLE: 코드/코드명 2열, 검색, 전체 행 복원, 내부 스크롤
- renderer 오류, load failure, renderer crash

제품 파일은 수정하지 않는다.
임시 Electron harness는 /tmp에 생성하고 실행 후 삭제한다.
Replit의 공유 라이브러리는 LD_LIBRARY_PATH에만 임시 연결하며 설치하지 않는다.
검증에는 확인된 Nix Electron 35.6.0 실행파일을 고정 사용한다.
이 결과는 Linux 소스 UI 검증이며 Windows Electron 43.2.0 최종검증을 대체하지 않는다.
인라인 TABLE은 open 속성 직접 변경이 아니라 실제 summary 클릭으로 펼친다.
각 ADRG 검증은 독립 실행하여 한 사례 실패가 다른 사례를 가리지 않게 한다.
검증 보고서와 캡처만 reports/electron_stage52_runtime_ui_preview_v1에 생성한다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import traceback
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
ELECTRON_ROOT = ROOT / "electron"
OPERATING_JSON = ROOT / "data" / "kdrg_v47_search_integrated_v3.json"
REPORT_DIR = ROOT / "reports" / "electron_stage52_runtime_ui_preview_nix_click_v1"
RESULT_JSON = REPORT_DIR / "preview_result.json"
SUMMARY_TXT = REPORT_DIR / "preview_summary.txt"

EXPECTED_HEAD = "3994508099651fa470bd53c8c52cebbb76152b5c"
EXPECTED_OPERATING_SHA256 = (
    "d865b8a421acb728b9cbc01ef3ba01036206bdc22b1877e70f938ead724e3dda"
)
NIX_ELECTRON_PATH = Path(
    "/nix/store/3j0s8gm1pnbbhxqr08v6b7hsrxyx5207-electron-35.6.0"
    "/bin/electron"
)
EXPECTED_RUNTIME_ELECTRON_VERSION = "v35.6.0"
EXPECTED_TRACKED = {
    "electron/renderer/app.js",
    "electron/renderer/styles.css",
    "electron/tests/validate-renderer-ui.js",
}

HARNESS_JS = r"""
'use strict';

const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');

const {
  app,
  BrowserWindow,
  ipcMain,
} = require('electron');

const WORKSPACE_ROOT = path.resolve(
  process.env.KDRG_WORKSPACE_ROOT || '/home/runner/workspace'
);
const ELECTRON_ROOT = path.join(WORKSPACE_ROOT, 'electron');
const REPORT_DIR = path.resolve(
  process.env.KDRG_STAGE52_REPORT_DIR
    || path.join(
      WORKSPACE_ROOT,
      'reports',
      'electron_stage52_runtime_ui_preview_nix_click_v1'
    )
);
const RESULT_JSON = path.join(REPORT_DIR, 'preview_result.json');
const SUMMARY_TXT = path.join(REPORT_DIR, 'preview_summary.txt');
const INDEX_HTML = path.join(REPORT_DIR, 'preview_index.html');
const HEADLESS = process.env.KDRG_STAGE52_HEADLESS !== '0';

const {
  buildBootstrapSnapshot,
} = require(path.join(ELECTRON_ROOT, 'src', 'bootstrap-data'));
const {
  resolveDataFiles,
} = require(path.join(ELECTRON_ROOT, 'src', 'data-paths'));
const {
  KdrgSearchService,
} = require(path.join(ELECTRON_ROOT, 'src', 'kdrg-search-service'));
const {
  normalizeSearchRequest,
  normalizeRelationRequest,
  normalizeDetailRequest,
} = require(path.join(ELECTRON_ROOT, 'src', 'search-result-contract'));
const Ui = require(
  path.join(ELECTRON_ROOT, 'renderer', 'ui-formatters')
);

const VERSION =
  '2026-08-06_KDRG_V47_STAGE52_NIX_CLICK_RUNTIME_UI_VALIDATOR_V1';

if (HEADLESS) {
  app.commandLine.appendSwitch('headless', 'new');
  app.commandLine.appendSwitch('ozone-platform', 'headless');
}
app.commandLine.appendSwitch('disable-gpu');
app.commandLine.appendSwitch('disable-dev-shm-usage');
app.commandLine.appendSwitch('force-device-scale-factor', '1');

fs.mkdirSync(REPORT_DIR, { recursive: true });

let bootstrapSnapshot = null;
let searchService = null;
let mainWindow = null;

const consoleErrors = [];
const rendererGone = [];
const loadFailures = [];

function sha256(buffer) {
  return crypto.createHash('sha256').update(buffer).digest('hex');
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function unique(values) {
  return [...new Set(
    (values || [])
      .map((value) => String(value || '').trim())
      .filter(Boolean)
  )];
}

function sameSet(actual, expected) {
  const left = [...new Set(actual || [])].sort();
  const right = [...new Set(expected || [])].sort();
  return JSON.stringify(left) === JSON.stringify(right);
}

function dataFiles() {
  return resolveDataFiles({
    isPackaged: false,
    resourcesPath: process.resourcesPath,
    moduleDirectory: path.join(ELECTRON_ROOT, 'src'),
  });
}

function bootstrap() {
  if (!bootstrapSnapshot) {
    bootstrapSnapshot = buildBootstrapSnapshot(dataFiles());
  }
  return bootstrapSnapshot;
}

function service() {
  if (!searchService) {
    searchService = new KdrgSearchService(dataFiles().integrated);
  }
  return searchService;
}

function registerIpc() {
  const channels = {
    bootstrap: 'kdrg:get-bootstrap-snapshot',
    searchStatus: 'kdrg:get-search-status',
    search: 'kdrg:search',
    relationSearch: 'kdrg:relation-search',
    detail: 'kdrg:get-detail',
  };

  for (const channel of Object.values(channels)) {
    ipcMain.removeHandler(channel);
  }

  ipcMain.handle(channels.bootstrap, async () => bootstrap());
  ipcMain.handle(channels.searchStatus, async () => service().status());
  ipcMain.handle(channels.search, async (_event, payload) => {
    const request = normalizeSearchRequest(payload);
    return service().search(request.query, request.entityType, {
      limit: request.limit,
      offset: request.offset,
      mdc: request.mdc,
      classification: request.classification,
    });
  });
  ipcMain.handle(channels.relationSearch, async (_event, payload) => {
    const request = normalizeRelationRequest(payload);
    return service().relationSearch(
      request.conditions,
      request.operator,
      {
        mdc: request.mdc,
        classification: request.classification,
      }
    );
  });
  ipcMain.handle(channels.detail, async (_event, payload) => {
    const request = normalizeDetailRequest(payload);
    return service().getDetail(
      request.entityType,
      request.entityId
    );
  });
}

async function execute(script) {
  return mainWindow.webContents.executeJavaScript(script, true);
}

async function waitFor(
  script,
  label,
  timeoutMs = 20000,
  intervalMs = 100
) {
  const started = Date.now();
  let lastValue = null;

  while (Date.now() - started < timeoutMs) {
    try {
      lastValue = await execute(script);
      if (lastValue) return lastValue;
    } catch (_error) {
      lastValue = null;
    }
    await delay(intervalMs);
  }

  throw new Error(
    `대기시간 초과: ${label} | last=${JSON.stringify(lastValue)}`
  );
}

function createWindow() {
  const window = new BrowserWindow({
    width: 1600,
    height: 980,
    minWidth: 1180,
    minHeight: 720,
    show: false,
    backgroundColor: '#f3f6fb',
    title: 'KDRG V4.7 Stage 52 Runtime UI Validation',
    webPreferences: {
      preload: path.join(ELECTRON_ROOT, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      devTools: false,
      spellcheck: false,
    },
  });

  window.webContents.setWindowOpenHandler(
    () => ({ action: 'deny' })
  );
  window.webContents.on(
    'will-navigate',
    (event) => event.preventDefault()
  );
  window.webContents.on(
    'console-message',
    (_event, level, message, line, sourceId) => {
      if (Number(level) >= 2) {
        consoleErrors.push({
          level,
          message,
          line,
          sourceId,
        });
      }
    }
  );
  window.webContents.on(
    'render-process-gone',
    (_event, details) => rendererGone.push(details)
  );
  window.webContents.on(
    'did-fail-load',
    (
      _event,
      errorCode,
      errorDescription,
      validatedURL,
      isMainFrame
    ) => {
      if (isMainFrame) {
        loadFailures.push({
          errorCode,
          errorDescription,
          validatedURL,
        });
      }
    }
  );

  return window;
}

async function initializeRenderer() {
  await mainWindow.loadFile(
    path.join(ELECTRON_ROOT, 'renderer', 'index.html')
  );

  await waitFor(
    `(() => {
      const input = document.querySelector('#search-query');
      const status = document.querySelector('#status-detail');
      return Boolean(
        document.readyState === 'complete'
        && input
        && !input.disabled
        && status
      );
    })()`,
    'renderer 초기화',
    30000
  );
}

async function getAdrgDetail(adrg) {
  const detail = await service().getDetail('ADRG', adrg);
  if (!detail || String(detail.entity_id || '') !== adrg) {
    throw new Error(`${adrg} ADRG detail을 불러오지 못했습니다.`);
  }
  return detail;
}

function groupTableIds(groups, field) {
  const result = [];
  for (const group of groups || []) {
    for (const leaf of group[field] || []) {
      result.push(...(leaf.table_ids || []));
    }
  }
  return unique(result);
}

async function buildFixture(adrg) {
  const detail = await getAdrgDetail(adrg);
  const coverage = Ui.userConditionCoverage(detail);
  const groups = Ui.buildConditionGroups(detail.condition_ast);

  if (adrg === '9610') {
    return {
      adrg,
      detail_status: coverage.status,
      expected_text: [
        '직접 코드 조건',
        '주진단명 코드가 아래 목록에 포함',
        '코드 목록',
        '내부 ID LT_9610_001',
      ],
      forbidden_text: [
        '명시적 조건 없음',
        '제외 조건 · WITHOUT',
      ],
      expected_table_ids: ['LT_9610_001'],
      expected_include_ids: [],
      expected_exclude_ids: [],
      direct_condition: true,
      expected_condition_text: '',
    };
  }

  if (adrg === '9620') {
    const includeIds = groupTableIds(groups, 'includes');
    const excludeIds = groupTableIds(groups, 'excludes');

    return {
      adrg,
      detail_status: coverage.status,
      expected_text: [
        '주진단명 table1',
        '시술명 table2',
        '제외 조건 · WITHOUT',
        '아래 TABLE에 해당하면 이 ADRG에서 제외됩니다.',
      ],
      forbidden_text: ['직접 코드 조건'],
      expected_table_ids: unique([...includeIds, ...excludeIds]),
      expected_include_ids: includeIds,
      expected_exclude_ids: excludeIds,
      direct_condition: false,
      expected_condition_text: detail.user_condition_text || '',
    };
  }

  if (adrg === 'O602') {
    return {
      adrg,
      detail_status: coverage.status,
      expected_text: [
        '주진단명 table2',
        '조건 TABLE 연결 완료',
      ],
      forbidden_text: [
        '직접 코드 조건',
        '제외 조건 · WITHOUT',
        '명시적 조건 없음',
      ],
      expected_table_ids: unique(coverage.table_ids),
      expected_include_ids: unique(coverage.table_ids),
      expected_exclude_ids: [],
      direct_condition: false,
      expected_condition_text: detail.user_condition_text || '',
    };
  }

  throw new Error(`정의되지 않은 ADRG fixture: ${adrg}`);
}

async function runSearch(adrg) {
  const encoded = JSON.stringify(adrg);

  await execute(
    `(() => {
      const input = document.querySelector('#search-query');
      const type = document.querySelector('#filter-type');
      const form = document.querySelector('#search-form');

      input.value = ${encoded};
      type.value = 'ADRG';
      type.dispatchEvent(
        new Event('change', { bubbles: true })
      );
      form.dispatchEvent(
        new Event('submit', {
          bubbles: true,
          cancelable: true,
        })
      );
      return true;
    })()`
  );

  await waitFor(
    `(() => {
      const panel = document.querySelector('#detail-content');
      const caption = document.querySelector('#detail-caption');
      return Boolean(
        panel
        && panel.textContent.includes(${encoded})
        && caption
        && !caption.textContent.includes('불러오는 중')
      );
    })()`,
    `${adrg} 상세 로드`,
    30000
  );
}

async function inspectInitial(fixture) {
  const fixtureJson = JSON.stringify(fixture);

  return execute(
    `(() => {
      const fixture = ${fixtureJson};
      const panel = document.querySelector('#detail-content');
      const panelText = panel?.textContent || '';
      const cards = [
        ...panel.querySelectorAll(
          'details[data-inline-table-id]'
        ),
      ];

      return {
        panel_text: panelText.replace(/\\s+/g, ' ').trim(),
        expected_text_presence: Object.fromEntries(
          fixture.expected_text.map(
            (text) => [text, panelText.includes(text)]
          )
        ),
        forbidden_text_presence: Object.fromEntries(
          fixture.forbidden_text.map(
            (text) => [text, panelText.includes(text)]
          )
        ),
        table_ids: cards.map(
          (card) => card.dataset.inlineTableId
        ),
        exclusion_table_ids: cards
          .filter(
            (card) => card.classList.contains(
              'table-card-exclusion'
            )
          )
          .map((card) => card.dataset.inlineTableId),
        direct_text_count: panel.querySelectorAll(
          '.direct-condition-text'
        ).length,
        include_block_count: panel.querySelectorAll(
          '.condition-include-block'
        ).length,
        exclude_block_count: panel.querySelectorAll(
          '.condition-exclude-block'
        ).length,
        without_operator_count: panel.querySelectorAll(
          '.condition-operator-without'
        ).length,
      };
    })()`
  );
}

async function expandAndInspectTables(expectedCount) {
  await execute(
    `(() => {
      for (const section of document.querySelectorAll(
        '#detail-content details.detail-section'
      )) {
        section.open = true;
      }
      return true;
    })()`
  );

  const actualCount = await execute(
    `(() => document.querySelectorAll(
      '#detail-content details[data-inline-table-id]'
    ).length)()`
  );

  for (let index = 0; index < actualCount; index += 1) {
    await execute(
      `(() => {
        const cards = [
          ...document.querySelectorAll(
            '#detail-content details[data-inline-table-id]'
          ),
        ];
        const card = cards[${index}];
        if (!card) return false;

        const summary = card.querySelector(
          ':scope > summary'
        );
        if (!summary) return false;

        if (!card.open) {
          summary.click();
        } else if (
          card.dataset.loaded !== 'true'
          && card.dataset.loading !== 'true'
        ) {
          card.open = false;
          summary.click();
        }
        return true;
      })()`
    );

    await waitFor(
      `(() => {
        const cards = [
          ...document.querySelectorAll(
            '#detail-content details[data-inline-table-id]'
          ),
        ];
        const card = cards[${index}];
        if (!card) return false;

        const error = card.querySelector(
          '.inline-table-content .error-message'
        );
        return card.dataset.loaded === 'true'
          || Boolean(error);
      })()`,
      `인라인 TABLE ${index + 1}/${actualCount} 사용자 클릭 로드`,
      30000
    );
  }

  return execute(
    `(() => {
      const cards = [
        ...document.querySelectorAll(
          '#detail-content details[data-inline-table-id]'
        ),
      ];

      return cards.map((card) => {
        const tableId = card.dataset.inlineTableId || '';
        const search = card.querySelector(
          'input.inline-code-search'
        );
        const table = card.querySelector(
          'table.inline-code-table'
        );
        const headers = table
          ? [...table.querySelectorAll('thead th')]
              .map((cell) => cell.textContent.trim())
          : [];
        const rowsBefore = table
          ? table.querySelectorAll(
              'tbody tr.inline-code-row'
            ).length
          : 0;
        const firstCode = table?.querySelector(
          'tbody tr.inline-code-row td.inline-code-value'
        )?.textContent?.trim() || '';
        const resultBefore = card.querySelector(
          '.inline-code-result-count'
        )?.textContent?.trim() || '';
        const errorText = card.querySelector(
          '.inline-table-content .error-message'
        )?.textContent?.trim() || '';
        const contentText = card.querySelector(
          '.inline-table-content'
        )?.textContent?.replace(/\s+/g, ' ').trim() || '';

        let rowsFiltered = rowsBefore;
        let rowsRestored = rowsBefore;
        let resultFiltered = resultBefore;

        if (search && firstCode) {
          search.value = firstCode;
          search.dispatchEvent(
            new Event('input', { bubbles: true })
          );
          rowsFiltered = table.querySelectorAll(
            'tbody tr.inline-code-row'
          ).length;
          resultFiltered = card.querySelector(
            '.inline-code-result-count'
          )?.textContent?.trim() || '';

          search.value = '';
          search.dispatchEvent(
            new Event('input', { bubbles: true })
          );
          rowsRestored = table.querySelectorAll(
            'tbody tr.inline-code-row'
          ).length;
        }

        const firstHeader = table?.querySelector(
          'thead th'
        );
        const viewport = card.querySelector(
          '.inline-code-table-viewport'
        );
        const headerStyle = firstHeader
          ? getComputedStyle(firstHeader)
          : null;
        const viewportStyle = viewport
          ? getComputedStyle(viewport)
          : null;

        return {
          table_id: tableId,
          open: card.open,
          loaded: card.dataset.loaded === 'true',
          loading: card.dataset.loading === 'true',
          error_text: errorText,
          content_text: contentText,
          exclusion: card.classList.contains(
            'table-card-exclusion'
          ),
          search_present: Boolean(search),
          table_present: Boolean(table),
          headers,
          rows_before: rowsBefore,
          first_code: firstCode,
          rows_filtered: rowsFiltered,
          rows_restored: rowsRestored,
          result_before: resultBefore,
          result_filtered: resultFiltered,
          sticky_header: Boolean(
            headerStyle
            && headerStyle.position === 'sticky'
          ),
          viewport_scroll: Boolean(
            viewportStyle
            && ['auto', 'scroll'].includes(
              viewportStyle.overflowY
            )
          ),
        };
      });
    })()`
  );
}


async function captureCase(adrg) {
  await delay(300);
  const image = await mainWindow.webContents.capturePage();

  if (!image || image.isEmpty()) {
    throw new Error(`${adrg} 화면 캡처가 비어 있습니다.`);
  }

  const png = image.toPNG();
  const filename = `${adrg}.png`;
  const filePath = path.join(REPORT_DIR, filename);
  fs.writeFileSync(filePath, png);

  const size = image.getSize();
  return {
    filename,
    path: filePath,
    width: size.width,
    height: size.height,
    size_bytes: png.length,
    sha256: sha256(png),
    non_blank: (
      size.width >= 1180
      && size.height >= 720
      && png.length >= 15000
    ),
  };
}

function buildChecks(
  fixture,
  initial,
  tables,
  screenshot
) {
  const checks = [];
  const add = (
    name,
    passed,
    actual,
    expected,
    severity = 'core'
  ) => {
    checks.push({
      name,
      passed: Boolean(passed),
      actual,
      expected,
      severity,
    });
  };

  add(
    'expected_text',
    Object.values(
      initial.expected_text_presence
    ).every(Boolean),
    initial.expected_text_presence,
    'all true'
  );
  add(
    'forbidden_text_absent',
    Object.values(
      initial.forbidden_text_presence
    ).every((value) => !value),
    initial.forbidden_text_presence,
    'all false'
  );
  add(
    'table_ids',
    sameSet(
      initial.table_ids,
      fixture.expected_table_ids
    ),
    initial.table_ids,
    fixture.expected_table_ids
  );
  add(
    'expected_table_count_positive',
    fixture.expected_table_ids.length > 0,
    fixture.expected_table_ids.length,
    '> 0'
  );
  add(
    'exclude_table_ids',
    sameSet(
      initial.exclusion_table_ids,
      fixture.expected_exclude_ids
    ),
    initial.exclusion_table_ids,
    fixture.expected_exclude_ids
  );

  if (fixture.adrg === '9610') {
    add(
      'direct_condition_rendered',
      initial.direct_text_count >= 1,
      initial.direct_text_count,
      '>= 1'
    );
    add(
      '9610_exact_source_table',
      sameSet(
        fixture.expected_table_ids,
        ['LT_9610_001']
      ),
      fixture.expected_table_ids,
      ['LT_9610_001']
    );
  }

  if (fixture.adrg === '9620') {
    add(
      '9620_exact_include_table',
      sameSet(
        fixture.expected_include_ids,
        ['LT_9620_001']
      ),
      fixture.expected_include_ids,
      ['LT_9620_001']
    );
    add(
      '9620_exact_exclude_table',
      sameSet(
        fixture.expected_exclude_ids,
        ['LT_9620_002']
      ),
      fixture.expected_exclude_ids,
      ['LT_9620_002']
    );
    add(
      'include_block_rendered',
      initial.include_block_count >= 1,
      initial.include_block_count,
      '>= 1'
    );
    add(
      'exclude_block_rendered',
      initial.exclude_block_count >= 1,
      initial.exclude_block_count,
      '>= 1'
    );
  }

  if (fixture.adrg === 'O602') {
    add(
      'O602_not_direct_condition',
      initial.direct_text_count === 0,
      initial.direct_text_count,
      0
    );
    add(
      'O602_not_without',
      initial.exclude_block_count === 0,
      initial.exclude_block_count,
      0
    );
  }

  add(
    'all_tables_no_error_message',
    tables.length === fixture.expected_table_ids.length
      && tables.every((item) => !item.error_text),
    tables.map(
      (item) => ({
        table_id: item.table_id,
        error_text: item.error_text,
        content_text: item.content_text,
      })
    ),
    'all error_text empty'
  );
  add(
    'all_tables_opened_by_summary_click',
    tables.length === fixture.expected_table_ids.length
      && tables.every((item) => item.open),
    tables.map(
      (item) => ({
        table_id: item.table_id,
        open: item.open,
      })
    ),
    'all true'
  );
  add(
    'all_tables_loaded',
    tables.length === fixture.expected_table_ids.length
      && tables.every((item) => item.loaded),
    tables.map(
      (item) => ({
        table_id: item.table_id,
        loaded: item.loaded,
      })
    ),
    `${fixture.expected_table_ids.length} loaded`
  );
  add(
    'all_tables_have_code_rows',
    tables.every((item) => item.rows_before > 0),
    tables.map(
      (item) => ({
        table_id: item.table_id,
        rows: item.rows_before,
      })
    ),
    'all > 0'
  );
  add(
    'two_column_headers',
    tables.every(
      (item) => JSON.stringify(item.headers)
        === JSON.stringify(['코드', '코드명'])
    ),
    tables.map(
      (item) => ({
        table_id: item.table_id,
        headers: item.headers,
      })
    ),
    ['코드', '코드명']
  );
  add(
    'search_inputs_present',
    tables.every((item) => item.search_present),
    tables.map(
      (item) => ({
        table_id: item.table_id,
        search_present: item.search_present,
      })
    ),
    'all true'
  );
  add(
    'search_filters_rows',
    tables.every(
      (item) => (
        item.rows_filtered >= 1
        && item.rows_filtered <= item.rows_before
      )
    ),
    tables.map(
      (item) => ({
        table_id: item.table_id,
        before: item.rows_before,
        filtered: item.rows_filtered,
        first_code: item.first_code,
      })
    ),
    '1 <= filtered <= before'
  );
  add(
    'search_clear_restores_all_rows',
    tables.every(
      (item) => item.rows_restored === item.rows_before
    ),
    tables.map(
      (item) => ({
        table_id: item.table_id,
        before: item.rows_before,
        restored: item.rows_restored,
      })
    ),
    'restored === before'
  );
  add(
    'sticky_headers',
    tables.every((item) => item.sticky_header),
    tables.map(
      (item) => ({
        table_id: item.table_id,
        sticky: item.sticky_header,
      })
    ),
    'all true'
  );
  add(
    'internal_scroll',
    tables.every((item) => item.viewport_scroll),
    tables.map(
      (item) => ({
        table_id: item.table_id,
        scroll: item.viewport_scroll,
      })
    ),
    'all true'
  );
  add(
    'screenshot_non_blank',
    screenshot.non_blank,
    {
      width: screenshot.width,
      height: screenshot.height,
      size_bytes: screenshot.size_bytes,
    },
    'non-blank',
    'warning'
  );

  return checks;
}

function caseStatus(checks) {
  return checks
    .filter((check) => check.severity === 'core')
    .every((check) => check.passed)
    ? 'PASS'
    : 'FAIL';
}

function writeSummary(result) {
  const lines = [
    'KDRG V4.7 Stage 52 Electron 실행화면 검증 결과 V1',
    '='.repeat(84),
    `validator=${result.validator}`,
    `runtime_electron_version=${result.runtime_electron_version}`,
    `runtime_node_version=${result.runtime_node_version}`,
    `status=${result.status}`,
    `core_pass=${result.core_pass}`,
    `core_fail=${result.core_fail}`,
    `warning_pass=${result.warning_pass}`,
    `warning_fail=${result.warning_fail}`,
    `screenshots=${result.cases.length}`,
    '',
  ];

  for (const item of result.cases) {
    lines.push(`[${item.adrg}] ${item.status}`);
    lines.push(
      `- tables=${(
        item.initial?.table_ids || []
      ).join(',')}`
    );
    lines.push(
      `- exclusion_tables=${(
        item.initial?.exclusion_table_ids || []
      ).join(',')}`
    );
    lines.push(
      `- rows=${(item.tables || []).map(
        (table) => (
          `${table.table_id}:${table.rows_before}`
        )
      ).join(',')}`
    );

    if (item.case_error) {
      lines.push(
        `- case_error=${item.case_error.message}`
      );
    }

    for (const table of item.tables || []) {
      if (table.error_text) {
        lines.push(
          `- table_error ${table.table_id}: `
          + table.error_text
        );
      }
    }

    for (const check of item.checks) {
      lines.push(
        `- ${check.passed ? 'PASS' : 'FAIL'} `
        + `[${check.severity}] ${check.name}`
      );
    }
    lines.push('');
  }

  if (result.console_errors.length) {
    lines.push('[renderer console errors]');
    for (const item of result.console_errors) {
      lines.push(
        `- level=${item.level} message=${item.message}`
      );
    }
  }

  if (result.load_failures.length) {
    lines.push('[load failures]');
    for (const item of result.load_failures) {
      lines.push(
        `- ${item.errorCode} ${item.errorDescription}`
      );
    }
  }

  fs.writeFileSync(
    SUMMARY_TXT,
    lines.join('\n') + '\n',
    'utf8'
  );
}

function writeHtml(result) {
  const cards = result.cases.map(
    (item) => `
      <section>
        <h2>${item.adrg} · ${item.status}</h2>
        ${item.screenshot
          ? `<img src="${item.screenshot.filename}"
                  alt="${item.adrg} 실행화면">`
          : '<p>화면 캡처 없음</p>'}
        <pre>${JSON.stringify(
          item.checks,
          null,
          2
        )}</pre>
      </section>
    `
  ).join('\n');

  const html = `<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>KDRG Stage 52 Runtime UI Validation</title>
<style>
body { font-family: sans-serif; margin: 24px; background: #f5f7fb; }
section { background: white; margin: 0 0 24px; padding: 18px; border-radius: 12px; }
img { max-width: 100%; border: 1px solid #ccd5df; }
pre { white-space: pre-wrap; font-size: 12px; }
</style>
</head>
<body>
<h1>KDRG Stage 52 Runtime UI Validation</h1>
<p>status=${result.status}</p>
${cards}
</body>
</html>`;

  fs.writeFileSync(INDEX_HTML, html, 'utf8');
}

async function run() {
  const result = {
    validator: VERSION,
    runtime_electron_version: process.versions.electron || '',
    runtime_node_version: process.versions.node || '',
    status: 'FAIL',
    cases: [],
    console_errors: consoleErrors,
    renderer_gone: rendererGone,
    load_failures: loadFailures,
    global_checks: [],
    core_pass: 0,
    core_fail: 0,
    warning_pass: 0,
    warning_fail: 0,
  };

  try {
    registerIpc();
    mainWindow = createWindow();
    await initializeRenderer();

    for (const adrg of ['9610', '9620', 'O602']) {
      try {
        const fixture = await buildFixture(adrg);
        await runSearch(adrg);
        const initial = await inspectInitial(fixture);
        const tables = await expandAndInspectTables(
          fixture.expected_table_ids.length
        );
        const screenshot = await captureCase(adrg);
        const checks = buildChecks(
          fixture,
          initial,
          tables,
          screenshot
        );

        result.cases.push({
          adrg,
          status: caseStatus(checks),
          fixture,
          initial,
          tables,
          screenshot,
          checks,
        });
      } catch (error) {
        let screenshot = null;
        try {
          screenshot = await captureCase(
            `${adrg}_ERROR`
          );
        } catch (_captureError) {
          screenshot = null;
        }

        result.cases.push({
          adrg,
          status: 'FAIL',
          fixture: null,
          initial: null,
          tables: [],
          screenshot,
          case_error: {
            name: error?.name || 'Error',
            message: error?.message || String(error),
            stack: error?.stack || '',
          },
          checks: [
            {
              name: 'case_execution_completed',
              passed: false,
              actual: error?.message || String(error),
              expected: 'completed',
              severity: 'core',
            },
          ],
        });
      }
    }

    const hashes = result.cases
      .map((item) => item.screenshot?.sha256)
      .filter(Boolean);

    result.global_checks = [
      {
        name: 'console_errors_absent',
        passed: consoleErrors.length === 0,
        actual: consoleErrors.length,
        expected: 0,
        severity: 'core',
      },
      {
        name: 'renderer_crash_absent',
        passed: rendererGone.length === 0,
        actual: rendererGone.length,
        expected: 0,
        severity: 'core',
      },
      {
        name: 'load_failures_absent',
        passed: loadFailures.length === 0,
        actual: loadFailures.length,
        expected: 0,
        severity: 'core',
      },
      {
        name: 'screenshots_distinct',
        passed: (
          hashes.length === result.cases.length
          && new Set(hashes).size === hashes.length
        ),
        actual: new Set(hashes).size,
        expected: result.cases.length,
        severity: 'warning',
      },
      {
        name: 'runtime_electron_version',
        passed: result.runtime_electron_version === '35.6.0',
        actual: result.runtime_electron_version,
        expected: '35.6.0',
        severity: 'warning',
      },
    ];

    const allChecks = [
      ...result.cases.flatMap((item) => item.checks),
      ...result.global_checks,
    ];

    result.core_pass = allChecks.filter(
      (check) => (
        check.severity === 'core'
        && check.passed
      )
    ).length;
    result.core_fail = allChecks.filter(
      (check) => (
        check.severity === 'core'
        && !check.passed
      )
    ).length;
    result.warning_pass = allChecks.filter(
      (check) => (
        check.severity === 'warning'
        && check.passed
      )
    ).length;
    result.warning_fail = allChecks.filter(
      (check) => (
        check.severity === 'warning'
        && !check.passed
      )
    ).length;
    result.status = result.core_fail === 0
      ? 'PASS'
      : 'FAIL';
  } catch (error) {
    result.fatal_error = {
      name: error?.name || 'Error',
      message: error?.message || String(error),
      stack: error?.stack || '',
    };
    result.status = 'FAIL';
  }

  fs.writeFileSync(
    RESULT_JSON,
    JSON.stringify(result, null, 2) + '\n',
    'utf8'
  );
  writeSummary(result);
  writeHtml(result);

  if (result.status !== 'PASS') {
    console.error(
      `[FAIL] Stage 52 실행화면 검증: `
      + `${result.core_pass} PASS / `
      + `${result.core_fail} FAIL`
    );
    if (result.fatal_error) {
      console.error(result.fatal_error.stack);
    }
    process.exitCode = 1;
    return;
  }

  console.log(
    `[PASS] Stage 52 실행화면 검증: `
    + `${result.core_pass} PASS / 0 FAIL`
  );
  console.log(
    `warning=${result.warning_pass} PASS / `
    + `${result.warning_fail} FAIL`
  );
  console.log(`report=${RESULT_JSON}`);
  console.log(`summary=${SUMMARY_TXT}`);
}

app.whenReady()
  .then(run)
  .catch((error) => {
    console.error(error?.stack || String(error));
    process.exitCode = 1;
  })
  .finally(() => {
    setTimeout(
      () => app.exit(process.exitCode || 0),
      80
    );
  });
"""


class ValidationError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_command(
    args: list[str],
    *,
    cwd: Path = ROOT,
    env: dict[str, str] | None = None,
    timeout: int = 240,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=cwd,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if check and result.returncode != 0:
        raise ValidationError(
            f"명령 실패({result.returncode}): {' '.join(args)}\n"
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}"
        )
    return result


def tracked_files() -> list[str]:
    result = run_command(
        ["git", "diff", "--name-only"],
        check=True,
    )
    return [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip()
    ]


def tracked_hashes() -> dict[str, str]:
    return {
        relative: sha256_file(ROOT / relative)
        for relative in sorted(EXPECTED_TRACKED)
    }


def find_electron() -> Path:
    if not NIX_ELECTRON_PATH.is_file():
        raise ValidationError(
            "고정 Nix Electron 실행파일이 없습니다: "
            f"{NIX_ELECTRON_PATH}"
        )
    return NIX_ELECTRON_PATH


MISSING_LDD_RE = re.compile(
    r"^\s*(\S+)\s+=>\s+not found\s*$"
)
RUNTIME_MISSING_RE = re.compile(
    r"error while loading shared libraries:\s*"
    r"([^:\s]+)"
)


def parse_missing_libraries(value: str) -> list[str]:
    output = []
    for line in str(value or "").splitlines():
        match = MISSING_LDD_RE.match(line)
        if match:
            output.append(match.group(1))
    return sorted(set(output))


def parse_runtime_missing_library(value: str) -> str:
    match = RUNTIME_MISSING_RE.search(str(value or ""))
    return match.group(1) if match else ""


def ldd_missing(
    electron: Path,
    env: dict[str, str],
) -> tuple[list[str], str]:
    ldd = shutil.which("ldd")
    if not ldd:
        return [], "ldd 명령 없음"

    result = run_command(
        [ldd, str(electron)],
        cwd=ELECTRON_ROOT,
        env=env,
        timeout=45,
        check=False,
    )
    combined = "\n".join(
        value
        for value in (result.stdout, result.stderr)
        if value
    )
    return parse_missing_libraries(combined), combined


def library_package_hints(name: str) -> tuple[str, ...]:
    mapping = {
        "libnspr4.so": ("nspr",),
        "libnss3.so": ("nss",),
        "libnssutil3.so": ("nss",),
        "libsmime3.so": ("nss",),
        "libplc4.so": ("nspr",),
        "libplds4.so": ("nspr",),
        "libatk-1.0.so.0": ("atk",),
        "libatk-bridge-2.0.so.0": ("at-spi2-atk",),
        "libatspi.so.0": ("at-spi2-core",),
        "libcups.so.2": ("cups",),
        "libdrm.so.2": ("libdrm",),
        "libdbus-1.so.3": ("dbus",),
        "libxkbcommon.so.0": ("libxkbcommon",),
        "libgbm.so.1": ("mesa", "libgbm"),
        "libX11.so.6": ("libx11",),
        "libXcomposite.so.1": ("libxcomposite",),
        "libXdamage.so.1": ("libxdamage",),
        "libXext.so.6": ("libxext",),
        "libXfixes.so.3": ("libxfixes",),
        "libXrandr.so.2": ("libxrandr",),
        "libxcb.so.1": ("libxcb",),
        "libpango-1.0.so.0": ("pango",),
        "libpangocairo-1.0.so.0": ("pango",),
        "libcairo.so.2": ("cairo",),
        "libasound.so.2": ("alsa-lib",),
    }
    return mapping.get(name, ())


_NIX_STORE_ENTRY_CACHE: list[Path] | None = None
_LIBRARY_CANDIDATE_CACHE: dict[str, list[Path]] = {}


def nix_store_entries() -> list[Path]:
    global _NIX_STORE_ENTRY_CACHE

    if _NIX_STORE_ENTRY_CACHE is not None:
        return _NIX_STORE_ENTRY_CACHE

    store = Path("/nix/store")
    entries: list[Path] = []

    if not store.is_dir():
        _NIX_STORE_ENTRY_CACHE = entries
        return entries

    started = time.monotonic()
    try:
        with os.scandir(store) as iterator:
            for index, item in enumerate(iterator, start=1):
                if item.is_dir(follow_symlinks=False):
                    entries.append(Path(item.path))
                if index >= 100000:
                    break
                if time.monotonic() - started >= 12:
                    break
    except OSError:
        entries = []

    _NIX_STORE_ENTRY_CACHE = entries
    return entries


def ldconfig_library_candidates(name: str) -> list[Path]:
    ldconfig = shutil.which("ldconfig")
    if not ldconfig:
        return []

    try:
        result = run_command(
            [ldconfig, "-p"],
            cwd=ROOT,
            timeout=12,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return []

    pattern = re.compile(
        rf"^\s*{re.escape(name)}\s+.*=>\s+(\S+)\s*$"
    )
    output: list[Path] = []

    for line in result.stdout.splitlines():
        match = pattern.match(line)
        if not match:
            continue
        candidate = Path(match.group(1))
        if candidate.exists():
            output.append(candidate)

    return output


def direct_library_candidates(name: str) -> list[Path]:
    directories = [
        Path(value)
        for value in os.environ.get(
            "LD_LIBRARY_PATH", ""
        ).split(":")
        if value
    ]
    directories += [
        Path("/usr/lib"),
        Path("/usr/lib64"),
        Path("/usr/lib/x86_64-linux-gnu"),
        Path("/lib"),
        Path("/lib64"),
        Path("/lib/x86_64-linux-gnu"),
        Path("/usr/local/lib"),
        Path("/opt/lib"),
    ]

    output: list[Path] = []
    for directory in directories:
        candidate = directory / name
        if candidate.exists():
            output.append(candidate)

        if directory.is_dir():
            try:
                output.extend(
                    path
                    for path in directory.glob(f"{name}*")
                    if path.exists()
                )
            except OSError:
                continue

    return output


def nix_library_candidates(name: str) -> list[Path]:
    entries = nix_store_entries()
    if not entries:
        return []

    hints = tuple(
        hint.casefold()
        for hint in library_package_hints(name)
    )
    preferred: list[Path] = []
    fallback: list[Path] = []

    for entry in entries:
        entry_name = entry.name.casefold()
        is_preferred = bool(
            hints
            and any(hint in entry_name for hint in hints)
        )

        # 우선 패키지 이름이 맞는 경로만 검사한다.
        # 패키지 힌트가 없는 경우에는 정확한 lib 위치만 제한적으로 검사한다.
        if hints and not is_preferred:
            continue

        for subdir in ("lib", "lib64"):
            directory = entry / subdir
            candidate = directory / name
            if candidate.exists():
                preferred.append(candidate)
                continue

            if is_preferred and directory.is_dir():
                try:
                    matches = [
                        path
                        for path in directory.glob(f"{name}*")
                        if path.exists()
                    ]
                except OSError:
                    matches = []
                preferred.extend(matches)

    # 이름 힌트에 맞는 패키지를 찾지 못했을 때만
    # Nix store 최상위 항목의 정확한 lib 경로를 한 번 더 확인한다.
    if not preferred:
        started = time.monotonic()
        for entry in entries:
            for subdir in ("lib", "lib64"):
                candidate = entry / subdir / name
                if candidate.exists():
                    fallback.append(candidate)
            if time.monotonic() - started >= 8:
                break

    return preferred or fallback


def find_library_candidates(name: str) -> list[Path]:
    cached = _LIBRARY_CANDIDATE_CACHE.get(name)
    if cached is not None:
        return list(cached)

    candidates: list[Path] = []
    candidates.extend(ldconfig_library_candidates(name))
    candidates.extend(direct_library_candidates(name))
    candidates.extend(nix_library_candidates(name))

    hints = library_package_hints(name)

    def score(candidate: Path) -> tuple[int, int, int, str]:
        value = str(candidate).casefold()
        hint_score = sum(
            1
            for hint in hints
            if hint.casefold() in value
        )
        exact_score = (
            1
            if candidate.name == name
            else 0
        )
        nix_score = (
            1
            if value.startswith("/nix/store/")
            else 0
        )
        return (
            -exact_score,
            -hint_score,
            -nix_score,
            value,
        )

    result = sorted(
        {
            candidate.resolve()
            for candidate in candidates
            if candidate.exists()
        },
        key=score,
    )
    _LIBRARY_CANDIDATE_CACHE[name] = result
    return list(result)


def append_library_directory(
    env: dict[str, str],
    directory: Path,
) -> bool:
    current = [
        value
        for value in env.get("LD_LIBRARY_PATH", "").split(":")
        if value
    ]
    value = str(directory)
    if value in current:
        return False
    env["LD_LIBRARY_PATH"] = ":".join([value, *current])
    return True


def prepare_electron_environment(
    electron: Path,
) -> tuple[dict[str, str], dict[str, Any]]:
    env = os.environ.copy()
    diagnostics: dict[str, Any] = {
        "electron": str(electron),
        "initial_missing": [],
        "resolved": {},
        "remaining_missing": [],
        "ld_library_path_additions": [],
        "ldd_output": "",
        "library_scan_mode": (
            "ldconfig + common directories + "
            "bounded /nix/store package scan"
        ),
    }

    additions: list[str] = []
    initial_missing: list[str] | None = None

    for _round in range(8):
        missing, ldd_output = ldd_missing(electron, env)
        diagnostics["ldd_output"] = ldd_output
        if initial_missing is None:
            initial_missing = list(missing)
        if not missing:
            diagnostics["initial_missing"] = initial_missing or []
            diagnostics["remaining_missing"] = []
            diagnostics["ld_library_path_additions"] = additions
            return env, diagnostics

        progress = False
        for library in missing:
            candidates = find_library_candidates(library)
            if not candidates:
                continue
            selected = candidates[0]
            if append_library_directory(env, selected.parent):
                additions.append(str(selected.parent))
                diagnostics["resolved"][library] = str(selected)
                progress = True

        if not progress:
            diagnostics["initial_missing"] = initial_missing or []
            diagnostics["remaining_missing"] = missing
            diagnostics["ld_library_path_additions"] = additions
            return env, diagnostics

    remaining, ldd_output = ldd_missing(electron, env)
    diagnostics["initial_missing"] = initial_missing or []
    diagnostics["remaining_missing"] = remaining
    diagnostics["ld_library_path_additions"] = additions
    diagnostics["ldd_output"] = ldd_output
    return env, diagnostics


def write_environment_failure_report(
    *,
    reason: str,
    diagnostics: dict[str, Any],
    stdout: str = "",
    stderr: str = "",
) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "validator": (
            "2026-08-06_KDRG_V47_STAGE52_"
            "RUNTIME_UI_VALIDATOR_V1"
        ),
        "status": "FAIL",
        "failure_type": "ENVIRONMENT_SHARED_LIBRARY",
        "reason": reason,
        "core_pass": 0,
        "core_fail": 1,
        "warning_pass": 0,
        "warning_fail": 0,
        "cases": [],
        "environment": diagnostics,
        "process_stdout": stdout,
        "process_stderr": stderr,
    }
    RESULT_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
        newline="\n",
    )

    lines = [
        "KDRG V4.7 Stage 52 Electron 실행화면 검증 결과 V1",
        "=" * 84,
        "status=FAIL",
        "failure_type=ENVIRONMENT_SHARED_LIBRARY",
        f"reason={reason}",
        "제품 소스 오류가 아니라 Replit 실행환경의 공유 라이브러리 문제",
        "",
        "[공유 라이브러리]",
        "initial_missing="
        + ",".join(diagnostics.get("initial_missing") or []),
        "remaining_missing="
        + ",".join(diagnostics.get("remaining_missing") or []),
        "ld_library_path_additions="
        + ",".join(
            diagnostics.get("ld_library_path_additions") or []
        ),
        "",
        "[안전 확인]",
        "제품 추적 파일 수정 없음",
        "운영 JSON 수정 없음",
    ]
    if stderr:
        lines += ["", "[stderr]", stderr.strip()]
    SUMMARY_TXT.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def self_test() -> int:
    failures: list[str] = []

    def check(title: str, condition: bool) -> None:
        if not condition:
            failures.append(title)

    required_markers = [
        "9610",
        "9620",
        "O602",
        "LT_9610_001",
        "LT_9620_001",
        "LT_9620_002",
        "제외 조건 · WITHOUT",
        "input.inline-code-search",
        "table.inline-code-table",
        "screenshots_distinct",
        "runtime_electron_version",
        "35.6.0",
        "summary.click()",
        "all_tables_no_error_message",
        "case_execution_completed",
    ]
    for marker in required_markers:
        check(f"marker:{marker}", marker in HARNESS_JS)

    check(
        "ldd missing parser",
        parse_missing_libraries(
            "libnspr4.so => not found\n"
            "libc.so.6 => /lib/libc.so.6"
        ) == ["libnspr4.so"],
    )
    check(
        "runtime missing parser",
        parse_runtime_missing_library(
            "error while loading shared libraries: "
            "libnspr4.so: cannot open shared object file"
        ) == "libnspr4.so",
    )

    with tempfile.TemporaryDirectory(
        prefix="kdrg-stage52-selftest-"
    ) as temp:
        js_path = Path(temp) / "harness.js"
        js_path.write_text(
            HARNESS_JS,
            encoding="utf-8",
            newline="\n",
        )
        node = shutil.which("node")
        if node:
            result = run_command(
                [node, "--check", str(js_path)],
                cwd=ROOT,
                timeout=30,
            )
            check("node --check", result.returncode == 0)

    if failures:
        print(
            f"[FAIL] Stage 52 실행검증기 self-test: "
            f"{len(required_markers) + 3 - len(failures)} PASS / "
            f"{len(failures)} FAIL"
        )
        for failure in failures:
            print(f"- {failure}")
        return 1

    print(
        f"[PASS] Stage 52 실행검증기 self-test: "
        f"{len(required_markers) + 3} PASS / 0 FAIL"
    )
    return 0


def validate_repository() -> None:
    if not (ROOT / ".git").is_dir():
        raise ValidationError(
            f"Git 저장소가 아닙니다: {ROOT}"
        )

    head = run_command(
        ["git", "rev-parse", "HEAD"],
        check=True,
    ).stdout.strip()
    if head != EXPECTED_HEAD:
        raise ValidationError(
            f"기준 커밋 불일치: actual={head}, "
            f"expected={EXPECTED_HEAD}"
        )

    changed = set(tracked_files())
    if changed != EXPECTED_TRACKED:
        raise ValidationError(
            f"tracked 변경 파일 불일치: "
            f"actual={sorted(changed)}, "
            f"expected={sorted(EXPECTED_TRACKED)}"
        )

    diff_check = run_command(
        ["git", "diff", "--check"],
        check=False,
    )
    if (
        diff_check.returncode != 0
        or diff_check.stdout
        or diff_check.stderr
    ):
        raise ValidationError(
            "git diff --check 실패\n"
            f"{diff_check.stdout}{diff_check.stderr}"
        )

    actual_operating_sha = sha256_file(OPERATING_JSON)
    if actual_operating_sha != EXPECTED_OPERATING_SHA256:
        raise ValidationError(
            f"운영 JSON SHA256 불일치: "
            f"actual={actual_operating_sha}, "
            f"expected={EXPECTED_OPERATING_SHA256}"
        )


def execute_runtime_validation() -> int:
    validate_repository()

    before_files = tracked_files()
    before_hashes = tracked_hashes()
    before_operating_sha = sha256_file(OPERATING_JSON)

    if REPORT_DIR.exists():
        shutil.rmtree(REPORT_DIR)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    electron = find_electron()

    version_result = run_command(
        [str(electron), "--version"],
        cwd=ELECTRON_ROOT,
        timeout=30,
        check=False,
    )
    runtime_version = version_result.stdout.strip()
    if (
        version_result.returncode != 0
        or runtime_version != EXPECTED_RUNTIME_ELECTRON_VERSION
    ):
        raise ValidationError(
            "Nix Electron 버전 확인 실패: "
            f"returncode={version_result.returncode}, "
            f"actual={runtime_version!r}, "
            f"expected={EXPECTED_RUNTIME_ELECTRON_VERSION!r}, "
            f"stderr={version_result.stderr.strip()!r}"
        )

    runtime_env, loader_diagnostics = (
        prepare_electron_environment(electron)
    )
    loader_diagnostics["runtime_electron_version"] = (
        runtime_version
    )
    loader_diagnostics["runtime_scope"] = (
        "Linux Nix Electron 35.6.0 source UI preview; "
        "final Electron 43.2.0 Windows exe validation remains required"
    )

    if loader_diagnostics.get("remaining_missing"):
        missing_text = ", ".join(
            loader_diagnostics["remaining_missing"]
        )
        write_environment_failure_report(
            reason=(
                "Electron 필수 공유 라이브러리를 "
                f"자동으로 찾지 못함: {missing_text}"
            ),
            diagnostics=loader_diagnostics,
        )
        print(
            "[FAIL] Electron 실행환경 공유 라이브러리 미확보: "
            f"{missing_text}"
        )
        print(
            f"summary={SUMMARY_TXT.relative_to(ROOT)}"
        )
        return 1

    with tempfile.TemporaryDirectory(
        prefix="kdrg-stage52-runtime-"
    ) as temp:
        harness_path = Path(temp) / "stage52-runtime-ui.js"
        harness_path.write_text(
            HARNESS_JS,
            encoding="utf-8",
            newline="\n",
        )

        node = shutil.which("node")
        if node:
            syntax = run_command(
                [node, "--check", str(harness_path)],
                timeout=30,
            )
            if syntax.returncode != 0:
                raise ValidationError(
                    "임시 Electron harness 문법검사 실패\n"
                    f"{syntax.stdout}{syntax.stderr}"
                )

        runtime_env["KDRG_WORKSPACE_ROOT"] = str(ROOT)
        runtime_env["KDRG_STAGE52_REPORT_DIR"] = str(
            REPORT_DIR
        )
        runtime_env["KDRG_STAGE52_HEADLESS"] = "1"
        runtime_env[
            "ELECTRON_DISABLE_SECURITY_WARNINGS"
        ] = "true"

        result = run_command(
            [str(electron), str(harness_path)],
            cwd=ELECTRON_ROOT,
            env=runtime_env,
            timeout=240,
            check=False,
        )

        runtime_missing = parse_runtime_missing_library(
            "\n".join(
                value
                for value in (result.stdout, result.stderr)
                if value
            )
        )
        if result.returncode != 0 and runtime_missing:
            candidates = find_library_candidates(
                runtime_missing
            )
            if candidates and append_library_directory(
                runtime_env,
                candidates[0].parent,
            ):
                loader_diagnostics[
                    "runtime_retry_library"
                ] = {
                    "name": runtime_missing,
                    "path": str(candidates[0]),
                }
                result = run_command(
                    [str(electron), str(harness_path)],
                    cwd=ELECTRON_ROOT,
                    env=runtime_env,
                    timeout=240,
                    check=False,
                )

    if result.stdout:
        print(result.stdout.rstrip())
    if result.stderr:
        print(result.stderr.rstrip())

    after_files = tracked_files()
    after_hashes = tracked_hashes()
    after_operating_sha = sha256_file(OPERATING_JSON)

    if after_files != before_files:
        raise ValidationError(
            f"실행 전후 tracked 변경 목록 차이: "
            f"before={before_files}, after={after_files}"
        )
    if after_hashes != before_hashes:
        raise ValidationError(
            "실행화면 검증 중 제품 소스 해시가 변경됐습니다."
        )
    if after_operating_sha != before_operating_sha:
        raise ValidationError(
            "실행화면 검증 중 운영 JSON이 변경됐습니다."
        )

    if not RESULT_JSON.is_file():
        combined = "\n".join(
            value
            for value in (result.stdout, result.stderr)
            if value
        )
        runtime_missing = parse_runtime_missing_library(
            combined
        )
        reason = (
            "Electron 실행 중 공유 라이브러리 미확보: "
            f"{runtime_missing}"
            if runtime_missing
            else (
                "Electron 프로세스가 결과 JSON 생성 전에 종료됨 "
                f"(종료코드={result.returncode})"
            )
        )
        write_environment_failure_report(
            reason=reason,
            diagnostics=loader_diagnostics,
            stdout=result.stdout,
            stderr=result.stderr,
        )
        print(f"summary={SUMMARY_TXT.relative_to(ROOT)}")
        return 1

    report = json.loads(
        RESULT_JSON.read_text(encoding="utf-8")
    )
    print("===== Stage 52 실행화면 핵심 결과 =====")
    print(f"validator={report.get('validator')}")
    print(
        "runtime_electron_version="
        f"{report.get('runtime_electron_version')}"
    )
    print(
        "runtime_scope=Linux Nix Electron 35.6.0 "
        "소스 UI 검증; Windows Electron 43.2.0 최종검증 별도"
    )
    print(f"status={report.get('status')}")
    print(f"core_pass={report.get('core_pass')}")
    print(f"core_fail={report.get('core_fail')}")
    print(f"warning_pass={report.get('warning_pass')}")
    print(f"warning_fail={report.get('warning_fail')}")

    for item in report.get("cases") or []:
        table_ids = (
            (item.get("initial") or {}).get("table_ids")
            or []
        )
        row_info = [
            f"{table.get('table_id')}:{table.get('rows_before')}"
            for table in item.get("tables") or []
        ]
        error_texts = [
            (
                f"{table.get('table_id')}:"
                f"{table.get('error_text')}"
            )
            for table in item.get("tables") or []
            if table.get("error_text")
        ]
        case_error = (
            (item.get("case_error") or {}).get("message")
            or ""
        )
        print(
            f"case={item.get('adrg')} "
            f"status={item.get('status')} "
            f"tables={','.join(table_ids)} "
            f"rows={','.join(row_info)} "
            f"table_errors={' | '.join(error_texts)} "
            f"case_error={case_error}"
        )

    print(f"summary={SUMMARY_TXT.relative_to(ROOT)}")
    print(f"result={RESULT_JSON.relative_to(ROOT)}")
    print(
        "tracked_source_files=실행 전후 변경 없음"
    )
    print(
        f"operating_json_sha256={after_operating_sha}"
    )

    if result.returncode != 0:
        return result.returncode
    if report.get("status") != "PASS":
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--self-test",
        action="store_true",
    )
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    try:
        return execute_runtime_validation()
    except subprocess.TimeoutExpired as exc:
        diagnostics = {
            "timeout_seconds": exc.timeout,
            "command": (
                list(exc.cmd)
                if isinstance(exc.cmd, (list, tuple))
                else str(exc.cmd)
            ),
            "library_scan_mode": (
                "ldconfig + common directories + "
                "bounded /nix/store package scan"
            ),
        }
        write_environment_failure_report(
            reason=(
                "실행환경 확인 또는 Electron 실행이 "
                f"{exc.timeout}초를 초과함"
            ),
            diagnostics=diagnostics,
        )
        print(
            f"[FAIL] Stage 52 실행화면 검증 시간초과: "
            f"{exc.timeout}초"
        )
        print(
            f"summary={SUMMARY_TXT.relative_to(ROOT)}"
        )
        return 1
    except Exception as exc:
        if not SUMMARY_TXT.is_file():
            write_environment_failure_report(
                reason=(
                    f"{type(exc).__name__}: {exc}"
                ),
                diagnostics={
                    "library_scan_mode": (
                        "ldconfig + common directories + "
                        "bounded /nix/store package scan"
                    ),
                },
            )
        print(
            f"[FAIL] Stage 52 실행화면 검증 실패: "
            f"{type(exc).__name__}: {exc}"
        )
        print(
            f"summary={SUMMARY_TXT.relative_to(ROOT)}"
        )
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
