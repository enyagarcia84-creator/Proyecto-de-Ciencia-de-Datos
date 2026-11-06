# Non-functional requirements (distilled from round 1)

Round 1 (Revolico + Playwright + Chrome) is archived in `archivo/ronda1_revolico/`.
It failed in the field: Revolico's Cloudflare "¿eres un robot?" check blocked the
automated browser. These are the requirements worth carrying forward.

## Learned from the failure
1. **No browser, no captcha.** Prefer data access that works with plain HTTP and
   needs no human to solve a challenge. A scraper that depends on someone clicking
   a checkbox is not a scraper.
2. **Test against the live site before shipping.** Round 1 was only checked against
   saved HTML. Every delivered script must have been run end-to-end against the real
   site, with the output inspected.
3. **Detect blocks and say so, but keep what was fetched.** If the site returns
   403/429 or a challenge page, stop with a clear Spanish message, write the partial
   JSON flagged `"incompleto": true` (bandwidth in Cuba is expensive), and (in
   `--depurar`) save the page. Never silently present partial data as complete.

## User / environment
4. **Runs on a Windows PC in Cuba, slow and expensive connection.** Minimise
   requests and bytes: dedupe URLs, filter by title before opening detail pages,
   cap results per search, pause between requests (configurable). Prefer the
   leanest data source (El Yerro's internal `/api/search/item`: ~7x smaller, 100
   results/request) but never depend on an undocumented endpoint alone: fall back to
   the public pages automatically and say so in the console.
5. **Minimal setup.** Ideally only Python; no `pip install`, no browser download.
   If a dependency is unavoidable, one `pip install` line in `requirements.txt`.
6. **Non-technical operator.** Double-click `.bat` per product; menu when run with
   no arguments; console progress in Spanish showing what was kept and *why* each
   item was discarded.
7. **Windows console safety.** Product titles contain emojis; printing must never
   crash (`sys.stdout.reconfigure(errors="replace")`).
8. **Beginner-readable code.** One file, Spanish comments, settings at the top
   (pages, pause, search terms, keywords, exclusions, brands).

## Data quality
9. **Never invent values.** Unknown → `null`. Not every listing has every field.
10. **Power is W, not Wh.** Wh is capacity. Convert kW → W. Prefer output/nominal
    power over peak/surge/input/charging.
11. **Brand and model in separate fields.**
12. **Product relevance filter.** Per-product keyword list + exclusion list
    (accessories, cables, unrelated batteries, etc.).
13. **Pass currency through as the site gives it** (round 2 site also uses `ZELLE`);
    don't force it into a fixed list. **Know which field to trust:** on El Yerro the
    search result's `currency` is right; the product page's JSON-LD `priceCurrency` /
    store currency can be wrong (USD prices shown as CUP). Cross-check sources live.
14. **Be explicit about what "date" means.** If the source has no true publication
    date, say which date is used for the 30-day filter, in the JSON and in the README.
19. **Context-aware field extraction** (learned live in round 2): classify a power value
    by its own segment, not the whole line ("1800W (3600W pico)"); ignore "hasta / en
    paralelo / total / tolerancia"; take brand only from title, spec sheet or explicit
    "Marca:" (descriptions say "compatible con EcoFlow"); for panels/inverters don't read
    battery type/capacity from the description (it describes compatible batteries).

## Robustness / delivery
15. **Per-item error tolerance.** Any exception on one item (timeout, odd page shape)
    skips that item, not the run.
16. **`--depurar` mode** saves raw pages to `depuracion/` for remote diagnosis.
17. **Output:** UTF-8 JSON, indented, in `resultados/<producto>_<YYYY-MM-DD_HHMM>.json`,
    with a metadata header (producto, fuente, ubicación, fecha_consulta, periodo,
    total) followed by the items.
18. **Deliverable bundle:** 4 Opencode prompts (rol, tarea medible con criterios de
    aceptación, contexto, restricciones, formato de salida), the script, the `.bat`
    files, `LEEME.md` with install/use/known limitations, and a zip for handoff.
