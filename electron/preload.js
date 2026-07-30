'use strict';

const { contextBridge, ipcRenderer } = require('electron');

const CHANNELS = Object.freeze({
  getBootstrapSnapshot: 'kdrg:get-bootstrap-snapshot',
  getSearchStatus: 'kdrg:get-search-status',
  search: 'kdrg:search',
  relationSearch: 'kdrg:relation-search',
  getDetail: 'kdrg:get-detail',
});

const api = Object.freeze({
  getBootstrapSnapshot: () => ipcRenderer.invoke(CHANNELS.getBootstrapSnapshot),
  getSearchStatus: () => ipcRenderer.invoke(CHANNELS.getSearchStatus),
  search: (request) => ipcRenderer.invoke(CHANNELS.search, request),
  relationSearch: (request) => ipcRenderer.invoke(CHANNELS.relationSearch, request),
  getDetail: (request) => ipcRenderer.invoke(CHANNELS.getDetail, request),
});

contextBridge.exposeInMainWorld('KDRG', api);
