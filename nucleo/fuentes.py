"""Lectura de listas de revistas (Scimago/Scopus, Web of Science) y consulta de
APIs abiertas (OpenAlex, DOAJ) y opcionales (Elsevier/Scopus con API key)."""
import csv
import io
import json
import re
import time
from pathlib import Path

import pandas as pd
import requests

UA = {"User-Agent": "MonitorRevistasFACE/1.0 (+uso académico)"}
SCIMAGO_URL = "https://www.scimagojr.com/journalrank.php?out=xls"
OPENALEX_URL = "https://api.openalex.org/sources"
DOAJ_URL = "https://doaj.org/api/search/journals/issn:{issn}"
ELSEVIER_URL = "https://api.elsevier.com/content/serial/title/issn/{issn}"


# ---------------------------------------------------------------- utilidades
def normalizar_issn(texto) -> list[str]:
    """'15420000, 0022-238X' -> ['1542-0000', '0022-238X']"""
    if texto is None or (isinstance(texto, float) and pd.isna(texto)):
        return []
    limpio = re.sub(r"[^0-9Xx,; ]", "", str(texto)).upper()
    salida = []
    for parte in re.split(r"[,; ]+", limpio):
        if len(parte) == 8:
            salida.append(f"{parte[:4]}-{parte[4:]}")
    return salida


def _num(serie: pd.Series) -> pd.Series:
    return pd.to_numeric(serie.astype(str).str.replace(",", ".", regex=False).str.strip(),
                         errors="coerce")


def _leer_tabla(origen) -> pd.DataFrame:
    """Lee CSV/TSV/XLSX buscando la fila de encabezado que contiene 'ISSN'
    (los exportes de Clarivate traen líneas de título antes del encabezado)."""
    nombre = getattr(origen, "name", str(origen)).lower()
    if nombre.endswith((".xlsx", ".xls")):
        crudo = pd.read_excel(origen, header=None, dtype=str)
        fila = next((i for i, r in crudo.iterrows()
                     if any("issn" in str(v).lower() for v in r.values)), 0)
        df = crudo.iloc[fila + 1:].copy()
        df.columns = [str(c).strip() for c in crudo.iloc[fila]]
        return df.reset_index(drop=True)
    datos = origen.read() if hasattr(origen, "read") else Path(origen).read_bytes()
    if isinstance(datos, bytes):
        for enc in ("utf-8-sig", "latin-1"):
            try:
                texto = datos.decode(enc)
                break
            except UnicodeDecodeError:
                continue
    else:
        texto = datos
    lineas = texto.splitlines()
    inicio = next((i for i, l in enumerate(lineas[:30]) if "issn" in l.lower()), 0)
    cuerpo = "\n".join(lineas[inicio:])
    try:
        sep = csv.Sniffer().sniff(lineas[inicio], delimiters=",;\t").delimiter
    except csv.Error:
        sep = ","
    return pd.read_csv(io.StringIO(cuerpo), sep=sep, dtype=str, on_bad_lines="skip")


def _col(df: pd.DataFrame, *patrones: str):
    """Primera columna cuyo nombre (minúsculas) coincide con algún regex."""
    for p in patrones:
        for c in df.columns:
            if re.fullmatch(p, str(c).strip().lower()):
                return c
    return None


# ---------------------------------------------------------------- Scimago
def descargar_scimago(destino: Path, anio: int | None = None) -> Path:
    url = SCIMAGO_URL + (f"&year={anio}" if anio else "")
    navegador = {
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/140.0 Safari/537.36"),
        "Accept": "text/csv,text/html,application/xhtml+xml,*/*;q=0.8",
        "Accept-Language": "es-CL,es;q=0.9,en;q=0.8",
        "Referer": "https://www.scimagojr.com/journalrank.php",
    }
    s = requests.Session()
    s.get("https://www.scimagojr.com/journalrank.php", headers=navegador, timeout=60)
    r = s.get(url, headers=navegador, timeout=180)
    r.raise_for_status()
    if b";" not in r.content[:2000]:
        raise ValueError("Scimago no devolvió un CSV (posible bloqueo). "
                         "Descárguelo manualmente desde scimagojr.com y súbalo en la app.")
    destino.write_bytes(r.content)
    return destino


def leer_scimago(origen) -> tuple[pd.DataFrame, int | None]:
    """Devuelve (tabla normalizada, año de los datos)."""
    df = _leer_tabla(origen)
    anio = None
    for c in df.columns:
        m = re.fullmatch(r"total docs\.? \((\d{4})\)", str(c).strip().lower())
        if m:
            anio = int(m.group(1))
    mapa = {
        "sourceid": _col(df, r"sourceid"),
        "titulo": _col(df, r"title"),
        "tipo": _col(df, r"type"),
        "issn_txt": _col(df, r"issn"),
        "editorial": _col(df, r"publisher"),
        "acceso_abierto": _col(df, r"open access"),
        "diamante": _col(df, r"open access diamond"),
        "sjr": _col(df, r"sjr"),
        "cuartil_sjr": _col(df, r"sjr best quartile"),
        "h_index": _col(df, r"h index"),
        "docs_anio": _col(df, r"total docs\.? \(\d{4}\)"),
        "docs_3y": _col(df, r"total docs\.? \(3years\)"),
        "refs": _col(df, r"total refs\.?"),
        "citas_3y": _col(df, r"total (cites|citations) \(3years\)"),
        "citables_3y": _col(df, r"citable docs\.? \(3years\)"),
        "citas_doc_2y": _col(df, r"(cites|citations) / doc\.? \(2years\)"),
        "pais": _col(df, r"country"),
        "region": _col(df, r"region"),
        "cobertura": _col(df, r"coverage"),
        "categorias": _col(df, r"categories"),
        "areas": _col(df, r"areas"),
    }
    if not mapa["titulo"] or not mapa["issn_txt"]:
        raise ValueError("El archivo no parece ser un CSV de Scimago (faltan Title/Issn).")
    out = pd.DataFrame({k: df[v] if v else None for k, v in mapa.items()})
    for c in ["sjr", "h_index", "docs_anio", "docs_3y", "refs", "citas_3y",
              "citables_3y", "citas_doc_2y"]:
        out[c] = _num(out[c])
    out["cuartil_sjr"] = out["cuartil_sjr"].where(out["cuartil_sjr"].isin(["Q1", "Q2", "Q3", "Q4"]))
    out["issns"] = out["issn_txt"].map(lambda t: ",".join(normalizar_issn(t)))
    out = out.drop(columns="issn_txt")
    return out, anio


# ---------------------------------------------------------------- Web of Science
COLECCIONES_WOS = ["SCIE", "SSCI", "AHCI", "ESCI"]


def detectar_coleccion(nombre_archivo: str) -> str | None:
    n = nombre_archivo.upper()
    for c in COLECCIONES_WOS:
        if c in n:
            return c
    if "JCR" in n:
        return "JCR"
    return None


def leer_wos(origen) -> pd.DataFrame:
    """Lee la Master Journal List de Clarivate (gratuita, una por colección) o un
    exporte del JCR (requiere licencia; incluye JIF y cuartil JIF)."""
    df = _leer_tabla(origen)
    c_tit = _col(df, r"journal (title|name)", r"title", r"full journal title")
    c_issn = _col(df, r"issn", r"print issn")
    c_eissn = _col(df, r"eissn", r"e-issn", r"electronic issn")
    c_cat = _col(df, r"web of science categories", r"categor(y|ies)")
    c_edic = _col(df, r"edition")
    c_jif = _col(df, r"\d{4} jif", r"jif", r"journal impact factor")
    c_q = _col(df, r"jif quartile", r"quartile")
    if not c_tit or not (c_issn or c_eissn):
        raise ValueError("El archivo no parece una lista de Web of Science (faltan título/ISSN).")
    out = pd.DataFrame({"titulo": df[c_tit]})
    out["issns"] = [",".join(normalizar_issn(f"{a or ''},{b or ''}"))
                    for a, b in zip(df[c_issn] if c_issn else [""] * len(df),
                                    df[c_eissn] if c_eissn else [""] * len(df))]
    out["wos_categorias"] = df[c_cat] if c_cat else None
    out["wos_edicion"] = df[c_edic] if c_edic else None
    out["jif"] = _num(df[c_jif]) if c_jif else None
    out["jif_cuartil"] = df[c_q].where(df[c_q].isin(["Q1", "Q2", "Q3", "Q4"])) if c_q else None
    return out[out["issns"] != ""].reset_index(drop=True)


# ---------------------------------------------------------------- OpenAlex
def consultar_openalex(issns: list[str], email: str = "", api_key: str = "",
                       sesion: requests.Session | None = None) -> dict[str, dict]:
    """Consulta OpenAlex en lotes de 50 ISSN. Devuelve {issn: datos}."""
    s = sesion or requests.Session()
    campos = ("id,display_name,issn,works_count,cited_by_count,summary_stats,is_oa,"
              "is_in_doaj,apc_usd,homepage_url,counts_by_year,host_organization_name")
    salida = {}
    for i in range(0, len(issns), 50):
        lote = issns[i:i + 50]
        params = {"filter": "issn:" + "|".join(lote), "per-page": 50, "select": campos + ",topics"}
        if email:
            params["mailto"] = email
        if api_key:
            params["api_key"] = api_key
        r = _get(s, OPENALEX_URL, params)
        if r is None:  # por si la API no acepta el campo de temas
            r = _get(s, OPENALEX_URL, {**params, "select": campos})
        if r is None:
            continue
        for src in r.json().get("results", []):
            stats = src.get("summary_stats") or {}
            datos = {
                "openalex_id": src.get("id"),
                "oa_trabajos": src.get("works_count"),
                "oa_citas": src.get("cited_by_count"),
                "oa_citas_media_2y": stats.get("2yr_mean_citedness"),
                "oa_h_index": stats.get("h_index"),
                "oa_i10": stats.get("i10_index"),
                "es_oa": int(bool(src.get("is_oa"))),
                "en_doaj": int(bool(src.get("is_in_doaj"))),
                "apc_usd": src.get("apc_usd"),
                "web": src.get("homepage_url"),
                "prod_anual": json.dumps(
                    {str(c["year"]): [c.get("works_count", 0), c.get("cited_by_count", 0)]
                     for c in src.get("counts_by_year") or []}),
            }
            temas = []
            for t in (src.get("topics") or [])[:25]:
                for nombre in (t.get("display_name"), (t.get("subfield") or {}).get("display_name")):
                    if nombre and nombre not in temas:
                        temas.append(nombre)
            if temas:
                datos["oa_temas"] = "; ".join(temas)
            for issn in src.get("issn") or []:
                salida[issn.upper()] = datos
        time.sleep(0.15)
    return salida


# ---------------------------------------------------------------- DOAJ
def consultar_doaj(issn: str, sesion: requests.Session | None = None) -> dict | None:
    """Políticas editoriales (exigencias) registradas en DOAJ para revistas OA."""
    s = sesion or requests.Session()
    r = _get(s, DOAJ_URL.format(issn=issn), {"pageSize": 1})
    if r is None:
        return None
    res = r.json().get("results") or []
    if not res:
        return None
    b = res[0].get("bibjson", {})
    apc = b.get("apc") or {}
    if apc.get("has_apc"):
        apc_txt = ", ".join(f"{m.get('price')} {m.get('currency')}" for m in apc.get("max") or []) or "Sí"
    else:
        apc_txt = "Sin APC"
    otros = b.get("other_charges") or {}
    ref = b.get("ref") or {}
    return {
        "doaj_revision": ", ".join((b.get("editorial") or {}).get("review_process") or []),
        "doaj_plagio": "Sí" if (b.get("plagiarism") or {}).get("detection") else "No declarado",
        "doaj_semanas": b.get("publication_time_weeks"),
        "doaj_licencia": ", ".join(l.get("type", "") for l in b.get("license") or []),
        "doaj_apc": apc_txt,
        "doaj_otros_cargos": "Sí" if otros.get("has_other_charges") else "No",
        "doaj_exoneracion": "Sí" if (b.get("waiver") or {}).get("has_waiver") else "No",
        "doaj_instrucciones": ref.get("author_instructions"),
        "doaj_alcance": ref.get("aims_scope"),
        "doaj_idiomas": ", ".join(b.get("language") or []),
        "doaj_derechos_autor": "Sí" if (b.get("copyright") or {}).get("author_retains") else "No",
    }


# ---------------------------------------------------------------- Elsevier (opcional)
def consultar_citescore(issn: str, api_key: str, sesion: requests.Session | None = None):
    """CiteScore vía Scopus Serial Title API. Requiere API key de Elsevier
    (dev.elsevier.com) y, normalmente, acceso desde la red de la universidad."""
    s = sesion or requests.Session()
    r = _get(s, ELSEVIER_URL.format(issn=issn), {"view": "CITESCORE"},
             headers={"X-ELS-APIKey": api_key, "Accept": "application/json"})
    if r is None:
        return None
    try:
        e = r.json()["serial-metadata-response"]["entry"][0]
        return float(e["citeScoreYearInfoList"]["citeScoreCurrentMetric"])
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def _get(s, url, params, headers=None, intentos=3):
    for n in range(intentos):
        try:
            r = s.get(url, params=params, headers={**UA, **(headers or {})}, timeout=60)
        except requests.RequestException:
            time.sleep(2 ** n)
            continue
        if r.status_code == 429:
            time.sleep(2 ** (n + 1))
            continue
        if r.status_code >= 400:
            return None
        return r
    return None
