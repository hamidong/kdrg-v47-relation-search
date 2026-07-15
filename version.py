# -*- coding: utf-8 -*-
"""KDRG V4.7 코드 관계 검색기 - 버전 정보 (단일 관리 지점).

이 값을 바꾸면 exe 파일명, Git 태그, Release 제목이 모두 이 값을 기준으로
결정됩니다. README, build_windows.bat, GitHub Actions workflow는 모두 이
파일을 읽어 사용하므로 버전을 올릴 때는 이 파일만 수정하면 됩니다.
"""

from __future__ import annotations

APP_VERSION = "0.1.0"
APP_NAME = "KDRG_V47_Relation_Search"
APP_DISPLAY_NAME = "KDRG V4.7 관계 검색기"

EXE_NAME = f"{APP_NAME}_{APP_VERSION}.exe"
GIT_TAG = f"v{APP_VERSION}"
RELEASE_TITLE = f"KDRG V4.7 관계 검색기 v{APP_VERSION}"


if __name__ == "__main__":
    # CI 스크립트/배치파일에서 값을 뽑아 쓸 수 있도록 인자로 필드명을 받습니다.
    # 예) python version.py EXE_NAME
    import sys

    field = sys.argv[1] if len(sys.argv) > 1 else "APP_VERSION"
    print(globals().get(field, ""))
