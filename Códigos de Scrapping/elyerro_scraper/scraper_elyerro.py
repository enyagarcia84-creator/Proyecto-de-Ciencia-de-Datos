"""
Scraper de El Yerro Menú (https://elyerromenu.com/l/la-habana-cuba)
Busca productos de energía en tiendas de La Habana actualizados en los últimos 30 días.

Productos disponibles:
    estaciones  -> estaciones de energía portátiles (EcoFlow, Bluetti, ...)
    paneles     -> paneles solares
    inversores  -> inversores para paneles solares
    baterias    -> baterías para almacenar energía solar

Uso:
    python scraper_elyerro.py estaciones
    python scraper_elyerro.py              (muestra un menú para elegir)
    python scraper_elyerro.py estaciones --depurar   (guarda las páginas en "depuracion")

Requisitos:
    - Solo Python 3.8 o más nuevo. No hace falta instalar nada más
      (ni Chrome, ni Playwright, ni "pip install").

Resultado: un archivo JSON en la carpeta "resultados".
"""

import gzip
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

URL_BASE = "https://elyerromenu.com"
URL_FUENTE = "https://elyerromenu.com/l/la-habana-cuba"
UBICACION_ID = "62aa50bedd41e7e0b82829f8"  # identificador de "La Habana, Cuba" en El Yerro
DIAS_MAXIMOS = 30              # solo productos actualizados en los últimos 30 días
RESULTADOS_POR_BUSQUEDA = 100  # máximo de resultados que se revisan por cada término de búsqueda
USAR_BUSCADOR_RAPIDO = True    # usa el buscador interno del sitio (gasta mucho menos internet);
                               # si falla, el script usa solo las páginas normales del buscador
PAUSA_ENTRE_PAGINAS = 1.5      # segundos de espera entre página y página (no saturar el sitio)
TIEMPO_ESPERA = 60             # segundos máximos esperando una página (internet lento)
REINTENTOS = 2                 # reintentos si una página falla
CARPETA = Path(__file__).parent
CARPETA_RESULTADOS = CARPETA / "resultados"
CARPETA_DEPURACION = CARPETA / "depuracion"

# Palabras comunes que aparecen junto a la marca pero no son parte del modelo
PALABRAS_NO_MODELO = {
    "de", "del", "la", "el", "con", "en", "y", "a", "para", "por", "tipo", "nuevo", "nueva",
    "nuevos", "original", "oferta", "precio", "vendo", "venta", "se", "disponible", "marca",
    "modelo", "serie", "electrica", "portatil", "estacion", "energia", "solar", "panel",
    "paneles", "inversor", "hibrido", "bateria", "baterias", "litio", "lithium", "lifepo4",
    "usd", "cup", "mlc", "eur", "zelle", "clasica", "clasico", "garantia", "sellado",
    "sellada", "caja", "stock", "domicilio", "gratis", "envio", "incluido", "incluida",
    "mensajeria", "genera", "mas", "capacidad", "potencia", "voltaje", "bifacial",
    "monocristalino", "monofacial", "mono", "watt", "watts", "ideal", "inteligente", "smart",
    "bifasico", "fase", "dividida", "todo", "uno", "vpt",
}

# En "excluir" cada elemento es un patrón de texto (expresión regular) que se busca en
# el título ya en minúscula y sin tildes. Si aparece, el producto se descarta.
PRODUCTOS = {
    "estaciones": {
        "nombre": "Estaciones de energía portátiles",
        "busquedas": ["ecoflow", "estacion de energia", "power station", "bluetti", "jackery"],
        # el título debe contener al menos una de estas palabras (sin tildes, en minúscula)
        "palabras_clave": ["ecoflow", "estacion", "power station", "bluetti", "jackery",
                           "anker solix", "planta portatil", "planta electrica portatil"],
        # accesorios, combos y otras cosas que no son una estación
        "excluir": [r"cable", r"sarten", r"panel", r"bateria (extra|auxiliar|adicional)",
                    r"funda", r"bolso", r"mochila", r"cargador", r"adaptador", r"combo",
                    r"\bkit\b", r"smart extra", r"nevera", r"refrigerador",
                    r"aire acondicionado", r"estacion de juego", r"playstation"],
        "bateria_en_descripcion": True,
        "marcas": ["EcoFlow", "Bluetti", "Jackery", "Anker", "Goal Zero", "Allpowers",
                   "Oukitel", "Fossibot", "Growatt", "Pecron", "Zendure", "DJI", "Vtoman",
                   "Ugreen", "Dabbsson", "Headway", "Mango Power", "Oupes", "Sako", "Must",
                   "Humsienk", "Eco-Worthy"],
    },
    "paneles": {
        "nombre": "Paneles solares",
        "busquedas": ["panel solar", "paneles solares", "placa solar"],
        "palabras_clave": ["panel solar", "paneles solares", "panel fotovoltaico",
                           "placa solar", "placas solares", "modulo solar", "panel bifacial",
                           "panel monocristalino"],
        "excluir": [r"lampara", r"farol", r"linterna", r"reflector", r"luz solar", r"bombillo",
                    r"cable", r"soporte", r"\bbases?\b", r"estructura", r"conector", r"mc4",
                    r"inversor", r"bateria", r"combo", r"\bkit\b", r"estacion", r"ventilador",
                    r"cargador", r"controlador", r"regulador", r"calentador", r"bomba",
                    r"camara", r"foco", r"limpieza", r"instalacion"],
        # en paneles no aplican tipo de batería ni capacidad: solo se leen del título/ficha
        # (las descripciones hablan de las baterías que se pueden conectar)
        "bateria_en_descripcion": False,
        "marcas": ["Jinko", "JA Solar", "JASolar", "Longi", "Trina", "Canadian Solar", "Risen",
                   "EcoFlow", "Bluetti", "Jackery", "Renogy", "Huawei", "Sunpower",
                   "Astronergy", "DAH Solar", "Felicity", "Growatt", "Tongwei", "Znshine",
                   "Seraphim", "Sunova", "Leapton", "Boviet", "Runergy", "Solar Ever",
                   "Lvyuan", "Eco-Worthy", "Sako"],
    },
    "inversores": {
        "nombre": "Inversores (para paneles solares)",
        "busquedas": ["inversor solar", "inversor hibrido", "inversor", "inverter"],
        "palabras_clave": ["inversor", "inverter"],
        "excluir": [r"aire acondicionado", r"\bsplit\b", r"refrigerador", r"nevera", r"lavadora",
                    r"congelador", r"freezer", r"televisor", r"microondas", r"cable", r"combo",
                    r"\bkit\b", r"ventilador", r"climatizador", r"sold(ar|ador|adora)",
                    r"ducha", r"monomando", r"mezclador", r"grifo", r"planta electrica",
                    r"generador", r"silencioso", r"gasolina", r"dual ?fuel", r"generac",
                    r"^\W*bateria"],
        "bateria_en_descripcion": False,
        "marcas": ["Growatt", "Deye", "Must", "Felicity", "Victron", "Huawei", "Voltronic",
                   "Luxpower", "SRNE", "Sungrow", "Goodwe", "Solis", "Epever", "PowMr",
                   "Easun", "Anern", "Anenji", "Kstar", "Sako", "Mecer", "Fronius", "Schneider",
                   "Sumry", "Datouboss", "Datou Boss", "Hoymiles", "Sorotec", "Voltacon",
                   "InfiniSolar", "Sunpal", "Eco-Worthy", "WattCycle", "Humsienk", "Powland",
                   "SRGFTS"],
    },
    "baterias": {
        "nombre": "Baterías para energía solar",
        "busquedas": ["bateria litio", "bateria lifepo4", "bateria solar",
                      "banco de baterias", "bateria de gel", "bateria ciclo profundo"],
        "palabras_clave": ["bateria", "baterias", "lifepo4", "banco de baterias"],
        "excluir": [r"laptop", r"celular", r"telefono", r"\bmoto", r"bicicleta", r"carro",
                    r"\bauto\b", r"control remoto", r"reloj", r"iphone", r"samsung", r"xiaomi",
                    r"power ?bank", r"externa", r"\bpilas?\b", r"scooter", r"patineta",
                    r"triciclo", r"ecoflow", r"bluetti", r"jackery", r"\bextra\b", r"auxiliar",
                    r"combo", r"\bkit\b", r"cargador de bateria", r"multimetro", r"camara",
                    r"drone", r"taladro", r"\bled\b", r"lampara", r"\bfoco\b", r"linterna",
                    r"calentador", r"biberon", r"18650", r"\d\s*mah\b",
                    r"(?<![\d.])[1-9]([.,]\d+)?\s*ah\b",   # 1 a 9 Ah: baterías de herramientas
                    r"^\W*inversor", r"todo en uno", r"\b(2|dos) en (1|uno)\b",
                    r"estacion de energia"],
        "bateria_en_descripcion": True,
        "marcas": ["Pylontech", "Felicity", "Felicitysolar", "Growatt", "Deye", "Dyness", "BYD",
                   "Huawei", "Ritar", "Narada", "Vision", "Trojan", "Victron", "SRNE", "Must",
                   "Daly", "Seplos", "EVE", "CATL", "Basen", "Hubble", "Sako", "PowMr",
                   "Humsienk", "WattCycle", "Eco-Worthy", "Poeruni", "Dumfume", "Unizuki",
                   "HuanTai"],
    },
}

# ---------------------------------------------------------------------------
# Descarga de páginas
# ---------------------------------------------------------------------------

CABECERAS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "es-ES,es;q=0.9",
    "Accept-Encoding": "gzip",  # páginas comprimidas: gasta mucho menos internet
}


class SitioBloqueado(Exception):
    """El sitio rechazó las peticiones (verificación de seguridad o demasiadas visitas)."""


def descargar(url, acepta="text/html,application/xhtml+xml"):
    """Descarga una página y devuelve su texto. Reintenta si falla la conexión."""
    for intento in range(REINTENTOS + 1):
        try:
            peticion = urllib.request.Request(url, headers={**CABECERAS, "Accept": acepta})
            with urllib.request.urlopen(peticion, timeout=TIEMPO_ESPERA) as respuesta:
                datos = respuesta.read()
                if respuesta.headers.get("Content-Encoding") == "gzip":
                    datos = gzip.decompress(datos)
                texto = datos.decode("utf-8", errors="replace")
            if "<title>Just a moment" in texto or "cf-challenge" in texto:
                raise SitioBloqueado("El sitio muestra una verificación de seguridad.")
            return texto
        except urllib.error.HTTPError as error:
            if error.code in (403, 429):
                raise SitioBloqueado(f"El sitio respondió con el código {error.code}.")
            if error.code == 404 or intento == REINTENTOS:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if intento == REINTENTOS:
                raise
        time.sleep(5 * (intento + 1))  # espera un poco más antes de cada reintento


def datos_nuxt(html):
    """El Yerro incluye en cada página sus datos en formato JSON
    (dentro de <script id="__NUXT_DATA__">). Están guardados como una lista donde
    los valores apuntan a otras posiciones; esta función devuelve la lista y una
    función para "armar" cualquier valor completo."""
    m = re.search(r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        return [], None
    lista = json.loads(m.group(1))

    def armar(posicion, profundidad=0):
        valor = lista[posicion]
        if profundidad > 12:
            return None
        if isinstance(valor, list):
            if valor and valor[0] in ("ShallowReactive", "Reactive", "Ref", "ShallowRef"):
                return armar(valor[1], profundidad)
            if valor and valor[0] == "Set":
                return [armar(x, profundidad + 1) for x in valor[1:]]
            return [armar(x, profundidad + 1) for x in valor]
        if isinstance(valor, dict):
            return {k: armar(x, profundidad + 1) for k, x in valor.items()}
        return valor

    return lista, armar


def buscar_objeto(lista, armar, claves):
    """Devuelve el primer objeto de los datos que tenga todas las claves indicadas."""
    for i, valor in enumerate(lista):
        if isinstance(valor, dict) and all(c in valor for c in claves):
            return armar(i)
    return None


def guardar_html(nombre, html):
    """Modo --depurar: guarda la página para revisar por qué algo no funciona."""
    CARPETA_DEPURACION.mkdir(exist_ok=True)
    nombre = re.sub(r"[^\w\-]+", "_", nombre)[:80]
    (CARPETA_DEPURACION / f"{nombre}.html").write_text(html, encoding="utf-8")


# ---------------------------------------------------------------------------
# Extracción de datos a partir del texto del producto
# ---------------------------------------------------------------------------

NUMERO = r"(\d{1,3}(?:[.,\u00a0 ]\d{3})+(?![\d])|\d+(?:[.,]\d+)?)"

MONEDAS = [
    ("USD", r"\busd\b|u\.s\.d|d[oó]lares?|\bdolar\b|\bus\$"),
    ("MLC", r"\bmlc\b"),
    ("ZELLE", r"\bzelle\b"),
    ("EUR", r"\beur\b|\beuros?\b|€"),
    ("CUP", r"\bcup\b|\bpesos?\b|\bmn\b|moneda nacional"),
]

TIPOS_BATERIA = [
    ("LiFePO4", r"lifepo4|\blfp\b|litio[\s-]*hierro[\s-]*fosfato|fosfato de hierro"),
    ("Gel", r"\bgel\b"),
    ("AGM", r"\bagm\b"),
    ("Plomo-ácido", r"plomo|lead[\s-]*acid"),
    ("NMC", r"\bnmc\b|\bncm\b"),
    ("Ion de litio", r"litio|lithium|li[\s-]?ion"),
]


def normalizar(texto):
    """Pasa a minúsculas y quita tildes y símbolos especiales ('LiFePO₄' -> 'lifepo4')."""
    texto = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in texto if not unicodedata.combining(c)).lower()


def a_numero(texto):
    """Convierte '1,200' / '1.200' / '2,5' a número."""
    t = texto.strip().replace(" ", "").replace("\u00a0", "")
    if re.fullmatch(r"\d{1,3}([.,]\d{3})+", t):
        valor = float(re.sub(r"[.,]", "", t))
    else:
        valor = float(t.replace(",", "."))
    return int(valor) if valor == int(valor) else valor


def detectar_moneda(texto):
    texto = normalizar(texto)
    for codigo, patron in MONEDAS:
        if re.search(patron, texto):
            return codigo
    return None


def precio_en_texto(texto):
    """Busca un precio escrito en la descripción, como '2250 USD' o 'precio: 300 usd'."""
    texto = normalizar(texto)
    patron_moneda = "|".join(p for _, p in MONEDAS)
    for patron in (rf"{NUMERO}\s*\$?\s*(?:{patron_moneda})",
                   rf"(?:{patron_moneda})\s*\$?\s*{NUMERO}",
                   rf"precio\s*:?\s*\$?\s*{NUMERO}"):
        for m in re.finditer(patron, texto):
            # se ignora si el número es en realidad una medida (2250 W, 100 Ah...)
            despues = texto[m.end(1):m.end(1) + 4] if m.lastindex else ""
            if re.match(r"\s*(k?wh?|v|ah|mah|%)\b", despues):
                continue
            valor = a_numero(m.group(1))
            if valor > 0:
                return valor, detectar_moneda(m.group(0))
    return None, None


def tipo_bateria(texto):
    texto = normalizar(texto)
    for nombre, patron in TIPOS_BATERIA:
        if re.search(patron, texto):
            return nombre
    return None


def potencia_w(titulo, descripcion=""):
    """Potencia en watts. Ignora Wh (capacidad), que no es potencia.
    Orden de preferencia:
      1. la potencia de salida / nominal / continua que diga la descripción o el título
      2. la que aparece en el título (en paneles e inversores casi siempre es la correcta)
      3. la mayor de la descripción que no sea de pico, de entrada, de carga ni "en paralelo"
    """
    def clasificar(texto):
        salida, normales, otras = [], [], []
        for linea in normalizar(texto).splitlines():
            # cada línea se parte en trozos: "1800W (3600W pico)" -> "1800W " y "3600W pico"
            for trozo in re.split(r"[()/,;|]|(?=\bhasta\b)", linea):
                for m in re.finditer(rf"{NUMERO}\s*(kw|w|watts?|vatios?)(?![a-z])", trozo):
                    valor = a_numero(m.group(1)) * (1000 if m.group(2) == "kw" else 1)
                    if not 1 <= valor <= 100000:
                        continue
                    if re.search(r"pico|peak|surge|maxim|hasta|entrada|input|carga|cargador|paralelo|"
                                 r"total|toleranc|ganancia|\bpv\b|mppt", trozo):
                        otras.append(valor)
                    elif re.search(r"salida|output|nominal|continu|potencia|\bac\b", trozo):
                        salida.append(valor)
                    else:
                        normales.append(valor)
        return salida, normales, otras

    salida_t, normales_t, _ = clasificar(titulo)
    salida_d, normales_d, otras_d = clasificar(descripcion)
    for valores in (salida_d + salida_t, normales_t, normales_d, otras_d):
        if valores:
            return int(max(valores))
    return None


def capacidad_wh(texto):
    """Capacidad en Wh (convierte kWh a Wh). Toma la primera que aparece."""
    for m in re.finditer(rf"{NUMERO}\s*(kwh|wh)\b", normalizar(texto)):
        valor = a_numero(m.group(1)) * (1000 if m.group(2) == "kwh" else 1)
        if 10 <= valor <= 200000:
            return int(valor)
    return None


UNIDADES = {"w", "watt", "watts", "kw", "wh", "kwh", "v", "ah", "mah", "kva", "a", "hp", "usd", "cup", "mlc", "eur"}


def limpiar_modelo(texto):
    """Toma las primeras palabras de un texto como modelo, saltando palabras comunes
    y cortando donde empiezan medidas ("3600w", "2048 wh"), precios o frases."""
    palabras = re.findall(r"[a-z0-9][\w\-+./*]*", texto)
    modelo = []
    for i, palabra in enumerate(palabras):
        palabra = palabra.strip(".-/*")
        siguiente = palabras[i + 1].strip(".-/*") if i + 1 < len(palabras) else ""
        if not palabra:
            continue
        if palabra in PALABRAS_NO_MODELO:
            if modelo:
                break       # el modelo ya empezó: aquí termina
            continue        # aún no empieza: se salta la palabra
        if re.search(r"\d\s*(k?wh?|v|ah|mah|kva|hp)$", palabra) or palabra in UNIDADES:
            break           # medidas como 3600w, 2048wh o 10-220v no son parte del modelo
        if re.fullmatch(r"[\d.,]+", palabra) and siguiente in UNIDADES:
            break           # "2048 wh", "1270 usd": un número seguido de una unidad
        modelo.append(palabra)
        if len(modelo) == 3:
            break
    # "delta 3 max" -> "Delta 3 Max";  "sun-5k-sg04lp1" -> "SUN-5K-SG04LP1"
    return " ".join(p.capitalize() if p.isalpha() else p.upper() for p in modelo) or None


def marca_y_modelo(titulo, descripcion, ficha, marcas):
    """Marca y modelo, en este orden de preferencia:
      - la ficha técnica ("Marca: ...", "Modelo: ...")
      - lo que el vendedor escribe como "Marca: X" o "Modelo: Y" en la descripción
      - una marca conocida que aparezca en el TÍTULO, y las palabras que la siguen como modelo
    En la descripción no se buscan marcas sueltas: muchas dicen "compatible con EcoFlow"."""
    texto = normalizar(f"{titulo}\n{descripcion}")
    marca = ficha.get("marca")
    modelo = ficha.get("modelo")
    if not marca:
        m = re.search(r"\bmarca\s*:?\s*([a-z][\w\-]{2,})", texto)
        if m and m.group(1) not in PALABRAS_NO_MODELO:
            conocida = [x for x in marcas if normalizar(x).replace(" ", "") == m.group(1).replace("-", "")]
            marca = conocida[0] if conocida else m.group(1).capitalize()
    if not modelo:
        m = re.search(r"\bmodelos?\s*:\s*([^\n,;|()]+)", texto)
        if m:
            # el vendedor lo escribió explícitamente: se toma tal cual (sin lo que sigue a " - ")
            modelo = re.split(r"\s+[-–]\s+|\s{2,}", m.group(1).strip())[0][:40].upper() or None
    t = normalizar(titulo)
    for conocida in marcas:
        patron = re.escape(normalizar(conocida)).replace(r"\ ", r"[\s-]*")
        m = re.search(rf"\b{patron}\b", t)
        if m and (not marca or normalizar(marca) == normalizar(conocida)):
            marca = conocida
            modelo = modelo or limpiar_modelo(t[m.end():m.end() + 80])
            break
    return marca, modelo


def titulo_relevante(titulo, producto):
    """Devuelve None si el título es del producto, o el motivo para descartarlo."""
    t = normalizar(titulo)
    if not any(p in t for p in producto["palabras_clave"]):
        return "el título no es del producto"
    for patron in producto["excluir"]:
        if re.search(patron, t):
            return f"accesorio u otro producto ('{patron}')"
    return None


def leer_fecha(texto):
    """Convierte '2026-10-30T15:07:56.002Z' a fecha y hora local."""
    try:
        return datetime.fromisoformat(texto.replace("Z", "+00:00")).astimezone()
    except (AttributeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Pasos del scraper
# ---------------------------------------------------------------------------

def paginas_de_busqueda(termino, depurar):
    """Devuelve, página por página, los resultados de buscar un término en La Habana,
    como pares (lista de productos, hay_pagina_siguiente).

    Primero prueba el buscador interno del sitio (/api/search/item): trae 100 resultados
    por petición y pesa unas 7 veces menos que la página normal. No es una parte pública
    del sitio y podría cambiar, así que si falla se usan las páginas normales del buscador
    (/l/search/...), que traen los mismos datos de 20 en 20."""
    global USAR_BUSCADOR_RAPIDO
    if USAR_BUSCADOR_RAPIDO:
        try:
            for salto in range(0, RESULTADOS_POR_BUSQUEDA, 100):
                url = (f"{URL_BASE}/api/search/item?text={quote(termino)}"
                       f"&location={UBICACION_ID}&limit=100&skip={salto}")
                texto = descargar(url, acepta="application/json")
                if depurar and salto == 0:
                    guardar_html(f"busqueda_rapida_{termino}", texto)
                datos = json.loads(texto)["data"]
                items = [i for i in datos["items"] if isinstance(i, dict)]
                yield items, salto + len(datos["items"]) < datos["count"]
                if salto + len(datos["items"]) >= datos["count"]:
                    return
            return
        except Exception as error:  # cualquier problema: se pasa a las páginas normales
            print(f"  El buscador rápido no respondió ({error}); se usan las páginas normales.")
            USAR_BUSCADOR_RAPIDO = False
    for numero_pagina in range(1, RESULTADOS_POR_BUSQUEDA // 20 + 1):
        yield buscar_pagina(termino, numero_pagina, depurar)


def buscar_pagina(termino, numero_pagina, depurar):
    """Abre una página normal de resultados del buscador de El Yerro, filtrada por La Habana.
    Devuelve (lista de productos, hay_pagina_siguiente)."""
    url = (f"{URL_BASE}/l/search/{quote(termino)}"
           f"?location={UBICACION_ID}&page={numero_pagina}")
    html = descargar(url)
    if depurar and numero_pagina == 1:
        guardar_html(f"busqueda_{termino}", html)
    lista, armar = datos_nuxt(html)
    resultado = buscar_objeto(lista, armar, ("items", "totalCount", "skipped")) if armar else None
    if not resultado:
        return [], False
    hay_siguiente = resultado["skipped"] + len(resultado["items"]) < resultado["totalCount"]
    return resultado["items"], hay_siguiente


def leer_producto(candidato, producto, limite, depurar):
    """Abre la página de un producto y extrae sus datos.
    Devuelve (datos, None) o (None, motivo por el que se descarta)."""
    html = descargar(candidato["url"])
    if depurar:
        guardar_html("producto_" + candidato["slug"], html)
    lista, armar = datos_nuxt(html)
    if not armar:
        return None, "la página no tiene datos del producto"
    item = buscar_objeto(lista, armar, ("updatedAt", "soldOut", "price")) or {}
    tienda = buscar_objeto(lista, armar, ("organization", "location", "contact")) or {}
    ficha_ld = {}
    for bloque in re.findall(r'<script[^>]*ld\+json[^>]*>(.*?)</script>', html, re.S):
        try:
            datos = json.loads(bloque)
        except ValueError:
            continue
        if isinstance(datos, dict) and datos.get("@type") == "Product":
            ficha_ld = datos

    if not item:
        return None, "la página no tiene datos del producto"
    if item.get("soldOut"):
        return None, "agotado"
    if item.get("active") is False:
        return None, "producto desactivado"
    actualizado = leer_fecha(item.get("updatedAt"))
    if not actualizado or actualizado < limite:
        fecha = actualizado.strftime("%Y-%m-%d") if actualizado else "sin fecha"
        return None, f"no se actualizó en los últimos {DIAS_MAXIMOS} días ({fecha})"
    ubicacion = (tienda.get("contact") or {}).get("county") or candidato["ubicacion"]
    if "habana" not in normalizar(ubicacion):
        return None, f"la tienda no está en La Habana ({ubicacion})"

    titulo = item.get("name") or candidato["titulo"]
    descripcion = item.get("note") or ficha_ld.get("description") or ""
    texto = f"{titulo}\n{descripcion}"

    # Ficha técnica: lista como ["Capacidad:3600Wh", "Potencia:3600W", "Tecnología:LiFePo4"]
    ficha = {}
    for linea in item.get("specs") or []:
        if isinstance(linea, str) and ":" in linea:
            clave, valor = linea.split(":", 1)
            ficha[normalizar(clave).strip()] = valor.strip()

    # Precio: el de oferta si está activo; si no, el normal; si es 0, se busca en el texto
    precio = item.get("offerPrice") if item.get("inOffer") and item.get("offerPrice") else item.get("price")
    # La moneda que muestra el buscador es la más fiable (la ficha de la página a veces
    # trae la moneda general de la tienda en vez de la del producto)
    moneda = (candidato["moneda"] or (ficha_ld.get("offers") or {}).get("priceCurrency")
              or tienda.get("currency"))
    if not precio:
        precio, moneda = precio_en_texto(texto)

    # Potencia: primero la ficha técnica, si no el título y la descripción
    potencia = next((potencia_w(f"potencia {v}") for k, v in ficha.items()
                     if k.startswith("potencia") and "pico" not in k), None)
    potencia = potencia or potencia_w(titulo, descripcion)
    capacidad = next((capacidad_wh(v) for k, v in ficha.items() if k.startswith("capacidad")), None)
    # En paneles e inversores la descripción suele hablar de las baterías que se les pueden
    # conectar ("hasta 10 kWh de litio"), así que ahí solo se usan el título y la ficha
    texto_bateria = texto if producto["bateria_en_descripcion"] else titulo
    capacidad = capacidad or capacidad_wh(texto_bateria)
    texto_bateria = " ".join(v for k, v in ficha.items()
                             if k.startswith(("tecnologia", "tipo", "bateria", "quimica"))) + "\n" + texto_bateria

    marca, modelo = marca_y_modelo(titulo, descripcion, ficha, producto["marcas"])
    return {
        "titulo": titulo,
        "tienda": tienda.get("name") or candidato["tienda"],
        "url": candidato["url"],
        "ubicacion": ubicacion,
        "fecha_actualizacion": actualizado.strftime("%Y-%m-%d"),
        "fecha_creacion": (leer_fecha(item.get("createdAt")) or actualizado).strftime("%Y-%m-%d"),
        "precio": a_numero(str(precio)) if precio else None,
        "moneda": moneda if precio else None,
        "tipo_bateria": tipo_bateria(texto_bateria),
        "potencia_w": potencia,
        "capacidad_wh": capacidad,
        "marca": marca,
        "modelo": modelo,
    }, None


def ejecutar(clave, depurar=False):
    producto = PRODUCTOS[clave]
    limite = datetime.now(timezone.utc).astimezone() - timedelta(days=DIAS_MAXIMOS)
    print(f"\n=== Buscando: {producto['nombre']} (La Habana, últimos {DIAS_MAXIMOS} días) ===")

    # 1) Buscar en El Yerro y quedarse con los productos que, por el título,
    #    son del producto buscado y están en tiendas de La Habana
    candidatos = {}
    productos = []
    descartados_titulo = 0
    incompleto = False
    try:
        for termino in producto["busquedas"]:
            print(f"\nBuscando '{termino}' en La Habana...")
            paginas = paginas_de_busqueda(termino, depurar)
            numero_pagina = 0
            while True:
                numero_pagina += 1
                try:
                    resultados, hay_siguiente = next(paginas)
                except StopIteration:
                    break
                except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError) as error:
                    print(f"  No se pudo abrir la página {numero_pagina}: {error}")
                    break
                nuevos = 0
                for r in resultados:
                    slug = r.get("slug") or ""
                    if "/product/" not in slug or slug in candidatos:
                        continue
                    if "habana" not in normalizar(r.get("locName")):
                        continue
                    if titulo_relevante(r.get("name", ""), producto):
                        descartados_titulo += 1
                        continue
                    candidatos[slug] = {
                        "slug": slug,
                        "url": f"{URL_BASE}/b/{slug}",
                        "titulo": r.get("name"),
                        "tienda": r.get("parentName"),
                        "ubicacion": r.get("locName"),
                        "moneda": r.get("currency"),
                    }
                    nuevos += 1
                print(f"  Página {numero_pagina}: {len(resultados)} productos, {nuevos} útiles")
                # Los resultados van por relevancia: si una página no trae nada útil, se para
                if not resultados or nuevos == 0 or not hay_siguiente:
                    break
                time.sleep(PAUSA_ENTRE_PAGINAS)

        print(f"\nDescartados por el título (accesorios u otros productos): {descartados_titulo}")
        print(f"Total de productos a revisar: {len(candidatos)}")

        # 2) Abrir cada producto para leer precio, fecha, descripción y ficha técnica
        for i, candidato in enumerate(candidatos.values(), 1):
            print(f"[{i}/{len(candidatos)}] {candidato['titulo']}")
            try:
                datos, motivo = leer_producto(candidato, producto, limite, depurar)
            except SitioBloqueado:
                raise
            except Exception as error:  # cualquier fallo en un producto no detiene el resto
                print(f"    Error al leer el producto, se omite: {error}")
                continue
            if datos:
                productos.append(datos)
                print(f"    OK -> {datos['precio']} {datos['moneda']} | {datos['marca']} {datos['modelo']}"
                      f" | {datos['potencia_w']} W | {datos['tipo_bateria']}")
            else:
                print(f"    Descartado: {motivo}")
            time.sleep(PAUSA_ENTRE_PAGINAS)
    except SitioBloqueado as error:
        print(f"\n{error}")
        print("El sitio está bloqueando las visitas automáticas. Espera un rato (o cambia de red)")
        print("y vuelve a intentarlo. Si se repite, ejecuta con --depurar y envía la carpeta 'depuracion'.")
        print("Se guardan los productos leídos hasta ahora (el archivo queda marcado como incompleto).")
        incompleto = True

    # 3) Guardar el resultado en JSON
    CARPETA_RESULTADOS.mkdir(exist_ok=True)
    archivo = CARPETA_RESULTADOS / f"{clave}_{datetime.now():%Y-%m-%d_%H%M}.json"
    resultado = {
        "producto": producto["nombre"],
        "fuente": URL_FUENTE,
        "ubicacion": "La Habana, Cuba",
        "fecha_consulta": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "periodo": f"productos actualizados en los últimos {DIAS_MAXIMOS} días",
        "incompleto": incompleto,
        "total_productos": len(productos),
        "productos": productos,
    }
    archivo.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nListo. {len(productos)} productos guardados en: {archivo}")
    if incompleto:
        sys.exit(1)


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
    # Evita que la consola de Windows falle al mostrar emojis de los títulos
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    depurar = "--depurar" in sys.argv
    argumentos = [a for a in sys.argv[1:] if a != "--depurar"]
    if argumentos and argumentos[0] in PRODUCTOS:
        ejecutar(argumentos[0], depurar)
    elif argumentos:
        print(f"Producto desconocido. Opciones: {', '.join(PRODUCTOS)}")
    else:
        ejecutar(elegir_producto(), depurar)
