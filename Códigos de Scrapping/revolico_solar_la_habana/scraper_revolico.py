"""
Scraper de Revolico: mercado solar de La Habana (últimos 30 días).

Una sola corrida recoge las 5 categorías en una sola base de datos:
    paneles, estaciones, baterias, inversores, kits

Uso:
    python scraper_revolico.py                 corrida completa (se puede interrumpir y reanudar)
    python scraper_revolico.py --solo-extraer  rehace el JSON/CSV con lo ya descargado, sin internet
    python scraper_revolico.py --solo-listado  recorre el listado sin abrir cada anuncio
    python scraper_revolico.py --prueba        corrida corta para comprobar que funciona
    python scraper_revolico.py --depurar       guarda las páginas en "depuracion/"

Requisitos: solo Python 3.8 o más nuevo. No hace falta instalar nada.

Resultado: resultados/anuncios_revolico_AAAA-MM-DD.json y .csv

Privacidad: los teléfonos y nombres de los vendedores NO se guardan. Solo se conserva una
huella irreversible del teléfono para detectar anuncios repetidos, y se borra de la salida.
"""

import csv
import gzip
import hashlib
import json
import random
import re
import statistics
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

URL_BASE = "https://www.revolico.com"
SUBCATEGORIA = "hogar-plantas-y-estaciones-de-energia"  # donde se publica casi todo lo solar
PROVINCIA = "la-habana"
PROVINCIA_ID = "1"
DIAS_MAXIMOS = 30
PAUSA = 1.5                # segundos entre peticiones (no saturar el sitio)
TIEMPO_ESPERA = 60
REINTENTOS = 3
TOPE_PAGINAS = 50          # Revolico deja de dar páginas nuevas pasado cierto número: si un
                           # tramo tiene más de TOPE_PAGINAS dentro del período, se parte
MUESTRA_POR_CATEGORIA = 500  # anuncios abiertos por categoría, elegidos al azar. Abrir todos
                           # tardaría muchas horas. Cambiar el número y volver a ejecutar
                           # descarga solo los que falten. None = abrir todos.
SEMILLA_MUESTRA = 2026     # misma semilla = misma muestra
PAGINAS_POR_TERMINO = 12   # páginas revisadas por cada búsqueda de texto

# Tasas para llevar a USD los precios en otras monedas: CUP por 1 USD, etc.
# None = esa moneda no se convierte y "precio_usd" queda vacío. Si se cambian, basta con
# ejecutar --solo-extraer. La fuente y fecha de la tasa se copian al JSON.
TASAS_A_USD = {"USD": 1.0, "CUP": 900.0, "MLC": None, "EUR": round(900 / 990, 4)}
FUENTE_TASAS = ("elTOQUE, mercado informal, 2 de noviembre de 2026: 1 USD = 900 CUP, 1 EUR = 990 CUP "
                "(publicado por Infobae y Directorio Cubano). Una sola tasa para todo el período. "
                "MLC sin tasa fechada: no se convierte.")

# Monedas y tramos de precio con los que se parte el listado
# Solo USD: el filtro de moneda de Revolico convierte los precios, así que un recorrido en CUP,
# MLC o EUR vuelve a leer los mismos anuncios. El tramo en USD ya incluye las otras monedas.
TRAMOS_POR_MONEDA = {"USD": (1, 200000)}

# Búsquedas de texto: recogen lo publicado fuera de la subcategoría (sobre todo baterías)
# y los anuncios sin precio. También sirven para medir si el recorrido quedó completo.
TERMINOS = ["panel solar", "paneles solares", "kit solar", "sistema solar", "combo solar",
            "inversor solar", "inversor hibrido", "bateria litio", "bateria lifepo4",
            "bateria solar", "banco de baterias", "bateria ciclo profundo", "bateria 48v",
            "estacion de energia", "ecoflow", "bluetti", "power station"]

MUNICIPIOS = ["playa", "plaza", "centro-habana", "habana-vieja", "regla", "habana-del-este",
              "guanabacoa", "san-miguel-del-padron", "diez-de-octubre", "cerro", "marianao",
              "la-lisa", "boyeros", "arroyo-naranjo", "cotorro"]

# Precio mínimo y máximo creíble en USD por categoría. Fuera de este rango el precio se
# conserva tal cual, pero se marca en "precio_alerta" y no se calcula "precio_usd".
PRECIO_CREIBLE_USD = {
    "paneles": (15, 3000),
    "estaciones": (50, 12000),
    "baterias": (30, 15000),
    "inversores": (40, 15000),
    "kits": (150, 60000),
}

CARPETA = Path(__file__).parent
CARPETA_RESULTADOS = CARPETA / "resultados"
CARPETA_CACHE = CARPETA / "cache"
CARPETA_DEPURACION = CARPETA / "depuracion"
ARCHIVO_LISTADO = CARPETA_CACHE / "listado.json"
ARCHIVO_DETALLES = CARPETA_CACHE / "detalles.jsonl"

MARCAS = [
    # estaciones
    "EcoFlow", "Bluetti", "Jackery", "Anker", "Goal Zero", "Allpowers", "Oukitel", "Fossibot",
    "Pecron", "Zendure", "Vtoman", "Ugreen", "Dabbsson", "Dabbson", "Headway", "Mango Power", "Oupes",
    "Aferiy", "Ampace", "Sinopower", "Marsriva", "Gnercell",
    # paneles
    "Jinko", "JA Solar", "Longi", "Trina", "Canadian Solar", "Risen", "Renogy", "Sunpower",
    "Astronergy", "DAH Solar", "Tongwei", "Znshine", "Seraphim", "Sunova", "Leapton", "Boviet",
    "Runergy", "Lvyuan", "TCL Solar", "Skymax", "Hiking", "VSUN", "MRS", "Vivamax", "Ronma", "Jinergy",
    "Horay", "Messi Solar", "Solar Ever", "Honor Solar", "Huasun", "Sunport",
    # inversores
    "Growatt", "Deye", "Must", "Felicity", "Victron", "Huawei", "Voltronic", "Luxpower", "SRNE",
    "Sungrow", "Goodwe", "Solis", "Epever", "PowMr", "Easun", "Anern", "Anenji", "Kstar", "Sako",
    "Mecer", "Fronius", "Schneider", "Sumry", "Datouboss", "Hoymiles", "Sorotec", "InfiniSolar",
    "Sunpal", "Eco-Worthy", "WattCycle", "Humsienk", "Powland", "SRGFTS", "Jasaki", "Zeneogk", "Ampinvt",
    "Tataliken", "Milexus", "Qidianfy", "Rich Solar", "Giga City",
    # baterías
    "Pylontech", "Dyness", "BYD", "Ritar", "Narada", "Trojan", "Daly", "Seplos", "EVE", "CATL",
    "Basen", "Hubble", "Poeruni", "Dumfume", "Unizuki", "HuanTai", "Yeagulch",
]
# escrituras alternativas que usan los vendedores -> marca correcta
ALIAS_MARCAS = {"ecoflows": "EcoFlow", "ekoflow": "EcoFlow", "ekoflows": "EcoFlow", "eko flow": "EcoFlow",
                "ecoflou": "EcoFlow", "powermr": "PowMr", "pow mr": "PowMr", "humsieak": "Humsienk",
                "infinitisolar": "InfiniSolar", "jinko solar": "Jinko", "surry": "Sumry", "summry": "Sumry", "saco": "Sako", "ecoworthy": "Eco-Worthy",
                "jasolar": "JA Solar", "eco flow": "EcoFlow", "infini solar": "InfiniSolar",
                "felicitysolar": "Felicity", "felicity solar": "Felicity", "eco worty": "Eco-Worthy",
                "infinity solar": "InfiniSolar", "infiny solar": "InfiniSolar", "infiniti solar": "InfiniSolar"}

PALABRAS_NO_MODELO = {
    "de", "del", "la", "el", "con", "en", "y", "a", "para", "por", "tipo", "nuevo", "nueva",
    "nuevos", "original", "oferta", "precio", "vendo", "venta", "se", "disponible", "marca",
    "modelo", "serie", "electrica", "portatil", "estacion", "energia", "solar", "panel",
    "paneles", "inversor", "hibrido", "bateria", "baterias", "litio", "lithium", "lifepo4",
    "usd", "cup", "mlc", "eur", "zelle", "clasica", "clasico", "garantia", "sellado", "sellada",
    "caja", "stock", "domicilio", "gratis", "envio", "incluido", "incluida", "mensajeria",
    "genera", "mas", "capacidad", "potencia", "voltaje", "bifacial", "monocristalino",
    "monofacial", "mono", "watt", "watts", "ideal", "inteligente", "smart", "bifasico", "fase",
    "dividida", "todo", "uno", "kit", "combo", "sistema", "tecnologia", "alta", "eficiencia",
    "lo", "mejor", "entrega", "factura", "variedad", "must", "central", "cables", "cable", "plantas",
    "su", "tu", "sus", "rebaja", "ganga", "contenedor", "unidad", "cantidad", "premium", "gran", "ya", "hoy", "solo",
}
UNIDADES = {"w", "watt", "watts", "kw", "wh", "kwh", "v", "ah", "mah", "kva", "a", "hp", "usd",
            "cup", "mlc", "eur", "k"}

# ---------------------------------------------------------------------------
# Descarga
# ---------------------------------------------------------------------------

CABECERAS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "es-ES,es;q=0.9",
    "Accept-Encoding": "gzip",
}
estadisticas = Counter()


class SitioBloqueado(Exception):
    """El sitio pidió una verificación o rechazó las peticiones. No se intenta esquivar."""


def descargar(url):
    for intento in range(REINTENTOS + 1):
        try:
            peticion = urllib.request.Request(url, headers=CABECERAS)
            with urllib.request.urlopen(peticion, timeout=TIEMPO_ESPERA) as respuesta:
                datos = respuesta.read()
                estadisticas["peticiones"] += 1
                estadisticas["bytes"] += len(datos)
                if respuesta.headers.get("Content-Encoding") == "gzip":
                    datos = gzip.decompress(datos)
            texto = datos.decode("utf-8", errors="replace")
            if "<title>Just a moment" in texto or "cf_chl" in texto:
                raise SitioBloqueado("Revolico muestra la verificación de Cloudflare.")
            time.sleep(PAUSA)
            return texto
        except urllib.error.HTTPError as error:
            if error.code in (403, 429, 503):
                raise SitioBloqueado(f"Revolico respondió con el código {error.code}.")
            if error.code == 404 or intento == REINTENTOS:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
            if intento == REINTENTOS:
                raise
        time.sleep(5 * (intento + 1))


def estado_apollo(html):
    """Revolico trae los datos de cada página en JSON dentro de <script id="__NEXT_DATA__">."""
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        return {}
    return json.loads(m.group(1))["props"]["pageProps"].get("__APOLLO_STATE__", {}) or {}


def guardar_html(nombre, html):
    CARPETA_DEPURACION.mkdir(exist_ok=True)
    nombre = re.sub(r"[^\w\-]+", "_", nombre)[:80]
    (CARPETA_DEPURACION / f"{nombre}.html").write_text(html, encoding="utf-8")


# ---------------------------------------------------------------------------
# Fase 1: listado de anuncios
# ---------------------------------------------------------------------------

def huella(valor):
    """Huella irreversible para comparar vendedores sin guardar su teléfono."""
    return hashlib.sha256(f"revolico-solar:{valor}".encode()).hexdigest()[:16] if valor else None


def leer_pagina_listado(parametros, pagina, depurar=False):
    """Devuelve (anuncios, número de páginas, hay_siguiente)."""
    html = descargar(f"{URL_BASE}/search?{urlencode({**parametros, 'page': pagina})}")
    if depurar and pagina == 1:
        guardar_html("listado_" + urlencode(parametros), html)
    estado = estado_apollo(html)
    consultas = estado.get("ROOT_QUERY", {})
    anuncios, paginas, siguiente = [], 0, False
    for clave, valor in consultas.items():
        if not clave.startswith(("adsPerPage(", "promotedAds(")) or not isinstance(valor, dict):
            continue
        for borde in valor.get("edges", []):
            ad = estado.get((borde.get("node") or {}).get("__ref", ""))
            if not ad or ad.get("provinceId") != PROVINCIA_ID:
                continue
            telefono = ((ad.get("phoneInfo") or {}).get("firstPhone") or {}).get("number")
            municipio = estado.get(f"MunicipalityType:{ad.get('municipalityId')}") or {}
            anuncios.append({
                "id": ad["id"], "titulo": ad.get("title") or "", "precio": ad.get("price"),
                "moneda": ad.get("currency"), "fecha": ad.get("updatedOnToOrder"),
                "enlace": ad.get("permalink"), "municipio": municipio.get("name"),
                "vendedor": huella(telefono), "vistas": ad.get("viewCount"),
            })
        if clave.startswith("adsPerPage("):
            info = valor.get("pageInfo", {})
            paginas, siguiente = info.get("pageCount") or 0, bool(info.get("hasNextPage"))
    return anuncios, paginas, siguiente


def leer_fecha(texto):
    try:
        return datetime.fromisoformat(texto.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None


class Listado:
    """Guarda los anuncios encontrados y permite reanudar si la corrida se interrumpe."""

    def __init__(self, limite):
        self.limite = limite
        self.anuncios = {}
        self.tramos_hechos = set()
        if ARCHIVO_LISTADO.exists():
            datos = json.loads(ARCHIVO_LISTADO.read_text(encoding="utf-8"))
            self.anuncios = datos["anuncios"]
            self.tramos_hechos = set(datos["tramos_hechos"])

    def guardar(self):
        CARPETA_CACHE.mkdir(exist_ok=True)
        # se escribe aparte y se reemplaza: una interrupción no puede dañar lo ya guardado
        temporal = ARCHIVO_LISTADO.with_suffix(".tmp")
        temporal.write_text(json.dumps(
            {"anuncios": self.anuncios, "tramos_hechos": sorted(self.tramos_hechos)},
            ensure_ascii=False), encoding="utf-8")
        temporal.replace(ARCHIVO_LISTADO)

    def agregar(self, anuncios, origen):
        nuevos = 0
        for ad in anuncios:
            fecha = leer_fecha(ad["fecha"])
            if not fecha or fecha < self.limite:
                continue
            if ad["id"] not in self.anuncios:
                ad["origen"] = origen
                self.anuncios[ad["id"]] = ad
                nuevos += 1
        return nuevos


def recorrer_tramo(listado, parametros, etiqueta, primera, depurar):
    """Recorre un tramo ordenado por fecha hasta salir del período.
    primera = (anuncios, páginas, hay_siguiente) de la página 1, ya descargada."""
    vistos = set()
    anuncios, paginas, siguiente = primera
    pagina, nuevos_total = 1, 0
    while True:
        ids = {a["id"] for a in anuncios}
        if pagina > 1 and not ids - vistos:
            print(f"    {etiqueta}: el sitio repite páginas desde la {pagina}; fin del tramo")
            estadisticas["tramos_con_tope"] += 1
            break
        vistos |= ids
        nuevos_total += listado.agregar(anuncios, "subcategoria")
        fechas = [f for f in (leer_fecha(a["fecha"]) for a in anuncios) if f]
        if not anuncios or not siguiente or (fechas and min(fechas) < listado.limite):
            break
        pagina += 1
        anuncios, paginas, siguiente = leer_pagina_listado(parametros, pagina, depurar)
    print(f"    {etiqueta}: {pagina} páginas, {nuevos_total} anuncios nuevos, "
          f"{len(listado.anuncios)} en total")


def partir_por_precio(listado, moneda, bajo, alto, depurar, municipio=None):
    """Parte el listado por precio hasta que cada tramo se pueda recorrer entero."""
    etiqueta = f"{moneda} {bajo}-{alto}" + (f" {municipio}" if municipio else "")
    if etiqueta in listado.tramos_hechos:
        return
    parametros = {"subcategory": SUBCATEGORIA, "province": PROVINCIA, "order": "date",
                  "currency": moneda, "min_price": bajo, "max_price": alto}
    if municipio:
        parametros["municipality"] = municipio
    primera = leer_pagina_listado(parametros, 1, depurar)
    paginas = primera[1]
    # ¿el período de 30 días cabe en TOPE_PAGINAS? Se mira la última página permitida
    demasiado = False
    if paginas > TOPE_PAGINAS:
        muestra = leer_pagina_listado(parametros, TOPE_PAGINAS)[0]
        fechas = [f for f in (leer_fecha(a["fecha"]) for a in muestra) if f]
        demasiado = bool(fechas) and min(fechas) >= listado.limite
    if demasiado and alto - bajo >= 1:
        medio = (bajo + alto) // 2
        partir_por_precio(listado, moneda, bajo, medio, depurar, municipio)
        partir_por_precio(listado, moneda, medio + 1, alto, depurar, municipio)
        return
    if demasiado and not municipio:
        # un único precio con demasiados anuncios: se parte por municipio
        for nombre in MUNICIPIOS:
            partir_por_precio(listado, moneda, bajo, alto, depurar, nombre)
        return
    if demasiado:
        print(f"    AVISO: {etiqueta} no cabe en {TOPE_PAGINAS} páginas; se toma lo que entre")
        estadisticas["tramos_truncados"] += 1
    recorrer_tramo(listado, parametros, etiqueta, primera, depurar)
    listado.tramos_hechos.add(etiqueta)
    listado.guardar()


def buscar_terminos(listado, depurar, terminos, paginas_max):
    """Búsquedas de texto por relevancia. Mide qué parte de lo que hallan ya se tenía, que es
    una comprobación independiente de que el recorrido por precio quedó completo."""
    conocidos, totales = 0, 0
    for termino in terminos:
        etiqueta = f"texto:{termino}"
        if etiqueta in listado.tramos_hechos:
            continue
        parametros = {"q": termino, "province": PROVINCIA}
        vistos = set()
        utiles_seguidas_vacias = 0
        for pagina in range(1, paginas_max + 1):
            anuncios, _, siguiente = leer_pagina_listado(parametros, pagina, depurar)
            ids = {a["id"] for a in anuncios}
            if not ids - vistos:
                break
            vistos |= ids
            utiles = [a for a in anuncios if clasificar(a["titulo"])[0]
                      and (leer_fecha(a["fecha"]) or listado.limite) >= listado.limite]
            for a in utiles:
                totales += 1
                conocidos += listado.anuncios.get(a["id"], {}).get("origen") == "subcategoria"
            for a in anuncios:
                # los que se encontraron solo por texto se marcan para saber su origen
                listado.agregar([a], "texto")
            utiles_seguidas_vacias = 0 if utiles else utiles_seguidas_vacias + 1
            if not siguiente or utiles_seguidas_vacias >= 2:
                break
        print(f"    '{termino}': {len(vistos)} anuncios revisados, {len(listado.anuncios)} en total")
        listado.tramos_hechos.add(etiqueta)
        listado.guardar()
    return conocidos, totales


# ---------------------------------------------------------------------------
# Clasificación por título
# ---------------------------------------------------------------------------

def normalizar(texto):
    """Minúsculas, sin tildes ni símbolos especiales ('LiFePO₄' -> 'lifepo4')."""
    texto = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in texto if not unicodedata.combining(c)).lower()


# Lo que no es producto del estudio, aunque mencione paneles o baterías
NO_ES_PRODUCTO = [
    (r"\bcompro\b|\bse compra\b|\bbusco\b|\bnecesito\b", "busca comprar, no vende"),
    (r"^\W*(instalacion|montaje)\b|\breparaci|\breparo\b|\bmantenimiento\b|\bservicios? de\b|\bse instala|\binstalador", "servicio"),
    (r"\bgasolina\b|\bdiesel\b|\bdual ?fuel\b|\bgenerac\b|\bmotor\b", "planta de combustible"),
    (r"\bcable|\bconector|\bmc4\b|\bsoporte|\bbases?\b|\bestructura|\bfundas?\b|\bbreaker|\bbreakers\b|"
     r"\bprotector|\bprotecciones\b|\bmultimetro|\bmultimeter|\bpinza|\bcajas? de\b|\bbarras?\b|\bterminal|\bfusible|"
     r"\bpeso muerto\b|\bmonitor de|\bextension|\bmochila|\bbolso|\badaptador|\bracks?\b|\bgabinete|"
     r"\bdisyuntor|\bcombiner|\batpsw?\b|\bdongle\b|\bwifi\b|\bcontrolador|\bregulador|\bmppt\b.*\bsolo\b",
     "accesorio"),
    (r"\btaladro|\btester\b|\blampara|\bfarol|\blinterna|\breflector|\bluz solar|\bluces\b|\bbombillo|\bfoco|\bcamara|"
     r"\bventilador|\bcalentador|\bbomba\b|\bnevera|\brefrigerador|\bfreezer|\bcongelador|\blavadora|"
     r"\baire acondicionado|\bsplit\b|\bclimatizador|\bmicroondas|\bolla\b|\bcocina\b|\bsold(ar|ador|adora)|"
     r"\btelevisor|\btv\b|\bcelular|\biphone|\bsamsung\b|\bxiaomi\b|\blaptop|\bcargador de (bateria|celular)|"
     r"\bpower ?bank|\bpilas?\b|\b18650\b|\bcasa\b|\bapartamento\b",
     "otro producto"),
    (r"\bmotos?\b|bi[cs]imoto|\bmotorina|\bciclomotor|\bcuatriciclo|\bbicicleta|\bbici\b|\bscooter|\bpatineta|\btriciclo|\bcarro\b|\bauto\b|\bautomovil|"
     r"\bcarrito de golf\b|\bjeep\b|\bmoskvich\b", "de vehículo"),
]

RE_KIT = r"\bkits?\b|\bcombos?\b|\bsistemas? (solar|fotovoltaico|completo|de energia|hibrido)|\bsistema de \d|\bsistema \d|\btodo en (uno|1)\b|\ball in one\b|\b(2|dos) en (1|uno)\b|\b\d+([.,]\d)?\s*(kw|k)?\s+con\s+\d+([.,]\d)?\s*(kwh?|k)?\b"
RE_PANEL = r"\bpanel(es)?\b|\bplacas? solar|\bmodulos? solar|\bfotovoltaico"
RE_INVERSOR = r"\binversor(es)?\b|\binverter\b"
RE_BATERIA = r"\bbaterias?\b|\blifepo4\b|\bbanco de baterias\b"
RE_ESTACION = (r"\becoflow\b|\beco flow\b|\bbluetti\b|\bjackery\b|\baferiy\b|\bampace\b|\banker solix\b|"
               r"\boukitel\b|\bfossibot\b|\bpecron\b|\bvtoman\b|\ballpowers\b|\bzendure\b|\boupes\b|"
               r"\bdabb?son\b|\bdabbsson\b|\bmars ?riva\b|\becoflo\w*|\bdelta ?(2|3|pro ?\d?|max|mini)\b|\briver ?(2|3|pro|max)\b|"
               r"\bestacion(es)? (de energia|d energia|energia|de carga|electrica|portatil|solar)|\bpower station\b|\benergia portatil\b|"
               r"\bplanta(s)? (electrica(s)? )?portatil|\bplanta(s)? (electrica(s)? )?(de )?(litio|bateria)|"
               r"\bgenerador(es)? solar")


def clasificar(titulo):
    """Devuelve (categoría, None) o (None, motivo del descarte)."""
    t = normalizar(titulo)
    # "ideal para kit solares", "compatible con baterías": la frase no describe lo que se vende
    t_limpio = re.sub(r"\b(para|compatible con|compatibles con|sirve para|sirven para|ideal para)\s+"
                      r"(tu |su |tus |sus |los |las |el |la |un |una )?(kits?|sistemas?|combos?|inversor(es)?|"
                      r"baterias?|panel(es)?|ecoflow|estacion(es)?)\b[^,.;|!]*", " ", t)
    hay_kit = re.search(RE_KIT, t_limpio)
    hay_panel = re.search(RE_PANEL, t_limpio)
    hay_inversor = re.search(RE_INVERSOR, t_limpio)
    hay_bateria = re.search(RE_BATERIA, t_limpio)
    hay_estacion = re.search(RE_ESTACION, t_limpio)
    if not (hay_kit or hay_panel or hay_inversor or hay_bateria or hay_estacion):
        return None, "el título no es de ninguna categoría"

    componentes = sum(bool(x) for x in (hay_panel, hay_inversor, hay_bateria))
    es_energia = (hay_panel or hay_inversor or hay_estacion or hay_bateria or
                  re.search(r"\bsolar|\d\s*k(w|wh)?\b|\blitio|\blifepo4|todo en (uno|1)|\d con \d|\bhibrido|infini ?solar", t_limpio))
    # "Panel EcoFlow 220W" es un panel; "EcoFlow Delta 3 + panel" es un combo
    es_kit = ((hay_kit and es_energia) or componentes >= 2
              or (hay_estacion and hay_panel and not re.match(r"\W*(panel|placa)", t)))

    # el título empieza nombrando un accesorio: es el accesorio, aunque mencione otros equipos
    if re.match(r"\W*(cables?|conector\w*|adaptador\w*|soportes?|bases?|estructuras?|breakers?|"
                r"protector\w*|supresor\w*|cajas?|fusibles?|terminal\w*|herramientas?|accesorios?|cargador\w*|balanceador\w*|bms|monitor\w*|controlador\w*|mppt)\b", t):
        return None, "accesorio"
    # "Panel 620w + base tipo torre": el título empieza por el producto y el accesorio es un añadido
    empieza_producto = re.match(r"\W*((vendo|venta de|oferta)\W+)?(panel(es)?|placas?|inversor(es)?|baterias?)\b", t)
    for patron, motivo in NO_ES_PRODUCTO:
        if re.search(patron, t):
            # un kit puede nombrar accesorios ("con cables y estructura"): no se descarta por eso
            if motivo == "accesorio" and (es_kit or empieza_producto):
                continue
            return None, motivo

    # "INVERSORES SUMRY, BATERÍAS, PANELES, CABLES": anuncio de una tienda, no un producto
    if componentes >= 2 and not hay_kit and not re.search(r"\d", t) and t.count(",") >= 2:
        return None, "catálogo de una tienda"
    if es_kit:
        return "kits", None
    if hay_estacion:
        if hay_panel and re.match(r"\W*(panel|placa)", t):  # "Panel Solar Portátil AFERIY 200W"
            return "paneles", None
        if re.search(r"\bextras?\b|\bauxiliar\b|\badicional\b", t) and hay_bateria:
            return None, "batería extra de una estación"
        return "estaciones", None
    if hay_inversor:
        # muchas plantas de gasolina se venden como "inverter"
        if re.search(r"\bplantas?\b|\bgenerador|silencios|\btiempos?\b", t):
            return None, "planta de combustible"
        return "inversores", None
    if hay_bateria:
        # "batería" a secas puede ser de cualquier cosa: se exige una señal de energía solar
        if re.search(r"lifepo4|\blitio\b|\blithium\b|\bgel\b|\bagm\b|ciclo profundo|\bsolar|"
                     r"\d\s*kwh?\b|\b(12|12[.,]8|24|25[.,]6|48|51[.,]2)\s*v\b|\b\d{2,3}\s*ah\b", t):
            if re.search(r"(?<![\d.,])[1-9]([.,]\d+)?\s*ah\b|\d\s*mah\b", t):
                return None, "batería pequeña (no es de sistema solar)"
            return "baterias", None
        return None, "batería sin señales de uso solar"
    if hay_panel:
        if re.search(r"\bsolar|fotovoltaico|\bbifacial|\bmonofacial|\bmonocristalino|\d\s*w(atts?)?\b", t):
            return "paneles", None
        return None, "panel que no parece solar"
    return None, "el título no es de ninguna categoría"


# ---------------------------------------------------------------------------
# Extracción de campos a partir del texto
# ---------------------------------------------------------------------------

NUMERO = r"(\d{1,3}(?:[.,  ]\d{3})+(?![\d])|\d+(?:[.,]\d+)?)"
# En medidas el espacio no separa miles ("AC70 768 Wh", "Delta 2 500W") y la cifra no sale de un
# nombre de modelo ("AC180,1152 Wh")
MEDIDA = r"(?<![a-z\d])(\d{1,3}(?:[.,]\d{3})+(?![\d])|\d+(?:[.,]\d+)?)"
MONEDAS = [("USD", r"\busd\b|u\.s\.d|d[oó]lares?|\bdolar\b|\bus\$"), ("MLC", r"\bmlc\b"),
           ("EUR", r"\beur\b|\beuros?\b|€"), ("CUP", r"\bcup\b|\bpesos?\b|\bmn\b|moneda nacional")]
TIPOS_BATERIA = [("LiFePO4", r"life\s*po4?\b|\blfp\b|litio[\s-]*hierro|fosfato de hierro"), ("Gel", r"\bgel\b"),
                 ("AGM", r"\bagm\b"), ("Plomo-ácido", r"\bplomo\b|lead[\s-]*acid"),
                 ("NMC", r"\bnmc\b|\bncm\b"), ("Ion de litio", r"\blitio\b|\blithium\b|\bli[\s-]?ion\b")]


def a_numero(texto):
    t = texto.strip().replace(" ", "").replace(" ", "")
    if re.fullmatch(r"\d{1,3}([.,]\d{3})+", t):
        valor = float(re.sub(r"[.,]", "", t))
    else:
        valor = float(t.replace(",", "."))
    return int(valor) if valor == int(valor) else valor


def con_unidad(numero, unidad):
    """Pasa a W o Wh. '15 kWh' son 15000 Wh, pero un valor de 1000 o más escrito en 'k' es un error
    del vendedor: '15350kw' y '15,338 kWh' son unos 15 kWh, y '4000 kW' son 4000 W."""
    valor = a_numero(numero)
    return valor * 1000 if unidad[0] == "k" and valor < 1000 else valor


def tipo_bateria(texto):
    for nombre, patron in TIPOS_BATERIA:
        if re.search(patron, texto):
            return nombre
    return None


def precio_en_texto(texto):
    """Busca un precio escrito en el texto, como '2250 USD' o 'precio: 300 usd'."""
    patron_moneda = "|".join(p for _, p in MONEDAS)
    for m in re.finditer(rf"{NUMERO}\s*\$?\s*({patron_moneda})|(?:{patron_moneda})\s*\$?\s*{NUMERO}", texto):
        numero = m.group(1) or m.group(m.lastindex)
        try:
            valor = a_numero(numero)
        except ValueError:
            continue
        if valor > 0:
            moneda = next((c for c, p in MONEDAS if re.search(p, m.group(0))), None)
            return valor, moneda
    return None, None


def potencias(texto):
    """Clasifica cada valor en W según las palabras que lo rodean.
    Devuelve (nominales, sin_etiqueta, picos). Se ignora Wh, que es capacidad.
    '1800W pico 3600W': el pico es 3600. '1800W (3600W pico)': también."""
    nominal, normal, pico = [], [], []
    for linea in texto.splitlines():
        for trozo in re.split(r"[()/,;|]|(?=\bhasta\b)", linea):
            for m in re.finditer(rf"{MEDIDA}\s*(kw|k|w|wats?|watts?|vatios?)(?![a-z])", trozo):
                try:
                    valor = con_unidad(m.group(1), m.group(2))
                except ValueError:
                    continue
                if not 1 <= valor <= 100000:
                    continue
                valor = int(valor) if valor == int(valor) else valor  # '8.5W' sigue siendo 8.5
                antes = trozo[max(0, m.start() - 22):m.start()]
                # lo que hay antes, solo hasta el valor anterior
                antes = re.split(r"\d\s*(?:kw|k|w|wats?|watts?|vatios?)\b", antes)[-1]
                despues = trozo[m.end():m.end() + 32]
                # 'soporta hasta 5600W en paneles' es lo que admite de entrada, no su pico
                if re.search(r"entrada|input|carga|cargador|paralelo|total|toleranc|ganancia|\bpv\b|mppt|soporta|admite",
                             antes) or re.match(r"\W*(de\s+|en\s+)?(entrada|input|carga|panel|solar|pv\b|total)", despues):
                    continue
                # "3600W pico 1800W nominal": lo que lleva "nominal" detrás es el nominal
                if re.match(r"\W*(nominal|continu)", despues):
                    nominal.append(valor)
                elif re.match(r"\W*picos?\W+\d[\d.,]*\s*k?w\W+(nominal|continu)", despues):
                    pico.append(valor)
                elif (re.search(r"pico|peak|surge|maxim|hasta|arranque", antes)
                        or re.match(r"\W*(de\s+)?(potencia\s+)?(picos?|peak|surge|max|maxim\w*)\b(?!\W*(?:de\s+)?\d)", despues)):
                    pico.append(valor)
                elif re.search(r"salida|output|nominal|continu|potencia|\bac\b", antes + " " + despues):
                    nominal.append(valor)
                else:
                    normal.append(valor)
    return nominal, normal, pico


def capacidad_declarada(texto, kw_vale=False):
    """Capacidad en Wh. Con kw_vale, acepta '15kw' escrito para una batería (error común)."""
    unidades = "kwh|wh|kw|k" if kw_vale else "kwh|wh"
    for m in re.finditer(rf"{MEDIDA}\s*({unidades})\b", texto):
        try:
            valor = con_unidad(m.group(1), m.group(2))
        except ValueError:
            continue
        if 50 <= valor <= 200000:
            return int(valor)
    return None


def voltaje_y_amperaje(texto):
    """Voltaje de batería y amperios-hora: '48V 100Ah', '12.8V y 100AH', '25.6 x 100'."""
    m = re.search(r"\b(\d{2}(?:[.,]\d)?)\s*v(?:ol\w*)?\b[^\n]{0,15}?\b(\d{2,4})\s*a(?:h|mp\w*)?\b", texto)
    if not m:
        m = re.search(r"\b(12(?:[.,]8)?|24|25(?:[.,]6)?|48|51(?:[.,]2)?)\s*v?\s*x\s*(\d{2,4})\b", texto)
    if m:
        return float(m.group(1).replace(",", ".")), int(m.group(2))
    v = re.search(r"\b(12(?:[.,]8)?|24|25[.,]6|48|51[.,]2)\s*v(?:ol\w*)?\b", texto)
    a = re.search(r"\b(\d{2,4})\s*ah\b", texto)
    return (float(v.group(1).replace(",", ".")) if v else None), (int(a.group(1)) if a else None)


def limpiar_modelo(texto):
    """Toma como modelo las palabras tras la marca, parando en medidas, precios o frases."""
    palabras = re.findall(r"[a-z0-9]+(?:[.+*][a-z0-9]+)*", texto.split("\n")[0])
    modelo = []
    for i, palabra in enumerate(palabras):
        siguiente = palabras[i + 1] if i + 1 < len(palabras) else ""
        if palabra == "con" or re.fullmatch(r"bifacial(es)?|monofacial(es)?|monocristalin[oa]s?|bms|fase|face", palabra):
            break
        if palabra in PALABRAS_NO_MODELO:
            if modelo:
                break
            continue
        if re.search(r"\d\s*(k?wh?|watts?|v|ah|mah|kva|hp|k|usd|cup)($|[.+*])", palabra) or palabra in UNIDADES:
            break
        if re.fullmatch(r"[\d.,]+", palabra) and (siguiente in UNIDADES or siguiente == "con"):
            break
        modelo.append(palabra)
        if len(modelo) == 3:
            break
    # un número suelto ("Must 6") no identifica un modelo
    if not any(re.search(r"[a-z]", p) for p in modelo) or (len(modelo) == 1 and len(modelo[0]) < 2):
        return None
    return " ".join(p.capitalize() if p.isalpha() else p.upper() for p in modelo)


def marca_y_modelo(titulo_n, descripcion_n):
    """Marca: del título o de un 'Marca: X' explícito. En la descripción no se buscan marcas
    sueltas porque muchas dicen 'compatible con EcoFlow'."""
    marca, modelo = None, None
    m = re.search(r"\bmodelos?\s*:\s*([^\n,;|()]+)", descripcion_n)
    if m:
        modelo = re.split(r"\s+[-–]\s+|\s{2,}", m.group(1).strip())[0][:40].upper() or None
    mejor = None
    candidatas = [(normalizar(x), x) for x in MARCAS] + list(ALIAS_MARCAS.items())
    for clave, nombre in candidatas:
        patron = re.escape(clave).replace(r"\ ", r"[\s-]*").replace(r"\-", r"[\s-]*")
        h = re.search(rf"\b{patron}\b", titulo_n)
        if h and (mejor is None or h.start() < mejor[0]):
            mejor = (h.start(), h.end(), ALIAS_MARCAS.get(clave, nombre))
    if mejor:
        marca = mejor[2]
        modelo = modelo or limpiar_modelo(titulo_n[mejor[1]:mejor[1] + 80])
    else:
        # "Delta 3", "River 2": son nombres de modelo exclusivos de EcoFlow
        h = re.search(r"\b(delta|river) ?(2|3|pro|max|mini)", titulo_n)
        if h:
            marca = "EcoFlow"
            modelo = modelo or limpiar_modelo(titulo_n[h.start():h.start() + 80])
    if not marca:
        m = re.search(r"\bmarca\s*:\s*([a-z][\w\-]{2,})", descripcion_n)
        if m and m.group(1) not in PALABRAS_NO_MODELO:
            marca = m.group(1).capitalize()
    return marca, modelo


def condiciones(texto):
    """Estado, garantía, instalación y envío. Si el anuncio no lo dice, queda en None."""
    # "NUEVO PRECIO" o "10 años de uso" no dicen nada del estado del equipo
    limpio = re.sub(r"\bnuev[oa]s? (precios?|ofertas?|lotes?|modelos?|generacion|tecnologia|ingresos?|envios?)\b|"
                    r"\b(mas|muy|ampliamente) usad[oa]s\b|\busad[oa]s? (en|para|por|como)\b|\bnuevos y de uso\b", " ", texto)
    estado = None
    if re.search(r"\busad[oa]s?\b|\b(es|son|esta|\w*semanas?|mes|meses|medio|dias?) de uso\b|\bde uso pero\b|"
                 r"segunda mano|poco uso|\bsemi ?nuev", limpio):
        estado = "usado"
    elif re.search(r"\bnuev[oa]s?\b|\bsellad[oa]s?\b|\ben (su )?caja\b|\bde paquete\b", limpio):
        estado = "nuevo"

    # "garantía lineal de potencia: 30 años" es del fabricante del panel, no lo que ofrece el vendedor
    texto_g = re.sub(r"garantia (lineal|de potencia|de rendimiento|de salida|del? fabricante)[^\n.]{0,40}", " ", texto)
    garantia, meses = None, None
    if re.search(r"\bsin garantia\b|\bno (tiene|tienen|hay|incluye|tenemos|damos) garantia\b", texto_g):
        garantia = False
    elif "garantia" in texto_g:
        garantia = True
        cifra = r"(\d{1,3}|un|una|dos|tres|cuatro|cinco|seis|diez)\s*(anos?|mes(?:es)?|semanas?|dias?)"
        m = re.search(rf"garantia[^\n.]{{0,30}}?\b{cifra}\b", texto_g) \
            or re.search(rf"\b{cifra}\s*(?:de\s*)?garantia", texto_g)
        if m:
            palabras = {"un": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "diez": 10}
            n = palabras.get(m.group(1)) or int(m.group(1))
            u = m.group(2)
            meses = (n * 12 if u.startswith("ano") else n if u.startswith("mes")
                     else round(n * 7 / 30, 1) if u.startswith("semana") else round(n / 30, 1))
            # "Garantía: 12 años producto": 3 años o más es del fabricante, no lo que da el vendedor
            if meses >= 36:
                garantia, meses = None, None

    # Instalación: mencionarla no basta ("fácil instalación", "montaje en pared", "ideal para
    # instalaciones solares"). Solo cuenta si el vendedor dice que la incluye, la cobra o la hace.
    trabajo = r"(?:instalan?cion|montaje)"
    con_y_sin = re.search(rf"\bsin {trabajo}", texto) and re.search(rf"\bcon {trabajo}", texto)
    if not con_y_sin and re.search(rf"\bno (incluye|incluimos|se hace|hacemos|realizamos|ofrecemos)\s*(la |el |los )?{trabajo}", texto):
        instalacion = "no incluida"
    elif con_y_sin or re.search(
            rf"si (lo |la )?(desea|quiere)\w*[^\n.]{{0,25}}{trabajo}|{trabajo}[^\n.]{{0,12}}(costo|precio) adicional|"
            rf"{trabajo}\s*(?:[:=]|en|a|por)?\s*\$?\s*\d{{2,}}|\bcon (base y )?{trabajo}[^\n.\d]{{0,30}}[:=]?\s*\$?\s*\d{{3,}}|"
            rf"\+\s*montaje\s*\+|(?:contratar|ofrecemos|ofertamos|con|nuestro) (?:el |los |un |nuestros? )?servicios? de {trabajo}|"
            rf"\b{trabajo} (?:profesional|disponible)|\bventa e instalacion|\b(?:instalamos|realizamos {trabajo}|hacemos {trabajo}|"
            rf"se instalan|mano de obra)|^\W*{trabajo} (?:de )?(?:kit|panel|sistema)|{trabajo} con (?:nuestro|nosotros)|"
            rf"(?:hacen|realizan|haga|hace) (?:el |la )?{trabajo}|\bmontan con nuestro|equipo de tecnicos[^\n]{{0,30}}{trabajo}|"
            rf"\binstala\w* con (?:n\b|nuestro|nosotros)|opcion de montaje|\b\d+ mes(?:es)? (?:de )?instalacion|"
            rf"contacto con el servicio de instalacion", texto):
        instalacion = "ofrecida"
    elif re.search(rf"{trabajo}[^\n.]{{0,25}}no (viene |esta )?incluid|{trabajo}[^\n.]{{0,12}}(aparte|por separado)|"
                   rf"\bsin {trabajo}|\bno (incluye|incluimos|se hace|hacemos|realizamos)\s*(la |el )?{trabajo}", texto):
        instalacion = "no incluida"
    elif re.search(rf"{trabajo}(?:\s+(?:y|e)\s+\w+)?\s*(?:esta\s+|estan\s+)?(?:incluid|gratis)|"
                   rf"\b(?:incluye|incluimos|incluido|incluida|incluyendo)\s+(?:la |el |toda la |todo el )?{trabajo}|"
                   rf"\bcon (?:\w+ y )?{trabajo}\b|\bmontaje y transporte\b|[+]\s*{trabajo}|\bmas {trabajo}|\busd instalado\b|ya instalado", texto):
        instalacion = "incluida"
    elif re.search(rf"\bsin {trabajo}", texto):
        instalacion = "no incluida"
    else:
        instalacion = None

    # "este envío llegará en agosto" habla de la importación, no de llevarlo al cliente
    # y "fácil transporte" o "Transporte: incluye asa", de lo fácil que es moverlo
    limpio = re.sub(r"\b(este|ultimo|proximo|siguiente|nuestro) envio\b|\benviamos inmediatamente\b|"
                    r"\b(facil|comodo|sencillo|para|de|durante|al|su)\s+(de\s+|el\s+|su\s+)?transporte\b|"
                    r"\btransporte\W+(incluye|con)\s+(asa|ruedas|mochila|bolsa|funda)", " ", texto)
    servicio = r"(?:envios?|mensajeria|domicilio|tra?[nm]?sporte|entrega|delivery)"
    vehiculo = "[\U0001F696-\U0001F69B\U0001F6FA\U0001F6F5\U0001F6FB]"  # "con 🚗", "🚛 incluido"
    envio = None
    if re.search(rf"\b(?:sin|no hay|no hacemos|no tenemos) {servicio}|\bdomicilio\W*no\b", limpio):
        envio = None
    elif re.search(rf"{servicio}[^\n.]{{0,15}}(?:adicional|aparte|no incluid|por cobrar)|{servicio} por costo", limpio):
        envio = "disponible"
    elif re.search(rf"{servicio}[^\n.]{{0,25}}(?:gratis|incluid)|gratis[^\n.]{{0,20}}{servicio}|"
                   rf"\bcon {servicio}|\b(?:incluye|incluido) (?:el |la )?{servicio}|"
                   rf"\bcon\s*{vehiculo}|{vehiculo}\W*(?:gratis|incluid)", limpio):
        envio = "gratis"
    elif re.search(r"\benvios?\b|mensajeria|\bdomicilio\b|\btra?[nm]?sporte\b|\bdelivery\b|llevamos", limpio):
        envio = "disponible"
    return estado, garantia, meses, instalacion, envio


def datos_kit(titulo_n, texto_n):
    """Componentes de un kit. Primero el título (más fiable), luego la descripción."""
    r = {"inversor_w": None, "bateria_wh": None, "cantidad_paneles": None, "panel_w": None}
    for fuente in (titulo_n, texto_n):
        # "6 con 15", "6kw con 15 kwh", "6 kw con 10 kw batería": inversor en kW con batería en kWh
        m = re.search(r"\b(\d{1,2}(?:[.,]\d)?)\s*(?:kw|k)?\s+con\s+(\d{1,3}(?:[.,]\d)?)\s*(?:kwh?|k)?\b(?!\s*(?:paneles|placas|\d))", fuente) \
            or re.search(r"\b(\d{1,2}(?:[.,]\d)?)\s*(?:kw|k)?\s*/\s*(\d{1,3}(?:[.,]\d)?)\s*(?:kwh?|k)\b", fuente)
        if m:
            inv, bat = a_numero(m.group(1)), a_numero(m.group(2))
            if 1 <= inv <= 50 and 1 <= bat <= 100:
                r["inversor_w"] = r["inversor_w"] or int(inv * 1000)
                r["bateria_wh"] = r["bateria_wh"] or int(bat * 1000)
        if r["bateria_wh"] is None:
            # la cifra va antes de la palabra: "15kw de batería", "10 en batería", "15 de respaldo"
            m = re.search(rf"{MEDIDA}\s*(kwh|kw|k)?\s*(?:de |en )+(?:bateria|respaldo|litio)", fuente)
            if m and (m.group(2) or a_numero(m.group(1)) <= 100):
                r["bateria_wh"] = int(con_unidad(m.group(1), "k"))
        if r["inversor_w"] is None:
            # "12kw de inversor y 30kw en batería": la cifra va antes
            m = re.search(rf"{MEDIDA}\s*(kw|k|w)\s+(?:de |en )?(?:inversor|inverter)\b", fuente)
            if m:
                r["inversor_w"] = int(con_unidad(m.group(1), m.group(2)))
        if r["inversor_w"] is None:
            m = re.search(rf"(?:inversor|inverter)\b[^+;\n]{{0,35}}?{MEDIDA}\s*(kw|k|w|wats?|watts?)\b", fuente)
            if m and "bateria" not in fuente[m.start():m.start(1)]:
                r["inversor_w"] = int(con_unidad(m.group(1), m.group(2)))
        if r["bateria_wh"] is None:
            # la cantidad va pegada a la palabra: en "110 y 220 Batería", 220 no son baterías
            m = re.search(rf"(?<![\d.,])(\d{{1,2}}\s*|dos\s+|tres\s+|cuatro\s+)?bateria\w*\b[^+;\n]{{0,35}}?{MEDIDA}\s*(kwh|wh|kw|k)\b", fuente)
            if m and "panel" not in fuente[m.start():m.start(2)]:
                valor = con_unidad(m.group(2), m.group(3))
                cantidad = {"dos": 2, "tres": 3, "cuatro": 4}.get((m.group(1) or "").strip()) or int(m.group(1) or 1)
                r["bateria_wh"] = int(valor * cantidad)
            else:
                m = re.search(r"(?<![\d.,])(?:(\d{1,2})\s*)?bateria\w*\b[^+;\n]{0,20}?(\d{2}(?:[.,]\d)?)\s*v?\b[^+;\n]{0,8}?(?:x|y)\s*(\d{2,4})\s*(?:ah)?", fuente)
                if m:
                    voltios = float(m.group(2).replace(",", "."))
                    r["bateria_wh"] = int(voltios * int(m.group(3)) * (int(m.group(1)) if m.group(1) else 1))
        if r["panel_w"] is None:
            m = re.search(rf"(?:(\d+)\s*)?(?:panel(?:es)?|placas?)\b[^+;\n]{{0,40}}?{MEDIDA}\s*(w|watts?)\b", fuente)
            if m:
                r["panel_w"] = int(a_numero(m.group(2)))
                if m.group(1):
                    r["cantidad_paneles"] = int(m.group(1))
                elif re.search(r"\b(panel|placa)\b", m.group(0)):
                    r["cantidad_paneles"] = 1  # "+ panel de 620W": en singular es uno
        if r["cantidad_paneles"] is None:
            m = re.search(r"\b(\d{1,3})\s*(?:x\s*)?(?:paneles|placas)\b", fuente)
            if m:
                r["cantidad_paneles"] = int(m.group(1))
    return r


def subcategoria(categoria, t, r):
    if categoria == "paneles":
        for nombre, patron in (("portátil/plegable", r"portatil|plegable"), ("flexible", r"flexible"),
                               ("bifacial", r"bifacial"), ("monofacial", r"monofacial")):
            if re.search(patron, t):
                return nombre
        return "sin especificar"
    if categoria == "estaciones":
        c = r["capacidad_wh"]
        return None if c is None else ("menos de 1 kWh" if c < 1000 else "1 a 2 kWh" if c < 2000
                                       else "2 a 4 kWh" if c < 4000 else "4 kWh o más")
    if categoria == "baterias":
        return r["tipo_bateria"] or "sin especificar"
    if categoria == "inversores":
        for nombre, patron in (("híbrido", r"hibrido|hybrid"), ("on-grid", r"on[\s-]?grid"),
                               ("off-grid", r"off[\s-]?grid")):
            if re.search(patron, t):
                return nombre
        return "sin especificar"
    if categoria == "kits":
        if re.search(RE_ESTACION, t) and re.search(RE_PANEL, t):
            return "estación + paneles"
        if re.search(RE_PANEL, t) or r["cantidad_paneles"] or r["potencia_total_paneles_w"]:
            return "sistema con paneles"
        return "sin paneles declarados"
    return None


def borrar_contactos(texto):
    """Quita teléfonos y correos de los textos que se guardan."""
    texto = re.sub(r"[\w.+-]+@[\w-]+\.[\w.]+", "[correo]", texto or "")
    # móviles (5xxxxxxx) y fijos (7xxxxxxx), con o sin +53 y con separadores habituales
    # 8 cifras seguidas siempre son un teléfono; con separadores se exige que no siga una unidad
    # ("5000 1000 W" no lo es)
    # un punto antes no impide nada ("...5XXXXXXX..."); una cifra y un punto antes, sí ("1.5XXXXXXX")
    prefijo = r"(?<!\d)(?<!\d[.,])(?:\+?\s?53[\s.-]*)?"
    texto = re.sub(prefijo + r"[57]\d{7}(?!\d)", "[teléfono]", texto)
    # pegado a otra cifra: "3600" + móvil, o dos móviles seguidos
    texto = re.sub(r"(?<=\d)(?:53)?5\d{7}(?!\d)", "[teléfono]", texto)
    texto = re.sub(r"(?<!\d)\d{9,}(?!\d)", "[teléfono]", texto)
    texto = re.sub(prefijo + r"[57](?:[\s.-]?\d){7}(?!\d)(?!\s?[a-zA-Z])", "[teléfono]", texto)
    return re.sub(prefijo + r"(?:[57]\d[\s.-]\d{3}[\s.-]?\d{3}|[57]\d{3}[\s.-]\d{4}|[57]\d[\s.-]\d{2}[\s.-]\d{2}[\s.-]\d{2})"
                  r"(?!\d)(?!\s?[a-zA-Z])", "[teléfono]", texto)


def extraer(ad, detalle):
    """Convierte un anuncio en un registro de la base de datos."""
    categoria = clasificar(ad["titulo"])[0]
    descripcion = (detalle or {}).get("descripcion") or ""
    t = normalizar(ad["titulo"])
    d = normalizar(descripcion)
    texto = f"{t}\n{d}"

    # Precio: el del anuncio; si no hay, el escrito en el texto
    precio, moneda, origen_precio = ad["precio"], ad["moneda"], "campo del anuncio"
    if not precio:
        precio, moneda = precio_en_texto(texto)
        origen_precio = "texto" if precio else None

    r = dict.fromkeys(("tipo_bateria", "potencia_w", "potencia_pico_w", "capacidad_wh", "capacidad_origen",
                       "voltaje_v", "amperaje_ah", "cantidad_paneles", "potencia_total_paneles_w"))
    nominal_t, normal_t, pico_t = potencias(t)
    nominal_d, normal_d, pico_d = potencias(d)

    if categoria == "paneles":
        validos = [w for w in nominal_t + normal_t + nominal_d + normal_d if 5 <= w <= 1000]
        r["potencia_w"] = validos[0] if validos else None
        r["tipo_bateria"] = None
    elif categoria == "inversores":
        validos = [w for w in nominal_t + nominal_d + normal_t + normal_d if 100 <= w <= 100000]
        r["potencia_w"] = validos[0] if validos else None
        picos = [w for w in pico_t + pico_d if w > (r["potencia_w"] or 0)]
        r["potencia_pico_w"] = picos[0] if picos else None
        r["voltaje_v"] = voltaje_y_amperaje(t)[0] or voltaje_y_amperaje(d)[0]
    elif categoria == "estaciones":
        validos = [w for w in nominal_t + nominal_d + normal_t + normal_d if 50 <= w <= 20000]
        r["potencia_w"] = validos[0] if validos else None
        picos = [w for w in pico_t + pico_d if w > (r["potencia_w"] or 0)]
        r["potencia_pico_w"] = picos[0] if picos else None
        r["capacidad_wh"] = capacidad_declarada(t) or capacidad_declarada(d)
        r["capacidad_origen"] = "declarada" if r["capacidad_wh"] else None
        r["tipo_bateria"] = tipo_bateria(texto)
    elif categoria == "baterias":
        voltios, amperios = voltaje_y_amperaje(t)
        if not voltios or not amperios:
            v2, a2 = voltaje_y_amperaje(d)
            voltios, amperios = voltios or v2, amperios or a2
        r["voltaje_v"], r["amperaje_ah"] = voltios, amperios
        r["capacidad_wh"] = capacidad_declarada(t, kw_vale=True) or capacidad_declarada(d)
        if r["capacidad_wh"]:
            r["capacidad_origen"] = "declarada"
        elif voltios and amperios:
            r["capacidad_wh"] = int(voltios * amperios)
            r["capacidad_origen"] = "calculada V x Ah"
        r["tipo_bateria"] = tipo_bateria(texto)
    elif categoria == "kits":
        k = datos_kit(t, d)
        r["potencia_w"] = k["inversor_w"]
        if r["potencia_w"] is None:
            m = re.search(rf"(?:kit|sistema|combo)[^\n+]{{0,40}}?{MEDIDA}\s*(kw|k)\b", t)
            if m and "bateria" not in t[m.start():m.start(1)]:
                r["potencia_w"] = int(con_unidad(m.group(1), m.group(2)))
        r["capacidad_wh"] = k["bateria_wh"]
        r["capacidad_origen"] = "declarada" if k["bateria_wh"] else None
        r["cantidad_paneles"] = k["cantidad_paneles"]
        if k["cantidad_paneles"] and k["panel_w"]:
            r["potencia_total_paneles_w"] = k["cantidad_paneles"] * k["panel_w"]
        # capacidad escrita sin nombrar la batería: "kit solar 26kwh", "combo 2560 Wh"
        if r["capacidad_wh"] is None:
            r["capacidad_wh"] = capacidad_declarada(t)
            r["capacidad_origen"] = "declarada" if r["capacidad_wh"] else None
        # kit de estación portátil: la capacidad y la potencia son las de la estación
        if re.search(RE_ESTACION, t) and r["capacidad_wh"] is None:
            r["capacidad_wh"] = capacidad_declarada(d)
            r["capacidad_origen"] = "declarada" if r["capacidad_wh"] else None
        if re.search(RE_ESTACION, t) and r["potencia_w"] is None:
            n, c, _ = potencias(re.split(RE_PANEL, t)[0])
            n2, c2, _ = potencias(re.split(RE_PANEL, d)[0])
            validos = n + c + n2 + c2
            r["potencia_w"] = validos[0] if validos else None
        r["tipo_bateria"] = tipo_bateria(texto)
        r["voltaje_v"] = voltaje_y_amperaje(t)[0]

    # un valor imposible es un error de lectura: mejor vacío que falso
    if r["capacidad_wh"] and not 50 <= r["capacidad_wh"] <= 200000:
        r["capacidad_wh"], r["capacidad_origen"] = None, None
    if r["potencia_w"] and not 1 <= r["potencia_w"] <= 100000:
        r["potencia_w"] = None

    estado, garantia, meses, instalacion, envio = condiciones(texto)
    marca, modelo = marca_y_modelo(t, d)
    registro = {
        "id": ad["id"],
        "categoria": categoria,
        "subcategoria": None,
        "titulo": borrar_contactos(ad["titulo"]),
        # el enlace corto funciona igual, y el largo puede llevar el teléfono escrito en el título
        "url": f"{URL_BASE}/item/{ad['id']}",
        "fecha_actualizacion": (ad["fecha"] or "")[:10] or None,
        "municipio": ad.get("municipio"),
        "precio": precio,
        "moneda": moneda,
        "precio_origen": origen_precio,
        "precio_usd": None,
        "precio_alerta": None,
        "marca": marca,
        "modelo": borrar_contactos(modelo) if modelo else None,
        **r,
        "usd_por_w": None,
        "usd_por_wh": None,
        "estado": estado,
        "tiene_garantia": garantia,
        "garantia_meses": meses,
        "instalacion": instalacion,
        "envio": envio,
        "veces_publicado": ad.get("veces_publicado", 1),
        "descripcion_leida": detalle is not None,
        "vistas": ad.get("vistas"),
        "origen": ad.get("origen"),
        "descripcion": borrar_contactos(descripcion),
    }
    registro["subcategoria"] = subcategoria(categoria, t, registro)
    if categoria == "kits" and registro["subcategoria"] != "estación + paneles":
        registro["modelo"] = None  # un sistema tiene varios componentes: la marca es la principal

    # Precio en USD y alertas: el precio original nunca se cambia
    if precio:
        tasa = TASAS_A_USD.get(moneda)
        usd = precio / tasa if (tasa and moneda != "USD") else (precio if moneda == "USD" else None)
        minimo, maximo = PRECIO_CREIBLE_USD[categoria]
        if moneda == "CUP" and usd is not None and usd < minimo:
            registro["precio_alerta"] = "moneda dudosa: parece USD marcado como CUP"
            usd = None
        elif usd is not None and usd < minimo:
            registro["precio_alerta"] = "precio simbólico o muy bajo"
            usd = None
        elif usd is not None and usd > maximo:
            registro["precio_alerta"] = "precio muy alto"
            usd = None
        registro["precio_usd"] = round(usd, 2) if usd is not None else None
        if usd is not None:
            if registro["potencia_w"]:
                registro["usd_por_w"] = round(usd / registro["potencia_w"], 3)
            if registro["capacidad_wh"]:
                registro["usd_por_wh"] = round(usd / registro["capacidad_wh"], 3)
    return registro


# ---------------------------------------------------------------------------
# Fase 2: abrir anuncios y armar la base de datos
# ---------------------------------------------------------------------------

def clave_repetido(ad):
    """Un vendedor suele publicar la misma oferta muchas veces, cambiando un poco el título:
    misma persona, categoría, precio, marca y prestaciones cuentan como una sola oferta."""
    r = extraer(ad, None)  # solo con el título; no hace falta abrir el anuncio
    return (ad.get("vendedor") or ad["id"], r["categoria"], ad["precio"], ad["moneda"],
            r["marca"], r["potencia_w"], r["capacidad_wh"])


def agrupar(anuncios, detalles=None):
    """Agrupa los repetidos y deja uno por grupo: el más reciente, o el ya abierto si lo hay,
    para no perder una descripción descargada al rehacer la base."""
    grupos = {}
    for ad in anuncios:
        grupos.setdefault(clave_repetido(ad), []).append(ad)
    unicos = []
    for grupo in grupos.values():
        grupo.sort(key=lambda a: (a["id"] in (detalles or {}), a["fecha"] or ""), reverse=True)
        unico = dict(grupo[0])
        unico["veces_publicado"] = len(grupo)
        unicos.append(unico)
    return unicos


def cargar_detalles():
    detalles = {}
    if ARCHIVO_DETALLES.exists():
        # split("\n") y no splitlines(): las descripciones pueden traer separadores Unicode raros
        for linea in ARCHIVO_DETALLES.read_text(encoding="utf-8").split("\n"):
            if linea.strip():
                try:
                    d = json.loads(linea)
                except ValueError:  # última línea a medias si la corrida se cortó: se vuelve a abrir
                    continue
                detalles[d["id"]] = d
    return detalles


def muestra_pendiente(unicos, detalles):
    """Anuncios de la muestra al azar por categoría que aún no se han abierto."""
    azar = random.Random(SEMILLA_MUESTRA)
    pendientes = []
    for categoria in PRECIO_CREIBLE_USD:
        grupo = sorted((a for a in unicos if clasificar(a["titulo"])[0] == categoria), key=lambda a: a["id"])
        azar.shuffle(grupo)
        faltan = [a for a in grupo if a["id"] not in detalles]
        if MUESTRA_POR_CATEGORIA:  # lo ya abierto cuenta: la muestra no cambia al rehacer la base
            faltan = faltan[:max(0, MUESTRA_POR_CATEGORIA - (len(grupo) - len(faltan)))]
        pendientes += faltan
    azar.shuffle(pendientes)
    return pendientes


def leer_detalles(unicos, detalles, depurar, maximo=None):
    pendientes = muestra_pendiente(unicos, detalles)
    if maximo is not None:
        pendientes = pendientes[:maximo]
    print(f"\nAbriendo {len(pendientes)} anuncios ({len(detalles)} ya estaban descargados)...")
    CARPETA_CACHE.mkdir(exist_ok=True)
    with ARCHIVO_DETALLES.open("a", encoding="utf-8") as salida:
        for i, ad in enumerate(pendientes, 1):
            try:
                html = descargar(URL_BASE + (ad.get("enlace") or f"/item/{ad['id']}"))
                if depurar and i <= 5:
                    guardar_html("anuncio_" + ad["id"], html)
                pagina = estado_apollo(html).get(f"AdType:{ad['id']}") or {}
                detalle = {"id": ad["id"], "descripcion": borrar_contactos(pagina.get("description") or ""),
                           "vendido": bool(pagina.get("isSold")), "estado_anuncio": pagina.get("status")}
            except SitioBloqueado:
                raise
            except Exception as error:  # un anuncio con problemas no detiene la corrida
                print(f"    [{i}] error, se omite: {error}")
                continue
            detalles[ad["id"]] = detalle
            salida.write(json.dumps(detalle, ensure_ascii=False) + "\n")
            salida.flush()
            if i % 50 == 0:
                print(f"    {i}/{len(pendientes)} anuncios abiertos "
                      f"({estadisticas['bytes'] / 1e6:.0f} MB descargados)")


def guardar(listado, detalles, incompleto, limite, ahora):
    anuncios = [a for a in listado.anuncios.values() if clasificar(a["titulo"])[0]]
    unicos = agrupar(anuncios, detalles)
    registros = []
    vendidos = sin_detalle = 0
    for ad in unicos:
        detalle = detalles.get(ad["id"])
        if detalle is None:
            sin_detalle += 1
        elif detalle.get("vendido"):
            vendidos += 1
            continue
        registros.append(extraer(ad, detalle))
    registros.sort(key=lambda r: (r["categoria"], r["precio_usd"] is None, r["precio_usd"] or 0))

    descartes = Counter(clasificar(a["titulo"])[1] for a in listado.anuncios.values()
                        if not clasificar(a["titulo"])[0])
    resumen = {
        "anuncios_vistos_en_el_periodo": len(listado.anuncios),
        "anuncios_de_las_categorias": len(anuncios),
        "anuncios_unicos": len(registros),
        "descartados_por_vendidos": vendidos,
        "descripciones_leidas": len(registros) - sin_detalle,
        "sin_descripcion_leida": sin_detalle,
        "motivos_de_descarte_por_titulo": dict(descartes.most_common()),
        "por_categoria": dict(Counter(r["categoria"] for r in registros).most_common()),
        "por_moneda": dict(Counter(str(r["moneda"]) for r in registros).most_common()),
    }
    resultado = {
        "proyecto": "¿Hasta dónde llega el dinero de un cubano en el mercado solar de La Habana?",
        "fuente": f"{URL_BASE}/search?subcategory={SUBCATEGORIA}&province={PROVINCIA}",
        "ubicacion": "La Habana, Cuba",
        "fecha_consulta": ahora.strftime("%Y-%m-%d %H:%M UTC"),
        "periodo": f"{limite:%Y-%m-%d} a {ahora:%Y-%m-%d}",
        "significado_de_la_fecha": ("updatedOnToOrder de Revolico: última publicación o renovación "
                                    "del anuncio, no su primera publicación"),
        "tasas_a_usd": TASAS_A_USD,
        "fuente_tasas": FUENTE_TASAS,
        "incompleto": incompleto,
        "resumen": resumen,
        "total_anuncios": len(registros),
        "anuncios": registros,
    }
    CARPETA_RESULTADOS.mkdir(exist_ok=True)
    base = CARPETA_RESULTADOS / f"anuncios_revolico_{ahora:%Y-%m-%d}"
    base.with_suffix(".json").write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    if registros:
        columnas = [c for c in registros[0] if c != "descripcion"]
        # utf-8-sig: para que Excel muestre bien las tildes
        with base.with_suffix(".csv").open("w", newline="", encoding="utf-8-sig") as f:
            escritor = csv.DictWriter(f, columnas, extrasaction="ignore")
            escritor.writeheader()
            escritor.writerows(registros)
    print(f"\nListo. {len(registros)} anuncios únicos en: {base}.json y .csv")
    print(json.dumps({k: v for k, v in resumen.items() if k != "motivos_de_descarte_por_titulo"},
                     ensure_ascii=False, indent=2))
    return registros


def ejecutar(depurar=False, prueba=False, solo_extraer=False, solo_listado=False):
    ahora = datetime.now(timezone.utc)
    limite = ahora - timedelta(days=DIAS_MAXIMOS)
    print(f"=== Mercado solar de La Habana en Revolico, desde {limite:%Y-%m-%d} ===")
    listado = Listado(limite)
    detalles = cargar_detalles()
    incompleto = False
    if not solo_extraer:
        try:
            print("\n1) Recorriendo el listado de la subcategoría por tramos de precio...")
            if prueba:
                partir_por_precio(listado, "USD", 3000, 3050, depurar)
                conocidos, totales = buscar_terminos(listado, depurar, ["kit solar"], 2)
            else:
                for moneda, (bajo, alto) in TRAMOS_POR_MONEDA.items():
                    print(f"  Moneda {moneda}")
                    partir_por_precio(listado, moneda, bajo, alto, depurar)
                print("\n2) Búsquedas de texto (fuera de la subcategoría y anuncios sin precio)...")
                conocidos, totales = buscar_terminos(listado, depurar, TERMINOS, PAGINAS_POR_TERMINO)
            if totales:
                print(f"\nComprobación: {conocidos} de {totales} anuncios útiles hallados por texto "
                      f"ya estaban en el recorrido por precio ({100 * conocidos / totales:.1f} %).")
            listado.guardar()
            unicos = agrupar([a for a in listado.anuncios.values() if clasificar(a["titulo"])[0]], detalles)
            print(f"\n3) {len(unicos)} anuncios únicos para abrir.")
            if not solo_listado:
                leer_detalles(unicos, detalles, depurar, maximo=10 if prueba else None)
        except SitioBloqueado as error:
            print(f"\n{error}")
            print("No se intenta esquivar la verificación. Se guarda lo leído hasta ahora y el")
            print("archivo queda marcado como incompleto. Vuelve a ejecutar más tarde: continúa")
            print("donde se quedó, sin repetir descargas.")
            incompleto = True
        except KeyboardInterrupt:
            print("\nInterrumpido. Se guarda lo leído. Al ejecutarlo de nuevo continúa donde se quedó.")
            incompleto = True
        listado.guardar()
    unicos = agrupar([a for a in listado.anuncios.values() if clasificar(a["titulo"])[0]], detalles)
    if muestra_pendiente(unicos, detalles):
        incompleto = True
    registros = guardar(listado, detalles, incompleto, limite, ahora)
    print(f"\nPeticiones: {estadisticas['peticiones']}, descargado: {estadisticas['bytes'] / 1e6:.1f} MB, "
          f"tramos con tope: {estadisticas['tramos_con_tope']}, tramos truncados: {estadisticas['tramos_truncados']}")
    if registros:
        usd = [r["precio_usd"] for r in registros if r["precio_usd"]]
        if usd:
            print(f"Mediana de precio en USD: {statistics.median(usd)}")
    if incompleto:
        sys.exit(1)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace", line_buffering=True)
    ejecutar(depurar="--depurar" in sys.argv, prueba="--prueba" in sys.argv,
             solo_extraer="--solo-extraer" in sys.argv, solo_listado="--solo-listado" in sys.argv)
