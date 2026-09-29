
const fs=require('fs');
const path=require('path');
const root=process.cwd();
const servicePath=path.join(root,'electron','src','kdrg-search-service.js');
const dataPath=path.join(root,'data','kdrg_v47_search_integrated_v3.json');
const outPath=path.join(root,'reports','stage68c_0516_classification_derived_aadrg_shadow_r3','_exact_relation_probe_output.json');

function pickClass(o){
  if(!o||typeof o!=='object') return {};
  const out={};
  for(const [k,v] of Object.entries(o)) if(/classification|abc_/i.test(k)) out[k]=v;
  return out;
}
function findId(x,id,found=[],p='$',depth=0){
  if(depth>10 || found.length>200) return found;
  if(Array.isArray(x)) x.forEach((v,i)=>findId(v,id,found,`${p}[${i}]`,depth+1));
  else if(x&&typeof x==='object'){
    const eid=String(x.entity_id||x.id||x.adrg||x.aadrg||'').toUpperCase();
    if(eid===id) found.push({path:p,classification:pickClass(x),value:x});
    for(const [k,v] of Object.entries(x)) findId(v,id,found,`${p}.${k}`,depth+1);
  }
  return found;
}
function slim(x,depth=0){
  if(depth>7) return '[depth]';
  if(Array.isArray(x)) return x.slice(0,250).map(v=>slim(v,depth+1));
  if(x&&typeof x==='object'){
    const o={};
    for(const [k,v] of Object.entries(x)){
      if(/entity|code|title|subtitle|summary|classification|abc_|relation|matched|total|aadrg|mdc|source|condition|result|disclaimer|operator|level/i.test(k))
        o[k]=slim(v,depth+1);
    }
    return o;
  }
  return x;
}
async function instantiate(){
  const mod=require(servicePath);
  const data=JSON.parse(fs.readFileSync(dataPath,'utf8'));
  const tries=[];
  const funcs=[];
  if(typeof mod==='function') funcs.push(['module',mod]);
  for(const [k,v] of Object.entries(mod||{})) if(typeof v==='function') funcs.push([k,v]);
  for(const [name,C] of funcs){
    for(const args of [[data],[dataPath],[]]){
      try{
        const x=new C(...args);
        if(x&&(typeof x.search==='function'||typeof x.relationSearch==='function')){
          if(typeof x.init==='function'){try{await x.init()}catch(e){}}
          if(typeof x.initialize==='function'){try{await x.initialize()}catch(e){}}
          return {svc:x,constructor:name,tries};
        }
      }catch(e){tries.push({constructor:name,args:args.map(a=>typeof a),error:String(e.message||e)})}
    }
  }
  if(mod&&typeof mod.createKdrgSearchService==='function'){
    for(const args of [[data],[dataPath],[]]){
      try{
        const x=await mod.createKdrgSearchService(...args);
        if(x) return {svc:x,constructor:'createKdrgSearchService',tries};
      }catch(e){tries.push({constructor:'createKdrgSearchService',error:String(e.message||e)})}
    }
  }
  throw new Error('service instance 생성 실패');
}
async function callSearch(svc){
  const variants=[
    ['F111','ADRG'],
    ['F111',{entityType:'ADRG'}],
    [{query:'F111',entityType:'ADRG'}],
  ];
  const errors=[];
  for(const args of variants){
    try{const r=await svc.search(...args); return {args,result:slim(r),f111:findId(r,'F111')}}
    catch(e){errors.push({args,error:String(e.message||e)})}
  }
  return {errors};
}
async function callDetail(svc){
  const variants=[
    ['ADRG','F111'],['F111','ADRG'],[{entityType:'ADRG',entityId:'F111'}],['F111']
  ];
  const errors=[];
  for(const args of variants){
    try{const r=await svc.getDetail(...args); return {args,result:slim(r),f111:findId(r,'F111')}}
    catch(e){errors.push({args,error:String(e.message||e)})}
  }
  return {errors};
}
async function callRelation(svc){
  const exact={
    conditions:[
      {codeType:'AUTO',code:'i214'},
      {codeType:'AUTO',code:'m6569'}
    ],
    operator:'AND',
    mdc:'',
    classification:''
  };
  const variants=[
    [exact],
    [{...exact,conditions:exact.conditions.map(x=>({...x,code:x.code.toUpperCase()}))}],
  ];
  const errors=[];
  for(const args of variants){
    try{
      const r=await svc.relationSearch(...args);
      const ids=(r?.results||[]).map(x=>String(x?.entity_id||'').toUpperCase());
      return {
        args,
        result:slim(r),
        result_ids:ids,
        result_count:Array.isArray(r?.results)?r.results.length:null,
        f111:findId(r,'F111'),
        fixture:{
          F111:findId(r,'F111'),F112:findId(r,'F112'),
          F121:findId(r,'F121'),F122:findId(r,'F122')
        }
      };
    }catch(e){errors.push({args,error:String(e.message||e)})}
  }
  return {errors};
}
(async()=>{
  const out={ok:false};
  try{
    const {svc,constructor,tries}=await instantiate();
    out.constructor=constructor; out.constructor_tries=tries;
    out.direct=await callSearch(svc);
    out.detail=await callDetail(svc);
    out.relation=await callRelation(svc);
    out.ok=true;
  }catch(e){out.error=String(e.stack||e)}
  fs.writeFileSync(outPath,JSON.stringify(out,null,2),'utf8');
})().catch(e=>fs.writeFileSync(outPath,JSON.stringify({ok:false,error:String(e.stack||e)},null,2),'utf8'));
