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
if exist "%~dp0autoexporter_script.py" set "SIDIR=%~dp0"
if defined SIDIR goto si_dir_found
set "PROFDIR=%INKSCAPE_PROFILE_DIR%"
if not defined PROFDIR for /f "usebackq delims=" %%I in (`"%INKBIN%inkscape.com" --user-data-directory 2^>nul`) do set "PROFDIR=%%I"
if not defined PROFDIR set "PROFDIR=%APPDATA%\inkscape"
set "EXTDIR=%PROFDIR%\extensions"
if not exist "%EXTDIR%" set "EXTDIR=%APPDATA%\inkscape\extensions"
if exist "%EXTDIR%\autoexporter_script.py" set "SIDIR=%EXTDIR%"
if not defined SIDIR for /d %%D in ("%EXTDIR%\*") do if not defined SIDIR if exist "%%D\autoexporter_script.py" set "SIDIR=%%D"
if defined SIDIR goto si_dir_found
echo ERROR: could not find autoexporter_script.py next to this file or under "%EXTDIR%".
pause
exit /b 1
:si_dir_found

set "PATH=%INKBIN%;%PATH%"
set "SI_INKSCAPE_BFN=%INK%"
cd /d "%SIDIR%"

SET SI_AE_BATCH=%~f0
SET SI_AE_READY=%TEMP%\si_ae_ready.flag

del "%SI_AE_READY%" 2>nul
echo Loading Scientific Inkscape Autoexporter...
start "" "%SIPY%" "autoexporter_script.py" "gASVIQIAAAAAAACMCGFyZ3BhcnNllIwJTmFtZXNwYWNllJOUKYGUfZQojAN0YWKUTowId2F0Y2hkaXKUjACUjAh3cml0ZWRpcpRoB4wGdXNlcGRmlImMBnVzZXBuZ5SJjAZ1c2VlbWaUiYwGdXNlZXBzlImMB3VzZXBzdmeUiYwDZHBplE1YAowKaW1hZ2Vtb2RlMpSIjAh0aGlubGluZZSIjAp0ZXh0dG9wYXRolImMC2JhY2tpbmdyZWN0lIiMCGRhcmttb2RllImMDHN0cm9rZXRvcGF0aJSJjAhsYXRleHBkZpSJjAh0ZXN0bW9kZZSJjAh0ZXN0cGFnZZRLAYwBdpSMAzEuMpSMDnJhc3Rlcml6ZXJtb2RllEsBjA1maW5hbGl6ZXJtb2RllEsBjAZtYXJnaW6URz_gAAAAAAAAjApleHBvcnR3aGF0lEsBjAtleHBvcnR3aGVyZZRLAowDaWRzlF2UjA5zZWxlY3RlZF9ub2Rlc5RdlIwIYXJnX2ZpbGWUTowNcmVkdWNlX2ltYWdlc5SIjAlleHBvcnRub3eUiYwJd2F0Y2hoZXJllImMDHdyaXRldG93YXRjaJSIjAxpbmtzY2FwZV9iZm6UjCpDOlxQcm9ncmFtIEZpbGVzXElua3NjYXBlXGJpblxpbmtzY2FwZS5leGWUjAdmb3JtYXRzlF2UjAdzeXNwYXRolF2UjAdndWl0eXBllIwGZ3RrMy4wlHViLg=="
set /a _si_tries=0
:si_wait
if exist "%SI_AE_READY%" goto si_ready
set /a _si_tries+=1
if %_si_tries% GEQ 120 goto si_ready
ping -n 2 127.0.0.1 >nul
goto si_wait
:si_ready
del "%SI_AE_READY%" 2>nul
