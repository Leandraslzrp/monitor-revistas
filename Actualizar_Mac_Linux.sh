#!/bin/bash
# Actualización automática (para cron). Ejemplo, todos los lunes a las 7:00:
#   0 7 * * 1 /ruta/a/monitor-revistas/Actualizar_Mac_Linux.sh
cd "$(dirname "$0")"
.venv/bin/python actualizar.py >> datos/actualizacion.log 2>&1
