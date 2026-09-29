
'use strict';
const fs=require('node:fs');
const path=require('node:path');

const ROOT=process.cwd();
const E=path.join(ROOT,'electron');
const OUT=path.join(ROOT,'reports','stage68c_0516_release_parity_fixture_matrix_r5','_fixture_matrix_probe_output.json');

const {resolveDataFiles}=require(path.join(E,'src','data-paths'));
const {KdrgSearchService,normalizeEntityId}=require(path.join(E,'src','kdrg-search-service'));
const {normalizeRelationRequest,SEARCH_ENTITY_TYPES}=require(path.join(E,'src','search-result-contract'));

const dataFiles=resolveDataFiles({
  isPackaged:false,
  resourcesPath:null,
  moduleDirectory:path.join(E,'src'),
});
const service=new KdrgSearchService(dataFiles.integrated);

function slimCode(raw){
  if(!raw) return null;
  return {
    entity_id:raw.entity_id,
    names:raw.names,
    related_adrgs:raw.related_adrgs,
    related_aadrgs:raw.related_aadrgs,
    namespace_meanings:raw.namespace_meanings,
    code_types:raw.code_types,
  };
}
function slimCandidate(c){
  if(!c) return null;
  return {
    entity_id:c.entity_id,
    title:c.title,
    summary:c.summary ?? null,
    relation_level:c.relation_level,
    relation_level_label:c.relation_level_label,
    matched_count:c.matched_count,
    total_count:c.total_count,
    code_matches:(c.code_matches??[]).map(x=>({
      code:x.code,
      code_type:x.code_type,
      code_type_label:x.code_type_label,
      exact_code_found:x.exact_code_found,
      matched_table_ids:x.matched_table_ids,
    })),
    aadrg_records:c.aadrg_records ?? [],
  };
}
function invokePayload(payload){
  try{
    const normalized=normalizeRelationRequest(payload);
    const response=service.relationSearch(
      normalized.conditions,
      normalized.operator,
      {mdc:normalized.mdc,classification:normalized.classification},
    );
    const ids=(response.results??[]).map(x=>x.entity_id);
    return {
      ok:true,
      payload,
      normalized,
      total_count:response.total_count,
      result_ids:ids,
      fixture:Object.fromEntries(
        ['F111','F112','F121','F122'].map(id=>[
          id,
          slimCandidate((response.results??[]).find(x=>x.entity_id===id))
        ])
      )
    };
  }catch(e){
    return {ok:false,payload,error:String(e?.stack??e)};
  }
}

const variants=[
  {
    name:'AUTO_lower',
    payload:{conditions:[
      {codeType:'AUTO',code:'i214'},
      {codeType:'AUTO',code:'m6569'},
    ],operator:'AND',mdc:'',classification:''}
  },
  {
    name:'AUTO_upper',
    payload:{conditions:[
      {codeType:'AUTO',code:'I214'},
      {codeType:'AUTO',code:'M6569'},
    ],operator:'AND',mdc:'',classification:''}
  },
  {
    name:'DIAGNOSIS_lower',
    payload:{conditions:[
      {codeType:'DIAGNOSIS',code:'i214'},
      {codeType:'DIAGNOSIS',code:'m6569'},
    ],operator:'AND',mdc:'',classification:''}
  },
  {
    name:'DIAGNOSIS_upper',
    payload:{conditions:[
      {codeType:'DIAGNOSIS',code:'I214'},
      {codeType:'DIAGNOSIS',code:'M6569'},
    ],operator:'AND',mdc:'',classification:''}
  },
];

const variantResults={};
for(const v of variants) variantResults[v.name]=invokePayload(v.payload);

const derivedMissingCode=[];
let derivedTotal=0;
for(const adrg of [...service.recordMaps.ADRG.keys()].sort()){
  const d=service.getDetail('ADRG',adrg)?.detail;
  for(const child of d?.aadrg_records??[]){
    derivedTotal++;
    const code=String(child?.summary?.classification_code??'').trim();
    const label=String(child?.summary?.classification_display_label??'').trim();
    if(!code){
      derivedMissingCode.push({
        adrg,
        aadrg:child?.entity_id??null,
        label,
        title:child?.title??null,
        abc_status:child?.summary?.abc_status??null,
      });
    }
  }
}

const out={
  ok:true,
  service_status:service.status(),
  public_types:Array.from(SEARCH_ENTITY_TYPES??[]),
  code_records:{
    I214:slimCode(service.recordMaps.CODE.get(normalizeEntityId('I214','CODE'))),
    M6569:slimCode(service.recordMaps.CODE.get(normalizeEntityId('M6569','CODE'))),
  },
  variants:variantResults,
  derived:{
    total:derivedTotal,
    missing_code_count:derivedMissingCode.length,
    missing_code_records:derivedMissingCode,
  },
};
fs.writeFileSync(OUT,JSON.stringify(out,null,2),'utf8');
