#!/bin/bash
# Monitor de Revistas FACE: doble clic para abrir
cd "$(dirname "$0")"
if [ ! -f ".venv/listo.txt" ]; then
  echo "=== Monitor de Revistas FACE: preparación (solo la primera vez) ==="
  PY=""
  for c in python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(sys.version_info < (3,10))' 2>/dev/null; then
      PY="$(command -v "$c")"; break
    fi
  done
  if [ -z "$PY" ]; then
    echo "No se encontró Python 3.10 o superior. Descargando el instalador oficial..."
    curl -L -o /tmp/python-instalador.pkg "https://www.python.org/ftp/python/3.12.10/python-3.12.10-macos11.pkg"
    echo "Siga el instalador que se abrirá y, al terminar, vuelva a abrir este archivo."
    open /tmp/python-instalador.pkg
    read -p "Presione Enter para cerrar"; exit 0
  fi
  echo "Instalando los componentes del programa (unos minutos)..."
  "$PY" -m venv .venv && .venv/bin/python -m pip install -q --upgrade pip \
    && .venv/bin/python -m pip install -q -r requirements.txt && echo listo > .venv/listo.txt
  if [ ! -f ".venv/listo.txt" ]; then
    echo "No se pudieron instalar los componentes. Revise su conexión a internet."
    read -p "Presione Enter para cerrar"; exit 1
  fi
fi
echo "Abriendo el Monitor de Revistas en su navegador. Deje esta ventana abierta mientras lo usa."
.venv/bin/python iniciar.py
