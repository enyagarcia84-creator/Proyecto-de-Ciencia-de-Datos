# Ronda 4: base unificada, 8 gráficos y artículo

*¿Hasta dónde llega el dinero de un cubano en el mercado solar de La Habana?*

## Qué hay aquí

| Archivo | Para qué sirve |
|---|---|
| `articulo.html` | **El artículo terminado.** Se abre con doble clic en cualquier navegador y está pensado primero para el teléfono. Usa la tipografía Inter (de Google Fonts) y la paleta verde y marfil. Sin internet usa la letra del sistema. |
| `graficos/g1.html` … `g8.html` | Los 8 gráficos, hechos en HTML y CSS para que el texto se lea bien en cualquier pantalla. Necesitan `estilos_graficos.css`. |
| `base_unificada.csv` / `.json` | Las cuatro fuentes en una sola tabla. El CSV se abre en Excel. |
| `cifras.json` | Todos los números que cita el artículo. |
| `unificar.py`, `graficos.py`, `articulo.py` | El código. Solo hace falta Python 3 y `numpy`. |
| `articulo_plantilla.html` | El texto del artículo, con marcadores `{{…}}` donde van las cifras y `{{GRAFICO N \| título \| explicación}}` donde va cada gráfico. |

Para rehacerlo todo:

```
python unificar.py
python graficos.py
python articulo.py
```

`unificar.py` necesita la carpeta del proyecto, con `resources/` y `resultados/` al lado. Con solo el zip se puede rehacer desde `python graficos.py`.

`articulo.py` se detiene si el texto cita una cifra que no existe.

## Los 8 gráficos (versión 2026-11-05, enfoque en resultados)

1. **Cantidad de anuncios por tipo de equipo.** Barras horizontales.
2. **Precio típico (mediana) por tipo de equipo.** Barras verticales.
3. **Del más barato al más caro.** Puntos con el rango de precios de cada tipo, del 5 % al 95 %, en escala logarítmica.
4. **Capacidad típica en Wh según el presupuesto.** Barras horizontales: estaciones portátiles y baterías de litio.
5. **Precio de 1 kWh guardado y de 1 kW de potencia.** Barras.
6. **Garantía por tipo de equipo.** Barras apiladas: ofrece, no ofrece, no lo especifica. Solo cuenta los anuncios cuya descripción completa se leyó.
7. **Instalación, envío y componentes.** Barras agrupadas.
8. **Ranking de energía por cada 100 USD.** Estaciones y baterías de litio por separado. Cada modelo se agrupa por marca y capacidad y necesita al menos 5 anuncios.

## Pendientes

Ninguno: el artículo ya no tiene recuadro [FALTA].

Resuelto por la autora (2026-11-05):
- **Recorte de Revolico:** la base de trabajo (18 717 de 38 051 ofertas) se limpió a mano. El artículo lo dice junto al gráfico 1 y en la nota metodológica.
- **Portada:** el artículo queda sin imagen.
- **Entrevistas:** no se publican testimonios. Solo se dice que hubo entrevistas y se usan sus datos de compra. Se hicieron en octubre de 2026, sobre compras lo más cercanas posible a ese mes.
- **Tasa:** 920 CUP por USD, de elTOQUE, octubre de 2026.
- **Instituciones:** se excluyen 3 registros de 33 (`EXCLUIR_INSTITUCIONES` en `unificar.py`):
  - el 20, sospechoso: un kit Renogy de 400 W clasificado como inversor de 3 kW;
  - el 29, un sistema COPEXTEL de 1 kW a 55 000 CUP;
  - el 4, un panel de UNE/COPEXTEL de 800 W a 75 200 CUP.

## Decisiones de análisis

- **Una sola base.** Cada registro conserva su `fuente` (Revolico, El Yerro Menú, Entrevistas, Instituciones) y su `tipo_fuente` (anuncio, entrevista, institución). Los conteos y las distribuciones usan solo anuncios. Las entrevistas (precios pagados) y las instituciones aparecen en los gráficos con símbolos propios, sin sumarse.
- **USD.** Se recalculó desde el precio y la moneda originales: USD tal cual y CUP / 920. Los 24 registros de entrevistas que tenían el USD vacío quedaron completos.
- **Precio dudoso.** 119 anuncios quedan fuera de los cálculos de precio: CUP demasiado bajos para el producto o alertas del raspador.
- **Comparabilidad.**
  - Paneles: solo de 100 a 800 W y como máximo 3 USD por W.
  - Baterías: solo de litio, según el tipo o el título. Las de plomo, gel o AGM no se comparan con ellas.
  - Inversores: en los gráficos 5 y 8, solo los híbridos o con MPPT según el título. Los inversores simples de 12 V cumplen otra función.
  - Estaciones y baterías se comparan por separado.
- **Gráfico 6.** Solo usa los 1 258 anuncios cuya descripción completa se leyó. «No lo dice» es una categoría propia y no significa «no tiene».
- **Gráfico 7.** Tramos de hasta 300, 300–700, 700–1 500, 1 500–3 000 y más de 3 000 USD. Son cifras redondas cercanas a los percentiles 10, 40, 75 y 95 de los precios.
- **Gráfico 8.** Destaca el modelo con el menor precio mediano por W o Wh en cada tramo de tamaño. Exige marca conocida y al menos 5 anuncios. No elige «el más barato».
- **Unidades ambiguas.** En 5 entrevistas el formulario dice «Capacidad en W»; ese valor no se usa como capacidad y queda anotado en `notas`.
- **Duplicados.** Se marcan, no se borran. Hay 3 477 registros que la auditoría de Enya marca como posible repetición (mismo título y precio) y 470 que coinciden entre Revolico y El Yerro.

## Advertencia de privacidad

Algunos títulos y descripciones de Revolico contienen teléfonos de vendedores. Por decisión del equipo no se borraron de los datos. El artículo no los muestra: las etiquetas usan marca, modelo y prestaciones. Hay que tenerlo en cuenta antes de publicar `base_unificada.csv` / `.json`.
