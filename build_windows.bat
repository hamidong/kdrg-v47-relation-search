@echo off
setlocal
cd /d "%~dp0"

echo [1/5] Python dependency install
python -m pip install --upgrade pip
if errorlevel 1 goto :fail
python -m pip install -r requirements.txt
if errorlevel 1 goto :fail
python -m pip install pyinstaller
if errorlevel 1 goto :fail

echo [2/5] Windows source runtime smoke
set QT_QPA_PLATFORM=offscreen
set QT_OPENGL=software
python tests\windows_runtime_source_smoke.py
if errorlevel 1 goto :fail

echo [3/5] PyInstaller build
python -m PyInstaller --noconfirm --clean kdrg.spec
if errorlevel 1 goto :fail

echo [4/5] Bundled exe validation
python tests\verify_windows_runtime_bundle.py --require-exe --launch --launch-seconds 8
if errorlevel 1 goto :fail

echo [5/5] Complete
echo [PASS] Windows exe build and runtime regression completed.
exit /b 0

:fail
echo [FAIL] Windows build stopped. Check the step above.
exit /b 1
