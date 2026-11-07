@echo off
setlocal
cd /d %~dp0
set "PY=.venv\Scripts\python.exe"
rem CUDA build of PyTorch used when an NVIDIA GPU is found. Change cu128 if your driver is older (see pytorch.org).
set "TORCH_INDEX=https://download.pytorch.org/whl/cu128"

if not exist %PY% (
  echo Creating virtual environment...
  python -m venv .venv
  if errorlevel 1 goto nopython
)

rem Install or update packages whenever requirements.txt changed since the last run.
fc /b requirements.txt .venv\requirements.installed >nul 2>&1
if errorlevel 1 (
  echo Installing packages. The first run can take several minutes...
  %PY% -m pip install --upgrade pip
  where nvidia-smi >nul 2>&1
  if not errorlevel 1 (
    echo NVIDIA GPU detected: installing the CUDA build of PyTorch...
    %PY% -m pip install torch --index-url %TORCH_INDEX% || echo CUDA build not installed, using the default PyTorch instead.
  )
  %PY% -m pip install -r requirements.txt
  if errorlevel 1 goto fail
  copy /y requirements.txt .venv\requirements.installed >nul
)

%PY% app.py
pause
exit /b 0

:nopython
echo Python was not found. Install Python 3.10+ from python.org and tick "Add Python to PATH".
pause
exit /b 1

:fail
echo Package installation failed. Check your internet connection and run this file again.
pause
exit /b 1
