@echo off
chcp 65001 >nul
title Monitor de Revistas FACE
cd /d "%~dp0"

if exist ".venv\listo.txt" goto iniciar

echo ============================================================
echo   Monitor de Revistas FACE - preparacion (solo la primera vez)
echo ============================================================
set "PY="
call :buscar_python
if defined PY goto crear_entorno

echo.
echo No se encontro Python. Instalandolo automaticamente...
echo (puede tardar 2 o 3 minutos, no cierre esta ventana)
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol='Tls12'; Invoke-WebRequest -UseBasicParsing -Uri 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe' -OutFile '%TEMP%\python-instalador.exe'"
if not exist "%TEMP%\python-instalador.exe" goto sin_python
"%TEMP%\python-instalador.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_launcher=1
call :buscar_python
if not defined PY goto sin_python

:crear_entorno
echo.
echo Instalando los componentes del programa (unos minutos)...
"%PY%" -m venv .venv
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q --upgrade pip
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 (
  echo.
  echo No se pudieron instalar los componentes. Revise su conexion a internet e intente de nuevo.
  pause
  exit /b 1
)
echo listo> ".venv\listo.txt"

rem Acceso directo en el Escritorio
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\Monitor de Revistas.lnk'); $s.TargetPath='%~dp0Iniciar_Windows.bat'; $s.WorkingDirectory='%~dp0'; $s.IconLocation='%SystemRoot%\System32\imageres.dll,186'; $s.Save()" >nul 2>nul
echo Se creo el acceso directo "Monitor de Revistas" en su Escritorio.

:iniciar
echo.
echo Abriendo el Monitor de Revistas en su navegador...
echo Deje esta ventana abierta (puede minimizarla) mientras usa el programa.
".venv\Scripts\python.exe" iniciar.py
pause
exit /b 0

:sin_python
echo.
echo No se pudo instalar Python automaticamente.
echo Instalelo desde https://www.python.org/downloads/ marcando "Add Python to PATH"
echo y vuelva a abrir este archivo.
start https://www.python.org/downloads/
pause
exit /b 1

:buscar_python
for %%V in (313 312 311 310) do (
  if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe"
)
if not defined PY for /f "delims=" %%P in ('py -3 -c "import sys;print(sys.executable)" 2^>nul') do set "PY=%%P"
if not defined PY for /f "delims=" %%P in ('where python 2^>nul ^| find /v /i "WindowsApps"') do if not defined PY set "PY=%%P"
exit /b 0
