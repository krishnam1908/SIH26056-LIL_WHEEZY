"""Stream quote fetcher for the continuous scraping engine.
Fetches real flight quotes from a single carrier, route, and date cell and prints JSON.
"""

import sys
import json
import os
from datetime import datetime, timezone

# Ensure project root is in sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from backend.scraper_python.scrapers import get_scraper


def fetch_cell(carrier: str, origin: str, destination: str, travel_date: str):
    scraper = get_scraper(carrier)
    result = scraper.scrape({
        'origin': origin,
        'destination': destination,
        'travelDate': travel_date,
        'currency': 'INR'
    })
    fares = result.get('fares', [])
    # Format datetimes to ISO string for JSON serialization
    serialized = []
    for f in fares:
        item = dict(f)
        for k in ('travelDate', 'collectionDate', 'scrapedAt'):
            if k in item and hasattr(item[k], 'isoformat'):
                item[k] = item[k].isoformat()
        serialized.append(item)
    return serialized


if __name__ == '__main__':
    carrier = sys.argv[1] if len(sys.argv) > 1 else 'akasa'
    origin = sys.argv[2] if len(sys.argv) > 2 else 'DEL'
    destination = sys.argv[3] if len(sys.argv) > 3 else 'BOM'
    travel_date = sys.argv[4] if len(sys.argv) > 4 else datetime.now(timezone.utc).strftime('%Y-%m-%d')

    try:
        fares = fetch_cell(carrier, origin, destination, travel_date)
        sys.stdout.write(json.dumps({'ok': True, 'fares': fares}, default=str))
    except Exception as err:
        sys.stderr.write(str(err))
        sys.stdout.write(json.dumps({'ok': False, 'error': str(err), 'fares': []}))
        sys.exit(1)
