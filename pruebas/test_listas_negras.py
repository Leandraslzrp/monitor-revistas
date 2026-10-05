from nucleo import listas_negras as L

LISTAS = {"rev_nombre": {"journal of fake studies": "Journal of Fake Studies", "research": "Research"},
          "rev_dominio": {"fakestudies.org": "Journal of Fake Studies"},
          "edi_nombre": {"predatory press": "Predatory Press"}, "edi_dominio": {"predpress.com": "Predatory Press"},
          "sec_autentica": {"real journal": (["http://real-journal.net"], "https://real.org")},
          "sec_dominio": {"real-journal.net": "Real Journal"}}


def test_evaluar():
    assert L.evaluar("Journal of Fake Studies", "Someone", None, LISTAS)[0] == "sospechosa"
    assert L.evaluar("Other", "Predatory Press", None, LISTAS)[0] == "sospechosa"
    assert L.evaluar("Other", "X", "https://www.predpress.com/j1", LISTAS)[0] == "sospechosa"
    assert L.evaluar("Real Journal", "Univ", "https://real.org", LISTAS)[0] == "suplantada"
    assert L.evaluar("Real Journal", "Univ", "http://real-journal.net/", LISTAS)[0] == "sospechosa"
    assert L.evaluar("Old Journal (discontinued)", "X", None, LISTAS)[0] == "descontinuada"
    # coincidencias de nombre con editoriales reconocidas o títulos de una palabra no cuentan
    assert L.evaluar("Journal of Fake Studies", "Elsevier B.V.", None, LISTAS)[0] == ""
    assert L.evaluar("Research", "Someone", None, LISTAS)[0] == ""
