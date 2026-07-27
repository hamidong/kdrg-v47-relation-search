'use strict';

const crypto = require('node:crypto');
const fs = require('node:fs');

const EXPECTED = Object.freeze({
  integrated: Object.freeze({
    schema: 'kdrg-v47-search-integrated-v2',
    sha256: '3de5d6d95cd9cbd16e674f5a4cffcd8bf89da2ee70627501f56d81b05bbe8af1',
  }),
  semanticProfile: Object.freeze({
    schema: 'kdrg-v47-ui-semantic-profile-v1',
    sha256: 'c9401fd9d6dcc1253fa2134b22048fe4a73c4c04aeea4d1d86c7fe1504d5456e',
  }),
  displayContract: Object.freeze({
    schema: 'kdrg-v47-ui-display-contract-v1',
    sha256: '9976307acd77bb6a0c8a48b2788d055faf563d497381b2c2cacfc7435df0f1ac',
  }),
});

const MAX_JSON_BYTES = 128 * 1024 * 1024;

function sha256(buffer) {
  return crypto.createHash('sha256').update(buffer).digest('hex');
}

function readRequiredJson(filePath, expectation) {
  const stat = fs.statSync(filePath);
  if (!stat.isFile()) {
    throw new Error(`필수 데이터 파일이 아닙니다: ${filePath}`);
  }
  if (stat.size <= 0 || stat.size > MAX_JSON_BYTES) {
    throw new Error(`필수 데이터 파일 크기가 허용 범위를 벗어났습니다: ${filePath}`);
  }

  const raw = fs.readFileSync(filePath);
  const digest = sha256(raw);
  if (digest !== expectation.sha256) {
    throw new Error(`필수 데이터 SHA256 불일치: ${filePath}`);
  }

  let payload;
  try {
    payload = JSON.parse(raw.toString('utf8'));
  } catch (error) {
    throw new Error(`필수 데이터 JSON 파싱 실패: ${filePath} | ${error.message}`);
  }

  const schema = payload?.meta?.schema_version;
  if (schema !== expectation.schema) {
    throw new Error(
      `필수 데이터 schema 불일치: ${filePath} | actual=${schema} | expected=${expectation.schema}`,
    );
  }

  return Object.freeze({
    payload,
    file: Object.freeze({
      filePath,
      fileName: filePath.split(/[\\/]/).pop(),
      sizeBytes: stat.size,
      sha256: digest,
      schema,
    }),
  });
}

function buildBootstrapSnapshot(dataFiles) {
  const integrated = readRequiredJson(dataFiles.integrated, EXPECTED.integrated);
  const semanticProfile = readRequiredJson(
    dataFiles.semanticProfile,
    EXPECTED.semanticProfile,
  );
  const displayContract = readRequiredJson(
    dataFiles.displayContract,
    EXPECTED.displayContract,
  );

  const integratedPayload = integrated.payload;
  const contractPayload = displayContract.payload;

  const snapshot = {
    status: 'ready',
    dataVersion: integratedPayload?.meta?.data_version ?? 'KDRG V4.7',
    schemas: {
      integrated: integrated.file.schema,
      semanticProfile: semanticProfile.file.schema,
      displayContract: displayContract.file.schema,
    },
    counts: {
      adrg: integratedPayload.adrg_records.length,
      aadrg: integratedPayload.aadrg_records.length,
      rdrg: integratedPayload.rdrg_records.length,
      tables: integratedPayload.logical_table_records.length,
      codes: integratedPayload.code_records.length,
      conditionAst: integratedPayload.condition_ast_records.length,
      conditionTableOccurrences:
        contractPayload.condition_table_occurrence_registry.length,
    },
    displayContract: {
      targetRuntimes: contractPayload?.meta?.target_runtimes ?? [],
      includeOccurrences:
        contractPayload?.contract_counts?.condition_table_include_occurrences ?? 0,
      excludeOccurrences:
        contractPayload?.contract_counts?.condition_table_exclude_occurrences ?? 0,
      unknownTableCount:
        contractPayload?.contract_counts?.table_category_counts?.unknown ?? 0,
    },
    files: {
      integrated: integrated.file,
      semanticProfile: semanticProfile.file,
      displayContract: displayContract.file,
    },
    capabilities: {
      rawCorpusExposedToRenderer: false,
      searchServiceConnected: true,
      stage: '50C_RENDERER_SEARCH_UI',
      nextStage: '50D_ELECTRON_PACKAGE_AND_WINDOWS_BUILD',
    },
  };

  return Object.freeze(snapshot);
}

module.exports = Object.freeze({
  EXPECTED,
  MAX_JSON_BYTES,
  sha256,
  readRequiredJson,
  buildBootstrapSnapshot,
});
