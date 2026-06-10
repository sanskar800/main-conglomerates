"""Tiny JSON file cache so re-runs don't re-hit the scraper / LLM."""
import json
from pathlib import Path


class Cache:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data = json.loads(self.path.read_text()) if self.path.exists() else {}

    def get(self, key):
        return self._data.get(key)

    def set(self, key, value):
        self._data[key] = value
        self.path.write_text(json.dumps(self._data, ensure_ascii=False, indent=2))
        return value

    def has(self, key):
        return key in self._data
