@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo Installing PyInstaller...
python -m pip install --upgrade pyinstaller

echo Building mflac_mp3_ui.exe ...
python -m PyInstaller --noconfirm --clean --onefile --windowed --name mflac_mp3_ui --hidden-import windnd mflac_mp3_ui.py

if exist "dist\mflac_mp3_ui.exe" (
    if not exist "release" mkdir release
    copy /Y "dist\mflac_mp3_ui.exe" "release\mflac_mp3_ui.exe"
    echo Done: release\mflac_mp3_ui.exe
) else (
    echo Build failed.
    exit /b 1
)

pause
