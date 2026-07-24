@echo off
REM FX Library Client launcher (no Python install needed on this machine)
cd /d "%~dp0"
"C:\Users\Administrator\.workbuddy\binaries\python\envs\default\Scripts\python.exe" main.py
if errorlevel 1 pause
