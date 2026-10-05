"""Rutas del proyecto y configuración editable (datos/config.json)."""
import json
import os
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATOS = Path(os.environ.get("MONITOR_DATOS", BASE / "datos"))
FUENTES = DATOS / "fuentes"
DB_PATH = DATOS / "revistas.db"
CONFIG_PATH = DATOS / "config.json"
INCENTIVOS_PATH = DATOS / "incentivos.csv"

# Áreas ASJC (Scimago/Scopus) más relevantes para una Facultad de Ciencias
# Económicas y Administrativas.
AREAS_FACE = [
    "Business, Management and Accounting",
    "Economics, Econometrics and Finance",
    "Decision Sciences",
    "Social Sciences",
]

# Carreras de la FACE (UBB) y las áreas/categorías Scimago (ASJC) que les corresponden.
# "areas": cualquier categoría dentro de esas áreas; "categorias": categorías puntuales.
# Áreas de la FACE: departamentos (https://face.ubiobio.cl/departamentos/) más Tributaria y Derecho.
# (El nombre CARRERAS se mantiene en el código por compatibilidad.) "titulo": la revista además
# debe nombrar el tema en su título, para áreas sin categoría propia en Scopus.
CARRERAS = {
    "Economía y Finanzas": {
        "icono": "💹", "areas": ["Economics, Econometrics and Finance"],
        "categorias": ["Finance", "Economics and Econometrics", "Development"]},
    "Administración y Auditoría": {
        "icono": "🧾", "areas": [],
        "categorias": ["Accounting", "Business, Management and Accounting (miscellaneous)",
                       "Public Administration", "Strategy and Management"]},
    "Gestión Empresarial": {
        "icono": "📈", "areas": ["Decision Sciences"],
        "categorias": ["Strategy and Management", "Business and International Management", "Marketing",
                       "Organizational Behavior and Human Resource Management",
                       "Management of Technology and Innovation", "Tourism, Leisure and Hospitality Management",
                       "Industrial Relations", "Management Science and Operations Research",
                       "Business, Management and Accounting (miscellaneous)"]},
    "Sistemas de Información": {
        "icono": "🗄️", "areas": [],
        "categorias": ["Information Systems", "Information Systems and Management", "Management Information Systems",
                       "Computer Science Applications", "Human-Computer Interaction", "Library and Information Sciences"]},
    "Ciencias de la Computación y TI": {
        "icono": "💻", "areas": ["Computer Science"], "categorias": []},
    "Tributaria": {
        "icono": "🏛️", "areas": [],
        "categorias": ["Accounting", "Finance", "Law", "Public Administration", "Economics and Econometrics",
                       "Economics, Econometrics and Finance (miscellaneous)",
                       "Business, Management and Accounting (miscellaneous)"],
        "titulo": r"\btax|\btribut|fiscal|\bfisc|impuest|public financ|public budget|hacienda|revenue"},
    "Derecho": {
        "icono": "⚖️", "areas": [],
        "categorias": ["Law", "Political Science and International Relations"]},
}

DEFAULT = {
    "carreras_interes": list(CARRERAS),
    "areas_interes": AREAS_FACE[:3],
    "alertar_nuevas_en_areas": True,
    "openalex_email": "",
    "openalex_api_key": "",
    "elsevier_api_key": "",
    "email_activo": False,
    "smtp_host": "smtp.gmail.com",
    "smtp_puerto": 587,
    "smtp_tls": True,
    "smtp_usuario": "",
    "smtp_password": "",
    "remitente": "",
    "destinatarios": [],
}


# Variables de entorno (secretos de GitHub en la versión web) que reemplazan la configuración
ENTORNO = {
    "MONITOR_SMTP_HOST": "smtp_host", "MONITOR_SMTP_PUERTO": "smtp_puerto",
    "MONITOR_SMTP_USUARIO": "smtp_usuario", "MONITOR_SMTP_PASSWORD": "smtp_password",
    "MONITOR_OPENALEX_EMAIL": "openalex_email", "MONITOR_ELSEVIER_API_KEY": "elsevier_api_key",
}


def cargar() -> dict:
    cfg = dict(DEFAULT)
    if CONFIG_PATH.exists():
        try:
            cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            pass
    for var, clave in ENTORNO.items():
        if os.environ.get(var):
            cfg[clave] = os.environ[var]
    if os.environ.get("MONITOR_DESTINATARIOS"):
        cfg["destinatarios"] = [d.strip() for d in os.environ["MONITOR_DESTINATARIOS"].split(",") if d.strip()]
    if os.environ.get("MONITOR_SMTP_PASSWORD"):
        cfg["email_activo"] = True
    return cfg


def guardar(cfg: dict) -> None:
    DATOS.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
