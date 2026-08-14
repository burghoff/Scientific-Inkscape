@echo off
REM ---- locate Inkscape ------------------------------------------
set "INK="
for /f "delims=" %%I in ('where inkscape.exe 2^>nul') do if not defined INK set "INK=%%I"
if not defined INK for /f "tokens=2*" %%A in ('reg query "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\inkscape.exe" /ve 2^>nul ^| findstr /i "REG_SZ"') do set "INK=%%B"
if not defined INK for /f "tokens=2*" %%A in ('reg query "HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\inkscape.exe" /ve 2^>nul ^| findstr /i "REG_SZ"') do set "INK=%%B"
if not defined INK if exist "%ProgramFiles%\Inkscape\bin\inkscape.exe" set "INK=%ProgramFiles%\Inkscape\bin\inkscape.exe"
if not defined INK if exist "%ProgramFiles(x86)%\Inkscape\bin\inkscape.exe" set "INK=%ProgramFiles(x86)%\Inkscape\bin\inkscape.exe"
if defined INK goto si_ink_found
echo ERROR: could not locate inkscape.exe ^(PATH, App Paths registry, or Program Files^).
pause
exit /b 1
:si_ink_found
for %%I in ("%INK%") do set "INKBIN=%%~dpI"

REM ---- locate Inkscape's Python --------------------------------
set "SIPY=%INKBIN%pythonw.exe"
if not exist "%SIPY%" set "SIPY=%INKBIN%python.exe"
if exist "%SIPY%" goto si_py_found
echo ERROR: no python under "%INKBIN%".
pause
exit /b 1
:si_py_found

REM ---- locate the Scientific Inkscape scripts -------------------
set "SIDIR="
if exist "%~dp0gallery_viewer_script.py" set "SIDIR=%~dp0"
if defined SIDIR goto si_dir_found
set "PROFDIR=%INKSCAPE_PROFILE_DIR%"
if not defined PROFDIR for /f "usebackq delims=" %%I in (`"%INKBIN%inkscape.com" --user-data-directory 2^>nul`) do set "PROFDIR=%%I"
if not defined PROFDIR set "PROFDIR=%APPDATA%\inkscape"
set "EXTDIR=%PROFDIR%\extensions"
if not exist "%EXTDIR%" set "EXTDIR=%APPDATA%\inkscape\extensions"
if exist "%EXTDIR%\gallery_viewer_script.py" set "SIDIR=%EXTDIR%"
if not defined SIDIR for /d %%D in ("%EXTDIR%\*") do if not defined SIDIR if exist "%%D\gallery_viewer_script.py" set "SIDIR=%%D"
if defined SIDIR goto si_dir_found
echo ERROR: could not find gallery_viewer_script.py next to this file or under "%EXTDIR%".
pause
exit /b 1
:si_dir_found

set "PATH=%INKBIN%;%PATH%"
set "SI_INKSCAPE_BFN=%INK%"
cd /d "%SIDIR%"

SET SI_GV_READY=%TEMP%\si_gv_ready.flag

REM Launch detached (settings passed as a base64 arg), then keep
REM this window as a loading indicator until the GUI is up.
del "%SI_GV_READY%" 2>nul
echo Loading Scientific Inkscape Gallery Viewer...
start "" "%SIPY%" "gallery_viewer_script.py" "gASVsAAAAAAAAACMCGFyZ3BhcnNllIwJTmFtZXNwYWNllJOUKYGUfZQojAN0YWKUTowHcG9ydG51bZRNiROMA2lkc5RdlIwOc2VsZWN0ZWRfbm9kZXOUXZSMCGFyZ19maWxllE6MDGlua3NjYXBlX2JmbpSMKkM6XFByb2dyYW0gRmlsZXNcSW5rc2NhcGVcYmluXGlua3NjYXBlLmV4ZZSMB3N5c3BhdGiUXZSMB2luc2hlbGyUiXViLg=="
set /a _si_tries=0
:si_wait
if exist "%SI_GV_READY%" goto si_ready
set /a _si_tries+=1
if %_si_tries% GEQ 120 goto si_ready
ping -n 2 127.0.0.1 >nul
goto si_wait
:si_ready
del "%SI_GV_READY%" 2>nul
