#!/usr/bin/env python3
"""Sweep what is on Australian subscription streaming services, from TMDB's watch providers.

TMDB's where-to-watch data comes from JustWatch and is served through TMDB's official API
(https://developer.themoviedb.org/reference/discover-movie), with the user's own key in the
CI/CD variable TMDB_API_KEY (v3 API key or v4 read access token). No scraping.

For each service and for movies and TV it pages through /discover with watch_region=AU and
flatrate (subscription) monetisation, then looks up IMDb ids (/external_ids, cached between
runs). The result, cache/tmdb_au.json, is used for:
  * the movie, TV and For You pages' "where to watch" (replacing the 7 Nov 2026 JustWatch
    snapshot), and
  * the New on streaming page: TMDB has no "date added", so a title counts as new when it
    shows up on a service that it was not on at the previous sweep. The first sweep is the
    baseline; new arrivals are listed from the next one.

The GitLab CI cache keeps the file between pipelines. Code pushes reuse it if it is younger
than --max-age-days; scheduled and manual pipelines pass --force. Without a key it exits 0.

Usage: python tools/fetch_tmdb_au.py [--out cache/tmdb_au.json] [--force]
       [--max-age-days 13] [--max-pages 500] [--max-lookups 40000] [--workers 8]
"""
import argparse
import concurrent.futures as cf
import datetime as dt
import json
import os
import pathlib
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
REGION = 'AU'
# Our service codes (the movie finder's JustWatch codes, plus two more for the New page) and
# the TMDB provider names they match. Names are compared lower-case, letters and digits only.
SERVICES = {
    'nfx': ('Netflix', ['netflix']),
    'prv': ('Prime Video', ['amazonprimevideo', 'primevideo']),
    'dnp': ('Disney+', ['disneyplus']),
    'stn': ('Stan', ['stan']),
    'pmp': ('Paramount+', ['paramountplus']),
    'mxx': ('HBO Max', ['hbomax', 'max']),
    'atp': ('Apple TV', ['appletvplus', 'appletv']),
    'bng': ('Binge', ['binge']),
    'fxn': ('Foxtel Now', ['foxtelnow']),
}
KINDS = {'m': 'movie', 't': 'tv'}


class Stop(Exception):
    pass


class Api:
    def __init__(self, key, base):
        self.base, self.lock, self.count = base, threading.Lock(), 0
        key = key.strip()
        self.headers = {'Accept': 'application/json', 'User-Agent': 'movie-finder-refresh/1.0'}
        self.params = {}
        if key.startswith('eyJ'):
            self.headers['Authorization'] = f'Bearer {key}'
        else:
            self.params['api_key'] = key

    def get(self, path, **params):
        url = f'{self.base}{path}?{urllib.parse.urlencode({**self.params, **params})}'
        for attempt in range(6):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=self.headers), timeout=40) as r:
                    with self.lock:
                        self.count += 1
                    return json.load(r)
            except urllib.error.HTTPError as e:
                with self.lock:
                    self.count += 1
                if e.code in (401, 403):
                    raise Stop(f'HTTP {e.code} from TMDB on {path} (check TMDB_API_KEY)')
                if e.code == 404:
                    return None
                if e.code == 429 or e.code >= 500:
                    time.sleep(float(e.headers.get('Retry-After') or 0) or 2 ** attempt)
                    continue
                raise Stop(f'HTTP {e.code} from TMDB on {path}')
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                if attempt < 5:
                    time.sleep(2 ** attempt)
                    continue
                raise Stop(f'Network error on {path}: {e}')
        raise Stop(f'TMDB kept refusing {path}')


def simple(name):
    return re.sub(r'[^a-z0-9]', '', (name or '').lower().replace('+', 'plus'))


def provider_ids(api):
    """Map our codes to TMDB provider ids for AU (movie and TV lists are merged)."""
    found = {code: set() for code in SERVICES}
    for kind in KINDS.values():
        res = api.get(f'/watch/providers/{kind}', watch_region=REGION, language='en-AU') or {}
        for p in res.get('results') or []:
            s = simple(p.get('provider_name'))
            for code, (_, names) in SERVICES.items():
                if s in names:
                    found[code].add(p['provider_id'])
    return {c: sorted(ids) for c, ids in found.items() if ids}


CHUNKS = [(None, '1979-12-31'), ('1980-01-01', '1999-12-31'), ('2000-01-01', '2009-12-31'),
          ('2010-01-01', '2014-12-31'), ('2015-01-01', '2019-12-31'), ('2020-01-01', '2022-12-31'),
          ('2023-01-01', None)]


def sweep_one(api, kind, params, max_pages, workers):
    first = api.get(f'/discover/{KINDS[kind]}', page=1, **params) or {}
    total_pages = int(first.get('total_pages') or 1)
    pages = min(total_pages, max_pages, 500)
    results = list(first.get('results') or [])
    with cf.ThreadPoolExecutor(workers) as ex:
        for res in ex.map(lambda n: api.get(f'/discover/{KINDS[kind]}', page=n, **params) or {}, range(2, pages + 1)):
            results.extend(res.get('results') or [])
    return results, total_pages > pages, int(first.get('total_results') or 0)


def sweep(api, code, ids, kind, max_pages, workers):
    params = dict(watch_region=REGION, with_watch_providers='|'.join(map(str, ids)),
                  with_watch_monetization_types='flatrate', include_adult='false',
                  sort_by='popularity.desc', language='en-AU')
    results, truncated, total = sweep_one(api, kind, params, max_pages, workers)
    if truncated and max_pages >= 500:
        # TMDB stops at page 500 (10,000 titles): split big catalogues by release date.
        field = 'primary_release_date' if kind == 'm' else 'first_air_date'
        results, truncated = [], False
        for lo, hi in CHUNKS:
            extra = dict(params)
            if lo:
                extra[f'{field}.gte'] = lo
            if hi:
                extra[f'{field}.lte'] = hi
            r, t, _ = sweep_one(api, kind, extra, max_pages, workers)
            results.extend(r)
            truncated = truncated or t
    return results, truncated, total


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--out', default=str(ROOT / 'cache/tmdb_au.json'))
    p.add_argument('--force', action='store_true')
    p.add_argument('--max-age-days', type=float, default=13)
    p.add_argument('--max-pages', type=int, default=500)
    p.add_argument('--max-lookups', type=int, default=40000)
    p.add_argument('--workers', type=int, default=8)
    a = p.parse_args()
    out = pathlib.Path(a.out)
    old = {}
    if out.exists():
        try:
            old = json.loads(out.read_text())
        except ValueError:
            old = {}
    if old.get('fetchedAtUnix') and old.get('complete') and not a.force and (time.time() - old['fetchedAtUnix']) / 86400 < a.max_age_days:
        print(f"tmdb-au: cached sweep is {(time.time() - old['fetchedAtUnix']) / 86400:.1f} days old, not fetching")
        return
    key = os.environ.get('TMDB_API_KEY', '').strip()
    if not key:
        print('tmdb-au: no TMDB_API_KEY set, skipping (pages keep the 7 Nov 2026 snapshot)')
        return
    api = Api(key, os.environ.get('TMDB_API_BASE', 'https://api.themoviedb.org/3'))
    now = int(time.time())
    try:
        pids = provider_ids(api)
        titles, truncated, totals = {}, [], {}
        for code, ids in pids.items():
            for kind in KINDS:
                results, trunc, total = sweep(api, code, ids, kind, a.max_pages, a.workers)
                totals[f'{code}:{kind}'] = total
                if trunc:
                    truncated.append(f'{code}:{kind}')
                for r in results:
                    k = f"{kind}{r['id']}"
                    t = titles.setdefault(k, {
                        'title': r.get('title') or r.get('name') or r.get('original_title') or r.get('original_name'),
                        'date': r.get('release_date') or r.get('first_air_date') or None,
                        'poster': r.get('poster_path'), 'overview': (r.get('overview') or '')[:400] or None,
                        'genres': r.get('genre_ids') or [], 'lang': r.get('original_language'),
                        'popularity': r.get('popularity'), 'on': {}})
                    t['on'][code] = 0
        # IMDb ids: reuse the cached map, look up the rest.
        imdb_map = dict(old.get('imdb') or {})
        todo = [k for k in titles if k not in imdb_map][:a.max_lookups]

        def lookup(k):
            res = api.get(f'/{KINDS[k[0]]}/{k[1:]}/external_ids') or {}
            iid = res.get('imdb_id')
            return k, iid if iid and str(iid).startswith('tt') else ''
        with cf.ThreadPoolExecutor(a.workers) as ex:
            for k, iid in ex.map(lookup, todo):
                imdb_map[k] = iid
        missing = sum(1 for k in titles if k not in imdb_map)
        genres = {}
        for kind in KINDS.values():
            for g in (api.get(f'/genre/{kind}/list', language='en') or {}).get('genres') or []:
                genres[str(g['id'])] = g['name']
    except Stop as e:
        print(f'tmdb-au: sweep stopped: {e}', file=sys.stderr)
        print('tmdb-au: keeping the previous data' if old else 'tmdb-au: no previous data', file=sys.stderr)
        return

    # "New" = on a service now but not at the previous complete sweep. Keep first-seen dates.
    prev_titles = old.get('titles') or {}
    baseline = old.get('baselineAtUnix') if prev_titles and old.get('complete') else None
    for k, t in titles.items():
        prev_on = (prev_titles.get(k) or {}).get('on') or {}
        for code in t['on']:
            if code in prev_on:
                t['on'][code] = prev_on[code]
            elif baseline and code in (old.get('providers') or {}):
                t['on'][code] = now
            # else 0: there at the baseline (or the service is newly swept), not "new"
    complete = not truncated and missing == 0
    data = {
        'source': 'TMDB watch providers (data from JustWatch)',
        'sourceUrl': 'https://www.themoviedb.org/',
        'region': REGION,
        'fetchedAt': dt.datetime.fromtimestamp(now, dt.timezone.utc).isoformat(timespec='seconds'),
        'fetchedAtUnix': now,
        'previousAtUnix': old.get('fetchedAtUnix') if baseline else None,
        'baselineAtUnix': baseline or now,
        'complete': complete,
        'truncated': truncated,
        'requests': api.count,
        'totals': totals,
        'providers': {c: {'name': SERVICES[c][0], 'tmdb': ids} for c, ids in pids.items()},
        'genres': genres,
        'imdb': {k: v for k, v in imdb_map.items() if k in titles},
        'titles': titles,
    }
    if not complete and old.get('complete'):
        # Don't let a partial sweep make titles look like they left; keep the last good one.
        print(f'tmdb-au: sweep incomplete (truncated {truncated}, {missing} without IMDb lookup); keeping previous',
              file=sys.stderr)
        old['imdb'] = {**(old.get('imdb') or {}), **data['imdb']}
        data = old
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')))
    tmp.replace(out)
    new = sum(1 for t in titles.values() for v in t['on'].values() if v == now)
    print(json.dumps({'requests': api.count, 'providers': {c: len(i) for c, i in pids.items()}, 'titles': len(titles),
                      'newSincePrevious': new, 'baseline': not baseline, 'complete': complete,
                      'truncated': truncated, 'lookups': len(todo)}))


if __name__ == '__main__':
    main()
