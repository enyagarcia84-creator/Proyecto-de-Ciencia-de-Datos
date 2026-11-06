# -*- coding: utf-8 -*-
"""
Construye articulo.html a partir de articulo_plantilla.html.

- {{ruta.a.la.cifra|formato}} se sustituye por el valor de cifras.json.
  Formatos: n (entero), d1 (un decimal), usd, t (texto), lista (lista con viñetas).
  Si una cifra no existe, se detiene: el artículo nunca muestra un número que no salga de los datos.
- {{GRAFICO N | título | explicación}} inserta el gráfico N con su título y su explicación.
"""
import json
import re
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
cifras = json.load(open(AQUI / "cifras.json", encoding="utf-8"))
css_graficos = (AQUI / "estilos_graficos.css").read_text(encoding="utf-8")
plantilla = (AQUI / "articulo_plantilla.html").read_text(encoding="utf-8")


def num(x, dec=0):
    return f"{float(x):,.{dec}f}".replace(",", " ").replace(".", ",")


def buscar(ruta):
    v = cifras
    for parte in ruta.split("."):
        if isinstance(v, list):
            v = v[int(parte)]
        elif parte in v:
            v = v[parte]
        else:
            sys.exit(f"Falta la cifra: {ruta}")
    if v is None:
        sys.exit(f"La cifra está vacía: {ruta}")
    return v


def formatear(m):
    v = buscar(m.group(1))
    fmt = m.group(2)
    if fmt == "n":
        return num(v)
    if fmt == "d1":
        return num(v, 1)
    if fmt == "usd":
        return num(v) + " USD"
    if fmt == "t":
        return str(v)
    if fmt == "lista":
        return '<ul class="lista-inst">' + "".join(f"<li>{x}</li>" for x in v) + "</ul>"
    sys.exit(f"Formato desconocido: {fmt}")


def figura(m):
    n, titulo, texto = (x.strip() for x in m.groups())
    grafico = (AQUI / "graficos" / f"g{n}.html").read_text(encoding="utf-8")
    return (f'<figure class="grafico" id="grafico-{n}">'
            f'<p class="g-num">Gráfico {n}</p><h3>{titulo}</h3><p class="g-desc">{texto}</p>'
            f'{grafico}</figure>')


cuerpo = re.sub(r"\{\{GRAFICO (\d) \| (.+?) \| (.+?)\}\}", figura, plantilla)
cuerpo = re.sub(r"\{\{([\w.]+?)\|(\w+)\}\}", formatear, cuerpo)
if "{{" in cuerpo:
    sys.exit("Quedó un marcador sin sustituir: " + cuerpo[cuerpo.index("{{"):][:80])

pagina = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>¿Hasta dónde llega el dinero de un cubano en el mercado solar de La Habana?</title>
<meta name="author" content="Enya Elena García Arrascaeta">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
/* Identidad visual: verde natural + marfil, tipografía Inter */
:root {{
  --bosque: #263F38;   /* títulos y textos destacados */
  --natural: #496B5A;  /* elementos principales, gráficos, enlaces */
  --salvia: #91A995;   /* datos secundarios y detalles */
  --niebla: #DCE5D9;   /* fondos de bloques */
  --marfil: #F7F5EF;   /* fondo general */
  --blanco: #FFFFFF;   /* tarjetas */
  --texto: #263F38;
  --fuente: "Inter", system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
}}
* {{ box-sizing: border-box; }}
html {{ -webkit-text-size-adjust: 100%; }}
body {{ margin: 0; background: var(--marfil); color: var(--texto); font-family: var(--fuente); font-weight: 400;
        font-size: 17px; line-height: 1.75; }}
main {{ max-width: 720px; margin: 0 auto; padding: 0 22px 96px; }}
a {{ color: var(--natural); text-underline-offset: 3px; }}
strong {{ font-weight: 600; color: var(--bosque); }}
p {{ margin: 0 0 1.25em; }}

/* portada */
.portada {{ padding: 72px 0 40px; border-bottom: 1px solid var(--niebla); margin-bottom: 44px; }}
.antetitulo {{ font-size: 12px; font-weight: 500; letter-spacing: .18em; text-transform: uppercase; color: var(--natural); margin-bottom: 22px; }}
h1 {{ font-weight: 300; font-size: clamp(2.1rem, 7.5vw, 3.6rem); line-height: 1.1; letter-spacing: -.02em; color: var(--bosque); margin: 0 0 28px; }}
.firma {{ font-size: 15px; font-weight: 500; color: var(--natural); margin: 0; }}

.entrada {{ font-size: 1.18rem; font-weight: 300; line-height: 1.7; color: var(--bosque); }}

/* capítulos */
.separador {{ display: flex; align-items: center; gap: 18px; margin: 72px 0 36px; color: var(--salvia); }}
.separador::before, .separador::after {{ content: ""; flex: 1; height: 1px; background: var(--niebla); }}
.separador span {{ font-weight: 300; font-size: 1.6rem; color: var(--natural); }}
.capitulo-num {{ font-size: 12px; font-weight: 600; letter-spacing: .18em; text-transform: uppercase; color: var(--salvia); margin-bottom: 8px; }}
h2 {{ font-weight: 300; font-size: clamp(1.75rem, 5.5vw, 2.5rem); line-height: 1.15; letter-spacing: -.015em; color: var(--bosque); margin: 0 0 26px; }}

/* frases destacadas */
.destacado {{ margin: 44px 0; padding: 0 0 0 22px; border-left: 2px solid var(--natural);
              font-weight: 300; font-size: clamp(1.3rem, 4.6vw, 1.65rem); line-height: 1.4; color: var(--bosque); }}

/* transiciones entre capítulos */
.transicion {{ background: var(--niebla); border-radius: 14px; padding: 28px 26px; margin: 56px 0 0; }}
.transicion p {{ margin: 0; font-weight: 300; font-size: 1.15rem; line-height: 1.6; color: var(--bosque); }}

/* «Lo que significa para usted» */
.para-ti {{ background: var(--blanco); border: 1px solid var(--niebla); border-radius: 12px; padding: 18px 20px; font-size: .97rem; }}
.para-ti span {{ display: block; font-size: 11.5px; font-weight: 600; letter-spacing: .14em; text-transform: uppercase; color: var(--natural); margin-bottom: 6px; }}

/* gráficos */
.grafico {{ background: var(--blanco); border: 1px solid var(--niebla); border-radius: 16px; padding: 26px 20px 22px; margin: 40px -8px; }}
@media (min-width: 820px) {{ .grafico {{ margin: 48px -48px; padding: 34px 40px 28px; }} }}
.g-num {{ font-size: 11.5px; font-weight: 600; letter-spacing: .16em; text-transform: uppercase; color: var(--salvia); margin: 0 0 6px; }}
.grafico h3 {{ font-weight: 500; font-size: clamp(1.2rem, 4.4vw, 1.45rem); line-height: 1.3; color: var(--bosque); margin: 0 0 6px; }}
.g-desc {{ font-size: 14.5px; line-height: 1.5; color: var(--natural); margin: 0 0 24px; }}

/* conclusiones: tarjetas por presupuesto */
.presupuestos {{ display: grid; grid-template-columns: 1fr; gap: 14px; margin: 30px 0 40px; }}
@media (min-width: 640px) {{ .presupuestos {{ grid-template-columns: 1fr 1fr; }} }}
.tarjeta {{ background: var(--blanco); border: 1px solid var(--niebla); border-radius: 14px; padding: 22px 20px; }}
.tarjeta p {{ font-size: .95rem; line-height: 1.6; margin: 0; }}
.tarjeta .monto {{ font-weight: 600; font-size: 1.05rem; color: var(--natural); margin-bottom: 8px; }}
.recuadro {{ background: var(--niebla); border-radius: 14px; padding: 26px 24px 14px; margin: 40px 0; }}
.recuadro-titulo {{ font-weight: 500; font-size: 1.15rem; color: var(--bosque); margin-bottom: 10px; }}
.recuadro ol {{ margin: 0 0 12px; padding-left: 1.2em; }}
.recuadro li {{ margin-bottom: 8px; }}
.cierre {{ font-weight: 300; font-size: clamp(1.35rem, 4.8vw, 1.75rem); line-height: 1.4; color: var(--bosque); margin-top: 44px;
           padding-top: 30px; border-top: 1px solid var(--niebla); }}

/* fuentes y autora */
.fuentes, .autora {{ margin-top: 72px; padding-top: 32px; border-top: 1px solid var(--niebla); font-size: .95rem; }}
.fuentes h2, .autora h2 {{ font-weight: 500; font-size: 1.15rem; letter-spacing: 0; margin-bottom: 16px; }}
.fuentes > ul {{ list-style: none; padding: 0; margin: 0; }}
.fuentes > ul > li {{ margin-bottom: 12px; }}
.lista-inst {{ margin: 8px 0 0; padding-left: 1.1em; columns: 1; color: var(--natural); font-size: .9rem; line-height: 1.6; }}
@media (min-width: 640px) {{ .lista-inst {{ columns: 2; column-gap: 28px; }} }}
.autora {{ background: var(--blanco); border: 1px solid var(--niebla); border-radius: 14px; padding: 26px 24px 12px; }}

{css_graficos}
</style>
</head>
<body>
<main>
{cuerpo}
</main>
</body>
</html>
"""
(AQUI / "articulo.html").write_text(pagina, encoding="utf-8")
print("articulo.html:", round(len(pagina.encode()) / 1024), "KB")
