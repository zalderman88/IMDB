"""Write research/imdb/india_titles.json: IMDb ids of Indian films and shows, from two public sources.

* Wikidata: every item whose country of origin (P495) is India (Q668) and that has an IMDb id
  (P345). One SPARQL query. Checked against 54,000 films with a JustWatch country: 99% of the
  matches are Indian productions.
* IMDb alternative titles (title.akas): ids matching research/title_quality.akas_pattern.
  Used for movies only, and only when neither JustWatch nor Wikidata knows the country.

If a source can't be read, the previous list for that source is kept so a refresh never
silently lets Indian titles back in.

Usage:
  python tools/refresh_india.py                                 # download both
  python tools/refresh_india.py --akas title.akas.tsv.gz        # local akas file
"""
import argparse
import csv
import datetime
import gzip
import json
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'research'))
from title_quality import INDIA_TITLES, akas_pattern  # noqa: E402

AKAS_URL = 'https://datasets.imdbws.com/title.akas.tsv.gz'
SPARQL = 'https://query.wikidata.org/sparql'
QUERY = 'SELECT ?imdb WHERE { ?item wdt:P495 wd:Q668; wdt:P345 ?imdb. }'
UA = 'movie-finder-refresh/1.0 (personal, non-commercial)'
csv.field_size_limit(sys.maxsize)


def wikidata():
    url = SPARQL + '?' + urllib.parse.urlencode({'query': QUERY, 'format': 'json'})
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'application/sparql-results+json'})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                rows = json.load(r)['results']['bindings']
            break
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == 2:
                raise
            time.sleep(70)  # Wikidata asks clients to wait when it is busy
    ids = sorted({b['imdb']['value'] for b in rows if b['imdb']['value'].startswith('tt')})
    if len(ids) < 20000:
        raise RuntimeError(f'only {len(ids):,} Wikidata ids returned')
    return ids


def akas(source, ids):
    raw = urllib.request.urlopen(urllib.request.Request(source, headers={'User-Agent': UA}), timeout=600) \
        if source.startswith('https://') else open(source, 'rb')
    regions, rows = {}, 0
    with gzip.open(raw, 'rt', encoding='utf-8', newline='') as f:
        for r in csv.DictReader(f, delimiter='\t', quoting=csv.QUOTE_NONE):
            rows += 1
            if r['titleId'] in ids:
                d = regions.setdefault(r['titleId'], {})
                d[r['region']] = d.get(r['region'], 0) + 1
    if rows < 10_000_000:
        raise RuntimeError(f'only {rows:,} alternative-title rows read (truncated download?)')
    return sorted(t for t, d in regions.items() if akas_pattern(d)), len(regions)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--akas', default=AKAS_URL)
    a = p.parse_args()
    previous = json.loads(INDIA_TITLES.read_text()) if INDIA_TITLES.exists() else {}
    out = dict(previous)
    today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    try:
        out['wikidata'] = wikidata()
        out['wikidataAsOf'] = today
    except Exception as e:  # keep the old list rather than letting Indian titles back in
        print(f'Warning: Wikidata not refreshed ({e}); keeping {len(previous.get("wikidata", [])):,} previous ids')
    ids = set()
    for name in ('movies_1k.json', 'tv_1k.json'):
        path = ROOT / 'research/imdb' / name
        if path.exists():
            ids |= {x['imdbId'] for x in json.loads(path.read_text())}
    try:
        out['akas'], checked = akas(a.akas, ids)
        out['akasAsOf'] = today
        out['akasRule'] = 'IN alternative titles >= 3 with < 30 regions, or >= 2 with < 15 regions'
    except Exception as e:
        checked = 0
        print(f'Warning: IMDb alternative titles not refreshed ({e}); keeping previous list')
    if not out.get('wikidata'):
        raise SystemExit('No Wikidata India list available; refusing to build without it.')
    INDIA_TITLES.write_text(json.dumps(out, indent=0) + '\n')
    print(json.dumps({'wikidata': len(out.get('wikidata', [])), 'akas': len(out.get('akas', [])), 'akasChecked': checked}))


if __name__ == '__main__':
    main()
