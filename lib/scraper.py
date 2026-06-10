"""Scraper API + browser-infra fallback.

  resource(url)  -> structured nav/footer JSON   (GET /get/resource)
  pages(urls)    -> [{url, markdown}]             (POST /call, path=page)
  browser(url)   -> rendered HTML                 (GET browser /forward)
"""
import json
import re
import urllib.request

SCRAPER_BASE = "http://172.235.34.34:8000"
BROWSER_BASE = "http://172.237.41.189:8000"

_TAG_RE = re.compile(r"<[^>]+>")
_DROP_RE = re.compile(r"<(script|style|noscript)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_IMG_RE = re.compile(r'<img[^>]+src="([^"]+)"', re.IGNORECASE)


def _get(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="ignore")


def resource(url, cache):
    key = f"resource:{url}"
    if not cache.has(key):
        try:
            cache.set(key, json.loads(_get(f"{SCRAPER_BASE}/get/resource/{url}", 30)))
        except Exception as e:
            cache.set(key, {"error": str(e)})
    return cache.get(key)


def _call(urls):
    body = json.dumps({"path": "page", "entity": urls}).encode()
    req = urllib.request.Request(f"{SCRAPER_BASE}/call/", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.load(r).get("data") or []


def pages(urls, cache):
    """Fetch page markdown; browser-render anything that comes back empty/failed."""
    key = f"pages:{','.join(sorted(urls))}"
    if cache.has(key):
        return cache.get(key)
    try:
        data = _call(urls)
    except Exception as e:
        return cache.set(key, [{"url": u, "error": str(e)} for u in urls])
    for i, d in enumerate(data):
        if d.get("error") or len(d.get("markdown") or "") < 200:
            md = browser_markdown(d.get("url") or "")
            if md:
                data[i] = {"url": d.get("url"), "markdown": md}
    return cache.set(key, data)


def browser_html(url):
    try:
        return _get(f"{BROWSER_BASE}/forward?url={url}", 120)
    except Exception:
        return ""


def browser_markdown(url):
    """Browser-rendered HTML reduced to text + image refs for the LLM."""
    html = browser_html(url)
    if not html:
        return ""
    html = _IMG_RE.sub(lambda m: f"\n![]({m.group(1)})\n", html)
    html = _DROP_RE.sub(" ", html)
    html = re.sub(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
                  lambda m: f"[{_TAG_RE.sub('', m.group(2)).strip()}]({m.group(1)})",
                  html, flags=re.DOTALL | re.IGNORECASE)
    text = _TAG_RE.sub("\n", html)
    text = re.sub(r"&[a-z]+;", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()
