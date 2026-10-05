"""Revistas sospechosas: depredadoras o en listas negras.

Fuente: la lista de Beall, que hoy mantiene Stop Predatory Journals
(github.com/stop-predatory-journals). Tiene tres partes: revistas independientes,
editoriales y revistas secuestradas (sitios falsos que copian el nombre de una revista real).
Las listas se descargan en la actualización semanal y se guardan en datos_web/listas."""
import re
import unicodedata
from urllib.parse import urlparse

import pandas as pd

from .config import BASE

CARPETA = BASE / "datos_web" / "listas"
URL_BASE = ("https://raw.githubusercontent.com/stop-predatory-journals/"
            "stop-predatory-journals.github.io/master/_data/")
ARCHIVOS = {"beall_revistas.csv": "journals.csv", "beall_editoriales.csv": "publishers.csv",
            "secuestradas.csv": "hijacked.csv"}
FUENTE = "Lista de Beall (Stop Predatory Journals)"
URL_FUENTE = "https://predatoryjournals.org"
# Dominios compartidos por muchas revistas: no sirven para identificar a una.
COMPARTIDOS = re.compile(r"(google|wordpress|blogspot|wix|weebly|github|academia|researchgate|"
                         r"ojs|scielo|redalyc|doaj|issn|worldcat|elsevier|springer|wiley|tandfonline|"
                         r"sagepub|emerald|oup|cambridge|jstor|mdpi|frontiersin|hindawi|jst|jstage|"
                         r"sciencedirect|ieee|degruyter|tandf|scielo|redalyc|latindex)\.", re.I)
# Editoriales reconocidas: si una revista suya tiene el mismo nombre que una de la lista, es
# una coincidencia de nombre o una revista que cambió de dueño (la lista no se actualiza).
REPUTADAS = re.compile(r"elsevier|springer|wiley|taylor|francis|routledge|sage|oxford|cambridge|"
                       r"emerald|ieee|acm\b|american chemical|american association for the advancement|"
                       r"de gruyter|walter de gruyter|nature|cell press|mdpi|frontiers|ios press|inderscience|"
                       r"world scientific(?! and)|university press|universi", re.I)


DESCONTINUADA = re.compile(r"\(discontinued\)", re.I)
NIVELES = {"sospechosa": "⚠️ Sospechosa", "descontinuada": "⚠️ Descontinuada en Scopus",
           "suplantada": "⚠️ Cuidado: sitios falsos"}


def descargar(sesion=None, carpeta=CARPETA) -> int:
    """Baja las listas actualizadas. Si alguna falla se conserva la copia anterior."""
    import requests
    sesion = sesion or requests.Session()
    carpeta.mkdir(parents=True, exist_ok=True)
    n = 0
    for local, remoto in ARCHIVOS.items():
        try:
            r = sesion.get(URL_BASE + remoto, timeout=30)
            r.raise_for_status()
            if r.text.count("\n") > 20:  # evita reemplazar la lista por una respuesta vacía
                (carpeta / local).write_text(r.text, encoding="utf-8")
                n += 1
        except Exception as e:
            print(f"No se pudo descargar {remoto}: {e}")
    return n


def normalizar(t) -> str:
    if not isinstance(t, str):
        return ""
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()
    t = t.replace("&", " and ")
    t = re.sub(r"[^a-z0-9]+", " ", t)
    t = re.sub(r"^(the|la|el|les|le|der|die) ", "", t.strip())
    return re.sub(r"\s+", " ", t).strip()


def dominio(u) -> str:
    if not isinstance(u, str) or not u.strip():
        return ""
    u = u.strip()
    if "://" not in u:
        u = "http://" + u
    host = (urlparse(u).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def _leer(nombre) -> pd.DataFrame:
    archivo = CARPETA / nombre
    if not archivo.exists():
        return pd.DataFrame()
    return pd.read_csv(archivo, dtype=str, keep_default_na=False, on_bad_lines="skip")


def _sitio_propio(u) -> str:
    """Dominio de una revista de la lista solo si el sitio es suyo (no una página dentro de otro sitio)."""
    d = dominio(u)
    if not d or COMPARTIDOS.search(d + "."):
        return ""
    ruta = urlparse(u if "://" in u else "http://" + u).path.strip("/")
    return d if ruta.count("/") <= 1 else ""


def cargar_listas() -> dict:
    rev, edi, sec = _leer("beall_revistas.csv"), _leer("beall_editoriales.csv"), _leer("secuestradas.csv")
    listas = {"rev_nombre": {}, "rev_dominio": {}, "edi_nombre": {}, "edi_dominio": {},
              "sec_autentica": {}, "sec_dominio": {}}
    for r in rev.itertuples():
        if len(normalizar(r.name)) >= 8:
            listas["rev_nombre"][normalizar(r.name)] = r.name
        if _sitio_propio(r.url):
            listas["rev_dominio"][_sitio_propio(r.url)] = r.name
    for r in edi.itertuples():
        if len(normalizar(r.name)) >= 6:
            listas["edi_nombre"][normalizar(r.name)] = r.name
        if dominio(r.url) and not COMPARTIDOS.search(dominio(r.url) + "."):
            listas["edi_dominio"][dominio(r.url)] = r.name
    for r in sec.itertuples():
        falsos = [u for u in (r.hijackedurl, r.althijackedurl) if u]
        for nombre in {r.authentic, r.hijacked}:
            if len(normalizar(nombre)) >= 8:
                listas["sec_autentica"][normalizar(nombre)] = (falsos, r.authenticurl)
        for u in falsos:
            if dominio(u):
                listas["sec_dominio"][dominio(u)] = r.hijacked
    return listas


def evaluar(titulo, editorial, web, listas: dict) -> tuple[str, str]:
    """(nivel, motivo). nivel: 'sospechosa', 'descontinuada', 'suplantada' o ''."""
    if isinstance(titulo, str) and DESCONTINUADA.search(titulo):
        return "descontinuada", ("Scopus dejó de indexarla (figura como «discontinued» en Scimago). Scopus "
                                 "retira revistas por problemas de calidad o de ética editorial.")
    t, e, d = normalizar(titulo), normalizar(editorial), dominio(web)
    if d and d in listas["sec_dominio"]:
        return "sospechosa", (f"Su sitio web ({d}) figura como sitio falso que suplanta a "
                              f"«{listas['sec_dominio'][d]}».")
    reputada = isinstance(editorial, str) and bool(REPUTADAS.search(editorial))
    if t and t in listas["rev_nombre"] and len(t.split()) >= 2 and not reputada:
        return "sospechosa", "La revista figura en la lista de revistas depredadoras."
    if d and d in listas["rev_dominio"] and not reputada:
        return "sospechosa", f"Su sitio web ({d}) figura en la lista de revistas depredadoras."
    if e and e in listas["edi_nombre"]:
        return "sospechosa", f"Su editorial ({editorial}) figura en la lista de editoriales depredadoras."
    if d and d in listas["edi_dominio"]:
        return "sospechosa", (f"Su sitio web ({d}) pertenece a una editorial de la lista de editoriales "
                              f"depredadoras ({listas['edi_dominio'][d]}).")
    if t and t in listas["sec_autentica"]:
        falsos, real = listas["sec_autentica"][t]
        sitios = ", ".join(dominio(u) for u in falsos if dominio(u)) or "otros sitios"
        oficial = f" El sitio oficial es {real}." if real else ""
        return "suplantada", (f"Hay sitios falsos que usan el nombre de esta revista ({sitios}). "
                              f"No envíe su artículo ni pague por esos sitios.{oficial}")
    return "", ""


def marcar(df: pd.DataFrame) -> pd.DataFrame:
    listas = cargar_listas()
    if not any(listas.values()):
        df["alerta"], df["alerta_motivo"] = "", ""
        return df
    df["alerta"], df["alerta_motivo"] = zip(*[evaluar(t, e, w, listas) for t, e, w in
                                              zip(df["titulo"], df.get("editorial"), df.get("web"))])
    return df
