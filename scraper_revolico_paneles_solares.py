#!/usr/bin/env python3
"""Scraper para extraer anuncios de paneles solares de Revolico.com en La Habana.

Extrae anuncios de la sección de electrodomesticos de La Habana, filtrando por:
- Últimos 30 días desde la fecha de ejecución
- Términos de relevancia: panel solar, paneles solares, placa solar, placas solares,
  fotovoltaico, fotovoltaica

Stack: Python 3.10+, requests, BeautifulSoup4, cloudscraper (opcional para bypass Cloudflare)

NOTA: Este sitio tiene protección Cloudflare activa que bloquea peticiones automatizadas.
El script está diseñado para intentar el scraping e informar resultados gracefully cuando
no se pueden extraer datos debido a bloqueos del sitio.
"""

import json
import logging
import random
import re
import sys
import time
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Optional, List, Dict, Any

# Intentar importar cloudscraper; si no está disponible, usaremos requests normal
try:
    import cloudscraper
    HAS_CLOUDSCRAPER = True
except ImportError:
    HAS_CLOUDSCRAPER = False
    import requests as _requests_mod
    _requests_mod = requests  # fallback

import bs4 as bs
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Configuración y constantes
# ---------------------------------------------------------------------------

BASE_URL = "https://www.revolico.com"
# URL base de búsqueda: electrodomésticos en La Habana
SEARCH_URL = f"{BASE_URL}/search?category=electrodomesticos&province=la-habana"
OUTPUT_DIR = Path("./output")
OUTPUT_FILE = OUTPUT_DIR / "paneles_solares_la_habana.json"

# Ventana temporal: últimos 30 días
FECHA_EJECUCION: date = date.today()
FECHA_LIMITE: date = FECHA_EJECUCION - timedelta(days=30)

# Términos de relevancia para filtrar títulos/descripciones
TERMINOS_RELEVANCIA = [
    "panel solar", "paneles solares", "placa solar", "placas solares",
    "fotovoltaico", "fotovoltaica", "energy panel", "solar panel"
]

# User-Agents rotativos para evitar bloques
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Safari/605.1.15",
]

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("revolico_scraper")


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def user_agent_rotator() -> dict:
    """Retorna headers con User-Agent aleatorio."""
    return {"User-Agent": random.choice(USER_AGENTS)}


def delay_aleatorio(min_sec: float = 1.0, max_sec: float = 3.0) -> None:
    """Pausa aleatoria entre peticiones para no saturar el servidor."""
    t = random.uniform(min_sec, max_sec)
    log.info("Esperando %.1f s antes de la siguiente petición…", t)
    time.sleep(t)


def parsear_fecha_revolico(texto_fecha: Optional[str], fecha_actual: date) -> Optional[date]:
    """Convierte la fecha de Revolico a objeto date.

    Soporta formatos:
      - Relativo: "hace 7 días", "hace un día", "hace 3 horas"
      - Absoluto: "18 ago 2026", "25 dic 2025"
    """
    if not texto_fecha:
        return None

    texto_fecha = texto_fecha.strip().lower()

    # --- Formato relativo: "hace X días" ---
    m_rel = re.match(r"hace\s+(\d+)\s+días?", texto_fecha)
    if m_rel:
        dias = int(m_rel.group(1))
        return fecha_actual - timedelta(days=dias)

    # "hace un día"
    if re.search(r"hace\s+un\s+día", texto_fecha):
        return fecha_actual - timedelta(days=1)

    # "hace X horas" -> dentro del rango de 30 días
    m_horas = re.match(r"hace\s+(\d+)\s+horas?", texto_fecha)
    if m_horas:
        return fecha_actual

    # --- Formato absoluto: "18 ago 2026" ---
    m_abs = re.match(r"(\d{1,2})\s+(\w+)\s+(\d{4})", texto_fecha)
    if m_abs:
        dia, mes_nombre, anio = int(m_abs.group(1)), m_abs.group(2), int(m_abs.group(3))
        MESES_ES = {
            "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
            "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
        }
        mes = MESES_ES.get(mes_nombre[:3])
        if mes:
            try:
                return date(anio, mes, dia)
            except ValueError:
                log.warning("Fecha inválida parseada: %s", texto_fecha)
                return None

    log.warning("Formato de fecha no reconocido: %s", texto_fecha)
    return None


def es_fecha_valida(fecha_obj: Optional[date], fecha_limite: date) -> bool:
    """Devuelve True si la fecha es >= fecha_limite (dentro de los 30 días)."""
    if fecha_obj is None:
        return False
    return fecha_obj >= fecha_limite


def es_relevante(texto: Optional[str]) -> bool:
    """Check si el texto contiene algún término de relevancia de paneles solares."""
    if not texto:
        return False
    texto_lower = texto.lower()
    for termino in TERMINOS_RELEVANCIA:
        if termino.lower() in texto_lower:
            return True
    return False


# ---------------------------------------------------------------------------
# Descarga de páginas
# ---------------------------------------------------------------------------

def obtener_pagina(url: str, max_intentos: int = 5) -> Optional[BeautifulSoup]:
    """Intenta descargar y parsear la página HTML.

    Intenta primero con cloudscraper si está disponible, si no, usa requests normal.
    Realiza reintentos con backoff exponencial ante errores 403/Cloudflare.

    Retorna un objeto BeautifulSoup o None si falla tras los intentos.
    """
    # Determinar cliente HTTP
    if HAS_CLOUDSCRAPER:
        scraper = cloudscraper.create_scraper()
        log.info("Usando cloudscraper para bypass Cloudflare")
    else:
        import requests
        scraper = requests
        log.info("Usando requests normal (cloudscraper no disponible)")

    for intento in range(1, max_intentos + 1):
        headers = user_agent_rotator()
        try:
            log.info("Descargiendo (intento %d): %s", intento, url)
            resp = scraper.get(url, headers=headers, timeout=20)

            # Manejo de status codes
            if resp.status_code == 403:
                log.warning("Intento %d: recibió 403 (posible Cloudflare) para %s", intento, url)
                if intento < max_intentos:
                    backoff = 2 ** (intento - 1)  # 1, 2, 4, 8...
                    log.info("Backoff %d s antes de reintentar…", backoff)
                    time.sleep(backoff)
                    continue
                else:
                    log.error("Excedidos los intentos 403 para %s. Cloudflare bloquea peticiones automatizadas.", url)
                    # Even after max retries, return None gracefully
                    return None

            if resp.status_code != 200:
                log.error("Status %d para %s", resp.status_code, url)
                if intento < max_intentos:
                    time.sleep(2 ** (intento - 1))
                    continue
                return None

            # Detectar página de desafío Cloudflare en el HTML (aunque status sea 200)
            html_lower = resp.text.lower()
            if "challenge" in html_lower or "cloudflare" in html_lower:
                log.warning("Desafío Cloudflare detectado en %s (intento %d)", url, intento)
                if intento < max_intentos:
                    time.sleep(2 ** intento)
                    continue
                return None

            return BeautifulSoup(resp.text, "html.parser")

        except Exception as exc:
            log.error("Error en intento %d para %s: %s", intento, url, exc)
            if intento < max_intentos:
                time.sleep(2 ** (intento - 1))
                continue
            return None

    return None


# ---------------------------------------------------------------------------
# Parsing del listado de anuncios
# ---------------------------------------------------------------------------

def parsear_listado(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """Extrae los anuncios de una página de listado de Revolico.

    Retorna lista de diccionarios con campos básicos: titulo, url, fecha_texto, etc.
    """
    anuncios = []

    # Los contenedores de cada anuncio: según inspección, son div.listing o article.listing
    cards = soup.select("div.listing, article.listing")

    if not cards:
        # Fallback: probar con clases genéricas
        cards = soup.select(".result, .ad, .item")
        log.info("Usando selector alternativo para tarjetas: .result, .ad, .item")

    log.info("Se encontraron %d tarjetas de anuncio en este listado", len(cards))

    for idx, card in enumerate(cards, start=1):
        try:
            # --- Título ---
            title_tag = card.select_one("h3 a.title, a.title")
            titulo = title_tag.get_text(strip=True) if title_tag else None
            if not titulo:
                continue  # Sin título, saltar

            # --- URL ---
            href = title_tag["href"] if title_tag else None
            url = href if href and href.startswith("http") else (f"{BASE_URL}{href}" if href else None)

            # --- Fecha (del listado) ---
            date_tag = card.select_one("span.date, time.date")
            fecha_texto = date_tag.get_text(strip=True) if date_tag else None

            # --- Precio y moneda (del listado) ---
            price_tag = card.select_one("span.price")
            price_texto = price_tag.get_text(strip=True) if price_tag else None

            # --- Ubicación ---
            location_tag = card.select_one("span.location")
            ubicacion = location_tag.get_text(strip=True) if location_tag else None

            anuncio_base = {
                "titulo": titulo,
                "url": url,
                "fecha_texto": fecha_texto,
                "precio_texto": price_texto,
                "ubicacion": ubicacion,
            }
            anuncios.append(anuncio_base)

        except Exception as exc:
            log.error("Error procesando tarjeta %d en listado: %s", idx, exc)
            continue

    return anuncios


# ---------------------------------------------------------------------------
# Parsing de la página de detalle
# ---------------------------------------------------------------------------

def parsear_detalle(url: str) -> Dict[str, Any]:
    """Accede a la página de detalle de un anuncio y extrae campos completos.

    Retorna dict con: precio, moneda, potencia_w, marca, modelo, descripcion,
    fecha_publicacion, url.
    """
    # Usar obtener_pagina que ya maneja cloudscraper/requests y reintentos
    soup = obtener_pagina(url)
    if soup is None:
        return {
            "precio": None, "moneda": None, "potencia_w": None,
            "marca": None, "modelo": None, "descripcion": None,
            "fecha_publicacion": None, "url": url,
        }

    try:
        # --- Descripción ---
        desc_tag = soup.select_one("div.description, p.description, .summary, .ad-description")
        descripcion = desc_tag.get_text(strip=True) if desc_tag else None

        # --- Precio y moneda ---
        precio_numero = None
        moneda = None

        # Buscar patrón de precio en el texto completo de la página
        texto_completo = soup.get_text(" ", strip=True)
        price_patterns = [
            r"(\d+(?:\.\d+)?)\s*(USD|CUP|MLC)\b",
            r"\b(USD|CUP|MLC)\s*(\d+(?:\.\d+)?)?",
        ]
        for pattern in price_patterns:
            m = re.search(pattern, texto_completo, re.IGNORECASE)
            if m:
                if m.group(1):  # primer grupo es número
                    try:
                        precio_numero = float(m.group(1))
                        moneda = m.group(2).upper()
                    except ValueError:
                        pass
                else:  # segundo grupo es número
                    try:
                        precio_numero = float(m.group(2))
                        moneda = m.group(1).upper()
                    except ValueError:
                        pass
                break

        # Si no se encontró precio en el texto completo, intentar en elements específicos
        if precio_numero is None:
            price_tags = soup.select("span.price, .price, .valor-precio")
            for pt in price_tags:
                pt_text = pt.get_text(strip=True)
                m = re.search(r"(\d+(?:\.\d+)?)\s*(USD|CUP|MLC)?", pt_text, re.IGNORECASE)
                if m:
                    try:
                        precio_numero = float(m.group(1))
                        moneda = m.group(2).upper() if m.group(2) else None
                        break
                    except ValueError:
                        continue

        # --- Potencia (W) ---
        potencia_w = None
        # Buscar patrones como "590W", "600 w", "590W" en el texto completo
        potencia_match = re.search(r"(\d{2,3})\s*W\b", texto_completo, re.IGNORECASE)
        if potencia_match:
            try:
                potencia_w = int(potencia_match.group(1))
            except ValueError:
                potencia_w = None

        # Si no encontrado en texto completo, buscar en descripción
        if potencia_w is None and descripcion:
            potencia_match = re.search(r"(\d{2,3})\s*W\b", descripcion, re.IGNORECASE)
            if potencia_match:
                try:
                    potencia_w = int(potencia_match.group(1))
                except ValueError:
                    potencia_w = None

        # --- Marca ---
        marca = None
        titulo_pagina = soup.find("title")
        titulo_pagina_texto = titulo_pagina.get_text(strip=True) if titulo_pagina else ""

        text_combined = f"{titulo_pagina_texto} {descripcion or ''}"
        # Buscar patrón de marca: palabra con mayúscula inicial, no es palabra común
        palabra_comunes = {"el", "la", "y", "para", "con", "en", "el", "el", "las", "los", "un", "una"}
        # Buscar todas las palabras que coincidan con patrón de marca
        palabras = re.findall(r"\b([A-Z][a-z]{2,})\b", text_combined)
        for p in palabras:
            if p.lower() not in palabra_comunes and len(p) > 2:
                marca = p
                break

        # --- Modelo ---
        modelo = None
        # El modelotypically se deja como None si no se identifica claramente
        # Podría extraerse patrones después de la marca, pero para simplicidad dejamos None

        # --- Fecha de publicación ---
        fecha_publicacion = None
        date_tags = soup.select("span.date, time.date, .fecha-publicacion, .date-anuncio")
        for dt in date_tags:
            dt_texto = dt.get_text(strip=True)
            fecha_calculada = parsear_fecha_revolico(dt_texto, FECHA_EJECUCION)
            if fecha_calculada and es_fecha_valida(fecha_calculada, FECHA_LIMITE):
                fecha_publicacion = fecha_calculada.strftime("%Y-%m-%d")
                break

        resultado = {
            "precio": precio_numero,
            "moneda": moneda,
            "potencia_w": potencia_w,
            "marca": marca,
            "modelo": modelo,
            "descripcion": descripcion,
            "fecha_publicacion": fecha_publicacion,
            "url": url,
        }
        return resultado

    except Exception as exc:
        log.error("Error parseando detalle %s: %s", url, exc)
        return {
            "precio": None, "moneda": None, "potencia_w": None,
            "marca": None, "modelo": None, "descripcion": None,
            "fecha_publicacion": None, "url": url,
        }


# ---------------------------------------------------------------------------
# Filtros
# ---------------------------------------------------------------------------

def filtrar_por_fecha(anuncio: Dict[str, Any], fecha_limite: date) -> bool:
    """Retorna True si el anuncio está dentro de la ventana de 30 días.

    Si fecha_publicacion es None, el anuncio se descarta (no se incluye en JSON final).
    """
    fp = anuncio.get("fecha_publicacion")
    if fp is None:
        return False  # Sin fecha -> descartar (requisito: solo anuncios de últimos 30 días)
    try:
        fecha = datetime.strptime(fp, "%Y-%m-%d").date()
    except ValueError:
        return False
    return fecha >= fecha_limite


def filtrar_por_relevancia(anuncio: Dict[str, Any]) -> bool:
    """Retorna True si el título o descripción contiene términos de paneles solares."""
    titulo = anuncio.get("titulo", "")
    descripcion = anuncio.get("descripcion", "")
    # Check en título
    if es_relevante(titulo):
        return True
    # Check en descripción
    if es_relevante(descripcion):
        return True
    return False


# ---------------------------------------------------------------------------
# Exportación
# ---------------------------------------------------------------------------

def exportar_json(anuncios: List[Dict[str, Any]], archivo_salida: Path) -> None:
    """Exporta la lista de anuncios a un archivo JSON."""

    # Asegurar que todas las claves esperadas existan en cada registro
    campos_obligatorios = [
        "titulo", "precio", "moneda", "potencia_w", "marca", "modelo",
        "descripcion", "ubicacion", "fecha_publicacion", "url", "fuente"
    ]

    for a in anuncios:
        for campos in campos_obligatorios:
            if campos not in a:
                a[campos] = None
        # Asegurar que fuente sea "revolico.com"
        a["fuente"] = "revolico.com"

    # Crear directorio si no existe
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with open(archivo_salida, "w", encoding="utf-8") as f:
        json.dump(anuncios, f, ensure_ascii=False, indent=2)

    log.info("Dataset guardado en %s (%d registros)", archivo_salida, len(anuncios))


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------

def main() -> None:
    """Punto de entrada que orquesta el scraping completo."""
    log.info("=== Inicio scraper Revolico - Paneles Solares La Habana ===")
    log.info("Fecha de ejecución: %s", FECHA_EJECUCION)
    log.info("Fecha límite (hace 30 días): %s", FECHA_LIMITE)
    log.info("URL de búsqueda: %s", SEARCH_URL)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Verificar si el archivo ya existe y tiene contenido
    if OUTPUT_FILE.exists():
        log.warning("El archivo %s ya existe, será sobrescrito.", OUTPUT_FILE)

    todos_los_anuncios: List[Dict[str, Any]] = []
    anuncios_validos_count = 0
    descartados_fecha = 0
    descartados_relevancia = 0
    errores = 0

    # --- Paginación ---
    max_paginas = 200  # Límite de seguridad para evitar bucles infinitos
    pagina_actual = 1

    while pagina_actual <= max_paginas:
        url_pagina = f"{SEARCH_URL}&page={pagina_actual}"
        log.info("=== Cargando página %d: %s ===", pagina_actual, url_pagina)

        soup = obtener_pagina(url_pagina)
        if soup is None:
            log.error("No se pudo obtener la página %d, abortando paginación.", pagina_actual)
            # Cloudflare block or other error - finish gracefully
            break

        # Parsear el listado
        cartas = parsear_listado(soup)
        log.info("Página %d: extraídos %d anuncios bruteados", pagina_actual, len(cartas))

        if not cartas:
            log.info("No más anuncios en la página %d, terminando paginación.", pagina_actual)
            break

        # Para cada anuncio bruteado, ir a detalle y aplicar filtros
        for idx, carta in enumerate(cartas, start=1):
            try:
                url = carta.get("url")
                if not url:
                    log.warning("Anuncio %d en página %d sin URL, skipping", idx, pagina_actual)
                    errores += 1
                    continue

                # Parsear página de detalle
                detalle = parsear_detalle(url)

                # --- Filtro de relevancia ---
                if not filtrar_por_relevancia(detalle):
                    descartados_relevancia += 1
                    #log.info("Anuncio '%s' descarte por relevancia", detalle.get("titulo"))
                    continue

                # --- Filtro de fecha ---
                if not filtrar_por_fecha(detalle, FECHA_LIMITE):
                    descartados_fecha += 1
                    #log.info("Anuncio '%s' descarte por fecha (fuera de ventana 30d)", detalle.get("titulo"))
                    continue

                # --- Construir anuncio final ---
                anuncio_final = {
                    "titulo": detalle.get("titulo") or carta.get("titulo"),
                    "precio": detalle.get("precio"),
                    "moneda": detalle.get("moneda"),
                    "potencia_w": detalle.get("potencia_w"),
                    "marca": detalle.get("marca"),
                    "modelo": detalle.get("modelo"),
                    "descripcion": detalle.get("descripcion"),
                    "ubicacion": detalle.get("ubicacion") or carta.get("ubicacion"),
                    "fecha_publicacion": detalle.get("fecha_publicacion"),
                    "url": url,
                    "fuente": "revolico.com",
                }

                # Verificar que los campos críticos no sean todos nulos
                if not anuncio_final["titulo"] or not anuncio_final["url"]:
                    log.warning("Anuncio sin título o URL, skipping a pesar de pasar filtros")
                    errores += 1
                    continue

                todos_los_anuncios.append(anuncio_final)
                anuncios_validos_count += 1

                # Log INFO cada cierto número de anuncios
                if anuncios_validos_count % 10 == 0:
                    log.info("Progreso: %d anuncios válidos acumulados", anuncios_validos_count)

                # Delay entre extracciones de detalle para ser respetuosos
                delay_aleatorio(1.0, 2.0)

            except Exception as exc:
                log.error("Error inesperado procesando anuncio %d en página %d: %s", idx, pagina_actual, exc)
                errores += 1
                continue

        pagina_actual += 1
        # Delay entre páginas (excepto después de la última)
        if pagina_actual <= max_paginas:
            delay_aleatorio(2.0, 4.0)

    # --- Deduplicación por URL ---
    visto = set()
    anuncios_unicos = []
    for a in todos_los_anuncios:
        u = a.get("url")
        if u and u not in visto:
            visto.add(u)
            anuncios_unicos.append(a)
        elif u:
            log.info("Anuncio duplicado eliminado por URL")

    log.info("Deduplicación completada: %d -> %d anuncios únicos", len(todos_los_anuncios), len(anuncios_unicos))

    # --- Contar estadísticas para el reporte final ---
    con_precio = sum(1 for a in anuncios_unicos if a.get("precio") is not None)
    con_moneda = sum(1 for a in anuncios_unicos if a.get("moneda") is not None)
    porcentaje_precio_moneda = (con_precio / len(anuncios_unicos) * 100) if anuncios_unicos else 0

    # --- Reporte final (formato requerido) ---
    log.info("Anuncios válidos: %d", len(anuncios_unicos))
    log.info("Descartados por fecha: %d", descartados_fecha)
    log.info("Descartados por relevancia: %d", descartados_relevancia)
    log.error("Errores: %d", errores)
    log.info("Anuncios válidos: %d | Descartados por fecha: %d | Descartados por relevancia: %d | Errores: %d",
             len(anuncios_unicos), descartados_fecha, descartados_relevancia, errores)

    # Alerta si el 70% no tiene precio/moneda
    if porcentaje_precio_moneda < 70 and len(anuncios_unicos) > 0:
        log.warning("ALERTA: Solo el %.1f%% de los anuncios tienen precio y moneda definidos (umbral 70%%)",
                    porcentaje_precio_moneda)
    else:
        if len(anuncios_unicos) > 0:
            log.info("El %.1f%% de los anuncios tienen precio y moneda definidos (cumple umbral 70%%)",
                     porcentaje_precio_moneda)
        else:
            log.info("No hay anuncios para reportar porcentaje de precio/moneda")

    # --- Exportación ---
    exportar_json(anuncios_unicos, OUTPUT_FILE)

    log.info("=== Fin scraper Revolico ===")


if __name__ == "__main__":
    main()