"""Versión web: los datos viven como archivos de texto en la carpeta `datos_web/`
del repositorio de GitHub. Una acción de GitHub los actualiza cada semana y la
app publicada (Streamlit Community Cloud) los carga al iniciar.

datos_web/
  fuentes/scimago_AAAA.csv, fuentes/wos_COLECCION.csv
  enriq.csv, alertas.csv, seguimiento.csv, notas.csv, incentivos.csv, config.json
"""
import base64
import json
import shutil
from pathlib import Path

import pandas as pd
import requests

from . import config, db, fuentes, monitor

DATOS_WEB = config.BASE / "datos_web"
TABLAS = ["enriq", "alertas", "seguimiento", "notas"]


def cargar(con, origen: Path = DATOS_WEB) -> None:
    """Copia datos_web/ a la carpeta de trabajo y reconstruye la base SQLite."""
    config.FUENTES.mkdir(parents=True, exist_ok=True)
    if (origen / "fuentes").exists():
        for f in (origen / "fuentes").iterdir():
            if f.is_file() and not f.name.startswith("."):
                shutil.copy(f, config.FUENTES / f.name)
    for nombre in ["incentivos.csv", "config.json"]:
        if (origen / nombre).exists():
            shutil.copy(origen / nombre, config.DATOS / nombre)
    for t in TABLAS:
        archivo = origen / f"{t}.csv"
        if archivo.exists() and archivo.stat().st_size > 0:
            df = pd.read_csv(archivo, dtype={"rid": str})
            con.execute(f"DELETE FROM {t}")
            df.to_sql(t, con, if_exists="append", index=False)
    for f in config.FUENTES.glob("scimago_*.csv"):
        df, anio = fuentes.leer_scimago(f)
        monitor._guardar_historial(con, df, anio or 0)
    monitor.actualizar_listas(con, config.cargar())
    con.commit()


def guardar(con, destino: Path = DATOS_WEB) -> None:
    """Escribe el estado actual de vuelta a datos_web/ (lo usa la acción de GitHub)."""
    (destino / "fuentes").mkdir(parents=True, exist_ok=True)
    for f in config.FUENTES.iterdir():
        if f.is_file() and not f.name.startswith("."):
            shutil.copy(f, destino / "fuentes" / f.name)
    for t in TABLAS:
        orden = "id" if t == "alertas" else "rid"
        df = pd.read_sql(f"SELECT * FROM {t} ORDER BY {orden}", con)
        if t == "alertas":
            df = df.tail(2000)
        df.to_csv(destino / f"{t}.csv", index=False)
    if config.INCENTIVOS_PATH.exists():
        shutil.copy(config.INCENTIVOS_PATH, destino / "incentivos.csv")


# ---------------------------------------------------------------- GitHub API
class GitHub:
    """Guarda cambios del panel de administración directamente en el repositorio."""

    def __init__(self, token: str, repo: str, rama: str = "main"):
        self.repo, self.rama = repo, rama
        self.h = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}

    def guardar_archivo(self, ruta: str, contenido: bytes, mensaje: str) -> None:
        url = f"https://api.github.com/repos/{self.repo}/contents/{ruta}"
        r = requests.get(url, headers=self.h, params={"ref": self.rama}, timeout=30)
        sha = r.json().get("sha") if r.status_code == 200 else None
        cuerpo = {"message": mensaje, "branch": self.rama,
                  "content": base64.b64encode(contenido).decode()}
        if sha:
            cuerpo["sha"] = sha
        r = requests.put(url, headers=self.h, json=cuerpo, timeout=60)
        r.raise_for_status()

    def ejecutar_actualizacion(self) -> None:
        url = (f"https://api.github.com/repos/{self.repo}/actions/workflows/"
               "actualizar.yml/dispatches")
        r = requests.post(url, headers=self.h, json={"ref": self.rama}, timeout=30)
        r.raise_for_status()


def tabla_csv(con, t: str) -> bytes:
    return pd.read_sql(f"SELECT * FROM {t} ORDER BY rid", con).to_csv(index=False).encode()


def config_publica(cfg: dict) -> bytes:
    """config.json sin contraseñas (las contraseñas van en los secretos de GitHub)."""
    publica = {k: v for k, v in cfg.items() if k not in ("smtp_password", "openalex_api_key",
                                                         "elsevier_api_key")}
    return json.dumps(publica, indent=2, ensure_ascii=False).encode()
