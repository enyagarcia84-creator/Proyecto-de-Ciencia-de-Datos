# Mercado solar de La Habana: scraper y datos de Revolico

Datos para la investigación *¿Hasta dónde llega el dinero de un cubano en el mercado solar de La Habana?*

## Qué hay en la carpeta

| Archivo | Para qué sirve |
|---|---|
| `resultados/anuncios_revolico_2026-11-03.json` | La base de datos completa, con las descripciones de la muestra |
| `resultados/anuncios_revolico_2026-11-03.csv` | Lo mismo, sin descripciones, para abrir en Excel |
| `scraper_revolico.py` | El código que generó los datos |

## Los datos

**38 051 ofertas** de 41 989 anuncios de La Habana, renovados entre el **4 de octubre y el 3 de
noviembre de 2026**. En total se revisaron 56 107 anuncios; el resto eran accesorios, plantas de
gasolina y otros productos. De las ofertas, **2 509 se abrieron** para leer su descripción.

| Categoría | Ofertas | Mediana (USD) | Con precio en USD | Con potencia | Con capacidad | Con marca |
|---|---:|---:|---:|---:|---:|---:|
| Estaciones portátiles | 12 340 | 770 | 97 % | 24 % | 28 % | 88 % |
| Kits y sistemas | 10 072 | 2 850 | 94 % | 53 % | 45 % | 60 % |
| Paneles | 5 545 | 170 | 96 % | 75 % | no aplica | 42 % |
| Baterías | 5 159 | 1 470 | 96 % | no aplica | 86 % | 56 % |
| Inversores | 4 935 | 850 | 96 % | 77 % | no aplica | 66 % |

### Cómo leerlos (importante para la investigación)

- **La unidad es la "oferta", no el producto.** Los vendedores republican lo mismo una y otra vez.
  Mismo vendedor, categoría, precio, marca y prestaciones cuentan como una sola oferta, y
  `veces_publicado` dice cuántos anuncios agrupa. Si alguien republica a otro precio, cuenta como otra.
- **La fecha no es la de publicación.** `fecha_actualizacion` es la última vez que el anuncio se
  publicó o renovó. Los últimos días tienen muchos más anuncios solo porque ahí están los renovados.
  **Estos datos no sirven para hablar de tendencias en el tiempo.**
- **Son precios pedidos, no precios de venta.**
- **Revolico es una parte del mercado:** no representa a todo el que vende, ni dice qué se compró.
- **Casi todo está en USD:** solo 65 ofertas están en CUP.
- **Tasa de cambio:** los pocos precios en otra moneda se convierten con una sola tasa, la de elTOQUE
  del 2 de noviembre de 2026 (1 USD = 900 CUP, 1 EUR = 990 CUP, según Infobae y Directorio Cubano). El
  peso se movió mucho en esas semanas, así que es una aproximación. MLC no se convierte.
- **Precios dudosos:** el precio original nunca se cambia. Si no es creíble, se explica en
  `precio_alerta` y `precio_usd` queda vacío. Así hay 1 199 ofertas, sobre todo precios simbólicos
  como 1 USD. **Para los gráficos usa `precio_usd`.**

### Qué datos sirven para cada gráfico

| Gráfico | Campos | Observación |
|---|---|---|
| 1. Qué se vende | `categoria` | Cuenta ofertas, no anuncios |
| 2. Cuánto cuesta entrar | `categoria`, `precio_usd` | Usa medianas |
| 3. Potencia por dinero (paneles) | `precio_usd`, `potencia_w`, `usd_por_w` | |
| 4. Energía que se almacena | `precio_usd`, `capacidad_wh`, `usd_por_wh` | En estaciones solo 28 % trae la capacidad, casi siempre en el título. Ver abajo |
| 5. Prestaciones por categoría | `subcategoria`, `precio_usd` | |
| 6. Qué incluye | `instalacion`, `envio`, `estado`, `tiene_garantia` | **Solo con `descripcion_leida` = true** |
| 7. Por presupuesto | `precio_usd`, `categoria` | Los tramos de presupuesto los defines tú |
| 8. Opciones destacadas | `usd_por_w`, `usd_por_wh`, `url` | Abre el anuncio antes de citarlo |

**Sobre el gráfico 6:** se abrió una muestra al azar de unas 500 ofertas por categoría, porque abrirlas
todas tardaría muchas horas. En un anuncio no abierto, un campo vacío **no** significa "no lo ofrece".
Incluso abierto, vacío significa "el anuncio no lo dice o las reglas no lo reconocieron". Además, 188 de los 2 509 tienen la
descripción vacía. Lo que dicen los anuncios abiertos:

| Categoría | Abiertas | Instalación: incluida / ofrecida / no incluida | Envío: gratis / disponible | Garantía: sí / no | Nuevo / usado |
|---|---:|---:|---:|---:|---:|
| Estaciones | 500 | 0 / 1 / 1 | 201 / 72 | 229 / 0 | 74 / 3 |
| Kits | 500 | 37 / 49 / 4 | 254 / 31 | 181 / 7 | 39 / 1 |
| Paneles | 509 | 0 / 4 / 0 | 189 / 78 | 121 / 1 | 29 / 3 |
| Baterías | 500 | 0 / 2 / 3 | 232 / 61 | 155 / 6 | 98 / 0 |
| Inversores | 500 | 1 / 4 / 4 | 236 / 61 | 173 / 2 | 70 / 1 |

La instalación solo tiene datos suficientes en los kits; en las demás categorías son muy pocos casos
para sacar conclusiones.

**Sobre los gráficos 3 y 4:** la potencia y la capacidad se leen del título y, si el anuncio se abrió,
también de la descripción. Por eso los abiertos tienen más datos (en estaciones, 68 % trae capacidad
frente a 28 % en el total). Los anuncios que dan estas cifras en el título no tienen por qué ser iguales
a los demás, así que estos gráficos describen a los anuncios con datos, no a todo el mercado.

## Campos

| Campo | Significado |
|---|---|
| `id`, `url`, `titulo` | Identificador, enlace y título del anuncio |
| `categoria` | `paneles`, `estaciones`, `baterias`, `inversores` o `kits` |
| `subcategoria` | Panel: bifacial, monofacial… Estación: tramo de capacidad. Batería: tipo. Inversor: híbrido… Kit: con o sin paneles |
| `fecha_actualizacion`, `municipio` | Última renovación y municipio |
| `precio`, `moneda`, `precio_origen` | Tal como aparece en el anuncio, y de dónde salió |
| `precio_usd`, `precio_alerta` | Precio en USD para analizar; motivo si se descartó |
| `marca`, `modelo` | En un kit, la marca principal |
| `tipo_bateria`, `voltaje_v`, `amperaje_ah` | Datos de la batería |
| `potencia_w`, `potencia_pico_w` | Nominal o de salida, y de pico. En un kit, la del inversor |
| `capacidad_wh`, `capacidad_origen` | Capacidad, y si es `declarada` o `calculada V x Ah` |
| `cantidad_paneles`, `potencia_total_paneles_w` | Solo kits |
| `usd_por_w`, `usd_por_wh` | Precio por vatio y por vatio-hora |
| `estado`, `tiene_garantia`, `garantia_meses` | Nuevo o usado, y garantía |
| `instalacion`, `envio` | `incluida`, `ofrecida` (se puede contratar) o `no incluida`; y `gratis` o `disponible`. "Gratis" suele valer solo para algunas zonas |
| `descripcion_leida`, `descripcion` | Si se abrió el anuncio, y su texto (solo en el JSON) |
| `veces_publicado`, `vistas`, `origen` | Anuncios agrupados, vistas, y cómo se encontró |

Un dato que el anuncio no trae queda vacío (`null`). **Nunca se inventa.**

**Privacidad:** no se guardan nombres ni teléfonos de vendedores. Los teléfonos y correos escritos en
títulos y descripciones se sustituyen por `[teléfono]` y `[correo]`. Es automático: la comprobación final
no halló ninguno, pero un número escrito de forma rara podría quedar. Revísalo si publicas textos.

## Limitaciones conocidas

- **Los campos salen del texto que escribe cada vendedor, con reglas automáticas, y hay errores.**
  Se comprobaron a mano 40 anuncios abiertos al azar, separados por categoría, comparando los campos con
  el texto del anuncio. 9 de los 40 tenían al menos un dato mal. Por campo: categoría 3 mal, potencia o
  capacidad 2, potencia pico 1, marca 1, modelo 1, garantía 1, precio 0. Además, 6 anuncios tenían vacío un
  dato que sí estaba en el texto (potencia, pico o envío). Después se corrigieron varios de estos fallos,
  pero no se volvió a medir. Son pocos anuncios y los revisó
  la misma herramienta que hizo las reglas, así que es **una orientación, no una tasa exacta**, y solo
  vale para los abiertos. En los demás únicamente se lee el título. **Comprueba los casos que vayas a citar.**
- **Los errores de categoría vienen sobre todo de títulos genéricos:** "Inversor infinisolar" puede ser
  un inversor con batería, que debería ser un kit, y cuesta mucho más que un inversor solo.
- **Anuncios con varios productos:** un anuncio puede listar varios productos con un solo precio. El
  precio y la potencia pueden no corresponder al mismo equipo.
- **Valores atípicos:** revisa los extremos antes de usarlos. Por ejemplo, hay estaciones anunciadas con
  14 400 W o 18 000 W, cifras escritas tal cual por el vendedor.
- **"Kit" es amplio:** incluye sistemas con paneles, inversor con batería ("6 con 15") y estación con
  panel. Usa `subcategoria` para no comparar cosas distintas.
- **Vendedores que escriben "15 kW" para una batería:** se interpreta como 15 kWh. Un valor de 1 000 o más
  en "k" se toma como W o Wh ("15350 kW" son 15 350 Wh; "4000 kW" son 4 000 W). Más de 200 kWh queda vacío.
- **Garantías de 3 años o más:** se dejan vacías, porque casi siempre son del fabricante del panel o la
  batería, no lo que ofrece quien vende. La marca se toma del título o de un "Marca:" explícito.
- **Paneles con varios tamaños en el título:** se toma la primera potencia.
- **"Planta":** se usa tanto para estaciones como para plantas de gasolina. Las que no nombran una
  marca o señal de batería se descartan, así que pueden faltar algunas estaciones.
- **Anuncios sin precio:** el recorrido principal filtra por precio, así que solo aparecen los que
  hallaron las búsquedas de texto. Están poco representados.
- **Solo Revolico.** Este paquete no incluye otras fuentes.

## Cómo se obtuvieron

1. Se recorre la subcategoría *Plantas y Estaciones de Energía* de La Habana, ordenada por fecha, hasta
   salir de los 30 días. Revolico deja de dar páginas nuevas a cierta profundidad, así que el listado se
   parte por tramos de precio para poder leerlo entero. El filtro de moneda convierte precios, por lo
   que con recorrer en USD se ven también los anuncios en otras monedas.
2. Búsquedas de texto recogen lo publicado fuera de esa subcategoría, sobre todo baterías. También sirven
   de comprobación: 12 957 de los 14 298 resultados útiles (90,6 %) ya estaban en el recorrido por precio,
   contando un anuncio varias veces si salió en varias búsquedas.
3. Cada título se clasifica, se descartan accesorios y otros productos, y se agrupan los repetidos.
4. Se abre la muestra de anuncios para leer las descripciones. Ninguno estaba marcado como vendido.

## Volver a ejecutarlo

Solo hace falta Python 3.8 o más nuevo. No hay que instalar nada.

```
python scraper_revolico.py                 corrida completa, se puede interrumpir y reanudar
python scraper_revolico.py --solo-extraer  rehace el JSON y el CSV sin internet (necesita la carpeta cache)
python scraper_revolico.py --prueba        corrida corta para comprobar que funciona
python scraper_revolico.py --depurar       guarda las páginas en la carpeta depuracion
```

Los ajustes están al inicio del archivo: `DIAS_MAXIMOS`, `PAUSA`, `MUESTRA_POR_CATEGORIA` y `TASAS_A_USD`.

**Costo:** el listado son unas 1 000 páginas (unos 60 MB y media hora). La muestra añade unos 40 MB y
hora y media. No conviene hacerlo con internet caro.

**Cloudflare:** el script no esquiva ninguna verificación. Lee las páginas sin navegador, y así Revolico
respondió sin verificación desde la computadora donde se ejecutó, fuera de Cuba. **Desde Cuba no se ha
probado y puede ser distinto.** Si aparece la verificación, el script se detiene, guarda lo leído con
`"incompleto": true`, y al ejecutarlo de nuevo continúa donde se quedó.
