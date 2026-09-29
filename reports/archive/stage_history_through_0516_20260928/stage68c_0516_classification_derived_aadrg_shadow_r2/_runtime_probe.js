
const fs = require('fs');
const path = require('path');
const root = process.cwd();
const servicePath = path.join(root,'electron','src','kdrg-search-service.js');
const dataPath = path.join(root,'data','kdrg_v47_search_integrated_v3.json');
const outPath = path.join(root,'reports','stage68c_0516_classification_derived_aadrg_shadow_r2','_runtime_probe_output.json');

function cls(o) {
  if (!o || typeof o !== 'object') return {};
  const keys = Object.keys(o).filter(k => /class|abc/i.test(k));
  const r={}; for (const k of keys) r[k]=o[k]; return r;
}
function id(o) {
  if (!o || typeof o !== 'object') return '';
  return String(o.entity_id || o.id || o.code || o.adrg || o.aadrg || o.group_code || '').toUpperCase();
}
function compact(x, depth=0) {
  if (depth > 5) return '[depth]';
  if (Array.isArray(x)) return x.slice(0,80).map(v=>compact(v,depth+1));
  if (x && typeof x === 'object') {
    const o={};
    for (const [k,v] of Object.entries(x)) {
      if (/class|abc|entity|code|title|name|adrg|summary|candidate|result|detail|match/i.test(k))
        o[k]=compact(v,depth+1);
    }
    return o;
  }
  return x;
}
function locateF111(x, found=[], p='$', depth=0) {
  if (depth > 8 || found.length > 50) return found;
  if (Array.isArray(x)) x.forEach((v,i)=>locateF111(v,found,`${p}[${i}]`,depth+1));
  else if (x && typeof x === 'object') {
    if (id(x)==='F111') found.push({path:p, classification:cls(x), record:compact(x)});
    for (const [k,v] of Object.entries(x)) locateF111(v,found,`${p}.${k}`,depth+1);
  }
  return found;
}
(async()=>{
  const result={ok:false, export_keys:[], constructor:null, attempts:[], direct:null, detail:null, relation:null};
  try {
    const mod=require(servicePath);
    result.export_keys=Object.keys(mod||{});
    const candidates=[];
    if (typeof mod === 'function') candidates.push(['module',mod]);
    for (const [k,v] of Object.entries(mod||{})) if (typeof v === 'function') candidates.push([k,v]);

    const data=JSON.parse(fs.readFileSync(dataPath,'utf8'));
    let svc=null, ctorName=null;
    for (const [name,C] of candidates) {
      for (const args of [[data],[dataPath],[]]) {
        try {
          const x=new C(...args);
          if (x && (typeof x.search==='function' || typeof x.relationSearch==='function')) {
            svc=x; ctorName=name; result.attempts.push({ctor:name,args:args.map(a=>typeof a),ok:true}); break;
          }
        } catch(e) { result.attempts.push({ctor:name,args:args.map(a=>typeof a),ok:false,error:String(e.message||e)}); }
      }
      if (svc) break;
    }
    if (!svc && mod && typeof mod.createKdrgSearchService==='function') {
      for (const args of [[data],[dataPath],[]]) {
        try { const x=await mod.createKdrgSearchService(...args); if(x){svc=x;ctorName='createKdrgSearchService';break;} } catch(e){}
      }
    }
    if (!svc) throw new Error('service instance 자동 생성 실패');
    result.constructor=ctorName;
    if (typeof svc.init==='function') { try { await svc.init(); } catch(e) {} }
    if (typeof svc.initialize==='function') { try { await svc.initialize(); } catch(e) {} }

    const callVariants = async (name, variants) => {
      if (typeof svc[name] !== 'function') return {available:false};
      const errors=[];
      for (const args of variants) {
        try {
          const v=await svc[name](...args);
          return {available:true,args,raw:compact(v),f111:locateF111(v)};
        } catch(e) { errors.push({args,error:String(e.message||e)}); }
      }
      return {available:true,errors};
    };

    result.direct=await callVariants('search', [
      ['F111','ADRG'], ['F111',{entityType:'ADRG'}], [{query:'F111',entityType:'ADRG'}]
    ]);
    result.detail=await callVariants('getDetail', [
      ['ADRG','F111'], ['F111','ADRG'], [{entityType:'ADRG',entityId:'F111'}], ['F111']
    ]);
    result.relation=await callVariants('relationSearch', [
      [['i214','m6569'],'AND'],
      [['i214','m6569'],{operator:'AND',matchMode:'ALL'}],
      [{codes:['i214','m6569'],operator:'AND',matchMode:'ALL'}],
      [{queries:['i214','m6569'],operator:'AND',matchMode:'ALL'}],
      [{terms:['i214','m6569'],mode:'AND'}]
    ]);
    result.ok=true;
  } catch(e) {
    result.error=String(e && (e.stack||e.message) || e);
  }
  fs.writeFileSync(outPath,JSON.stringify(result,null,2),'utf8');
})().catch(e=>{
  fs.writeFileSync(outPath,JSON.stringify({ok:false,error:String(e.stack||e)},null,2),'utf8');
});
