"""Pure text helpers: URL keys, name normalisation, heading parsing."""
import re

_DESCRIPTOR_WORDS = {
    "assembly", "motorcycle", "motorcycles", "ev", "tyres", "tyre", "limited",
    "ltd", "pvt", "private", "p", "factory", "plant", "co", "company", "inc",
    "corp", "and", "the", "nepal",
}
_HEADING_RE = re.compile(r"^#{1,6}\s+(.+)$")
_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_IMG_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")


def domain_of(url):
    m = re.match(r"https?://([^/]+)", url or "")
    return m.group(1).lower().lstrip("www.") if m else ""


def nkey(url):
    """Scheme/host-insensitive URL key (http/https + www collapse)."""
    return re.sub(r"^https?://(www\.)?", "", (url or "")).rstrip("/").lower()


def fuzzy_key(name):
    """Normalised key for matching the same entity written two ways."""
    s = re.sub(r"[^\w\s]", " ", (name or "").lower())
    return " ".join(t for t in s.split() if t and t not in _DESCRIPTOR_WORDS)


def clean_division_name(s):
    """Strip group/page-title boilerplate: 'Chaudhary Group | Foods' -> 'Foods'."""
    parts = [p.strip() for p in re.split(r"\s*[|–]\s*|\s-\s", s or "") if p.strip()]
    bad = ("group", "archives", "businesses", "organisation", "organization")
    cand = [p for p in parts if not any(b in p.lower() for b in bad)]
    div = (cand[0] if cand else (parts[0] if parts else s or "")).strip()
    div = re.sub(r"\s+archives$", "", div, flags=re.IGNORECASE).strip()
    if div and (("-" in div or "_" in div) and " " not in div):
        div = re.sub(r"[-_]+", " ", div).strip()
    return div.title() if div.islower() else div


def headings(markdown):
    """All heading texts on a page (markdown ## ... and setext === / ---).
    These correspond to <h1>-<h6> in the source HTML."""
    out, lines = set(), (markdown or "").split("\n")
    for i, line in enumerate(lines):
        s = line.strip()
        m = _HEADING_RE.match(s)
        if m:
            out.add(_clean_heading(m.group(1)))
        elif i + 1 < len(lines) and re.match(r"^[=-]{3,}$", lines[i + 1].strip()) and s:
            out.add(_clean_heading(s))
    return {h for h in out if h}


def _clean_heading(t):
    t = _IMG_RE.sub("", t)
    t = _LINK_RE.sub(r"\1", t)
    return re.sub(r"\s+", " ", t).strip()
