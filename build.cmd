@echo off
setlocal

pushd "%~dp0"

echo Cleaning stale Cython .c files...
del /f __init__.c loader.c resolver.c backend.c 2>nul
echo Clean done.

echo Building pure-Python wheel...
set CONFIGFLOW_CYTHONIZE=
python -m build
if errorlevel 1 goto :error

echo Building protected wheel (.pyd)...
set CONFIGFLOW_CYTHONIZE=1
python -m build
if errorlevel 1 goto :error

echo Build complete. Artifacts are in %~dp0dist
popd
endlocal
exit /b 0

:error
echo Build failed.
popd
endlocal
exit /b 1
