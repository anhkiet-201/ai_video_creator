@echo off
setlocal

REM 1. Neu khong co tham so: mac dinh chay setup.py
if "%~1"=="" (
    python "%~dp0setup.py"
    exit /b %ERRORLEVEL%
)

REM 2. Neu tham so dau tien la update: chay git pull
if /i "%~1"=="update" (
    echo [i] Dang cap nhat AI Video Creator tu Git ^(git pull^)...
    git -C "%~dp0" pull
    exit /b %ERRORLEVEL%
)

set "HAS_SOURCE=0"
for %%A in (%*) do (
    if /i "%%~A"=="--source-folder" set "HAS_SOURCE=1"
)

if "%HAS_SOURCE%"=="1" goto run_with_source
python "%~dp0cli.py" --source-folder "%CD%" %*
goto end

:run_with_source
python "%~dp0cli.py" %*

:end

endlocal

