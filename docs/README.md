# Realtor's Practice

This is a simplified version of the Realtor scraping project adapted for
demonstration purposes.  The project consists of a core scraping
pipeline, a set of parser modules and configuration files.  The key
changes from the original version are:

- **Configuration‑driven:** The list of sites to scrape is no longer
  hard‑coded in `main.py`.  Instead, sites are defined in
  `config.yaml` and can be enabled or disabled without editing
  code.
- **Manageable via script:** A new `manage_config.py` utility can be
  used to add or remove site definitions and generate parser stubs.
- **Simplified scraping engine:** The Playwright‑based deep crawler has
  been replaced with a basic HTTP fetch.  Extend `core/scraper_engine.py`
  to restore full functionality.

Refer to `main.py` for the entrypoint and `core/cleaner.py` for the
normalization logic.  You can add additional site configurations in
`parsers/specials.py` and update `config.yaml` accordingly.