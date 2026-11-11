#!/usr/bin/env python3
"""Build the Coming soon page (coming.html): upcoming movies and new TV seasons in Australia.

Official API only (TMDB, the user's own key in the CI/CD variable TMDB_API_KEY). No scraping.

What counts as "coming soon" (window: 14 days ago to --days ahead):
  * Movies already listed on one of our AU subscription services (TMDB watch providers, which
    are JustWatch data) whose release is in the window: usually streaming originals, so the
    release date is the streaming date.
  * Movies with an Australian digital release date (TMDB release type 4) in the window. If
    no subscription service is listed yet, the page says "digital (rent or buy)".
  * Movies opening in Australian cinemas in the window (no streaming date known yet).
  * TV: new shows premiering, and new seasons (episode 1 of a season) of shows, from TMDB's
    next/last episode data. Services come from AU watch providers; otherwise the network.
TMDB has no "arrives on Stan on this date" data for titles that aren't on a service yet, so
the page falls back to the release/premiere date and says so.

The fetched list is kept in cache/coming_soon.json (GitLab CI cache). If TMDB fails, the old
list is reused; with no key at all the page says it isn't set up.

Usage: python tools/build_coming_soon.py [--cache cache/coming_soon.json]
       [--ratings /tmp/imdb/title.ratings.tsv.gz] [--out Coming_Soon_Android.html]
       [--days 180] [--offline]
"""
import argparse
import concurrent.futures as cf
import datetime as dt
import json
import os
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
import fetch_tmdb_au as tm  # noqa: E402  shared TMDB client, service codes, provider ids
from build_new_streaming import load_ratings, INDIAN_LANGS  # noqa: E402

TEMPLATE = ROOT / 'research/coming_soon_template.html'
STYLE_FROM = ROOT / 'research/new_streaming_template.html'
BACK_DAYS = 14
# Talk, News, Soap: daily shows that would flood the TV list.
TV_SKIP_GENRES = '10767|10763|10766'
IMG = 'https://image.tmdb.org/t/p/w185'


def day(s):
    try:
        return dt.date.fromisoformat((s or '')[:10])
    except ValueError:
        return None


def pages(api, path, params, n):
    out = []
    for p in range(1, n + 1):
        res = api.get(path, page=p, **params) or {}
        out += res.get('results') or []
        if p >= (res.get('total_pages') or 0):
            break
    return out


def au_services(details, by_pid):
    au = ((details.get('watch/providers') or {}).get('results') or {}).get('AU') or {}
    codes = []
    for p in au.get('flatrate') or []:
        c = by_pid.get(p.get('provider_id'))
        if c and c not in codes:
            codes.append(c)
    return codes, au.get('link') or ''


def is_indian(d):
    countries = set(d.get('origin_country') or []) | {c.get('iso_3166_1') for c in d.get('production_countries') or []}
    return d.get('original_language') in INDIAN_LANGS or 'IN' in countries


def movie_item(d, by_pid, start, end, genres):
    codes, link = au_services(d, by_pid)
    au = [r for c in (d.get('release_dates') or {}).get('results') or [] if c.get('iso_3166_1') == 'AU'
          for r in c.get('release_dates') or []]
    by_type = {}
    for r in au:
        x = day(r.get('release_date'))
        if x:
            by_type.setdefault(r.get('type'), []).append(x)
    in_win = lambda xs: sorted(x for x in xs if start <= x <= end)
    primary = day(d.get('release_date'))
    digital = in_win(by_type.get(4, []))
    cinema = in_win(by_type.get(3, []) + by_type.get(2, []))
    if codes:
        when = digital[0] if digital else primary if primary and start <= primary <= end else None
        what = 'streaming'
    elif digital:
        when, what = digital[0], 'digital'
    elif cinema:
        when, what = cinema[0], 'cinema'
    else:
        return None
    if not when:
        return None
    return {'kind': 'movie', 'tmdb': d['id'], 'imdb': (d.get('external_ids') or {}).get('imdb_id') or d.get('imdb_id') or '',
            'title': d.get('title') or d.get('original_title') or '', 'date': when.isoformat(), 'what': what,
            'services': codes, 'link': link, 'genres': [g['name'] for g in d.get('genres') or []][:3] or genres,
            'overview': d.get('overview') or '', 'poster': IMG + d['poster_path'] if d.get('poster_path') else '',
            'lang': d.get('original_language') or '', 'pop': round(d.get('popularity') or 0, 1),
            'year': (primary or when).year}


def tv_item(d, by_pid, start, end, today):
    codes, link = au_services(d, by_pid)
    first = day(d.get('first_air_date'))
    nxt, last = d.get('next_episode_to_air') or {}, d.get('last_episode_to_air') or {}
    season = None
    if first and start <= first <= end:
        when, what, season = first, 'premiere', 1
    elif nxt.get('episode_number') == 1 and day(nxt.get('air_date')) and start <= day(nxt['air_date']) <= end:
        when, what, season = day(nxt['air_date']), 'season', nxt.get('season_number')
    elif last.get('episode_number') == 1 and day(last.get('air_date')) and start <= day(last['air_date']) <= today:
        when, what, season = day(last['air_date']), 'season', last.get('season_number')
    else:
        return None
    nets = [n.get('name') for n in d.get('networks') or [] if n.get('name')]
    return {'kind': 'tv', 'tmdb': d['id'], 'imdb': (d.get('external_ids') or {}).get('imdb_id') or '',
            'title': d.get('name') or d.get('original_name') or '', 'date': when.isoformat(), 'what': what,
            'season': season, 'services': codes, 'link': link, 'network': nets[0] if nets else '',
            'genres': [g['name'] for g in d.get('genres') or []][:3], 'overview': d.get('overview') or '',
            'poster': IMG + d['poster_path'] if d.get('poster_path') else '', 'lang': d.get('original_language') or '',
            'pop': round(d.get('popularity') or 0, 1), 'year': first.year if first else when.year}


def fetch(api, days, workers=8):
    today = dt.date.today()
    start, end = today - dt.timedelta(days=BACK_DAYS), today + dt.timedelta(days=days)
    pids = tm.provider_ids(api)
    by_pid = {pid: c for c, ids in pids.items() for pid in ids}
    allp = '|'.join(str(p) for ids in pids.values() for p in ids)
    s, e = start.isoformat(), end.isoformat()
    base = dict(language='en-AU', include_adult='false', sort_by='popularity.desc')
    movies, shows = {}, {}
    for r in pages(api, '/discover/movie', dict(base, watch_region='AU', with_watch_providers=allp, with_watch_monetization_types='flatrate', **{'primary_release_date.gte': s, 'primary_release_date.lte': e}), 5):
        movies[r['id']] = r
    for r in pages(api, '/discover/movie', dict(base, region='AU', with_release_type='4', **{'release_date.gte': s, 'release_date.lte': e}), 5):
        movies[r['id']] = r
    for r in pages(api, '/discover/movie', dict(base, region='AU', with_release_type='2|3', **{'release_date.gte': s, 'release_date.lte': e}), 3):
        movies[r['id']] = r
    for r in pages(api, '/discover/tv', dict(base, watch_region='AU', with_watch_providers=allp, with_watch_monetization_types='flatrate', without_genres=TV_SKIP_GENRES, **{'air_date.gte': s, 'air_date.lte': e}), 10):
        shows[r['id']] = r
    for r in pages(api, '/discover/tv', dict(base, without_genres=TV_SKIP_GENRES, **{'first_air_date.gte': s, 'first_air_date.lte': e}), 3):
        shows[r['id']] = r

    def one(job):
        kind, tid = job
        if kind == 'movie':
            d = api.get(f'/movie/{tid}', language='en-AU', append_to_response='release_dates,external_ids,watch/providers')
            return d and not is_indian(d) and movie_item(d, by_pid, start, end, [])
        d = api.get(f'/tv/{tid}', language='en-AU', append_to_response='external_ids,watch/providers')
        return d and not is_indian(d) and tv_item(d, by_pid, start, end, today)

    jobs = [('movie', i) for i in movies] + [('tv', i) for i in shows]
    with cf.ThreadPoolExecutor(workers) as ex:
        items = [x for x in ex.map(one, jobs) if x]
    items = [x for x in items if x['title'] and (x['poster'] or x['overview'])]
    return {'fetchedAtUnix': int(time.time()), 'services': {c: tm.SERVICES[c][0] for c in pids},
            'from': s, 'to': e, 'items': items, 'requests': api.count}


def build(data, ratings_path=None, state=None):
    order = list(tm.SERVICES)
    meta = {'state': state or ('ok' if data else 'no-key'),
            'services': [{'id': c, 'name': tm.SERVICES[c][0]} for c in order],
            'fetchedAt': (data or {}).get('fetchedAtUnix'), 'source': 'TMDB', 'sourceUrl': 'https://www.themoviedb.org/'}
    items = list((data or {}).get('items') or [])
    ratings = load_ratings(ratings_path, {x['imdb'] for x in items if x.get('imdb')})
    for x in items:
        if x.get('imdb') in ratings:
            x['score'], x['votes'] = ratings[x['imdb']]
    items.sort(key=lambda x: (x['date'], -x.get('pop', 0)))
    if ratings_path:
        meta['imdbAsOf'] = dt.date.today().isoformat()
    return items, meta


def render(items, meta):
    style = STYLE_FROM.read_text(encoding='utf-8')
    style = style[style.index('<style>'):style.index('</style>') + len('</style>')]
    esc = lambda o: json.dumps(o, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
    page = TEMPLATE.read_text(encoding='utf-8')
    for k in ('@@STYLE@@', '@@DATA@@', '@@META@@'):
        if page.count(k) != 1:
            raise SystemExit(f'{TEMPLATE.name} must contain {k} once')
    return page.replace('@@STYLE@@', style).replace('@@META@@', esc(meta)).replace('@@DATA@@', esc(items))


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--cache', default=str(ROOT / 'cache/coming_soon.json'))
    p.add_argument('--ratings')
    p.add_argument('--out', default=str(ROOT / 'Coming_Soon_Android.html'))
    p.add_argument('--days', type=int, default=180)
    p.add_argument('--offline', action='store_true', help='only rebuild the page from the cache')
    a = p.parse_args()
    cache = pathlib.Path(a.cache)
    old = json.loads(cache.read_text()) if cache.exists() else None
    key, state, data = os.environ.get('TMDB_API_KEY', '').strip(), None, old
    if not a.offline and key:
        try:
            data = fetch(tm.Api(key, os.environ.get('TMDB_API_BASE', 'https://api.themoviedb.org/3')), a.days)
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(data, ensure_ascii=False))
        except Exception as e:  # keep the build going with the last good list
            print('coming-soon: TMDB fetch failed, keeping the cached list:', e)
            state = 'stale' if old else 'error'
    elif not a.offline:
        print('coming-soon: no TMDB_API_KEY set')
    items, meta = build(data, a.ratings, state)
    html = render(items, meta)
    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding='utf-8')
    print(json.dumps({'state': meta['state'], 'titles': len(items), 'requests': (data or {}).get('requests'),
                      'movies': sum(x['kind'] == 'movie' for x in items), 'tv': sum(x['kind'] == 'tv' for x in items),
                      'bytes': len(html.encode())}))


if __name__ == '__main__':
    main()
