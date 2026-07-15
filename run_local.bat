@echo off
REM KDRG V4.7 코드 관계 검색기 - 개발용 로컬 실행 (main.py)

setlocal

where python >nul 2>nul
if errorlevel 1 (
    echo [오류] Python이 설치되어 있지 않습니다. https://www.python.org/downloads/ 에서 설치하세요.
    exit /b 1
)

if not exist ".venv" (
    echo [준비] 가상환경이 없어 새로 만듭니다...
    python -m venv .venv
)

call .venv\Scripts\activate.bat
python -m pip install -r requirements.txt
python main.py

endlocal
