from parsers import specials

def scrape(fallback_order, filters, start_url=None, site=None):
    return specials.scrape(fallback_order, filters, start_url=start_url, site=site, site_key="propertypro")
