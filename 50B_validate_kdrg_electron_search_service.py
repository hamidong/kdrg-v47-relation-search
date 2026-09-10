from __future__ import annotations
import hashlib, json, shutil, subprocess
from pathlib import Path

SCRIPT_VERSION="2026-09-08_KDRG_V47_ELECTRON_STAGE50B_VALIDATOR_V9_AADRG_PUBLIC"
ROOT=Path(__file__).resolve().parent
ELECTRON=ROOT/"electron"
DATA=ROOT/"data/kdrg_v47_search_integrated_v3.json"
REPORT_TXT=ROOT/"reports/electron_stage50b_validation_report.txt"
REPORT_JSON=ROOT/"reports/electron_stage50b_validation_report.json"
EXPECTED_JSON_SHA="1a3d50400567ecaad9695b7be8e7c0382131f8652f398e010cf01f4d8dda6c58"

def sha256(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()

def run(cmd,cwd):
    p=subprocess.run(cmd,cwd=cwd,text=True,capture_output=True)
    return {"returncode":p.returncode,"stdout":p.stdout,"stderr":p.stderr}

def locate_node():
    candidates=[Path("/home/runner/.cache/kdrg-stage50a-node-v22/current/bin/node"),Path.home()/".cache/kdrg-stage50a-node-v22/current/bin/node"]
    found=shutil.which("node")
    if found: candidates.append(Path(found))
    for p in candidates:
        if p.exists() and run([str(p),"--version"],ROOT)["returncode"]==0:
            return str(p)
    return None

def main():
    checks=[]; outputs={}
    def check(name,actual,expected=True):
        checks.append({"name":name,"actual":actual,"expected":expected,"passed":actual==expected})

    check("운영 JSON 존재",DATA.exists(),True)
    check("운영 JSON SHA256",sha256(DATA),EXPECTED_JSON_SHA)
    data=json.loads(DATA.read_text(encoding="utf-8"))
    check("ADRG count",len(data.get("adrg_records",[])),1132)
    check("AADRG count",len(data.get("aadrg_records",[])),1233)
    check("CODE count",len(data.get("code_records",[])),16571)
    check("MDC master count",len(data.get("mdc_master",{}).get("items",[])),26)
    check("dual-role contract",data.get("code_namespace_contract",{}).get("dual_role_literal_count"),60)

    node=locate_node(); check("Node runtime",bool(node),True)
    if node:
        for script in ["tests/validate-stage59b-skeleton.js","tests/validate-stage59b-search.js","tests/validate-stage59b-smoke.js","tests/validate-electron-skeleton.js","tests/validate-search-service.js"]:
            result=run([node,script],ELECTRON); outputs[script]=result; check(script,result["returncode"],0)
        probe = """
const path=require('node:path');
const {KdrgSearchService}=require('./src/kdrg-search-service');
const s=new KdrgSearchService(path.resolve('..','data','kdrg_v47_search_integrated_v3.json'));
if(JSON.stringify(s.status().public_search_types)!==JSON.stringify(['CODE','AADRG'])) throw new Error('public types');
for(const code of ['T601','ADC3A','E011']){
 const row=s.recordMaps.CODE.get(code); if(!row) throw new Error('missing '+code);
 const r=s.search(code,'ALL',{limit:500});
 const expected=new Set(['CODE:'+code,...(row.related_aadrgs||[]).map(x=>'AADRG:'+x)]);
 const actual=new Set(r.results.map(x=>x.entity_type+':'+x.entity_id));
 if(expected.size!==actual.size || [...expected].some(x=>!actual.has(x))) throw new Error('exact projection '+code);
}
const p=s.getDetail('AADRG','P6510').detail;
if(p.adrg!=='P651'||!p.parent_adrg_detail||!('condition_ast' in p)) throw new Error('AADRG inherited condition');
const m=s.recordMaps.CODE.get('M6536');
if(!(m.names||[]).includes('결절성 힘줄병, 아래다리')) throw new Error('diagnosis lost');
if(!(m.names||[]).includes('클립을 사용한 경피적 경도관 승모판 재건술')) throw new Error('procedure lost');
const ns=[...s.recordMaps.CODE.values()].filter(x=>x.namespace_meanings?.diagnosis&&x.namespace_meanings?.procedure);
if(ns.length!==60) throw new Error('dual role '+ns.length);
console.log('[PASS] Stage50B 0.5.10 runtime contract');
"""
        result=run([node,"-e",probe],ELECTRON); outputs["runtime_probe"]=result; check("0.5.10 runtime probe",result["returncode"],0)

    failures=[x for x in checks if not x["passed"]]
    REPORT_TXT.parent.mkdir(parents=True,exist_ok=True)
    lines=["KDRG V4.7 Stage 50B Electron 검색 service 독립검증 - 0.5.10","="*90,f"스크립트 버전: {SCRIPT_VERSION}",""]
    for x in checks: lines.append(f"- [{'PASS' if x['passed'] else 'FAIL'}] {x['name']} | actual={x['actual']} | expected={x['expected']}")
    for name,v in outputs.items(): lines+=["",f"[{name} stdout]",v["stdout"],f"[{name} stderr]",v["stderr"]]
    lines+=["",f"전체 결과: {'PASS' if not failures else 'FAIL'}"]
    REPORT_TXT.write_text("\n".join(lines)+"\n",encoding="utf-8")
    REPORT_JSON.write_text(json.dumps({"script_version":SCRIPT_VERSION,"status":"PASS" if not failures else "FAIL","checks":checks,"outputs":outputs},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    if failures:
        print(f"[FAIL] KDRG Stage 50B Electron 검색 service 검증: {len(checks)-len(failures)} PASS / {len(failures)} FAIL")
        for x in failures: print(f"- {x['name']} | actual={x['actual']} | expected={x['expected']}")
        return 1
    print(f"[PASS] KDRG Stage 50B Electron 검색 service 검증: {len(checks)} PASS / 0 FAIL")
    print(f"report={REPORT_TXT}")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
