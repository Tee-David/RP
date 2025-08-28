# core/dispatcher.py
#
# The dispatcher is responsible for locating and instantiating parser
# modules for each site key.  It supports a mapping of "special"
# parsers that override the default naming convention and falls back
# to a generic parser adapter when no module exists for a site.  The
# ParserAdapter class provides a uniform interface to call either a
# site‑specific ``scrape`` function or a generic deep crawl.

import importlib
from typing import Any, Dict


# Map specific site keys to bespoke parser modules.  If a key is not
# present here the dispatcher will attempt to import a module from
# ``parsers.<key>``.  If that fails it will use the generic
# special parser instead.
SPECIAL: Dict[str, str] = {
    # Add site keys here if they require a custom parser implementation
    # not following the generic pattern in parsers/specials.py
}


def get_parser(key: str) -> "ParserAdapter":
    """Return a ParserAdapter for the given site key.  The adapter
    will call the site's ``scrape`` function if available; otherwise
    it will delegate to the generic deep crawler.
    """
    module_name = SPECIAL.get(key, key)
    try:
        module = importlib.import_module(f"parsers.{module_name}")
    except ImportError:
        # Fall back to the generic parser in ``specials.py``
        module = importlib.import_module("parsers.specials")
    return ParserAdapter(module)


class ParserAdapter:
    """Adapter class that provides a uniform ``scrape`` method."""

    def __init__(self, module: Any):
        self.module = module

    def scrape(self, url: str, **kwargs) -> Any:
        """Call the module's ``scrape`` function with supported kwargs.

        If the module defines its own ``scrape`` function, it will be
        called with the provided arguments.  Otherwise, this method
        delegates to the ``generic_deep_crawl`` function in
        ``core.scraper_engine`` which handles generic scraping using
        Playwright.
        """
        # Introspect the module to determine which arguments are
        # accepted.  Pass through only those that are supported.
        func = getattr(self.module, "scrape", None)
        if func is None:
            # Fallback: call the generic crawler
            from core.scraper_engine import generic_deep_crawl
            return generic_deep_crawl(url, **kwargs)
        # Determine which kwargs this function supports
        import inspect
        sig = inspect.signature(func)
        allowed = {
            k: v for k, v in kwargs.items() if k in sig.parameters
        }
        return func(url, **allowed)