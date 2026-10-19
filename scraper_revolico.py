#!/usr/bin/env python3
"""Scraper para extraer anuncios de paneles solares de Revolico.com.

Estrategia: Se accede a la categoria /h/plantas-y-estaciones-de-energia,
recorre paginación con ?page=N, extrae datos de cada anuncio y filtra
por fecha de publicación (últimos 30 días). Los datos se guardan en JSON.

Datos extraídos por anuncio: titulo, precio, descripcion, ubicacion,
fecha_publicacion, url, fuente.
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

# ---------------------------------------------------------------------------
# Configuración y constantes
# ---------------------------------------------------------------------------

BASE_URL = "https://www.revolico.com"
CATEGORY_URL = f"{BASE_URL}/h/plantas-y-estaciones-de-energia"
OUTPUT_DIR = Path("./output")
OUTPUT_FILE = OUTPUT_DIR / "anuncios_paneles_solares_revolico.json"

# Fecha de ejecución y corte (30 días atrás)
FECHA_EJECUCION: date = date.today()
FECHA_LIMITE: date = FECHA_EJECUCION - timedelta(days=30)

# User‑Agents rotativos para reducir riesgo de bloqueo
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Safari/605.1.15",
]

# Mapeo de nombres de meses en español a número (para fechas absolutas)
MESES_ES: Dict[str, int] = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
}

# Logging: INFO para progreso, ERROR para fallos
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("revolico")


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def user_agent_rotator() -> dict:
    """Retorna headers con User-Agent aleatorio de la lista definida."""
    return {"User-Agent": random.choice(USER_AGENTS)}


def delay_aleatorio(min_sec: float = 1.0, max_sec: float = 3.0) -> None:
    """Pausa aleatoria entre peticiones para no saturar el servidor."""
    t = random.uniform(min_sec, max_sec)
    log.info("Esperando %.1f s antes de la siguiente petición…", t)
    time.sleep(t)


def parsear_fecha_revolico(texto_fecha: str, fecha_actual: date) -> Optional[date]:
    """Convierte la fecha que aparece en Revolico a un objeto `date`.

    Soporta dos formatos observados en el sitio:
      - Relativo en español: "hace 7 días", "hace un día", "hace 3 horas"
      - Absoluto en formato "dd mmm aaaa", ej: "18 ago 2026"
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

    # "hace X horas" → considered within the 30‑day window
    m_horas = re.match(r"hace\s+(\d+)\s+horas?", texto_fecha)
    if m_horas:
        return fecha_actual

    # --- Formato absoluto: "18 ago 2026" ---
    m_abs = re.match(r"(\d{1,2})\s+(\w+)\s+(\d{4})", texto_fecha)
    if m_abs:
        dia, mes_nombre, anio = int(m_abs.group(1)), m_abs.group(2), int(m_abs.group(3))
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
    """Devuelve True si la fecha es >= fecha_limite (últimos 30 días)."""
    if fecha_obj is None:
        return False
    return fecha_obj >= fecha_limite


# ---------------------------------------------------------------------------
# Descarga de páginas con reintentos y backoff exponencial
# ---------------------------------------------------------------------------

def obtener_pagina(url: str, max_intentos: int = 5) -> Optional[BeautifulSoup]:
    """Intenta descargar y parsear la página HTML, con reintentos.

    Retorna un objeto BeautifulSoup o None si falla tras los intentos.
    Intenta rotar User-Agent y usa backoff exponencial ante 403/Cloudflare.
    """
    for intento in range(1, max_intentos + 1):
        headers = user_agent_rotator()
        try:
            log.info("Descargiendo (intento %d): %s", intento, url)
            resp = requests.get(url, headers=headers, timeout=20)

            # Cloudflare devuelve 403 o una página de "Just a moment"
            if resp.status_code == 403:
                log.warning("Intento %d: recibió 403 (posible Cloudflare) para %s", intento, url)
                if intento < max_intentos:
                    backoff = 2 ** (intento - 1)  # 1, 2, 4, 8 ...
                    log.info("Backoff %d s antes de reintentar…", backoff)
                    time.sleep(backoff)
                    continue
                else:
                    log.error("Excedidos los intentos 403 para %s", url)
                    return None

            if resp.status_code != 200:
                log.error("Status %d para %s", resp.status_code, url)
                return None

            # Detectar página de desafío Cloudflare en el HTML
            html_lower = resp.text.lower()
            if "challenge" in html_lower or "cloudflare" in html_lower:
                log.warning("Desafío Cloudflare detectado en %s (intento %d)", url, intento)
                if intento < max_intentos:
                    time.sleep(2 ** intento)
                    continue
                return None

            return BeautifulSoup(resp.text, "html.parser")

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

def parsear_listado(soup: BeautifulSoup, fecha_limite: date) -> List[Dict[str, Any]]:
    """Extrae los anuncios de una página de listado, aplicando filtro de fecha.

    Retorna una lista de diccionarios con los campos básicos.
    Cada diccionario contendrá: titulo, precio, descripcion, ubicacion,
    fecha_publicacion, url, fuente.
    """
    anuncios: List[Dict[str, Any]] = []

    # Los contenedores de cada anuncio pueden ser <div class="listing"> o <article>
    # según la disposición actual del sitio.
    cards = soup.select("div.listing, article.listing")

    # Fallback: si no encontramos los anteriores, probamos con clases genéricas
    if not cards:
        cards = soup.select(".result, .ad, .item")
        log.info("Usando selector alternativo para tarjetas: %s", ".result, .ad, .item")

    log.info("Se encontraron %d tarjetas de anuncio en este listado", len(cards))

    for idx, card in enumerate(cards, start=1):
        try:
            # --- Título ---
            title_tag = card.select_one("h3 a.title, a.title")
            titulo = title_tag.get_text(strip=True) if title_tag else None
            if not titulo:
                log.warning("Anuncio %d: título vacío, skipping", idx)
                continue

            # --- URL ---
            href = title_tag["href"] if title_tag else None
            url = href if href and href.startswith("http") else (f"{BASE_URL}{href}" if href else None)

            # --- Precio ---
            price_tag = card.select_one("span.price")
            precio = price_tag.get_text(strip=True) if price_tag else None

            # --- Fecha ---
            date_tag = card.select_one("span.date, time.date")
            fecha_texto = date_tag.get_text(strip=True) if date_tag else None
            fecha_publicacion = parsear_fecha_revolico(fecha_texto, FECHA_EJECUCION)

            # Aplicar filtro de fecha: si el anuncio tiene más de 30 días, lo descartamos
            # (aún así lo procesamos para no perder la estructura, pero no lo incluimos
            # en la salida final si está fuera de la ventana).
            if not es_fecha_valida(fecha_publicacion, fecha_limite):
                # Anuncio fuera de la ventana de 30 días; no lo agregaremos al resultado final
                # pero seguimos procesando el resto.
                pass

            # --- Ubicación ---
            location_tag = card.select_one("span.location")
            ubicacion = location_tag.get_text(strip=True) if location_tag else None

            # --- Descripción (opcional, puede no estar en el listado) ---
            desc_tag = card.select_one("p.description, .summary")
            descripcion = desc_tag.get_text(strip=True) if desc_tag else None

            anuncio = {
                "titulo": titulo,
                "precio": precio,
                "descripcion": descripcion,
                "ubicacion": ubicacion,
                "fecha_publicacion": fecha_publicacion.strftime("%Y-%m-%d") if fecha_publicacion else None,
                "url": url,
                "fuente": "revolico.com",
            }
            anuncios.append(anuncio)

        except Exception as exc:
            log.error("Error procesando tarjeta %d en listado: %s", idx, exc)
            continue

    return anuncios


# ---------------------------------------------------------------------------
# Paginación
# ---------------------------------------------------------------------------

def obtener_siguiente_pagina(soup: BeautifulSoup, pagina_actual: int) -> Optional[str]:
    """Intenta encontrar la URL de la siguiente página de resultados.

    Busca:
      1. Un enlace con texto "Siguiente" o "Next".
      2. Enlaces de paginación numérica para construir ?page=N.
    Retorna la URL completa o None si no hay más páginas.
    """
    # 1. Buscar enlace "Siguiente"
    next_link = soup.select_one("a.next, a.siguiente")
    if next_link and next_link.get("href"):
        href = next_link["href"]
        return f"{BASE_URL}{href}" if not href.startswith("http") else href

    # 2. Construir ?page=N a partir del número actual
    # El sitio usa ?page=X en la query string.
    try:
        siguiente = pagina_actual + 1
        return f"{BASE_URL}/h/plantas-y-estaciones-de-energia?page={siguiente}"
    except Exception:
        log.warning("No fue posible construir la URL de la próxima página.")
        return None


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------

def main() -> None:
    """Punto de entrada que orquesta el scraping completo.

    Flujo:
      1. Verifica directorio de salida.
      2. Itera sobre páginas de listado de paneles solares.
      3. Extrae anuncios y aplica filtro de fecha (últimos 30 días).
      4. Alcanza el volumen objetivo (500 anuncios) o agota páginas.
      5. Filtra definitivamente por fecha y exporta a JSON.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    log.info("=== Inicio scraper Revolico - Paneles Solares ===")
    log.info("Fecha de ejecución: %s", FECHA_EJECUCION)
    log.info("Fecha límite (hace 30 días): %s", FECHA_LIMITE)

    # Si ya existe un archivo previo, advertimos que será sobrescrito
    if OUTPUT_FILE.exists():
        log.warning("El archivo %s ya existe, será sobrescrito.", OUTPUT_FILE)

    todos_los_anuncios: List[Dict[str, Any]] = []
    pagina_actual = 1

    # URL inicial: categoría con orden por fecha y página 1
    url_actual = f"{CATEGORY_URL}?page=1&order=date"

    while url_actual and len(todos_los_anuncios) < 500:
        log.info("=== Descargando página %s ===", url_actual)

        soup = obtener_pagina(url_actual)
        if soup is None:
            log.error("No se pudo obtener la página %s, abortando paginación.", url_actual)
            break

        anuncios_pagina = parsear_listado(soup, FECHA_LIMITE)
        log.info(
            "Página %d: extraídos %d anuncios (total acumulado: %d)",
            pagina_actual,
            len(anuncios_pagina),
            len(todos_los_anuncios) + len(anuncios_pagina),
        )

        # Acumular anuncios (temporalmente; el filtro final los ajustará)
        for a in anuncios_pagina:
            # Solo guardamos aquellos cuya fecha aún no fue rechazada definitivamente
            if a["fecha_publicacion"] is not None and es_fecha_valida(a["fecha_publicacion"], FECHA_LIMITE):
                todos_los_anuncios.append(a)
            elif a["fecha_publicacion"] is None:
                # Si no tenemos fecha, conservamos con la advertencia de que
                # no podemos garantizar la ventana de 30 días; la filtración
                # final decidirá.
                log.info(
                    "Anuncio '%s' sin fecha detectable; se conserva para filtrado final.",
                    a.get("titulo"),
                )
                todos_los_anuncios.append(a)

        # Si ya alcanzamos el volumen objetivo, rompemos el bucle
        if len(todos_los_anuncios) >= 500:
            log.info("Se alcanzó el objetivo de 500 anuncios. Recortando lista.")
            todos_los_anuncios = todos_los_anuncios[:500]
            break

        # Buscar próxima página
        url_actual = obtener_siguiente_pagina(soup, pagina_actual)
        if url_actual is None:
            log.info("No hay más páginas disponibles o se alcanzó el fin de los resultados.")
            break

        # Retardo aleatorio entre 1 y 3 s antes de la siguiente petición
        pagina_actual += 1
        delay_aleatorio(1.0, 3.0)

    # ---------- Filtrado final estricto por ventana de 30 días ----------
    anuncios_filtrados: List[Dict[str, Any]] = []
    for a in todos_los_anuncios:
        if es_fecha_valida(a.get("fecha_publicacion"), FECHA_LIMITE):
            # Asegurar que el campo fecha_publicacion tenga el formato YYYY‑MM‑DD
            fp = a.get("fecha_publicacion")
            a["fecha_publicacion"] = fp.strftime("%Y-%m-%d") if fp else None
            anuncios_filtrados.append(a)
        else:
            log.info(
                "Anuncio '%s' descartado por fuera de la ventana temporal (fecha=%s).",
                a.get("titulo"),
                a.get("fecha_publicacion"),
            )

    log.info("Total de anuncios después del filtro estricto de 30 días: %d", len(anuncios_filtrados))

    # Asegurar que todos los objetos tengan 'fuente' = "revolico.com"
    for a in anuncios_filtrados:
        a["fuente"] = "revolico.com"

    # Ordenar por fecha descendente (más recientes primero)
    anuncios_filtrados.sort(
        key=lambda x: x.get("fecha_publicacion") or "", reverse=True
    )

    # ---------- Exportación a JSON ----------
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(anuncios_filtrados, f, ensure_ascii=False, indent=2)

    log.info("Dataset guardado en %s (%d registros)", OUTPUT_FILE, len(anuncios_filtrados))
    log.info("=== Fin scraper ===")


if __name__ == "__main__":
    main()