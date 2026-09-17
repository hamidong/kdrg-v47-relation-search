from __future__ import annotations
import hashlib, json, shutil, subprocess, sys
from pathlib import Path

SCRIPT_VERSION="2026-09-17_KDRG_V47_ELECTRON_STAGE50D_VALIDATOR_V10_0511"
ROOT=Path(__file__).resolve().parent
ELECTRON=ROOT/"electron"
DATA=ROOT/"data/kdrg_v47_search_integrated_v3.json"
REPORT_TXT=ROOT/"reports/electron_stage50d_validation_report.txt"
REPORT_JSON=ROOT/"reports/electron_stage50d_validation_report.json"
EXPECTED_JSON_SHA="1a3d50400567ecaad9695b7be8e7c0382131f8652f398e010cf01f4d8dda6c58"

def sha256(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
    return h.hexdigest()

def run(cmd,cwd,timeout=1200):
    if isinstance(cmd, (list, tuple)) and cmd:
        executable = str(cmd[0]).lower()
        if executable in {"npm", "npm.cmd"}:
            resolved = shutil.which("npm.cmd") or shutil.which("npm")
            if resolved:
                cmd = [resolved, *cmd[1:]]
    try:
        p=subprocess.run(cmd,cwd=cwd,text=True,capture_output=True,timeout=timeout)
        return {"returncode":p.returncode,"stdout":p.stdout,"stderr":p.stderr}
    except Exception as e:
        return {"returncode":999,"stdout":"","stderr":f"{type(e).__name__}: {e}"}

def locate_node():
    for p in [Path("/home/runner/.cache/kdrg-stage50a-node-v22/current/bin/node"),Path.home()/".cache/kdrg-stage50a-node-v22/current/bin/node"]:
        if p.exists(): return str(p)
    return shutil.which("node")

def main():
    checks=[];outputs={}
    def check(name,actual,expected=True): checks.append({"name":name,"actual":actual,"expected":expected,"passed":actual==expected})
    pkg=json.loads((ELECTRON/"package.json").read_text(encoding="utf-8")); lock=json.loads((ELECTRON/"package-lock.json").read_text(encoding="utf-8")); scripts=pkg.get("scripts",{})
    check("운영 JSON SHA",sha256(DATA),EXPECTED_JSON_SHA)
    check("package version",pkg.get("version"),"0.5.11"); check("lock version",lock.get("version"),"0.5.11")
    check("validate skeleton current",scripts.get("validate:skeleton"),"node tests/validate-stage59b-skeleton.js")
    check("validate search current",scripts.get("validate:search"),"node tests/validate-stage59b-search.js")
    check("validate UI current",scripts.get("validate:ui"),"node tests/validate-stage59b-ui.js")
    check("Stage59B smoke",scripts.get("validate:stage59b-smoke"),"node tests/validate-stage59b-smoke.js")
    check("packaged smoke preserved",scripts.get("validate:smoke-contract"),"node tests/validate-packaged-runtime-smoke.js")
    check("packaging preserved",scripts.get("validate:packaging"),"node tests/validate-packaging-config.js")
    check("check packaging syntax","validate-packaging-config.js" in scripts.get("check",""),True)
    check("check packaged smoke syntax","validate-packaged-runtime-smoke.js" in scripts.get("check",""),True)
    node=locate_node(); check("Node runtime",bool(node),True)
    if node:
        for script in ["tests/validate-packaging-config.js","tests/validate-packaged-runtime-smoke.js","tests/validate-stage59b-skeleton.js","tests/validate-stage59b-search.js","tests/validate-stage59b-ui.js","tests/validate-stage59b-smoke.js"]:
            r=run([node,script],ELECTRON); outputs[script]=r; check(script,r["returncode"],0)
    npm=run(["npm","run","check"],ELECTRON); outputs["npm run check"]=npm; check("npm run check",npm["returncode"],0)
    b=run([sys.executable,"50B_validate_kdrg_electron_search_service.py"],ROOT); outputs["50B"]=b; check("50B independent",b["returncode"],0)
    c=run([sys.executable,"50C_validate_kdrg_electron_renderer_ui.py"],ROOT); outputs["50C"]=c; check("50C independent",c["returncode"],0)
    app=(ELECTRON/"renderer/app.js").read_text(encoding="utf-8"); html=(ELECTRON/"renderer/index.html").read_text(encoding="utf-8")
    check("사용자 검색 유형 CODE·AADRG",'<option value="CODE">코드</option>' in html and '<option value="AADRG">AADRG</option>' in html and '<option value="ADRG">ADRG</option>' not in html,True)
    check("TABLE 기술상세 비노출","TABLE 기술 상세" not in app and "table-technical-button" not in app,True)
    check("AADRG 사용자 결과","makeBadge('AADRG')" in app and "renderAadrgDetail" in app,True)
    check("CODE 상세 관련 AADRG","'관련 AADRG'" in app,True)
    check("history back","pushHistory" in app and "restoreScroll" in app,True)
    failures=[x for x in checks if not x["passed"]]
    REPORT_TXT.parent.mkdir(parents=True,exist_ok=True)
    lines=["KDRG V4.7 Stage 50D Electron Windows packaging 독립검증 - 0.5.11","="*92,f"스크립트 버전: {SCRIPT_VERSION}",""]
    for x in checks: lines.append(f"- [{'PASS' if x['passed'] else 'FAIL'}] {x['name']} | actual={x['actual']} | expected={x['expected']}")
    for name,v in outputs.items(): lines+=["",f"[{name} stdout]",v["stdout"],f"[{name} stderr]",v["stderr"]]
    lines+=["",f"전체 결과: {'PASS' if not failures else 'FAIL'}"]
    REPORT_TXT.write_text("\n".join(lines)+"\n",encoding="utf-8")
    REPORT_JSON.write_text(json.dumps({"script_version":SCRIPT_VERSION,"status":"PASS" if not failures else "FAIL","checks":checks,"outputs":outputs},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    if failures:
        print(f"[FAIL] KDRG Stage 50D Windows packaging 검증: {len(checks)-len(failures)} PASS / {len(failures)} FAIL")
        for x in failures: print(f"- {x['name']} | actual={x['actual']} | expected={x['expected']}")
        return 1
    print(f"[PASS] KDRG Stage 50D Windows packaging 검증: {len(checks)} PASS / 0 FAIL")
    print(f"report={REPORT_TXT}")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
