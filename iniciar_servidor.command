#!/bin/bash
# Lanzador para macOS (equivalente al .bat de Windows).
# Sirve para probar el sistema en un Mac. Doble clic para ejecutar.
cd "$(dirname "$0")"

echo "============================================================"
echo "   SanitaPoint - Servidor"
echo "============================================================"
echo

# 1. Verificar Python
if ! command -v python3 >/dev/null 2>&1; then
  echo "[ERROR] No se encontro python3. Instala Python 3.11+ desde python.org"
  read -n 1 -s -r -p "Presiona una tecla para salir..."
  exit 1
fi

# 2. Primera ejecucion: crear entorno e instalar dependencias
if [ ! -x ".venv/bin/python" ]; then
  echo "Primera ejecucion: creando entorno virtual e instalando dependencias..."
  python3 -m venv .venv
  source .venv/bin/activate
  python -m pip install --upgrade pip
  pip install -r requirements.txt || { echo "[ERROR] Fallo la instalacion."; read -n 1 -s; exit 1; }
else
  source .venv/bin/activate
fi

# 3. Mostrar la IP local para las cajas
echo
echo "------------------------------------------------------------"
echo " Las CAJAS deben abrir en su navegador:"
IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null)
[ -n "$IP" ] && echo "     http://$IP:8000"
echo " En este mismo equipo:  http://localhost:8000"
echo "------------------------------------------------------------"
echo
echo " Para APAGAR el servidor: pulsa Ctrl+C o cierra esta ventana."
echo

# 4. Abrir navegador y arrancar
( sleep 2 && open http://localhost:8000 ) &
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
