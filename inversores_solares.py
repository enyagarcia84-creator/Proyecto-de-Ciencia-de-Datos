#!/usr/bin/env python3
"""Scraper para extraer anuncios de inversores solares de Revolico.com en La Habana.

Extrae anuncios de la sección Hogar → Plantas y Estaciones de Energía,
filtrando por: ventana temporal 30 días y relevancia de inversores solares.
Incluye conversión de potencia de kW a W y clasificación por tipo (nominal/pico).
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

import requests
from bs4 import BeautifulSoup
from dateutil.parser import parse as dateutil_parse

# ---------------------------------------------------------------------------
# Configuración y constantes
# ---------------------------------------------------------------------------

BASE_URL = "https://www.revolico.com"
# URL base de búsqueda: Hogar → Plantas y Estaciones de Energía en La Habana
SEARCH_URL = (
    f"{BASE_URL}/search?category=hogar&subcategory=hogar-plantas-y-estaciones-de-energia"
    f"&province=la-habana&order=date&page=1"
)
OUTPUT_DIR = Path("./output")
OUTPUT_FILE = OUTPUT_DIR / "inversores_solares_la_habana.json"

# Ventana temporal: últimos 30 días
FECHA_EJECUCION: date = date.today()
FECHA_LIMITE: date = FECHA_EJECUCION - timedelta(days=30)

# Términos de relevancia para filtrar inversores solares
TERMINOS_RELEVANCIA = [
    "inversor solar", "inversor híbrido", "inversor off-grid", "inversor onda pura",
    "inverter solar", "inversor MPPT", "inversor cargador", "estación de energía",
    "inversor 24V", "inversor 48V", "inversor 72V",
    # Variantes en inglés comúnmente usadas
    "solar inverter", "hybrid inverter", "off-grid inverter", "pure sine wave",
]

# User-Agents rotativos para evitar bloques
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Safari/605.1.15",
]

# Marcas frecuentes en el mercado cubano de inversores solares
MARCAS_FRECUENTES = [
    "SUMRY", "SAKO", "Felicity Solar", "MUST", "EcoFlow", "OUPES",
    "Unizuki", "LVYUAN", "Growatt", "Victron", "Amptron", "Hoymiles",
    "SolarEdge", "Multec", "Novax", "WindyNation",
]

# Logging setup: INFO para progreso, ERROR para fallos, WARNING para datos faltantes
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("revolico_inversores")


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def user_agent_rotator() -> dict:
    """Retorna headers con User-Agent aleatorio de la lista definida."""
    return {"User-Agent": random.choice(USER_AGENTS)}


def delay_aleatorio(min_sec: float = 1.0, max_sec: float = 3.0) -> None:
    """Pausa aleatoria entre peticiones para no saturar el servidor (1-3 s)."""
    t = random.uniform(min_sec, max_sec)
    log.info("Esperando %.1f s antes de la siguiente petición…", t)
    time.sleep(t)


def limpiar_precio(texto: Optional[str]) -> Optional[float]:
    """Limpia el texto del precio: quita comas, símbolos de moneda y devuelve número.

    Ejemplos:
      "1,650 USD" -> 1650.0
      "440 USD" -> 440.0
      "1 CUP" -> 1.0
      null si no hay texto o no se puede parsear
    """
    if not texto:
        return None

    texto = texto.strip()

    # Caso: "1 CUP" o "180 CUP" -> conservar como 1.0 o 180.0
    m_cup = re.match(r"^(\d+(?:[.,]\d+)?)\s*CUP\b", texto, re.IGNORECASE)
    if m_cup:
        try:
            return float(m_cup.group(1).replace(",", "."))
        except ValueError:
            return None

    # Caso general: quita cualquier símbolo USD/CUP/MLC al final y quitas comas
    texto_limpio = re.sub(r"[USD|CUP|MLC]$", "", texto, flags=re.IGNORECASE)
    texto_limpio = texto_limpio.replace(",", ".").strip()

    try:
        return float(texto_limpio)
    except ValueError:
        return None


def es_relevante(texto: Optional[str]) -> bool:
    """Check si el texto contiene algún término de relevancia de inversores solares.

    Busca los 11 términos definidos en TERMINOS_RELEVANCIA, sin importar mayúsculas/minúsculas.
    """
    if not texto:
        return False

    texto_lower = texto.lower()

    for termino in TERMINOS_RELEVANCIA:
        if termino.lower() in texto_lower:
            return True

    return False


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

    # Intento con dateutil como fallback
    try:
        fecha_dt = dateutil_parse(texto_fecha, dayfirst=False)
        return fecha_dt.date()
    except Exception:
        log.warning("Formato de fecha no reconocido: %s", texto_fecha)
        return None


def es_fecha_valida(fecha_obj: Optional[date], fecha_limite: date) -> bool:
    """Devuelve True si la fecha es >= fecha_limite (dentro de los 30 días)."""
    if fecha_obj is None:
        return False
    return fecha_obj >= fecha_limite


def identificar_marca(texto: Optional[str]) -> Optional[str]:
    """Intenta identificar la marca del inversor en el texto.

    Busca coincidencias con la lista MARCAS_FRECUENTES.
    Si no encuentra ninguna, devuelve None.
    """
    if not texto:
        return None

    texto_lower = texto.lower()
    for marca in MARCAS_FRECUENTES:
        if marca.lower() in texto_lower:
            patron = re.escape(marca.lower())
            match = re.search(patron, texto, re.IGNORECASE)
            if match:
                return texto[match.start():match.end()]
    return None


def convertir_potencia_a_w(potencia_texto: Optional[str]) -> Optional[int]:
    """Convierte el texto de potencia a enteros en watts.

    Soporta:
      - "4000W" -> 4000
      - "4kw" -> 4000
      - "3.6kW" -> 3600
      - "1750 watts continuos" -> 1750
      - Ningún patrón -> None

    También detecta si es potencia nominal o pico y devuelve el valor
    junto con el tipo en un diccionario (aunque la función retorna solo el entero
    para compatibilidad con el campo potencia_w; el tipo se documenta en comentarios).
    """
    if not potencia_texto:
        return None

    texto = potencia_texto.strip().lower()

    # Buscar patrón "numero kW" o "numero.kW"
    m_kw = re.match(r"(\d+(?:\.\d+)?)k?w", texto)
    if m_kw:
        try:
            valor_kw = float(m_kw.group(1))
            return int(valor_kw * 1000)
        except ValueError:
            return None

    # Buscar patrón "numeroW" directo
    m_w = re.search(r"(\d{1,4})w", texto)
    if m_w:
        try:
            return int(m_w.group(1))
        except ValueError:
            return None

    # Buscar patrón "numero watts" o "numero watts continuos"
    m_watts = re.search(r"(\d{1,4})\s*watts", texto)
    if m_watts:
        try:
            return int(m_watts.group(1))
        except ValueError:
            return None

    # Buscar "pico" o "máxima" para documentar el tipo
    if "pico" in texto or "máxima" in texto or "peak" in texto:
        # Podría tener un número antes; si no, regresamos None y el llamador
        # decide anotar potencia_tipo='pico' por aparte
        pass

    return None


def detectar_tipo_potencia(potencia_texto: Optional[str]) -> Optional[str]:
    """Detecta si la potencia es 'nominal' o 'pico' basándose en el texto.

    Returns 'nominal', 'pico', o None si no se puede determinar.
    """
    if not potencia_texto:
        return None

    texto_lower = potencia_texto.lower()
    if "pico" in texto_lower or "máxima" in texto_lower or "peak" in texto_lower:
        return "pico"
    if "nominal" in texto_lower or "continua" in texto_lower or " continuo" in texto_lower:
        return "nominal"
    return None


# ---------------------------------------------------------------------------
# Descarga de páginas
# ---------------------------------------------------------------------------

def obtener_pagina(url: str, max_intentos: int = 5) -> Optional[BeautifulSoup]:
    """Intenta descargar y parsear la página HTML con reintentos y backoff exponencial.

    Usa requests con rotación de User-Agent.
    Retorna un objeto BeautifulSoup o None si falla tras los intentos.
    """
    for intento in range(1, max_intentos + 1):
        headers = user_agent_rotator()
        try:
            log.info("Descargiendo (intento %d): %s", intento, url)
            resp = requests.get(url, headers=headers, timeout=20)

            if resp.status_code == 403:
                log.warning("Intento %d: recibió 403 (posible Cloudflare) para %s", intento, url)
                if intento < max_intentos:
                    backoff = 2 ** (intento - 1)  # 1, 2, 4, 8...
                    log.info("Backoff %d s antes de reintentar…", backoff)
                    time.sleep(backoff)
                    continue
                else:
                    log.error("Excedidos los intentos 403 para %s. Cloudflare bloquea peticiones automatizadas.", url)
                    return None

            if resp.status_code != 200:
                log.error("Status %d para %s", resp.status_code, url)
                if intento < max_intentos:
                    time.sleep(2 ** (intento - 1))
                    continue
                return None

            # Detectar página de desafío Cloudflare en el HTML
            html_lower = resp.text.lower()
            if "challenge" in html_lower or "cloudflare" in html_lower:
                log.warning("Desafío Cloudflare detectado en %s (intento %d)", url, intento)
                if intento < max_intentos:
                    time.sleep(2 ** intento)
                    continue
                return None

            return BeautifulSoup(resp.text, "lxml")

        except requests.RequestException as exc:
            log.error("Error de red en intento %d para %s: %s", intento, url, exc)
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

    Retorna lista de diccionarios con campos básicos: titulo, url, fecha_texto, precio_texto, ubicacion.
    """
    anuncios = []

    cards = soup.select("div.listing, article.listing")

    if not cards:
        cards = soup.select(".result, .ad, .item")
        log.info("Usando selector alternativo para tarjetas: .result, .ad, .item")

    log.info("Se encontraron %d tarjetas de anuncio en este listado", len(cards))

    for idx, card in enumerate(cards, start=1):
        try:
            title_tag = card.select_one("h3 a.title, a.title")
            titulo = title_tag.get_text(strip=True) if title_tag else None
            if not titulo:
                continue

            href = title_tag["href"] if title_tag else None
            url = href if href and href.startswith("http") else (f"{BASE_URL}{href}" if href else None)

            date_tag = card.select_one("span.date, time.date")
            fecha_texto = date_tag.get_text(strip=True) if date_tag else None

            price_tag = card.select_one("span.price")
            precio_texto = price_tag.get_text(strip=True) if price_tag else None

            location_tag = card.select_one("span.location")
            ubicacion = location_tag.get_text(strip=True) if location_tag else None

            anuncio_base = {
                "titulo": titulo,
                "url": url,
                "fecha_texto": fecha_texto,
                "precio_texto": precio_texto,
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

    Retorna dict con: precio (float), moneda (str), potencia_w (int|null),
    marca (str|null), modelo (str|null), titulo (str|null),
    ubicacion (str|null), fecha_publicacion (str YYYY-MM-DD|null),
    url, fuente (str "revolico.com"), potencia_tipo (str "nominal"|"pico"|null).
    """
    soup = obtener_pagina(url)
    if soup is None:
        return {
            "precio": None, "moneda": None, "potencia_w": None,
            "marca": None, "modelo": None, "titulo": None,
            "ubicacion": None, "fecha_publicacion": None, "url": url,
            "fuente": "revolico.com", "potencia_tipo": None,
        }

    try:
        # --- Título de la página ---
        title_tag = soup.find("title")
        titulo_pagina = title_tag.get_text(strip=True) if title_tag else ""

        # --- Descripción (aunque en el listado ya viene; aquí la refinamos) ---
        desc_tag = soup.select_one("div.description, p.description, .summary, .ad-description")
        descripcion = desc_tag.get_text(strip=True) if desc_tag else None

        # --- Precio y moneda ---
        precio_numero = limpiar_precio(texto_completo := soup.get_text(" ", strip=True))
        moneda = None
        m_moneda = re.search(r"(USD|CUP|MLC)\b", texto_completo, re.IGNORECASE)
        if m_moneda:
            moneda = m_moneda.group(1).upper()

        # --- Potencia (W) y tipo ---
        potencia_w = None
        potencia_tipo = None

        # 1. Buscar en el texto completo patrones W, kW
        #    Si hay kW, convertir a W y documentar tipo
        #    Si hay W directo, usar y documentar tipo según contexto

        # Extraer especificación de energía del texto completo
        spec_energia = extraer_especificacion_energia(texto_completo)

        # Buscar "5000W" u otros patrones W directamente en el texto
        w_match = re.search(r"(\d{1,4})W\b", texto_completo, re.IGNORECASE)
        if w_match:
            try:
                potencia_w = int(w_match.group(1))
                # Determinar tipo: si el texto también tiene "pico" o "máxima", es pico
                if detectar_tipo_potencia(texto_completo) == "pico":
                    potencia_tipo = "pico"
                else:
                    potencia_tipo = "nominal"
            except ValueError:
                potencia_w = None

        # Si no se encontró W directo, intentar con kW → W
        if potencia_w is None:
            # Ya extraer_especificacion_energia buscó kWh/Ah/V/W, pero para potencia_w
            # necesitamos solo el valor numérico en W
            # Re-buscamos patrones kW
            m_kw = re.search(r"(\d+(?:\.\d+)?)k?w\b", texto_completo, re.IGNORECASE)
            if m_kw:
                try:
                    valor_kw = float(m_kw.group(1))
                    potencia_w = int(valor_kw * 1000)
                    # Determinar tipo
                    if detectar_tipo_potencia(texto_completo) == "pico":
                        potencia_tipo = "pico"
                    else:
                        potencia_tipo = "nominal"
                except ValueError:
                    potencia_w = None

        # --- Marca ---
        marca = identificar_marca(texto_completo)

        # --- Modelo ---
        modelo = None
        # El modelo typically se deja como None si no se identifica claramente
        # después de la marca. Se podría heurísticamente extraer después de la marca,
        # pero para simplicidad y evitar falsos positivos, lo dejamos None.

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
            "titulo": titulo_pagina,  # Usamos el título de la página o dejamos None
            "ubicacion": None,  # Se sobreescribirá con la del listado en main()
            "fecha_publicacion": fecha_publicacion,
            "url": url,
            "fuente": "revolico.com",
            "potencia_tipo": potencia_tipo,
        }
        return resultado

    except Exception as exc:
        log.error("Error parseando detalle %s: %s", url, exc)
        return {
            "precio": None, "moneda": None, "potencia_w": None,
            "marca": None, "modelo": None, "titulo": None,
            "ubicacion": None, "fecha_publicacion": None, "url": url,
            "fuente": "revolico.com", "potencia_tipo": None,
        }


def extraer_especificacion_energia(texto: Optional[str]) -> Optional[str]:
    """Extrae la especificación de energía (kW, kWh, V, etc.) del texto.

    Devuelve el valor string tal como aparece, o None si no hay patrón.
    Útil para documentar hallazgos en logs.
    """
    if not texto:
        return None

    patrones = [
        r"(\d+(?:\.\d+)?)\s*kW",
        r"(\d+(?:\.\d+)?)\s*kWh",
        r"(\d+(?:\.\d+)?)\s*V",
        r"(\d{1,4})W",
    ]

    for patron in patrones:
        m = re.search(patron, texto, re.IGNORECASE)
        if m:
            return m.group(0)

    return None


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
    """Retorna True si el título o descripción contiene términos de inversores solares."""
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
# Deduplicación
# ---------------------------------------------------------------------------

def deduplicar_por_url(anuncios: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Elimina anuncios duplicados por url, conservando el primero visto."""
    visto = set()
    unicos = []
    for a in anuncios:
        u = a.get("url")
        if u and u not in visto:
            visto.add(u)
            unicos.append(a)
        elif u:
            log.info("Anuncio duplicado eliminado por URL: ...%s", u[-20:] if len(u) > 20 else u)
    return unicos


# ---------------------------------------------------------------------------
# Exportación
# ---------------------------------------------------------------------------

def exportar_json(anuncios: List[Dict[str, Any]], archivo_salida: Path) -> None:
    """Exporta la lista de anuncios a un archivo JSON.

    Asegura que todas las claves esperadas existan en cada registro.
    Los campos adicionales (potencia_tipo) se conservan tal como vengan.
    """
    # Campos obligatorios que debe tener cada registro (aunque sean null)
    campos_obligatorios = [
        "titulo", "precio", "moneda", "potencia_w", "marca", "modelo",
        "ubicacion", "fecha_publicacion", "url", "fuente", "potencia_tipo"
    ]

    for a in anuncios:
        # Asegurar que los campos obligatorios existan
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
    log.info("=== Inicio scraper Revolico - Inversores Solares La Habana ===")
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
        if pagina_actual == 1:
            url_pagina = SEARCH_URL
        else:
            base = SEARCH_URL.replace("&page=1", "")
            url_pagina = f"{base}&page={pagina_actual}"

        log.info("=== Cargando página %d: %s ===", pagina_actual, url_pagina)

        soup = obtener_pagina(url_pagina)
        if soup is None:
            log.error("No se pudo obtener la página %d, abortando paginación.", pagina_actual)
            # Cloudflare block o otro error - terminar gracefully
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
                    #log.info("Anuncio '%s' descarte por relevancia", detalle.get("titulo"))
                    descartados_relevancia += 1
                    continue

                # --- Filtro de fecha ---
                if not filtrar_por_fecha(detalle, FECHA_LIMITE):
                    # Obtener fecha del listado para logging
                    fecha_listado = carta.get("fecha_texto")
                    descartados_fecha += 1
                    #log.info("Anuncio '%s' descarte por fecha (fuera de ventana 30d)", detalle.get("titulo"))
                    continue

                # --- Construir anuncio final ---
                # Nota: potencia_tipo y potencia_w ya vienen del detalle
                #ubicacion_anuncio = detalle.get("ubicacion") or carta.get("ubicacion")

                anuncio_final = {
                    "titulo": detalle.get("titulo") or carta.get("titulo"),
                    "precio": detalle.get("precio"),
                    "moneda": detalle.get("moneda"),
                    "potencia_w": detalle.get("potencia_w"),
                    "marca": detalle.get("marca"),
                    "modelo": detalle.get("modelo"),
                    "ubicacion": detalle.get("ubicacion") or carta.get("ubicacion"),
                    "fecha_publicacion": detalle.get("fecha_publicacion"),
                    "url": url,
                    "fuente": "revolico.com",
                    "potencia_tipo": detalle.get("potencia_tipo"),
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

                # Delay entre extracciones de detalle para ser respetuosos (1-2 s)
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
    anuncios_unicos = deduplicar_por_url(todos_los_anuncios)
    log.info("Deduplicación: %d -> %d anuncios únicos", len(todos_los_anuncios), len(anuncios_unicos))

    # --- Contar estadísticas para el reporte final ---
    con_precio = sum(1 for a in anuncios_unicos if a.get("precio") is not None)
    con_moneda = sum(1 for a in anuncios_unicos if a.get("moneda") is not None)
    porcentaje_precio_moneda = (con_precio / len(anuncios_unicos) * 100) if anuncios_unicos else 0

    # --- Reporte final (formato requerido) ---
    log.info("Anuncios válidos: %d", len(anuncios_unicos))
    log.info("Descartados por fecha: %d", descartados_fecha)
    log.info("Descartados por relevancia: %d", descartados_relevancia)
    log.error("Errores: %d", errores)
    log.info(
        "Anuncios válidos: %d | Descartados por fecha: %d | Descartados por relevancia: %d | Errores: %d",
        len(anuncios_unicos), descartados_fecha, descartados_relevancia, errores,
    )

    # Alerta si el 60% no tiene precio/moneda
    if porcentaje_precio_moneda < 60 and len(anuncios_unicos) > 0:
        log.warning(
            "ALERTA: Solo el %.1f%% de los anuncios tienen precio y moneda definidos (umbral 60%%)",
            porcentaje_precio_moneda,
        )
    else:
        if len(anuncios_unicos) > 0:
            log.info(
                "El %.1f%% de los anuncios tienen precio y moneda definidos (cumple umbral 60%%)",
                porcentaje_precio_moneda,
            )
        else:
            log.info("No hay anuncios para reportar porcentaje de precio/moneda")

    # --- Exportación ---
    exportar_json(anuncios_unicos, OUTPUT_FILE)

    log.info("=== Fin scraper Revolico ===")


if __name__ == "__main__":
    main()