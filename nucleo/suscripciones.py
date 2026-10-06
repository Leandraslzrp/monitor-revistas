"""Suscripciones personales a alertas por correo.

La lista de correos se guarda cifrada (datos_web/suscripciones.enc) porque el repositorio es
público. La clave vive solo en los secretos: `clave_suscripciones` en Streamlit y
CLAVE_SUSCRIPCIONES en GitHub Actions (la misma en ambos)."""
import json
import os
import re
from datetime import date, timedelta
from email.message import EmailMessage
from html import escape
from pathlib import Path

import pandas as pd

from .config import BASE

ARCHIVO = BASE / "datos_web" / "suscripciones.enc"
CORREO_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
URL_APP = "https://monitor-revistas.streamlit.app"


def _fernet(clave: str | None):
    from cryptography.fernet import Fernet
    clave = clave or os.environ.get("MONITOR_CLAVE_SUSCRIPCIONES")
    return Fernet(clave.encode()) if clave else None


def nueva_clave() -> str:
    from cryptography.fernet import Fernet
    return Fernet.generate_key().decode()


def cargar(clave: str | None = None, archivo: Path = ARCHIVO) -> list[dict]:
    f = _fernet(clave)
    if f is None or not archivo.exists() or archivo.stat().st_size == 0:
        return []
    return json.loads(f.decrypt(archivo.read_bytes()).decode("utf-8"))


def descifrar(contenido: bytes | None, clave: str | None = None) -> list[dict]:
    if not contenido:
        return []
    return json.loads(_fernet(clave).decrypt(contenido).decode("utf-8"))


def cifrar(lista: list[dict], clave: str | None = None) -> bytes:
    return _fernet(clave).encrypt(json.dumps(lista, ensure_ascii=False).encode("utf-8"))


def agregar(lista: list[dict], correo: str, areas: list[str], revistas: list[str], avisos: list[str]) -> list[dict]:
    correo = correo.strip().lower()
    otras = [s for s in lista if s["correo"] != correo]
    return otras + [{"correo": correo, "areas": areas, "revistas": revistas, "avisos": avisos,
                     "fecha": date.today().isoformat()}]


def quitar(lista: list[dict], correo: str) -> list[dict]:
    return [s for s in lista if s["correo"] != correo.strip().lower()]


# ---------------------------------------------------------------- resumen semanal
AVISOS = {"cambios": "Cambios de cuartil, indexación o cobro en mis revistas y áreas",
          "convocatorias": "Convocatorias abiertas y cierres próximos",
          "nuevas": "Revistas nuevas en mis áreas"}


def resumen(sus: dict, df: pd.DataFrame, alertas: pd.DataFrame, dias: int = 8) -> str | None:
    """HTML del resumen semanal para un suscriptor, o None si no hay nada que contar."""
    areas = set(sus.get("areas") or [])
    revistas = set(sus.get("revistas") or [])
    suyo = df[df["rid"].isin(revistas) | df["carreras"].map(lambda c: bool(areas & set(str(c).split("; "))))]
    rids = set(suyo["rid"])
    desde = (date.today() - timedelta(days=dias)).isoformat()
    recientes = alertas[(alertas["fecha"] >= desde) & alertas["rid"].isin(rids)] if not alertas.empty else alertas
    bloques = []
    avisos = set(sus.get("avisos") or AVISOS)
    if "cambios" in avisos and not recientes.empty:
        cambios = recientes[recientes["tipo"] != "Nueva revista"]
        if not cambios.empty:
            bloques.append(("Cambios en sus revistas", [f"<b>{escape(r.titulo)}</b>: {escape(r.detalle)}"
                                                        for r in cambios.head(40).itertuples()]))
    if "nuevas" in avisos and not recientes.empty:
        nuevas = recientes[recientes["tipo"] == "Nueva revista"]
        if not nuevas.empty:
            bloques.append(("Revistas nuevas en sus áreas", [f"<b>{escape(r.titulo)}</b>: {escape(r.detalle)}"
                                                              for r in nuevas.head(30).itertuples()]))
    if "convocatorias" in avisos:
        conv = suyo[suyo["recepcion_txt"].isin(["Convocatoria abierta", "Número especial abierto"])].copy()
        conv["_lim"] = pd.to_datetime(conv["fecha_limite"], errors="coerce")
        conv = conv[conv["_lim"].notna()].sort_values("_lim").head(15)
        if "alerta" in conv:
            conv = conv[~conv["alerta"].isin(["sospechosa", "descontinuada"])]
        if not conv.empty:
            bloques.append(("Convocatorias abiertas", [
                f'<b><a href="{escape(r.url_instr)}">{escape(r.titulo)}</a></b> ({escape(str(r.cuartil_sjr or "sin cuartil"))}): '
                f'{escape(r.periodo_txt)}' for r in conv.itertuples()]))
    if not bloques:
        return None
    cuerpo = "".join(f"<h3 style='color:#0b2e59'>{t}</h3><ul>" + "".join(f"<li>{x}</li>" for x in xs) + "</ul>"
                     for t, xs in bloques)
    return (f"<div style='font-family:Arial,sans-serif;max-width:640px'><h2 style='color:#0b2e59'>📚 Monitor de "
            f"Revistas · resumen semanal</h2>{cuerpo}<p><a href='{URL_APP}'>Abrir el Monitor de Revistas</a></p>"
            f"<p style='color:#64748b;font-size:12px'>Recibe este correo porque se suscribió en el Monitor de Revistas "
            f"de la FACE (áreas: {escape(', '.join(sorted(areas)) or '—')}). Para darse de baja entre a {URL_APP} "
            f"→ 🔔 Alertas → Recibir por correo.<br>Monitor de Revistas · Universidad del Bío-Bío · Realizado por Darling "
            f"Leandra Salazar Pincheira · Desarrollado con apoyo de IA (Claude, Anthropic)</p></div>")


def enviar_resumenes(con, cfg, clave: str | None = None) -> int:
    """Envía a cada suscriptor su resumen semanal. Devuelve cuántos correos salieron."""
    from . import monitor
    lista = cargar(clave)
    if not lista or not cfg.get("smtp_usuario") or not cfg.get("smtp_password"):
        return 0
    df = monitor.vista(con)
    alertas = pd.read_sql("SELECT * FROM alertas", con)
    enviados = 0
    for sus in lista:
        html_ = resumen(sus, df, alertas)
        if not html_:
            continue
        msg = EmailMessage()
        msg["Subject"] = "Monitor de Revistas FACE: su resumen semanal"
        msg["From"] = cfg.get("remitente") or cfg.get("smtp_usuario")
        msg["To"] = sus["correo"]
        msg.set_content("Abra este correo en un lector que muestre HTML o visite " + URL_APP)
        msg.add_alternative(html_, subtype="html")
        try:
            monitor.enviar_correo(cfg, msg)
            enviados += 1
        except Exception as e:  # un correo malo no detiene a los demás
            print(f"No se pudo enviar a un suscriptor: {e}")
    return enviados
