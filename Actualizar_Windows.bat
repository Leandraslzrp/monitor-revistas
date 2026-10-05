@echo off
rem Actualizacion automatica (para el Programador de tareas de Windows)
cd /d "%~dp0"
".venv\Scripts\python.exe" actualizar.py >> datos\actualizacion.log 2>&1
