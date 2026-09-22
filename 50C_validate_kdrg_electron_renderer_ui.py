from __future__ import annotations
import hashlib, json, shutil, subprocess
from pathlib import Path

SCRIPT_VERSION="2026-09-08_KDRG_V47_ELECTRON_STAGE50C_VALIDATOR_V9_AADRG_PUBLIC_UI"
ROOT=Path(__file__).resolve().parent
ELECTRON=ROOT/"electron"
DATA=ROOT/"data/kdrg_v47_search_integrated_v3.json"
REPORT_TXT=ROOT/"reports/electron_stage50c_validation_report.txt"
REPORT_JSON=ROOT/"reports/electron_stage50c_validation_report.json"
EXPECTED_JSON_SHA="1a3d50400567ecaad9695b7be8e7c0382131f8652f398e010cf01f4d8dda6c58"

def sha256(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
    return h.hexdigest()

def run(cmd,cwd):
    if isinstance(cmd, (list, tuple)) and cmd:
        executable = str(cmd[0]).lower()
        if executable in {"npm", "npm.cmd"}:
            resolved = shutil.which("npm.cmd") or shutil.which("npm")
            if resolved:
                cmd = [resolved, *cmd[1:]]
    p=subprocess.run(cmd,cwd=cwd,text=True,capture_output=True)
    return {"returncode":p.returncode,"stdout":p.stdout,"stderr":p.stderr}

def locate_node():
    for p in [Path("/home/runner/.cache/kdrg-stage50a-node-v22/current/bin/node"),Path.home()/".cache/kdrg-stage50a-node-v22/current/bin/node"]:
        if p.exists(): return str(p)
    return shutil.which("node")

def main():
    checks=[]; outputs={}
    def check(name,actual,expected=True): checks.append({"name":name,"actual":actual,"expected":expected,"passed":actual==expected})
    check("운영 JSON SHA",sha256(DATA),EXPECTED_JSON_SHA)
    app=(ELECTRON/"renderer/app.js").read_text(encoding="utf-8")
    html=(ELECTRON/"renderer/index.html").read_text(encoding="utf-8")
    css=(ELECTRON/"renderer/styles.css").read_text(encoding="utf-8")
    fmt=(ELECTRON/"renderer/ui-formatters.js").read_text(encoding="utf-8")
    check("공개 ADRG 검색옵션",'<option value="ADRG">ADRG</option>' in html,True)
    check("공개 AADRG 검색옵션 숨김",'<option value="AADRG">AADRG</option>' not in html,True)
    check("MDC 24/25 제거",'value="24">MDC 24' not in html and 'value="25">MDC 25' not in html,True)
    check("동적 MDC filter","populateMdcFilter" in app,True)
    check("뒤로가기",'id="detail-back"' in html and "pushHistory" in app and "restoreScroll" in app,True)
    check("PDF형 multiline 조건","condition-pretty-expression" in app and "condition-pretty-line" in css,True)
    check("CODE 상세 ADRG 중심","function renderCodeDetail" in app and "'관련 ADRG'" in app,True)
    check("TABLE 기술정보 제거","TABLE 기술 상세" not in app and "table-technical-button" not in app,True)
    check("자동 첫상세 제거","openFirst" not in app,True)
    check("AADRG 상세 조건상속","renderAadrgDetail" in app and "renderUserConditionSummary(detail)" in app,True)
    check("formatter public type","const ordered = ['CODE', 'ADRG'];" in fmt,True)
    check("relation ADRG 중심","makeBadge('ADRG')" in app and "ADRG 상세 보기" in app,True)
    check("관련 AADRG 강조","related-aadrg-section" in css,True)
    node=locate_node(); check("Node runtime",bool(node),True)
    if node:
        for script in ["tests/validate-stage59b-ui.js","tests/validate-stage59b-skeleton.js","tests/validate-renderer-ui.js","tests/validate-stage51c-user-condition-ui.js"]:
            r=run([node,script],ELECTRON); outputs[script]=r; check(script,r["returncode"],0)
    npm=run(["npm","run","check"],ELECTRON); outputs["npm run check"]=npm; check("npm run check",npm["returncode"],0)
    failures=[x for x in checks if not x["passed"]]
    REPORT_TXT.parent.mkdir(parents=True,exist_ok=True)
    lines=["KDRG V4.7 Stage 50C Electron renderer UI 독립검증 - 0.5.10","="*90,f"스크립트 버전: {SCRIPT_VERSION}",""]
    for x in checks: lines.append(f"- [{'PASS' if x['passed'] else 'FAIL'}] {x['name']} | actual={x['actual']} | expected={x['expected']}")
    for name,v in outputs.items(): lines+=["",f"[{name} stdout]",v["stdout"],f"[{name} stderr]",v["stderr"]]
    lines+=["",f"전체 결과: {'PASS' if not failures else 'FAIL'}"]
    REPORT_TXT.write_text("\n".join(lines)+"\n",encoding="utf-8")
    REPORT_JSON.write_text(json.dumps({"script_version":SCRIPT_VERSION,"status":"PASS" if not failures else "FAIL","checks":checks,"outputs":outputs},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    if failures:
        print(f"[FAIL] KDRG Stage 50C Electron renderer UI 검증: {len(checks)-len(failures)} PASS / {len(failures)} FAIL")
        for x in failures: print(f"- {x['name']} | actual={x['actual']} | expected={x['expected']}")
        return 1
    print(f"[PASS] KDRG Stage 50C Electron renderer UI 검증: {len(checks)} PASS / 0 FAIL")
    print(f"report={REPORT_TXT}")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
