# Scraper de Revolico — Energía solar en La Habana

Este paquete reemplaza el paso de Opencode: aquí ya están los **prompts** y el **código** que Opencode habría generado.

## Qué hay en la carpeta

| Archivo | Para qué sirve |
|---|---|
| `prompts/01_estaciones_energia.md` … `04_baterias.md` | Los 4 prompts detallados (rol, tarea, contexto, restricciones, formato de salida) para entregar o para pegar en Opencode |
| `scraper_revolico.py` | El scraper en Python (sirve para los 4 productos) |
| `buscar_estaciones.bat`, `buscar_paneles.bat`, `buscar_inversores.bat`, `buscar_baterias.bat` | Doble clic para ejecutar cada búsqueda (Windows) |
| `requirements.txt` | La única biblioteca que hace falta: Playwright |
| `resultados/` | Aquí aparecen los archivos JSON (se crea solo) |

## Instalación (una sola vez)

1. **Google Chrome** instalado (el normal de siempre).
2. **Python 3** instalado: https://www.python.org/downloads/
   En Windows, durante la instalación marca la casilla **"Add Python to PATH"**.
3. Abre una terminal (en Windows: tecla Windows → escribe `cmd` → Enter) y ejecuta:

   ```
   pip install playwright
   ```

   No hace falta `playwright install`: el script usa tu Chrome, así que no descarga otro navegador.

## Cómo usarlo

- **Windows:** doble clic en `buscar_estaciones.bat` (o el producto que quieras).
- **Desde la terminal**, dentro de esta carpeta:

  ```
  python scraper_revolico.py estaciones
  python scraper_revolico.py paneles
  python scraper_revolico.py inversores
  python scraper_revolico.py baterias
  ```

  O solo `python scraper_revolico.py` para elegir el producto en un menú.

Se abrirá una ventana de Chrome que navega sola. **No la cierres.** En la terminal se ve el progreso: cada anuncio guardado o descartado y el motivo. Al terminar dice dónde quedó el JSON, por ejemplo `resultados/estaciones_2026-10-28_2146.json`.

### Si aparece una verificación de seguridad

Revolico a veces muestra una pantalla de "verificando que eres humano". Si pasa, el script se detiene y lo avisa: resuélvela en la ventana de Chrome (marca la casilla) y luego presiona **Enter** en la terminal.

## Cómo funciona (para explicarlo)

1. Para cada producto busca varios términos (por ejemplo "ecoflow", "bluetti"…) directamente en las búsquedas de Revolico filtradas por La Habana: `https://www.revolico.com/search?q=ecoflow&province=la-habana&page=1`.
2. Cada página de resultados trae hasta 100 anuncios con sus datos (título, precio, moneda, fecha, municipio). El script se queda con los que por el título son del producto, son de La Habana y tienen menos de 30 días.
3. Abre cada uno de esos anuncios para leer la descripción y sacar de ahí tipo de batería, potencia en W, marca y modelo.
4. Si un dato no aparece, lo deja como `null` (vacío), sin inventarlo.
5. Guarda todo en un archivo JSON.

## Ajustes fáciles (al inicio de `scraper_revolico.py`)

- `PAGINAS_POR_BUSQUEDA = 3`: páginas de resultados por término (100 anuncios cada una).
- `PAUSA_ENTRE_PAGINAS = 2.0`: segundos de espera entre páginas.
- En `PRODUCTOS` se pueden agregar términos de búsqueda, palabras a excluir o marcas.

## Limitaciones conocidas

- La forma de buscar y de leer los anuncios se comprobó con páginas reales de Revolico guardadas en octubre de 2026, pero el script completo no se pudo ejecutar contra el sitio real. Si Revolico cambia su diseño puede dejar de funcionar.
- Los anuncios marcados como vendidos se descartan.
- Revolico usa una verificación de seguridad (Cloudflare). Si aparece, hay que resolverla a mano en Chrome y presionar Enter. Si se repite sin fin, el sitio está rechazando navegadores automáticos y el script no puede seguir; probar más tarde o con menos búsquedas.
- Para revisar un problema, ejecuta `python scraper_revolico.py estaciones --depurar`: se guardan copias de las páginas en la carpeta `depuracion/`, que se pueden enviar a quien vaya a corregir el script.
- La fecha (`fecha_publicacion`) es la que Revolico usa para ordenar los anuncios: la de publicación o la de la última vez que el vendedor renovó el anuncio.
- Algunos vendedores ponen precios simbólicos (por ejemplo 1 USD); el script guarda el precio tal como aparece.
- Marca, modelo, potencia y tipo de batería se sacan del texto que escribe cada vendedor, así que puede haber errores. Conviene revisar el JSON.
- Si el precio solo aparece en el texto con el símbolo `$`, la moneda queda vacía (en Cuba puede ser CUP o USD).
