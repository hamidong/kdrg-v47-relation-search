# KDRG V4.7 Windows 빌드·회귀검증

## 현재 목적

이 단계는 전체 runtime 데이터가 연결된 PySide 검색기를 Windows에서 빌드하고,
생성된 exe가 즉시 종료되지 않는지 자동으로 확인하는 단계입니다.

- runtime 데이터: `data/kdrg_v47_search_integrated.json`
- ADRG: 1,132개
- TABLE: 1,308개
- 검색 코드: 16,571개
- GUI: PySide6 onefile·windowed exe
- Replit 전용 `reports/qt_native_shim`은 Windows 번들에 포함하지 않습니다.

## 생성·교체 파일

- `kdrg.spec`
- `build_windows.bat`
- `run_local.bat`
- `tests/windows_runtime_source_smoke.py`
- `tests/verify_windows_runtime_bundle.py`
- `.github/workflows/build-windows-release.yml`

## Windows 로컬 빌드

프로젝트 폴더에서 `build_windows.bat`를 실행합니다.

검사 순서:

1. Python 의존성 설치
2. 전체 runtime source smoke
3. PyInstaller onefile GUI 빌드
4. exe 파일·PE 헤더·크기 검증
5. offscreen으로 exe를 실행해 8초 이상 생존하는지 확인

## GitHub Actions 수동 회귀검증

GitHub 저장소의 **Actions** 화면에서
`Build Windows exe and publish Release`를 선택하고
`Run workflow`를 실행합니다.

수동 실행에서는 Windows 빌드와 회귀검증만 수행하며 Release를 생성하지 않습니다.
Actions artifact 임시보관 업로드도 사용하지 않습니다.

## GitHub Release 배포

Release 배포는 `version.py`의 다음 값이 확정된 뒤에만 진행합니다.

- `APP_VERSION`
- `EXE_NAME`
- `GIT_TAG`
- `RELEASE_TITLE`

태그를 푸시하면 workflow가 다음을 순서대로 수행합니다.

1. Windows source runtime smoke
2. PyInstaller 빌드
3. exe 기동검증
4. 태그와 `version.py` 일치 확인
5. GitHub Release 생성
6. exe를 Release Assets에 업로드

## 번들 제외 대상

다음 항목은 exe에 포함하지 않습니다.

- `sources/raw`
- `legacy_reference`
- `reports/qt_native_shim`
- UI preview 이미지
- 원본 PDF·HWPX·XLSX
- GitHub credentials
- build·dist 캐시

## 사용자 Windows 확인 항목

자동검증 통과 후 실제 Windows PC에서 다음을 확인합니다.

1. exe가 설치 없이 실행되는지
2. 콘솔창이 함께 뜨지 않는지
3. 한글 글꼴이 깨지지 않는지
4. 초기 E011 선택과 전체 집계가 정상인지
5. ADRG 검색이 되는지
6. 점이 포함된 상병코드 검색이 되는지
7. TABLE 검색과 상세 관계가 표시되는지
8. physical source·condition usage·runtime related가 구분되는지
9. 창 종료 후 오류창이 뜨지 않는지
