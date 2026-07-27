'use strict';

const { contextBridge, ipcRenderer } = require('electron');

const CHANNELS = Object.freeze({
  getBootstrapSnapshot: 'kdrg:get-bootstrap-snapshot',
});

const api = Object.freeze({
  getBootstrapSnapshot: () => ipcRenderer.invoke(CHANNELS.getBootstrapSnapshot),
});

contextBridge.exposeInMainWorld('KDRG', api);
