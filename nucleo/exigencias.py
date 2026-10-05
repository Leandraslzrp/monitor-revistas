"""Exigencias para autores: extensión máxima (palabras, caracteres, páginas,
resumen) y modalidad de recepción (continua o por convocatoria).

No existe una fuente estructurada con estos datos, así que se leen las
instrucciones para autores publicadas en el sitio de cada revista y se buscan
patrones de texto en español, inglés y portugués. El resultado es orientativo:
la ficha muestra la página de origen y la frase encontrada para verificarla.
"""
import re
from datetime import date
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import requests

UA = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/140.0 Safari/537.36"),
      "Accept-Language": "es-CL,es;q=0.9,en;q=0.8,pt;q=0.6"}

CLAVES_ENLACE = re.compile(
    r"author|autor|guide|gu[ií]a|instruc|submission|submit|env[ií]o|normas|directrices|"
    r"diretrizes|for-authors|policies|pol[ií]tica", re.I)

NUM = r"(\d{1,3}(?:[.,\s]\d{3})+|\d{2,6})"
LIMITE = (r"(?:max(?:imum|imo|ima|\.)?|m[aá]x(?:imo|ima)?\.?|not\s+(?:to\s+)?exceed|no\s+(?:debe|deber[aá]n?)?\s*"
          r"(?:exceder|superar|sobrepasar)|n[aã]o\s+(?:deve\s+)?(?:exceder|ultrapassar)|up\s+to|no\s+more\s+than|"
          r"hasta|at[eé]|limit(?:e|ed\s+to)?|l[ií]mite|extensi[oó]n|length|extens[aã]o|between|entre)")
UNIDADES = {
    "palabras": r"(?:words?|palabras|palavras)",
    "caracteres": r"(?:characters?|caracteres|car[aá]cteres)",
    "paginas": r"(?:pages?|p[aá]ginas|cuartillas|laudas)",
}
RESUMEN = re.compile(r"abstract|resumen|resumo|summary", re.I)

CONTINUA = re.compile(
    r"continuous(?:ly)?\s+(?:basis|submissions?|publication|flow)|rolling\s+basis|"
    r"(?:accept|receive)s?\s+(?:manuscripts|submissions|papers|articles)\s+(?:at\s+any\s+time|all\s+year|"
    r"throughout\s+the\s+year|continuously|on\s+a\s+continuous)|throughout\s+the\s+year|year[-\s]round|"
    r"flujo\s+continuo|recepci[oó]n\s+(?:continua|permanente|abierta\s+todo)|todo\s+el\s+a[nñ]o|"
    r"en\s+cualquier\s+momento|de\s+forma\s+(?:continua|permanente)|publicaci[oó]n\s+continua|"
    r"modalidad\s+continua|fluxo\s+cont[ií]nuo|em\s+fluxo\s+cont[ií]nuo|a\s+qualquer\s+momento|"
    r"publica[cç][aã]o\s+cont[ií]nua", re.I)
CONVOCATORIA = re.compile(
    r"call\s+for\s+(?:papers|submissions|articles)|convocatoria|chamada\s+(?:de|para)\s+(?:artigos|trabalhos)|"
    r"deadline|fecha\s+l[ií]mite|plazo\s+de\s+(?:recepci[oó]n|env[ií]o)|cierre\s+de\s+(?:la\s+)?recepci[oó]n|"
    r"prazo\s+(?:de|para)\s+(?:submiss[aã]o|envio)", re.I)

ESPECIAL = re.compile(r"special\s+(?:issue|section)|n[uú]mero\s+(?:especial|monogr[aá]fico)|monogr[aá]fico|"
                      r"dossi[eê]r|edi[cç][aã]o\s+especial|thematic\s+issue", re.I)

# Editoriales que bloquean la lectura automática: no se intenta leerlas, pero se arma
# el enlace directo a sus instrucciones para autores para que el académico lo abra.
BLOQUEADOS = ("elsevier.com", "sciencedirect.com", "wiley.com", "tandfonline.com", "sagepub.com",
              "oup.com", "ieee.org", "springer.com", "emeraldinsight.com", "emerald.com", "informs.org",
              "uchicago.edu", "annualreviews.org", "nowpublishers.com", "mitpressjournals.org",
              "acm.org", "cambridge.org", "jstor.org", "degruyter.com", "routledge.com")
GENERICOS = ("authorservices.", "/authors/", "author-services")


def enlace_guia(web: str | None) -> str | None:
    """Enlace probable a las instrucciones para autores según la editorial."""
    if not isinstance(web, str) or not web:
        return None
    u = web.strip().rstrip("/")
    m = re.search(r"journals\.elsevier\.com/([^/?#]+)", u)
    if m:
        return f"https://www.sciencedirect.com/journal/{m.group(1)}/publish/guide-for-authors"
    m = re.search(r"sciencedirect\.com/journal/([^/?#]+)", u)
    if m:
        return f"https://www.sciencedirect.com/journal/{m.group(1)}/publish/guide-for-authors"
    m = re.search(r"onlinelibrary\.wiley\.com/journal/(?:10\.\d+/\(ISSN\))?(\d{4}-?\d{3}[\dXx])", u)
    if m:
        return f"https://onlinelibrary.wiley.com/page/journal/{m.group(1)}/homepage/forauthors.html"
    m = re.search(r"tandfonline\.com/(?:toc|journals|loi)/([a-z0-9]+)", u, re.I)
    if m:
        return f"https://www.tandfonline.com/action/authorSubmission?show=instructions&journalCode={m.group(1)}"
    m = re.search(r"link\.springer\.com/journal/(\d+)", u) or re.search(r"springer\.com/(\d{3,6})$", u)
    if m:
        return f"https://link.springer.com/journal/{m.group(1)}/submission-guidelines"
    m = re.search(r"journals\.sagepub\.com/home/([a-z0-9]+)", u, re.I)
    if m:
        return f"https://journals.sagepub.com/author-instructions/{m.group(1).upper()}"
    m = re.search(r"academic\.oup\.com/([a-z0-9]+)$", u, re.I)
    if m:
        return f"https://academic.oup.com/{m.group(1)}/pages/General_Instructions"
    m = re.search(r"mdpi\.com/journal/([a-z0-9-]+)", u, re.I)
    if m:
        return f"https://www.mdpi.com/journal/{m.group(1)}/instructions"
    if "index.php" in u:
        base = u.split("/issue")[0].split("/about")[0]
        return base + "/about/submissions"
    return None


def bloqueado(url: str | None) -> bool:
    return bool(url) and any(b in urlparse(url).netloc for b in BLOQUEADOS)


MESES = {m: i + 1 for i, m in enumerate(
    ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
     "septiembre", "octubre", "noviembre", "diciembre"])}
MESES.update({m: i + 1 for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"])})
MESES.update({"setiembre": 9, "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "maio": 5,
              "junho": 6, "julho": 7, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12})
FECHAS = [
    re.compile(r"(\d{1,2})\s+(?:de\s+)?([a-zç]+)\s+(?:de\s+|del\s+)?(20\d{2})", re.I),
    re.compile(r"([a-z]+)\s+(\d{1,2}),?\s+(20\d{2})", re.I),
    re.compile(r"(20\d{2})-(\d{2})-(\d{2})"),
    re.compile(r"(\d{1,2})[/.](\d{1,2})[/.](20\d{2})"),
]


# ---------------------------------------------------------------- HTML → texto
class _Lector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.texto, self.enlaces, self._omitir, self._href, self._ancla = [], [], 0, None, []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "svg"):
            self._omitir += 1
        elif tag == "a":
            self._href, self._ancla = dict(attrs).get("href"), []
        elif tag in ("p", "li", "br", "div", "h1", "h2", "h3", "h4", "tr", "section"):
            self.texto.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg"):
            self._omitir = max(0, self._omitir - 1)
        elif tag == "a" and self._href:
            self.enlaces.append((self._href, " ".join(self._ancla)))
            self._href = None

    def handle_data(self, data):
        if self._omitir:
            return
        self.texto.append(data)
        if self._href is not None:
            self._ancla.append(data.strip())


def leer_html(html: str):
    p = _Lector()
    try:
        p.feed(html)
    except Exception:
        pass
    texto = re.sub(r"[ \t\r\f\v ]+", " ", "".join(p.texto))
    return re.sub(r"\n\s*\n+", "\n", texto), p.enlaces


# ---------------------------------------------------------------- extracción
def _numero(txt: str) -> int | None:
    limpio = re.sub(r"[.,\s]", "", txt)
    return int(limpio) if limpio.isdigit() else None


def extraer(texto: str) -> dict:
    """Busca límites de extensión y modalidad de recepción en un texto."""
    res = {}
    for clave, unidad in UNIDADES.items():
        patron = re.compile(LIMITE + r"[^.\n]{0,60}?" + NUM + r"(?:\s*(?:-|–|a|to|y|and|e)\s*" + NUM + r")?"
                            r"\s*(?:\w+\s+){0,2}?" + unidad, re.I)
        principales, resumenes = [], []
        for m in patron.finditer(texto):
            valores = [_numero(g) for g in m.groups()[0:2] if g]
            valor = max(v for v in valores if v) if any(valores) else None
            if not valor:
                continue
            contexto = texto[max(0, m.start() - 80):m.start()] + m.group(0)
            frase = _frase(texto, m.start(), m.end())
            if clave == "palabras" and RESUMEN.search(contexto[-140:]) and valor <= 600:
                resumenes.append((valor, frase))
            elif ((clave == "palabras" and 1500 <= valor <= 40000)
                  or (clave == "caracteres" and 8000 <= valor <= 250000)
                  or (clave == "paginas" and 5 <= valor <= 80)):
                principales.append((valor, frase))
        if principales:
            valor, frase = max(principales)
            res[f"{clave}_max"] = valor
            res.setdefault("evidencia", frase)
        if resumenes:
            res["resumen_max"] = max(resumenes)[0]

    if CONTINUA.search(texto):
        res["recepcion"] = "Continua"
        res["evidencia_recepcion"] = _frase(texto, *CONTINUA.search(texto).span())
    else:
        # Solo se informa una convocatoria si trae fecha; las de números especiales
        # se informan aparte y solo si siguen abiertas.
        for m in CONVOCATORIA.finditer(texto):
            fecha = _fecha_cercana(texto[m.start():m.start() + 300])
            if not fecha:
                continue
            especial = bool(ESPECIAL.search(texto[max(0, m.start() - 200):m.start() + 300]))
            if especial and fecha < date.today():
                continue
            if especial:
                res["recepcion"] = "Número especial abierto"
            else:
                res["recepcion"] = "Convocatoria abierta" if fecha >= date.today() else "Convocatoria cerrada"
            res["fecha_limite"] = fecha.isoformat()
            res["evidencia_recepcion"] = _frase(texto, m.start(), m.end())
            break
    if "evidencia_recepcion" in res:
        if "evidencia" in res:
            res["evidencia"] = res["evidencia"] + " … " + res.pop("evidencia_recepcion")
        else:
            res["evidencia"] = res.pop("evidencia_recepcion")
    return res


def _frase(texto, ini, fin, margen=120):
    a = max(0, ini - margen)
    b = min(len(texto), fin + margen)
    return " ".join(texto[a:b].split())[:300]


def _fecha_cercana(txt: str):
    for i, pat in enumerate(FECHAS):
        for m in pat.finditer(txt):
            try:
                g = m.groups()
                if i == 0:
                    d, mes, a = int(g[0]), MESES.get(g[1].lower()), int(g[2])
                elif i == 1:
                    mes, d, a = MESES.get(g[0].lower()), int(g[1]), int(g[2])
                elif i == 2:
                    a, mes, d = int(g[0]), int(g[1]), int(g[2])
                else:
                    d, mes, a = int(g[0]), int(g[1]), int(g[2])
                if mes:
                    return date(a, mes, d)
            except (ValueError, TypeError):
                continue
    return None


# ---------------------------------------------------------------- búsqueda de la página
def candidatos(web: str | None, enlaces: list[tuple[str, str]]) -> list[str]:
    """URLs probables de las instrucciones para autores."""
    urls = []
    if web:
        u = web.rstrip("/")
        host = urlparse(u).netloc
        if "index.php" in u or "/ojs" in u:
            urls.append(u + "/about/submissions")
        if "link.springer.com/journal" in u:
            urls.append(u + "/submission-guidelines")
        if "sciencedirect.com/journal" in u:
            urls.append(u + "/publish/guide-for-authors")
        if "tandfonline.com/journals/" in u:
            code = u.rsplit("/", 1)[-1]
            urls.append(f"https://www.tandfonline.com/action/authorSubmission?show=instructions&journalCode={code}")
        if "mdpi.com/journal" in u:
            urls.append(u + "/instructions")
        if "emerald.com" in host:
            urls.append(u + "#author-guidelines")
    puntuados = []
    for href, ancla in enlaces:
        if not href or href.startswith(("mailto:", "javascript:", "#")) or any(g in href for g in GENERICOS):
            continue
        texto = f"{ancla} {href}"
        if CLAVES_ENLACE.search(texto):
            puntos = 3 if re.search(r"author|autor|instruc|guide|gu[ií]a|normas|diretrizes", texto, re.I) else 1
            puntuados.append((puntos, urljoin(web or "", href)))
    for _, u in sorted(puntuados, key=lambda x: -x[0]):
        if u not in urls:
            urls.append(u)
    return urls[:4]


def buscar(web: str | None, instrucciones: str | None = None,
           sesion: requests.Session | None = None, timeout: int = 15) -> dict:
    """Descarga las instrucciones para autores y extrae las exigencias."""
    s = sesion or requests.Session()
    visitadas, mejor = [], {}
    guia = enlace_guia(web)

    def probar(url):
        if not url or url in visitadas or len(visitadas) >= 5:
            return None
        visitadas.append(url)
        try:
            r = s.get(url, headers=UA, timeout=timeout, allow_redirects=True)
        except requests.RequestException:
            return None
        if r.status_code >= 400 or "html" not in r.headers.get("content-type", "html"):
            return None
        texto, enlaces = leer_html(r.text)
        return extraer(texto), enlaces, r.url

    for url in [instrucciones, guia]:
        if bloqueado(url):
            continue
        out = probar(url)
        if out and len(out[0]) > len(mejor):
            mejor = {**out[0], "url": out[2]}
    portada = probar(web) if web and not bloqueado(web) else None
    enlaces = portada[1] if portada else []
    if portada and len(portada[0]) > len(mejor):
        mejor = {**portada[0], "url": portada[2]}
    for url in candidatos(portada[2] if portada else web, enlaces):
        if {"palabras_max", "recepcion"} <= set(mejor) or {"caracteres_max", "recepcion"} <= set(mejor):
            break
        out = probar(url)
        if out and len(out[0]) > len(mejor) - (1 if "url" in mejor else 0):
            mejor = {**out[0], "url": out[2]}
    if not mejor.get("url"):
        mejor["url"] = instrucciones or guia or web
    return mejor
