'use strict';

const path = require('node:path');
const { app, BrowserWindow, ipcMain, Menu } = require('electron');
const { buildBootstrapSnapshot } = require('./src/bootstrap-data');
const { resolveDataFiles } = require('./src/data-paths');

const IPC_CHANNEL = 'kdrg:get-bootstrap-snapshot';
let mainWindow = null;
let bootstrapSnapshot = null;

function getBootstrapSnapshot() {
  if (bootstrapSnapshot) {
    return bootstrapSnapshot;
  }

  const dataFiles = resolveDataFiles({
    isPackaged: app.isPackaged,
    resourcesPath: process.resourcesPath,
  });
  bootstrapSnapshot = buildBootstrapSnapshot(dataFiles);
  return bootstrapSnapshot;
}

function registerIpcHandlers() {
  ipcMain.removeHandler(IPC_CHANNEL);
  ipcMain.handle(IPC_CHANNEL, async () => getBootstrapSnapshot());
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
    if (!mainWindow) {
      return;
    }
    if (mainWindow.isMinimized()) {
      mainWindow.restore();
    }
    mainWindow.focus();
  });

  app.whenReady().then(() => {
    app.setName('KDRG V4.7 관계 검색기');
    Menu.setApplicationMenu(null);
    registerIpcHandlers();
    mainWindow = createMainWindow();

    app.on('activate', () => {
      if (BrowserWindow.getAllWindows().length === 0) {
        mainWindow = createMainWindow();
      }
    });
  });
}

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
