# Monitor de Revistas Indexadas (Scopus / Web of Science) · FACE

Programa de escritorio que reúne en una sola plataforma las revistas indexadas en
**Scopus** y **Web of Science**, con sus indicadores, clasificación por área,
APC y exigencias para autores, y que **avisa por
correo y dentro de la app** cuando algo cambia en las revistas que usted sigue.

Se abre en el navegador, pero todo funciona en su computador: los datos quedan en
la carpeta `datos/`.

## Cómo empezar

1. Descomprima la carpeta `monitor-revistas` (clic derecho → *Extraer todo*).
2. Haga doble clic en `Iniciar_Windows.bat` (en Mac, `Iniciar_Mac.command`; la
   primera vez: clic derecho → Abrir).
3. La primera vez el programa se prepara solo: si falta Python lo instala, instala
   sus componentes y crea el acceso directo **Monitor de Revistas** en el
   Escritorio. Tarda unos minutos. En Mac, si falta Python, se abre el instalador
   oficial; termínelo y vuelva a abrir el archivo.
4. Se abre el navegador. Pulse **🚀 Comenzar** y listo.

Las siguientes veces use el acceso directo del Escritorio. Deje la ventana negra
abierta (puede minimizarla) mientras usa el programa.

Para mantener los datos al día pulse **🔄 Actualizar todo ahora** en *Actualizar
datos* (el programa le recuerda si pasan más de 30 días).

**Web of Science (opcional, una vez al año):** Clarivate no permite la descarga
automática. Descargue las listas SSCI, SCIE, AHCI y ESCI desde
<https://mjl.clarivate.com> (cuenta gratuita) y arrástrelas en *Actualizar datos*.
Si la universidad tiene licencia del **JCR**, suba también su exporte para
obtener el JIF y el cuartil JIF.

Luego, en **Configuración**, puede cambiar sus áreas, activar el correo.

## Qué muestra cada revista

| Bloque | Contenido | Fuente |
|---|---|---|
| Indexación | Scopus, colecciones WoS (SSCI, SCIE, AHCI, ESCI) | Scimago, Clarivate MJL |
| Ranking | Cuartil SJR (mejor y por categoría), SJR, índice H, JIF y cuartil JIF*, CiteScore* | Scimago, JCR*, API Elsevier* |
| Indicadores de producción | Documentos por año y en 3 años, citas, citas/documento, producción y citas anuales, índices H e i10 | Scimago, OpenAlex |
| Clasificación | Áreas de la FACE según sus departamentos (Economía y Finanzas, Administración y Auditoría, Gestión Empresarial, Sistemas de Información, Ciencias de la Computación y TI) más Ciencias Jurídicas, áreas y categorías con cuartil | Scimago, Clarivate |
| Costos | APC (cargo por publicar), otros cargos, exoneraciones | OpenAlex, DOAJ |
| Exigencias | Extensión máxima (palabras, caracteres o páginas), extensión del resumen, recepción continua o por convocatoria (con fecha límite), revisión por pares, tiempo a publicación, idiomas | Instrucciones para autores del sitio de cada revista (lectura automática), DOAJ y correcciones del administrador |

\* Requieren licencia o clave institucional (ver abajo).

## Alertas

Se generan al actualizar, para las revistas marcadas con ⭐ **Seguir**:

- Cambio de cuartil SJR (sube/baja) o de cuartil JIF.
- Ingreso o salida de Scopus o de una colección de Web of Science.
- Cambio de APC; ingreso o salida de DOAJ.
- Revistas nuevas que aparecen en sus áreas de interés.

Se ven en la página **Alertas** y se envían por correo si está activado (Gmail u
Outlook: use una *contraseña de aplicación*, no su contraseña normal).

### Actualización automática

- Windows: abra el *Programador de tareas* → *Crear tarea básica* → semanal →
  acción *Iniciar un programa* → `Actualizar_Windows.bat`.
- Mac/Linux: `crontab -e` y agregue
  `0 7 * * 1 /ruta/a/monitor-revistas/Actualizar_Mac_Linux.sh`.

El registro queda en `datos/actualizacion.log`.

## Qué es gratis y qué requiere licencia

| Fuente | Acceso |
|---|---|
| Scimago (cuartiles y métricas de Scopus) | Gratis |
| Clarivate Master Journal List (colecciones WoS) | Gratis con cuenta |
| OpenAlex (producción, citas, APC) | Gratis (opcional: correo o API key para más velocidad) |
| DOAJ (políticas de revistas de acceso abierto) | Gratis |
| JCR (JIF y cuartil JIF) | Licencia institucional de Clarivate |
| CiteScore (API de Scopus) | API key de <https://dev.elsevier.com>, normalmente desde la red de la universidad |

Las exigencias detalladas (extensión, formato, plantilla) no se publican de forma
estructurada para todas las revistas; la pestaña **Notas** de cada revista permite
registrarlas y compartirlas copiando la carpeta `datos/`.

## ¿Por qué faltan algunas exigencias?

La extensión máxima y las fechas de recepción solo están escritas en la página de instrucciones de
cada revista. Las grandes editoriales (Elsevier, Wiley, Taylor & Francis, SAGE, Oxford, Emerald,
IEEE) bloquean a los programas que leen sus páginas, incluso con un navegador automático (probado
en octubre de 2026). Para esas revistas se muestra el enlace directo a sus instrucciones. Cuando no
se encuentra un periodo publicado se indica *Continua (habitual)*, porque casi todas las revistas
indexadas reciben artículos todo el año. Quien administra la página puede completar o corregir
cada revista desde su ficha (✏️); esos datos no se sobrescriben.

La página **📬 Convocatorias** reúne las revistas con convocatoria o número especial abierto,
ordenadas por fecha de cierre.

## Versión web (un enlace para toda la FACE)

La misma app puede publicarse gratis en Streamlit Community Cloud desde un
repositorio de GitHub. En esa versión:

- Todos ven las mismas revistas, indicadores, exigencias y convocatorias abiertas, y pueden
  descargar a Excel sin instalar nada.
- Los datos viven en la carpeta `datos_web/` del repositorio. La acción de GitHub
  `.github/workflows/actualizar.yml` los actualiza cada lunes (o al pulsar
  *Actualizar todo ahora* en la app) y envía las alertas por correo.
- La lista de revistas en seguimiento, las notas, las correcciones de exigencias y
  las listas de WoS las administra quien tenga la contraseña (menú 🔒 Administración);
  los cambios se guardan en el repositorio.

Publicación:

1. En <https://share.streamlit.io> entre con GitHub → *Create app* → elija el
   repositorio, rama `main`, archivo `app.py`.
2. En *Advanced settings → Secrets* pegue el contenido de
   `.streamlit/secrets.toml.ejemplo` con sus valores. El `github_token` es un
   *fine-grained token* (GitHub → Settings → Developer settings) limitado a este
   repositorio con permisos **Contents** y **Actions** de lectura y escritura.
3. En GitHub → repositorio → *Settings → Secrets and variables → Actions* agregue
   `SMTP_HOST`, `SMTP_PUERTO`, `SMTP_USUARIO` y `SMTP_PASSWORD` para enviar las
   alertas por correo (opcional: `OPENALEX_EMAIL`, `ELSEVIER_API_KEY`).

## Compartir con otros académicos

Comprima la carpeta **sin** `datos/revistas.db`, `datos/config.json` (contiene su
contraseña de correo) ni `.venv`. Si quiere compartir una base ya cargada, incluya
`datos/revistas.db` y `datos/fuentes/` pero no `config.json`.

## Para soporte técnico

- Código: `app.py` (interfaz), `nucleo/fuentes.py` (lectura de fuentes y APIs),
  `nucleo/monitor.py` (combinación, alertas, correo),
  `actualizar.py` (actualización por línea de comandos).
- Pruebas sin conexión: `python -m pytest pruebas`.
- Datos: SQLite en `datos/revistas.db`.

## Cómo se obtienen las exigencias para autores

No existe una base pública con la extensión máxima o el periodo de recepción de
cada revista. El programa visita el sitio web de la revista (registrado en
OpenAlex o DOAJ), busca la página de instrucciones para autores y lee frases como
"no debe exceder 8.000 palabras" o "recepción en flujo continuo". La ficha
muestra la frase encontrada y el enlace para verificarla. La actualización
semanal revisa hasta 1.500 revistas por vez (primero las seguidas y las de mejor
cuartil) y las fichas se completan solas al abrirlas. Las editoriales grandes (Elsevier, Wiley, Taylor & Francis, Springer, SAGE, Oxford,
IEEE, entre otras) bloquean la lectura automática: para ellas la ficha entrega el
enlace directo a su guía para autores, y el administrador puede completar los datos a mano desde la ficha (✏️ Corregir o completar exigencias).
