from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Iterable

SCRIPT_VERSION = "2026-07-30_KDRG_V47_CHECKOUT_BYTE_INTEGRITY_VALIDATOR_V3"

ROOT = Path(__file__).resolve().parents[2]

IMMUTABLE_DATA_HASHES = {
    "data/kdrg_v47_search_integrated.json":
        "3de5d6d95cd9cbd16e674f5a4cffcd8bf89da2ee70627501f56d81b05bbe8af1",
    "data/kdrg_v47_ui_semantic_profile.json":
        "c9401fd9d6dcc1253fa2134b22048fe4a73c4c04aeea4d1d86c7fe1504d5456e",
    "data/kdrg_v47_ui_display_contract.json":
        "9976307acd77bb6a0c8a48b2788d055faf563d497381b2c2cacfc7435df0f1ac",
}

OBSERVED_MUTABLE_TEXT_FILES = (
    ".gitattributes",
    "electron/.gitignore",
    "electron/renderer/index.html",
    "electron/renderer/app.js",
    "electron/renderer/styles.css",
)

REQUIRED_ATTRIBUTE_RULES = (
    "* text eol=lf",
    ".gitattributes text eol=lf",
    ".gitignore text eol=lf",
    "*.bat text eol=crlf",
    "*.cmd text eol=crlf",
)

BATCH_SIZE = 40


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_git(args: list[str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
    )


def chunks(items: list[str], size: int) -> Iterable[list[str]]:
    for index in range(0, len(items), size):
        yield items[index:index + size]


def tracked_files() -> list[str]:
    result = run_git(["ls-files", "-z"])
    if result.returncode != 0:
        raise RuntimeError(
            "git ls-files 실패: "
            + result.stderr.decode("utf-8", errors="replace").strip()
        )
    return [
        item.decode("utf-8", errors="surrogateescape")
        for item in result.stdout.split(b"\0")
        if item
    ]


def read_attributes(paths: list[str]) -> dict[str, dict[str, str]]:
    attributes: dict[str, dict[str, str]] = {
        path: {} for path in paths
    }
    for batch in chunks(paths, BATCH_SIZE):
        result = run_git(["check-attr", "-z", "text", "eol", "--", *batch])
        if result.returncode != 0:
            raise RuntimeError(
                "git check-attr 실패: "
                + result.stderr.decode("utf-8", errors="replace").strip()
            )
        parts = result.stdout.split(b"\0")
        if parts and parts[-1] == b"":
            parts.pop()
        if len(parts) % 3 != 0:
            raise RuntimeError(
                f"git check-attr 출력 구조 오류: field_count={len(parts)}"
            )
        for index in range(0, len(parts), 3):
            path = parts[index].decode(
                "utf-8",
                errors="surrogateescape",
            )
            name = parts[index + 1].decode(
                "utf-8",
                errors="replace",
            )
            value = parts[index + 2].decode(
                "utf-8",
                errors="replace",
            )
            attributes.setdefault(path, {})[name] = value
    return attributes


def newline_counts(path: Path) -> tuple[int, int]:
    payload = path.read_bytes()
    crlf = payload.count(b"\r\n")
    bare_cr = payload.replace(b"\r\n", b"").count(b"\r")
    return crlf, bare_cr


def main() -> int:
    failures: list[str] = []
    details: list[str] = []

    attrs_path = ROOT / ".gitattributes"
    if not attrs_path.is_file():
        failures.append(".gitattributes 파일 없음")
        attrs_text = ""
    else:
        attrs_text = attrs_path.read_text(encoding="utf-8")
        missing_rules = [
            rule for rule in REQUIRED_ATTRIBUTE_RULES
            if rule not in attrs_text
        ]
        if missing_rules:
            failures.append(
                ".gitattributes 필수 규칙 누락: "
                + ", ".join(missing_rules)
            )

    try:
        paths = tracked_files()
        attr_map = read_attributes(paths)
    except Exception as exc:
        failures.append(f"{type(exc).__name__}: {exc}")
        paths = []
        attr_map = {}

    text_files = 0
    lf_files = 0
    crlf_policy_files = 0
    binary_files = 0

    for relative in paths:
        path = ROOT / relative
        attrs = attr_map.get(relative, {})
        text_value = attrs.get("text", "unspecified")
        eol_value = attrs.get("eol", "unspecified")

        if text_value == "unset":
            binary_files += 1
            continue

        if text_value != "set":
            failures.append(
                f"텍스트/바이너리 정책 미결정: {relative} "
                f"(text={text_value}, eol={eol_value})"
            )
            continue

        text_files += 1

        if eol_value == "lf":
            lf_files += 1
            if not path.is_file():
                failures.append(f"추적 텍스트 파일 없음: {relative}")
                continue
            crlf, bare_cr = newline_counts(path)
            if crlf or bare_cr:
                failures.append(
                    f"LF 정책 위반: {relative} "
                    f"crlf={crlf} bare_cr={bare_cr}"
                )
        elif eol_value == "crlf":
            crlf_policy_files += 1
            if not relative.lower().endswith((".bat", ".cmd")):
                failures.append(
                    f"예상하지 않은 CRLF 예외: {relative}"
                )
        else:
            failures.append(
                f"EOL 정책 미결정: {relative} "
                f"(text={text_value}, eol={eol_value})"
            )

    observed_files = (
        *OBSERVED_MUTABLE_TEXT_FILES,
        *IMMUTABLE_DATA_HASHES.keys(),
    )
    for relative in observed_files:
        path = ROOT / relative
        attrs = attr_map.get(relative, {})
        actual_eol = attrs.get("eol", "missing")
        if not path.is_file():
            failures.append(f"관찰 대상 파일 없음: {relative}")
            continue
        if actual_eol != "lf":
            failures.append(
                f"관찰 대상 EOL 정책 불일치: {relative} "
                f"actual={actual_eol} expected=lf"
            )
        actual_hash = sha256_file(path)
        crlf, bare_cr = newline_counts(path)
        details.append(
            f"file={relative} sha256={actual_hash} "
            f"crlf={crlf} bare_cr={bare_cr} eol={actual_eol} "
            f"mode={'immutable-data' if relative in IMMUTABLE_DATA_HASHES else 'mutable-eol-only'}"
        )

    for relative, expected_hash in IMMUTABLE_DATA_HASHES.items():
        path = ROOT / relative
        if not path.is_file():
            failures.append(f"불변 데이터 파일 없음: {relative}")
            continue
        actual_hash = sha256_file(path)
        if actual_hash != expected_hash:
            failures.append(
                f"불변 데이터 SHA256 불일치: {relative} "
                f"actual={actual_hash} expected={expected_hash}"
            )

    print(f"validator={SCRIPT_VERSION}")
    print(f"root={ROOT}")
    print(f"tracked={len(paths)}")
    print(f"text={text_files}")
    print(f"lf={lf_files}")
    print(f"crlf_policy={crlf_policy_files}")
    print(f"binary={binary_files}")
    print(f"immutable_data={len(IMMUTABLE_DATA_HASHES)}")
    print(f"mutable_eol_only={len(OBSERVED_MUTABLE_TEXT_FILES)}")
    for line in details:
        print(line)

    if failures:
        print(
            f"[FAIL] checkout byte integrity 검증: "
            f"{len(paths)} tracked / {len(failures)} FAIL"
        )
        for failure in failures:
            print(f"- {failure}")
        return 1

    print(
        f"[PASS] checkout byte integrity 검증: "
        f"{len(paths)} tracked / 0 FAIL"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
