from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

SCRIPT_VERSION = "2026-07-28_KDRG_V47_PACKAGE_LOCK_REGISTRY_VALIDATOR_V1"
ELECTRON_ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ELECTRON_ROOT / "package-lock.json"
OFFICIAL_HOST = "registry.npmjs.org"
FORBIDDEN_HOST = "package-firewall.replit.local"


def collect_resolved_urls(value: object) -> list[str]:
    urls: list[str] = []
    if isinstance(value, dict):
        resolved = value.get("resolved")
        if isinstance(resolved, str) and resolved.strip():
            urls.append(resolved.strip())
        for child in value.values():
            urls.extend(collect_resolved_urls(child))
    elif isinstance(value, list):
        for child in value:
            urls.extend(collect_resolved_urls(child))
    return urls


def main() -> int:
    if not LOCK_PATH.exists():
        print(f"[FAIL] package-lock 파일이 없습니다: {LOCK_PATH}")
        return 1

    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    urls = collect_resolved_urls(lock)

    internal = [url for url in urls if FORBIDDEN_HOST in url.lower()]
    plain_http = [url for url in urls if url.lower().startswith("http://")]
    non_official = [
        url
        for url in urls
        if urlparse(url).hostname != OFFICIAL_HOST
    ]

    failures: list[str] = []
    if len(urls) < 50:
        failures.append(f"resolved URL 수가 비정상적으로 적습니다: {len(urls)}")
    if internal:
        failures.append(
            f"Replit 내부 registry URL이 남아 있습니다: {len(internal)}건"
        )
    if plain_http:
        failures.append(f"평문 HTTP resolved URL이 남아 있습니다: {len(plain_http)}건")
    if non_official:
        failures.append(
            f"공식 npm registry 외 resolved URL이 남아 있습니다: {len(non_official)}건"
        )

    print(f"validator={SCRIPT_VERSION}")
    print(f"lock={LOCK_PATH}")
    print(f"resolved_total={len(urls)}")
    print(f"official_registry={len(urls) - len(non_official)}")
    print(f"internal_registry={len(internal)}")
    print(f"plain_http={len(plain_http)}")

    if failures:
        print("[FAIL] package-lock registry canonicalization 검증 실패")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print(
        "[PASS] package-lock registry canonicalization 검증: "
        f"{len(urls)} URLs / 0 FAIL"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
