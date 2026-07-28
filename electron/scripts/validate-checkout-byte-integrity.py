from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

SCRIPT_VERSION = "2026-07-28_KDRG_V47_CHECKOUT_BYTE_INTEGRITY_VALIDATOR_V1"
ROOT = Path(__file__).resolve().parents[2]

EXPECTED: dict[str, dict[str, Any]] = {
    "data/kdrg_v47_search_integrated.json": {
        "sha256": "3de5d6d95cd9cbd16e674f5a4cffcd8bf89da2ee70627501f56d81b05bbe8af1",
        "schema": "kdrg-v47-search-integrated-v2",
    },
    "data/kdrg_v47_ui_semantic_profile.json": {
        "sha256": "c9401fd9d6dcc1253fa2134b22048fe4a73c4c04aeea4d1d86c7fe1504d5456e",
        "schema": "kdrg-v47-ui-semantic-profile-v1",
    },
    "data/kdrg_v47_ui_display_contract.json": {
        "sha256": "9976307acd77bb6a0c8a48b2788d055faf563d497381b2c2cacfc7435df0f1ac",
        "schema": "kdrg-v47-ui-display-contract-v1",
    },
}


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def main() -> int:
    failures: list[str] = []
    print(f"validator={SCRIPT_VERSION}")
    print(f"root={ROOT}")

    attributes_path = ROOT / ".gitattributes"
    if not attributes_path.is_file():
        failures.append(".gitattributes 없음")
    else:
        attributes = attributes_path.read_text(encoding="utf-8")
        required_rules = (
            "*.json text eol=lf",
            "*.js text eol=lf",
            "*.py text eol=lf",
            "*.yml text eol=lf",
        )
        for rule in required_rules:
            if rule not in attributes:
                failures.append(f".gitattributes 규칙 누락: {rule}")

    for relative, expectation in EXPECTED.items():
        path = ROOT / relative
        if not path.is_file():
            failures.append(f"필수 파일 없음: {relative}")
            continue

        raw = path.read_bytes()
        actual_hash = sha256_bytes(raw)
        crlf_count = raw.count(b"\r\n")
        bare_cr_count = raw.replace(b"\r\n", b"").count(b"\r")

        try:
            payload = json.loads(raw.decode("utf-8"))
            actual_schema = payload.get("meta", {}).get("schema_version")
        except Exception as exc:
            failures.append(f"JSON 파싱 실패: {relative} | {type(exc).__name__}: {exc}")
            actual_schema = None

        print(
            f"file={relative} "
            f"sha256={actual_hash} "
            f"crlf={crlf_count} "
            f"bare_cr={bare_cr_count} "
            f"schema={actual_schema}"
        )

        if actual_hash != expectation["sha256"]:
            failures.append(
                f"SHA256 불일치: {relative} | "
                f"actual={actual_hash} expected={expectation['sha256']}"
            )
        if crlf_count != 0 or bare_cr_count != 0:
            failures.append(
                f"CR 문자 감지: {relative} | "
                f"crlf={crlf_count} bare_cr={bare_cr_count}"
            )
        if actual_schema != expectation["schema"]:
            failures.append(
                f"schema 불일치: {relative} | "
                f"actual={actual_schema} expected={expectation['schema']}"
            )

    if failures:
        print(
            f"[FAIL] checkout byte integrity 검증: "
            f"{len(EXPECTED)} files / {len(failures)} FAIL"
        )
        for failure in failures:
            print(f"- {failure}")
        return 1

    print(
        f"[PASS] checkout byte integrity 검증: "
        f"{len(EXPECTED)} files / 0 FAIL"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
