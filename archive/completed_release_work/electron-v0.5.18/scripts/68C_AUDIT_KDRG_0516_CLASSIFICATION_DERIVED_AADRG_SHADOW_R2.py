#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage68C R2 — KDRG 0.5.16 Full Classification + Derived AADRG Shadow Audit

목적
- 제품 파일/운영 JSON을 절대 수정하지 않는 Shadow audit.
- F111 direct/detail/relation 경로와 renderer 참조 필드를 비교한다.
- 1,132 ADRG 및 파생 AADRG의 classification 계약을 전수 점검한다.
- ADRG 상세의 파생 AADRG UI 복원에 필요한 현재 source shape를 확인한다.
- 0.5.15 공개 검색 정책(CODE/ADRG only) 회귀 여부를 점검한다.

주의
- 이 스크립트는 reports/ 아래 보고서만 생성한다.
- 운영 JSON, electron 소스, validator, package 파일은 변경하지 않는다.
- 68C R1의 "원본 ADRG classification 보정"은 수행하지 않는다.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROOT = Path.cwd()
REPORT_DIR = ROOT / "reports" / "stage68c_0516_classification_derived_aadrg_shadow_r2"
REPORT_JSON = REPORT_DIR / "audit.json"
REPORT_TXT = REPORT_DIR / "audit_summary.txt"
NODE_PROBE = REPORT_DIR / "_runtime_probe.js"
NODE_OUT = REPORT_DIR / "_runtime_probe_output.json"

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
EXPECTED_PUBLIC_TYPES = ["CODE", "ADRG"]
GOLDEN_ADRGS = ["F111", "F112", "F121", "F122"]
GOLDEN_CODES = ["i214", "m6569"]

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")

def norm_id(v: Any) -> str:
    return str(v or "").strip().upper()

def first(obj: Any, keys: Iterable[str], default=None):
    if not isinstance(obj, dict):
        return default
    for k in keys:
        if k in obj and obj[k] not in (None, "", [], {}):
            return obj[k]
    return default

def as_list(v: Any) -> List[Any]:
    if v is None:
        return []
    return v if isinstance(v, list) else [v]

def classification(obj: Any) -> Dict[str, Any]:
    if not isinstance(obj, dict):
        return {"codes": [], "labels": [], "raw": {}}
    codes = []
    labels = []
    for k in ("classification_code", "abc_code", "abc_classification", "classification_codes", "abc_codes"):
        for x in as_list(obj.get(k)):
            s = str(x).strip().upper()
            if s and s not in codes:
                codes.append(s)
    for k in ("classification_display_label", "abc_display_label", "abc_display_labels",
              "classification_label", "classification_labels"):
        for x in as_list(obj.get(k)):
            s = str(x).strip()
            if s and s not in labels:
                labels.append(s)
    return {"codes": codes, "labels": labels,
            "raw": {k: obj.get(k) for k in obj if "class" in k.lower() or "abc" in k.lower()}}

def entity_id(obj: Any) -> str:
    return norm_id(first(obj, ("entity_id", "id", "code", "adrg", "aadrg", "group_code", "group_id")))

def walk(obj: Any, path="$"):
    yield path, obj
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk(v, f"{path}[{i}]")

def find_records(data: Any, wanted_type: str) -> List[Tuple[str, dict]]:
    out = []
    seen = set()
    for p, o in walk(data):
        if not isinstance(o, dict):
            continue
        eid = entity_id(o)
        et = norm_id(first(o, ("entity_type", "type", "kind", "record_type")))
        looks = False
        if wanted_type == "ADRG":
            looks = bool(re.fullmatch(r"[A-Z]\d{3}", eid)) and et != "AADRG"
        elif wanted_type == "AADRG":
            looks = bool(re.fullmatch(r"[A-Z]\d{4}", eid))
        if et == wanted_type or looks:
            key = (eid, json.dumps(o, ensure_ascii=False, sort_keys=True, default=str))
            if eid and key not in seen:
                seen.add(key)
                out.append((p, o))
    return out

def best_records(records: List[Tuple[str, dict]]) -> Dict[str, Tuple[str, dict]]:
    # 같은 ID가 여러 projection에 존재하면 classification/child 정보가 많은 레코드를 우선.
    grouped = defaultdict(list)
    for p, o in records:
        grouped[entity_id(o)].append((p, o))
    out = {}
    for eid, xs in grouped.items():
        def score(po):
            p, o = po
            c = classification(o)
            child = first(o, ("aadrg_records", "derived_aadrg", "derived_aadrgs", "children"), [])
            return (bool(c["codes"]) + bool(c["labels"])) * 100 + len(as_list(child)) * 10 + len(o)
        out[eid] = max(xs, key=score)
    return out

def source_shape(text: str) -> Dict[str, Any]:
    needles = [
        "renderAdrgDetail", "renderDerivedAadrgList", "renderAadrgDetail",
        "aadrg_records", "classification_code", "classification_display_label",
        "abc_display_labels", "relationSearch", "SEARCH_ENTITY_TYPES",
        "파생 AADRG", "질병군 분류"
    ]
    return {n: {"present": n in text, "count": text.count(n)} for n in needles}

def extract_function_window(text: str, name: str, radius=6000) -> str:
    m = re.search(rf"\b{name}\b", text)
    if not m:
        return ""
    return text[max(0, m.start()-500): min(len(text), m.start()+radius)]

def run(cmd: List[str], timeout=120) -> Tuple[int, str]:
    try:
        p = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (("\n" + p.stderr) if p.stderr else "")
    except Exception as e:
        return 999, f"{type(e).__name__}: {e}"

def make_runtime_probe() -> None:
    # 서비스 export/호출 형태가 버전별로 달라도 가능한 범위에서 자동 탐색한다.
    js = r"""
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
"""
    NODE_PROBE.write_text(js, encoding="utf-8")

def main() -> int:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    checks = []
    warnings = []
    failures = []

    required = [DATA, SERVICE, APP, CSS, FORMATTERS] + VALIDATORS
    missing = [str(p.relative_to(ROOT)) for p in required if not p.exists()]
    checks.append({"name": "required_files", "pass": not missing, "missing": missing})
    if missing:
        failures.append(f"필수 파일 누락 {len(missing)}개")

    if not DATA.exists() or not SERVICE.exists() or not APP.exists():
        result = {"stage":"68C_R2","shadow":True,"pass":False,"checks":checks,"failures":failures}
        REPORT_JSON.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
        REPORT_TXT.write_text("[FAIL] 필수 파일 누락\n" + "\n".join(missing),encoding="utf-8")
        print(f"[FAIL] Stage68C R2: 필수 파일 누락 {len(missing)}개")
        print(f"report={REPORT_TXT.relative_to(ROOT)}")
        return 1

    data_hash = sha256(DATA)
    hash_ok = data_hash == EXPECTED_DATA_SHA256
    checks.append({"name":"operating_json_sha256","pass":hash_ok,"actual":data_hash,"expected":EXPECTED_DATA_SHA256})
    if not hash_ok:
        failures.append("운영 JSON SHA256이 0.5.15 인계 기준과 다름")

    data = json.loads(read_text(DATA))
    service_text = read_text(SERVICE)
    app_text = read_text(APP)
    css_text = read_text(CSS)
    formatter_text = read_text(FORMATTERS)

    adrg_all = find_records(data, "ADRG")
    aadrg_all = find_records(data, "AADRG")
    adrg = best_records(adrg_all)
    aadrg = best_records(aadrg_all)

    # 데이터 레벨 전수 classification 감사
    adrg_missing_code = []
    adrg_missing_label = []
    adrg_partial = []
    for eid,(p,o) in sorted(adrg.items()):
        c=classification(o)
        if not c["codes"]: adrg_missing_code.append({"id":eid,"path":p,"classification":c})
        if not c["labels"]: adrg_missing_label.append({"id":eid,"path":p,"classification":c})
        if bool(c["codes"]) != bool(c["labels"]): adrg_partial.append({"id":eid,"path":p,"classification":c})

    aadrg_missing_code = []
    aadrg_missing_label = []
    aadrg_partial = []
    for eid,(p,o) in sorted(aadrg.items()):
        c=classification(o)
        if not c["codes"]: aadrg_missing_code.append({"id":eid,"path":p,"classification":c})
        if not c["labels"]: aadrg_missing_label.append({"id":eid,"path":p,"classification":c})
        if bool(c["codes"]) != bool(c["labels"]): aadrg_partial.append({"id":eid,"path":p,"classification":c})

    # ADRG child aadrg_records shape 감사
    derived_total = 0
    derived_missing_id = []
    derived_missing_code = []
    derived_missing_label = []
    adrg_with_children = 0
    child_field_counts = Counter()
    child_fields = ("aadrg_records","derived_aadrg","derived_aadrgs","children")
    for eid,(p,o) in sorted(adrg.items()):
        children = []
        used = None
        for k in child_fields:
            if isinstance(o.get(k), list):
                children=o[k]; used=k; break
        if used:
            child_field_counts[used]+=1
        if children:
            adrg_with_children += 1
        for i,ch in enumerate(children):
            derived_total += 1
            cid=entity_id(ch)
            cc=classification(ch)
            if not cid: derived_missing_id.append({"adrg":eid,"index":i})
            if not cc["codes"]: derived_missing_code.append({"adrg":eid,"aadrg":cid,"classification":cc})
            if not cc["labels"]: derived_missing_label.append({"adrg":eid,"aadrg":cid,"classification":cc})

    # 소스 shape
    source = {
        "service": source_shape(service_text),
        "app": source_shape(app_text),
        "styles": source_shape(css_text),
        "formatters": source_shape(formatter_text),
        "renderAdrgDetail_window": extract_function_window(app_text,"renderAdrgDetail"),
        "renderDerivedAadrgList_window": extract_function_window(app_text,"renderDerivedAadrgList"),
        "relationSearch_window": extract_function_window(service_text,"relationSearch"),
    }

    # 공개 검색 정책 정적 감사
    combined = app_text + "\n" + service_text
    public_contract = {
        "expected": EXPECTED_PUBLIC_TYPES,
        "has_CODE": bool(re.search(r"""['"]CODE['"]""", combined)),
        "has_ADRG": bool(re.search(r"""['"]ADRG['"]""", combined)),
        "search_entity_types_mentions": re.findall(r"SEARCH_ENTITY_TYPES.{0,300}", combined)[:10],
    }
    # AADRG가 내부 detail에 존재하는 것은 정상. 공개 search type 문맥만 좁혀 판정.
    leak_patterns = [
        r"SEARCH_ENTITY_TYPES\s*=\s*\[[^\]]*['\"]AADRG['\"]",
        r"<option[^>]+value=['\"]AADRG['\"]",
        r"data-(?:entity-)?type=['\"]AADRG['\"][^>]*>\s*AADRG",
    ]
    public_aadrg_leaks = []
    for pat in leak_patterns:
        for m in re.finditer(pat, combined, re.I|re.S):
            public_aadrg_leaks.append(m.group(0)[:500])
    public_contract["aadrg_public_leaks"] = public_aadrg_leaks

    # Golden F111 데이터 projection 후보
    golden_static = {}
    for gid in GOLDEN_ADRGS:
        rec = adrg.get(gid)
        golden_static[gid] = None if not rec else {
            "path":rec[0], "classification":classification(rec[1]),
            "child_count":len(as_list(first(rec[1],child_fields,[])))
        }

    # Runtime 4-way probe
    make_runtime_probe()
    rc, node_log = run(["node", str(NODE_PROBE.relative_to(ROOT))], timeout=120)
    runtime = {}
    if NODE_OUT.exists():
        try: runtime=json.loads(read_text(NODE_OUT))
        except Exception as e: runtime={"ok":False,"error":f"probe output parse: {e}"}
    else:
        runtime={"ok":False,"error":"runtime probe output 없음","node_log":node_log[-3000:]}
    runtime_ok = bool(runtime.get("ok"))
    if not runtime_ok:
        warnings.append("runtime 4-way 자동 probe가 현재 service constructor/signature를 자동 인식하지 못함")

    # renderer contract: derived section과 classification 참조가 같은 함수창에 있는지
    derived_window = source["renderDerivedAadrgList_window"]
    detail_window = source["renderAdrgDetail_window"]
    renderer_contract = {
        "renderAdrgDetail_exists": bool(detail_window),
        "renderDerivedAadrgList_exists": bool(derived_window),
        "detail_calls_derived_renderer": bool(re.search(r"renderDerivedAadrgList\s*\(", detail_window)),
        "derived_has_classification_reference": bool(re.search(r"classification|abc_", derived_window, re.I)),
        "derived_has_aadrg_reference": bool(re.search(r"AADRG|aadrg", derived_window)),
        "derived_section_label_present": "파생 AADRG" in app_text,
        "derived_details_default_closed": None,
    }
    if derived_window:
        if re.search(r"<details(?![^>]*\bopen\b)", derived_window, re.I|re.S):
            renderer_contract["derived_details_default_closed"] = True
        elif re.search(r"<details[^>]*\bopen\b", derived_window, re.I|re.S):
            renderer_contract["derived_details_default_closed"] = False

    # validator coverage
    validator_coverage = {}
    terms = ["F111","i214","m6569","renderDerivedAadrgList","aadrg_records",
             "classification_code","classification_display_label","SEARCH_ENTITY_TYPES"]
    for p in VALIDATORS:
        if p.exists():
            t=read_text(p)
            validator_coverage[str(p.relative_to(ROOT))] = {term:(term in t) for term in terms}

    # 현재 R2는 "수정 전 감사"이므로 누락을 발견하는 것이 정상일 수 있다.
    # PASS는 감사 자체가 완결되었는지를 뜻하며 제품 버그가 없다는 뜻이 아니다.
    audit_integrity_pass = (
        not missing and hash_ok and
        bool(adrg) and bool(aadrg) and
        "F111" in adrg and
        bool(detail_window)
    )
    if len(adrg) != 1132:
        warnings.append(f"ADRG unique 탐지={len(adrg)} (인계 기준 1,132와 다름: JSON shape 확인 필요)")
    if not renderer_contract["renderDerivedAadrgList_exists"]:
        warnings.append("현재 app.js에서 renderDerivedAadrgList 함수가 탐지되지 않음")
    if not renderer_contract["detail_calls_derived_renderer"]:
        warnings.append("현재 renderAdrgDetail에서 renderDerivedAadrgList 호출이 탐지되지 않음")
    if not renderer_contract["derived_has_classification_reference"]:
        warnings.append("파생 AADRG renderer에서 classification 참조가 탐지되지 않음")
    if public_aadrg_leaks:
        failures.append("공개 AADRG 검색 노출 가능 패턴 탐지")

    result = {
        "stage":"68C_R2",
        "purpose":"0.5.16 Full Classification + Derived AADRG Shadow Audit",
        "shadow":True,
        "product_files_modified":False,
        "audit_integrity_pass":audit_integrity_pass and not failures,
        "operating_json":{"path":str(DATA.relative_to(ROOT)),"sha256":data_hash,"expected_sha256":EXPECTED_DATA_SHA256},
        "counts":{
            "adrg_unique_detected":len(adrg),
            "aadrg_unique_detected":len(aadrg),
            "adrg_occurrences":len(adrg_all),
            "aadrg_occurrences":len(aadrg_all),
            "adrg_with_derived_children":adrg_with_children,
            "derived_children_total":derived_total,
            "derived_child_field_counts":dict(child_field_counts),
        },
        "classification_audit":{
            "adrg_missing_code":adrg_missing_code,
            "adrg_missing_label":adrg_missing_label,
            "adrg_partial":adrg_partial,
            "aadrg_missing_code":aadrg_missing_code,
            "aadrg_missing_label":aadrg_missing_label,
            "aadrg_partial":aadrg_partial,
            "derived_missing_id":derived_missing_id,
            "derived_missing_code":derived_missing_code,
            "derived_missing_label":derived_missing_label,
        },
        "golden_static":golden_static,
        "runtime_probe":runtime,
        "renderer_contract":renderer_contract,
        "public_search_contract":public_contract,
        "validator_coverage":validator_coverage,
        "source_shape":source,
        "checks":checks,
        "warnings":warnings,
        "failures":failures,
        "next_decision":{
            "rule":"이 결과로 원인을 확정한 뒤에만 68D Actual 적용. 68C R1은 실행하지 않음.",
            "likely_product_files":[
                "electron/src/kdrg-search-service.js (relation projection에서만 분류가 사라질 때)",
                "electron/renderer/app.js (relation renderer 또는 derived AADRG 호출/표시 누락 때)",
                "electron/renderer/styles.css (기존 badge 스타일로 충분하지 않을 때만)"
            ]
        }
    }
    REPORT_JSON.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")

    lines = []
    lines.append("Stage68C R2 — KDRG 0.5.16 Shadow Audit")
    lines.append("="*58)
    lines.append(f"audit_integrity={'PASS' if result['audit_integrity_pass'] else 'FAIL'}")
    lines.append(f"operating_json_sha256={'PASS' if hash_ok else 'FAIL'}")
    lines.append(f"ADRG unique={len(adrg)} / expected=1132")
    lines.append(f"AADRG unique={len(aadrg)}")
    lines.append(f"ADRG with derived children={adrg_with_children}")
    lines.append(f"derived children total={derived_total}")
    lines.append("")
    lines.append("[classification]")
    lines.append(f"ADRG missing code={len(adrg_missing_code)}")
    lines.append(f"ADRG missing label={len(adrg_missing_label)}")
    lines.append(f"ADRG partial(code/label mismatch)={len(adrg_partial)}")
    lines.append(f"AADRG missing code={len(aadrg_missing_code)}")
    lines.append(f"AADRG missing label={len(aadrg_missing_label)}")
    lines.append(f"AADRG partial(code/label mismatch)={len(aadrg_partial)}")
    lines.append(f"derived missing id={len(derived_missing_id)}")
    lines.append(f"derived missing code={len(derived_missing_code)}")
    lines.append(f"derived missing label={len(derived_missing_label)}")
    lines.append("")
    lines.append("[F111/F112/F121/F122 static]")
    for gid in GOLDEN_ADRGS:
        g=golden_static.get(gid)
        lines.append(f"{gid}: {g['classification'] if g else 'NOT_FOUND'}")
    lines.append("")
    lines.append("[runtime 4-way probe]")
    lines.append(f"runtime_probe={'PASS' if runtime_ok else 'REVIEW'}")
    if runtime_ok:
        for k in ("direct","detail","relation"):
            v=runtime.get(k) or {}
            lines.append(f"{k}: available={v.get('available')} F111_hits={len(v.get('f111') or [])}")
    else:
        lines.append(str(runtime.get("error","unknown"))[:1000])
    lines.append("")
    lines.append("[renderer]")
    for k,v in renderer_contract.items():
        lines.append(f"{k}={v}")
    lines.append("")
    lines.append("[public search]")
    lines.append("expected=CODE,ADRG")
    lines.append(f"AADRG public leak patterns={len(public_aadrg_leaks)}")
    lines.append("")
    lines.append("[validator coverage missing]")
    for p,cov in validator_coverage.items():
        miss=[k for k,v in cov.items() if not v]
        lines.append(f"{p}: {', '.join(miss) if miss else 'NONE'}")
    if warnings:
        lines.append("")
        lines.append("[REVIEW]")
        lines.extend(f"- {x}" for x in warnings)
    if failures:
        lines.append("")
        lines.append("[FAIL]")
        lines.extend(f"- {x}" for x in failures)
    lines.append("")
    lines.append("상세 전체 목록은 audit.json 확인. 제품/운영 데이터 수정 없음.")
    REPORT_TXT.write_text("\n".join(lines)+"\n",encoding="utf-8")

    # Shell에는 핵심만.
    print(f"[{'PASS' if result['audit_integrity_pass'] else 'FAIL'}] Stage68C R2 Shadow audit")
    print(f"ADRG={len(adrg)} AADRG={len(aadrg)} derived={derived_total}")
    print(f"ADRG_missing_code={len(adrg_missing_code)} ADRG_missing_label={len(adrg_missing_label)}")
    print(f"AADRG_missing_code={len(aadrg_missing_code)} AADRG_missing_label={len(aadrg_missing_label)}")
    print(f"runtime_probe={'PASS' if runtime_ok else 'REVIEW'}")
    print(f"derived_renderer={renderer_contract['renderDerivedAadrgList_exists']} "
          f"detail_calls_it={renderer_contract['detail_calls_derived_renderer']} "
          f"classification_ref={renderer_contract['derived_has_classification_reference']}")
    print(f"public_AADRG_leak_patterns={len(public_aadrg_leaks)}")
    print(f"report={REPORT_TXT.relative_to(ROOT)}")
    print(f"json={REPORT_JSON.relative_to(ROOT)}")
    return 0 if result["audit_integrity_pass"] else 1

if __name__ == "__main__":
    sys.exit(main())
