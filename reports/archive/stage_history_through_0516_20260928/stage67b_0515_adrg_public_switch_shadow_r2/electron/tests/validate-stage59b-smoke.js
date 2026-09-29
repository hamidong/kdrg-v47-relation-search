'use strict';
const assert=require('node:assert/strict');const path=require('node:path');const {KdrgSearchService}=require('../src/kdrg-search-service');const s=new KdrgSearchService(path.resolve(__dirname,'..','..','data','kdrg_v47_search_integrated_v3.json'));
const r=s.search('T601','ALL',{limit:500});assert.ok(r.results.length>=2);assert.ok(r.results.every(x=>['CODE','ADRG'].includes(x.entity_type)));const d=s.getDetail('AADRG','P6510').detail;assert.ok(d.parent_adrg_detail);assert.ok(d.mdc_name);console.log('stage59_smoke: PASS');
