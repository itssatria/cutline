@echo off
cd /d %~dp0
if not exist .venv\Scripts\python.exe (
  echo First run: creating environment and installing packages. This takes a few minutes...
  python -m venv .venv
  .venv\Scripts\python -m pip install --upgrade pip
  .venv\Scripts\python -m pip install -r requirements.txt
)
.venv\Scripts\python app.py
pause
