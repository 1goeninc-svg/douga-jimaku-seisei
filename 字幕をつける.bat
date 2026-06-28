@echo off
chcp 65001 >nul
set PYTHONUTF8=1

rem Drag and drop a video file onto this .bat to generate subtitles (.srt).
rem To also burn subtitles into the video, add  --burn  to the python line below.

if "%~1"=="" (
    echo Please drag and drop a video file onto this .bat icon.
    pause
    exit /b
)

python "%~dp0make_subtitle.py" "%~1"

echo.
echo Done. Press any key to close...
pause >nul
