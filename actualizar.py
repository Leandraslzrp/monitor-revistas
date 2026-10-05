"""Actualización automática (para programarla con el Programador de tareas de
Windows o cron). Uso:

    python actualizar.py                 # descarga Scimago, enriquece y notifica
    python actualizar.py --sin-descarga  # usa los archivos ya cargados
    python actualizar.py --web           # versión web: lee y escribe datos_web/
"""
import argparse
import os
import sys
import tempfile

WEB = "--web" in sys.argv
if WEB:  # trabajar en una carpeta temporal y devolver el resultado a datos_web/
    os.environ["MONITOR_DATOS"] = tempfile.mkdtemp(prefix="monitor_")

from nucleo import config, db, monitor  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="Monitor de revistas: actualización")
    ap.add_argument("--sin-descarga", action="store_true", help="no descargar Scimago")
    ap.add_argument("--sin-enriquecer", action="store_true")
    ap.add_argument("--web", action="store_true", help="usar la carpeta datos_web/ del repositorio")
    ap.add_argument("--exigencias", type=int, default=1500,
                    help="cuántas revistas revisar en busca de exigencias para autores (0 = ninguna)")
    args = ap.parse_args()

    con = db.conectar()
    if args.web:
        from nucleo import web
        web.cargar(con)
    cfg = config.cargar()
    if args.sin_enriquecer:
        if not args.sin_descarga:
            monitor.descargar_scimago(con)
        avisos = monitor.actualizar_listas(con, cfg)
    else:
        avisos, error = monitor.actualizacion_completa(
            con, cfg, progreso=lambda f, t: print(f"[{f:4.0%}] {t}", flush=True),
            descargar=not args.sin_descarga, exigencias_limite=args.exigencias)
        if error:  # se sigue con el archivo anterior
            print(f"No se pudo descargar Scimago: {error}", file=sys.stderr)
    for a in avisos:
        print("ALERTA:", a)
    try:
        n = monitor.enviar_alertas(con, cfg)
        if n:
            print(f"{n} alerta(s) enviadas por correo.")
    except Exception as e:
        print(f"No se pudo enviar el correo: {e}", file=sys.stderr)
    if args.web:
        from nucleo import suscripciones
        try:
            n = suscripciones.enviar_resumenes(con, cfg)
            print(f"{n} resumen(es) semanal(es) enviados a suscriptores.")
        except Exception as e:
            print(f"No se pudieron enviar los resúmenes: {e}", file=sys.stderr)
        web.guardar(con)


if __name__ == "__main__":
    main()
