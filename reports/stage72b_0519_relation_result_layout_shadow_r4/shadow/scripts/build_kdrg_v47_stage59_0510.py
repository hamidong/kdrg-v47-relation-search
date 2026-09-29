#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))

def dump(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def canon(value):
    return re.sub(r"[^A-Za-z0-9]", "", str(value or "")).upper()

def uniq(values):
    out, seen = [], set()
    for value in values or []:
        s = str(value or "").strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out

def add_once(row, field, value):
    row.setdefault(field, [])
    if str(value) not in [str(x) for x in row[field]]:
        row[field].append(value)

def must(ok, message):
    if not ok:
        raise RuntimeError(message)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--contract", required=True)
    ap.add_argument("--mdc-source", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    baseline = Path(args.baseline)
    contract_path = Path(args.contract)
    mdc_source_path = Path(args.mdc_source)
    output = Path(args.output)

    contract = load(contract_path)
    mdc_source = load(mdc_source_path)

    must(sha256(baseline) == contract["baseline"]["sha256"],
         "baseline SHA mismatch")
    must(contract["schema_version"] == "KDRG_V47_STAGE59_0510_SOURCE_CONTRACT_V1",
         "source contract schema mismatch")
    must(mdc_source["schema_version"] == "KDRG_V47_STAGE59_0510_MDC_SOURCE_V1",
         "MDC source schema mismatch")

    data = load(baseline)
    tables = {str(x.get("logical_table_id", "")): x for x in data.get("logical_table_records", [])}
    adrgs = {str(x.get("adrg", "")): x for x in data.get("adrg_records", [])}
    codes = {canon(x.get("code")): x for x in data.get("code_records", [])}

    children = {}
    for row in data.get("aadrg_records", []):
        children.setdefault(str(row.get("adrg", "")), []).append(str(row.get("aadrg", "")))
    children = {k: uniq(v) for k, v in children.items()}

    data["mdc_master"] = contract["mdc_master"]

    repaired = []
    for item in contract["safe_boundary_repairs"]:
        table_id = item["table_id"]
        bad = item["removed"]
        table = tables.get(table_id)
        must(table is not None, f"boundary table missing: {table_id}")
        must(canon(bad) in [canon(x) for x in table.get("codes", [])],
             f"boundary code missing before repair: {table_id}/{bad}")
        table["codes"] = [x for x in table.get("codes", []) if canon(x) != canon(bad)]
        table["code_count"] = len(table["codes"])
        repaired.append({"table_id": table_id, "removed": bad})

    m_cfg = contract["m6536"]
    m = codes.get("M6536")
    must(m is not None, "M6536 diagnosis code record missing")
    for required_name in m_cfg["baseline_required_names"]:
        must(required_name in m.get("names", []),
             f"M6536 baseline diagnosis name missing: {required_name}")

    add_once(m, "names", m_cfg["procedure_name"])
    add_once(m, "roles", "procedure")

    for item in m_cfg["targets"]:
        table_id = item["table_id"]
        owner = item["owner_adrg"]
        table = tables.get(table_id)
        must(table is not None, f"M6536 target table missing: {table_id}")
        if "M6536" not in [canon(x) for x in table.get("codes", [])]:
            table.setdefault("codes", []).append("M6536")
        table["code_count"] = len(table["codes"])
        add_once(m, "logical_table_ids", table_id)

        rel = uniq(table.get("related_adrgs", [])) or uniq(table.get("condition_adrgs", [])) or [owner]
        for adrg in rel:
            add_once(m, "related_adrgs", adrg)
            for aadrg in children.get(adrg, []):
                add_once(m, "related_aadrgs", aadrg)

    rows = contract["namespace"]["rows"]
    must(len(rows) == 59, f"namespace source rows={len(rows)} expected=59")
    namespace_count = 0
    for item in rows:
        code = canon(item["code"])
        row = codes.get(code)
        must(row is not None, f"dual-role code missing: {code}")
        row["namespace_meanings"] = {
            "diagnosis": {"names": list(item["operating_names"])},
            "procedure": {"names": [item["procedure_name"]]},
        }
        namespace_count += 1

    m["namespace_meanings"] = {
        "diagnosis": {
            "names": list(m_cfg["diagnosis_names"]),
            "normalized_from": m_cfg["normalized_from"],
        },
        "procedure": {
            "names": [m_cfg["procedure_name"]],
            "classification": m_cfg["classification"],
            "source": m_cfg["source_date"],
        },
    }
    namespace_count += 1
    must(namespace_count == 60, "dual-role namespace final count mismatch")

    data["code_namespace_contract"] = {
        "version": "KDRG_V47_DUAL_ROLE_NAMESPACE_V1",
        "dual_role_literal_count": 60,
        "codes": uniq(list(contract["namespace"]["current_dual_role_codes"]) + ["M6536"]),
    }

    mdc_sets = mdc_source["mdc_to_codes"]
    applied = []
    for adrg, cfg in contract["mdc_structured_targets"].items():
        row = adrgs.get(adrg)
        must(row is not None, f"MDC structured target ADRG missing: {adrg}")
        mdc = cfg["mdc"]
        expected = cfg["code_count"]
        codeset = list(mdc_sets.get(mdc, []))
        must(len(codeset) == expected,
             f"{adrg} MDC {mdc} code_count={len(codeset)} expected={expected}")
        row["mdc_virtual_principal_diagnosis"] = {
            "status": "STRUCTURED",
            "mdc": mdc,
            "code_count": len(codeset),
            "codes": codeset,
            "source": "KDRG V4.7 appendix diagnosis_index.indexes.mdc_to_codes",
        }
        applied.append(adrg)

    for adrg in contract["mdc_review_hold"]:
        must(adrg in adrgs, f"MDC HOLD ADRG missing: {adrg}")
        adrgs[adrg]["mdc_virtual_review_status"] = "HOLD"

    data["stage59b_shadow_contract"] = {
        "version": "STAGE59B_0510_R3",
        "official_correction": "2026-07-31 cumulative only",
        "public_search_types": ["CODE", "AADRG"],
        "primary_user_group": "AADRG",
        "safe_boundary_repairs": repaired,
        "dual_role_literal_count": 60,
        "mdc_structured_targets": list(contract["mdc_structured_targets"]),
        "mdc_review_hold": list(contract["mdc_review_hold"]),
    }

    dump(output, data)
    actual_sha = sha256(output)
    must(actual_sha == contract["output"]["sha256"],
         f"generated SHA mismatch: {actual_sha}")
    print("[PASS] KDRG V4.7 Stage59 0.5.10 canonical data rebuild")
    print(f"output={output}")
    print(f"sha256={actual_sha}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
