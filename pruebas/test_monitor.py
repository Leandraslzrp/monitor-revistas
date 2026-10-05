"""Pruebas sin conexión: python -m pytest pruebas"""
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ["MONITOR_DATOS"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo import config, db, fuentes, monitor  # noqa: E402

FX = Path(__file__).parent / "fixtures"


class Resp:
    def __init__(self, data, code=200):
        self._d, self.status_code = data, code

    def json(self):
        return self._d


class SesionFalsa:
    """Imita OpenAlex y DOAJ."""
    def __init__(self, apc=1500):
        self.apc = apc

    def get(self, url, params=None, headers=None, timeout=None):
        if "openalex" in url:
            issns = params["filter"][5:].split("|")
            res = []
            if "1138-4891" in issns:
                res.append({"id": "S1", "issn": ["1138-4891", "1988-4885"], "works_count": 900,
                            "cited_by_count": 8000, "summary_stats": {"2yr_mean_citedness": 2.5,
                            "h_index": 30, "i10_index": 200}, "is_oa": True, "is_in_doaj": True,
                            "apc_usd": self.apc, "homepage_url": "https://example.org",
                            "counts_by_year": [{"year": 2023, "works_count": 25, "cited_by_count": 700},
                                               {"year": 2024, "works_count": 21, "cited_by_count": 760}]})
            return Resp({"results": res})
        if "doaj" in url and "1138-4891" in url:
            return Resp({"results": [{"bibjson": {
                "apc": {"has_apc": True, "max": [{"price": self.apc, "currency": "USD"}]},
                "editorial": {"review_process": ["Double anonymous peer review"]},
                "plagiarism": {"detection": True}, "publication_time_weeks": 14,
                "license": [{"type": "CC BY-NC-ND"}], "language": ["ES", "EN"],
                "ref": {"author_instructions": "https://example.org/autores"}}}]})
        return Resp({"results": []})


def test_flujo_completo():
    con = db.conectar()
    cfg = config.cargar()
    assert fuentes.normalizar_issn("00335533, 15314650") == ["0033-5533", "1531-4650"]

    assert monitor.importar_scimago(con, FX / "scimago_2023.csv") == 2023
    monitor.importar_wos(FX / "wos_SSCI.csv", "SSCI")
    assert monitor.actualizar_listas(con, cfg) == []  # primera carga: sin alertas
    rid = "1138-4891"
    db.seguir(con, rid)
    monitor.enriquecer(con, cfg, "areas", sesion=SesionFalsa(1500))

    # Nuevo año: Revista de Contabilidad baja a Q2, ingresa JCR y una revista nueva
    assert monitor.importar_scimago(con, FX / "scimago_2024.csv") == 2024
    monitor.importar_wos(FX / "JCR_export.csv", "JCR")
    avisos = monitor.actualizar_listas(con, cfg)
    texto = " | ".join(avisos)
    assert "Q1 a Q2" in texto
    assert "Cuartil JIF" not in texto  # no tenía cuartil JIF antes
    assert "Nueva Revista de Finanzas" in texto
    assert "Journal of Chemical Physics" not in texto
    avisos = monitor.enriquecer(con, cfg, "seguimiento", sesion=SesionFalsa(1800))
    assert any("USD 1,500 a USD 1,800" in a for a in avisos)

    v = monitor.vista(con).set_index("rid")
    assert v.loc[rid, "cuartil_sjr"] == "Q2"
    assert v.loc[rid, "jif_cuartil"] == "Q3"
    assert v.loc[rid, "wos_colecciones"] == "SSCI"
    assert v.loc[rid, "doaj_revision"] == "Double anonymous peer review"
    assert json.loads(v.loc[rid, "prod_anual"])["2024"] == [21, 760]
    assert v.loc["0121-4772", "scopus"] == 0 and v.loc["0121-4772", "wos"] == 1  # solo WoS
    assert v.loc["0121-4772", "areas"] == "Economics, Econometrics and Finance"
    hist = db.tabla(con, "historial")
    assert set(hist[hist.rid == rid]["anio"]) == {2023, 2024}

    inc = monitor.cargar_incentivos()
    inc.loc[(inc.base == "Scopus") & (inc.nivel == "Q2"), "monto"] = 3000
    inc.loc[(inc.base == "WoS") & (inc.nivel == "SSCI"), "monto"] = 5000
    monto, regla = monitor.calcular_incentivo(v.loc[rid].to_dict(), inc)
    assert monto == 5000 and "SSCI" in regla
