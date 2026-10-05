import os, tempfile
os.environ["MONITOR_DATOS"] = tempfile.mkdtemp()
from nucleo import db, web, monitor, recomendador as R
con = db.conectar(); web.cargar(con); df = monitor.vista(con); f = df[df.carreras != ""]
for q in ["Divulgación ESG y desempeño financiero en empresas chilenas", "Machine learning para detectar fraude contable",
          "Teletrabajo y derecho laboral en América Latina", "Fintech e inclusión financiera de pymes"]:
    top, m = R.recomendar(f, q)
    print("\n##", q, m)
    for _, r in top.iterrows():
        print(f"  {r.puntaje:.2f} {r.cuartil_sjr} {r.titulo} | {r.razones[0]}")
