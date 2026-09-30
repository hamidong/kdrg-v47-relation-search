'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const ROOT = path.resolve(__dirname, '..', '..');
const APP_PATH = process.env.KDRG_APP_PATH
  ? path.resolve(process.env.KDRG_APP_PATH)
  : path.join(ROOT, 'electron', 'renderer', 'app.js');

const app = fs.readFileSync(APP_PATH, 'utf8');

function functionBody(name) {
  const start = app.indexOf(`function ${name}`);
  assert.ok(start >= 0, `missing function ${name}`);
  const next = app.indexOf('\nfunction ', start + 20);
  return app.slice(start, next >= 0 ? next : app.length);
}

function element(tag, className = '', text = '') {
  return {
    tag,
    className,
    textContent: text ?? '',
    children: [],
    dataset: {},
    attrs: {},
    disabled: false,
    append(...items) {
      for (const item of items.flat()) {
        if (item !== null && item !== undefined) this.children.push(item);
      }
    },
    replaceChildren(...items) {
      this.children = [];
      this.append(...items);
    },
    setAttribute(name, value) {
      this.attrs[name] = String(value);
    },
  };
}

const ids = new Map();
function byId(id) {
  if (!ids.has(id)) ids.set(id, element('div', `id-${id}`));
  return ids.get(id);
}

function create(tag, className = '', text = '') {
  return element(tag, className, text);
}

function makeBadge(text) {
  return element('span', 'badge', text);
}

function makeChip(text, className = '') {
  return element('span', `chip ${className}`.trim(), text);
}

function appendClassificationBadges(host, values) {
  let count = 0;
  for (const value of values ?? []) {
    if (!value) continue;
    host.append(makeChip(value, 'classification-chip'));
    count += 1;
  }
  return count;
}

function mdcDisplayText(mdc, name) {
  return name ? `MDC ${mdc} · ${name}` : `MDC ${mdc}`;
}

const state = {
  selectedKey: null,
  response: null,
  relationResponse: null,
  activeMode: null,
};

const textState = new Map();
function setText(id, value) {
  textState.set(id, String(value));
}

const Ui = {
  formatNumber(value) {
    return String(value);
  },
};

function renderRelationCounts() {}

const context = {
  console,
  state,
  Ui,
  byId,
  create,
  makeBadge,
  makeChip,
  appendClassificationBadges,
  mdcDisplayText,
  setText,
  renderRelationCounts,
};

const relationSource = functionBody('renderRelationResults');
const renderRelationResults = vm.runInNewContext(
  `(${relationSource})`,
  context,
  { filename: APP_PATH },
);

const response = {
  operator: 'AND',
  total_count: 2,
  results: [
    {
      entity_id: 'F022',
      relation_level: 'strict',
      relation_level_label: '같은 조건 선택지',
      matched_count: 2,
      total_count: 2,
      parent_adrg: null,
      title: 'F022 · 런타임 검증',
      subtitle: '',
      summary: {
        mdc: '06',
        mdc_name: '소화기',
        abc_display_labels: ['A 전문'],
        classification_code: 'A',
        classification_display_label: 'A 전문',
      },
    },
    {
      entity_id: 'P020',
      relation_level: 'split',
      relation_level_label: '다른 선택지',
      matched_count: 2,
      total_count: 2,
      parent_adrg: null,
      title: 'P020 · 분류정보 없음 검증',
      subtitle: '',
      summary: {
        mdc: '08',
        mdc_name: '근골격',
        abc_display_labels: [],
        classification_code: '',
        classification_display_label: '',
      },
    },
  ],
};

try {
  renderRelationResults(response);

  const list = byId('result-list');
  assert.equal(list.children.length, 2, 'relation result card count');

  const first = list.children[0];
  const second = list.children[1];

  assert.match(first.className, /relation-result-card/);
  assert.match(second.className, /relation-result-card/);

  const firstMain = first.children[0];
  const secondMain = second.children[0];

  assert.ok(firstMain, 'first main missing');
  assert.ok(secondMain, 'second main missing');
  assert.match(firstMain.className, /result-card-main/);
  assert.match(secondMain.className, /result-card-main/);

  const firstTexts = firstMain.children.map((x) => x.textContent);
  const secondTexts = secondMain.children.map((x) => x.textContent);

  assert.ok(firstTexts.includes('ADRG'), 'ADRG badge missing');
  assert.ok(firstTexts.includes('F022 · 런타임 검증'), 'relation title missing');

  const firstClassification = firstMain.children.find(
    (x) => String(x.className).includes('result-card-classification'),
  );
  const secondClassification = secondMain.children.find(
    (x) => String(x.className).includes('result-card-classification'),
  );

  assert.ok(firstClassification, 'classification group missing');
  assert.ok(secondClassification, 'classification fallback group missing');

  assert.ok(
    firstClassification.children.some((x) => x.textContent === 'A 전문'),
    'A 전문 classification missing',
  );
  assert.ok(
    secondClassification.children.some((x) => x.textContent === '분류정보 없음'),
    'classification fallback missing',
  );

  function flatten(node, out = []) {
    out.push(node);
    for (const child of node.children ?? []) flatten(child, out);
    return out;
  }

  const nodes = flatten(first);
  assert.ok(
    !nodes.some((x) => String(x.className).includes('result-match-chip')),
    'per-card relation-level chip must remain removed',
  );

  assert.equal(state.activeMode, 'relation');
  assert.equal(byId('page-previous').disabled, true);
  assert.equal(byId('page-next').disabled, true);

  console.log('[PASS] Stage73B runtime smoke / renderRelationResults');
  console.log('relation_cards=2');
  console.log('main_scope=PASS');
  console.log('adrg_badge=PASS');
  console.log('relation_title=PASS');
  console.log('classification_A=PASS');
  console.log('classification_fallback=PASS');
  console.log('relation_level_chip=REMOVED');
} catch (error) {
  console.log('[FAIL] Stage73B runtime smoke / renderRelationResults');
  console.log(`${error.name}: ${error.message}`);
  process.exitCode = 1;
}
