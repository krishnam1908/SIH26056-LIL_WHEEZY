"""Scraper registry (Python port of src/scrapers/index.js).

Every source module is imported LAZILY. Importing this package never pulls in
Playwright or any other heavy/optional dependency; a source module is only
imported on the first real request for it via ``get_scraper`` (or the module
level ``__getattr__``). So ``get_scraper("spicejet")`` keeps working even when
Playwright — required only by the Playwright-backed sources
(indigo / airindia / airindiaexpress) — is not installed.

Adding a new source is ONE step:
  1. create scrapers/<source>.py
  2. add a ``(module_name, class_name)`` entry to ``_REGISTRY`` below
"""

import importlib

from .base import BaseScraper

# source key -> (module name, scraper class name).  Loaded on demand only.
_REGISTRY = {
    "akasa": ("akasa", "AkasaScraper"),
    "spicejet": ("spicejet", "SpiceJetScraper"),
    "indigo": ("indigo", "IndiGoScraper"),
    "airindia": ("airindia", "AirIndiaScraper"),
    "airindiaexpress": ("airindiaexpress", "AirIndiaExpressScraper"),
}

# class name -> source key, used to serve ``from .scrapers import <Class>`` lazily.
_CLASS_TO_SOURCE = {
    class_name: source for source, (_, class_name) in _REGISTRY.items()
}

_cached_classes = {}


def _load_source(name):
    """Import (once) and cache the registered scraper class for ``name``."""
    try:
        return _cached_classes[name]
    except KeyError:
        module_name, class_name = _REGISTRY[name]
        module = importlib.import_module(f".{module_name}", package=__name__)
        cls = getattr(module, class_name)
        _cached_classes[name] = cls
        return cls


def _make_factory(name):
    """Build a callable that lazily loads ``name`` and instantiates it."""

    def factory(config=None):
        return _load_source(name)(config or {})

    return factory


# ``scrapers[name](config)`` -> lazy instance; ``list(scrapers)`` stays cheap.
scrapers = {
    source: _make_factory(source) for source in _REGISTRY
}


def get_scraper(name, config=None):
    """Instantiate the registered source adapter for ``name`` with the given config.

    The backing module is imported on demand, so requesting one source never
    forces other (possibly Playwright-heavy) sources to load.
    """
    factory = scrapers.get(name)
    if not factory:
        available = ", ".join(scrapers.keys())
        raise KeyError(f"Unknown scraper source '{name}'. Available: {available}")
    return factory(config or {})


def list_sources():
    """List all registered source keys without importing any source module."""
    return list(scrapers.keys())


def has_source(name):
    """True when the source is registered (no module import needed)."""
    return name in scrapers


def __getattr__(name):
    """Serve ``from .scrapers import SomeScraper`` lazily (PEP 562).

    Resolves registered scraper class names (e.g. ``SpiceJetScraper``) to the
    matching source module without forcing other sources to load.
    """
    source = _CLASS_TO_SOURCE.get(name)
    if source is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return _load_source(source)


__all__ = [
    "scrapers",
    "get_scraper",
    "list_sources",
    "has_source",
    "BaseScraper",
    *_CLASS_TO_SOURCE,
]
