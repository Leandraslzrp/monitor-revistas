"""Monitor de Revistas Indexadas (Scopus / Web of Science) para la FACE.
Ejecutar con:  streamlit run app.py   (o con los lanzadores Iniciar_*)"""
import hashlib
import io
import os
import re
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st


def secreto(clave, defecto=None):
    try:
        return st.secrets.get(clave, defecto)
    except Exception:  # no hay archivo de secretos (uso local)
        return defecto


# Versión web (Streamlit Community Cloud): se activa con el secreto modo_web = true
MODO_WEB = bool(secreto("modo_web")) or os.environ.get("MONITOR_MODO_WEB") == "1"
if MODO_WEB:
    os.environ.setdefault("MONITOR_DATOS", str(Path(tempfile.gettempdir()) / "monitor_revistas_web"))

from nucleo import config, db, fuentes, monitor, web  # noqa: E402
from nucleo.config import AREAS_FACE  # noqa: E402

st.set_page_config(page_title="Monitor de Revistas FACE", page_icon="📚", layout="wide")


def firma_datos_web() -> str:
    h = hashlib.md5()
    for f in sorted(web.DATOS_WEB.rglob("*")):
        if f.is_file():
            h.update(f"{f.name}{f.stat().st_size}{f.stat().st_mtime}".encode())
    return h.hexdigest()


@st.cache_resource(show_spinner="Preparando la base de revistas…")
def preparar_web(firma: str) -> str:
    web.cargar(db.conectar())
    return firma


if MODO_WEB:
    preparar_web(firma_datos_web())

con = db.conectar()
cfg = config.cargar()
if "admin" not in st.session_state:
    st.session_state.admin = not MODO_WEB
ADMIN = st.session_state.admin


def github():
    if secreto("github_token") and secreto("github_repo"):
        return web.GitHub(secreto("github_token"), secreto("github_repo"), secreto("github_rama", "main"))
    return None


def persistir(ruta: str, contenido: bytes, mensaje: str):
    """En la versión web guarda el archivo en GitHub para que el cambio sea permanente."""
    if not MODO_WEB:
        return
    gh = github()
    if gh is None:
        st.warning("Cambio aplicado solo hasta que se reinicie la página: faltan los secretos "
                   "github_token y github_repo para guardarlo de forma permanente.")
        return
    try:
        gh.guardar_archivo(f"datos_web/{ruta}", contenido, mensaje)
    except Exception as e:
        st.error(f"No se pudo guardar en GitHub: {e}")

PH = "Elija una o varias opciones"
COLUMNAS = {
    "titulo": "Revista", "issns": "ISSN", "cuartil_sjr": "Cuartil SJR", "sjr": "SJR",
    "h_index": "Índice H", "wos_colecciones": "WoS", "jif_cuartil": "Cuartil JIF",
    "jif": "JIF", "citescore": "CiteScore", "areas": "Áreas", "pais": "País",
    "editorial": "Editorial", "acceso_abierto": "Acceso abierto", "apc_usd": "APC (USD)",
    "docs_anio": "Artículos (último año)", "citas_doc_2y": "Citas/doc (2 años)",
    "oa_trabajos": "Trabajos (OpenAlex)", "oa_citas_media_2y": "Citas media 2 años (OpenAlex)",
    "incentivo": "Incentivo estimado", "doaj_revision": "Revisión", "doaj_semanas": "Semanas a publicación",
}


@st.cache_data(show_spinner="Cargando base de revistas…")
def datos(version: str) -> pd.DataFrame:
    return monitor.vista(db.conectar())


def version() -> str:
    return "|".join(str(db.meta(con, k)) for k in
                    ("ultima_actualizacion", "ultimo_enriquecimiento", "cambio_local"))


def marcar_cambio():
    db.meta(con, "cambio_local", db.ahora() + str(pd.Timestamp.now().value))
    st.cache_data.clear()


def categorias(texto) -> list[tuple[str, str]]:
    return re.findall(r"([^;]+?)\s*\((Q[1-4])\)", texto if isinstance(texto, str) else "")


# ---------------------------------------------------------------- barra lateral
st.sidebar.title("📚 Monitor de Revistas")
st.sidebar.caption("Scopus (Scimago) · Web of Science · OpenAlex · DOAJ")
no_leidas = con.execute("SELECT COUNT(*) FROM alertas WHERE leida=0").fetchone()[0]
paginas = ["Buscar revistas", "Revistas FACE" if MODO_WEB else "Mis revistas",
           "Alertas" if MODO_WEB or not no_leidas else f"Alertas ({no_leidas})"]
if ADMIN:
    paginas += ["Actualizar datos", "Configuración"]
pagina = st.sidebar.radio("Ir a", paginas)
if MODO_WEB:
    with st.sidebar.expander("🔒 Administración" if not ADMIN else "🔓 Administración activa"):
        if not ADMIN:
            clave = st.text_input("Contraseña", type="password")
            if clave and clave == secreto("admin_password"):
                st.session_state.admin = True
                st.rerun()
            elif clave:
                st.error("Contraseña incorrecta.")
        elif st.button("Cerrar sesión"):
            st.session_state.admin = False
            st.rerun()
st.sidebar.divider()
st.sidebar.caption(f"Listas actualizadas: {db.meta(con, 'ultima_actualizacion') or 'nunca'}")
st.sidebar.caption(f"Indicadores OpenAlex/DOAJ: {db.meta(con, 'ultimo_enriquecimiento') or 'nunca'}")

def correr_actualizacion(descargar=True) -> bool:
    """Actualización completa con barra de progreso. Devuelve True si hay datos."""
    barra = st.progress(0.0, "Comenzando…")
    avisos, error = monitor.actualizacion_completa(
        con, cfg, progreso=lambda f, t: barra.progress(min(max(f, 0.0), 1.0), t), descargar=descargar)
    marcar_cambio()
    hay_datos = bool(list(config.FUENTES.glob("scimago_*.csv")))
    if error and not hay_datos:
        st.error("No se pudo descargar la lista de Scopus automáticamente (a veces la red de la "
                 "universidad o Scimago lo bloquean). Siga los pasos de abajo para cargarla a mano.")
        return False
    if error:
        st.warning("No se pudo descargar una lista nueva de Scopus; se usó la que ya tenía.")
    st.success(f"Listo. {len(avisos)} alerta(s) nuevas.")
    return True


df = datos(version())
if df.empty and MODO_WEB and pagina not in ("Actualizar datos", "Configuración"):
    st.title("📚 Monitor de Revistas FACE")
    st.info("La base de revistas se está preparando. La primera actualización se hace en GitHub "
            "y la página se completará sola cuando termine. Vuelva en unos minutos.")
    st.stop()
if df.empty and pagina != "Configuración" and not MODO_WEB:
    st.title("👋 Le damos la bienvenida al Monitor de Revistas")
    st.markdown("""
Este programa reúne en un solo lugar las revistas **Scopus** y **Web of Science** con sus cuartiles,
indicadores de producción, APC, incentivo UBB y exigencias, y le avisa cuando cambian.

Para empezar solo pulse **Comenzar**. El programa descargará la lista de revistas y los indicadores
de las áreas de la FACE (economía, negocios y ciencias de la decisión). Tarda unos minutos y solo
se hace una vez.
""")
    if st.button("🚀 Comenzar", type="primary"):
        if correr_actualizacion():
            st.rerun()
    with st.expander("¿Falló la descarga? Cargar la lista a mano"):
        st.markdown("1. Abra [scimagojr.com/journalrank.php](https://www.scimagojr.com/journalrank.php).\n"
                    "2. Pulse **Download data** (arriba a la derecha de la tabla).\n"
                    "3. Arrastre el archivo descargado aquí:")
        manual = st.file_uploader("Archivo de Scimago (.csv)", type=["csv"], key="manual_sc")
        if manual and st.button("Continuar con este archivo", type="primary"):
            try:
                monitor.importar_scimago(con, manual)
                if correr_actualizacion(descargar=False):
                    st.rerun()
            except Exception as e:
                st.error(f"El archivo no se pudo leer: {e}")
    st.stop()

_ult = db.meta(con, "ultima_actualizacion")
if (not MODO_WEB and _ult and (pd.Timestamp.now() - pd.Timestamp(_ult)).days > 30
        and pagina == "Buscar revistas"):
    c1, c2 = st.columns([4, 1])
    c1.warning(f"Los datos no se actualizan desde {_ult[:10]}.")
    if c2.button("Actualizar ahora"):
        if correr_actualizacion():
            st.rerun()


# ---------------------------------------------------------------- ficha de revista
def ficha(fila: pd.Series):
    abierta = fila.get("acceso_abierto") == "Yes" or fila.get("en_doaj") == 1
    if (abierta and not isinstance(fila.get("doaj_revision"), str)
            and not db.meta(con, f"doaj_sin_datos:{fila['rid']}")):
        with st.spinner("Consultando exigencias en DOAJ…"):
            try:
                if monitor.doaj_una(con, fila["rid"], fila.get("issns")):
                    marcar_cambio()
                    st.rerun()
            except Exception:
                pass
    st.subheader(fila["titulo"])
    st.caption(f"ISSN {_t(fila.get('issns'))} · {_t(fila.get('editorial'))} · {_t(fila.get('pais'))}")
    c = st.columns(6)
    c[0].metric("Cuartil SJR", _t(fila.get("cuartil_sjr")))
    c[1].metric("SJR", f"{fila['sjr']:.3f}" if pd.notna(fila.get("sjr")) else "—")
    c[2].metric("Índice H", f"{fila['h_index']:.0f}" if pd.notna(fila.get("h_index")) else "—")
    c[3].metric("Web of Science", fila.get("wos_colecciones") or "No")
    c[4].metric("APC", f"USD {fila['apc_usd']:,.0f}" if pd.notna(fila.get("apc_usd")) else "—")
    inc = fila.get("incentivo") or 0
    c[5].metric("Incentivo estimado", f"{inc:,.0f}" if inc else "—",
                help=fila.get("regla_incentivo") or "Configure la tabla en Configuración")

    t1, t2, t3, t4 = st.tabs(["Indicadores de producción", "Clasificación", "Exigencias", "Notas"])
    with t1:
        a, b = st.columns(2)
        a.markdown(f"""
| Indicador (Scimago/Scopus) | Valor |
|---|---|
| Documentos último año | {_f(fila.get('docs_anio'))} |
| Documentos 3 años | {_f(fila.get('docs_3y'))} |
| Citas 3 años | {_f(fila.get('citas_3y'))} |
| Documentos citables 3 años | {_f(fila.get('citables_3y'))} |
| Citas por documento (2 años) | {_f(fila.get('citas_doc_2y'), 2)} |
| Referencias totales | {_f(fila.get('refs'))} |
| CiteScore (API Elsevier) | {_f(fila.get('citescore'), 2)} |
| JIF (JCR) | {_f(fila.get('jif'), 3)} |
""")
        b.markdown(f"""
| Indicador (OpenAlex) | Valor |
|---|---|
| Trabajos publicados (total) | {_f(fila.get('oa_trabajos'))} |
| Citas recibidas (total) | {_f(fila.get('oa_citas'))} |
| Citas medias 2 años | {_f(fila.get('oa_citas_media_2y'), 2)} |
| Índice H | {_f(fila.get('oa_h_index'))} |
| Índice i10 | {_f(fila.get('oa_i10'))} |
""")
        prod = monitor.produccion_anual(fila.get("prod_anual"))
        if not prod.empty:
            st.markdown("**Producción anual (OpenAlex)**")
            st.bar_chart(prod.set_index("Año")[["Artículos"]])
            st.line_chart(prod.set_index("Año")[["Citas"]])
        else:
            st.caption("Sin datos de OpenAlex aún. Use *Actualizar datos → Indicadores de producción*.")
        hist = pd.read_sql("SELECT anio AS Año, sjr AS SJR, cuartil_sjr AS Cuartil FROM historial "
                           "WHERE rid=? ORDER BY anio", con, params=(fila["rid"],))
        if len(hist) > 1:
            st.markdown("**Evolución del SJR**")
            st.line_chart(hist.set_index("Año")[["SJR"]])
            st.dataframe(hist, hide_index=True)
    with t2:
        st.markdown(f"**Áreas (Scopus/ASJC):** {_t(fila.get('areas'))}")
        cats = categorias(fila.get("categorias"))
        if cats:
            st.dataframe(pd.DataFrame(cats, columns=["Categoría Scopus", "Cuartil"]), hide_index=True)
        st.markdown(f"**Categorías Web of Science:** {_t(fila.get('wos_categorias'))}")
        st.markdown(f"**Tipo:** {_t(fila.get('tipo'))} · **Cobertura Scopus:** {_t(fila.get('cobertura'))}")
    with t3:
        st.markdown(f"""
| Exigencia / política | Valor |
|---|---|
| Acceso abierto | {'Sí' if fila.get('acceso_abierto') == 'Yes' or fila.get('es_oa') == 1 else 'No'} |
| Cargo por publicación (APC) | {fila.get('doaj_apc') if isinstance(fila.get('doaj_apc'), str) else (f"USD {fila['apc_usd']:,.0f}" if pd.notna(fila.get('apc_usd')) else 'No registrado (posible revista de suscripción o híbrida)')} |
| Otros cargos | {_t(fila.get('doaj_otros_cargos'))} |
| Exoneración de APC | {_t(fila.get('doaj_exoneracion'))} |
| Tipo de revisión por pares | {_t(fila.get('doaj_revision'))} |
| Detección de plagio | {_t(fila.get('doaj_plagio'))} |
| Semanas promedio a publicación | {_f(fila.get('doaj_semanas'))} |
| Licencia | {_t(fila.get('doaj_licencia'))} |
| El autor conserva derechos | {_t(fila.get('doaj_derechos_autor'))} |
| Idiomas | {_t(fila.get('doaj_idiomas'))} |
""")
        for etiqueta, campo in [("Instrucciones para autores", "doaj_instrucciones"),
                                ("Enfoque y alcance", "doaj_alcance"), ("Sitio web", "web")]:
            if isinstance(fila.get(campo), str) and fila[campo]:
                st.markdown(f"[{etiqueta}]({fila[campo]})")
        st.caption("Las políticas provienen de DOAJ (solo revistas de acceso abierto registradas allí). "
                   "Para otras revistas, registre las exigencias en la pestaña Notas.")
    with t4:
        if not ADMIN:
            st.markdown(db.nota(con, fila["rid"]) or "_Sin notas registradas por la FACE._")
        else:
            texto = st.text_area("Notas y exigencias propias (extensión, formato, plantilla, idioma, "
                                 "tiempos, experiencias del equipo…)", db.nota(con, fila["rid"]),
                                 key=f"nota_{fila['rid']}", height=150)
            if st.button("Guardar nota", key=f"g_{fila['rid']}"):
                db.nota(con, fila["rid"], texto)
                persistir("notas.csv", web.tabla_csv(con, "notas"), f"Nota: {fila['titulo']}")
                st.success("Nota guardada.")
    if not ADMIN:
        if fila.get("seguida"):
            st.caption("⭐ Esta revista está en la lista de seguimiento de la FACE.")
        return
    seguida = bool(fila.get("seguida"))
    etiqueta = "la lista de la FACE" if MODO_WEB else "mis revistas"
    if st.button(f"Quitar de {etiqueta}" if seguida else f"⭐ Seguir (agregar a {etiqueta} y recibir alertas)",
                 key=f"s_{fila['rid']}"):
        db.seguir(con, fila["rid"], not seguida)
        persistir("seguimiento.csv", web.tabla_csv(con, "seguimiento"),
                  f"{'Quitar' if seguida else 'Seguir'}: {fila['titulo']}")
        marcar_cambio()
        st.rerun()


def _t(v):
    if v is None or (isinstance(v, float) and pd.isna(v)) or v == "":
        return "—"
    return str(v)


def _f(v, dec=0):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    try:
        return f"{float(v):,.{dec}f}"
    except (TypeError, ValueError):
        return str(v)


def tabla_seleccionable(sub: pd.DataFrame, clave: str):
    cols = [c for c in COLUMNAS if c in sub.columns]
    mostrar = sub[cols].rename(columns=COLUMNAS)
    ev = st.dataframe(mostrar, hide_index=True, width="stretch", height=420,
                      on_select="rerun", selection_mode="single-row", key=clave,
                      column_config={"SJR": st.column_config.NumberColumn(format="%.3f"),
                                     "APC (USD)": st.column_config.NumberColumn(format="%.0f"),
                                     "Incentivo estimado": st.column_config.NumberColumn(format="%.0f")})
    a, b, _ = st.columns([1, 1, 4])
    a.download_button("⬇️ CSV", mostrar.to_csv(index=False).encode("utf-8-sig"),
                      "revistas.csv", "text/csv", key=clave + "_csv")
    buf = io.BytesIO()
    mostrar.to_excel(buf, index=False)
    b.download_button("⬇️ Excel", buf.getvalue(), "revistas.xlsx", key=clave + "_xlsx")
    filas = ev.selection.rows if ev and ev.selection else []
    if filas:
        st.divider()
        ficha(sub.iloc[filas[0]])
    else:
        st.caption("Seleccione una fila para ver la ficha completa de la revista.")


# ---------------------------------------------------------------- páginas
if pagina == "Buscar revistas":
    st.title("Buscar revistas")
    todas_areas = sorted({a.strip() for x in df["areas"].dropna() for a in x.split(";") if a.strip()})
    f1, f2, f3, f4 = st.columns([2, 2, 1, 1])
    texto = f1.text_input("Título, ISSN o editorial")
    areas = f2.multiselect("Área", todas_areas, placeholder=PH,
                           default=[a for a in cfg.get("areas_interes", []) if a in todas_areas])
    base = f3.selectbox("Indexada en", ["Scopus o WoS", "Scopus", "Web of Science", "Ambas"])
    cuartiles = f4.multiselect("Cuartil SJR", ["Q1", "Q2", "Q3", "Q4"], placeholder=PH)
    g1, g2, g3, g4 = st.columns([2, 2, 1, 1])
    sub = df
    if areas:
        sub = sub[sub["areas"].fillna("").map(lambda x: any(a in x for a in areas))]
    cats_disp = sorted({c for x in sub["categorias"].dropna() for c, _ in categorias(x)})
    cat = g1.selectbox("Categoría específica (cuartil por categoría)", ["(todas)"] + cats_disp)
    paises = g2.multiselect("País", sorted(df["pais"].dropna().unique()), placeholder=PH)
    solo_oa = g3.checkbox("Solo acceso abierto")
    apc_max = g4.number_input("APC máximo (USD)", 0, 20000, 0, step=100,
                              help="0 = sin límite. Incluye revistas sin APC registrado.")
    if texto:
        t = texto.lower()
        sub = sub[sub["titulo"].fillna("").str.lower().str.contains(t, regex=False)
                  | sub["issns"].fillna("").str.contains(texto.upper(), regex=False)
                  | sub["editorial"].fillna("").str.lower().str.contains(t, regex=False)]
    if base == "Scopus":
        sub = sub[sub["scopus"] == 1]
    elif base == "Web of Science":
        sub = sub[sub["wos"] == 1]
    elif base == "Ambas":
        sub = sub[(sub["scopus"] == 1) & (sub["wos"] == 1)]
    if cat != "(todas)":
        sub = sub.copy()
        sub["cuartil_sjr"] = sub["categorias"].map(lambda x: dict(categorias(x)).get(cat))
        sub = sub[sub["cuartil_sjr"].notna()]
    if cuartiles:
        sub = sub[sub["cuartil_sjr"].isin(cuartiles)]
    if paises:
        sub = sub[sub["pais"].isin(paises)]
    if solo_oa:
        sub = sub[(sub["acceso_abierto"] == "Yes") | (sub.get("es_oa") == 1)]
    if apc_max:
        sub = sub[sub["apc_usd"].isna() | (sub["apc_usd"] <= apc_max)]
    sub = sub.sort_values(["sjr"], ascending=False, na_position="last").reset_index(drop=True)
    m = st.columns(5)
    m[0].metric("Revistas", f"{len(sub):,}")
    for i, q in enumerate(["Q1", "Q2", "Q3", "Q4"]):
        m[i + 1].metric(q, f"{(sub['cuartil_sjr'] == q).sum():,}")
    tabla_seleccionable(sub, "busqueda")

elif pagina in ("Mis revistas", "Revistas FACE"):
    st.title("Revistas en seguimiento de la FACE" if MODO_WEB else "Mis revistas en seguimiento")
    sub = df[df["seguida"]].reset_index(drop=True)
    if sub.empty:
        st.info("Aún no hay revistas en seguimiento. Búsquelas y pulse **⭐ Seguir**."
                if ADMIN else "La FACE aún no ha agregado revistas a su lista de seguimiento.")
    else:
        tabla_seleccionable(sub, "seguidas")

elif pagina.startswith("Alertas"):
    st.title("Alertas")
    al = pd.read_sql("SELECT id, fecha, titulo, tipo, detalle, leida, enviada FROM alertas "
                     "ORDER BY id DESC", con)
    if al.empty:
        st.info("Sin alertas. Se generan al actualizar los datos cuando una revista que usted sigue "
                "cambia de cuartil, indexación o APC, o cuando aparece una revista nueva en sus áreas.")
    else:
        solo = False if MODO_WEB else st.checkbox("Solo no leídas", value=True)
        vis = al[al["leida"] == 0] if solo else al
        if MODO_WEB:
            vis = vis.drop(columns=["leida"])
        st.dataframe(vis.drop(columns=["id"]).rename(columns={
            "fecha": "Fecha", "titulo": "Revista", "tipo": "Tipo", "detalle": "Detalle",
            "leida": "Leída", "enviada": "Enviada por correo"}), hide_index=True, width="stretch")
        if not MODO_WEB and st.button("Marcar todas como leídas"):
            con.execute("UPDATE alertas SET leida=1")
            con.commit()
            st.rerun()

elif pagina == "Actualizar datos":
    st.title("Actualizar datos")
    st.markdown("Un solo botón descarga la lista de Scopus, la combina con Web of Science, agrega los "
                "indicadores de producción y le avisa de los cambios en sus revistas.")
    if MODO_WEB:
        st.caption("En la versión web la actualización corre en GitHub cada lunes. Puede lanzarla ahora; "
                   "tarda unos 10 minutos y la página se actualiza sola al terminar.")
    if st.button("🔄 Actualizar todo ahora", type="primary"):
        if MODO_WEB:
            try:
                github().ejecutar_actualizacion()
                st.success("Actualización lanzada en GitHub.")
            except Exception as e:
                st.error(f"No se pudo lanzar la actualización en GitHub: {e}")
        elif correr_actualizacion():
            st.rerun()
    st.caption(f"Última actualización: {db.meta(con, 'ultima_actualizacion') or 'nunca'}")

    st.divider()
    st.markdown("#### Agregar Web of Science (opcional)")
    st.markdown("Clarivate no permite descargar sus listas automáticamente. Una vez al año:\n"
                "1. Entre a [mjl.clarivate.com](https://mjl.clarivate.com) con una cuenta gratuita.\n"
                "2. En *Downloads*, descargue **SSCI**, **SCIE**, **AHCI** y **ESCI**.\n"
                "3. Arrastre los archivos aquí abajo. El programa reconoce la colección por el nombre.")
    archivos = st.file_uploader("Listas de WoS (CSV o Excel)", type=["csv", "xlsx", "xls"],
                                accept_multiple_files=True)
    if archivos:
        elecciones = {}
        for f in archivos:
            det = fuentes.detectar_coleccion(f.name)
            opciones = fuentes.COLECCIONES_WOS + ["JCR"]
            elecciones[f.name] = st.selectbox(f"Colección de {f.name}", opciones,
                                              index=opciones.index(det) if det else 0)
        if st.button("Agregar a la base", type="primary"):
            for f in archivos:
                try:
                    st.success(f"{f.name}: {monitor.importar_wos(f, elecciones[f.name]):,} revistas.")
                    ext = ".xlsx" if f.name.lower().endswith((".xlsx", ".xls")) else ".csv"
                    persistir(f"fuentes/wos_{elecciones[f.name]}{ext}", f.getvalue(),
                              f"Lista WoS {elecciones[f.name]}")
                except Exception as e:
                    st.error(f"{f.name}: {e}")
            with st.spinner("Combinando con Scopus…"):
                monitor.actualizar_listas(con, cfg)
            marcar_cambio()
    cargados = sorted(p.name for p in config.FUENTES.glob("*.*") if not p.name.startswith("."))
    st.caption("Archivos cargados: " + (", ".join(cargados) or "ninguno"))

    if not MODO_WEB:
        with st.expander("Opciones avanzadas"):
            st.markdown("**Scopus: otro año o carga manual**")
            a, b = st.columns(2)
            with a:
                anio = st.number_input("Año (0 = el más reciente)", 0, 2100, 0)
                if st.button("Descargar ese año de scimagojr.com"):
                    with st.spinner("Descargando Scimago…"):
                        try:
                            y = monitor.descargar_scimago(con, anio or None)
                            monitor.actualizar_listas(con, cfg)
                            marcar_cambio()
                            st.success(f"Scimago {y} descargado.")
                        except Exception as e:
                            st.error(f"No se pudo descargar: {e}")
            with b:
                sub_sc = st.file_uploader("Subir CSV de Scimago (puede subir varios años)",
                                          type=["csv"], accept_multiple_files=True)
                if sub_sc and st.button("Importar CSV de Scimago"):
                    for f in sub_sc:
                        try:
                            st.success(f"{f.name}: datos de {monitor.importar_scimago(con, f)} importados.")
                        except Exception as e:
                            st.error(f"{f.name}: {e}")
                    monitor.actualizar_listas(con, cfg)
                    marcar_cambio()
            st.markdown("**Indicadores y exigencias (OpenAlex + DOAJ)**")
            alcance = st.radio("¿Qué revistas?", ["seguimiento", "areas", "todas"], horizontal=True,
                               format_func={"seguimiento": "Solo las que sigo",
                                            "areas": "Las de mis áreas de interés",
                                            "todas": "Todas (muy lento)"}.get, index=0)
            n = len(monitor.objetivos(con, cfg, alcance)) if not df.empty else 0
            st.caption(f"{n:,} revistas a consultar (incluye políticas DOAJ, puede tardar).")
            if st.button("Consultar OpenAlex y DOAJ", disabled=n == 0):
                barra = st.progress(0.0)
                avisos = monitor.enriquecer(con, cfg, alcance, progreso=lambda f, t: barra.progress(f, t))
                marcar_cambio()
                st.success(f"Listo. {len(avisos)} alerta(s) nuevas.")

            st.markdown("**Enviar alertas pendientes por correo**")
            if st.button("Enviar ahora"):
                try:
                    st.success(f"{monitor.enviar_alertas(con, cfg)} alerta(s) enviadas.")
                except Exception as e:
                    st.error(f"Error de correo: {e}")

elif pagina == "Configuración":
    st.title("Configuración")
    st.markdown("#### Áreas de interés")
    opciones = sorted(set(AREAS_FACE) | set(cfg["areas_interes"]) | (
        {a.strip() for x in df["areas"].dropna() for a in x.split(";")} if not df.empty else set()))
    cfg["areas_interes"] = st.multiselect("Áreas (Scopus/ASJC)", opciones, cfg["areas_interes"], placeholder=PH)
    cfg["alertar_nuevas_en_areas"] = st.checkbox("Alertar cuando aparezcan revistas nuevas en mis áreas",
                                                 cfg["alertar_nuevas_en_areas"])

    st.markdown("#### Tabla de incentivos (cuánto paga la universidad por publicar)")
    st.caption("Edite los montos según el reglamento de su facultad. El incentivo estimado de cada "
               "revista es el mayor monto entre las reglas que cumple.")
    inc = st.data_editor(monitor.cargar_incentivos(), num_rows="dynamic", hide_index=True,
                         width="stretch",
                         column_config={"base": st.column_config.SelectboxColumn(options=["Scopus", "WoS"]),
                                        "nivel": st.column_config.SelectboxColumn(options=[
                                            "Q1", "Q2", "Q3", "Q4", "Sin cuartil", "JIF Q1", "JIF Q2",
                                            "JIF Q3", "JIF Q4", "SSCI", "SCIE", "AHCI", "ESCI"])})

    st.markdown("#### Notificaciones por correo")
    if MODO_WEB:
        dest = st.text_input("Correos que reciben las alertas (separados por coma)",
                             ", ".join(cfg["destinatarios"]))
        cfg["destinatarios"] = [d.strip() for d in dest.split(",") if d.strip()]
        st.caption("La cuenta que envía los correos se configura en los secretos del repositorio "
                   "de GitHub (ver LEEME, sección Versión web).")
        if st.button("Guardar configuración", type="primary"):
            config.guardar(cfg)
            inc.to_csv(config.INCENTIVOS_PATH, index=False)
            persistir("config.json", web.config_publica(cfg), "Configuración")
            persistir("incentivos.csv", config.INCENTIVOS_PATH.read_bytes(), "Tabla de incentivos")
            marcar_cambio()
            st.success("Configuración guardada.")
        st.stop()
    cfg["email_activo"] = st.checkbox("Enviar alertas por correo", cfg["email_activo"])
    c1, c2 = st.columns(2)
    cfg["smtp_host"] = c1.text_input("Servidor SMTP", cfg["smtp_host"])
    cfg["smtp_puerto"] = c2.number_input("Puerto", 1, 65535, int(cfg["smtp_puerto"]))
    cfg["smtp_usuario"] = c1.text_input("Usuario (correo)", cfg["smtp_usuario"])
    cfg["smtp_password"] = c2.text_input("Contraseña de aplicación", cfg["smtp_password"], type="password",
                                         help="En Gmail/Outlook use una 'contraseña de aplicación'.")
    cfg["remitente"] = c1.text_input("Remitente (opcional)", cfg["remitente"])
    dest = c2.text_input("Destinatarios (separados por coma)", ", ".join(cfg["destinatarios"]))
    cfg["destinatarios"] = [d.strip() for d in dest.split(",") if d.strip()]

    st.markdown("#### Claves de API (opcionales)")
    cfg["openalex_email"] = st.text_input("Correo para OpenAlex (acceso más rápido)", cfg["openalex_email"])
    cfg["openalex_api_key"] = st.text_input("API key de OpenAlex (opcional)", cfg["openalex_api_key"], type="password")
    cfg["elsevier_api_key"] = st.text_input("API key de Elsevier/Scopus para CiteScore (dev.elsevier.com)",
                                            cfg["elsevier_api_key"], type="password")

    a, b = st.columns(2)
    if a.button("Guardar configuración", type="primary"):
        config.guardar(cfg)
        inc.to_csv(config.INCENTIVOS_PATH, index=False)
        marcar_cambio()
        st.success("Configuración guardada.")
    if b.button("Enviar correo de prueba"):
        from email.message import EmailMessage
        msg = EmailMessage()
        msg["Subject"], msg["From"] = "Prueba Monitor de Revistas", cfg["remitente"] or cfg["smtp_usuario"]
        msg["To"] = ", ".join(cfg["destinatarios"])
        msg.set_content("Las notificaciones del Monitor de Revistas funcionan correctamente.")
        try:
            monitor.enviar_correo(cfg, msg)
            st.success("Correo enviado.")
        except Exception as e:
            st.error(f"Error: {e}")
