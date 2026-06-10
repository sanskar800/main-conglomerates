"""Gemini extraction. The prompt is generic (no real-company example names)
so the model can't echo placeholders as fake entities on a thin page."""
import json
import time
import urllib.request

PRICE_IN = 0.30 / 1_000_000
PRICE_OUT = 2.50 / 1_000_000

EXTRACT_PROMPT = """Extract every subsidiary, brand, hotel/property, and invested company that ACTUALLY APPEARS in the {group} website page below.

INCLUDE: companies and product/hotel brands the group owns, operates, or invested in (even abroad).
EXCLUDE: the group's own name; pure third-party vendors not owned; generic locations; website URLs;
individual products / SKUs / flavours / pack-sizes (keep only the base brand once).

CRITICAL: only output names present in the content below. If nothing qualifies, return [].
Never invent names.

Fields per item:
- name: clean name exactly as written (Title Case)
- parent: set ONLY if the page explicitly states this entity is a brand/sub-unit OF a specific named
  company on the same page; else null. Never nest sibling companies.
- relationship: subsidiary | brand | property | investment
- sector: food/finance/electronics/cement/hospitality/education/energy/telecom/real_estate/beverage/
  brewery/automotive/packaging/insurance/media/other
- description: the descriptive text the page gives (2-4 sentences), else null
- image: logo/photo image URL near it (from a markdown ![..](url)), else null
- website: the entity's own website if linked, else null

Return ONLY a JSON array using this SHAPE (do not copy placeholder values):
[{{"name": "<Company Pvt. Ltd.>", "parent": null, "relationship": "subsidiary", "sector": "<sector>", "description": null, "image": null, "website": null}}]

Section: {section}

{content}"""


class Gemini:
    def __init__(self, key, model, cache, cost_log):
        self.key, self.model, self.cache, self.cost_log = key, model, cache, cost_log

    def extract(self, markdown, group, section, page_url):
        ckey = f"extract:{group}:{page_url}"
        ukey = "usage:" + ckey
        if self.cache.has(ckey):
            self.cost_log.append(self.cache.get(ukey) or {"in": 0, "out": 0})
            return self.cache.get(ckey)
        prompt = EXTRACT_PROMPT.format(group=group, section=section, content=markdown[:12000])
        result, usage = self._call(prompt)
        self.cache.set(ckey, result)
        self.cache.set(ukey, usage)
        self.cost_log.append(usage)
        return result

    def _call(self, prompt):
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{self.model}:generateContent?key={self.key}")
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json",
                                 "thinkingConfig": {"thinkingBudget": 0}},
        }
        for attempt in range(3):
            try:
                req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                             headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=90) as r:
                    resp = json.load(r)
                txt = resp["candidates"][0]["content"]["parts"][0]["text"]
                um = resp.get("usageMetadata", {})
                return json.loads(txt), {"in": um.get("promptTokenCount", 0),
                                         "out": um.get("candidatesTokenCount", 0)}
            except Exception as e:
                print(f"    Gemini error: {e}, retry {attempt + 1}")
                time.sleep(2 ** attempt)
        return [], {"in": 0, "out": 0}


def cost_of(cost_log):
    i = sum(u.get("in", 0) for u in cost_log)
    o = sum(u.get("out", 0) for u in cost_log)
    return {"calls": len(cost_log), "input_tokens": i, "output_tokens": o,
            "cost_usd": round(i * PRICE_IN + o * PRICE_OUT, 4)}
