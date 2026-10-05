"""Base de datos local SQLite (datos/revistas.db)."""
import sqlite3
from datetime import datetime

import pandas as pd

from .config import DATOS, DB_PATH

ESQUEMA = """
CREATE TABLE IF NOT EXISTS revistas (rid TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS enriq (
    rid TEXT PRIMARY KEY, openalex_id TEXT, oa_trabajos INTEGER, oa_citas INTEGER,
    oa_citas_media_2y REAL, oa_h_index INTEGER, oa_i10 INTEGER, es_oa INTEGER,
    en_doaj INTEGER, apc_usd REAL, web TEXT, prod_anual TEXT,
    doaj_revision TEXT, doaj_plagio TEXT, doaj_semanas INTEGER, doaj_licencia TEXT,
    doaj_apc TEXT, doaj_otros_cargos TEXT, doaj_exoneracion TEXT,
    doaj_instrucciones TEXT, doaj_alcance TEXT, doaj_idiomas TEXT,
    doaj_derechos_autor TEXT, citescore REAL, oa_temas TEXT, fecha TEXT);
CREATE TABLE IF NOT EXISTS historial (
    rid TEXT, anio INTEGER, sjr REAL, cuartil_sjr TEXT, h_index REAL,
    docs_anio REAL, PRIMARY KEY (rid, anio));
CREATE TABLE IF NOT EXISTS seguimiento (rid TEXT PRIMARY KEY, fecha TEXT);
CREATE TABLE IF NOT EXISTS notas (rid TEXT PRIMARY KEY, texto TEXT, fecha TEXT);
CREATE TABLE IF NOT EXISTS alertas (
    id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, rid TEXT, titulo TEXT,
    tipo TEXT, detalle TEXT, leida INTEGER DEFAULT 0, enviada INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS exigencias (
    rid TEXT PRIMARY KEY, palabras_max INTEGER, caracteres_max INTEGER, paginas_max INTEGER,
    resumen_max INTEGER, recepcion TEXT, fecha_inicio TEXT, fecha_limite TEXT, evidencia TEXT, url TEXT,
    fecha TEXT, manual INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS temas (area TEXT, tema TEXT, n INTEGER, n_prev INTEGER, fecha TEXT);
CREATE TABLE IF NOT EXISTS ubb_articulos (id TEXT PRIMARY KEY, titulo TEXT, anio INTEGER, fuente TEXT,
    doi TEXT, autores TEXT, fecha TEXT);
CREATE TABLE IF NOT EXISTS meta (clave TEXT PRIMARY KEY, valor TEXT);
"""


NUEVAS_COLUMNAS = [("exigencias", "fecha_inicio"), ("enriq", "oa_temas")]


def conectar() -> sqlite3.Connection:
    DATOS.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.executescript(ESQUEMA)
    for tabla, col in NUEVAS_COLUMNAS:  # bases creadas con versiones anteriores
        if col not in {c[1] for c in con.execute(f"PRAGMA table_info({tabla})")}:
            con.execute(f"ALTER TABLE {tabla} ADD COLUMN {col} TEXT")
    return con


def ahora() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def meta(con, clave, valor=None):
    if valor is None:
        fila = con.execute("SELECT valor FROM meta WHERE clave=?", (clave,)).fetchone()
        return fila[0] if fila else None
    con.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (clave, str(valor)))
    con.commit()


def tabla(con, nombre) -> pd.DataFrame:
    return pd.read_sql(f"SELECT * FROM {nombre}", con)


def seguimiento(con) -> set[str]:
    return {r[0] for r in con.execute("SELECT rid FROM seguimiento")}


def seguir(con, rid, activo=True):
    if activo:
        con.execute("INSERT OR IGNORE INTO seguimiento VALUES (?,?)", (rid, ahora()))
    else:
        con.execute("DELETE FROM seguimiento WHERE rid=?", (rid,))
    con.commit()


def nota(con, rid, texto=None):
    if texto is None:
        f = con.execute("SELECT texto FROM notas WHERE rid=?", (rid,)).fetchone()
        return f[0] if f else ""
    con.execute("INSERT OR REPLACE INTO notas VALUES (?,?,?)", (rid, texto, ahora()))
    con.commit()


def agregar_alerta(con, rid, titulo, tipo, detalle):
    con.execute("INSERT INTO alertas (fecha, rid, titulo, tipo, detalle) VALUES (?,?,?,?,?)",
                (ahora(), rid, titulo, tipo, detalle))
