@echo off
rem clip.cmd: the one command for this repo on Windows (same as ./clip; run it without arguments for help).
setlocal
set "DIR=%~dp0"
set "DIR=%DIR:~0,-1%"
set "PY=%DIR%\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
rem UTF-8 for every open(): transcripts have accented letters, and Windows Python would read them as cp1252
set "PYTHONUTF8=1"
set "PYTHONPATH=%DIR%;%DIR%\clips;%PYTHONPATH%"
"%PY%" -m prep.cli %*
