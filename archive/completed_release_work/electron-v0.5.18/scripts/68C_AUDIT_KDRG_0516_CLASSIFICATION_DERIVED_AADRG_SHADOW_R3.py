#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage68C R3 — KDRG 0.5.16 Exact Relation Classification Shadow Audit

R2 보정사항
1) ADRG/AADRG 판정은 entity_id 정규식이 아니라 entity_type 명시값만 사용한다.
2) 실제 Electron renderer와 동일한 relationSearch request shape를 사용한다.
3) 실제 fixture: i214 + m6569 / AUTO + AUTO / AND / 필터 없음.
4) F111 direct / detail / relation candidate를 정확히 비교한다.
5) current workspace app.js에서 relation detail 및 derived AADRG 호출 경로를 직접 검사한다.
6) 제품파일/운영JSON은 수정하지 않는다.
"""

from __future__ import annotations
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path.cwd()
REPORT_DIR = ROOT / "reports" / "stage68c_0516_classification_derived_aadrg_shadow_r3"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

REPORT_JSON = REPORT_DIR / "audit.json"
REPORT_TXT = REPORT_DIR / "audit_summary.txt"
NODE_PROBE = REPORT_DIR / "_exact_relation_probe.js"
NODE_OUT = REPORT_DIR / "_exact_relation_probe_output.json"

DATA = ROOT / "data" / "kdrg_v47_search_integrated_v3.json"
SERVICE = ROOT / "electron" / "src" / "kdrg-search-service.js"
APP = ROOT / "electron" / "renderer" / "app.js"
CSS = ROOT / "electron" / "renderer" / "styles.css"
FORMATTERS = ROOT / "electron" / "renderer" / "ui-formatters.js"

VALIDATORS = [
    ROOT / "electron" / "tests" / "validate-stage59b-search.js",
    ROOT / "electron" / "tests" / "validate-stage59b-ui.js",
    ROOT / "electron" / "tests" / "validate-stage59b-smoke.js",
    ROOT / "electron" / "tests" / "validate-packaged-runtime-smoke.js",
    ROOT / "electron" / "tests" / "validate-stage60c-packaged-relation-smoke.js",
    ROOT / "50B_validate_kdrg_electron_search_service.py",
    ROOT / "50C_validate_kdrg_electron_renderer_ui.py",
    ROOT / "50D_validate_kdrg_electron_windows_packaging.py",
]

EXPECTED_DATA_SHA256 = "1a3d50400567ecaad9695b7be8e7c0382131f8652f398e010cf01f4d8dda6c58"
EXPECTED_ADRG_COUNT = 1132
FIXTURE_ADRGS = ["F111", "F112", "F121", "F122"]

def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")

def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()

def norm(v: Any) -> str:
    return str(v or "").strip().upper()

def walk(obj: Any, path="$"):
    yield path, obj
    if isinstance(obj, dict):
        for k,v in obj.items():
            yield from walk(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i,v in enumerate(obj):
            yield from walk(v, f"{path}[{i}]")

def entity_id(o: dict) -> str:
    for k in ("entity_id","id","code","adrg","aadrg"):
        if o.get(k) not in (None,""):
            return norm(o[k])
    return ""

def classification(o: Any) -> Dict[str, List[str]]:
    if not isinstance(o, dict):
        return {"codes":[], "labels":[]}
    codes, labels = [], []
    for k in ("classification_code","classification_codes","abc_classification_code",
              "abc_classification_codes","abc_code","abc_codes"):
        v=o.get(k)
        vals=v if isinstance(v,list) else ([] if v in (None,"") else [v])
        for x in vals:
            s=str(x).strip().upper()
            if s and s not in codes: codes.append(s)
    for k in ("classification_display_label","classification_display_labels",
              "abc_display_label","abc_display_labels"):
        v=o.get(k)
        vals=v if isinstance(v,list) else ([] if v in (None,"") else [v])
        for x in vals:
            s=str(x).strip()
            if s and s not in labels: labels.append(s)
    return {"codes":codes, "labels":labels}

def exact_entities(data: Any, wanted: str) -> Tuple[Dict[str,List[Tuple[str,dict]]], int]:
    grouped=defaultdict(list)
    occurrences=0
    for p,o in walk(data):
        if not isinstance(o,dict): continue
        if norm(o.get("entity_type")) != wanted: continue
        eid=entity_id(o)
        if not eid: continue
        grouped[eid].append((p,o)); occurrences += 1
    return dict(grouped), occurrences

def choose_best(records: List[Tuple[str,dict]]) -> Tuple[str,dict]:
    def score(po):
        p,o=po
        c=classification(o)
        detail=o.get("detail") if isinstance(o.get("detail"),dict) else {}
        dc=classification(detail)
        children=detail.get("aadrg_records") if isinstance(detail,dict) else None
        if children is None: children=o.get("aadrg_records")
        return (
            (bool(c["codes"])+bool(c["labels"])+bool(dc["codes"])+bool(dc["labels"]))*1000
            + (len(children) if isinstance(children,list) else 0)*100
            + len(o)
        )
    return max(records,key=score)

def function_block(text: str, name: str) -> str:
    # JS 함수 시작에서 brace depth로 실제 함수 전체를 추출.
    m=re.search(rf"(?:async\s+)?function\s+{re.escape(name)}\s*\([^)]*\)\s*\{{", text)
    if not m: return ""
    i=m.end()-1
    depth=0
    quote=None
    esc=False
    for j in range(i,len(text)):
        ch=text[j]
        if quote:
            if esc: esc=False
            elif ch=="\\": esc=True
            elif ch==quote: quote=None
            continue
        if ch in ("'",'"','`'):
            quote=ch; continue
        if ch=="{": depth+=1
        elif ch=="}":
            depth-=1
            if depth==0:
                return text[m.start():j+1]
    return text[m.start():m.start()+12000]

def compact_runtime(obj: Any) -> Any:
    return obj

def make_node_probe():
    js = r"""
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
"""
    NODE_PROBE.write_text(js,encoding="utf-8")

def extract_runtime_class(hitlist: Any, prefer_summary=True) -> Dict[str,List[str]]:
    # path 우선순위: summary > detail > record root
    if not isinstance(hitlist,list): return {"codes":[],"labels":[]}
    candidates=[]
    for hit in hitlist:
        if not isinstance(hit,dict): continue
        p=str(hit.get("path",""))
        c=classification(hit.get("classification",{}))
        # classification()은 wrapper keys를 다시 못 읽을 수 있으므로 원문 value도 확인
        v=hit.get("value")
        cv=classification(v)
        merged={"codes":c["codes"] or cv["codes"],"labels":c["labels"] or cv["labels"]}
        rank=(3 if ".summary" in p else 2 if ".detail" in p else 1)
        if merged["codes"] or merged["labels"]: candidates.append((rank,merged,p))
    if not candidates: return {"codes":[],"labels":[]}
    return max(candidates,key=lambda x:x[0])[1]

def main():
    required=[DATA,SERVICE,APP,CSS,FORMATTERS]
    missing=[str(p.relative_to(ROOT)) for p in required if not p.exists()]
    if missing:
        REPORT_TXT.write_text("[FAIL] required files missing\n"+"\n".join(missing),encoding="utf-8")
        print(f"[FAIL] Stage68C R3 required_missing={len(missing)}")
        print(f"report={REPORT_TXT.relative_to(ROOT)}")
        return 1

    data_hash=sha256(DATA)
    hash_ok=data_hash==EXPECTED_DATA_SHA256
    data=json.loads(read_text(DATA))
    app=read_text(APP)
    service=read_text(SERVICE)

    adrg_groups, adrg_occ=exact_entities(data,"ADRG")
    aadrg_groups, aadrg_occ=exact_entities(data,"AADRG")
    adrg_ids=sorted(adrg_groups)
    aadrg_ids=sorted(aadrg_groups)

    # exact entity_type 기준 분류 상태. projection이 여러 개면 best projection 사용.
    adrg_best={k:choose_best(v) for k,v in adrg_groups.items()}
    aadrg_best={k:choose_best(v) for k,v in aadrg_groups.items()}
    adrg_missing_both=[]
    adrg_partial=[]
    for eid,(p,o) in adrg_best.items():
        c=classification(o)
        d=o.get("detail") if isinstance(o.get("detail"),dict) else {}
        dc=classification(d)
        cc={"codes":c["codes"] or dc["codes"],"labels":c["labels"] or dc["labels"]}
        if not cc["codes"] and not cc["labels"]: adrg_missing_both.append(eid)
        elif bool(cc["codes"]) != bool(cc["labels"]): adrg_partial.append({"id":eid,"class":cc,"path":p})

    aadrg_missing_both=[]
    aadrg_partial=[]
    for eid,(p,o) in aadrg_best.items():
        c=classification(o)
        d=o.get("detail") if isinstance(o.get("detail"),dict) else {}
        dc=classification(d)
        cc={"codes":c["codes"] or dc["codes"],"labels":c["labels"] or dc["labels"]}
        if not cc["codes"] and not cc["labels"]: aadrg_missing_both.append(eid)
        elif bool(cc["codes"]) != bool(cc["labels"]): aadrg_partial.append({"id":eid,"class":cc,"path":p})

    # renderer source exact function audit
    render_rel=function_block(app,"renderRelationDetail")
    render_adrg=function_block(app,"renderAdrgDetail")
    render_derived=function_block(app,"renderDerivedAadrgList")
    current_req=function_block(app,"currentRelationRequest")

    renderer={
        "currentRelationRequest_exact_shape":
            all(x in current_req for x in ["conditions","operator","mdc","classification"]),
        "relation_reads_candidate_summary_abc":
            "candidate.summary?.abc_display_labels" in render_rel or
            "candidate.summary.abc_display_labels" in render_rel,
        "relation_has_derived_aadrg_section":
            "파생 AADRG" in render_rel,
        "renderDerivedAadrgList_exists":bool(render_derived),
        "derived_reads_classification":
            "classification_code" in render_derived and "classification_display_label" in render_derived,
        "renderAdrgDetail_exists":bool(render_adrg),
        "adrg_detail_has_derived_header":"파생 AADRG" in render_adrg,
        "adrg_detail_calls_derived":
            bool(re.search(r"\brenderDerivedAadrgList\s*\(",render_adrg)),
        "adrg_detail_default_closed":
            bool(re.search(r"makeSection\(\s*['\"]파생 AADRG['\"].*?open\s*:\s*false",render_adrg,re.S)),
        "public_search_aadrg_leak":bool(
            re.search(r"SEARCH_ENTITY_TYPES\s*=\s*\[[^\]]*['\"]AADRG['\"]",app,re.S) or
            re.search(r"<option[^>]+value=['\"]AADRG['\"]",app,re.I)
        ),
    }

    # relation service projection source clues
    service_clues=[]
    for needle in ("abc_display_labels","abc_classification_codes","classification_display_label",
                   "aadrg_records","relationSearch"):
        positions=[m.start() for m in re.finditer(re.escape(needle),service)]
        service_clues.append({"needle":needle,"count":len(positions)})

    make_node_probe()
    p=subprocess.run(["node",str(NODE_PROBE.relative_to(ROOT))],cwd=ROOT,text=True,capture_output=True,timeout=180)
    runtime={}
    if NODE_OUT.exists():
        try: runtime=json.loads(read_text(NODE_OUT))
        except Exception as e: runtime={"ok":False,"error":f"parse error: {e}"}
    else:
        runtime={"ok":False,"error":"node output missing","log":((p.stdout or "")+(p.stderr or ""))[-3000:]}

    relation=runtime.get("relation") or {}
    rel_ids=[norm(x) for x in relation.get("result_ids",[])]
    fixture_presence={x:(x in rel_ids) for x in FIXTURE_ADRGS}
    f111_rel_hits=relation.get("fixture",{}).get("F111",[]) if isinstance(relation.get("fixture"),dict) else []

    direct_class=extract_runtime_class((runtime.get("direct") or {}).get("f111"))
    detail_class=extract_runtime_class((runtime.get("detail") or {}).get("f111"))
    relation_class=extract_runtime_class(f111_rel_hits)

    # direct summary에는 code가 없고 labels만 있는 것이 현재 정상 계약일 수 있다.
    direct_labels=direct_class["labels"]
    detail_labels=detail_class["labels"]
    relation_labels=relation_class["labels"]

    root_cause="UNRESOLVED"
    if runtime.get("ok") and fixture_presence.get("F111"):
        if direct_labels and detail_labels and not relation_labels:
            root_cause="RELATION_CANDIDATE_CLASSIFICATION_PROJECTION_MISSING"
        elif direct_labels and relation_labels and set(direct_labels)==set(relation_labels):
            if renderer["relation_reads_candidate_summary_abc"]:
                root_cause="RUNTIME_PAYLOAD_OK_RECHECK_RENDERER_OR_STALE_BUILD"
            else:
                root_cause="RELATION_RENDERER_FIELD_MISMATCH"
        elif relation_labels and set(direct_labels)!=set(relation_labels):
            root_cause="RELATION_CLASSIFICATION_VALUE_MISMATCH"
        else:
            root_cause="RELATION_CLASSIFICATION_PATH_REVIEW"
    elif runtime.get("ok") and not fixture_presence.get("F111"):
        root_cause="FIXTURE_RELATION_RESULT_MISMATCH"
    elif not runtime.get("ok"):
        root_cause="RUNTIME_PROBE_FAILED"

    # validators: permanent coverage status
    coverage={}
    terms=["F111","i214","m6569","abc_display_labels","renderDerivedAadrgList",
           "aadrg_records","SEARCH_ENTITY_TYPES"]
    for vp in VALIDATORS:
        if not vp.exists():
            coverage[str(vp.relative_to(ROOT))]={"exists":False}
        else:
            t=read_text(vp)
            coverage[str(vp.relative_to(ROOT))]={"exists":True,**{x:(x in t) for x in terms}}

    audit_complete = (
        hash_ok and runtime.get("ok") is True and
        renderer["currentRelationRequest_exact_shape"] and
        bool(render_rel) and bool(render_adrg)
    )

    result={
        "stage":"68C_R3",
        "shadow":True,
        "product_files_modified":False,
        "audit_complete":audit_complete,
        "operating_json":{"sha256":data_hash,"expected":EXPECTED_DATA_SHA256,"match":hash_ok},
        "canonical_entity_audit":{
            "method":"entity_type exact match only",
            "adrg_unique":len(adrg_ids),
            "adrg_occurrences":adrg_occ,
            "expected_adrg_unique":EXPECTED_ADRG_COUNT,
            "aadrg_unique":len(aadrg_ids),
            "aadrg_occurrences":aadrg_occ,
            "adrg_missing_both":adrg_missing_both,
            "adrg_partial":adrg_partial,
            "aadrg_missing_both":aadrg_missing_both,
            "aadrg_partial":aadrg_partial,
        },
        "fixture_request":{
            "conditions":[
                {"codeType":"AUTO","code":"i214"},
                {"codeType":"AUTO","code":"m6569"}
            ],
            "operator":"AND","mdc":"","classification":""
        },
        "fixture_presence":fixture_presence,
        "f111_compare":{
            "direct":direct_class,
            "detail":detail_class,
            "relation":relation_class,
            "direct_relation_labels_equal":bool(direct_labels and relation_labels and set(direct_labels)==set(relation_labels)),
        },
        "root_cause":root_cause,
        "renderer":renderer,
        "service_source_clues":service_clues,
        "runtime":runtime,
        "validator_coverage":coverage,
        "next_rule":"68C R3 audit 완료 후 root_cause에 따라 68D Actual 생성. 운영 JSON은 근거 없이 수정 금지."
    }
    REPORT_JSON.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")

    lines=[
        "Stage68C R3 — Exact Relation Classification Shadow Audit",
        "="*64,
        f"audit_complete={'PASS' if audit_complete else 'FAIL'}",
        f"operating_json_sha256={'PASS' if hash_ok else 'FAIL'}",
        f"ADRG exact entity_type unique={len(adrg_ids)} expected={EXPECTED_ADRG_COUNT}",
        f"AADRG exact entity_type unique={len(aadrg_ids)}",
        f"relation_fixture_results={relation.get('result_count')}",
        f"fixture F111/F112/F121/F122={fixture_presence}",
        "",
        "[F111 classification]",
        f"direct={direct_class}",
        f"detail={detail_class}",
        f"relation={relation_class}",
        f"ROOT_CAUSE={root_cause}",
        "",
        "[renderer]",
    ]
    lines += [f"{k}={v}" for k,v in renderer.items()]
    lines += [
        "",
        "[canonical classification quality]",
        f"ADRG missing both={len(adrg_missing_both)} partial={len(adrg_partial)}",
        f"AADRG missing both={len(aadrg_missing_both)} partial={len(aadrg_partial)}",
        "",
        "제품/운영 JSON 수정 없음.",
        "상세 payload와 validator coverage는 audit.json에 저장."
    ]
    REPORT_TXT.write_text("\n".join(lines)+"\n",encoding="utf-8")

    print(f"[{'PASS' if audit_complete else 'FAIL'}] Stage68C R3 exact shadow audit")
    print(f"ADRG_exact={len(adrg_ids)} expected={EXPECTED_ADRG_COUNT} AADRG_exact={len(aadrg_ids)}")
    print(f"relation_results={relation.get('result_count')} fixture={fixture_presence}")
    print(f"F111_direct_labels={direct_labels}")
    print(f"F111_detail_labels={detail_labels}")
    print(f"F111_relation_labels={relation_labels}")
    print(f"ROOT_CAUSE={root_cause}")
    print(f"adrg_detail_calls_derived={renderer['adrg_detail_calls_derived']} "
          f"derived_classification={renderer['derived_reads_classification']} "
          f"public_AADRG_leak={renderer['public_search_aadrg_leak']}")
    print(f"report={REPORT_TXT.relative_to(ROOT)}")
    print(f"json={REPORT_JSON.relative_to(ROOT)}")
    return 0 if audit_complete else 1

if __name__=="__main__":
    sys.exit(main())
