@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ============================================================
echo    SanitaPoint - Servidor
echo ============================================================
echo.

REM --- 1. Verificar que Python este instalado ---------------------------
where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] No se encontro Python.
  echo.
  echo Instala Python 3.11 o superior desde:
  echo    https://www.python.org/downloads/
  echo IMPORTANTE: marca la casilla "Add Python to PATH" al instalar.
  echo.
  pause
  exit /b 1
)

REM --- 2. Primera ejecucion: crear entorno e instalar dependencias -------
if not exist ".venv\Scripts\python.exe" (
  echo Primera ejecucion detectada.
  echo Creando entorno virtual e instalando dependencias...
  echo (esto solo ocurre la primera vez y puede tardar unos minutos)
  echo.
  python -m venv .venv
  call ".venv\Scripts\activate.bat"
  python -m pip install --upgrade pip
  python -m pip install -r requirements.txt
  if errorlevel 1 (
    echo.
    echo [ERROR] Fallo la instalacion de dependencias. Revisa tu conexion a internet.
    pause
    exit /b 1
  )
) else (
  call ".venv\Scripts\activate.bat"
)

REM --- 3. Mostrar la direccion para las cajas ---------------------------
python -c "import usb.core; import libusb_package; assert libusb_package.get_libusb1_backend() is not None" >nul 2>nul
if errorlevel 1 (
  echo Instalando soporte de impresoras USB...
  python -m pip install "pyusb>=1.2" "libusb-package>=1.0.26"
  if errorlevel 1 (
    echo [AVISO] No se pudo instalar el soporte USB. Revisa la conexion a internet.
  )
)

python -c "import win32print" >nul 2>nul
if errorlevel 1 (
  echo Instalando soporte de impresoras Windows...
  python -m pip install "pywin32>=306"
  if errorlevel 1 (
    echo [AVISO] No se pudo instalar el soporte Windows. Revisa la conexion a internet.
  )
)

echo.
echo ------------------------------------------------------------
echo  Las CAJAS deben abrir en su navegador una de estas URL:
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do (
  set "ip=%%a"
  set "ip=!ip: =!"
  echo      http://!ip!:8000
)
echo  En este mismo equipo tambien sirve:  http://localhost:8000
echo ------------------------------------------------------------
echo.
echo  Para APAGAR el servidor: cierra esta ventana.
echo.

REM --- 4. Abrir el navegador local y arrancar el servidor ---------------
start "" http://localhost:8000
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --reload-dir app

pause
