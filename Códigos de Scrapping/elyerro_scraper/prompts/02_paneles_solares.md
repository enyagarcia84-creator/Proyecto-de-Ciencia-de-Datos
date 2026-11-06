# Prompt para Opencode: Paneles solares

## Rol
Actúa como un **analista de datos** con experiencia en Python y en extracción de datos web (web scraping).

## Tarea
Crea un script de Python que haga scraping del sitio **El Yerro Menú**, sección de La Habana (https://elyerromenu.com/l/la-habana-cuba), y recopile **solo paneles solares (fotovoltaicos)** de tiendas ubicadas en **La Habana, Cuba**, que se hayan publicado o actualizado en los **últimos 30 días**.

De cada producto el script debe extraer:

1. **Precio** (número, sin símbolos).
2. **Moneda del precio** (tal como la muestra el sitio: USD, CUP, MLC, EUR, ZELLE…).
3. **Tipo de batería** (por ejemplo: LiFePO4, ion de litio, gel, AGM, plomo-ácido).
4. **Potencia en watts (W)** (número; convertir kW a W; no confundir con Wh, que es capacidad).
5. **Marca y modelo** (en dos campos separados).

Además debe guardar el **título**, el **nombre de la tienda**, la **URL** del producto, la **ubicación** (municipio), la **fecha de última actualización** y la **fecha de creación**.

La tarea se considera cumplida cuando:
- El script se ejecuta sin errores con `python scraper_elyerro.py paneles`, sin instalar nada aparte de Python.
- Genera un archivo JSON válido en la carpeta `resultados/`.
- Todos los productos del JSON son paneles solares, de tiendas de La Habana, y su fecha de actualización es de los últimos 30 días.
- Ningún valor de `potencia_w` es en realidad una capacidad en Wh.
- La consola muestra el progreso: cuántos productos se revisan, cuáles se guardan y por qué se descartan los demás.

## Contexto
- El Yerro Menú **no es un sitio de anuncios clasificados**: es un directorio de tiendas con sus catálogos de productos. No hay "fecha de publicación del anuncio"; cada producto tiene una fecha de creación (`createdAt`) y una de última actualización (`updatedAt`).
- **No hace falta navegador.** Las páginas se pueden descargar con `urllib.request` de la biblioteca estándar de Python, enviando un `User-Agent` de navegador normal. Así no aparece la verificación de Cloudflare ("¿eres un robot?") que bloqueó el intento anterior con Revolico. No usar Playwright, Selenium ni Chrome.
- Buscador del sitio, ya filtrado por La Habana. Hay dos formas de usarlo, con los mismos datos:
  - **Buscador interno (preferido, gasta unas 7 veces menos internet):**
    `https://elyerromenu.com/api/search/item?text=<término>&location=62aa50bedd41e7e0b82829f8&limit=100&skip=<n>`
    Devuelve JSON: `data.items` (máximo 100 por petición), `data.count` (total) y `data.skipped`.
    No es una parte pública del sitio y puede cambiar sin aviso.
  - **Página normal del buscador (respaldo, 20 resultados por página):**
    `https://elyerromenu.com/l/search/<término>?location=62aa50bedd41e7e0b82829f8&page=<n>`
  - El script debe probar primero el buscador interno y, si falla por cualquier motivo, avisar en la consola y seguir con la página normal.
- Cada página trae sus datos en JSON dentro de `<script id="__NUXT_DATA__">`. Es una lista "aplanada": los valores de los objetos son posiciones de otros elementos de la misma lista y hay que resolverlas.
  - En la página normal del buscador, el objeto con `items`, `totalCount` y `skipped` contiene los resultados. En las dos formas, cada resultado trae `name`, `price`, `currency`, `locName` (por ejemplo "Cerro, La Habana"), `parentName` (tienda) y `slug`.
  - La página del producto es `https://elyerromenu.com/b/<slug>`. Allí el objeto con `updatedAt`, `soldOut` y `price` es el producto. Tiene `note` (descripción), `price`, `offerPrice`, `inOffer`, `createdAt`, `updatedAt`, `soldOut`, `active` y `specs` (ficha técnica como `["Capacidad:3600Wh", "Potencia:3600W", "Tecnología:LiFePo4"]`).
  - El objeto con `organization`, `location` y `contact` es la tienda: `name`, `currency` y `contact.county` (municipio).
  - La página también trae un bloque `application/ld+json` de tipo `Product` con `offers.price` y `offers.priceCurrency`.
  - **Moneda:** usar la `currency` del resultado del buscador. La del bloque `ld+json` y la de la tienda a veces están mal (por ejemplo dicen CUP para un precio en USD).
- Términos de búsqueda sugeridos: "panel solar", "paneles solares", "placa solar".
- El script se ejecutará en una computadora con Windows en Cuba, con internet lento y caro.
- Para usar poco internet: pedir las páginas comprimidas (`Accept-Encoding: gzip`), filtrar por el título **antes** de abrir cada producto, no abrir dos veces el mismo producto y limitar las páginas por búsqueda.

## Restricciones
- Solo datos de https://elyerromenu.com y solo de tiendas de **La Habana**.
- Solo productos con `updatedAt` dentro de los **últimos 30 días**.
- Descartar lo que no sea del producto, por ejemplo lámparas, faroles o reflectores solares, bases y soportes para paneles, cables, conectores, controladores, kits y combos.
- Descartar los productos agotados (`soldOut`) o desactivados.
- **No todos los productos incluirán todos los datos.** El script debe guardar los que encuentre y dejar en `null` los que no pueda determinar; nunca inventar valores.
- Leer primero la ficha técnica (`specs`) y, si falta un dato, buscarlo en el título y la descripción. Si el precio es 0, buscarlo en la descripción (por ejemplo "2250 USD").
- Usar el precio de oferta cuando `inOffer` es verdadero.
- Potencia:
  - Preferir la de salida, nominal o continua antes que la de pico, entrada o carga.
  - Clasificar cada **trozo** de la línea y no la línea entera: en "Potencia de salida 1800W (3600W pico)" la potencia es 1800.
  - Aceptar números con separador de miles con espacio o con punto ("12 000 W", "10.000 W").
  - Ignorar los valores con "hasta", "en paralelo", "total" o "tolerancia".
  - En paneles e inversores, preferir la potencia que aparece en el título.
- En paneles e inversores, el tipo de batería y la capacidad solo se toman del título o de la ficha técnica: sus descripciones hablan de las baterías que se les pueden conectar.
- Marca: tomarla solo del título, de la ficha técnica o de un "Marca: X" escrito en la descripción. No buscar marcas sueltas en la descripción, porque muchas dicen "compatible con EcoFlow".
- Modelo: si la descripción dice "Modelo: X", usar eso; si no, las palabras que siguen a la marca en el título, sin incluir medidas (3600W, 2048Wh, 48V), precios ni palabras como "nuevo" u "oferta".
- Usar solo la biblioteca estándar de Python (`urllib`, `json`, `re`, `gzip`, `datetime`, `unicodedata`).
- Esperar 1 o 2 segundos entre página y página, y reintentar si una página falla por la conexión.
- Si el sitio responde 403/429 o muestra una verificación de seguridad, detenerse con un mensaje claro en español y **guardar lo que ya se leyó** con `"incompleto": true` (con internet caro, no se debe perder lo descargado).
- Un producto que falle, por el motivo que sea, no debe detener todo el script.
- Que la consola de Windows no falle al mostrar emojis de los títulos (`sys.stdout.reconfigure(errors="replace")`).
- Código comentado en español y fácil de entender para un principiante, con la configuración (páginas, pausa, términos, palabras a excluir, marcas) al inicio del archivo.

## Formato de salida
Un archivo **JSON** (UTF-8, con sangría) en `resultados/paneles_AAAA-MM-DD_HHMM.json` con esta estructura:

```json
{
  "producto": "Paneles solares",
  "fuente": "https://elyerromenu.com/l/la-habana-cuba",
  "ubicacion": "La Habana, Cuba",
  "fecha_consulta": "AAAA-MM-DD HH:MM",
  "periodo": "productos actualizados en los últimos 30 días",
  "incompleto": false,
  "total_productos": 0,
  "productos": [
    {
      "titulo": "texto",
      "tienda": "texto o null",
      "url": "https://elyerromenu.com/b/...",
      "ubicacion": "Municipio, La Habana",
      "fecha_actualizacion": "AAAA-MM-DD",
      "fecha_creacion": "AAAA-MM-DD",
      "precio": 0,
      "moneda": "USD | CUP | MLC | EUR | ZELLE | null",
      "tipo_bateria": "texto o null",
      "potencia_w": 0,
      "capacidad_wh": 0,
      "marca": "texto o null",
      "modelo": "texto o null"
    }
  ]
}
```

Entrega el código completo en un solo archivo `scraper_elyerro.py`, junto con las instrucciones para ejecutarlo.
