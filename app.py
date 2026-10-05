"""Monitor de Revistas Indexadas (Scopus / Web of Science) · FACE UBB.
Ejecutar con:  streamlit run app.py   (o con los lanzadores Iniciar_*)"""
import hashlib
import html
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
    except Exception:  # sin archivo de secretos (uso local)
        return defecto


# La versión web se activa sola cuando el repositorio trae datos en datos_web/
# (los lanzadores de escritorio fijan MONITOR_MODO_LOCAL=1 para usar la versión personal).
_BASE = Path(__file__).resolve().parent
MODO_WEB = (bool(secreto("modo_web")) or os.environ.get("MONITOR_MODO_WEB") == "1"
            or (os.environ.get("MONITOR_MODO_LOCAL") != "1"
                and any((_BASE / "datos_web" / "fuentes").glob("scimago_*.csv"))))
if MODO_WEB:
    os.environ.setdefault("MONITOR_DATOS", str(Path(tempfile.gettempdir()) / "monitor_revistas_web"))

from nucleo import config, db, fuentes, monitor, web  # noqa: E402
from nucleo.config import CARRERAS  # noqa: E402

st.set_page_config(page_title="Monitor de Revistas FACE · UBB", page_icon="📚", layout="wide",
                   initial_sidebar_state="collapsed")

# ---------------------------------------------------------------- estilo
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"], .stMarkdown, .stText, button, input, textarea, select { font-family: 'Inter', sans-serif !important; }
[data-testid="stToolbarActions"], [data-testid="stMainMenu"], [data-testid="stAppDeployButton"],
[data-testid="stDecoration"], #MainMenu, footer, .viewerBadge_container__r5tak { display: none !important; }
header[data-testid="stHeader"] { background: rgba(255,255,255,.92); backdrop-filter: blur(8px);
                                  border-bottom: 1px solid #eef2f7; }
.block-container { padding-top: 1.2rem; max-width: 1400px; }
.hero { background: linear-gradient(120deg, #0b2e59 0%, #134e8e 55%, #1f6fb5 100%); color: #fff;
        border-radius: 20px; padding: 28px 32px; margin-bottom: 18px; box-shadow: 0 10px 30px rgba(11,46,89,.18); }
.hero h1 { color: #fff; font-size: 1.9rem; font-weight: 800; margin: 0 0 4px 0; letter-spacing: -.02em; }
.hero p { color: #d6e4f5; margin: 0; font-size: 1rem; }
.hero .stats { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 18px; }
.hero .stat { background: rgba(255,255,255,.12); border: 1px solid rgba(255,255,255,.18); border-radius: 14px;
              padding: 10px 16px; min-width: 110px; }
.hero .stat b { display: block; font-size: 1.35rem; font-weight: 800; color: #fff; }
.hero .stat span { font-size: .78rem; color: #cfe0f3; text-transform: uppercase; letter-spacing: .04em; }
.card { background: #fff; border: 1px solid #e6ebf2; border-radius: 18px; padding: 20px 22px;
        box-shadow: 0 2px 10px rgba(15,23,42,.04); margin-bottom: 14px; }
.card h2 { font-size: 1.45rem; font-weight: 800; margin: 0 0 4px 0; color: #0f172a; letter-spacing: -.01em; }
.card h3 { font-size: 1.05rem; font-weight: 700; margin: 0 0 12px 0; color: #0f172a; }
.muted { color: #64748b; font-size: .9rem; }
.badges { display: flex; flex-wrap: wrap; gap: 6px; margin: 10px 0 2px 0; }
.badge { display: inline-flex; align-items: center; gap: 4px; padding: 4px 10px; border-radius: 999px;
         font-size: .78rem; font-weight: 600; border: 1px solid transparent; }
.q1 { background: #dcfce7; color: #166534; } .q2 { background: #fef9c3; color: #854d0e; }
.q3 { background: #ffedd5; color: #9a3412; } .q4 { background: #fee2e2; color: #991b1b; }
.qn { background: #f1f5f9; color: #475569; }
.b-blue { background: #e0ecff; color: #1e40af; } .b-violet { background: #ede9fe; color: #5b21b6; }
.b-green { background: #dcfce7; color: #166534; } .b-gray { background: #f1f5f9; color: #334155; }
.b-amber { background: #fef3c7; color: #92400e; } .b-red { background: #fee2e2; color: #991b1b; }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; }
.tile { background: #f8fafc; border: 1px solid #eef2f7; border-radius: 14px; padding: 12px 14px; }
.tile span { display: block; font-size: .74rem; color: #64748b; text-transform: uppercase; letter-spacing: .04em; font-weight: 600; }
.tile b { display: block; font-size: 1.15rem; color: #0f172a; font-weight: 700; margin-top: 2px; }
.tile small { color: #64748b; }
.evid { background: #f8fafc; border-left: 3px solid #93c5fd; padding: 8px 12px; border-radius: 8px;
        color: #334155; font-size: .85rem; margin-top: 10px; }
div[data-testid="stPills"] button { border-radius: 999px !important; }
.stDownloadButton button, .stButton button { border-radius: 10px !important; font-weight: 600 !important; }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------- datos
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


@st.cache_data(show_spinner="Cargando revistas…")
def datos(version: str) -> pd.DataFrame:
    return monitor.vista(db.conectar())


def version() -> str:
    return "|".join(str(db.meta(con, k)) for k in
                    ("ultima_actualizacion", "ultimo_enriquecimiento", "cambio_local"))


def marcar_cambio():
    db.meta(con, "cambio_local", db.ahora() + str(pd.Timestamp.now().value))
    st.cache_data.clear()


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
        st.toast("Cambio aplicado hasta que la página se reinicie (falta conectar GitHub para guardarlo).")
        return
    try:
        gh.guardar_archivo(f"datos_web/{ruta}", contenido, mensaje)
    except Exception as e:
        st.error(f"No se pudo guardar en GitHub: {e}")


# ---------------------------------------------------------------- utilidades de formato
def _vacio(v) -> bool:
    return v is None or (isinstance(v, float) and pd.isna(v)) or v == ""


def _t(v) -> str:
    return "—" if _vacio(v) else str(v)


def _n(v, dec=0) -> str:
    if _vacio(v):
        return "—"
    try:
        return f"{float(v):,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return str(v)


def e(v) -> str:
    return html.escape(_t(v))


def categorias(texto) -> list[tuple[str, str]]:
    return re.findall(r"([^;]+?)\s*\((Q[1-4])\)", texto if isinstance(texto, str) else "")


def badge_q(q) -> str:
    q = q if isinstance(q, str) and q in ("Q1", "Q2", "Q3", "Q4") else None
    return f'<span class="badge {q.lower() if q else "qn"}">{q or "Sin cuartil"}</span>'


def extension(fila) -> str:
    if not _vacio(fila.get("palabras_max")):
        return f"{_n(fila['palabras_max'])} palabras"
    if not _vacio(fila.get("caracteres_max")):
        return f"{_n(fila['caracteres_max'])} caracteres"
    if not _vacio(fila.get("paginas_max")):
        return f"{_n(fila['paginas_max'])} páginas"
    return ""


def badge_recepcion(fila) -> str:
    r = fila.get("recepcion")
    if _vacio(r):
        return '<span class="badge b-gray">Recepción: sin información</span>'
    clase = {"Continua": "b-green", "Convocatoria abierta": "b-green", "Por convocatoria": "b-amber",
             "Convocatoria cerrada": "b-red", "Cerrada": "b-red"}.get(r, "b-gray")
    extra = f" hasta {fila['fecha_limite']}" if not _vacio(fila.get("fecha_limite")) and r != "Continua" else ""
    texto = "Recepción continua" if r == "Continua" else f"{r}{extra}"
    return f'<span class="badge {clase}">📬 {html.escape(texto)}</span>'


def hero(titulo, subtitulo, stats=None):
    s = "".join(f'<div class="stat"><b>{v}</b><span>{k}</span></div>' for k, v in (stats or []))
    st.markdown(f'<div class="hero"><h1>{titulo}</h1><p>{subtitulo}</p>'
                f'{"<div class=stats>" + s + "</div>" if s else ""}</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------- ficha de revista
def ficha(fila: pd.Series):
    rid = fila["rid"]
    abierta = fila.get("acceso_abierto") == "Yes" or fila.get("en_doaj") == 1
    if (abierta and not isinstance(fila.get("doaj_revision"), str)
            and not db.meta(con, f"doaj_sin_datos:{rid}")):
        with st.spinner("Consultando políticas en DOAJ…"):
            try:
                if monitor.doaj_una(con, rid, fila.get("issns")):
                    marcar_cambio()
                    st.rerun()
            except Exception:
                pass
    if _vacio(fila.get("exi_fecha")) and (isinstance(fila.get("web"), str) or isinstance(fila.get("doaj_instrucciones"), str)):
        with st.spinner("Buscando las instrucciones para autores en el sitio de la revista…"):
            try:
                monitor.exigencias_una(con, rid, fila.get("web") if isinstance(fila.get("web"), str) else None,
                                       fila.get("doaj_instrucciones") if isinstance(fila.get("doaj_instrucciones"), str) else None)
                marcar_cambio()
                st.rerun()
            except Exception:
                pass

    # Encabezado
    badges = [badge_q(fila.get("cuartil_sjr"))]
    if fila.get("scopus") == 1:
        badges.append('<span class="badge b-blue">Scopus</span>')
    for c in str(fila.get("wos_colecciones") or "").split(";"):
        if c:
            badges.append(f'<span class="badge b-violet">WoS · {html.escape(c)}</span>')
    if isinstance(fila.get("jif_cuartil"), str):
        badges.append(f'<span class="badge b-violet">JIF {fila["jif_cuartil"]}</span>')
    if abierta or fila.get("es_oa") == 1:
        badges.append('<span class="badge b-green">🔓 Acceso abierto</span>')
    if fila.get("seguida"):
        badges.append('<span class="badge b-amber">⭐ En seguimiento</span>')
    carreras = "".join(f'<span class="badge b-gray">{CARRERAS[c]["icono"]} {html.escape(c)}</span>'
                       for c in str(fila.get("carreras") or "").split("; ") if c in CARRERAS)
    st.markdown(f"""<div class="card"><h2>{e(fila['titulo'])}</h2>
<div class="muted">{e(fila.get('editorial'))} · {e(fila.get('pais'))} · ISSN {e(fila.get('issns'))}</div>
<div class="badges">{''.join(badges)}</div><div class="badges">{carreras}</div></div>""", unsafe_allow_html=True)

    # Exigencias principales
    apc = fila.get("doaj_apc") if isinstance(fila.get("doaj_apc"), str) else (
        f"USD {_n(fila['apc_usd'])}" if not _vacio(fila.get("apc_usd")) else "No registrado")
    ext = extension(fila) or "No encontrado"
    resumen = f"{_n(fila['resumen_max'])} palabras" if not _vacio(fila.get("resumen_max")) else "—"
    semanas = f"{_n(fila['doaj_semanas'])} semanas" if not _vacio(fila.get("doaj_semanas")) else "—"
    url = fila.get("exi_url") if isinstance(fila.get("exi_url"), str) else (
        fila.get("doaj_instrucciones") if isinstance(fila.get("doaj_instrucciones"), str) else fila.get("web"))
    enlace = (f'<a href="{html.escape(url)}" target="_blank">Ver instrucciones para autores ↗</a>'
              if isinstance(url, str) and url.startswith("http") else "")
    evid = (f'<div class="evid">“{html.escape(fila["evidencia"])}”</div>'
            if isinstance(fila.get("evidencia"), str) and fila["evidencia"] else "")
    origen = ("Datos ingresados por la FACE." if fila.get("manual") == 1 else
              "Detectado automáticamente en el sitio de la revista: verifique antes de enviar.")
    st.markdown(f"""<div class="card"><h3>📝 Exigencias principales</h3>
<div class="badges" style="margin-bottom:12px">{badge_recepcion(fila)}</div>
<div class="tiles">
<div class="tile"><span>Extensión máxima</span><b>{html.escape(ext)}</b></div>
<div class="tile"><span>Resumen</span><b>{resumen}</b></div>
<div class="tile"><span>Cobro por publicar (APC)</span><b>{html.escape(apc)}</b></div>
<div class="tile"><span>Revisión por pares</span><b>{e(fila.get('doaj_revision'))}</b></div>
<div class="tile"><span>Tiempo a publicación</span><b>{semanas}</b></div>
<div class="tile"><span>Idiomas</span><b>{e(fila.get('doaj_idiomas'))}</b></div>
</div>{evid}<div class="muted" style="margin-top:10px">{origen} {enlace}</div></div>""", unsafe_allow_html=True)

    if ADMIN:
        with st.expander("✏️ Corregir o completar exigencias"):
            with st.form(f"exi_{rid}"):
                c1, c2, c3 = st.columns(3)
                pal = c1.number_input("Palabras máximas", 0, 100000,
                                      int(fila["palabras_max"]) if not _vacio(fila.get("palabras_max")) else 0, step=500)
                car = c2.number_input("Caracteres máximos", 0, 500000,
                                      int(fila["caracteres_max"]) if not _vacio(fila.get("caracteres_max")) else 0, step=1000)
                res = c3.number_input("Palabras del resumen", 0, 2000,
                                      int(fila["resumen_max"]) if not _vacio(fila.get("resumen_max")) else 0, step=50)
                opciones = ["Sin información", "Continua", "Convocatoria abierta", "Convocatoria cerrada"]
                actual = fila.get("recepcion") if fila.get("recepcion") in opciones else "Sin información"
                rec = c1.selectbox("Recepción de artículos", opciones, index=opciones.index(actual))
                fecha = c2.date_input("Fecha límite (si es convocatoria)",
                                      pd.to_datetime(fila["fecha_limite"]).date() if not _vacio(fila.get("fecha_limite")) else None)
                u = c3.text_input("Enlace a instrucciones", url if isinstance(url, str) else "")
                if st.form_submit_button("Guardar exigencias", type="primary"):
                    monitor.guardar_exigencias(con, rid, {
                        "palabras_max": pal or None, "caracteres_max": car or None, "resumen_max": res or None,
                        "recepcion": None if rec == "Sin información" else rec,
                        "fecha_limite": fecha.isoformat() if fecha else None, "url": u or None,
                        "evidencia": "Ingresado manualmente."}, manual=True)
                    persistir("exigencias.csv", web.tabla_csv(con, "exigencias"), f"Exigencias: {fila['titulo']}")
                    marcar_cambio()
                    st.rerun()

    t1, t2, t3 = st.tabs(["📊 Indicadores de producción", "🗂️ Clasificación", "🗒️ Notas"])
    with t1:
        st.markdown(f"""<div class="tiles">
<div class="tile"><span>SJR</span><b>{_n(fila.get('sjr'), 3)}</b></div>
<div class="tile"><span>Índice H</span><b>{_n(fila.get('h_index'))}</b></div>
<div class="tile"><span>Citas por documento (2 años)</span><b>{_n(fila.get('citas_doc_2y'), 2)}</b></div>
<div class="tile"><span>Documentos último año</span><b>{_n(fila.get('docs_anio'))}</b></div>
<div class="tile"><span>Documentos 3 años</span><b>{_n(fila.get('docs_3y'))}</b></div>
<div class="tile"><span>Citas 3 años</span><b>{_n(fila.get('citas_3y'))}</b></div>
<div class="tile"><span>Trabajos totales (OpenAlex)</span><b>{_n(fila.get('oa_trabajos'))}</b></div>
<div class="tile"><span>Citas totales (OpenAlex)</span><b>{_n(fila.get('oa_citas'))}</b></div>
<div class="tile"><span>JIF (JCR)</span><b>{_n(fila.get('jif'), 3)}</b></div>
</div>""", unsafe_allow_html=True)
        prod = monitor.produccion_anual(fila.get("prod_anual"))
        if not prod.empty:
            prod = prod[prod["Año"] >= prod["Año"].max() - 9].astype({"Año": str})
            a, b = st.columns(2)
            a.markdown("**Artículos publicados por año**")
            a.bar_chart(prod.set_index("Año")[["Artículos"]], color="#1f6fb5", height=220)
            b.markdown("**Citas recibidas por año**")
            b.area_chart(prod.set_index("Año")[["Citas"]], color="#16a34a", height=220)
        hist = pd.read_sql("SELECT anio AS Año, sjr AS SJR FROM historial WHERE rid=? ORDER BY anio",
                           con, params=(rid,))
        if len(hist) > 1:
            st.markdown("**Evolución del SJR**")
            st.line_chart(hist.astype({"Año": str}).set_index("Año"), color="#0b2e59", height=200)
    with t2:
        cats = categorias(fila.get("categorias"))
        if cats:
            st.markdown("".join(f'<span class="badge {q.lower()}" style="margin:3px">{html.escape(c.strip())} · {q}</span>'
                                for c, q in cats), unsafe_allow_html=True)
        st.markdown(f"**Áreas Scopus:** {_t(fila.get('areas'))}  \n**Categorías WoS:** {_t(fila.get('wos_categorias'))}  \n"
                    f"**Cobertura Scopus:** {_t(fila.get('cobertura'))}")
        if isinstance(fila.get("web"), str):
            st.markdown(f"[Sitio web de la revista ↗]({fila['web']})")
    with t3:
        if not ADMIN:
            st.markdown(db.nota(con, rid) or "_Sin notas registradas por la FACE._")
        else:
            texto = st.text_area("Notas para los académicos (plantilla, formato de citas, experiencias…)",
                                 db.nota(con, rid), key=f"nota_{rid}", height=130)
            if st.button("Guardar nota", key=f"g_{rid}"):
                db.nota(con, rid, texto)
                persistir("notas.csv", web.tabla_csv(con, "notas"), f"Nota: {fila['titulo']}")
                st.toast("Nota guardada.")

    if ADMIN:
        seguida = bool(fila.get("seguida"))
        if st.button("Quitar de seguimiento" if seguida else "⭐ Seguir esta revista (recibir alertas)",
                     key=f"s_{rid}", type="secondary" if seguida else "primary"):
            db.seguir(con, rid, not seguida)
            persistir("seguimiento.csv", web.tabla_csv(con, "seguimiento"),
                      f"{'Quitar' if seguida else 'Seguir'}: {fila['titulo']}")
            marcar_cambio()
            st.rerun()


# ---------------------------------------------------------------- tabla
def _color_q(v):
    return {"Q1": "background-color:#dcfce7;color:#166534;font-weight:600",
            "Q2": "background-color:#fef9c3;color:#854d0e;font-weight:600",
            "Q3": "background-color:#ffedd5;color:#9a3412;font-weight:600",
            "Q4": "background-color:#fee2e2;color:#991b1b;font-weight:600"}.get(v, "")


def _color_r(v):
    if v in ("Continua", "Convocatoria abierta"):
        return "color:#166534;font-weight:600"
    if v == "Convocatoria cerrada":
        return "color:#991b1b"
    return ""


def tabla(sub: pd.DataFrame, clave: str):
    if sub.empty:
        st.info("No hay revistas con esos filtros.")
        return
    mostrar = pd.DataFrame({
        "Revista": sub["titulo"],
        "Cuartil": sub["cuartil_sjr"].fillna("—"),
        "SJR": sub["sjr"],
        "Índice H": sub["h_index"],
        "WoS": sub["wos_colecciones"].replace("", "—").fillna("—"),
        "Extensión máx.": [extension(r) or "—" for _, r in sub.iterrows()],
        "Recepción": sub["recepcion"].fillna("—") if "recepcion" in sub else "—",
        "APC (USD)": sub["apc_usd"],
        "Acceso abierto": ["Sí" if (a == "Yes" or o == 1) else "No"
                           for a, o in zip(sub["acceso_abierto"], sub.get("es_oa", [None] * len(sub)))],
        "País": sub["pais"].fillna("—"),
        "Carreras": sub["carreras"].fillna(""),
    })
    estilo = (mostrar.style.map(_color_q, subset=["Cuartil"]).map(_color_r, subset=["Recepción"])
              .format({"SJR": "{:.3f}", "Índice H": "{:.0f}", "APC (USD)": "US$ {:,.0f}"}, na_rep="—"))
    ev = st.dataframe(estilo, hide_index=True, width="stretch", height=460, on_select="rerun",
                      selection_mode="single-row", key=clave,
                      column_config={
                          "Revista": st.column_config.TextColumn(width="large"),
                          "Carreras": st.column_config.TextColumn(width="medium")})
    a, b, c = st.columns([1, 1, 5])
    a.download_button("⬇️ Excel", _excel(mostrar), "revistas_face.xlsx", key=clave + "_xlsx", width="stretch")
    b.download_button("⬇️ CSV", mostrar.to_csv(index=False).encode("utf-8-sig"), "revistas_face.csv",
                      "text/csv", key=clave + "_csv", width="stretch")
    c.caption("👆 Haga clic en el cuadro a la izquierda de una revista para ver su ficha completa.")
    filas = ev.selection.rows if ev and ev.selection else []
    if filas:
        ficha(sub.iloc[filas[0]])


def _excel(df_):
    buf = io.BytesIO()
    df_.to_excel(buf, index=False)
    return buf.getvalue()


# ---------------------------------------------------------------- páginas
def correr_actualizacion(descargar=True) -> bool:
    barra = st.progress(0.0, "Comenzando…")
    avisos, error = monitor.actualizacion_completa(
        con, cfg, progreso=lambda f, t: barra.progress(min(max(f, 0.0), 1.0), t), descargar=descargar,
        exigencias_limite=150)
    marcar_cambio()
    if error and not list(config.FUENTES.glob("scimago_*.csv")):
        st.error("No se pudo descargar la lista de Scopus automáticamente. Cárguela a mano (abajo).")
        return False
    if error:
        st.warning("No se pudo descargar una lista nueva de Scopus; se usó la que ya tenía.")
    st.success(f"Listo. {len(avisos)} alerta(s) nuevas.")
    return True


def pagina_buscar():
    df = DF
    st.markdown("##### ¿Para qué carrera busca revista?")
    nombres = list(CARRERAS)
    sel = st.pills("Carrera", nombres, selection_mode="multi", label_visibility="collapsed",
                   format_func=lambda c: f"{CARRERAS[c]['icono']} {c}", key="carreras_sel")
    sub = df[df["carreras"] != ""]
    if sel:
        sub = sub[sub["carreras"].map(lambda x: any(c in x for c in sel))]

    f1, f2, f3 = st.columns([3, 2, 2])
    texto = f1.text_input("Buscar", placeholder="🔎  Título, ISSN o editorial", label_visibility="collapsed")
    cuartiles = f2.pills("Cuartil", ["Q1", "Q2", "Q3", "Q4"], selection_mode="multi", label_visibility="collapsed")
    base = f3.segmented_control("Indexación", ["Todas", "Scopus", "WoS", "Ambas"], default="Todas",
                                label_visibility="collapsed")
    with st.expander("Más filtros"):
        g1, g2, g3, g4 = st.columns(4)
        cats = sorted({c.strip() for x in sub["categorias"].dropna() for c, _ in categorias(x)})
        cat = g1.selectbox("Categoría específica", ["(todas)"] + cats)
        paises = g2.multiselect("País", sorted(df["pais"].dropna().unique()), placeholder="Todos")
        apc_max = g3.number_input("APC máximo (USD, 0 = sin límite)", 0, 20000, 0, step=100)
        solo_oa = g4.toggle("Solo acceso abierto")
        solo_cont = g4.toggle("Solo recepción continua o abierta")
    if texto:
        t = texto.lower()
        sub = sub[sub["titulo"].fillna("").str.lower().str.contains(t, regex=False)
                  | sub["issns"].fillna("").str.contains(texto.upper(), regex=False)
                  | sub["editorial"].fillna("").str.lower().str.contains(t, regex=False)]
    if base == "Scopus":
        sub = sub[sub["scopus"] == 1]
    elif base == "WoS":
        sub = sub[sub["wos"] == 1]
    elif base == "Ambas":
        sub = sub[(sub["scopus"] == 1) & (sub["wos"] == 1)]
    if cat != "(todas)":
        sub = sub.copy()
        sub["cuartil_sjr"] = sub["categorias"].map(lambda x: dict((c.strip(), q) for c, q in categorias(x)).get(cat))
        sub = sub[sub["cuartil_sjr"].notna()]
    if cuartiles:
        sub = sub[sub["cuartil_sjr"].isin(cuartiles)]
    if paises:
        sub = sub[sub["pais"].isin(paises)]
    if solo_oa:
        sub = sub[(sub["acceso_abierto"] == "Yes") | (sub.get("es_oa") == 1)]
    if apc_max:
        sub = sub[sub["apc_usd"].isna() | (sub["apc_usd"] <= apc_max)]
    if solo_cont:
        sub = sub[sub["recepcion"].isin(["Continua", "Convocatoria abierta"])]
    sub = sub.sort_values("sjr", ascending=False, na_position="last").reset_index(drop=True)
    st.markdown(f"**{_n(len(sub))} revistas** · " + " · ".join(
        f"{q}: {_n((sub['cuartil_sjr'] == q).sum())}" for q in ["Q1", "Q2", "Q3", "Q4"]))
    tabla(sub, "busqueda")


def pagina_seguidas():
    sub = DF[DF["seguida"]].reset_index(drop=True)
    if sub.empty:
        st.info("Aún no hay revistas en seguimiento." +
                (" Búsquelas y pulse **⭐ Seguir esta revista** en su ficha." if ADMIN else ""))
    else:
        tabla(sub, "seguidas")


def pagina_alertas():
    al = pd.read_sql("SELECT id, fecha, titulo, tipo, detalle, leida FROM alertas ORDER BY id DESC", con)
    if al.empty:
        st.info("Sin alertas por ahora. Aparecen cuando una revista en seguimiento cambia de cuartil, "
                "indexación o APC, o cuando entra una revista nueva para las carreras de la FACE.")
        return
    iconos = {"Cuartil SJR": "📊", "Cuartil JIF": "📊", "Indexación": "🏷️", "Indexación WoS": "🏷️",
              "APC": "💲", "Nueva revista": "🆕"}
    for r in al.head(200).itertuples():
        st.markdown(f'<div class="card" style="padding:12px 16px"><b>{iconos.get(r.tipo, "🔔")} {html.escape(r.titulo)}</b>'
                    f'<div class="muted">{html.escape(r.detalle)} · {r.fecha}</div></div>', unsafe_allow_html=True)
    if not MODO_WEB and st.button("Marcar todas como leídas"):
        con.execute("UPDATE alertas SET leida=1")
        con.commit()
        st.rerun()


def pagina_actualizar():
    st.markdown("### ⚙️ Actualizar datos")
    if MODO_WEB:
        st.caption("La actualización corre sola en GitHub cada lunes. Puede lanzarla ahora; tarda unos minutos "
                   "y la página se actualiza sola al terminar.")
    if st.button("🔄 Actualizar todo ahora", type="primary"):
        if MODO_WEB:
            gh = github()
            if gh is None:
                st.warning("Para lanzarla desde aquí falta conectar GitHub (ver LEEME). Mientras tanto se "
                           "actualiza sola cada lunes.")
            else:
                try:
                    gh.ejecutar_actualizacion()
                    st.success("Actualización lanzada en GitHub.")
                except Exception as ex:
                    st.error(f"No se pudo lanzar la actualización: {ex}")
        elif correr_actualizacion():
            st.rerun()
    st.caption(f"Última actualización: {db.meta(con, 'ultima_actualizacion') or 'nunca'}")

    st.markdown("#### Lista de Scopus (Scimago)")
    st.caption("Normalmente se descarga sola. Si falla, descárguela en "
               "[scimagojr.com/journalrank.php](https://www.scimagojr.com/journalrank.php) (Download data) y súbala.")
    sc = st.file_uploader("Archivo de Scimago (.csv)", type=["csv"], key="sc_up")
    if sc and st.button("Agregar lista de Scopus"):
        try:
            anio = monitor.importar_scimago(con, sc)
            persistir(f"fuentes/scimago_{anio}.csv", sc.getvalue(), f"Lista Scimago {anio}")
            monitor.actualizar_listas(con, cfg)
            marcar_cambio()
            st.success(f"Lista de Scopus {anio} agregada.")
        except Exception as ex:
            st.error(f"No se pudo leer el archivo: {ex}")

    st.markdown("#### Web of Science (una vez al año)")
    st.caption("Descargue SSCI, SCIE, AHCI y ESCI en [mjl.clarivate.com](https://mjl.clarivate.com) "
               "(cuenta gratuita) y súbalas aquí. El programa reconoce la colección por el nombre del archivo.")
    archivos = st.file_uploader("Listas de WoS (CSV o Excel)", type=["csv", "xlsx", "xls"], accept_multiple_files=True)
    if archivos:
        elecciones = {}
        for f in archivos:
            det = fuentes.detectar_coleccion(f.name)
            opciones = fuentes.COLECCIONES_WOS + ["JCR"]
            elecciones[f.name] = st.selectbox(f"Colección de {f.name}", opciones,
                                              index=opciones.index(det) if det else 0)
        if st.button("Agregar listas de WoS", type="primary"):
            for f in archivos:
                try:
                    st.success(f"{f.name}: {monitor.importar_wos(f, elecciones[f.name]):,} revistas.")
                    ext = ".xlsx" if f.name.lower().endswith((".xlsx", ".xls")) else ".csv"
                    persistir(f"fuentes/wos_{elecciones[f.name]}{ext}", f.getvalue(), f"Lista WoS {elecciones[f.name]}")
                except Exception as ex:
                    st.error(f"{f.name}: {ex}")
            monitor.actualizar_listas(con, cfg)
            marcar_cambio()
    cargados = sorted(p.name for p in config.FUENTES.glob("*.*") if not p.name.startswith("."))
    st.caption("Archivos cargados: " + (", ".join(cargados) or "ninguno"))


def pagina_config():
    st.markdown("### 🛠️ Configuración")
    cfg["carreras_interes"] = st.multiselect(
        "Carreras para las que se generan alertas de revistas nuevas", list(CARRERAS),
        [c for c in cfg.get("carreras_interes", list(CARRERAS)) if c in CARRERAS])
    cfg["alertar_nuevas_en_areas"] = st.toggle("Avisar cuando aparezcan revistas nuevas", cfg["alertar_nuevas_en_areas"])
    dest = st.text_input("Correos que reciben las alertas (separados por coma)", ", ".join(cfg["destinatarios"]))
    cfg["destinatarios"] = [d.strip() for d in dest.split(",") if d.strip()]
    if MODO_WEB:
        st.caption("La cuenta que envía los correos se configura en los secretos de GitHub (ver LEEME).")
    else:
        cfg["email_activo"] = st.toggle("Enviar alertas por correo", cfg["email_activo"])
        c1, c2 = st.columns(2)
        cfg["smtp_host"] = c1.text_input("Servidor SMTP", cfg["smtp_host"])
        cfg["smtp_puerto"] = c2.number_input("Puerto", 1, 65535, int(cfg["smtp_puerto"]))
        cfg["smtp_usuario"] = c1.text_input("Usuario (correo)", cfg["smtp_usuario"])
        cfg["smtp_password"] = c2.text_input("Contraseña de aplicación", cfg["smtp_password"], type="password")
        cfg["openalex_email"] = c1.text_input("Correo para OpenAlex (opcional)", cfg["openalex_email"])
        cfg["elsevier_api_key"] = c2.text_input("API key de Elsevier para CiteScore (opcional)",
                                                cfg["elsevier_api_key"], type="password")
    if st.button("Guardar configuración", type="primary"):
        config.guardar(cfg)
        persistir("config.json", web.config_publica(cfg), "Configuración")
        marcar_cambio()
        st.success("Configuración guardada.")


def bienvenida_local():
    hero("👋 Monitor de Revistas FACE", "Revistas Scopus y Web of Science para las carreras de la FACE, "
         "con sus indicadores y exigencias para autores.")
    st.markdown("Pulse **Comenzar** para descargar la lista de revistas. Tarda unos minutos y solo se hace una vez.")
    if st.button("🚀 Comenzar", type="primary"):
        if correr_actualizacion():
            st.rerun()
    with st.expander("¿Falló la descarga? Cargar la lista a mano"):
        st.markdown("1. Abra [scimagojr.com/journalrank.php](https://www.scimagojr.com/journalrank.php).\n"
                    "2. Pulse **Download data**.\n3. Arrastre el archivo aquí:")
        manual = st.file_uploader("Archivo de Scimago (.csv)", type=["csv"], key="manual_sc")
        if manual and st.button("Continuar con este archivo", type="primary"):
            monitor.importar_scimago(con, manual)
            if correr_actualizacion(descargar=False):
                st.rerun()


def pagina_vacia():
    st.info("La base de revistas aún no tiene datos. Vuelva en unos minutos.")


# ---------------------------------------------------------------- armado
DF = datos(version())
if not DF.empty:
    face = DF[DF["carreras"] != ""]
    con_exi = face["recepcion"].notna().sum() + face["palabras_max"].notna().sum()
    hero("📚 Monitor de Revistas FACE · UBB",
         "Revistas indexadas en Scopus y Web of Science para las carreras de la Facultad de Ciencias "
         "Empresariales: cuartiles, indicadores de producción y exigencias para autores.",
         [("Revistas", _n(len(face))), ("Q1", _n((face["cuartil_sjr"] == "Q1").sum())),
          *([("En WoS", _n((face["wos"] == 1).sum()))] if (face["wos"] == 1).any() else []),
          ("Acceso abierto", _n((face["acceso_abierto"] == "Yes").sum())),
          ("Actualizado", (db.meta(con, "ultima_actualizacion") or "—")[:10])])

if MODO_WEB:
    with st.sidebar:
        st.markdown("### 🔒 Administración")
        if not ADMIN:
            clave = st.text_input("Contraseña", type="password")
            if clave:
                if secreto("admin_password") and clave == secreto("admin_password"):
                    st.session_state.admin = True
                    st.rerun()
                else:
                    st.error("Contraseña incorrecta." if secreto("admin_password") else
                             "Aún no se ha definido la contraseña (secreto admin_password en Streamlit).")
        elif st.button("Cerrar sesión"):
            st.session_state.admin = False
            st.rerun()

if DF.empty and not MODO_WEB:
    paginas = [st.Page(bienvenida_local, title="Comenzar", icon="🚀"), st.Page(pagina_config, title="Configuración", icon="🛠️")]
elif DF.empty:
    paginas = [st.Page(pagina_vacia, title="Inicio", icon="📚")]
    if ADMIN:
        paginas.append(st.Page(pagina_actualizar, title="Actualizar datos", icon="⚙️"))
else:
    paginas = [st.Page(pagina_buscar, title="Buscar revistas", icon="🔎", default=True),
               st.Page(pagina_seguidas, title="En seguimiento", icon="⭐"),
               st.Page(pagina_alertas, title="Alertas", icon="🔔")]
    if ADMIN:
        paginas += [st.Page(pagina_actualizar, title="Actualizar datos", icon="⚙️"),
                    st.Page(pagina_config, title="Configuración", icon="🛠️")]
st.navigation(paginas, position="top").run()
