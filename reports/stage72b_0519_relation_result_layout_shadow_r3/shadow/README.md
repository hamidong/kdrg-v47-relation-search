# KDRG 코드 관계 검색기 (KDRG V4.7)

코드/ADRG/TABLE/MDC를 검색하고, 여러 개의 코드가 같은 ADRG·같은 조건식 안에서
구조적으로 연결되는지 확인하는 PySide6 데스크톱 도구입니다.

**이 도구는 최종 DRG/질병군을 판정하지 않습니다.** 복수 코드 관계검색 결과는
공식 분류조건 안에서의 연결구조를 보여주는 것이며, 실제 청구·심사에는 반드시
공식 분류집·교정표 원문을 확인해야 합니다.

## 실행 방법

```bash
pip install -r requirements.txt
python main.py
```

## Windows exe 빌드 & 배포

GitHub Actions가 태그 push 시 자동으로 Windows exe를 빌드해서 GitHub
Release Assets에 올립니다. 자세한 순서는 `BUILD_AND_RELEASE.md`를
참고하세요.

- 버전/exe 파일명/Release 제목은 `version.py` 한 곳에서 관리합니다.
- 로컬 Windows PC에서 직접 빌드: `build_windows.bat`
- 개발용 로컬 실행: `run_local.bat`
- PyInstaller spec: `kdrg.spec`

## 프로젝트 구조

```
kdrg-v47/
  main.py                  실행 진입점
  app/
    __init__.py
    models.py               데이터 모델(dataclass) + 문자열/코드 유틸리티
    data_store.py            JSON 기반 데이터 저장소(KDRGDataStore) — 검색/관계검색 로직
    main_window.py           화면 컴포넌트 + MainWindow (검색 결과 카드, 상세화면, 관계검색 UI)
    styles.py                QSS 스타일시트
  data/
    kdrg_v47_ui_fixture.json 파일럿 9개 ADRG UI 데이터 (기존 V4.7 파일럿 JSON 기반)
  tests/
    validate_fixture.py      데이터 무결성 + A/B/C 분류 [별표 1] PDF 대비 검증
    smoke_test_ui.py          오프스크린 GUI 스모크 테스트
    generate_ui_preview.py    1700x960 UI 미리보기 PNG 생성
  reports/
    ui_preview_v47_initial.png  최신 미리보기 결과물
  sources/
    raw/                    공식 원본자료 6종(원본 파일명 그대로, 미가공)
    SOURCE_MANIFEST.md        원본자료 역할·우선순위 설명
  legacy_reference/          v16(KDRG V4.6 세대) 참고자료 — 코드/데이터 소스로 사용 금지
  requirements.txt
  version.py                버전/exe 파일명/Release 제목 단일 관리
  kdrg.spec                  PyInstaller 빌드 스펙
  build_windows.bat          Windows 로컬 exe 빌드 스크립트
  run_local.bat              Windows 로컬 개발 실행 스크립트
  BUILD_AND_RELEASE.md       GitHub Actions/Release 배포 순서 안내
```

저장소 루트의 `.github/workflows/build-windows-release.yml`이 태그 push 시
Windows exe를 빌드해 GitHub Release Assets에 업로드합니다.

`sources/raw/`의 공식 원본 PDF/HWPX 원천자료는 용량이 크고 재배포 대상이
아니므로 이 저장소와 exe 번들에는 포함하지 않습니다(`.gitignore`,
`kdrg.spec` 모두 제외). 원본자료의 역할·우선순위 설명(`sources/SOURCE_MANIFEST.md`)만
저장소에 포함됩니다.

## 검증 실행

```bash
python tests/validate_fixture.py
QT_QPA_PLATFORM=offscreen python tests/smoke_test_ui.py
QT_QPA_PLATFORM=offscreen python tests/generate_ui_preview.py
```

리눅스/오프스크린 환경에서 한글이 깨져 보이면 Noto Sans CJK 계열 폰트를 설치하십시오.
Windows 배포본에서는 OS에 설치된 맑은 고딕이 그대로 사용되어 별도 폰트 설치가 필요 없습니다.

## 데이터 범위와 원칙

- 현재 `data/kdrg_v47_ui_fixture.json`에는 KDRG V4.7 파일럿 9개 ADRG
  (E011, E501, E502, E511, E512, F022, F136, F194, F195)만 포함되어 있습니다.
  분류집 전체(1,282쪽) 파싱과 전체 ADRG 확장은 다음 단계 작업입니다.
- A/B/C 질병군 분류는 `sources/raw/`의 새 **[별표 1] PDF**(상급종합병원의 지정 및 평가
  규정, 제3조제1항 관련)만 근거로 삼습니다. 구 HWP/HWPX 기반 자료나
  `legacy_reference/`의 v16 데이터는 A/B/C 판단에 사용하지 않습니다.
- TABLE 소속(코드가 어느 table에 포함되는지)은 분류집 본문·교정표만 근거로 삼습니다.
  시술목록·질병군명칭 xlsx나 부록 PDF에서 TABLE 소속을 추정하지 않습니다.
- 자세한 우선순위와 파일별 역할은 `sources/SOURCE_MANIFEST.md`를 참고하십시오.

## 다음 단계 (이번 범위 밖)

1. 분류집 본문(1,282쪽)·부록(776쪽) 전체 파싱으로 511개(추정) 전체 ADRG/AADRG 확장
2. 2026-05-01 교정표(HWPX) 개별 교정 항목을 기존 조건식에 반영
3. 시술목록(2,791행)·질병군명칭(2,700행) xlsx로 코드명 표준화 검증
