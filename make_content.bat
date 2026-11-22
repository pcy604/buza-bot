@echo off
chcp 65001 >nul
rem ---------------------------------------------------------------------
rem  Daily market content builder  (2026-11-23)
rem    Double-click, or run:  make_content.bat        (Korean close)
rem                           make_content.bat us     (US close)
rem
rem  WHY THIS FILE IS ASCII-ONLY  (2026-11-23, measured)
rem    This .bat is UTF-8. cmd reads it with the console codepage, so a
rem    3-byte Korean char is seen as cp949 lead bytes and EATS the next
rem    ASCII char. Real failures observed: "python" -> "n",
rem    "social" -> "ocial". Korean survives only at end-of-line (that is
rem    why stock_screener's old .bat files look fine - their Korean sits
rem    in rem/echo tails). So: no Korean in this file. The Python scripts
rem    print Korean themselves and that works (chcp 65001 + PYTHONIOENCODING).
rem
rem    python / py are Windows Store stubs that HANG. Use the absolute path.
rem    PowerShell has no && operator, which is the other reason for this file.
rem ---------------------------------------------------------------------
setlocal
set PY=%LOCALAPPDATA%\Python\bin\python.exe
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8

if not exist "%PY%" (
  echo [ERROR] python not found: %PY%
  pause
  exit /b 1
)

set KIND=kr
if /i "%~1"=="us" set KIND=daily

echo.
echo ===== [1/3] build content + shorts script  (%KIND%) =====
rem Picking the newest file by date would grab the hand-written drafts
rem (sihwang_*_v2/v3.json). Ask the generator for the exact path instead.
set DOC=
for /f "delims=" %%F in ('""%PY%" -m social.sihwang %KIND% --path-only"') do set DOC=%%F
if not defined DOC (
  echo [ERROR] generator failed
  pause
  exit /b 1
)
echo    file: %DOC%

echo.
echo ===== [2/3] capture dashboard cards  (vertical, ~2 min) =====
"%PY%" -m social.shot cards --mobile
if errorlevel 1 echo [WARN] capture failed - frames will have empty card slots

echo.
echo ===== [3/3] build 1080x1920 shorts frames =====
"%PY%" -m social.frame "%DOC%"

echo.
echo ===== done =====
echo   preview : py -m social dry   "%DOC%" threads
echo   naver   : py -m social naver "%DOC%"
echo   publish : py -m social draft "%DOC%" threads
echo             (telegram preview arrives, then: py -m social approve ^<id^>)
echo.
echo   frames + narration.txt : social\out\frames\
echo.
pause
