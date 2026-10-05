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


FRASES = {
    "inteligencia artificial": "artificial intelligence", "aprendizaje automatico": "machine learning",
    "aprendizaje profundo": "deep learning", "gobierno corporativo": "corporate governance",
    "responsabilidad social": "social responsibility", "recursos humanos": "human resources",
    "cadena de suministro": "supply chain", "sistemas de informacion": "information systems",
    "derecho laboral": "labor law", "derecho del trabajo": "labor law", "inclusion financiera": "financial inclusion",
    "transformacion digital": "digital transformation", "america latina": "Latin America",
    "pequenas empresas": "small business", "redes sociales": "social media", "control interno": "internal control",
    "sector publico": "public sector", "politica publica": "public policy", "desempeno financiero": "financial performance",
    "mercado de capitales": "capital market", "empresas familiares": "family firms", "cambio climatico": "climate change",
    "internet de las cosas": "internet of things", "big data": "big data", "machine learning": "machine learning",
    "deep learning": "deep learning", "artificial intelligence": "artificial intelligence",
}
SUFIJOS = ("aciones", "acion", "ciones", "cion", "idades", "idad", "mente", "ings", "ing", "ias", "ia", "ers",
           "ar", "er", "ir", "es", "os", "as", "s", "o", "a", "e")


def raiz(w: str) -> str:
    """Raíz para truncar (audit*, contabl*, fraud*)."""
    for suf in SUFIJOS:
        if w.endswith(suf) and len(w) - len(suf) >= (4 if suf == "s" else 5):
            return w[: -len(suf)]
    return w


def interpretar(texto: str) -> tuple[str, list[str]]:
    """Admite operadores booleanos: NOT/-término excluye; AND, OR, comillas y * se aceptan.
    Devuelve (texto sin operadores, términos excluidos)."""
    excluir = [m.strip('"').lower() for m in re.findall(r'(?:\bNOT\s+|(?<!\S)-)("[^"]+"|\S+)', texto)]
    limpio = re.sub(r'(?:\bNOT\s+|(?<!\S)-)("[^"]+"|\S+)', " ", texto)
    limpio = re.sub(r"\b(AND|OR|Y|O)\b|[()\"*?]", " ", limpio)
    return " ".join(limpio.split()), [_plano(x).rstrip("*") for x in excluir]


def unidades(texto: str) -> list[tuple[str, str]]:
    """Conceptos del tema como (español, inglés), detectando frases de varias palabras."""
    t = " " + " ".join(re.findall(r"[a-zñ0-9]+", _plano(texto))) + " "
    out = []
    for es, en in sorted(FRASES.items(), key=lambda kv: -len(kv[0])):
        if f" {es} " in t:
            out.append((es, en))
            t = t.replace(f" {es} ", " ")
    for w in palabras(t):
        out.append((w, DICCIONARIO.get(w, w)))
    vistos, res = set(), []
    for es, en in out:
        if (es, en) not in vistos:
            vistos.add((es, en))
            res.append((es, en))
    return res[:6]


def _termino(x: str) -> str:
    x = x.lower() if not x.isupper() else x
    if " " in x:
        return f'"{x}"'
    r = raiz(x)
    return f"{r}*" if len(x) > 4 else x


def _grupo(variantes: list[str]) -> str:
    """Une variantes con OR, quitando las que ya cubre otra truncada (detect* cubre detection*)."""
    v = list(dict.fromkeys(variantes))
    v = [x for x in v if not any(y != x and y.endswith("*") and x.startswith(y[:-1]) for y in v)]
    return v[0] if len(v) == 1 else "(" + " OR ".join(v) + ")"


def _variantes(termino: str) -> str:
    """Un término del usuario con su traducción: auditoría -> (auditor* OR audit*)."""
    t = termino.strip('"')
    plano = " ".join(re.findall(r"[a-zñ0-9]+", _plano(t)))
    if termino.endswith("*"):
        en = DICCIONARIO.get(plano)
        return _grupo([f"{plano}*", _termino(en)]) if en and en != plano else f"{plano}*"
    en = FRASES.get(plano) or (" ".join(DICCIONARIO.get(w, w) for w in plano.split()) if " " not in plano
                               else plano)
    return _grupo([_termino(plano), _termino(en)])


def consulta_booleana(texto: str) -> dict[str, str]:
    """Cadena de búsqueda lista para Scopus y Web of Science, con sinónimos ES/EN y truncado (*).
    Si el usuario escribió operadores (AND, OR, NOT, comillas, *), se respeta su estructura."""
    if re.search(r'\b(AND|OR|NOT)\b|"|\*', texto):
        partes = re.findall(r'"[^"]+"|\(|\)|\bAND\b|\bOR\b|\bNOT\b|[^\s()"]+', texto)
        out, prev_term = [], False
        for p_ in partes:
            if p_ in ("AND", "OR", "NOT", "(", ")"):
                if p_ == "NOT" and prev_term:
                    out.append("AND")
                out.append(p_)
                prev_term = p_ == ")"
                continue
            if _plano(p_.strip('"*')) in VACIAS:
                continue
            if prev_term:
                out.append("AND")
            out.append(_variantes(p_))
            prev_term = True
        cuerpo = " ".join(out).replace("( ", "(").replace(" )", ")")
    else:
        limpio, _ = interpretar(texto)
        grupos = []
        for es, en in unidades(limpio):
            grupos.append(_grupo([_termino(es), _termino(en)]))
        cuerpo = " AND ".join(grupos)
    if not cuerpo:
        return {}
    return {"Scopus": f"TITLE-ABS-KEY({cuerpo})",
            "Web of Science": "TS=(" + cuerpo.replace(" AND NOT ", " NOT ") + ")"}


def _buscar_openalex(consulta: str, sesion, email: str = "") -> dict[str, int]:
    desde = f"{date.today().year - 5}-01-01"
    params = {"search": consulta, "filter": f"from_publication_date:{desde},type:article",
              "group_by": "primary_location.source.id", "per-page": 200}
    if email:
        params["mailto"] = email
    r = sesion.get(OPENALEX_WORKS, params=params, timeout=8)
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


# Conceptos frecuentes (en español e inglés, sin tildes) y las categorías Scimago donde se publican.
CONCEPTOS = {
    "Accounting": "contab contable contador auditor audit account niif ifrs earnings tributar impuest tax fraude "
                  "fraud reporte reporting costo cost control_interno internal_control divulgacion disclosure "
                  "revelacion informe_financiero financial_report sostenibilidad_reporte",
    "Finance": "finanz financ banc bank credit inversion invest bolsa stock fintech riesgo risk capital dividend "
               "portafolio portfolio cripto crypto seguro insurance microfinanz microfinanc inclusion_financiera "
               "financial_inclusion",
    "Economics and Econometrics": "econom crecimiento growth pobreza poverty desigualdad inequal inflacion "
                                  "inflation monetar comercio_internacional trade econometr productividad productiv",
    "Strategy and Management": "estrategi strateg gestion management gobierno_corporativo corporate_governance "
                               "governance empresa firm pyme sme competitiv esg sostenib sustainab "
                               "responsabilidad_social csr familiar family_firm desempeno performance",
    "Business and International Management": "internacional international export negocio business multinacional "
                                             "globaliz esg sostenib sustainab",
    "Marketing": "marketing consumidor consumer marca brand publicidad advertis ventas sales cliente customer "
                 "redes_sociales social_media comprador",
    "Organizational Behavior and Human Resource Management": "recursos_humanos human_resource liderazgo leadership "
        "trabajador employee teletrabajo telework remote_work clima_organizacional satisfaccion_laboral "
        "job_satisfaction motivacion motivation talento talent",
    "Management of Technology and Innovation": "innovacion innovation emprend entrepreneur startup "
        "transformacion_digital digital_transformation tecnolog technolog",
    "Tourism, Leisure and Hospitality Management": "turismo touris hotel hospitality",
    "Public Administration": "administracion_publica public_administration gobierno government municip "
                             "politica_publica public_policy sector_publico public_sector",
    "Law": "derecho law legal juridic ley constitucion constitutional penal criminal contrato contract tribunal "
           "court justicia justice regulac regulat",
    "Industrial Relations": "laboral labor sindicat union teletrabajo telework",
    "Political Science and International Relations": "politic democra eleccion election",
    "Artificial Intelligence": "inteligencia_artificial artificial_intelligence machine_learning "
                               "aprendizaje_automatico deep_learning redes_neuronales neural llm chatgpt",
    "Computer Science Applications": "machine_learning algoritm algorithm software aplicacion application",
    "Information Systems": "sistemas_de_informacion information_system erp big_data blockchain nube cloud "
                           "ciberseguridad cybersecurity",
    "Management Information Systems": "sistemas_de_informacion information_system erp business_intelligence "
                                      "inteligencia_de_negocios analytics",
    "Information Systems and Management": "sistemas_de_informacion information_system gestion_de_datos "
                                          "data_management",
    "Computer Networks and Communications": "redes network iot internet_de_las_cosas wireless ciberseguridad "
                                            "cybersecurity",
    "Software": "software programacion programming",
    "Education": "educacion education docencia teaching estudiante student universidad universit curricul",
    "E-learning": "e_learning online_learning aprendizaje_en_linea educacion_virtual",
    "Human-Computer Interaction": "usabilidad usability interfaz interface experiencia_de_usuario user_experience",
    "Management Science and Operations Research": "operaciones operations logistic cadena_de_suministro "
        "supply_chain optimizac optimiz inventario inventory",
    "Statistics, Probability and Uncertainty": "estadistic statistic",
    "Development": "pobreza poverty rural desarrollo_economico economic_development",
    "Geography, Planning and Development": "regional territori urban ciudad city",
    "Gender Studies": "genero gender mujer women",
}
_CONCEPTOS = {cat: [k.replace("_", " ") for k in v.split()] for cat, v in CONCEPTOS.items()}


def _coincide(clave: str, texto: str) -> bool:
    """La clave (raíz o frase) aparece al inicio de una palabra del texto."""
    return re.search(rf"\b{re.escape(clave)}", texto) is not None


def categorias_del_tema(texto: str) -> dict[str, int]:
    t = _plano(texto) + " " + _plano(traducir(texto))
    out = {}
    for cat, claves in _CONCEPTOS.items():
        n = sum(1 for k in claves if _coincide(k, t))
        if n:
            out[cat] = n
    return out


def _cats_revista(texto) -> dict[str, str]:
    return dict((c.strip(), q) for c, q in re.findall(r"([^;]+?)\s*\((Q[1-4])\)", texto if isinstance(texto, str) else ""))


def afinidad_local(texto: str, df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """(afinidad, cuartil en la categoría más afín) comparando el tema con las categorías,
    el título y los temas de OpenAlex de cada revista (respaldo sin conexión)."""
    claves = [k for k in dict.fromkeys(palabras(texto) + palabras(traducir(texto))) if len(k) > 3]
    temas = categorias_del_tema(texto)
    raices = list(dict.fromkeys(raiz(k) for k in claves))
    rel, cuart = [], []
    col_temas = df["oa_temas"] if "oa_temas" in df else pd.Series("", index=df.index)
    total = sum(temas.values()) or 1
    for tit, cats, oat, q in zip(df["titulo"], df["categorias"], col_temas, df["cuartil_sjr"]):
        cr = _cats_revista(cats)
        t = _plano(tit if isinstance(tit, str) else "")
        o = _plano(oat if isinstance(oat, str) else "")
        # un concepto del tema se cumple si la revista tiene esa categoría o lo nombra en su título/temas
        cumplidos = [g for g in temas if g in cr or any(_coincide(k, t) or _coincide(k, o) for k in _CONCEPTOS[g])]
        p_cat = sum(temas[g] for g in cumplidos) / total
        p_tit = min(1.0, 0.25 * sum(1 for k in raices if _coincide(k, t)))
        p_oa = min(1.0, 0.2 * sum(1 for k in raices if _coincide(k, o)))
        rel.append(2.0 * p_cat + p_tit + p_oa)
        cuart.append(min((q2 for c, q2 in cr.items() if c in temas), default=q))
    return pd.Series(rel, index=df.index, dtype=float), pd.Series(cuart, index=df.index)


def recomendar(df: pd.DataFrame, texto: str, n: int = 5, email: str = "", sesion=None,
               conteo: dict | None = None) -> tuple[pd.DataFrame, str]:
    """Devuelve las n revistas más recomendadas con su puntaje y razones, y el método usado.
    conteo: artículos recientes por revista según OpenAlex ({} si no se pudo consultar)."""
    if df.empty or not texto.strip():
        return df.head(0), ""
    texto, excluir = interpretar(texto)
    df = df.copy()
    if "alerta" in df:  # nunca se recomiendan revistas depredadoras o descontinuadas
        df = df[~df["alerta"].isin(["sospechosa", "descontinuada"])]
    if excluir:  # NOT: se descartan revistas cuyo título o categorías nombran el término
        campo = (df["titulo"].fillna("") + " " + df["categorias"].fillna("")).map(_plano)
        df = df[~campo.map(lambda c: any(_coincide(x, c) for x in excluir))]
    local, cuartil = afinidad_local(texto, df)
    df["_cuartil"] = cuartil
    if conteo is None:
        try:
            conteo = afinidad_openalex(texto, email, sesion)
        except Exception:
            conteo = {}
    ids = df["openalex_id"].fillna("").astype(str).str.rsplit("/", n=1).str[-1]
    df["_art"] = ids.map(conteo or {}).fillna(0)
    metodo = "openalex" if df["_art"].sum() > 0 else "local"
    rel_l = local / local.max() if local.max() > 0 else local * 0
    rel_o = df["_art"].map(math.log1p)
    rel_o = rel_o / rel_o.max() if rel_o.max() > 0 else rel_o * 0
    df["_rel"] = (0.5 * rel_l + 0.5 * rel_o) if metodo == "openalex" else rel_l
    df["_loc"] = local
    if df["_rel"].max() <= 0:
        return df.head(0), metodo
    df["_rel"] = df["_rel"] / df["_rel"].max()
    df["_cal"] = df["_cuartil"].map(PESO_Q).fillna(0.15)
    df["puntaje"] = (0.7 * df["_rel"] + 0.3 * df["_cal"]) * (df["_rel"] > 0)
    top = df[df["puntaje"] > 0].sort_values(["puntaje", "sjr"], ascending=False).head(n)
    temas = categorias_del_tema(texto)
    top["razones"] = [razones(r, temas) for _, r in top.iterrows()]
    return top, metodo


def razones(r, temas: dict | None = None) -> list[str]:
    out = []
    if r.get("_art", 0) > 0:
        out.append(f"Publicó {int(r['_art'])} artículos sobre su tema en los últimos 5 años")
    cats = [c for c in _cats_revista(r.get("categorias")) if c in (temas or {})]
    if cats:
        out.append("Publica en " + ", ".join(cats[:3]))
    elif r.get("_loc", 0) > 0 and not r.get("_art", 0):
        out.append("Su título o sus temas coinciden con su artículo")
    q = r.get("_cuartil") if isinstance(r.get("_cuartil"), str) else r.get("cuartil_sjr")
    if isinstance(q, str):
        cat_q = next((c for c in cats if _cats_revista(r.get("categorias")).get(c) == q), None)
        out.append(f"Cuartil {q} en la categoría {cat_q}" if cat_q else f"Cuartil {q} en Scopus")
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
