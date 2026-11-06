"""
Scraper de anuncios de Revolico (La Habana, últimos 30 días).

Productos disponibles:
    estaciones  -> estaciones de energía portátiles (EcoFlow, Bluetti, ...)
    paneles     -> paneles solares
    inversores  -> inversores para paneles solares
    baterias    -> baterías para almacenar energía solar

Uso:
    python scraper_revolico.py estaciones
    python scraper_revolico.py            (muestra un menú para elegir)

Requisitos:
    - Google Chrome instalado
    - pip install playwright        (NO hace falta "playwright install")

Resultado: un archivo JSON en la carpeta "resultados".
"""

import json
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote_plus, urljoin

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

URL_BASE = "https://www.revolico.com"
PROVINCIA = "la-habana"        # filtro de provincia en la dirección de búsqueda
PROVINCIA_ID = "1"             # identificador de La Habana en los datos de Revolico
DIAS_MAXIMOS = 30            # solo anuncios de los últimos 30 días
PAGINAS_POR_BUSQUEDA = 3     # páginas de resultados por búsqueda (100 anuncios cada una)
PAUSA_ENTRE_PAGINAS = 2.0    # segundos de espera entre páginas (no saturar el sitio)
CARPETA_RESULTADOS = Path(__file__).parent / "resultados"
CARPETA_PERFIL = Path(__file__).parent / ".perfil_chrome"

PRODUCTOS = {
    "estaciones": {
        "nombre": "Estaciones de energía portátiles",
        "busquedas": ["ecoflow", "estacion de energia", "estacion electrica portatil",
                      "power station", "bluetti", "jackery"],
        # el título o la descripción debe contener al menos una de estas palabras
        "palabras_clave": ["ecoflow", "estacion", "estación", "power station", "bluetti",
                           "jackery", "anker solix", "planta portatil", "planta portátil"],
        "excluir": ["mochila", "funda", "solo cable"],
        "marcas": ["EcoFlow", "Bluetti", "Jackery", "Anker", "Goal Zero", "Allpowers",
                   "Oukitel", "Fossibot", "Growatt", "Pecron", "Zendure", "DJI", "Vtoman",
                   "Ugreen"],
    },
    "paneles": {
        "nombre": "Paneles solares",
        "busquedas": ["panel solar", "paneles solares", "placa solar"],
        "palabras_clave": ["panel solar", "paneles solares", "panel fotovoltaico",
                           "placa solar", "placas solares", "modulo solar", "módulo solar"],
        "excluir": ["lampara", "lámpara", "farol", "linterna", "reflector"],
        "marcas": ["Jinko", "JA Solar", "Longi", "Trina", "Canadian Solar", "Risen",
                   "EcoFlow", "Bluetti", "Jackery", "Renogy", "Huawei", "Sunpower",
                   "Astronergy", "DAH Solar", "Felicity", "Growatt"],
    },
    "inversores": {
        "nombre": "Inversores (para paneles solares)",
        "busquedas": ["inversor solar", "inversor hibrido", "inversor", "inverter"],
        "palabras_clave": ["inversor", "inverter"],
        "excluir": ["aire acondicionado", "split", "refrigerador", "nevera", "lavadora"],
        "marcas": ["Growatt", "Deye", "Must", "Felicity", "Victron", "Huawei", "Voltronic",
                   "Luxpower", "SRNE", "Sungrow", "Goodwe", "Solis", "Epever", "PowMr",
                   "Easun", "Anern", "Kstar", "Sako", "Mecer", "Fronius", "Schneider"],
    },
    "baterias": {
        "nombre": "Baterías para energía solar",
        "busquedas": ["bateria litio", "bateria lifepo4", "bateria solar",
                      "banco de baterias", "bateria de gel", "bateria ciclo profundo"],
        "palabras_clave": ["bateria", "batería", "baterias", "baterías", "lifepo4",
                           "banco de baterias"],
        "excluir": ["laptop", "celular", "telefono", "teléfono", "moto", "bicicleta",
                    "auto ", "carro", "control remoto", "reloj", "iphone", "samsung"],
        "marcas": ["Pylontech", "Felicity", "Growatt", "Deye", "Dyness", "BYD", "Huawei",
                   "Ritar", "Narada", "Vision", "Trojan", "Victron", "SRNE", "Must",
                   "Daly", "Seplos", "EVE", "CATL", "Basen"],
    },
}

# ---------------------------------------------------------------------------
# Extracción de datos a partir del texto del anuncio
# ---------------------------------------------------------------------------

NUMERO = r"(\d{1,3}(?:[.,\s]\d{3})+|\d+(?:[.,]\d+)?)"

MONEDAS = [
    ("USD", r"usd|u\.s\.d|d[oó]lares?|dolar|\bus\$"),
    ("MLC", r"\bmlc\b"),
    ("EUR", r"eur|euros?|€"),
    ("CUP", r"cup|pesos?(?:\s+cubanos?)?|\bmn\b|moneda nacional"),
]

TIPOS_BATERIA = [
    ("LiFePO4", r"lifepo4|lfp|litio[\s-]*hierro[\s-]*fosfato|fosfato de hierro"),
    ("Gel", r"\bgel\b"),
    ("AGM", r"\bagm\b"),
    ("Plomo-ácido", r"plomo|[aá]cido|lead[\s-]*acid"),
    ("NMC", r"\bnmc\b|\bncm\b"),
    ("Ion de litio", r"litio|lithium|li[\s-]?ion"),
]


def a_numero(texto):
    """Convierte '1,200' / '1.200' / '1 200' / '2,5' a número."""
    t = texto.strip().replace(" ", "")
    if re.fullmatch(r"\d{1,3}([.,]\d{3})+", t):
        return float(re.sub(r"[.,]", "", t))
    return float(t.replace(",", "."))


def limpiar_numero(valor):
    return int(valor) if valor == int(valor) else valor


def detectar_moneda(texto):
    texto = texto.lower()
    for codigo, patron in MONEDAS:
        if re.search(patron, texto):
            return codigo
    return None


def extraer_precio(texto_precio, texto_completo):
    """Devuelve (precio, moneda). Primero usa el precio oficial del anuncio,
    si no existe busca un precio dentro del texto."""
    if texto_precio:
        m = re.search(NUMERO, texto_precio)
        if m:
            return limpiar_numero(a_numero(m.group(1))), detectar_moneda(texto_precio)

    # Busca algo como "350 usd", "$ 350", "precio: 350"
    patron_moneda = "|".join(p for _, p in MONEDAS)
    texto = texto_completo.lower()
    candidatos = [
        rf"{NUMERO}\s*(?:\$\s*)?({patron_moneda})",
        rf"(?:{patron_moneda})\s*\$?\s*{NUMERO}",
        rf"\$\s*{NUMERO}",
        rf"precio\s*:?\s*\$?\s*{NUMERO}",
    ]
    for patron in candidatos:
        m = re.search(patron, texto)
        if m:
            numero = next(g for g in m.groups() if g and re.match(r"\d", g))
            return limpiar_numero(a_numero(numero)), detectar_moneda(m.group(0))
    return None, None


def extraer_tipo_bateria(texto):
    texto = texto.lower()
    for nombre, patron in TIPOS_BATERIA:
        if re.search(patron, texto):
            return nombre
    return None


def extraer_potencia_w(texto):
    """Potencia en watts. Ignora Wh (capacidad), que no es potencia.
    Si el anuncio indica la potencia de salida se usa esa; si no, la mayor
    que no sea de pico, de entrada o de carga."""
    salida, normales, otras = [], [], []
    for linea in texto.lower().splitlines():
        for m in re.finditer(rf"{NUMERO}\s*(kw|w|watts?|vatios?)(?![a-záéíóúñ])", linea):
            valor = a_numero(m.group(1))
            if m.group(2) == "kw":
                valor *= 1000
            if not 1 <= valor <= 100000:
                continue
            if re.search(r"salida|output|nominal|continu", linea):
                salida.append(valor)
            elif re.search(r"pico|peak|surge|entrada|input|carga|cargador", linea):
                otras.append(valor)
            else:
                normales.append(valor)
    valores = salida or normales or otras
    return limpiar_numero(max(valores)) if valores else None


def extraer_marca_modelo(titulo, texto, marcas):
    """Busca una marca conocida y toma las palabras siguientes como modelo."""
    marca_encontrada = None
    for marca in marcas:
        patron = re.escape(marca).replace(r"\ ", r"\s*")
        for fuente in (titulo, texto):
            for m in re.finditer(rf"\b{patron}\b[ \t]*([A-Za-z0-9][\w\-+./]*(?:[ \t]+[A-Za-z0-9][\w\-+./]*){{0,2}})?",
                                 fuente, re.IGNORECASE):
                marca_encontrada = marca_encontrada or marca
                modelo = (m.group(1) or "").strip()
                # corta el modelo donde empiezan palabras comunes que no son modelo
                modelo = re.split(r"(?:^|\s+)(?:de|del|con|en|nuevo|nueva|a|para|y|precio|usd|cup|mlc|"
                                  r"vendo|se|esta|está|buen|como)\b",
                                  modelo, flags=re.IGNORECASE)[0].strip()
                # quita del final medidas como "3600W" o "2048Wh", que no son parte del modelo
                modelo = re.sub(r"(?:^|[ \t]+)[\d.,]+[ \t]*(?:k?wh?|v|ah|mah)$", "", modelo,
                                flags=re.IGNORECASE).strip()
                if modelo:
                    return marca, modelo
    # Se prefiere una marca con modelo (muchos escriben "ecoflow" para cualquier estación);
    # si ninguna tiene modelo, se devuelve la primera marca encontrada
    return marca_encontrada, None


def es_relevante(titulo, texto, producto):
    contenido = f"{titulo} {texto}".lower()
    if not any(p in contenido for p in producto["palabras_clave"]):
        return False
    return not any(p in titulo.lower() for p in producto["excluir"])


def leer_fecha_iso(texto):
    """Convierte '2026-10-21T20:35:27.287Z' a una fecha de la hora local."""
    if not texto:
        return None
    try:
        return datetime.fromisoformat(texto.replace("Z", "+00:00")).astimezone().replace(tzinfo=None)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Navegación con Playwright
# ---------------------------------------------------------------------------

def esperar_verificacion(page):
    """Si aparece la verificación de seguridad (Cloudflare), espera a que
    la persona la resuelva a mano en la ventana de Chrome."""
    def hay_verificacion():
        titulo = page.title().lower()
        return any(p in titulo for p in ("just a moment", "un momento", "attention required",
                                         "verific"))
    if hay_verificacion():
        print("\n  >> Revolico muestra una verificación de seguridad.")
        print("  >> Resuélvela en la ventana de Chrome (marca la casilla si aparece).")
        input("  >> Cuando veas la página normal de Revolico, presiona Enter aquí... ")
        page.wait_for_load_state("domcontentloaded")


def abrir(page, url):
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    esperar_verificacion(page)


def datos_de_pagina(page):
    """Revolico incluye en cada página los datos de los anuncios en formato JSON
    (dentro de <script id="__NEXT_DATA__">). Devuelve esos datos o {} si no están."""
    try:
        contenido = page.locator("script#__NEXT_DATA__").text_content(timeout=15000)
        datos = json.loads(contenido)
        return datos["props"]["pageProps"].get("__APOLLO_STATE__", {})
    except (PlaywrightTimeout, PlaywrightError, ValueError, KeyError, TypeError):
        return {}


def nombre_municipio(datos, municipio_id):
    municipio = datos.get(f"MunicipalityType:{municipio_id}") or {}
    return municipio.get("name")


def buscar_pagina(page, termino, numero_pagina):
    """Abre una página de resultados de búsqueda (ya filtrada por La Habana).
    Devuelve (lista de anuncios, datos de la página, hay_pagina_siguiente)."""
    url = f"{URL_BASE}/search?q={quote_plus(termino)}&province={PROVINCIA}&page={numero_pagina}"
    abrir(page, url)
    datos = datos_de_pagina(page)
    consultas = datos.get("ROOT_QUERY", {})
    anuncios, hay_siguiente = [], False
    for clave, valor in consultas.items():
        # "adsPerPage(...)" son los resultados normales y "promotedAds(...)" los destacados
        if not clave.startswith(("adsPerPage(", "promotedAds(")) or not isinstance(valor, dict):
            continue
        for borde in valor.get("edges", []):
            anuncio = datos.get(borde.get("node", {}).get("__ref", ""))
            if anuncio:
                anuncios.append(anuncio)
        if clave.startswith("adsPerPage("):
            hay_siguiente = valor.get("pageInfo", {}).get("hasNextPage", False)
    return anuncios, datos, hay_siguiente


def texto_de(page, selectores):
    for selector in selectores:
        elemento = page.locator(selector).first
        try:
            if elemento.count() > 0:
                texto = elemento.inner_text(timeout=3000).strip()
                if texto:
                    return texto
        except (PlaywrightTimeout, PlaywrightError):
            continue
    return ""


def leer_anuncio(page, candidato, producto):
    """Abre un anuncio y extrae sus datos. Devuelve (datos, None) o (None, motivo)."""
    abrir(page, candidato["url"])
    datos = datos_de_pagina(page)
    anuncio = datos.get(f"AdType:{candidato['id']}") or {}
    titulo = anuncio.get("title") or candidato["titulo"] or texto_de(page, ["h1"])
    descripcion = anuncio.get("description") or texto_de(page, ["main", "body"])

    if anuncio.get("isSold"):
        return None, "ya está vendido"
    if not es_relevante(titulo, descripcion, producto):
        return None, "no es del producto buscado"

    texto = f"{titulo}\n{descripcion}"
    precio, moneda = candidato["precio"], candidato["moneda"]
    if precio is None:
        precio, moneda = extraer_precio(None, texto)
    marca, modelo = extraer_marca_modelo(titulo, descripcion, producto["marcas"])
    return {
        "titulo": titulo or None,
        "url": candidato["url"],
        "fecha_publicacion": candidato["fecha"].strftime("%Y-%m-%d") if candidato["fecha"] else None,
        "ubicacion": candidato["ubicacion"],
        "precio": precio,
        "moneda": moneda,
        "tipo_bateria": extraer_tipo_bateria(texto),
        "potencia_w": extraer_potencia_w(texto),
        "marca": marca,
        "modelo": modelo,
    }, None


def ejecutar(clave, depurar=False):
    producto = PRODUCTOS[clave]
    limite = datetime.now() - timedelta(days=DIAS_MAXIMOS)
    print(f"\n=== Buscando: {producto['nombre']} (La Habana, últimos {DIAS_MAXIMOS} días) ===")

    with sync_playwright() as p:
        try:
            # channel="chrome" usa el Google Chrome instalado en la computadora
            navegador = p.chromium.launch_persistent_context(
                str(CARPETA_PERFIL), channel="chrome", headless=False, locale="es-ES",
            )
        except PlaywrightError:
            try:
                # Si no hay Chrome, se intenta con el Chromium de Playwright
                # (requiere haber ejecutado antes: playwright install chromium)
                navegador = p.chromium.launch_persistent_context(
                    str(CARPETA_PERFIL), headless=False, locale="es-ES",
                )
            except PlaywrightError as error:
                print("\nNo se pudo abrir Google Chrome. ¿Está instalado?")
                print(f"Detalle: {error}")
                sys.exit(1)
        page = navegador.pages[0] if navegador.pages else navegador.new_page()

        # 1) Revisar las páginas de resultados y quedarse con los anuncios que,
        #    por su título y fecha, parecen del producto y de los últimos 30 días
        candidatos = {}
        for termino in producto["busquedas"]:
            print(f"\nBuscando '{termino}' en La Habana...")
            for numero_pagina in range(1, PAGINAS_POR_BUSQUEDA + 1):
                try:
                    anuncios, datos, hay_siguiente = buscar_pagina(page, termino, numero_pagina)
                except (PlaywrightTimeout, PlaywrightError) as error:
                    print(f"  No se pudo abrir la página {numero_pagina}: {error}")
                    break
                if depurar and numero_pagina == 1:
                    guardar_html(page, f"busqueda_{termino.replace(' ', '_')}")
                nuevos = 0
                for anuncio in anuncios:
                    if anuncio.get("id") in candidatos or anuncio.get("provinceId") != PROVINCIA_ID:
                        continue
                    fecha = leer_fecha_iso(anuncio.get("updatedOnToOrder"))
                    if fecha and fecha < limite:
                        continue
                    if not es_relevante(anuncio.get("title", ""), "", producto):
                        continue
                    municipio = nombre_municipio(datos, anuncio.get("municipalityId"))
                    candidatos[anuncio["id"]] = {
                        "id": anuncio["id"],
                        "url": urljoin(URL_BASE, anuncio.get("permalink", f"/item/{anuncio['id']}")),
                        "titulo": anuncio.get("title"),
                        "precio": anuncio.get("price"),
                        "moneda": anuncio.get("currency"),
                        "fecha": fecha,
                        "ubicacion": f"{municipio}, La Habana" if municipio else "La Habana",
                    }
                    nuevos += 1
                print(f"  Página {numero_pagina}: {len(anuncios)} anuncios, {nuevos} útiles")
                # Los resultados van por relevancia: si una página no trae nada útil, se para
                if not anuncios or nuevos == 0 or not hay_siguiente:
                    break
                time.sleep(PAUSA_ENTRE_PAGINAS)

        print(f"\nTotal de anuncios a revisar: {len(candidatos)}")

        # 2) Abrir cada anuncio para leer la descripción y sacar los datos
        anuncios = []
        for i, candidato in enumerate(candidatos.values(), 1):
            print(f"[{i}/{len(candidatos)}] {candidato['url']}")
            try:
                datos, motivo = leer_anuncio(page, candidato, producto)
                if depurar and i <= 3:
                    guardar_html(page, f"anuncio_{i}")
            except (PlaywrightTimeout, PlaywrightError) as error:
                print(f"    Error al leer el anuncio, se omite: {error}")
                continue
            if datos:
                anuncios.append(datos)
                print(f"    OK -> {datos['precio']} {datos['moneda']} | {datos['marca']} {datos['modelo']}"
                      f" | {datos['potencia_w']} W | {datos['tipo_bateria']}")
            else:
                print(f"    Descartado: {motivo}")
            time.sleep(PAUSA_ENTRE_PAGINAS)

        navegador.close()

    # 3) Guardar el resultado en JSON
    CARPETA_RESULTADOS.mkdir(exist_ok=True)
    archivo = CARPETA_RESULTADOS / f"{clave}_{datetime.now():%Y-%m-%d_%H%M}.json"
    resultado = {
        "producto": producto["nombre"],
        "fuente": URL_BASE,
        "ubicacion": "La Habana, Cuba",
        "fecha_consulta": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "periodo": f"últimos {DIAS_MAXIMOS} días",
        "total_anuncios": len(anuncios),
        "anuncios": anuncios,
    }
    archivo.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nListo. {len(anuncios)} anuncios guardados en: {archivo}")


def guardar_html(page, nombre):
    """Modo --depurar: guarda la página para revisar por qué algo no funciona."""
    carpeta = Path(__file__).parent / "depuracion"
    carpeta.mkdir(exist_ok=True)
    (carpeta / f"{nombre}.html").write_text(page.content(), encoding="utf-8")


def elegir_producto():
    claves = list(PRODUCTOS)
    print("¿Qué producto quieres buscar?")
    for i, clave in enumerate(claves, 1):
        print(f"  {i}. {PRODUCTOS[clave]['nombre']}")
    while True:
        opcion = input("Escribe el número y presiona Enter: ").strip()
        if opcion.isdigit() and 1 <= int(opcion) <= len(claves):
            return claves[int(opcion) - 1]


if __name__ == "__main__":
    depurar = "--depurar" in sys.argv
    argumentos = [a for a in sys.argv[1:] if a != "--depurar"]
    if argumentos and argumentos[0] in PRODUCTOS:
        ejecutar(argumentos[0], depurar)
    elif argumentos:
        print(f"Producto desconocido. Opciones: {', '.join(PRODUCTOS)}")
    else:
        ejecutar(elegir_producto(), depurar)
