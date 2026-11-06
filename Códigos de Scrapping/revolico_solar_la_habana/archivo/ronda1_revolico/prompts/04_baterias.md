# Prompt para Opencode — Baterías para almacenar la energía de paneles solares

## Rol
Actúa como un **analista de datos** con experiencia en Python y en extracción de datos web (web scraping) con Playwright.

## Tarea
Crea un script de Python que haga scraping del sitio de anuncios clasificados **Revolico** (https://www.revolico.com) y recopile **solo anuncios de baterías para almacenar la energía de paneles solares (LiFePO4, litio, gel, AGM, plomo-ácido, bancos de baterías)** publicados en **La Habana, Cuba**, durante los **últimos 30 días**.

De cada anuncio el script debe extraer:

1. **Precio** (número, sin símbolos).
2. **Moneda del precio** (USD, CUP, MLC o EUR).
3. **Tipo de batería** (por ejemplo: LiFePO4, ion de litio, gel, AGM, plomo-ácido).
4. **Potencia en watts (W)** (número; convertir kW a W; no confundir con Wh, que es capacidad).
5. **Marca y modelo** (en dos campos separados).

Además debe guardar el **título**, la **URL** del anuncio, la **fecha de publicación** y la **ubicación**.

La tarea se considera cumplida cuando:
- El script se ejecuta sin errores con `python scraper_revolico.py baterias`.
- Genera un archivo JSON válido en la carpeta `resultados/`.
- Todos los anuncios del JSON son de baterías para almacenar la energía de paneles solares, de La Habana y de los últimos 30 días.
- Se muestra en la consola el progreso (cuántos anuncios se revisan, cuáles se guardan y por qué se descartan los demás).

## Contexto
- Fuente de datos: únicamente https://www.revolico.com.
- Biblioteca: usar **solamente Playwright** para Python (`playwright.sync_api`). No usar requests, BeautifulSoup, Selenium ni APIs externas; para procesar el texto se pueden usar módulos estándar de Python (`re`, `json`, `datetime`).
- Navegador: usar el **Google Chrome instalado** en la computadora (`channel="chrome"`), en modo visible (`headless=False`), para no tener que descargar otro navegador.
- El script se ejecutará en una computadora en Cuba, con una conexión a internet que puede ser lenta.
- Términos de búsqueda sugeridos: "bateria litio", "bateria lifepo4", "bateria solar", "banco de baterias", "bateria de gel".
- Revolico puede mostrar una verificación de seguridad; si aparece, el script debe pausarse y pedir al usuario que la resuelva a mano en la ventana de Chrome y presione Enter.

## Restricciones
- Solo anuncios de la página https://www.revolico.com.
- Solo anuncios de **La Habana**.
- Solo anuncios de los **últimos 30 días** (interpretar fechas como "hace 3 días", "ayer" o "12/10/2026").
- Descartar anuncios que no sean del producto, por ejemplo baterías de laptop, celular, moto, auto, bicicleta, relojes y controles remotos.
- **No todos los anuncios incluirán todos los datos.** El script debe guardar los datos que encuentre y dejar en `null` los que no pueda determinar; nunca inventar valores.
- Esperar unos segundos entre página y página para no sobrecargar el sitio, y limitar la cantidad de páginas de resultados revisadas.
- Manejar errores (tiempo de espera agotado, anuncio que no carga) sin que el script se detenga por completo.
- Código comentado en español y fácil de entender para un principiante.

## Formato de salida
Un archivo **JSON** (UTF-8, con sangría) con esta estructura:

```json
{
  "producto": "...",
  "fuente": "https://www.revolico.com",
  "ubicacion": "La Habana, Cuba",
  "fecha_consulta": "AAAA-MM-DD HH:MM",
  "periodo": "últimos 30 días",
  "total_anuncios": 0,
  "anuncios": [
    {
      "titulo": "texto o null",
      "url": "https://www.revolico.com/...",
      "fecha_publicacion": "AAAA-MM-DD o null",
      "ubicacion": "texto o null",
      "precio": 0,
      "moneda": "USD | CUP | MLC | EUR | null",
      "tipo_bateria": "texto o null",
      "potencia_w": 0,
      "marca": "texto o null",
      "modelo": "texto o null"
    }
  ]
}
```

Entrega el código completo en un solo archivo `scraper_revolico.py`, junto con las instrucciones para instalar Playwright (`pip install playwright`) y ejecutar el script.
