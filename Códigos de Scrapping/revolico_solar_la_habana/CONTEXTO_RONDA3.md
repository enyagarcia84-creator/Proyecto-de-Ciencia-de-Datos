# Contexto de la ronda 3 (texto de Enya)

## Prompt pedido
Crea un prompt para opencode que me cree un código de scraping en Revolico que incluya rol, tarea concreta y medible, contexto, restricciones y formato de salida.

- **Rol:** analista de datos.
- **Tarea:** scraping con Python de anuncios en La Habana, Cuba, en Revolico. Variables: precio, tipo de batería, moneda del precio, potencia en watts (W), marca y modelo.
- **Contexto:** https://www.revolico.com/search?q=Paneles+solares&province=la-habana
- **Restricciones:** solo esa página y últimos 30 días. No todos los anuncios incluirán estos datos: guardar los que se encuentren y dejar vacíos los demás. Que sea capaz de saltarse Cloudflare.
- **Formato de salida:** JSON.

"El lío es que el scrapping en dónde tengo que conseguir este gran volumen de datos. No lo puedo hacer en mi computadora."
"Ve a ver si me puedes hacer el código de scrapping para revolico, y para facebook."

Categorías: paneles solares; estaciones portátiles de energía (como EcoFlow); baterías (de paneles); inversores (de paneles); kits solares.

## La investigación
**Título:** ¿Hasta dónde llega el dinero de un cubano en el mercado solar de La Habana?

**Pregunta:** ¿Qué equipos y sistemas solares anunciados en La Habana ofrecen la mejor relación entre precio y prestaciones energéticas, y cómo varían las alternativas disponibles según el presupuesto del comprador durante el período estudiado? (30 días)

**Objetivo general:** analizar la oferta de productos y sistemas solares anunciados en La Habana durante un período determinado, comparando precios, características energéticas y condiciones comerciales para identificar las alternativas según distintos presupuestos.

**Objetivos específicos:** recopilar anuncios de paneles, estaciones portátiles, baterías, inversores y sistemas completos; organizar y limpiar en una base uniforme; comparar precios, potencias, capacidades y prestaciones entre categorías similares; identificar alternativas por presupuesto; comunicar con 7-8 gráficos y una historia.

## Gráficos previstos
1. ¿Qué se vende? Distribución de anuncios por categoría.
2. ¿Cuánto cuesta entrar? Distribución de precios por categoría (medianas y rangos).
3. ¿Qué potencia obtenemos por nuestro dinero? Precio vs. potencia nominal de paneles.
4. ¿Cuánta energía puedo almacenar? Precio vs. capacidad en Wh de baterías y estaciones.
5. ¿Qué prestaciones ofrece cada categoría? Medianas de precio por subcategoría.
6. ¿Qué incluye lo que compro? Componentes, instalación, envío y estado.
7. Cantidad de alternativas por tramo de presupuesto y categoría.
8. Precio vs. potencia o capacidad por tipo de producto: opciones destacadas, con garantía, estado y componentes.

## Otras fuentes de Enya
30 personas responden un formulario (paneles, baterías, estaciones, inversores, kits; más fecha, lugar y garantía) e instituciones en proceso; Enya los añade después.
