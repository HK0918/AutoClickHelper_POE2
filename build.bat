@echo off
chcp 65001 > nul
echo ========================================
echo   Auto Click Helper - EXE Build
echo ========================================
echo.

echo [1/4] Installing required packages...
python -m pip install --upgrade pip --quiet
python -m pip install pyinstaller opencv-python numpy pyautogui keyboard Pillow pywin32 --quiet
echo Done.

echo.
echo [2/4] Stopping running process if any...
taskkill /f /im AutoClickHelper.exe 2>nul
timeout /t 1 /nobreak > nul

echo.
echo [3/4] Cleaning previous build (exe only)...
if exist build rmdir /s /q build
if exist AutoClickHelper.spec del AutoClickHelper.spec
if exist dist\AutoClickHelper.exe del dist\AutoClickHelper.exe

echo.
echo [4/4] Building EXE (with admin rights)...
python -m PyInstaller ^
  --onefile ^
  --noconsole ^
  --clean ^
  --uac-admin ^
  --name AutoClickHelper ^
  --add-data poe2_tribute_clicker.py;. ^
  --add-data tribute_symbol.png;. ^
  --add-data tribute_lock.png;. ^
  auto_click_helper_ui.py

echo.
if exist dist\AutoClickHelper.exe (
  echo Build successful!
  echo dist\AutoClickHelper.exe is ready.
) else (
  echo Build FAILED. Check errors above.
)
echo.
pause
