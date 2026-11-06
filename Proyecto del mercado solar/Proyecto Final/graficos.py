# -*- coding: utf-8 -*-
"""
Calcula las cifras del artículo y construye los 8 gráficos.

Entrada: base_unificada.json (de unificar.py).
Salida:  cifras.json (cada número que cita el artículo) y graficos/g1.html ... g8.html.

Los gráficos son HTML y CSS (barras y puntos), no imágenes: así el texto conserva
su tamaño real en el teléfono y se adaptan a cualquier pantalla. Los estilos están
en estilos_graficos.css. Solo usa Python y numpy.
"""
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

AQUI = Path(__file__).resolve().parent
SALIDA = AQUI / "graficos"
SALIDA.mkdir(exist_ok=True)
for viejo in list(SALIDA.glob("*.svg")) + list(SALIDA.glob("tablas.json")):
    viejo.unlink()

NOMBRE = {"paneles": "Paneles solares", "estaciones": "Estaciones portátiles",
          "baterias": "Baterías", "inversores": "Inversores", "kits": "Sistemas completos"}
ORDEN = ["paneles", "estaciones", "baterias", "inversores", "kits"]
cifras = {}


# ------------------------------------------------------------ utilidades

def num(x, dec=0):
    """Número en estilo español: 10 149 ; 0,29."""
    return f"{float(x):,.{dec}f}".replace(",", " ").replace(".", ",")


def usd(x):
    return f"{num(x)} USD"


def wh(x):
    return f"{num(x / 1000, 1)} kWh" if x >= 1000 else f"{num(x)} Wh"


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def pct(a, b):
    return round(100 * a / b) if b else 0


_LITIO = re.compile(r"litio|lifepo|lfp|lithium|li-?ion", re.I)
_HIBRIDO = re.compile(r"h[ií]brid|hybrid|mppt", re.I)


def es_litio(r):
    """Batería de litio según su tipo o su título (las de plomo, gel o AGM no se comparan)."""
    return bool(_LITIO.search((r["tipo_bateria"] or "") + " " + (r["titulo"] or "")))


def es_hibrido(r):
    """Inversor híbrido o con MPPT según el título (los simples de 12 V cumplen otra función)."""
    return bool(_HIBRIDO.search(r["titulo"] or ""))


# ------------------------------------------------------------ datos

base = json.load(open(AQUI / "base_unificada.json", encoding="utf-8"))
R = base["registros"]
ANUNCIOS = [r for r in R if r["tipo_fuente"] == "anuncio"]
VALIDOS = [r for r in ANUNCIOS if r["precio_usd"] and not r["precio_dudoso"]]
INSTIT = [r for r in R if r["tipo_fuente"] == "institucion" and r["precio_usd"] and not r["precio_dudoso"]]
ENTREV = [r for r in R if r["tipo_fuente"] == "entrevista" and r["precio_usd"]]


def de(cat, lista=VALIDOS):
    return [r for r in lista if r["categoria"] == cat]


def paneles_ok():
    return [r for r in de("paneles") if r["potencia_w"] and 100 <= r["potencia_w"] <= 800
            and r["precio_usd"] < 1000 and r["precio_usd"] / r["potencia_w"] <= 3]


def almacen_ok(cat):
    out = [r for r in de(cat) if r["capacidad_wh"] and 100 <= r["capacidad_wh"] <= 20000
           and 0.05 <= r["precio_usd"] / r["capacidad_wh"] <= 3]
    return [r for r in out if es_litio(r)] if cat == "baterias" else out


def inversores_ok():
    return [r for r in de("inversores") if r["potencia_w"] and 300 <= r["potencia_w"] <= 30000 and es_hibrido(r)]


cifras["total_anuncios"] = len(ANUNCIOS)
cifras["total_entrevistas"] = sum(r["tipo_fuente"] == "entrevista" for r in R)
cifras["instituciones_lista"] = sorted({r["municipio_o_lugar"].split(" (")[0] for r in INSTIT})
cifras["mediana_global"] = round(float(np.median([r["precio_usd"] for r in VALIDOS])))


# ------------------------------------------------------------ piezas de HTML

def leyenda(items):
    return ('<div class="g-leyenda">' + "".join(
        f'<span><i class="{c}"></i>{esc(t)}</span>' for t, c in items) + "</div>")


def barra_h(etiqueta, valor, vmax, texto, clase="c1", sub=""):
    ancho = max(0.8, 56 * valor / vmax) if vmax else 0
    sub_html = f'<span class="g-sub">{esc(sub)}</span>' if sub else ""
    return (f'<div class="g-fila"><div class="g-etq">{esc(etiqueta)}{sub_html}</div>'
            f'<div class="g-pista"><div class="g-barra {clase}" style="width:{ancho:.1f}%"></div>'
            f'<span class="g-valor">{texto}</span></div></div>')


def guardar(n, html):
    (SALIDA / f"g{n}.html").write_text(html, encoding="utf-8")


# ============================================================ 1. ¿Qué se vende?

def grafico1():
    conteo = Counter(r["categoria"] for r in ANUNCIOS)
    total = sum(conteo.values())
    orden = sorted(ORDEN, key=lambda c: -conteo[c])
    vmax = conteo[orden[0]]
    filas = "".join(barra_h(NOMBRE[c], conteo[c], vmax, f"<b>{num(conteo[c])}</b> · {pct(conteo[c], total)} %",
                            "c1" if i == 0 else "c2") for i, c in enumerate(orden))
    guardar(1, f'<div class="g g-barras-h">{filas}<p class="g-nota">Número de anuncios por tipo de equipo.</p></div>')
    cifras["g1"] = {c: {"n": conteo[c], "pct": pct(conteo[c], total)} for c in ORDEN}
    cifras["g1"]["veces_estaciones_vs_paneles"] = round(conteo["estaciones"] / conteo["paneles"])


# ============================================================ 2. Precio típico por categoría

def grafico2():
    med = {c: float(np.median([r["precio_usd"] for r in de(c)])) for c in ORDEN}
    orden = sorted(ORDEN, key=lambda c: med[c])
    vmax = max(med.values())
    cols = "".join(
        f'<div class="g-col">'
        f'<div class="g-col-pista"><span class="g-valor">{usd(round(med[c]))}</span><div class="g-barra {"c1" if c == "kits" else "c2"}" '
        f'style="height:{max(1.5, 100 * med[c] / vmax):.1f}%"></div></div>'
        f'<span class="g-etq">{NOMBRE[c]}</span></div>' for c in orden)
    guardar(2, f'<div class="g g-barras-v">{cols}</div>'
               f'<p class="g-nota">Precio típico (mediana) de cada tipo de equipo, en USD.</p>')
    cifras["g2"] = {c: round(med[c]) for c in ORDEN}
    cifras["g2"]["kits_vs_paneles"] = round(med["kits"] / med["paneles"])
    dentro = 0
    for r in ENTREV:
        p = [x["precio_usd"] for x in de(r["categoria"])]
        dentro += bool(np.percentile(p, 5) <= r["precio_usd"] <= np.percentile(p, 95))
    cifras["g2"]["entrevistas_dentro"] = dentro
    cifras["g2"]["entrevistas_n"] = len(ENTREV)


# ============================================================ 3. Del más barato al más caro

def grafico3():
    lo, hi = np.log10(60), np.log10(25000)
    pos = lambda v: 100 * (np.log10(min(max(v, 60), 25000)) - lo) / (hi - lo)
    filas = []
    out = {}
    for c in ORDEN:
        p = np.array([r["precio_usd"] for r in de(c)])
        a, b = np.percentile(p, [5, 95])
        out[c] = {"desde": round(float(a)), "hasta": round(float(b)), "veces": round(float(b / a))}
        filas.append(
            f'<div class="g-fila"><div class="g-etq">{NOMBRE[c]}</div><div class="g-pista g-rango">'
            f'<div class="g-linea" style="left:{pos(a):.1f}%;width:{pos(b) - pos(a):.1f}%"></div>'
            f'<span class="g-punto c2" style="left:{pos(a):.1f}%"></span>'
            f'<span class="g-punto c1" style="left:{pos(b):.1f}%"></span>'
            f'<span class="g-rango-txt" style="left:{pos(a):.1f}%">{usd(round(a))}</span>'
            f'<span class="g-rango-txt fin" style="left:{pos(b):.1f}%">{usd(round(b))}</span>'
            f'</div></div>')
    eje = "".join(f'<span style="left:{pos(t):.1f}%">{num(t)}</span>' for t in (100, 300, 1000, 3000, 10000))
    guardar(3, f'<div class="g g-puntos">{leyenda([("Los más baratos", "c2"), ("Los más caros", "c1")])}'
               f'{"".join(filas)}<div class="g-fila g-fila-eje"><div class="g-etq"></div><div class="g-eje">{eje}</div></div>'
               f'<p class="g-nota">Precios en USD. Se dejan fuera los anuncios más extremos de cada lado.</p></div>')
    cifras["g3"] = out


# ============================================================ 4. Energía según el presupuesto

TRAMOS = [(0, 300, "Hasta 300 USD"), (300, 700, "De 301 a 700 USD"), (700, 1500, "De 701 a 1 500 USD"),
          (1500, 3000, "De 1 501 a 3 000 USD"), (3000, 1e12, "Más de 3 000 USD")]


def grafico4():
    est, bat = almacen_ok("estaciones"), almacen_ok("baterias")
    datos = []
    for a, b, e in TRAMOS:
        fila = {"tramo": e}
        for k, lista in (("estacion", est), ("bateria", bat)):
            sub = [r["capacidad_wh"] for r in lista if a < r["precio_usd"] <= b]
            fila[k] = int(np.median(sub)) if len(sub) >= 15 else None
        datos.append(fila)
    vmax = max(v for f in datos for v in (f["estacion"], f["bateria"]) if v)
    bloques = []
    for f in datos:
        barras = ""
        for k, cls in (("estacion", "c1"), ("bateria", "c2")):
            v = f[k]
            if v:
                barras += (f'<div class="g-pista g-mini"><div class="g-barra {cls}" style="width:{56 * v / vmax:.1f}%"></div>'
                           f'<span class="g-valor"><b>{wh(v)}</b></span></div>')
            else:
                barras += '<div class="g-pista g-mini"><span class="g-valor g-vacio">pocas ofertas</span></div>'
        bloques.append(f'<div class="g-grupo"><div class="g-etq">{f["tramo"]}</div><div>{barras}</div></div>')
    guardar(4, f'<div class="g g-agrupado">{leyenda([("Estación portátil", "c1"), ("Batería de litio (necesita inversor)", "c2")])}'
               f'{"".join(bloques)}<p class="g-nota">Capacidad típica de los equipos anunciados en cada rango de precio. '
               f'1 kWh = 1 000 Wh.</p></div>')
    cifras["g4"] = datos


# ============================================================ 5. Lo que cuesta cada unidad de energía

def grafico5():
    u = lambda lista, campo: float(np.median([r["precio_usd"] / r[campo] for r in lista]))
    almac = [("Batería de litio", u(almacen_ok("baterias"), "capacidad_wh") * 1000, "c2"),
             ("Estación portátil", u(almacen_ok("estaciones"), "capacidad_wh") * 1000, "c1")]
    poten = [("Inversor híbrido", u(inversores_ok(), "potencia_w") * 1000, "c2"),
             ("Paneles solares", u(paneles_ok(), "potencia_w") * 1000, "c1")]
    vmax = max(v for _, v, _ in almac + poten)
    guardar(5, '<div class="g g-barras-h">'
               '<p class="g-bloque">Guardar 1 kWh de energía</p>'
               + "".join(barra_h(e, v, vmax, f"<b>{usd(round(v, -1))}</b>", c) for e, v, c in almac)
               + '<p class="g-bloque">Conseguir 1 kW de potencia</p>'
               + "".join(barra_h(e, v, vmax, f"<b>{usd(round(v, -1))}</b>", c) for e, v, c in poten)
               + '<p class="g-nota">Precio típico por unidad de energía o de potencia.</p></div>')
    cifras["g5"] = {"bateria_kwh": round(almac[0][1], -1), "estacion_kwh": round(almac[1][1], -1),
                    "inversor_kw": round(poten[0][1], -1), "panel_kw": round(poten[1][1], -1),
                    "estacion_vs_bateria": round(almac[1][1] / almac[0][1], 1)}


# ============================================================ 6. Garantía

def grafico6():
    L = [r for r in ANUNCIOS if r["descripcion_leida"]]
    filas = []
    out = {}
    con_t = sin_t = 0
    for c in ORDEN:
        sub = [r for r in L if r["categoria"] == c]
        con = sum(r["tiene_garantia"] is True for r in sub)
        sin = sum(r["tiene_garantia"] is False for r in sub)
        con_t += con
        sin_t += sin
        p = [pct(con, len(sub)), pct(sin, len(sub))]
        p.append(100 - p[0] - p[1])
        out[c] = {"con": p[0], "sin": p[1], "no_dice": p[2]}
        seg = "".join(f'<div class="g-seg {cls}" style="width:{v}%">{f"{v} %" if v >= 10 else ""}</div>'
                      for v, cls in zip(p, ("c1", "c4", "c5")) if v > 0)
        filas.append(f'<div class="g-fila"><div class="g-etq">{NOMBRE[c]}</div><div class="g-apilada">{seg}</div></div>')
    guardar(6, f'<div class="g g-apiladas">{leyenda([("Ofrece garantía", "c1"), ("Sin garantía", "c4"), ("No lo especifica", "c5")])}'
               f'{"".join(filas)}<p class="g-nota">Porcentaje de anuncios de cada tipo de equipo.</p></div>')
    out["total_con"] = pct(con_t, len(L))
    out["total_no_dice"] = pct(len(L) - con_t - sin_t, len(L))
    cifras["g6"] = out


# ============================================================ 7. Instalación, envío y componentes

def grafico7():
    L = [r for r in ANUNCIOS if r["descripcion_leida"]]
    kl = [r for r in L if r["categoria"] == "kits"]
    kits = [r for r in ANUNCIOS if r["categoria"] == "kits"]
    tres = sum(bool(r["potencia_total_paneles_w"] and r["potencia_inversor_w"] and r["capacidad_wh"]) for r in kits)
    alguno = sum(bool(r["potencia_total_paneles_w"] or r["potencia_inversor_w"] or r["capacidad_wh"]) for r in kits)
    grupos = [
        ("Instalación", "sistemas completos",
         pct(sum(r["instalacion"] == "incluida" for r in kl), len(kl)),
         pct(sum(r["instalacion"] == "ofrecida" for r in kl), len(kl)), "Incluida en el precio", "Se ofrece aparte"),
        ("Envío", "todos los equipos",
         pct(sum(r["envio"] == "gratis" for r in L), len(L)),
         pct(sum(r["envio"] == "disponible" for r in L), len(L)), "Gratis", "Disponible, sin precisar costo"),
        ("Componentes", "sistemas completos",
         pct(tres, len(kits)), pct(alguno - tres, len(kits)), "Detalla paneles, inversor y batería", "Detalla solo una parte"),
    ]
    bloques = []
    for nombre, sub, a, b, ta, tb in grupos:
        bloques.append(
            f'<div class="g-grupo"><div class="g-etq">{nombre}<span class="g-sub">{sub}</span></div><div>'
            f'<div class="g-pista g-mini"><div class="g-barra c1" style="width:{max(a * .6, .8):.1f}%"></div>'
            f'<span class="g-valor"><b>{a} %</b> {esc(ta)}</span></div>'
            f'<div class="g-pista g-mini"><div class="g-barra c2" style="width:{max(b * .6, .8):.1f}%"></div>'
            f'<span class="g-valor"><b>{b} %</b> {esc(tb)}</span></div></div></div>')
    guardar(7, f'<div class="g g-agrupado">{"".join(bloques)}'
               f'<p class="g-nota">Porcentaje de anuncios. El resto no menciona el servicio.</p></div>')
    cifras["g7"] = {"instalacion_incluida": grupos[0][2], "instalacion_aparte": grupos[0][3],
                    "envio_gratis": grupos[1][2], "envio_disponible": grupos[1][3],
                    "componentes_completos": grupos[2][2], "componentes_parcial": grupos[2][3]}


# ============================================================ 8. Ranking de valor

def ranking(lista, cuantos=6):
    """Agrupa por marca y capacidad (el nombre del modelo viene escrito de muchas formas)
    y ordena por Wh que se obtienen con cada 100 USD (precio mediano del grupo). Mínimo 5 anuncios."""
    g = defaultdict(list)
    for r in lista:
        if r["marca"]:
            g[(r["marca"], r["capacidad_wh"])].append(r)
    filas = []
    for (marca, cap), v in g.items():
        if len(v) < 5:
            continue
        precio = float(np.median([r["precio_usd"] for r in v]))
        modelo = Counter(r["modelo"] for r in v if r["modelo"]).most_common(1)
        nombre = f"{marca} {modelo[0][0]}" if modelo else marca
        filas.append({"nombre": nombre, "marca": marca, "wh": cap, "precio": round(precio),
                      "wh_100": round(100 * cap / precio), "n": len(v)})
    filas.sort(key=lambda f: -f["wh_100"])
    return filas[:cuantos]


def grafico8():
    est = ranking(almacen_ok("estaciones"))
    bat = ranking(almacen_ok("baterias"))
    med = lambda lista: round(100 / float(np.median([r["precio_usd"] / r["capacidad_wh"] for r in lista])))
    med_est, med_bat = med(almacen_ok("estaciones")), med(almacen_ok("baterias"))
    vmax = max(f["wh_100"] for f in est + bat)

    def bloque(titulo, filas, m, cls):
        h = f'<p class="g-bloque">{titulo}</p>'
        for i, f in enumerate(filas, 1):
            h += barra_h(f"{i}. {f['nombre']}", f["wh_100"], vmax, f"<b>{num(f['wh_100'])} Wh</b>", cls,
                         sub=f"{wh(f['wh'])} · unos {usd(f['precio'])}")
        h += f'<p class="g-ref">Lo habitual en esta categoría: {num(m)} Wh por cada 100 USD</p>'
        return h

    guardar(8, '<div class="g g-barras-h g-ranking">'
               + bloque("Estaciones portátiles", est, med_est, "c1")
               + bloque("Baterías de litio", bat, med_bat, "c3")
               + '<p class="g-nota">Energía que se obtiene por cada 100 USD: cuanto más larga la barra, mejor. '
                 'Precio típico de cada modelo. Las baterías necesitan además un inversor.</p></div>')
    cifras["g8"] = {"estaciones": est, "baterias": bat, "med_est": med_est, "med_bat": med_bat}


if __name__ == "__main__":
    for g in (grafico1, grafico2, grafico3, grafico4, grafico5, grafico6, grafico7, grafico8):
        g()
    json.dump(cifras, open(AQUI / "cifras.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1,
              default=lambda o: o.item() if hasattr(o, "item") else str(o))
    print("Listo:", ", ".join(sorted(p.name for p in SALIDA.glob("g*.html"))))
