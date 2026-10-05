"""Recomendación de revistas a partir del tema de un artículo.

Usa OpenAlex para ver en qué revistas se publican hoy artículos sobre ese tema (búsqueda
en títulos y resúmenes de los últimos años) y combina esa afinidad con la calidad de la
revista. Si OpenAlex no responde, compara el texto con títulos y categorías de las revistas."""
import math
import re
import unicodedata
from datetime import date

import pandas as pd
import requests

OPENALEX_WORKS = "https://api.openalex.org/works"
PESO_Q = {"Q1": 1.0, "Q2": 0.75, "Q3": 0.5, "Q4": 0.3}

# Traducción de términos frecuentes en la FACE para buscar también en inglés.
DICCIONARIO = {
    "contabilidad": "accounting", "contable": "accounting", "auditoria": "auditing", "auditor": "auditor",
    "finanzas": "finance", "financiero": "financial", "financiera": "financial", "tributario": "tax",
    "tributaria": "tax", "impuestos": "taxes", "impuesto": "tax", "costos": "costs", "costo": "cost",
    "gestion": "management", "administracion": "management", "empresa": "firm", "empresas": "firms",
    "pymes": "SMEs", "pyme": "SME", "emprendimiento": "entrepreneurship", "innovacion": "innovation",
    "marketing": "marketing", "consumidor": "consumer", "consumidores": "consumers", "ventas": "sales",
    "recursos": "resources", "humanos": "human", "trabajo": "work", "trabajadores": "workers",
    "liderazgo": "leadership", "estrategia": "strategy", "sostenibilidad": "sustainability",
    "sostenible": "sustainable", "responsabilidad": "responsibility", "social": "social",
    "gobierno": "governance", "corporativo": "corporate", "corporativa": "corporate",
    "economia": "economics", "economico": "economic", "economica": "economic", "crecimiento": "growth",
    "desarrollo": "development", "pobreza": "poverty", "desigualdad": "inequality", "mercado": "market",
    "mercados": "markets", "bancos": "banks", "banca": "banking", "credito": "credit", "inversion": "investment",
    "bolsa": "stock market", "riesgo": "risk", "fraude": "fraud", "corrupcion": "corruption",
    "derecho": "law", "juridico": "legal", "juridica": "legal", "ley": "law", "constitucional": "constitutional",
    "penal": "criminal", "laboral": "labor", "civil": "civil", "contratos": "contracts", "derechos": "rights",
"tribunal": "court", "justicia": "justice", "regulacion": "regulation",
    "politica": "policy", "publica": "public", "publico": "public", "municipal": "municipal", "estado": "state",
    "informatica": "computing", "software": "software", "datos": "data", "inteligencia": "intelligence",
    "artificial": "artificial", "aprendizaje": "learning", "automatico": "machine", "redes": "networks",
    "seguridad": "security", "ciberseguridad": "cybersecurity", "sistemas": "systems", "informacion": "information",
    "algoritmos": "algorithms", "algoritmo": "algorithm", "nube": "cloud", "digital": "digital",
    "transformacion": "transformation", "tecnologia": "technology", "tecnologias": "technologies",
    "educacion": "education", "universidad": "university", "universidades": "universities",
    "estudiantes": "students", "docencia": "teaching", "enseñanza": "teaching", "turismo": "tourism",
    "agricola": "agricultural", "agricultura": "agriculture", "rural": "rural", "region": "region",
    "regional": "regional", "chile": "Chile", "latinoamerica": "Latin America", "america latina": "Latin America",
    "genero": "gender", "mujeres": "women", "familia": "family", "familiares": "family", "salud": "health",
    "cadena": "chain", "suministro": "supply", "logistica": "logistics", "operaciones": "operations",
    "calidad": "quality", "productividad": "productivity", "eficiencia": "efficiency", "medicion": "measurement",
    "reportes": "reporting", "reporte": "reporting", "informes": "reports", "normas": "standards",
    "desempeno": "performance", "divulgacion": "disclosure", "revelacion": "disclosure",
    "chilenas": "Chile", "chilenos": "Chile", "chilena": "Chile", "chileno": "Chile", "detectar": "detection",
    "deteccion": "detection", "prediccion": "prediction", "teletrabajo": "telework", "inclusion": "inclusion",
    "niif": "IFRS", "ifrs": "IFRS", "esg": "ESG", "blockchain": "blockchain", "fintech": "fintech",
}
VACIAS = set("""de la el los las un una unos unas y o en del al con por para sobre que como su sus se
es son entre desde hacia hasta sin mi mis nuestro nuestra este esta estos estas ese esa articulo paper
estudio investigacion analisis caso efecto efectos impacto rol papel the of and in on for to a an with
by from study analysis effect effects impact role case evidence""".split())


def _plano(t: str) -> str:
    t = unicodedata.normalize("NFKD", t.lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def palabras(texto: str) -> list[str]:
    return [w for w in re.findall(r"[a-zñ0-9]+", _plano(texto)) if len(w) > 2 and w not in VACIAS]


def traducir(texto: str) -> str:
    """Versión en inglés aproximada (palabra a palabra) de las palabras clave."""
    out = [DICCIONARIO.get(w, w) for w in palabras(texto)]
    return " ".join(dict.fromkeys(out))


def _buscar_openalex(consulta: str, sesion, email: str = "") -> dict[str, int]:
    desde = f"{date.today().year - 5}-01-01"
    params = {"search": consulta, "filter": f"from_publication_date:{desde},type:article",
              "group_by": "primary_location.source.id", "per-page": 200}
    if email:
        params["mailto"] = email
    r = sesion.get(OPENALEX_WORKS, params=params, timeout=20)
    r.raise_for_status()
    return {g["key"].rsplit("/", 1)[-1]: g["count"] for g in r.json().get("group_by", []) if g.get("key")}


def afinidad_openalex(texto: str, email: str = "", sesion=None) -> dict[str, int]:
    """{id de OpenAlex (S…): artículos recientes sobre el tema}. Busca en español y en inglés."""
    s = sesion or requests.Session()
    conteo: dict[str, int] = {}
    consultas = [" ".join(palabras(texto))]
    en = traducir(texto)
    if en and en != consultas[0]:
        consultas.append(en)
    for q in consultas:
        if not q:
            continue
        for k, v in _buscar_openalex(q, s, email).items():
            conteo[k] = conteo.get(k, 0) + v
    return conteo


def afinidad_local(texto: str, df: pd.DataFrame) -> pd.Series:
    """Coincidencia de palabras con título, categorías y áreas (respaldo sin conexión)."""
    claves = set(palabras(texto)) | set(palabras(traducir(texto)))
    if not claves:
        return pd.Series(0.0, index=df.index)
    campo = (df["titulo"].fillna("") + " " + df["categorias"].fillna("") + " " + df["areas"].fillna("")).map(_plano)
    return campo.map(lambda c: float(sum(1 for k in claves if re.search(rf"\b{re.escape(k)}", c))))


def recomendar(df: pd.DataFrame, texto: str, n: int = 5, email: str = "", sesion=None,
               conteo: dict | None = None) -> tuple[pd.DataFrame, str]:
    """Devuelve las n revistas más recomendadas con su puntaje y razones, y el método usado."""
    if df.empty or not texto.strip():
        return df.head(0), ""
    df = df.copy()
    metodo = "openalex"
    try:
        if conteo is None:
            conteo = afinidad_openalex(texto, email, sesion)
        ids = df["openalex_id"].fillna("").str.rsplit("/", n=1).str[-1]
        df["_art"] = ids.map(conteo).fillna(0)
        if df["_art"].sum() == 0:
            raise ValueError("sin coincidencias")
        rel = df["_art"].map(lambda v: math.log1p(v))
    except Exception:
        metodo = "local"
        df["_art"] = 0
        rel = afinidad_local(texto, df)
    if rel.max() <= 0:
        return df.head(0), metodo
    df["_rel"] = rel / rel.max()
    df["_cal"] = df["cuartil_sjr"].map(PESO_Q).fillna(0.15)
    df["puntaje"] = (0.65 * df["_rel"] + 0.35 * df["_cal"]) * (df["_rel"] > 0)
    top = df[df["puntaje"] > 0].sort_values(["puntaje", "sjr"], ascending=False).head(n)
    top["razones"] = [razones(r) for _, r in top.iterrows()]
    return top, metodo


def razones(r) -> list[str]:
    out = []
    if r.get("_art", 0) > 0:
        out.append(f"Publicó {int(r['_art'])} artículos sobre su tema en los últimos 5 años")
    elif r.get("_rel", 0) > 0:
        out.append("Su título o categorías coinciden con el tema")
    if isinstance(r.get("cuartil_sjr"), str):
        out.append(f"Cuartil {r['cuartil_sjr']} en Scopus")
    if r.get("wos") == 1:
        out.append("Indexada en Web of Science")
    apc = pd.to_numeric(r.get("apc_usd"), errors="coerce")
    if r.get("acceso_abierto") == "Yes" and (apc is None or pd.isna(apc) or apc == 0):
        out.append("Acceso abierto sin cobro registrado")
    elif apc is not None and not pd.isna(apc) and apc > 0:
        out.append(f"Cobro por acceso abierto (APC): US$ {apc:,.0f}".replace(",", "."))
    if r.get("recepcion_txt") in ("Convocatoria abierta", "Número especial abierto"):
        out.append(f"Convocatoria abierta: {r.get('periodo_txt')}")
    return out
