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

# Streamlit Cloud no recarga los módulos propios al publicar una versión nueva: se descartan
# los que cambiaron en disco para que se importe la versión actual.
import sys  # noqa: E402
_propios = [k for k in list(sys.modules) if k == "nucleo" or k.startswith("nucleo.")]
if any(getattr(sys.modules[k], "__file__", None)
       and os.path.getmtime(sys.modules[k].__file__) > getattr(sys.modules[k], "_mtime_carga", 0)
       for k in _propios):
    for k in _propios:  # se descartan todos, incluido el paquete, para no mezclar versiones
        del sys.modules[k]
from nucleo import config, db, exigencias, fuentes, monitor, recomendador, web  # noqa: E402
for _mod in (sys.modules["nucleo"], config, db, exigencias, fuentes, monitor, recomendador, web):
    if not hasattr(_mod, "_mtime_carga"):
        _mod._mtime_carga = os.path.getmtime(_mod.__file__)
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
.recep { display: flex; justify-content: space-between; align-items: center; gap: 14px; border-radius: 14px;
         padding: 14px 18px; margin-bottom: 14px; border: 1px solid #e2e8f0; background: #f8fafc; }
.recep.ok { background: #f0fdf4; border-color: #bbf7d0; } .recep.aviso { background: #fffbeb; border-color: #fde68a; }
.recep.cerrada { background: #fef2f2; border-color: #fecaca; }
.recep .lbl { display: block; font-size: .72rem; color: #64748b; text-transform: uppercase; letter-spacing: .05em; font-weight: 700; }
.recep b { font-size: 1.2rem; color: #0f172a; }
.periodo { font-weight: 600; color: #1e293b; margin-top: 2px; }
.recep .nota { font-size: .82rem; color: #64748b; margin-top: 4px; }
.cuenta { text-align: center; background: #fff; border-radius: 12px; padding: 8px 14px; border: 1px solid #e2e8f0; min-width: 90px; }
.cuenta b { display: block; font-size: 1.6rem; color: #0b2e59; } .cuenta span { font-size: .72rem; color: #64748b; }
.conv { min-height: 190px; } .conv .tit { font-size: 1rem; color: #0f172a; display: block; margin-bottom: 2px; }
.encab { margin: 4px 0 14px 0; } .encab h2 { font-size: 1.6rem; font-weight: 800; color: #0f172a; margin: 0; letter-spacing: -.02em; }
.encab p { color: #64748b; margin: 2px 0 0 0; }
.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin: 6px 0 18px 0; }
.kpi { background: #fff; border: 1px solid #e6ebf2; border-radius: 16px; padding: 14px 18px; box-shadow: 0 2px 10px rgba(15,23,42,.04); }
.kpi span { display: block; font-size: .74rem; color: #64748b; text-transform: uppercase; letter-spacing: .05em; font-weight: 700; }
.kpi b { display: block; font-size: 1.9rem; font-weight: 800; color: #0b2e59; line-height: 1.2; margin-top: 2px; }
.kpi small { color: #64748b; font-size: .8rem; }
.mini { display: flex; gap: 12px; align-items: center; padding: 8px 0; border-bottom: 1px solid #f1f5f9; }
.mini .dias { flex: 0 0 54px; text-align: center; background: #eff6ff; border-radius: 12px; padding: 4px 0; }
.mini .dias b { display: block; font-size: 1.2rem; color: #0b2e59; } .mini .dias span { font-size: .7rem; color: #64748b; }
.fila-top { display: flex; align-items: center; gap: 12px; padding: 7px 0; border-bottom: 1px solid #f1f5f9; }
.fila-top .pos { flex: 0 0 28px; height: 28px; border-radius: 8px; background: #eff6ff; color: #0b2e59; font-weight: 800;
                 display: flex; align-items: center; justify-content: center; font-size: .85rem; }
.fila-top .nom { flex: 1; font-weight: 600; color: #0f172a; } .fila-top .nom small { display: block; color: #64748b; font-weight: 400; }
.fila-top a { color: #1f6fb5; font-weight: 600; font-size: .85rem; text-decoration: none; white-space: nowrap; }
.accion { text-align: left; min-height: 104px; } .accion .ic { font-size: 1.8rem; display: block; }
.accion b { font-size: 1.08rem; color: #0f172a; } .accion p { color: #64748b; font-size: .88rem; margin: 2px 0 0 0; }
.tema { display: grid; grid-template-columns: minmax(0, 2.2fr) 1.4fr auto auto; gap: 10px; align-items: center;
        padding: 6px 0; border-bottom: 1px solid #f1f5f9; font-size: .9rem; }
.tema .nom { color: #0f172a; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tema .bar { height: 8px; background: #eef2f7; border-radius: 99px; overflow: hidden; }
.tema .bar i { display: block; height: 100%; background: #256abf; border-radius: 99px; }
.tema .num { color: #64748b; font-size: .8rem; white-space: nowrap; }
.autoria { text-align: center; color: #64748b; font-size: .85rem; margin: 28px 0 8px 0; padding-top: 14px;
           border-top: 1px solid #eef2f7; } .autoria b { color: #0b2e59; }
.cab { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; flex-wrap: wrap; }
.btn-guia { background: #0b2e59; color: #fff !important; padding: 8px 14px; border-radius: 10px; font-size: .88rem;
            white-space: nowrap; box-shadow: 0 2px 8px rgba(11,46,89,.2); }
.btn-guia:hover { background: #1f6fb5; }
.rec { display: flex; gap: 16px; align-items: flex-start; }
.rec .num { flex: 0 0 46px; height: 46px; border-radius: 14px; background: linear-gradient(135deg,#0b2e59,#1f6fb5);
            color: #fff; font-weight: 800; font-size: 1.3rem; display: flex; align-items: center; justify-content: center; }
.rec .cuerpo { flex: 1; min-width: 0; }
.rec .tit { font-size: 1.08rem; font-weight: 700; color: #0f172a; }
.barra { height: 8px; background: #eef2f7; border-radius: 99px; overflow: hidden; margin: 8px 0 4px 0; }
.barra div { height: 100%; background: linear-gradient(90deg,#16a34a,#22c55e); border-radius: 99px; }
.rec ul { margin: 6px 0 8px 0; padding-left: 18px; color: #334155; font-size: .9rem; }
.rec .acciones a { margin-right: 14px; font-size: .9rem; }
.card a { color: #1f6fb5; font-weight: 600; text-decoration: none; }
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
    # incluye la fecha de los archivos del programa para no usar datos armados por una versión anterior
    codigo = max(os.path.getmtime(f) for f in (_BASE / "nucleo").glob("*.py"))
    return "|".join(str(db.meta(con, k)) for k in
                    ("ultima_actualizacion", "ultimo_enriquecimiento", "cambio_local")) + f"|{codigo}"


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


COLOR_REC = {"Continua": "b-green", "Continua (habitual)": "b-gray", "Convocatoria abierta": "b-green",
             "Número especial abierto": "b-amber", "Convocatoria cerrada": "b-red", "Por convocatoria": "b-amber"}


def badge_recepcion(fila) -> str:
    r = fila.get("recepcion_txt") or "Continua (habitual)"
    texto = {"Continua": "Recepción continua", "Continua (habitual)": "Recepción continua (estimada)"}.get(r, r)
    return f'<span class="badge {COLOR_REC.get(r, "b-gray")}">📬 {html.escape(texto)}</span>'


def dias_restantes(limite) -> int | None:
    try:
        return (pd.to_datetime(limite).date() - pd.Timestamp.now().date()).days
    except (TypeError, ValueError):
        return None


def bloque_recepcion(fila) -> str:
    """Franja con el estado de recepción, el periodo y de dónde sale el dato."""
    r = fila.get("recepcion_txt") or "Continua (habitual)"
    periodo = fila.get("periodo_txt") or "Todo el año"
    origen = fila.get("recepcion_origen")
    nota = {"manual": "Dato ingresado por la FACE.",
            "detectada": "Leído en el sitio de la revista.",
            "estimada": "No encontramos un periodo publicado. Las revistas indexadas suelen recibir "
                        "artículos todo el año; confírmelo en las instrucciones."}.get(origen, "")
    dias = dias_restantes(fila.get("fecha_limite")) if r in ("Convocatoria abierta", "Número especial abierto") else None
    cuenta = (f'<div class="cuenta"><b>{dias}</b><span>{"día" if dias == 1 else "días"} para el cierre</span></div>'
              if dias is not None and dias >= 0 else "")
    clase = {"b-green": "ok", "b-amber": "aviso", "b-red": "cerrada"}.get(COLOR_REC.get(r), "neutra")
    return (f'<div class="recep {clase}"><div><span class="lbl">Recepción de artículos</span>'
            f'<b>{html.escape(r)}</b><div class="periodo">🗓️ {html.escape(periodo)}</div>'
            f'<div class="nota">{html.escape(nota)}</div></div>{cuenta}</div>')


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
    guia = fila.get("url_instr")
    boton = (f'<a class="btn-guia" href="{html.escape(guia)}" target="_blank">📄 Instrucciones para autores ↗</a>'
             if isinstance(guia, str) else "")
    st.markdown(f"""<div class="card"><div class="cab"><h2>{e(fila['titulo'])}</h2>{boton}</div>
<div class="muted">{e(fila.get('editorial'))} · {e(fila.get('pais'))} · ISSN {e(fila.get('issns'))}</div>
<div class="badges">{''.join(badges)}</div><div class="badges">{carreras}</div></div>""", unsafe_allow_html=True)

    # Exigencias principales
    apc = fila.get("doaj_apc") if isinstance(fila.get("doaj_apc"), str) else (
        f"USD {_n(fila['apc_usd'])}" if not _vacio(fila.get("apc_usd")) else "No registrado")
    ext = extension(fila) or "No encontrado"
    resumen = f"{_n(fila['resumen_max'])} palabras" if not _vacio(fila.get("resumen_max")) else "—"
    semanas = f"{_n(fila['doaj_semanas'])} semanas" if not _vacio(fila.get("doaj_semanas")) else "—"
    url = fila.get("url_instr")
    enlace = (f'<a href="{html.escape(url)}" target="_blank">Ver instrucciones para autores ↗</a>'
              if isinstance(url, str) and url.startswith("http") else "")
    evid = (f'<div class="evid">“{html.escape(fila["evidencia"])}”</div>'
            if isinstance(fila.get("evidencia"), str) and fila["evidencia"] else "")
    sin_datos = not any(not _vacio(fila.get(k)) for k in
                        ("palabras_max", "caracteres_max", "paginas_max", "resumen_max", "recepcion"))
    bloqueada = (exigencias.bloqueado(fila.get("web")) or exigencias.bloqueado(url)
                 or exigencias.editorial_bloqueada(fila.get("editorial")))
    if fila.get("manual") == 1:
        origen = "Datos ingresados por la FACE."
    elif sin_datos and bloqueada:
        origen = (f"{e(fila.get('editorial'))} no permite que programas lean su sitio, por eso la extensión "
                  "máxima no aparece. Está en sus instrucciones para autores:")
    elif sin_datos and not _vacio(fila.get("exi_fecha")):
        origen = ("El sitio de la revista no publica estos datos en un formato que se pueda leer "
                  "automáticamente. Revíselos directamente:")
    else:
        origen = "Detectado automáticamente en el sitio de la revista: verifique antes de enviar."
    st.markdown(f"""<div class="card"><h3>📝 Exigencias principales</h3>
{bloque_recepcion(fila)}
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
                opciones = ["Sin información", "Continua", "Convocatoria abierta", "Número especial abierto"]
                actual = fila.get("recepcion") if fila.get("recepcion") in opciones else "Sin información"
                rec = c1.selectbox("Recepción de artículos", opciones, index=opciones.index(actual))
                fecha = c2.date_input("Cierre de recepción (si es convocatoria)",
                                      pd.to_datetime(fila["fecha_limite"]).date() if not _vacio(fila.get("fecha_limite")) else None)
                inicio = c3.date_input("Apertura de recepción (opcional)",
                                       pd.to_datetime(fila["fecha_inicio"]).date() if not _vacio(fila.get("fecha_inicio")) else None)
                u = st.text_input("Enlace a instrucciones", url if isinstance(url, str) else "")
                if st.form_submit_button("Guardar exigencias", type="primary"):
                    monitor.guardar_exigencias(con, rid, {
                        "palabras_max": pal or None, "caracteres_max": car or None, "resumen_max": res or None,
                        "recepcion": None if rec == "Sin información" else rec,
                        "fecha_limite": fecha.isoformat() if fecha else None,
                        "fecha_inicio": inicio.isoformat() if inicio else None, "url": u or None,
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
    if v in ("Continua", "Convocatoria abierta", "Número especial abierto"):
        return "color:#166534;font-weight:600"
    if v == "Convocatoria cerrada":
        return "color:#991b1b"
    if v == "Continua (habitual)":
        return "color:#64748b;font-style:italic"
    return ""


def tabla(sub: pd.DataFrame, clave: str):
    if sub.empty:
        st.info("No hay revistas con esos filtros.")
        return
    mostrar = pd.DataFrame({
        "Revista": sub["titulo"],
        "Instrucciones": sub["url_instr"],
        "Cuartil": sub["cuartil_sjr"].fillna("—"),
        "SJR": pd.to_numeric(sub["sjr"], errors="coerce"),
        "Índice H": pd.to_numeric(sub["h_index"], errors="coerce"),
        "WoS": sub["wos_colecciones"].replace("", "—").fillna("—"),
        "Extensión máx.": [extension(r) or "—" for _, r in sub.iterrows()],
        "Recepción": sub["recepcion_txt"],
        "Fecha de recepción": sub["periodo_txt"],
        "APC (USD)": [f"US$ {_n(v)}" if not _vacio(v) else "Sin dato" for v in pd.to_numeric(sub["apc_usd"], errors="coerce")],
        "Acceso abierto": ["Sí" if (a == "Yes" or o == 1) else "No"
                           for a, o in zip(sub["acceso_abierto"], sub.get("es_oa", [None] * len(sub)))],
        "País": sub["pais"].fillna("—"),
        "Áreas": sub["carreras"].fillna(""),
    })
    estilo = (mostrar.style.map(_color_q, subset=["Cuartil"]).map(_color_r, subset=["Recepción"])
              .format({"SJR": "{:.3f}", "Índice H": "{:.0f}"}, na_rep="—"))
    ev = st.dataframe(estilo, hide_index=True, width="stretch", height=460, on_select="rerun",
                      selection_mode="single-row", key=clave,
                      column_config={
                          "Revista": st.column_config.TextColumn(width="large"),
                          "Instrucciones": st.column_config.LinkColumn(
                              "Instrucciones", display_text="Ver ↗", width="small",
                              help="Instrucciones para autores de la revista"),
                          "Áreas": st.column_config.TextColumn(width="medium")})
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


def encabezado(titulo: str, subtitulo: str = ""):
    st.markdown(f'<div class="encab"><h2>{titulo}</h2>'
                f'{f"<p>{subtitulo}</p>" if subtitulo else ""}</div>', unsafe_allow_html=True)


COLOR_Q = {"Q1": "#104281", "Q2": "#256abf", "Q3": "#5598e7", "Q4": "#86b6ef"}


def grafico_carreras(face: pd.DataFrame):
    import altair as alt
    filas = []
    for c in CARRERAS:
        sub = face[face["carreras"].str.contains(c, regex=False)]
        for q in ["Q1", "Q2", "Q3", "Q4"]:
            filas.append({"Área": f"{CARRERAS[c]['icono']} {c}", "Cuartil": q,
                          "Revistas": int((sub["cuartil_sjr"] == q).sum())})
    d = pd.DataFrame(filas)
    orden = list(dict.fromkeys(d["Área"]))
    graf = (alt.Chart(d).mark_bar(cornerRadiusEnd=4, stroke="#ffffff", strokeWidth=2)
            .encode(y=alt.Y("Área:N", sort=orden, title=None, scale=alt.Scale(paddingInner=0.35),
                           axis=alt.Axis(labelLimit=320, labelFontSize=12)),
                    x=alt.X("sum(Revistas):Q", title="Revistas", axis=alt.Axis(grid=True, gridColor="#eef2f7")),
                    color=alt.Color("Cuartil:N", scale=alt.Scale(domain=list(COLOR_Q), range=list(COLOR_Q.values())),
                                    legend=alt.Legend(orient="top", title=None)),
                    order=alt.Order("Cuartil:N", sort="ascending"),
                    tooltip=["Área", "Cuartil", alt.Tooltip("Revistas:Q", format=",")])
            .properties(height=330).configure_view(stroke=None).configure_axis(domainColor="#cbd5e1", labelFontSize=12))
    st.altair_chart(graf, use_container_width=True)


def grafico_paises(sub: pd.DataFrame):
    import altair as alt
    d = sub["pais"].fillna("Sin dato").value_counts().head(8).rename_axis("País").reset_index(name="Revistas")
    base = alt.Chart(d).encode(y=alt.Y("País:N", sort="-x", title=None, axis=alt.Axis(labelLimit=200)),
                               x=alt.X("Revistas:Q", title=None, axis=None),
                               tooltip=["País", alt.Tooltip("Revistas:Q", format=",")])
    graf = (base.mark_bar(cornerRadiusEnd=4, height=18, color="#256abf")
            + base.mark_text(align="left", dx=4, color="#334155").encode(text="Revistas:Q"))
    st.altair_chart(graf.properties(height=250).configure_view(stroke=None), use_container_width=True)


GLOSARIO = """
- **Cuartil (Q1 a Q4):** posición de la revista dentro de su área según su impacto. Q1 es el 25 % superior.
- **SJR:** indicador de impacto de Scopus (Scimago). Mientras más alto, más citada e influyente es la revista.
- **Índice H:** la revista tiene H artículos con al menos H citas cada uno.
- **APC:** cobro que algunas revistas de acceso abierto piden a los autores por publicar.
- **Scopus y Web of Science (WoS):** las dos grandes bases de revistas indexadas que se usan en concursos y acreditación.
- **Acceso abierto:** cualquiera puede leer los artículos gratis.
- **Convocatoria o número especial:** la revista recibe artículos sobre un tema hasta una fecha límite.
"""


def _temas(area: str | None) -> pd.DataFrame:
    try:
        t = pd.read_sql("SELECT area, tema, n, n_prev FROM temas", con)
    except Exception:
        return pd.DataFrame()
    if t.empty:
        return t
    if area:
        t = t[t["area"] == area]
    t = t.groupby("tema", as_index=False)[["n", "n_prev"]].sum().sort_values("n", ascending=False)
    return t.head(10)


def bloque_temas(sel: str | None, sub: pd.DataFrame):
    st.markdown(f"**🔥 Temas sobre los que más se está publicando{' en ' + sel if sel else ''}**")
    t = _temas(sel)
    if t.empty:
        # Mientras no haya datos de OpenAlex: especialidades con más revistas en el área
        cats = pd.Series([c.strip() for x in sub["categorias"].dropna() for c, _ in categorias(x)]).value_counts().head(8)
        st.caption("Los temas de los artículos publicados en el último año se calculan en la próxima actualización "
                   "automática. Mientras tanto, estas son las especialidades con más revistas:")
        maximo = cats.max() if len(cats) else 1
        st.markdown("".join(f'<div class="tema"><span class="nom">{html.escape(c)}</span><span class="bar">'
                            f'<i style="width:{100 * n / maximo:.0f}%"></i></span><span class="num">{_n(n)} revistas</span></div>'
                            for c, n in cats.items()), unsafe_allow_html=True)
        return
    st.caption("Artículos publicados en los últimos 12 meses en las revistas del área (fuente: OpenAlex). "
               "Toque un tema para ver qué revistas le convienen.")
    maximo = t["n"].max()
    filas = []
    for r in t.itertuples():
        crec = (r.n - r.n_prev) / r.n_prev * 100 if r.n_prev else None
        if crec is None:
            flecha = '<span class="badge b-green">nuevo</span>'
        elif crec >= 10:
            flecha = f'<span class="badge b-green">▲ {crec:.0f}%</span>'
        elif crec <= -10:
            flecha = f'<span class="badge b-gray">▼ {abs(crec):.0f}%</span>'
        else:
            flecha = '<span class="badge b-gray">estable</span>'
        filas.append(f'<div class="tema"><span class="nom">{html.escape(r.tema)}</span><span class="bar">'
                     f'<i style="width:{100 * r.n / maximo:.0f}%"></i></span><span class="num">{_n(r.n)} artículos</span>'
                     f'{flecha}</div>')
    st.markdown("".join(filas), unsafe_allow_html=True)
    elegido = st.pills("👉 Ver revistas recomendadas para:", t["tema"].head(6).tolist(), key="tema_click")
    if elegido:
        st.session_state.pedido_inicio = elegido
        st.session_state.pop("tema_click", None)
        st.switch_page(PAG["asistente"])


def pagina_inicio():
    face = DF[DF["carreras"] != ""]
    st.markdown("""<div class="hero"><h1>👋 ¡Hola! ¿Dónde publicará su próximo artículo?</h1>
<p>Revistas Scopus y Web of Science para las áreas de la FACE · Universidad del Bío-Bío.</p></div>""",
                unsafe_allow_html=True)

    # Tres acciones principales
    acciones = [("🤖", "Recomiéndame revistas", "Escriba el tema de su artículo y le muestro las 5 mejores opciones.", "asistente"),
                ("🔎", "Explorar revistas", "Filtre por área, cuartil, cobro o indexación.", "buscar"),
                ("📬", "Convocatorias abiertas", "Revistas que reciben artículos sobre un tema hasta una fecha.", "convocatorias")]
    cols = st.columns(3)
    for col, (ic, tit, desc, destino) in zip(cols, acciones):
        with col.container(border=True):
            st.markdown(f'<div class="accion"><span class="ic">{ic}</span><b>{tit}</b><p>{desc}</p></div>',
                        unsafe_allow_html=True)
            if st.button("Ir →", key=f"acc_{destino}", width="stretch", type="primary" if destino == "asistente" else "secondary"):
                st.switch_page(PAG[destino])

    with st.container(border=True):
        c1, c2 = st.columns([5, 1])
        tema = c1.text_input("Tema", placeholder="✍️  Escriba aquí el tema de su artículo, por ejemplo: inteligencia artificial en la auditoría",
                             label_visibility="collapsed", key="tema_inicio")
        if c2.button("Recomiéndame →", type="primary", width="stretch") and tema.strip():
            st.session_state.pedido_inicio = tema.strip()
            st.switch_page(PAG["asistente"])

    sel = st.pills("Elija su área para personalizar el panel", list(CARRERAS), selection_mode="single",
                   key="inicio_carrera", format_func=lambda c: f"{CARRERAS[c]['icono']} {c}")
    sub = face[face["carreras"].str.contains(sel, regex=False)] if sel else face
    apc = pd.to_numeric(sub["apc_usd"], errors="coerce")
    sin_cobro = int((((sub["acceso_abierto"] == "Yes") & (apc.isna() | (apc == 0)))).sum())
    abiertas = sub[sub["recepcion_txt"].isin(["Convocatoria abierta", "Número especial abierto"])]
    tiles = [("📚", "Revistas", _n(len(sub)), "en Scopus y WoS"),
             ("🥇", "De primer nivel (Q1)", _n((sub["cuartil_sjr"] == "Q1").sum()),
              f"{_n(100 * (sub['cuartil_sjr'] == 'Q1').mean())} % del total"),
             ("📈", "Q1 o Q2", _n(sub["cuartil_sjr"].isin(["Q1", "Q2"]).sum()), "mitad superior de su área"),
             ("🆓", "Publicar gratis", _n(sin_cobro), "acceso abierto sin cobro"),
             ("📬", "Convocatorias", _n(len(abiertas)), "abiertas ahora")]
    st.markdown('<div class="kpis">' + "".join(
        f'<div class="kpi"><span>{ic} {k}</span><b>{v}</b><small>{d}</small></div>' for ic, k, v, d in tiles) + "</div>",
        unsafe_allow_html=True)

    a, b = st.columns([3, 2], gap="large")
    with a:
        with st.container(border=True):
            bloque_temas(sel, sub)
    with b:
        with st.container(border=True):
            st.markdown("**⏳ Próximos cierres de convocatoria**")
            prox = abiertas.assign(_d=abiertas["fecha_limite"].map(dias_restantes)).sort_values("_d").head(4)
            if prox.empty:
                st.caption("No hay convocatorias abiertas detectadas. La mayoría recibe artículos todo el año.")
            for _, r in prox.iterrows():
                st.markdown(f'<div class="mini"><div class="dias"><b>{r["_d"]}</b><span>días</span></div>'
                            f'<div><b>{e(r["titulo"])}</b><div class="muted">{badge_q(r.get("cuartil_sjr"))} '
                            f'{html.escape(r["periodo_txt"])}</div></div></div>', unsafe_allow_html=True)

    a, b = st.columns([3, 2], gap="large")
    with a:
        with st.container(border=True):
            st.markdown(f"**🏆 Revistas Q1 con mayor impacto{' en ' + sel if sel else ''}**")
            top = sub[sub["cuartil_sjr"] == "Q1"].sort_values("sjr", ascending=False).head(6)
            for i, (_, r) in enumerate(top.iterrows(), 1):
                st.markdown(f'<div class="fila-top"><span class="pos">{i}</span><span class="nom">{e(r["titulo"])}'
                            f'<small>{e(r.get("pais"))} · SJR {_n(r.get("sjr"), 2)}</small></span>'
                            f'<a href="{html.escape(r["url_instr"])}" target="_blank">Instrucciones ↗</a></div>',
                            unsafe_allow_html=True)
    with b:
        with st.container(border=True):
            st.markdown("**📊 Revistas por área y cuartil**")
            grafico_carreras(face)

    with st.expander("📖 ¿Qué significa cada término?"):
        st.markdown(GLOSARIO)
    st.caption(f"Datos de Scimago (Scopus), Clarivate, OpenAlex y DOAJ · Actualizado el "
               f"{(db.meta(con, 'ultima_actualizacion') or '—')[:10]} · Se actualiza solo cada lunes.")


def pagina_buscar():
    df = DF
    encabezado("🔎 Buscar revistas", "Filtre por área, cuartil o indexación. Haga clic en una revista para ver su ficha.")
    st.markdown("##### ¿En qué área busca revista?")
    nombres = list(CARRERAS)
    sel = st.pills("Área", nombres, selection_mode="multi", label_visibility="collapsed",
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
        solo_cont = g4.toggle("Solo con convocatoria abierta ahora")
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
        sub = sub[sub["recepcion_txt"].isin(["Convocatoria abierta", "Número especial abierto"])]
    sub = sub.sort_values("sjr", ascending=False, na_position="last").reset_index(drop=True)
    st.markdown(f"**{_n(len(sub))} revistas** · " + " · ".join(
        f"{q}: {_n((sub['cuartil_sjr'] == q).sum())}" for q in ["Q1", "Q2", "Q3", "Q4"]))
    tabla(sub, "busqueda")
    explicacion_datos()


EXPLICACION = """
**¿Por qué algunas revistas no muestran la extensión máxima o el periodo de recepción?**

No es un problema de acceso de la universidad. Los cuartiles, indicadores y APC vienen de bases
abiertas (Scimago, OpenAlex, DOAJ) y están para todas las revistas. En cambio, la **extensión máxima** y
las **fechas de recepción** solo aparecen escritas en la página de instrucciones de cada revista, y:

- Las **grandes editoriales** (Elsevier, Wiley, Taylor & Francis, SAGE, Oxford, Emerald, IEEE…) bloquean
  a propósito a los programas que leen sus páginas. Lo probamos incluso con un navegador automático y
  también lo bloquean. En esas revistas el programa le deja el **enlace directo** a sus instrucciones.
- Muchas revistas no publican un límite de palabras, o lo dan solo en la plantilla descargable.
- Casi todas las revistas indexadas **reciben artículos todo el año**. Cuando no encontramos una fecha
  publicada se indica *Continua (habitual)*, en gris, para que lo confirme en el enlace.

**Cómo se completa:** el programa vuelve a leer los sitios cada lunes, y quien administra la página puede
corregir o completar las exigencias de cualquier revista desde su ficha (✏️). Esos datos quedan
marcados como *ingresados por la FACE* y no se sobrescriben.
"""


def explicacion_datos():
    with st.expander("ℹ️ ¿De dónde salen los datos y por qué algunos faltan?"):
        st.markdown(EXPLICACION)


EJEMPLOS = ['fintech AND ("inclusión financiera" OR microfinanzas) NOT bancos',
            "Divulgación ESG y desempeño financiero en empresas chilenas",
            "Machine learning para detectar fraude contable",
            "Teletrabajo y derecho laboral en América Latina",
            "Fintech e inclusión financiera de pymes"]


@st.cache_data(show_spinner=False, ttl=86400)
def _afinidad(texto: str) -> dict | None:
    try:
        return recomendador.afinidad_openalex(texto, cfg.get("openalex_email", ""))
    except Exception:
        return None


def tarjeta_recomendada(i: int, r, info: dict, clave: str):
    pct = int(round(info["puntaje"] * 100))
    badges = [badge_q(r.get("cuartil_sjr"))]
    if r.get("scopus") == 1:
        badges.append('<span class="badge b-blue">Scopus</span>')
    if r.get("wos") == 1:
        badges.append('<span class="badge b-violet">WoS</span>')
    if r.get("acceso_abierto") == "Yes":
        badges.append('<span class="badge b-green">🔓 Acceso abierto</span>')
    badges.append(badge_recepcion(r))
    lista = "".join(f"<li>{html.escape(x)}</li>" for x in info["razones"])
    ext = extension(r)
    ext = f" · Extensión máx.: {html.escape(ext)}" if ext else ""
    st.markdown(f"""<div class="card"><div class="rec"><div class="num">{i}</div><div class="cuerpo">
<div class="tit">{e(r['titulo'])}</div>
<div class="muted">{e(r.get('editorial'))} · {e(r.get('pais'))} · SJR {_n(r.get('sjr'), 2)}{ext}</div>
<div class="badges">{''.join(badges)}</div>
<div class="barra"><div style="width:{pct}%"></div></div><div class="muted">Afinidad con su tema: <b>{pct}%</b></div>
<ul>{lista}</ul>
<div class="acciones"><a href="{html.escape(r['url_instr'])}" target="_blank">📄 Instrucciones para autores ↗</a></div>
</div></div></div>""", unsafe_allow_html=True)
    if st.button("Ver ficha completa", key=f"{clave}_{r['rid']}"):
        st.session_state.ficha_rid = r["rid"]


def pagina_asistente():
    encabezado("🤖 Recomiéndame revistas", "Cuénteme de qué trata su artículo (tema, objetivo o palabras clave, "
               "en español o inglés) y le muestro las 5 revistas más adecuadas.")
    with st.container(border=True):
        carreras = st.pills("Área (opcional)", list(CARRERAS), selection_mode="multi", key="as_carr",
                            format_func=lambda c: f"{CARRERAS[c]['icono']} {c}")
        c2, c3 = st.columns(2)
        nivel = c2.segmented_control("Cuartil", ["Cualquiera", "Q1–Q2", "Solo Q1"], default="Cualquiera", key="as_q")
        base = c3.segmented_control("Indexación", ["Todas", "Scopus", "WoS", "Ambas"], default="Todas", key="as_b")
        d1, d2, d3 = st.columns(3)
        sin_apc = d1.toggle("Sin cobro por publicar", key="as_apc")
        solo_oa = d2.toggle("Solo acceso abierto", key="as_oa")
        abierta = d3.toggle("Solo con convocatoria abierta", key="as_conv")

    sub = DF[DF["carreras"] != ""]
    if carreras:
        sub = sub[sub["carreras"].map(lambda x: any(c in x for c in carreras))]
    if nivel == "Q1–Q2":
        sub = sub[sub["cuartil_sjr"].isin(["Q1", "Q2"])]
    elif nivel == "Solo Q1":
        sub = sub[sub["cuartil_sjr"] == "Q1"]
    if base == "Scopus":
        sub = sub[sub["scopus"] == 1]
    elif base == "WoS":
        sub = sub[sub["wos"] == 1]
    elif base == "Ambas":
        sub = sub[(sub["scopus"] == 1) & (sub["wos"] == 1)]
    if sin_apc:
        sub = sub[pd.to_numeric(sub["apc_usd"], errors="coerce").fillna(0) == 0]
    if solo_oa:
        sub = sub[sub["acceso_abierto"] == "Yes"]
    if abierta:
        sub = sub[sub["recepcion_txt"].isin(["Convocatoria abierta", "Número especial abierto"])]

    chat = st.session_state.setdefault("chat", [])
    if not chat:
        with st.chat_message("assistant", avatar="🤖"):
            st.markdown("¡Hola! ¿Sobre qué es su artículo? Escríbalo con sus palabras o como búsqueda booleana "
                        "(AND, OR, NOT, comillas, `*`). Puede probar con uno de estos ejemplos:")
            ej = st.pills("Ejemplos", EJEMPLOS, label_visibility="collapsed", key="as_ej")
    else:
        ej = None
    for n, m in enumerate(chat):
        with st.chat_message(m["rol"], avatar="🤖" if m["rol"] == "assistant" else "🧑‍🏫"):
            st.markdown(m["texto"])
            if m.get("consulta"):
                with st.expander("🔎 Búsqueda booleana para Scopus y Web of Science (con truncado *)"):
                    st.caption("Así interpreté su tema, con sinónimos en español e inglés. Cópiela y péguela en "
                               "la búsqueda avanzada de Scopus o WoS para ver los artículos publicados.")
                    for base_, cadena in m["consulta"].items():
                        st.markdown(f"**{base_}**")
                        st.code(cadena, language=None, wrap_lines=True)
            for i, info in enumerate(m.get("top", []), 1):
                filas = DF[DF["rid"] == info["rid"]]
                if not filas.empty:
                    tarjeta_recomendada(i, filas.iloc[0], info, f"rec{n}")

    pedido = (st.chat_input('Describa su tema. También acepta AND, OR, NOT, comillas y truncado: audit* AND "inteligencia artificial"') or ej
              or st.session_state.pop("pedido_inicio", None))
    if pedido:
        chat.append({"rol": "user", "texto": pedido})
        with st.spinner("Buscando revistas que publican sobre su tema…"):
            top, metodo = recomendador.recomendar(sub, pedido, conteo=_afinidad(pedido) or {})
        if top.empty:
            texto = ("No encontré revistas para ese tema con los filtros elegidos. Pruebe con otras palabras "
                     "clave (idealmente en inglés) o quite algún filtro.")
        else:
            texto = (f"Estas son las {len(top)} revistas que le recomiendo para **{pedido}**"
                     + (", según los artículos publicados sobre el tema en los últimos 5 años."
                        if metodo == "openalex" else
                        ", según las áreas en que publica cada revista, su título y su cuartil."))
        chat.append({"rol": "assistant", "texto": texto, "consulta": recomendador.consulta_booleana(pedido),
                     "top": [{"rid": r["rid"], "puntaje": r["puntaje"], "razones": r["razones"]}
                             for _, r in top.iterrows()]})
        st.session_state.pop("as_ej", None)
        st.rerun()

    if chat:
        if st.button("🧹 Nueva conversación"):
            st.session_state.chat = []
            st.session_state.pop("ficha_rid", None)
            st.rerun()
    rid = st.session_state.get("ficha_rid")
    if rid and not DF[DF["rid"] == rid].empty:
        st.divider()
        ficha(DF[DF["rid"] == rid].iloc[0])


def pagina_convocatorias():
    encabezado("📬 Convocatorias abiertas", "Revistas con una convocatoria o número especial que recibe "
               "artículos ahora, ordenadas por fecha de cierre.")
    sub = DF[(DF["carreras"] != "") & DF["recepcion_txt"].isin(["Convocatoria abierta", "Número especial abierto"])].copy()
    if sub.empty:
        st.info("No se detectaron convocatorias abiertas en esta actualización. La mayoría de las revistas "
                "recibe artículos todo el año.")
    else:
        sub["_dias"] = sub["fecha_limite"].map(dias_restantes)
        sub = sub.sort_values("_dias").reset_index(drop=True)
        cols = st.columns(3)
        for i, r in sub.iterrows():
            d = r["_dias"]
            urg = "b-red" if d is not None and d <= 14 else ("b-amber" if d is not None and d <= 45 else "b-green")
            enlace = r.get("exi_url") if isinstance(r.get("exi_url"), str) else r.get("web")
            link = (f'<a href="{html.escape(enlace)}" target="_blank">Ver convocatoria ↗</a>'
                    if isinstance(enlace, str) and enlace.startswith("http") else "")
            cols[i % 3].markdown(f"""<div class="card conv"><div class="badges" style="margin:0 0 8px 0">
{badge_q(r.get('cuartil_sjr'))}<span class="badge {urg}">⏳ {d} días</span>
<span class="badge b-gray">{html.escape(r['recepcion_txt'])}</span></div>
<b class="tit">{e(r['titulo'])}</b><div class="muted">{e(r.get('pais'))} · {e(r.get('editorial'))}</div>
<div class="periodo" style="margin-top:8px">🗓️ {html.escape(r['periodo_txt'])}</div>
<div class="muted" style="margin-top:6px">{link}</div></div>""", unsafe_allow_html=True)
        st.markdown("&nbsp;")
        st.markdown("**Ver ficha completa**")
        tabla(sub.drop(columns="_dias"), "convocatorias")
    explicacion_datos()


def pagina_seguidas():
    encabezado("⭐ En seguimiento", "Revistas que la FACE sigue de cerca. Avisamos cuando cambian de cuartil, indexación o cobro.")
    sub = DF[DF["seguida"]].reset_index(drop=True)
    if sub.empty:
        st.info("Aún no hay revistas en seguimiento." +
                (" Búsquelas y pulse **⭐ Seguir esta revista** en su ficha." if ADMIN else ""))
    else:
        tabla(sub, "seguidas")


def pagina_alertas():
    encabezado("🔔 Alertas", "Cambios detectados en cada actualización semanal.")
    al = pd.read_sql("SELECT id, fecha, titulo, tipo, detalle, leida FROM alertas ORDER BY id DESC", con)
    if al.empty:
        st.info("Sin alertas por ahora. Aparecen cuando una revista en seguimiento cambia de cuartil, "
                "indexación o APC, o cuando entra una revista nueva en las áreas de la FACE.")
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
        "Áreas para las que se generan alertas de revistas nuevas", list(CARRERAS),
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
    hero("👋 Monitor de Revistas FACE", "Revistas Scopus y Web of Science para las áreas de la FACE, "
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
PAG = {}
for _k in ("inicio_carrera", "carreras_sel", "as_carr"):  # selecciones con nombres de versiones anteriores
    _v = st.session_state.get(_k)
    if _v and any(x not in CARRERAS for x in ([_v] if isinstance(_v, str) else _v)):
        del st.session_state[_k]

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
    PAG.update(
        inicio=st.Page(pagina_inicio, title="Inicio", icon="🏠", default=True),
        asistente=st.Page(pagina_asistente, title="Recomiéndame revistas", icon="🤖", url_path="asistente"),
        buscar=st.Page(pagina_buscar, title="Buscar revistas", icon="🔎", url_path="buscar"),
        convocatorias=st.Page(pagina_convocatorias, title="Convocatorias", icon="📬", url_path="convocatorias"),
        seguidas=st.Page(pagina_seguidas, title="En seguimiento", icon="⭐", url_path="seguimiento"),
        alertas=st.Page(pagina_alertas, title="Alertas", icon="🔔", url_path="alertas"))
    paginas = list(PAG.values())
    if ADMIN:
        paginas += [st.Page(pagina_actualizar, title="Actualizar datos", icon="⚙️"),
                    st.Page(pagina_config, title="Configuración", icon="🛠️")]
st.navigation(paginas, position="top").run()
st.markdown('<div class="autoria">Monitor de Revistas FACE · Universidad del Bío-Bío · Realizado por '
            '<b>Darling Leandra Salazar Pincheira</b></div>', unsafe_allow_html=True)
