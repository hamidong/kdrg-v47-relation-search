#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage68C R5 — 0.5.15 Release Parity + Exact Fixture Matrix Shadow Audit

이 단계가 마지막 원인확정용 Shadow audit이다.
- 현재 HEAD/workspace와 electron-v0.5.15 태그의 실제 제품파일을 비교한다.
- normalizeRelationRequest를 포함한 실제 IPC-equivalent 경로를 재현한다.
- i214 + m6569를 AUTO/DIAGNOSIS 및 대소문자 조합으로 확인한다.
- F111 relation candidate가 반환될 때 summary.abc_display_labels 존재 여부를 확인한다.
- 21개 derived AADRG classification_code 누락 레코드의 실제 label을 확인한다.
- 제품파일/운영JSON/태그는 수정하지 않는다.
"""

from __future__ import annotations
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
REPORT_DIR = ROOT / "reports" / "stage68c_0516_release_parity_fixture_matrix_r5"
REPORT_JSON = REPORT_DIR / "audit.json"
REPORT_TXT = REPORT_DIR / "audit_summary.txt"
NODE_PROBE = REPORT_DIR / "_fixture_matrix_probe.js"
NODE_OUT = REPORT_DIR / "_fixture_matrix_probe_output.json"

TAG = "electron-v0.5.15"
EXPECTED_COMMIT = "6e0bc2857ebf6abb482428b90f452d5e07c486ac"

PRODUCT_FILES = [
    "electron/src/kdrg-search-service.js",
    "electron/src/search-result-contract.js",
    "electron/main.js",
    "electron/preload.js",
    "electron/renderer/app.js",
    "electron/renderer/styles.css",
    "electron/renderer/ui-formatters.js",
]

def run(args, check=False):
    p = subprocess.run(args, cwd=ROOT, text=True, capture_output=True)
    if check and p.returncode:
        raise RuntimeError((p.stderr or p.stdout or "").strip())
    return p

def sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def current_bytes(rel: str):
    p = ROOT / rel
    return p.read_bytes() if p.exists() else None

def tag_bytes(rel: str):
    p = subprocess.run(
        ["git", "show", f"{TAG}:{rel}"],
        cwd=ROOT,
        capture_output=True,
    )
    return p.stdout if p.returncode == 0 else None

def text_flags(text: str):
    return {
        "relation_reads_candidate_summary_abc":
            "candidate.summary?.abc_display_labels" in text
            or "candidate.summary.abc_display_labels" in text,
        "render_derived_function_exists":
            "function renderDerivedAadrgList(" in text,
        "adrg_detail_has_derived_header":
            "makeSection('파생 AADRG'" in text
            or 'makeSection("파생 AADRG"' in text,
        "adrg_detail_calls_derived":
            "renderDerivedAadrgList(detail.aadrg_records)" in text,
        "derived_reads_code":
            "summary.classification_code" in text,
        "derived_reads_label":
            "summary.classification_display_label" in text,
    }

def make_node():
    js = r"""
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
"""
    NODE_PROBE.write_text(js, encoding="utf-8")

def main():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    tag_check=run(["git","rev-parse",TAG])
    if tag_check.returncode:
        print(f"[FAIL] {TAG} tag not found")
        return 1
    tag_commit=tag_check.stdout.strip()

    head=run(["git","rev-parse","HEAD"],check=True).stdout.strip()
    status=run(["git","status","--short"],check=True).stdout.splitlines()

    parity={}
    for rel in PRODUCT_FILES:
        cb=current_bytes(rel)
        tb=tag_bytes(rel)
        parity[rel]={
            "current_exists":cb is not None,
            "tag_exists":tb is not None,
            "current_sha256":sha_bytes(cb) if cb is not None else None,
            "tag_sha256":sha_bytes(tb) if tb is not None else None,
            "same":cb is not None and tb is not None and cb==tb,
        }

    current_app=(current_bytes("electron/renderer/app.js") or b"").decode("utf-8","replace")
    tag_app=(tag_bytes("electron/renderer/app.js") or b"").decode("utf-8","replace")
    app_flags={
        "current":text_flags(current_app),
        "tag_0515":text_flags(tag_app),
    }

    make_node()
    p=subprocess.run(
        ["node",str(NODE_PROBE.relative_to(ROOT))],
        cwd=ROOT,text=True,capture_output=True,timeout=180
    )
    if p.returncode or not NODE_OUT.exists():
        log=((p.stdout or "")+"\n"+(p.stderr or ""))[-4000:]
        REPORT_TXT.write_text("[FAIL] node probe\n"+log+"\n",encoding="utf-8")
        print("[FAIL] Stage68C R5 node probe")
        print(f"report={REPORT_TXT.relative_to(ROOT)}")
        return 1

    runtime=json.loads(NODE_OUT.read_text(encoding="utf-8"))
    variants=runtime.get("variants",{})
    derived=runtime.get("derived",{})

    matrix={}
    any_f111=False
    for name,v in variants.items():
        f=(v.get("fixture") or {}).get("F111") if isinstance(v,dict) else None
        matrix[name]={
            "ok":v.get("ok") if isinstance(v,dict) else False,
            "total":v.get("total_count") if isinstance(v,dict) else None,
            "F111":bool(f),
            "F111_labels":((f or {}).get("summary") or {}).get("abc_display_labels",[]),
            "normalized":v.get("normalized") if isinstance(v,dict) else None,
        }
        any_f111 = any_f111 or bool(f)

    current_changed=[k for k,v in parity.items() if not v["same"]]

    # 원인 분류
    current_rel=app_flags["current"]["relation_reads_candidate_summary_abc"]
    tag_rel=app_flags["tag_0515"]["relation_reads_candidate_summary_abc"]
    current_derived=app_flags["current"]["adrg_detail_calls_derived"]
    tag_derived=app_flags["tag_0515"]["adrg_detail_calls_derived"]

    if any_f111:
        labels_present=any(bool(x["F111_labels"]) for x in matrix.values() if x["F111"])
        if labels_present and not tag_rel:
            root="0515_RELATION_RENDERER_DOES_NOT_READ_CLASSIFICATION"
        elif labels_present and tag_rel and not parity["electron/renderer/app.js"]["same"]:
            root="CURRENT_SOURCE_DIFFERS_FROM_0515_CHECK_TAG_RENDERER_BEHAVIOR"
        elif labels_present and tag_rel:
            root="SERVICE_AND_0515_RENDERER_CONTRACT_APPEAR_OK_DEPLOYED_RUNTIME_RECHECK"
        else:
            root="F111_RETURNED_BUT_CLASSIFICATION_PROJECTION_MISSING"
    else:
        root="FIXTURE_NOT_REPRODUCED_BY_CURRENT_SERVICE_ALL_VARIANTS"

    result={
        "stage":"68C_R5",
        "shadow":True,
        "product_files_modified":False,
        "head":head,
        "expected_0515_commit":EXPECTED_COMMIT,
        "head_matches_expected_0515_commit":head==EXPECTED_COMMIT,
        "tag":TAG,
        "tag_commit":tag_commit,
        "tag_matches_expected_0515_commit":tag_commit==EXPECTED_COMMIT,
        "git_status_short":status,
        "product_file_parity":parity,
        "changed_vs_0515":current_changed,
        "app_contract":app_flags,
        "fixture_matrix":matrix,
        "runtime":runtime,
        "root_cause":root,
    }
    REPORT_JSON.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")

    lines=[
        "Stage68C R5 — 0.5.15 Release Parity + Fixture Matrix",
        "="*66,
        f"HEAD={head}",
        f"HEAD_matches_expected_0515={head==EXPECTED_COMMIT}",
        f"TAG_commit={tag_commit}",
        f"TAG_matches_expected_0515={tag_commit==EXPECTED_COMMIT}",
        f"git_status_entries={len(status)}",
        f"changed_product_files_vs_0515={current_changed}",
        "",
        "[app contract: current / tag]",
        f"current={app_flags['current']}",
        f"tag_0515={app_flags['tag_0515']}",
        "",
        "[fixture matrix]",
    ]
    for name,x in matrix.items():
        lines.append(f"{name}: total={x['total']} F111={x['F111']} labels={x['F111_labels']}")
        lines.append(f"  normalized={x['normalized']}")
    lines += [
        "",
        "[code records]",
        f"I214={runtime.get('code_records',{}).get('I214')}",
        f"M6569={runtime.get('code_records',{}).get('M6569')}",
        "",
        "[derived AADRG missing classification_code]",
        f"total_derived={derived.get('total')}",
        f"missing_code_count={derived.get('missing_code_count')}",
    ]
    for row in (derived.get("missing_code_records") or []):
        lines.append(
            f"- {row.get('adrg')} -> {row.get('aadrg')} / "
            f"label={row.get('label')} / status={row.get('abc_status')}"
        )
    lines += [
        "",
        f"ROOT_CAUSE={root}",
        "",
        "제품/운영 JSON/tag 수정 없음.",
    ]
    REPORT_TXT.write_text("\n".join(lines)+"\n",encoding="utf-8")

    print("[PASS] Stage68C R5 release parity + fixture matrix")
    print(f"HEAD_match_0515={head==EXPECTED_COMMIT} TAG_match_0515={tag_commit==EXPECTED_COMMIT}")
    print(f"git_status_entries={len(status)} changed_vs_0515={current_changed}")
    print(
        "app_current="
        f"relation_class={current_rel} derived_call={current_derived} | "
        "tag_0515="
        f"relation_class={tag_rel} derived_call={tag_derived}"
    )
    for name,x in matrix.items():
        print(f"{name}: total={x['total']} F111={x['F111']} labels={x['F111_labels']}")
    print(
        f"derived_missing_code={derived.get('missing_code_count')} "
        f"of {derived.get('total')}"
    )
    print(f"ROOT_CAUSE={root}")
    print(f"report={REPORT_TXT.relative_to(ROOT)}")
    print(f"json={REPORT_JSON.relative_to(ROOT)}")
    return 0

if __name__=="__main__":
    sys.exit(main())
