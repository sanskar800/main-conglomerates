"""Entry point — run the config-driven extractor for one group.

    python run.py cg          # uses config/cg.json

Output: output/{slug}.json  +  output/{slug}.html
"""
import json
import sys

from lib import settings
from lib.cache import Cache
from lib.llm import Gemini, cost_of
from lib.pipeline import run_group

CONFIG_DIR = settings.CONFIG_DIR
OUT_DIR = settings.OUTPUT_DIR


def main():
    slug = sys.argv[1] if len(sys.argv) > 1 else "cg"
    config = json.loads((CONFIG_DIR / f"{slug}.json").read_text())

    cache = Cache(OUT_DIR / "cache.json")
    cost_log = []
    gemini = Gemini(settings.GEMINI_API_KEY, settings.MODEL_NAME, cache, cost_log)

    print(f"== {config['name']} ==")
    companies = run_group(config, gemini, cache)
    cost = cost_of(cost_log)

    result = {"group": config["name"], "slug": slug, "url": config["url"],
              "company_count": len(companies), "llm_cost": cost, "companies": companies}
    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / f"{slug}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    write_html(result, OUT_DIR / f"{slug}.html")
    print(f"\nSaved output/{slug}.json  |  {len(companies)} companies  |  ${cost['cost_usd']}")


def write_html(result, path):
    col = {"subsidiary": "#27ae60", "brand": "#2980b9", "property": "#16a085",
           "investment": "#8e44ad"}
    by_div = {}
    for c in result["companies"]:
        by_div.setdefault(c.get("division") or "(none)", []).append(c)
    by_parent = {}
    for c in result["companies"]:
        if c.get("parent"):
            by_parent.setdefault(c["parent"], []).append(c)

    def row(c, indent, flag=""):
        img = (f'<img src="{c["image"]}" style="width:18px;height:18px;object-fit:contain;'
               f'vertical-align:middle;margin-right:6px">' if c.get("image") else "")
        desc = c.get("description") or ""
        return (f'<tr><td style="padding-left:{12 + indent*20}px">{img}<b>{c["name"]}</b>{flag}'
                f'{"<br><small style=color:#888>" + desc + "</small>" if desc else ""}</td>'
                f'<td style="color:{col.get(c.get("relationship"),"#777")};font-size:11px">'
                f'{c.get("relationship","")}</td><td style="font-size:11px;color:#555">'
                f'{c.get("sector","")}</td></tr>')

    rows = ""
    for div, members in sorted(by_div.items(), key=lambda x: -len(x[1])):
        rows += (f'<tr><td colspan=3 style="background:#eef2f7;font-weight:bold;'
                 f'padding:6px 12px">▸ {div} ({len(members)})</td></tr>')
        for c in members:
            if c.get("parent"):
                continue
            rows += row(c, 1)
            for ch in by_parent.get(c["name"], []):
                rows += row(ch, 2, ' <span style="color:#e67e22;font-size:9px">~llm</span>')
    lc = result["llm_cost"]
    path.write_text(f"""<!doctype html><meta charset=utf-8><title>{result['group']}</title>
<style>body{{font-family:-apple-system,Segoe UI,sans-serif;margin:0;background:#f5f6fa}}
.h{{background:#2c3e50;color:#fff;padding:14px 20px}}.h h1{{margin:0;font-size:18px}}
table{{width:100%;border-collapse:collapse;background:#fff}}td{{padding:5px 12px;
border-bottom:1px solid #f0f0f0;font-size:12px;vertical-align:top}}</style>
<div class=h><h1>{result['group']} — {result['company_count']} companies</h1>
<small>config-driven · ${lc['cost_usd']} · {lc['calls']} LLM calls</small></div>
<table>{rows}</table>""", encoding="utf-8")


if __name__ == "__main__":
    main()
