from __future__ import annotations
import hashlib, json, shutil, subprocess, sys
from pathlib import Path

SCRIPT_VERSION="2026-09-21_KDRG_V47_ELECTRON_STAGE50D_VALIDATOR_V12_0513"
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

def _stage65_validate_kdrg_icon_contract():
    import json as _s65_json
    from pathlib import Path as _s65_Path
    import struct as _s65_struct

    _s65_root = _s65_Path(__file__).resolve().parent
    _s65_package = _s65_json.loads(
        (_s65_root / "electron/package.json").read_text(encoding="utf-8")
    )

    _s65_icon = (
        (_s65_package.get("build") or {})
        .get("win", {})
        .get("icon")
    )
    if _s65_icon != "renderer/assets/icon-kdrg-v47.ico":
        raise RuntimeError(
            f"Stage65 icon config mismatch: {_s65_icon!r}"
        )

    _s65_png_path = _s65_root / "electron/renderer/assets/icon-kdrg-v47.png"
    _s65_ico_path = _s65_root / "electron/renderer/assets/icon-kdrg-v47.ico"

    if not _s65_png_path.is_file():
        raise RuntimeError(f"Stage65 PNG missing: {_s65_png_path}")
    if not _s65_ico_path.is_file():
        raise RuntimeError(f"Stage65 ICO missing: {_s65_ico_path}")

    _s65_png = _s65_png_path.read_bytes()
    if _s65_png[:8] != b"\x89PNG\r\n\x1a\n":
        raise RuntimeError("Stage65 PNG signature mismatch")
    if _s65_png[12:16] != b"IHDR":
        raise RuntimeError("Stage65 PNG IHDR missing")
    _s65_width, _s65_height = _s65_struct.unpack(">II", _s65_png[16:24])
    if (_s65_width, _s65_height) != (512, 512):
        raise RuntimeError(
            f"Stage65 PNG size mismatch: {_s65_width}x{_s65_height}"
        )

    _s65_ico = _s65_ico_path.read_bytes()
    if len(_s65_ico) < 6:
        raise RuntimeError("Stage65 ICO too small")
    _s65_reserved, _s65_type, _s65_count = _s65_struct.unpack(
        "<HHH", _s65_ico[:6]
    )
    if (_s65_reserved, _s65_type) != (0, 1):
        raise RuntimeError("Stage65 ICO header mismatch")

    _s65_sizes = set()
    for _s65_index in range(_s65_count):
        _s65_pos = 6 + (_s65_index * 16)
        if _s65_pos + 16 > len(_s65_ico):
            raise RuntimeError("Stage65 ICO directory truncated")

        (
            _s65_w,
            _s65_h,
            _s65_colors,
            _s65_rsv,
            _s65_planes,
            _s65_bits,
            _s65_size,
            _s65_offset,
        ) = _s65_struct.unpack(
            "<BBBBHHII",
            _s65_ico[_s65_pos:_s65_pos + 16],
        )

        _s65_w = 256 if _s65_w == 0 else _s65_w
        _s65_h = 256 if _s65_h == 0 else _s65_h
        if _s65_w != _s65_h:
            raise RuntimeError(
                f"Stage65 ICO non-square frame: {_s65_w}x{_s65_h}"
            )
        if _s65_offset + _s65_size > len(_s65_ico):
            raise RuntimeError(
                f"Stage65 ICO frame outside file: {_s65_w}"
            )
        _s65_sizes.add(_s65_w)

    _s65_expected = {16, 20, 24, 32, 40, 48, 64, 128, 256}
    if _s65_sizes != _s65_expected:
        raise RuntimeError(
            f"Stage65 ICO sizes mismatch: {sorted(_s65_sizes)}"
        )


_stage65_validate_kdrg_icon_contract()


def main():
    checks=[];outputs={}
    def check(name,actual,expected=True): checks.append({"name":name,"actual":actual,"expected":expected,"passed":actual==expected})
    pkg=json.loads((ELECTRON/"package.json").read_text(encoding="utf-8")); lock=json.loads((ELECTRON/"package-lock.json").read_text(encoding="utf-8")); scripts=pkg.get("scripts",{})
    check("운영 JSON SHA",sha256(DATA),EXPECTED_JSON_SHA)
    check("package version",pkg.get("version"),"0.5.13"); check("lock version",lock.get("version"),"0.5.13")
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
    lines=["KDRG V4.7 Stage 50D Electron Windows packaging 독립검증 - 0.5.13","="*92,f"스크립트 버전: {SCRIPT_VERSION}",""]
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
