'use strict';

const path = require('node:path');
const { app, BrowserWindow, ipcMain, Menu } = require('electron');
const { buildBootstrapSnapshot } = require('./src/bootstrap-data');
const { resolveDataFiles } = require('./src/data-paths');
const { KdrgSearchService } = require('./src/kdrg-search-service');
const {
  normalizeSearchRequest,
  normalizeDetailRequest,
} = require('./src/search-result-contract');

const IPC_CHANNELS = Object.freeze({
  bootstrap: 'kdrg:get-bootstrap-snapshot',
  searchStatus: 'kdrg:get-search-status',
  search: 'kdrg:search',
  detail: 'kdrg:get-detail',
});

let mainWindow = null;
let bootstrapSnapshot = null;
let searchService = null;

function getDataFiles() {
  return resolveDataFiles({
    isPackaged: app.isPackaged,
    resourcesPath: process.resourcesPath,
  });
}

function getBootstrapSnapshot() {
  if (!bootstrapSnapshot) {
    bootstrapSnapshot = buildBootstrapSnapshot(getDataFiles());
  }
  return bootstrapSnapshot;
}

function getSearchService() {
  if (!searchService) {
    searchService = new KdrgSearchService(getDataFiles().integrated);
  }
  return searchService;
}

function registerIpcHandlers() {
  for (const channel of Object.values(IPC_CHANNELS)) {
    ipcMain.removeHandler(channel);
  }

  ipcMain.handle(IPC_CHANNELS.bootstrap, async () => getBootstrapSnapshot());
  ipcMain.handle(IPC_CHANNELS.searchStatus, async () => getSearchService().status());
  ipcMain.handle(IPC_CHANNELS.search, async (_event, payload) => {
    const request = normalizeSearchRequest(payload);
    return getSearchService().search(request.query, request.entityType, {
      limit: request.limit,
      offset: request.offset,
      mdc: request.mdc,
      classification: request.classification,
    });
  });
  ipcMain.handle(IPC_CHANNELS.detail, async (_event, payload) => {
    const request = normalizeDetailRequest(payload);
    return getSearchService().getDetail(request.entityType, request.entityId);
  });
}

function createMainWindow() {
  const window = new BrowserWindow({
    width: 1600,
    height: 980,
    minWidth: 1180,
    minHeight: 720,
    show: false,
    backgroundColor: '#f3f6fb',
    title: 'KDRG V4.7 관계 검색기 · Electron 기반',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      devTools: process.env.KDRG_ELECTRON_DEVTOOLS === '1',
      spellcheck: false,
    },
  });

  window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  window.webContents.on('will-navigate', (event) => event.preventDefault());
  window.webContents.on('render-process-gone', (_event, details) => {
    console.error('[KDRG Electron] renderer process 종료', details);
  });
  window.once('ready-to-show', () => window.show());
  window.on('closed', () => {
    if (mainWindow === window) {
      mainWindow = null;
    }
  });

  window.loadFile(path.join(__dirname, 'renderer', 'index.html'));
  return window;
}

const hasSingleInstanceLock = app.requestSingleInstanceLock();
if (!hasSingleInstanceLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (!mainWindow) return;
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.focus();
  });

  app.whenReady().then(() => {
    app.setName('KDRG V4.7 관계 검색기');
    Menu.setApplicationMenu(null);
    registerIpcHandlers();
    getSearchService();
    mainWindow = createMainWindow();

    app.on('activate', () => {
      if (BrowserWindow.getAllWindows().length === 0) {
        mainWindow = createMainWindow();
      }
    });
  });
}

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
