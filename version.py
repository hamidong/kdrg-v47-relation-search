# -*- coding: utf-8 -*-
"""KDRG V4.7 코드 관계 검색기 - 버전 정보 (단일 관리 지점).

이 값을 바꾸면 exe 파일명, Git 태그, Release 제목이 모두 이 값을 기준으로
결정됩니다. README, build_windows.bat, GitHub Actions workflow는 모두 이
파일을 읽어 사용하므로 버전을 올릴 때는 이 파일만 수정하면 됩니다.

v0.2.0-dev: UI v0.2 개발 미리보기. main 병합 전까지 유지.
"""

from __future__ import annotations

APP_VERSION = "0.2.0-dev"
APP_NAME = "KDRG_V47_Relation_Search"
APP_DISPLAY_NAME = "KDRG V4.7 관계 검색기"

EXE_NAME = f"{APP_NAME}_{APP_VERSION}.exe"
GIT_TAG = f"v{APP_VERSION}"
RELEASE_TITLE = f"KDRG V4.7 관계 검색기 v{APP_VERSION}"


if __name__ == "__main__":
    # CI 스크립트/배치파일에서 값을 뽑아 쓸 수 있도록 인자로 필드명을 받습니다.
    # 예) python version.py EXE_NAME
    import sys

    # Windows 콘솔 기본 인코딩(cp1252)에서도 한글 출력이 깨지지 않도록 강제 UTF-8 설정
    for _stream_name in ("stdout", "stderr"):
        _stream = getattr(sys, _stream_name, None)
        if _stream is not None and hasattr(_stream, "reconfigure"):
            try:
                _stream.reconfigure(encoding="utf-8")
            except Exception:
                pass

    field = sys.argv[1] if len(sys.argv) > 1 else "APP_VERSION"
    print(globals().get(field, ""))
