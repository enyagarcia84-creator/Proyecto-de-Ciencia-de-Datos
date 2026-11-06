# Scraper de El Yerro Menú: energía solar en La Habana

Segunda versión. La primera (Revolico) quedó bloqueada por la verificación de Cloudflare
("¿eres un robot?"). Esta usa **El Yerro Menú** (https://elyerromenu.com/l/la-habana-cuba),
que se puede leer **sin navegador**, así que esa verificación no aparece.

Aquí ya están los **prompts** y el **código** que Opencode habría generado.

## Qué hay en la carpeta

| Archivo | Para qué sirve |
|---|---|
| `prompts/01_estaciones_energia.md` … `04_baterias.md` | Los 4 prompts (rol, tarea, contexto, restricciones, formato de salida) para entregar o pegar en Opencode |
| `scraper_elyerro.py` | El scraper en Python (sirve para los 4 productos) |
| `buscar_estaciones.bat`, `buscar_paneles.bat`, `buscar_inversores.bat`, `buscar_baterias.bat` | Doble clic para ejecutar cada búsqueda (Windows) |
| `resultados/` | Aquí aparecen los archivos JSON (se crea solo) |

## Instalación (una sola vez)

Solo hace falta **Python 3** (versión 3.8 o más nueva): https://www.python.org/downloads/
En Windows, durante la instalación marca la casilla **"Add Python to PATH"**.

No hay que instalar nada más: ni Chrome, ni Playwright, ni `pip install`.

## Cómo usarlo

- **Windows:** doble clic en `buscar_estaciones.bat` (o el producto que quieras).
- **Desde la terminal**, dentro de esta carpeta:

  ```
  python scraper_elyerro.py estaciones
  python scraper_elyerro.py paneles
  python scraper_elyerro.py inversores
  python scraper_elyerro.py baterias
  ```

  O solo `python scraper_elyerro.py` para elegir el producto en un menú.

En la terminal se ve el progreso: cada producto guardado o descartado y el motivo. Al terminar
dice dónde quedó el JSON, por ejemplo `resultados/estaciones_2026-11-01_0215.json`.
Cada búsqueda tarda unos minutos (se espera un poco entre página y página para no saturar el sitio).

## Cómo funciona (para explicarlo)

1. Para cada producto usa el buscador de El Yerro con varios términos (por ejemplo "ecoflow",
   "bluetti"…), ya filtrado por La Habana. Primero prueba el buscador interno del sitio
   (`/api/search/item`), que trae 100 resultados de una vez y gasta unas 7 veces menos internet.
   Si ese buscador falla, usa las páginas normales (`/l/search/ecoflow?location=...&page=1`,
   20 resultados cada una), que traen los mismos datos.
2. Cada resultado trae título, precio, moneda, tienda y municipio.
   El script se queda con los que por el título son del producto buscado (descarta accesorios
   como cables, sartenes, bases de paneles, etc.).
3. Abre cada uno de esos productos para leer la fecha de actualización, la descripción y la
   ficha técnica, y saca de ahí tipo de batería, potencia en W, capacidad en Wh, marca y modelo.
4. Si un dato no aparece, lo deja como `null` (vacío), sin inventarlo.
5. Guarda todo en un archivo JSON.

## Datos que guarda de cada producto

`titulo`, `tienda`, `url`, `ubicacion` (municipio), `fecha_actualizacion`, `fecha_creacion`,
`precio`, `moneda`, `tipo_bateria`, `potencia_w`, `capacidad_wh`, `marca`, `modelo`.

`capacidad_wh` no estaba pedido, pero se agrega porque en estaciones y baterías es el dato
que más importa (y así no se confunde con la potencia en W).

## Ajustes fáciles (al inicio de `scraper_elyerro.py`)

- `RESULTADOS_POR_BUSQUEDA = 100`: máximo de resultados revisados por cada término.
- `USAR_BUSCADOR_RAPIDO = True`: poner `False` para usar solo las páginas normales del buscador.
- `PAUSA_ENTRE_PAGINAS = 1.5`: segundos de espera entre páginas.
- `DIAS_MAXIMOS = 30`: antigüedad máxima.
- En `PRODUCTOS` se pueden agregar términos de búsqueda, palabras a excluir o marcas.

## Limitaciones conocidas

- **El Yerro no es un sitio de anuncios, es un directorio de tiendas con catálogos.** No existe
  "fecha de publicación del anuncio". El filtro de "últimos 30 días" usa la **fecha de última
  actualización** del producto en el catálogo (`fecha_actualizacion`). También se guarda la
  fecha en que la tienda lo creó (`fecha_creacion`), que puede ser más vieja.
- Son precios de **tiendas**, no de particulares. Una misma tienda puede tener el mismo producto
  repetido con precios distintos.
- Solo se guardan productos de tiendas ubicadas en La Habana. Se descartan los agotados.
- La moneda se guarda tal como la muestra el buscador de El Yerro (USD, CUP, EUR, ZELLE…).
  Si el precio en el catálogo es 0, se busca en la descripción (por ejemplo "2250 USD").
- Marca, modelo, potencia y tipo de batería se sacan de lo que escribe cada tienda, así que
  puede haber errores (por ejemplo, si el título dice "3600W / 1800W" sin aclarar cuál es la
  potencia de pico). Conviene revisar el JSON.
- En paneles e inversores el "tipo de batería" y la capacidad casi nunca aplican: solo se toman
  del título o de la ficha técnica, por eso suelen quedar vacíos.
- Algunas plantas eléctricas de gasolina se venden como "inverter" sin decir que son plantas
  (por ejemplo "Inverter Sigma SG6500iSE"); pueden colarse en los inversores.
- Si el sitio empieza a bloquear las visitas automáticas, el script lo avisa, guarda lo que ya
  leyó (el JSON queda con `"incompleto": true`) y se detiene. Probar más tarde o desde otra red.
- Para revisar un problema, ejecuta `python scraper_elyerro.py estaciones --depurar`: se
  guardan copias de las páginas en la carpeta `depuracion/`, que se pueden enviar a quien vaya
  a corregir el script.
- El buscador rápido es una parte interna del sitio, no pública: puede cambiar o cerrarse sin
  aviso. Si deja de responder, el script lo dice en la consola y sigue con las páginas normales.
- Si El Yerro cambia la forma de sus páginas, el script puede dejar de funcionar.
