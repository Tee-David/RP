# core/dispatcher.py
import importlib
import inspect
from typing import Any, Dict, List
from core.scraper_engine import generic_deep_crawl

SPECIAL = {
    # keep direct modules for specialized sites
    "npc": "parsers.npc",
    "propertypro": "parsers.propertypro",
    "buyletlive": "parsers.buyletlive",
    "hutbay": "parsers.hutbay",
    "castles": "parsers.castles",
    "hata": "parsers.hata",
}

def get_parser(site_key: str):
    """
    Resolves a parser module with a scrape() function.
    If no special module exists, tries parsers.<site_key>.
    Wraps with ParserAdapter so kwargs mismatches don't break.
    """
    module_name = SPECIAL.get(site_key, f"parsers.{site_key}")
    try:
        mod = importlib.import_module(module_name)
    except Exception:
        # If the site has no module, return a Generic adapter
        return ParserAdapter(site_key, None)
    return ParserAdapter(site_key, mod)

class ParserAdapter:
    """
    Uniform interface around parser modules.
    - Attempts to call module.scrape(**kwargs) with only supported params.
    - If the module is None or call fails/returns 0, falls back to generic_deep_crawl.
    """

    def __init__(self, site_key: str, module):
        self.site_key = site_key
        self.module = module
        self.start_url = getattr(module, "START_URL", None) if module else None

    def _call_scrape_if_available(self, kwargs: Dict[str, Any]) -> List[Dict]:
        if not self.module or not hasattr(self.module, "scrape"):
            return []

        fn = getattr(self.module, "scrape")
        sig = inspect.signature(fn)
        allowed = {k: v for k, v in kwargs.items() if k in sig.parameters}

        try:
            return fn(**allowed)
        except TypeError as e:
            # Retry without kwargs ONLY if function actually takes no required params
            try:
                if all(p.default != inspect._empty or p.kind in (p.VAR_KEYWORD, p.VAR_POSITIONAL)
                       for p in sig.parameters.values()):
                    return fn()
            except Exception:
                pass
            # Reraise to trigger generic fallback
            raise e

    def scrape(self, **kwargs) -> List[Dict]:
        # 1) Try module scrape
        try:
            items = self._call_scrape_if_available(kwargs)
        except Exception:
            items = []

        # 2) If module missing or empty -> generic deep crawl
        if not items:
            start_url = kwargs.get("site", {}).get("url") or getattr(self.module, "START_URL", None)
            if not start_url:
                # if absolutely no URL known, nothing we can do
                return []
            items = generic_deep_crawl(start_url)

        return items
