# main_conglomerates

Config-driven extractor that turns a Nepali business-group website into
structured **Group → Division → Company → Brand** data.

An earlier version used **one universal LLM prompt + heuristics** for every
site. It held up for 2–3 sites but got fragile as more were added — every new
site needed prompt tweaks that broke the others. This version separates the two
concerns:

- **Config decides WHAT to scrape** (`config/<slug>.json`) — explicit, per-site,
  no LLM guessing of which pages list companies.
- **Deterministic rules decide WHAT survives** — the LLM only reads page text;
  config rules clean the result. Adding a site is a new config file, not a
  prompt edit, so one site's quirks never break another.

## Quick start

```bash
pip install -r requirements.txt          # python-dotenv
cp .env.example .env                      # add GEMINI_API_KEY + MODEL_NAME
python run.py cg
```

Outputs `output/cg.json` and `output/cg.html`.

## Layout

```
.env                 # GEMINI_API_KEY, MODEL_NAME   (not committed)
requirements.txt
run.py               # entry point + HTML report
config/
  cg.json            # per-site: discovery (which pages) + cleaning rules
lib/
  settings.py        # loads .env via python-dotenv
  cache.py           # json file cache (scraper + LLM responses)
  scraper.py         # Indexpress /get/resource, /call + browser /forward fallback
  llm.py             # Gemini extraction (generic prompt — no hallucination)
  text.py            # url keys, name normalisation, heading parsing
  pipeline.py        # discover → extract → apply config rules → dedup
output/              # results + cache (not committed)
```

## How it works

```
1. discover   config.discovery → the company/sector page URLs (nav section
              children, same-domain, + one level of "Read More" detail pages)
2. fetch      Indexpress /call markdown; browser /forward fallback for
              host-blocked / JS-rendered pages
3. extract    Gemini reads each page → {name, relationship, sector,
              description, image, website}. The prompt is generic (no real
              company names as examples) so it can't echo placeholders as
              fake entities on a thin page.
4. clean      deterministic, config-driven rules (below)
5. output     {slug}.json + {slug}.html (Division → Company → Brand tree)
```

### Cleaning rules (config-driven)

| rule | what it does |
|------|--------------|
| `division_from: page` | a company's division = the page it was scraped from (page provenance — a fact, not an LLM guess) |
| structural-echo drop | drops entities that match the group's own nav/footer link names (e.g. `CG Infra` echoed in a thin page's footer), keeping the page's own anchor |
| `nest_brand_under_company_only` | a brand may nest under a subsidiary, never brand→brand or sibling→sibling |
| `drop_if_contains` | drop names containing region/location/noise tokens |
| `min_name_length` | drop too-short fragments |
| `name_must_be_heading` *(optional, off)* | strict gate: keep only names that are real page headings (`<h1>`–`<h6>`). Drops legit brands that live in cards/text, so it's **off by default** — enable only for very noisy sites |

## config schema (`config/<slug>.json`)

```jsonc
{
  "name": "Chaudhary Group (CG)",
  "slug": "cg",
  "url":  "https://chaudharygroup.com",

  "discovery": {
    "nav_section": "Companies",   // use children of this nav section
    "follow_read_more": true,     // follow one level of "Read More" links
    "same_domain_only": true
  },

  "rules": {
    "name_must_be_heading": false,
    "division_from": "page",
    "nest_brand_under_company_only": true,
    "drop_if_contains": ["region", "main unit", "head office"],
    "min_name_length": 3
  }
}
```

## Adding a site

Drop in `config/<slug>.json` and run `python run.py <slug>`. No code change.
Per-site quirks (a noisy footer, a JS nav, a product-catalog section to skip)
are expressed as config, so tuning one site never regresses another.

## Notes / limits

- **Hierarchy backbone (Group → Division → Company) is reliable** — it comes
  from page provenance + nav structure.
- **Brand → Company nesting is an LLM guess** (kept only when it resolves to a
  real subsidiary) and is flagged `~llm` in the HTML — the one place that needs
  a human review pass.
- A site that lists companies only on a homepage grid, or behind a true
  client-side SPA with no static content, may need a per-site config tweak or
  yield little.
