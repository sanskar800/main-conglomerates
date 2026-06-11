"""Config-driven pipeline:  discover pages -> extract -> apply rules.

The config decides WHAT to scrape (discovery) and HOW to clean it (rules).
The LLM only reads page content; deterministic rules from the config decide
what survives — which is what keeps it accurate as more sites are added.
"""
import re
from collections import defaultdict

from . import scraper
from .text import (domain_of, nkey, fuzzy_key, clean_division_name, headings)

SUBPAGE_ANCHORS = ("read more", "learn more", "view more", "explore", "details", "know more")
JUNK_CHILD = ("product", "catalogue", "faq", "about", "contact", "career", "news",
              "media", "gallery", "vision", "mission", "history", "team", "csr")
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")


# ── 1. discovery (config-driven, no LLM) ──────────────────────────────────────

def discover_pages(config, cache):
    """Page URLs to scrape. Either an explicit list (sites whose nav links don't
    work — WordPress ?page_id=, JS nav) or the children of a named nav section."""
    disc = config.get("discovery", {})
    home = domain_of(config["url"])

    if disc.get("pages"):
        return [{"url": u, "section": u.rstrip("/").split("/")[-1].replace("-", " ").title()}
                for u in disc["pages"]]

    nav = (scraper.resource(config["url"], cache).get("data") or {}).get("nav") or []

    pages, seen = [], set()
    want = (disc.get("nav_section") or "").lower()
    for item in nav:
        if want and want in (item.get("title") or "").lower():
            for ch in (item.get("children") or []):
                u, t = ch.get("url"), (ch.get("title") or "").strip()
                if (u and u.startswith("http") and nkey(u) not in seen
                        and (not disc.get("same_domain_only") or domain_of(u) == home)
                        and not any(j in t.lower() for j in JUNK_CHILD)):
                    seen.add(nkey(u))
                    pages.append({"url": u, "section": t})
    return pages


def discover_detail_pages(pages_by_url, section_of, home, config):
    """Optional one level of Read-More detail links (config: follow_read_more).
    Returns {detail_url: parent_section} and {nkey(detail_url): parent_section}."""
    if not config.get("discovery", {}).get("follow_read_more"):
        return {}, {}
    have = {nkey(u) for u in pages_by_url}
    subs, sub_section = {}, {}
    for url, page in pages_by_url.items():
        parent = section_of.get(nkey(url), "")
        for anchor, link in _MD_LINK_RE.findall(page.get("markdown", "") or ""):
            clean = link.rstrip("/")
            if (nkey(clean) not in have and domain_of(link) == home
                    and anchor.strip().lower() in SUBPAGE_ANCHORS):
                subs[clean] = parent
                sub_section[nkey(clean)] = parent
                have.add(nkey(clean))
    return subs, sub_section


# ── 2. rules (config-driven, deterministic) ───────────────────────────────────

def keep_only_headings(companies, heads_by_url):
    """Rule name_must_be_heading: drop any entity whose name is not a page heading.
    Headings come from <h1>-<h6>; an LLM-invented name won't be one."""
    head_keys = {nkey_url: {fuzzy_key(h) for h in hs} for nkey_url, hs in heads_by_url.items()}
    out = []
    for c in companies:
        keys = head_keys.get(nkey(c.get("source_url")), set())
        fk = fuzzy_key(c["name"])
        if fk and any(fk == hk or fk in hk or hk in fk for hk in keys):
            out.append(c)
    return out


def drop_noise(companies, config):
    rules = config.get("rules", {})
    bad = [b.lower() for b in rules.get("drop_if_contains", [])]
    minlen = rules.get("min_name_length", 3)
    out = []
    for c in companies:
        n = (c.get("name") or "").strip()
        if len(re.sub(r"[^\w]", "", n)) < minlen:
            continue
        if any(b in n.lower() for b in bad):
            continue
        out.append(c)
    return out


def structural_keys(config, cache):
    """Fuzzy-keys of the group's own nav/footer link titles (CG Motors, About,
    CG Mansion...). These echo in every page's footer; on a thin page the LLM
    extracts them as fake companies."""
    keys = set()
    data = (scraper.resource(config["url"], cache).get("data") or {})

    def walk(items):
        for it in items or []:
            t = (it.get("title") or "").strip()
            if t:
                keys.add(fuzzy_key(clean_division_name(t)))
            walk(it.get("children"))

    walk(data.get("nav"))
    walk(data.get("footer"))
    return keys


def drop_structural_echoes(companies, struct_keys):
    """Drop an entity that matches a nav/footer structural name, UNLESS it is
    the anchor of its own page (its name == its division — e.g. 'CG Foods' on
    the CG Foods page is kept; 'CG Infra' echoed on the energy-drink page is not)."""
    out = []
    for c in companies:
        nk = fuzzy_key(c["name"])
        own = fuzzy_key(c.get("division") or "")
        if nk in struct_keys and nk != own:
            continue
        out.append(c)
    return out


def apply_division(companies, section_of):
    """Rule division_from=page: a company's division is the page it came from."""
    for c in companies:
        sec = section_of.get(nkey(c.get("source_url")), "")
        c["division"] = clean_division_name(sec.split("/")[0]) or None
    return companies


def dedup(companies):
    groups, order = {}, []
    for c in companies:
        fk = fuzzy_key(c["name"])
        if not fk:
            continue
        if fk not in groups:
            groups[fk] = []
            order.append(fk)
        groups[fk].append(c)
    out = []
    for fk in order:
        es = groups[fk]
        canon = min(es, key=lambda c: len(c.get("name") or ""))
        first = lambda f: next((e[f] for e in es if e.get(f)), None)
        best_desc = max((e.get("description") or "" for e in es), key=len, default="")
        out.append({"name": canon["name"], "division": first("division"),
                    "parent": first("parent"),
                    "relationship": canon.get("relationship") or first("relationship"),
                    "sector": canon.get("sector") or first("sector"),
                    "description": best_desc or None, "image": first("image"),
                    "website": first("website"), "source_url": first("source_url")})
    return out


def resolve_parents(companies, config):
    """Rule nest_brand_under_company_only: keep parent only if it resolves to a
    real COMPANY (subsidiary/property) and the child is a brand."""
    if not config.get("rules", {}).get("nest_brand_under_company_only", True):
        return companies
    by = {fuzzy_key(c["name"]): c for c in companies}
    for c in companies:
        p = c.get("parent")
        parent = by.get(fuzzy_key(clean_division_name(p))) if p else None
        if (parent and parent["name"] != c["name"]
                and c.get("relationship") == "brand"
                and parent.get("relationship") in ("subsidiary", "property")):
            c["parent"] = parent["name"]
        else:
            c["parent"] = None
    return companies


# ── 3. orchestration ──────────────────────────────────────────────────────────

def run_group(config, gemini, cache):
    name, home = config["name"], domain_of(config["url"])
    pages = discover_pages(config, cache)
    print(f"  discovered {len(pages)} pages: {[p['section'] for p in pages]}")

    section_of = {nkey(p['url']): p['section'] for p in pages}
    pages_by_url = {p["url"]: p for p in scraper.pages([p["url"] for p in pages], cache)}

    subs, sub_section = discover_detail_pages(pages_by_url, section_of, home, config)
    if subs:
        print(f"  +{len(subs)} detail pages")
        for p in scraper.pages(list(subs), cache):
            pages_by_url[p["url"]] = p
            section_of[nkey(p["url"])] = sub_section.get(nkey(p["url"]), "")

    companies, heads_by_url = [], {}
    for url, page in pages_by_url.items():
        md = page.get("markdown")
        if page.get("error") or not md:
            continue
        heads_by_url[nkey(url)] = headings(md)
        got = gemini.extract(md, name, section_of.get(nkey(url), ""), url)
        for c in got:
            if isinstance(c, dict):
                c.setdefault("source_url", url)
        companies.extend(c for c in got if isinstance(c, dict))

    companies = apply_division(companies, section_of)

    before = len(companies)
    if config.get("rules", {}).get("name_must_be_heading"):
        companies = keep_only_headings(companies, heads_by_url)
        print(f"  heading-rule: {before} -> {len(companies)} (dropped non-heading)")

    companies = drop_structural_echoes(companies, structural_keys(config, cache))
    companies = drop_noise(companies, config)
    companies = dedup(companies)
    companies = resolve_parents(companies, config)
    print(f"  final: {len(companies)} companies (from {before} extracted)")
    return companies
