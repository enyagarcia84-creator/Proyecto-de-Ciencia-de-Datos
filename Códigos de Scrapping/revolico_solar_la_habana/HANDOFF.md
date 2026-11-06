Continúa el proyecto «¿Hasta dónde llega el dinero de un cubano en el mercado solar de La Habana?». Enya no puede ejecutar el raspador en su computadora, así que el entregable son el script y los datos.

**Estado actual (2026-11-03):** la ronda 3 de Revolico está terminada. El zip final tiene 38,051 ofertas de los últimos 30 días, sin aviso PRELIMINAR y con `incompleto: false`. Facebook queda fuera de alcance.

**Archivos:**
- @.ajournal/2026-11-03.md: qué se hizo, decisiones, calidad y pendientes (entradas anteriores en la misma carpeta)
- @LEEME.md: uso, resultados y limitaciones
- @scraper_revolico.py: raspador y reglas de extracción
- @NFR.md: requisitos no funcionales
- @CONTEXTO_RONDA3.md: contexto de Enya
- @resultados/anuncios_revolico_2026-11-03.json: datos finales (42 MB; no lo leas entero)

**Objetivo siguiente:** confirmar que Enya recibió el zip final y que borró el preliminar de las 22:33, que filtraba teléfonos. Después, atender lo que pida Enya para sus gráficos.

**Reglas:**
- Para cambiar reglas de extracción, reconstruye con `--solo-extraer` (sin red) y revisa una muestra a mano.
- Tras cualquier reconstrucción, busca teléfonos en el JSON y el CSV antes de rehacer `revolico_solar_la_habana.zip`.
- No incluyas `cache/` en el zip.
- No inventes valores: lo desconocido queda en `null`.
