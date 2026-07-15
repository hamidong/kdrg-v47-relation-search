@echo off
REM KDRG V4.7 코드 관계 검색기 - Windows 로컬 exe 빌드
REM GitHub Actions와 동일한 절차를 로컬 Windows PC에서 재현합니다.

setlocal

echo [1/5] Python 가상환경 확인...
where python >nul 2>nul
if errorlevel 1 (
    echo [오류] Python이 설치되어 있지 않습니다. https://www.python.org/downloads/ 에서 설치하세요.
    exit /b 1
)

echo [2/5] 의존성 설치 (requirements.txt + pyinstaller)...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller
if errorlevel 1 (
    echo [오류] 의존성 설치에 실패했습니다.
    exit /b 1
)

echo [3/5] 자동검증 실행...
python tests\validate_fixture.py
if errorlevel 1 (
    echo [오류] fixture validator 실패. 빌드를 중단합니다.
    exit /b 1
)

set QT_QPA_PLATFORM=offscreen
python tests\smoke_test_ui.py
if errorlevel 1 (
    echo [오류] GUI smoke test 실패. 빌드를 중단합니다.
    exit /b 1
)
set QT_QPA_PLATFORM=

echo [4/5] PyInstaller 빌드...
python -m PyInstaller --noconfirm --clean kdrg.spec
if errorlevel 1 (
    echo [오류] PyInstaller 빌드에 실패했습니다.
    exit /b 1
)

echo [5/5] 결과 확인...
python tests\verify_release_readiness.py --skip-exe-checks-if-missing=false
if errorlevel 1 (
    echo [오류] 배포 전 정적 검증에 실패했습니다.
    exit /b 1
)

echo.
echo 빌드 완료. dist\ 폴더 안의 exe 파일을 확인하세요.
dir dist

endlocal
