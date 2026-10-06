# Aísla los datos de las pruebas antes de que cualquier prueba importe nucleo.
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("MONITOR_DATOS", tempfile.mkdtemp())
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
