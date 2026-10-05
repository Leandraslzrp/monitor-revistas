"""Construcción de la base, enriquecimiento, detección de cambios, incentivos y
notificaciones."""
import json
import re
import smtplib
import ssl
from email.message import EmailMessage
from datetime import date, datetime

import pandas as pd
import requests

from . import db, fuentes
from .config import CARRERAS, FUENTES, INCENTIVOS_PATH

CLAVES_LISTA = ["scopus", "cuartil_sjr", "wos_colecciones", "jif_cuartil"]


# ---------------------------------------------------------------- importación
def importar_scimago(con, origen) -> int:
    """Guarda un CSV de Scimago (de cualquier año) y registra su historial."""
    FUENTES.mkdir(parents=True, exist_ok=True)
    datos = origen.read() if hasattr(origen, "read") else open(origen, "rb").read()
    import io
    df, anio = fuentes.leer_scimago(io.BytesIO(datos))
    anio = anio or 0
    (FUENTES / f"scimago_{anio}.csv").write_bytes(datos)
    _guardar_historial(con, df, anio)
    return anio


def _guardar_historial(con, df, anio):
    viejos = _mapa_issn_rid(con)
    filas = []
    for r in df.itertuples():
        issns = r.issns.split(",") if r.issns else []
        rid = next((viejos[i] for i in issns if i in viejos), issns[0] if issns else f"SC{r.sourceid}")
        filas.append((rid, anio, r.sjr, r.cuartil_sjr, r.h_index, r.docs_anio))
    con.executemany("INSERT OR REPLACE INTO historial VALUES (?,?,?,?,?,?)", filas)
    con.commit()


def importar_wos(origen, coleccion: str) -> int:
    FUENTES.mkdir(parents=True, exist_ok=True)
    datos = origen.read() if hasattr(origen, "read") else open(origen, "rb").read()
    import io
    nombre = getattr(origen, "name", str(origen))
    buf = io.BytesIO(datos)
    buf.name = nombre
    df = fuentes.leer_wos(buf)
    ext = ".xlsx" if nombre.lower().endswith((".xlsx", ".xls")) else ".csv"
    for viejo in FUENTES.glob(f"wos_{coleccion}.*"):
        viejo.unlink()
    (FUENTES / f"wos_{coleccion}{ext}").write_bytes(datos)
    return len(df)


def descargar_scimago(con, anio=None) -> int:
    import tempfile, pathlib
    tmp = pathlib.Path(tempfile.mkstemp(suffix=".csv")[1])
    fuentes.descargar_scimago(tmp, anio)
    return importar_scimago(con, tmp)


# ---------------------------------------------------------------- construcción
def _mapa_issn_rid(con) -> dict:
    try:
        df = pd.read_sql("SELECT rid, issns FROM revistas", con)
    except Exception:
        return {}
    m = {}
    for rid, issns in zip(df["rid"], df.get("issns", [])):
        for i in (issns or "").split(","):
            if i:
                m[i] = rid
    return m


def construir_revistas(con) -> pd.DataFrame:
    archivos = sorted(FUENTES.glob("scimago_*.csv"),
                      key=lambda p: int(re.sub(r"\D", "", p.stem) or 0))
    viejos = _mapa_issn_rid(con)
    if archivos:
        sc, anio = fuentes.leer_scimago(archivos[-1])
        sc["anio_sjr"] = anio
        sc["scopus"] = 1
    else:
        sc = pd.DataFrame(columns=["titulo", "issns", "sourceid", "scopus"])
    sc["rid"] = [next((viejos[i] for i in (s or "").split(",") if i in viejos),
                      (s or "").split(",")[0] or f"SC{sid}")
                 for s, sid in zip(sc["issns"], sc["sourceid"])]
    sc = sc.drop_duplicates("rid")
    indice = {}
    for rid, issns in zip(sc["rid"], sc["issns"]):
        for i in (issns or "").split(","):
            if i:
                indice[i] = rid

    extra = {}   # rid -> datos WoS
    nuevos = {}  # rid -> fila solo-WoS
    for f in FUENTES.glob("wos_*.*"):
        col = f.stem.split("_", 1)[1]
        try:
            w = fuentes.leer_wos(f)
        except ValueError:
            continue
        for r in w.itertuples():
            issns = r.issns.split(",")
            rid = next((indice[i] for i in issns if i in indice), None)
            if rid is None:
                rid = next((viejos[i] for i in issns if i in viejos), issns[0])
                if rid not in nuevos:
                    nuevos[rid] = {"rid": rid, "titulo": r.titulo, "issns": r.issns, "scopus": 0}
                for i in issns:
                    indice[i] = rid
            e = extra.setdefault(rid, {"cols": set(), "cats": set(), "jif": None, "q": None})
            if col != "JCR":
                e["cols"].add(col)
            elif isinstance(r.wos_edicion, str):
                e["cols"].update(x.strip() for x in re.split(r"[,;]", r.wos_edicion) if x.strip())
            if isinstance(r.wos_categorias, str):
                e["cats"].update(x.strip().title() for x in re.split(r"[|;]", r.wos_categorias) if x.strip())
            if pd.notna(r.jif):
                e["jif"] = max(e["jif"] or 0, r.jif)
            if isinstance(r.jif_cuartil, str):
                e["q"] = min(e["q"] or "Q9", r.jif_cuartil)
    if nuevos:
        sc = pd.concat([sc, pd.DataFrame(nuevos.values())], ignore_index=True)
    sc["wos_colecciones"] = sc["rid"].map(lambda r: ";".join(sorted(extra[r]["cols"])) if r in extra else "")
    sc["wos_categorias"] = sc["rid"].map(lambda r: "; ".join(sorted(extra[r]["cats"])) if r in extra else "")
    sc["jif"] = sc["rid"].map(lambda r: extra[r]["jif"] if r in extra else None)
    sc["jif_cuartil"] = sc["rid"].map(lambda r: extra[r]["q"] if r in extra else None)
    sc["wos"] = (sc["wos_colecciones"] != "").astype(int)
    sin_area = sc["areas"].isna() | (sc["areas"] == "") if "areas" in sc else pd.Series(True, index=sc.index)
    sc.loc[sin_area, "areas"] = sc.loc[sin_area, "wos_categorias"].map(areas_desde_wos)
    sc["scopus"] = sc["scopus"].fillna(0).astype(int)
    return sc


# Equivalencia aproximada de categorías WoS -> áreas ASJC (para revistas solo-WoS)
WOS_A_ASJC = {
    "economics": "Economics, Econometrics and Finance",
    "finance": "Economics, Econometrics and Finance",
    "business": "Business, Management and Accounting",
    "management": "Business, Management and Accounting",
    "hospitality": "Business, Management and Accounting",
    "operations research": "Decision Sciences",
    "statistics": "Decision Sciences",
}


def areas_desde_wos(cats) -> str:
    if not isinstance(cats, str) or not cats:
        return ""
    t = cats.lower()
    encontradas = sorted({a for k, a in WOS_A_ASJC.items() if k in t})
    if not encontradas and "social" in t:
        encontradas = ["Social Sciences"]
    return "; ".join(encontradas)


_CAT_RE = re.compile(r"([^;]+?)\s*\((?:Q[1-4]|-)\)|([^;()]+)")


def carreras_de(areas, categorias, wos_cats=None, titulo=None) -> list[str]:
    """Áreas de la FACE a las que corresponde una revista."""
    areas = areas if isinstance(areas, str) else ""
    cats = {(a or b).strip() for a, b in _CAT_RE.findall(categorias)} if isinstance(categorias, str) else set()
    wos = wos_cats.lower() if isinstance(wos_cats, str) else ""
    tit = titulo.lower() if isinstance(titulo, str) else ""
    salida = []
    for nombre, c in CARRERAS.items():
        if any(a in areas for a in c["areas"]) or cats & set(c["categorias"]) \
                or (wos and any(x.lower() in wos for x in c["categorias"] if len(x) > 3)):
            if c.get("titulo") and not re.search(c["titulo"], tit):
                continue
            salida.append(nombre)
        elif c.get("extra") and cats & set(c["extra"]["categorias"]) and re.search(c["extra"]["titulo"], tit):
            salida.append(nombre)
    return salida


def areas_interes(cfg) -> set[str]:
    """Áreas elegidas en la configuración (ignora nombres de versiones anteriores)."""
    elegidas = set(cfg.get("carreras_interes") or []) & set(CARRERAS)
    return elegidas or set(CARRERAS)


def actualizar_listas(con, cfg) -> list[str]:
    """Reconstruye la tabla de revistas y genera alertas por cambios."""
    try:
        viejo = pd.read_sql("SELECT * FROM revistas", con).set_index("rid")
    except Exception:
        viejo = pd.DataFrame()
    nuevo = construir_revistas(con)
    avisos = []
    if not viejo.empty and "titulo" in viejo.columns:
        avisos = _comparar_listas(con, cfg, viejo, nuevo.set_index("rid"))
    nuevo.to_sql("revistas", con, if_exists="replace", index=False)
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_rev ON revistas(rid)")
    db.meta(con, "ultima_actualizacion", db.ahora())
    con.commit()
    return avisos


def _v(df, rid, col):
    if rid not in df.index or col not in df.columns:
        return None
    x = df.at[rid, col]
    return None if pd.isna(x) or x == "" else x


def _comparar_listas(con, cfg, viejo, nuevo) -> list[str]:
    seg = db.seguimiento(con)
    avisos = []

    def alerta(rid, tipo, detalle):
        tit = _v(nuevo, rid, "titulo") or _v(viejo, rid, "titulo") or rid
        db.agregar_alerta(con, rid, tit, tipo, detalle)
        avisos.append(f"{tit}: {detalle}")

    for rid in seg:
        sv, sn = _v(viejo, rid, "scopus"), _v(nuevo, rid, "scopus")
        if sv == 1 and sn != 1:
            alerta(rid, "Indexación", "Ya no aparece en Scopus/Scimago")
        elif sv != 1 and sn == 1 and rid in viejo.index:
            alerta(rid, "Indexación", "Ingresó a Scopus/Scimago")
        qv, qn = _v(viejo, rid, "cuartil_sjr"), _v(nuevo, rid, "cuartil_sjr")
        if qv and qn and qv != qn:
            alerta(rid, "Cuartil SJR", f"Cambió de {qv} a {qn} ({'sube' if qn < qv else 'baja'})")
        wv = set((_v(viejo, rid, "wos_colecciones") or "").split(";")) - {""}
        wn = set((_v(nuevo, rid, "wos_colecciones") or "").split(";")) - {""}
        if wv != wn and rid in nuevo.index:
            partes = []
            if wn - wv:
                partes.append("ingresó a " + ", ".join(sorted(wn - wv)))
            if wv - wn:
                partes.append("salió de " + ", ".join(sorted(wv - wn)))
            alerta(rid, "Indexación WoS", "Web of Science: " + "; ".join(partes))
        jv, jn = _v(viejo, rid, "jif_cuartil"), _v(nuevo, rid, "jif_cuartil")
        if jv and jn and jv != jn:
            alerta(rid, "Cuartil JIF", f"Cuartil JIF cambió de {jv} a {jn}")

    interes = areas_interes(cfg)
    if cfg.get("alertar_nuevas_en_areas"):
        for rid in nuevo.index.difference(viejo.index):
            cs = [c for c in carreras_de(_v(nuevo, rid, "areas"), _v(nuevo, rid, "categorias"),
                                         _v(nuevo, rid, "wos_categorias"), _v(nuevo, rid, "titulo")) if c in interes]
            if cs:
                q = _v(nuevo, rid, "cuartil_sjr") or "sin cuartil"
                alerta(rid, "Nueva revista", f"Nueva revista ({q}) para {', '.join(cs)}")
    con.commit()
    return avisos


# ---------------------------------------------------------------- enriquecimiento
def objetivos(con, cfg, alcance: str) -> pd.DataFrame:
    rev = pd.read_sql("SELECT rid, titulo, issns, areas, categorias, wos_categorias, acceso_abierto, "
                      "cuartil_sjr FROM revistas", con)
    seg = db.seguimiento(con)
    mask = rev["rid"].isin(seg)
    if alcance == "todas":
        mask |= True
    elif alcance == "areas":
        interes = areas_interes(cfg)
        mask |= pd.Series([bool(set(carreras_de(a, c, w, t)) & interes) for a, c, w, t in
                           zip(rev["areas"], rev["categorias"], rev["wos_categorias"], rev["titulo"])],
                          index=rev.index)
    return rev[mask]


def enriquecer(con, cfg, alcance="areas", progreso=None, sesion=None, con_doaj=True) -> list[str]:
    """Agrega indicadores de producción (OpenAlex), APC y exigencias (DOAJ).
    con_doaj: True (todas las revistas abiertas), "seguimiento" (solo las seguidas) o False.
    Las exigencias que no se vuelven a consultar se conservan."""
    s = sesion or requests.Session()
    obj = objetivos(con, cfg, alcance)
    progreso = progreso or (lambda f, t: None)
    issn_a_rid = {}
    for rid, issns in zip(obj["rid"], obj["issns"]):
        for i in (issns or "").split(",")[:2]:
            if i:
                issn_a_rid[i] = rid
    progreso(0.0, f"Consultando OpenAlex para {len(obj)} revistas…")
    lista = list(issn_a_rid)
    oa = {}
    for k in range(0, len(lista), 500):
        oa.update(fuentes.consultar_openalex(lista[k:k + 500], cfg.get("openalex_email", ""),
                                             cfg.get("openalex_api_key", ""), s))
        progreso(min(0.5, 0.5 * (k + 500) / max(len(lista), 1)), "Consultando OpenAlex…")
    por_rid = {}
    for issn, datos in oa.items():
        if issn in issn_a_rid:
            por_rid.setdefault(issn_a_rid[issn], datos)

    viejo = pd.read_sql("SELECT * FROM enriq", con).set_index("rid")
    seg = db.seguimiento(con)
    titulos = dict(zip(obj["rid"], obj["titulo"]))
    issns_de = dict(zip(obj["rid"], obj["issns"]))
    avisos = []
    rids = list(obj["rid"])
    oa_scimago = dict(zip(obj["rid"], obj["acceso_abierto"].astype(str).str.lower() == "yes"))
    for n, rid in enumerate(rids):
        fila = dict(por_rid.get(rid, {}))
        abierta = fila.get("en_doaj") or oa_scimago[rid]
        pedir_doaj = con_doaj is True or (con_doaj == "seguimiento" and rid in seg)
        if pedir_doaj and abierta:
            for issn in (issns_de[rid] or "").split(",")[:2]:
                d = fuentes.consultar_doaj(issn, s) if issn else None
                if d:
                    fila.update(d)
                    break
        if cfg.get("elsevier_api_key") and (rid in seg or alcance == "seguimiento"):
            issn = (issns_de[rid] or "").split(",")[0]
            if issn:
                fila["citescore"] = fuentes.consultar_citescore(issn, cfg["elsevier_api_key"], s)
        if not fila:
            continue
        if rid in seg and rid in viejo.index:
            avisos += _comparar_enriq(con, rid, titulos[rid], viejo.loc[rid], fila)
        if rid in viejo.index:  # conservar lo que no se volvió a consultar
            previo = {k: v for k, v in viejo.loc[rid].to_dict().items() if pd.notna(v)}
            fila = {**previo, **fila}
        fila["rid"], fila["fecha"] = rid, db.ahora()
        cols = list(fila)
        con.execute(f"INSERT OR REPLACE INTO enriq ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                    [fila[c] for c in cols])
        if n % 25 == 0:
            con.commit()
            progreso(0.5 + 0.5 * n / max(len(rids), 1), f"Políticas editoriales (DOAJ): {n}/{len(rids)}")
    con.commit()
    db.meta(con, "ultimo_enriquecimiento", db.ahora())
    progreso(1.0, "Listo")
    return avisos


def _comparar_enriq(con, rid, titulo, viejo, nuevo) -> list[str]:
    avisos = []
    a0, a1 = viejo.get("apc_usd"), nuevo.get("apc_usd")
    if pd.notna(a0) and a1 is not None and float(a0) != float(a1):
        det = f"El APC cambió de USD {a0:,.0f} a USD {a1:,.0f}"
        db.agregar_alerta(con, rid, titulo, "APC", det)
        avisos.append(f"{titulo}: {det}")
    d0, d1 = viejo.get("en_doaj"), nuevo.get("en_doaj")
    if pd.notna(d0) and d1 is not None and int(d0) != int(d1):
        det = "Ingresó a DOAJ" if d1 else "Salió de DOAJ"
        db.agregar_alerta(con, rid, titulo, "Indexación", det)
        avisos.append(f"{titulo}: {det}")
    return avisos


def doaj_una(con, rid, issns: str, sesion=None) -> bool:
    """Consulta DOAJ para una sola revista (al abrir su ficha)."""
    for issn in (issns or "").split(",")[:2]:
        d = fuentes.consultar_doaj(issn, sesion) if issn else None
        if d:
            fila = {"rid": rid, "fecha": db.ahora(), **d}
            existe = con.execute("SELECT 1 FROM enriq WHERE rid=?", (rid,)).fetchone()
            if existe:
                con.execute(f"UPDATE enriq SET {', '.join(k + '=?' for k in d)} WHERE rid=?",
                            [*d.values(), rid])
            else:
                cols = list(fila)
                con.execute(f"INSERT INTO enriq ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                            [fila[c] for c in cols])
            con.commit()
            return True
    con.execute("INSERT OR IGNORE INTO meta VALUES (?, '1')", (f"doaj_sin_datos:{rid}",))
    con.commit()
    return False


def actualizacion_completa(con, cfg, progreso=None, descargar=True,
                           exigencias_limite=0) -> tuple[list[str], str | None]:
    """Todo en un paso: descarga Scimago, reconstruye, indicadores y alertas.
    Devuelve (alertas, error de descarga o None)."""
    progreso = progreso or (lambda f, t: None)
    error = None
    if descargar:
        progreso(0.02, "Descargando la lista de Scopus desde Scimago (≈ 30.000 revistas)…")
        try:
            descargar_scimago(con)
        except Exception as e:
            error = str(e)
    progreso(0.15, "Combinando Scopus y Web of Science…")
    avisos = actualizar_listas(con, cfg)
    if not list(FUENTES.glob("scimago_*.csv")):
        return avisos, error
    avisos += enriquecer(con, cfg, "areas", con_doaj="seguimiento",
                         progreso=lambda f, t: progreso(0.2 + 0.6 * f, t))
    if exigencias_limite:
        exigencias_lote(con, cfg, exigencias_limite, progreso=lambda f, t: progreso(0.8 + 0.18 * f, t))
    progreso(0.98, "Calculando los temas más publicados…")
    try:
        temas_por_area(con, cfg)
    except Exception:
        pass
    progreso(0.99, "Buscando las publicaciones de la UBB…")
    try:
        produccion_ubb(con, cfg)
    except Exception:
        pass
    try:
        enviar_alertas(con, cfg)
    except Exception:
        pass
    progreso(1.0, "Listo")
    return avisos, error


# ---------------------------------------------------------------- temas más publicados
def temas_por_area(con, cfg, sesion=None, por_area=15) -> int:
    """Temas (topics de OpenAlex) de los artículos publicados en los últimos 12 meses en las
    revistas de cada área, comparados con los 12 meses anteriores."""
    s = sesion or requests.Session()
    df = vista(con)
    hoy = date.today()
    hace1 = hoy.replace(year=hoy.year - 1)
    hace2 = hoy.replace(year=hoy.year - 2)
    filas = []
    for area in CARRERAS:
        sub = df[df["carreras"].str.contains(area, regex=False) & df["openalex_id"].notna()]
        sub = sub.sort_values("docs_anio", ascending=False).head(100)
        ids = "|".join(sub["openalex_id"].astype(str).str.rsplit("/", n=1).str[-1])
        if not ids:
            continue
        conteos = []
        for desde, hasta in ((hace1, hoy), (hace2, hace1)):
            params = {"filter": f"primary_location.source.id:{ids},from_publication_date:{desde.isoformat()},"
                                f"to_publication_date:{hasta.isoformat()}", "group_by": "topics.id", "per-page": 200}
            if cfg.get("openalex_email"):
                params["mailto"] = cfg["openalex_email"]
            r = fuentes._get(s, fuentes.OPENALEX_URL.replace("/sources", "/works"), params)
            conteos.append({g["key_display_name"]: g["count"] for g in (r.json().get("group_by", []) if r else [])})
        actual, previo = conteos
        for tema, n in sorted(actual.items(), key=lambda kv: -kv[1])[:por_area]:
            filas.append((area, tema, n, previo.get(tema, 0), db.ahora()))
    if filas:
        con.execute("DELETE FROM temas")
        con.executemany("INSERT INTO temas VALUES (?,?,?,?,?)", filas)
        con.commit()
    return len(filas)


# ---------------------------------------------------------------- producción UBB
UBB_BUSQUEDA = "Universidad del Bío-Bío"


def produccion_ubb(con, cfg, sesion=None, anios=5, max_paginas=60) -> int:
    """Artículos con autoría de la Universidad del Bío-Bío en los últimos años (OpenAlex)."""
    s = sesion or requests.Session()
    base = fuentes.OPENALEX_URL.rsplit("/", 1)[0]
    extra = {"mailto": cfg["openalex_email"]} if cfg.get("openalex_email") else {}
    r = fuentes._get(s, f"{base}/institutions", {"search": UBB_BUSQUEDA, "filter": "country_code:CL", **extra})
    resultados = r.json().get("results", []) if r else []
    if not resultados:
        return 0
    inst = resultados[0]["id"].rsplit("/", 1)[-1]
    db.meta(con, "ubb_institucion", f"{inst}|{resultados[0].get('display_name')}")
    desde = f"{date.today().year - anios + 1}-01-01"
    filas, cursor = [], "*"
    for _ in range(max_paginas):
        params = {"filter": f"institutions.id:{inst},from_publication_date:{desde},type:article",
                  "select": "id,title,publication_year,primary_location,doi,authorships",
                  "per-page": 200, "cursor": cursor, **extra}
        r = fuentes._get(s, f"{base}/works", params)
        if r is None:
            break
        datos = r.json()
        for w in datos.get("results", []):
            fuente = ((w.get("primary_location") or {}).get("source") or {}).get("id")
            if not fuente:
                continue
            autores = [a.get("author", {}).get("display_name") for a in w.get("authorships") or []
                       if any(str(i.get("id", "")).endswith(inst) for i in a.get("institutions") or [])]
            filas.append((w["id"].rsplit("/", 1)[-1], w.get("title"), w.get("publication_year"),
                          fuente.rsplit("/", 1)[-1], w.get("doi"), "; ".join(x for x in autores if x)[:300], db.ahora()))
        cursor = (datos.get("meta") or {}).get("next_cursor")
        if not cursor:
            break
    if filas:
        con.execute("DELETE FROM ubb_articulos")
        con.executemany("INSERT OR REPLACE INTO ubb_articulos VALUES (?,?,?,?,?,?,?)", filas)
        con.commit()
    return len(filas)


# ---------------------------------------------------------------- vista combinada
def vista(con) -> pd.DataFrame:
    try:
        rev = pd.read_sql("SELECT * FROM revistas", con)
    except Exception:
        return pd.DataFrame()
    if rev.empty or "titulo" not in rev.columns:
        return pd.DataFrame()
    enr = pd.read_sql("SELECT * FROM enriq", con).drop(columns=["fecha"])
    exi = pd.read_sql("SELECT * FROM exigencias", con).rename(columns={"url": "exi_url", "fecha": "exi_fecha"})
    df = rev.merge(enr, on="rid", how="left").merge(exi, on="rid", how="left")
    df["seguida"] = df["rid"].isin(db.seguimiento(con))
    df["carreras"] = ["; ".join(carreras_de(a, c, w, t)) for a, c, w, t in
                      zip(df["areas"], df["categorias"], df["wos_categorias"], df["titulo"])]
    df["recepcion_txt"], df["periodo_txt"], df["recepcion_origen"] = zip(*[
        recepcion_mostrar(r, i, f, m) for r, i, f, m in
        zip(df["recepcion"], df["fecha_inicio"], df["fecha_limite"], df["manual"])])
    df["url_instr"] = [url_instrucciones(*v) for v in
                       zip(df["titulo"], df["web"], df["exi_url"], df["doaj_instrucciones"], df["manual"])]
    return df


def url_instrucciones(titulo, web, exi_url, doaj_url, manual) -> str:
    """Mejor enlace disponible a las instrucciones para autores; si no hay, una búsqueda."""
    from urllib.parse import quote_plus
    from . import exigencias
    ok = lambda u: isinstance(u, str) and u.startswith("http")
    if manual == 1 and ok(exi_url):
        return exi_url
    for u in (doaj_url, exigencias.enlace_guia(web if ok(web) else None)):
        if ok(u):
            return u
    if ok(exi_url) and exi_url.rstrip("/") != str(web).rstrip("/"):
        return exi_url
    if ok(web):
        return web
    return "https://www.google.com/search?q=" + quote_plus(f'"{titulo}" author guidelines')


MESES_CORTOS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def fecha_corta(iso) -> str:
    try:
        d = datetime.fromisoformat(str(iso)[:10]).date()
    except ValueError:
        return ""
    return f"{d.day} {MESES_CORTOS[d.month - 1]} {d.year}"


SIN_INFO = "Sin información"


def recepcion_mostrar(rec, inicio, limite, manual) -> tuple[str, str, str]:
    """(estado, periodo, origen). Si no se encontró nada se dice explícitamente: no se
    supone que la recepción sea continua."""
    vacio = lambda v: v is None or (isinstance(v, float) and pd.isna(v)) or v in ("", SIN_INFO)
    origen = "manual" if manual == 1 else "detectada"
    if vacio(rec):
        return SIN_INFO, "Sin fecha publicada", "sin_dato"
    if rec == "Continua":
        return "Continua", "Todo el año", origen
    if vacio(limite):
        return rec, "Según convocatoria", origen
    hasta = fecha_corta(limite)
    if str(limite)[:10] < date.today().isoformat():
        return "Convocatoria cerrada", f"Cerró el {hasta}", origen
    periodo = f"{fecha_corta(inicio)} al {hasta}" if not vacio(inicio) else f"Hasta el {hasta}"
    return rec, periodo, origen


# ---------------------------------------------------------------- exigencias para autores
CAMPOS_EXI = ["palabras_max", "caracteres_max", "paginas_max", "resumen_max", "recepcion",
              "fecha_inicio", "fecha_limite", "evidencia", "url"]


def guardar_exigencias(con, rid, datos: dict, manual=False):
    fila = {k: datos.get(k) for k in CAMPOS_EXI}
    fila.update(rid=rid, fecha=db.ahora(), manual=int(manual))
    cols = list(fila)
    con.execute(f"INSERT OR REPLACE INTO exigencias ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                [fila[c] for c in cols])
    con.commit()


def exigencias_una(con, rid, web=None, instrucciones=None, sesion=None) -> dict:
    """Busca las exigencias de una revista en su sitio (no reemplaza datos manuales)."""
    from . import exigencias
    previo = con.execute("SELECT manual FROM exigencias WHERE rid=?", (rid,)).fetchone()
    if previo and previo[0] == 1:
        return {}
    datos = exigencias.buscar(web, instrucciones, sesion) if (web or instrucciones) else {}
    guardar_exigencias(con, rid, datos)
    return datos


def exigencias_lote(con, cfg, limite=600, progreso=None, hilos=8) -> int:
    """Busca exigencias para las revistas seguidas y, por turnos, para las demás de las
    carreras (las de mejor cuartil primero). Devuelve cuántas se consultaron."""
    from concurrent.futures import ThreadPoolExecutor
    from . import exigencias
    progreso = progreso or (lambda f, t: None)
    obj = objetivos(con, cfg, "areas")
    enr = pd.read_sql("SELECT rid, web, doaj_instrucciones FROM enriq", con)
    exi = pd.read_sql("SELECT rid, fecha, manual FROM exigencias", con)
    obj = obj.merge(enr, on="rid", how="left").merge(exi, on="rid", how="left")
    obj = obj[obj["web"].notna() | obj["doaj_instrucciones"].notna()]
    obj = obj[obj["manual"].fillna(0) != 1]
    # las editoriales que bloquean la lectura automática solo reciben el enlace a su guía
    bloq = obj["web"].map(lambda w: exigencias.bloqueado(w) if isinstance(w, str) else False) \
        & obj["doaj_instrucciones"].isna()
    for r in obj[bloq & obj["fecha"].isna()].itertuples():
        guardar_exigencias(con, r.rid, {"url": exigencias.enlace_guia(r.web) or r.web})
    obj = obj[~bloq]
    seg = db.seguimiento(con)
    obj["prioridad"] = [0 if r in seg else (1 if pd.isna(f) else 2) for r, f in zip(obj["rid"], obj["fecha"])]
    obj["q"] = obj["cuartil_sjr"].fillna("Q9")
    obj = obj.sort_values(["prioridad", "fecha", "q"], na_position="first").head(limite)

    def tarea(fila):
        try:
            return fila.rid, exigencias.buscar(fila.web if isinstance(fila.web, str) else None,
                                               fila.doaj_instrucciones if isinstance(fila.doaj_instrucciones, str) else None,
                                               timeout=12)
        except Exception:
            return fila.rid, {}

    n = 0
    with ThreadPoolExecutor(hilos) as ex:
        for rid, datos in ex.map(tarea, obj.itertuples()):
            guardar_exigencias(con, rid, datos)
            n += 1
            if n % 20 == 0:
                progreso(n / max(len(obj), 1), f"Exigencias para autores: {n}/{len(obj)}")
    return n


# ---------------------------------------------------------------- incentivos
def cargar_incentivos() -> pd.DataFrame:
    if not INCENTIVOS_PATH.exists():
        import shutil
        from pathlib import Path
        INCENTIVOS_PATH.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(Path(__file__).with_name("incentivos_plantilla.csv"), INCENTIVOS_PATH)
    if INCENTIVOS_PATH.exists():
        t = pd.read_csv(INCENTIVOS_PATH, dtype=str)
        t["monto"] = pd.to_numeric(t["monto"], errors="coerce").fillna(0)
        return t
    return pd.DataFrame(columns=["base", "nivel", "monto", "moneda", "nota"])


def calcular_incentivo(fila, tabla: pd.DataFrame):
    """Monto mayor entre las reglas que cumple la revista."""
    candidatos = []
    if fila.get("scopus") == 1:
        candidatos.append(("Scopus", fila.get("cuartil_sjr") or "Sin cuartil"))
    for c in str(fila.get("wos_colecciones") or "").split(";"):
        if c:
            candidatos.append(("WoS", c))
    if isinstance(fila.get("jif_cuartil"), str):
        candidatos.append(("WoS", "JIF " + fila["jif_cuartil"]))
    mejor, regla = 0.0, ""
    for base, nivel in candidatos:
        m = tabla[(tabla["base"] == base) & (tabla["nivel"] == nivel)]
        if not m.empty and m["monto"].iloc[0] > mejor:
            mejor = float(m["monto"].iloc[0])
            regla = f"{base} {nivel} ({m['moneda'].iloc[0]})"
    return mejor, regla


# ---------------------------------------------------------------- notificaciones
def enviar_alertas(con, cfg) -> int:
    """Envía por correo las alertas que aún no se han enviado."""
    pend = pd.read_sql("SELECT * FROM alertas WHERE enviada=0 ORDER BY id", con)
    if pend.empty or not cfg.get("email_activo") or not cfg.get("destinatarios"):
        return 0
    lineas = [f"- [{r.tipo}] {r.titulo}: {r.detalle} ({r.fecha})" for r in pend.itertuples()]
    msg = EmailMessage()
    msg["Subject"] = f"Monitor de revistas: {len(pend)} alerta(s) nueva(s)"
    msg["From"] = cfg.get("remitente") or cfg.get("smtp_usuario")
    msg["To"] = ", ".join(cfg["destinatarios"])
    msg.set_content("Se detectaron los siguientes cambios en sus revistas:\n\n"
                    + "\n".join(lineas) + "\n\nAbra el Monitor de Revistas para más detalle.")
    enviar_correo(cfg, msg)
    con.executemany("UPDATE alertas SET enviada=1 WHERE id=?", [(int(i),) for i in pend["id"]])
    con.commit()
    return len(pend)


def enviar_correo(cfg, msg):
    puerto = int(cfg.get("smtp_puerto") or 587)
    ctx = ssl.create_default_context()
    if puerto == 465:
        srv = smtplib.SMTP_SSL(cfg["smtp_host"], puerto, context=ctx, timeout=30)
    else:
        srv = smtplib.SMTP(cfg["smtp_host"], puerto, timeout=30)
        if cfg.get("smtp_tls", True):
            srv.starttls(context=ctx)
    with srv:
        if cfg.get("smtp_usuario"):
            srv.login(cfg["smtp_usuario"], cfg["smtp_password"])
        srv.send_message(msg)


def produccion_anual(texto) -> pd.DataFrame:
    if not isinstance(texto, str) or not texto:
        return pd.DataFrame(columns=["Año", "Artículos", "Citas"])
    d = json.loads(texto)
    return pd.DataFrame([(int(a), v[0], v[1]) for a, v in d.items()],
                        columns=["Año", "Artículos", "Citas"]).sort_values("Año")
