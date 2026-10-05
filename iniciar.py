"""Inicia la app y abre el navegador (sin preguntas de Streamlit en la consola)."""
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path


def puerto_libre(inicio=8501):
    for p in range(inicio, inicio + 20):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:
                return p
    return inicio


def main():
    puerto = puerto_libre()
    base = Path(__file__).resolve().parent
    proc = subprocess.Popen([sys.executable, "-m", "streamlit", "run", str(base / "app.py"),
                             "--server.headless", "true", "--server.port", str(puerto)], cwd=base)
    url = f"http://localhost:{puerto}"
    for _ in range(120):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", puerto)) == 0:
                break
        time.sleep(0.5)
    webbrowser.open(url)
    print(f"\nEl Monitor de Revistas está abierto en {url}\n"
          "Deje esta ventana abierta mientras lo usa. Para salir, ciérrela.\n")
    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()


if __name__ == "__main__":
    main()
