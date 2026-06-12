"""Entry point — run the config-driven extractor for one group.

    python run.py cg          # uses config/cg.json

Output: output/{slug}.json   (one JSON per group)
        output/index.html     (ONE combined dashboard, rebuilt every run)
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

    build_index(OUT_DIR)   # rebuild the single combined dashboard from all group JSONs
    print(f"\nSaved output/{slug}.json  |  {len(companies)} companies  |  ${cost['cost_usd']}")
    print(f"Rebuilt output/index.html")


# ── combined dashboard ────────────────────────────────────────────────────────

REL_COLORS = {"subsidiary": "#27ae60", "brand": "#2980b9", "property": "#16a085",
              "investment": "#8e44ad"}


def _row(c, indent, flag=""):
    img = (f'<img src="{c["image"]}" style="width:18px;height:18px;object-fit:contain;'
           f'vertical-align:middle;margin-right:6px">' if c.get("image") else "")
    desc = c.get("description") or ""
    return (f'<tr><td style="padding-left:{12 + indent*20}px">{img}<b>{c["name"]}</b>{flag}'
            f'{"<br><small style=color:#888>" + desc + "</small>" if desc else ""}</td>'
            f'<td style="color:{REL_COLORS.get(c.get("relationship"),"#777")};font-size:11px">'
            f'{c.get("relationship","")}</td><td style="font-size:11px;color:#555">'
            f'{c.get("sector","")}</td></tr>')


def _group_section(result):
    """One <details> block for a group: its division-grouped company table."""
    by_div, by_parent = {}, {}
    for c in result["companies"]:
        by_div.setdefault(c.get("division") or "(none)", []).append(c)
        if c.get("parent"):
            by_parent.setdefault(c["parent"], []).append(c)

    rows = ""
    for div, members in sorted(by_div.items(), key=lambda x: -len(x[1])):
        rows += (f'<tr><td colspan=3 style="background:#eef2f7;font-weight:bold;'
                 f'padding:6px 12px">▸ {div} ({len(members)})</td></tr>')
        for c in members:
            if c.get("parent"):
                continue
            rows += _row(c, 1)
            for ch in by_parent.get(c["name"], []):
                rows += _row(ch, 2, ' <span style="color:#e67e22;font-size:9px">~llm</span>')

    lc = result["llm_cost"]
    return (f'<details id="{result["slug"]}" class="grp">'
            f'<summary><b>{result["group"]}</b> '
            f'<span class="cnt">{result["company_count"]}</span>'
            f'<span class="meta">${lc["cost_usd"]} · {lc["calls"]} calls · '
            f'<a href="{result["url"]}" target="_blank">site</a></span></summary>'
            f'<table>{rows}</table></details>')


def build_index(out_dir):
    """Load every output/{slug}.json and render ONE combined dashboard.
    Also removes any stale per-group HTML left from older runs."""
    results = []
    for f in sorted(out_dir.glob("*.json")):
        if f.name == "cache.json":
            continue
        try:
            results.append(json.loads(f.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue
    results.sort(key=lambda r: -r.get("company_count", 0))

    # drop legacy per-group html files (only index.html survives)
    for h in out_dir.glob("*.html"):
        if h.name != "index.html":
            h.unlink()

    total = sum(r.get("company_count", 0) for r in results)
    cost = sum((r.get("llm_cost", {}) or {}).get("cost_usd", 0) for r in results)
    toc = " ".join(f'<a href="#{r["slug"]}">{r["group"]} '
                   f'<b>{r["company_count"]}</b></a>' for r in results)
    sections = "".join(_group_section(r) for r in results)

    (out_dir / "index.html").write_text(f"""<!doctype html><meta charset=utf-8>
<title>Conglomerates — {len(results)} groups</title>
<style>
body{{font-family:-apple-system,Segoe UI,sans-serif;margin:0;background:#f5f6fa;color:#222}}
.h{{background:#2c3e50;color:#fff;padding:16px 24px;position:sticky;top:0;z-index:5}}
.h h1{{margin:0;font-size:19px}}.h small{{opacity:.8}}
.toc{{padding:12px 24px;background:#fff;border-bottom:1px solid #e2e6ea;
line-height:2.2}}.toc a{{display:inline-block;background:#eef2f7;color:#2c3e50;
text-decoration:none;padding:3px 10px;border-radius:12px;margin:2px;font-size:12px}}
.toc a b{{color:#e67e22}}
.grp{{background:#fff;margin:14px 24px;border:1px solid #e2e6ea;border-radius:8px;
overflow:hidden}}
.grp>summary{{cursor:pointer;padding:12px 16px;font-size:15px;list-style:none;
display:flex;align-items:center;gap:10px}}
.grp>summary::-webkit-details-marker{{display:none}}
.cnt{{background:#27ae60;color:#fff;border-radius:10px;padding:1px 9px;font-size:12px}}
.meta{{margin-left:auto;color:#888;font-size:11px;font-weight:normal}}
.meta a{{color:#2980b9}}
table{{width:100%;border-collapse:collapse}}td{{padding:5px 12px;
border-bottom:1px solid #f3f3f3;font-size:12px;vertical-align:top}}
</style>
<div class=h><h1>Nepal Conglomerates — {len(results)} groups · {total} companies</h1>
<small>config-driven extractor · total LLM cost ${cost:.4f}</small></div>
<div class=toc>{toc}</div>
{sections}""", encoding="utf-8")


if __name__ == "__main__":
    main()
