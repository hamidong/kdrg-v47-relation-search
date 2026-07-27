'use strict';

const path = require('node:path');

const DATA_FILES = Object.freeze({
  integrated: 'kdrg_v47_search_integrated.json',
  semanticProfile: 'kdrg_v47_ui_semantic_profile.json',
  displayContract: 'kdrg_v47_ui_display_contract.json',
});

function resolveDataDirectory({ isPackaged, resourcesPath, moduleDirectory = __dirname }) {
  if (isPackaged) {
    if (!resourcesPath) {
      throw new Error('packaged 환경의 resourcesPath가 비어 있습니다.');
    }
    return path.resolve(resourcesPath, 'data');
  }

  return path.resolve(moduleDirectory, '..', '..', 'data');
}

function resolveDataFiles(options) {
  const dataDirectory = resolveDataDirectory(options);
  return Object.freeze(
    Object.fromEntries(
      Object.entries(DATA_FILES).map(([key, fileName]) => [
        key,
        path.join(dataDirectory, fileName),
      ]),
    ),
  );
}

module.exports = Object.freeze({
  DATA_FILES,
  resolveDataDirectory,
  resolveDataFiles,
});
