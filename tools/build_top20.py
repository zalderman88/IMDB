#!/usr/bin/env python3
"""Build the Top 20 page (top20.html): what is popular on Australian streaming services right now.

It combines only official, published data and documented APIs (no scraping):

1. Netflix's own Top 10 for Australia (the weekly TSV file Netflix publishes for download at
   netflix.com/tudum/top10). No key needed.
2. The services' own top lists for Australia through the Streaming Availability API
   (GET /shows/top, country=au): Netflix, Prime Video, Disney+, Apple TV+, Paramount+ and
   HBO Max where the API has them. Needs the API key (env var below); skipped without it.
3. TMDB popularity for titles TMDB lists as streaming on each Australian subscription service
   that has no official chart (Stan, Binge, Foxtel Now, BritBox, ABC iview, SBS On Demand ...).
   Optional: only with a TMDB_API_KEY. Uses TMDB's watch-provider data (from JustWatch).
4. IMDb ratings and votes from IMDb's official datasets (title.basics + title.ratings), which
   are also used to identify Netflix chart titles. Optional locally, always present in CI.

Scoring (shown on the page too):
  * Each chart gives 10 points to its #1 down to 1 point for #10 (scaled for other lengths).
  * A service counts once per title: the best of its charts. Netflix adds a quarter of the points
    of the previous week's official chart, so staying power counts a little.
  * TMDB popularity lists count at 60%, because they are worldwide interest in titles that
    are on that AU service, not an AU viewing chart.
  * Points from different services add up, so a hit on two services ranks higher.
  * Quality bonus: up to 4.5 points from the IMDb rating (needs 1,000+ votes): (rating - 6) x 1.5.
    Without an IMDb rating, the Streaming Availability rating (0-100, average of online
    ratings) is used the same way.
  India is excluded, as on the other pages (research/imdb/india_titles.json).

The build never fails the pipeline because a chart source is down: it records which sources
worked and the page says so.

Usage: python tools/build_top20.py [--basics title.basics.tsv.gz --ratings title.ratings.tsv.gz]
       [--netflix-tsv all-weeks-countries.tsv] [--sa-fixture dir] [--tmdb-fixture dir]
       [--out Top20_Android.html] [--json top20.json]
"""
import argparse
import csv
import datetime
import gzip
import io
import json
import os
import pathlib
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / 'research/top20_template.html'
INDIA = ROOT / 'research/imdb/india_titles.json'
NETFLIX_TSV = 'https://www.netflix.com/tudum/top10/data/all-weeks-countries.tsv'
UA = 'movie-finder-top20/1.0 (private, fortnightly)'
SA_SERVICES = ['netflix', 'prime', 'disney', 'apple', 'paramount', 'hbo']
NAMES = {'netflix': 'Netflix', 'prime': 'Prime Video', 'disney': 'Disney+', 'apple': 'Apple TV+',
         'paramount': 'Paramount+', 'hbo': 'HBO Max', 'stan': 'Stan', 'binge': 'Binge',
         'foxtel': 'Foxtel Now', 'britbox': 'BritBox', 'iview': 'ABC iview', 'sbs': 'SBS On Demand',
         'shudder': 'Shudder', 'docplay': 'DocPlay', 'crunchyroll': 'Crunchyroll'}
# TMDB AU provider names -> our service id. Services with an official chart above are not
# repeated here, so TMDB only fills the gaps.
TMDB_PROVIDERS = {'Stan': 'stan', 'Binge': 'binge', 'Foxtel Now': 'foxtel', 'BritBox': 'britbox',
                  'ABC iview': 'iview', 'SBS On Demand': 'sbs', 'Shudder': 'shudder', 'DocPlay': 'docplay'}
TMDB_WEIGHT = 0.6
MIN_VOTES = 1000
csv.field_size_limit(sys.maxsize)


def log(*a):
    print(*a, file=sys.stderr)


def norm(title):
    t = unicodedata.normalize('NFKD', title or '').encode('ascii', 'ignore').decode().lower()
    t = t.replace('&', ' and ')
    t = re.sub(r'[^a-z0-9]+', ' ', t).strip()
    return re.sub(r'^the ', '', t)


def points(rank, length):
    length = max(length, 1)
    return round(10 * (length + 1 - rank) / length, 3)


def get_json(url, headers, retries=3):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA, **headers})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403, 404):
                raise
            if e.code == 429 or attempt + 1 < retries:
                time.sleep(5 * (attempt + 1))
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            if attempt + 1 == retries:
                raise
            time.sleep(5 * (attempt + 1))


# ---------- source 1: Netflix official Top 10 ----------

def netflix_charts(path):
    if path:
        text = pathlib.Path(path).read_text(encoding='utf-8')
    else:
        for attempt in range(4):
            try:
                req = urllib.request.Request(NETFLIX_TSV, headers={'User-Agent': UA})
                with urllib.request.urlopen(req, timeout=180) as r:
                    text = r.read().decode('utf-8')
                break
            except Exception:  # noqa: BLE001 - large file; retry cut-off downloads
                if attempt == 3:
                    raise
                time.sleep(10 * (attempt + 1))
    rows = [r for r in csv.DictReader(io.StringIO(text), delimiter='\t', quoting=csv.QUOTE_NONE)
            if r.get('country_iso2') == 'AU']
    weeks = sorted({r['week'] for r in rows}, reverse=True)
    if not weeks:
        raise ValueError('no Australian rows in the Netflix file')
    out = {}
    for label, week in (('this', weeks[0]), ('last', weeks[1] if len(weeks) > 1 else None)):
        for kind, cat in (('movie', 'Films'), ('series', 'TV')):
            lst = sorted((r for r in rows if r['week'] == week and r['category'] == cat),
                         key=lambda r: int(r['weekly_rank']))
            out[(label, kind)] = [{'title': r['show_title'], 'rank': int(r['weekly_rank']),
                                   'weeks': int(r['cumulative_weeks_in_top_10'] or 0)} for r in lst]
    return weeks[0], out


# ---------- source 2: Streaming Availability API (official service top lists) ----------

def sa_config():
    """Same key variables as tools/fetch_new_streaming.py (one shared key for both pages)."""
    key = os.environ.get('STREAMING_AVAILABILITY_API_KEY', '').strip()
    if key:
        return os.environ.get('STREAMING_API_BASE', 'https://api.movieofthenight.com/v4'), {'X-API-Key': key}
    key = os.environ.get('RAPIDAPI_KEY', '').strip()
    if key:
        return 'https://streaming-availability.p.rapidapi.com', {
            'X-RapidAPI-Key': key, 'X-RapidAPI-Host': 'streaming-availability.p.rapidapi.com'}
    return None


def sa_charts(fixture_dir, cache, force, max_age_days):
    """Official top lists. About 12 requests; cached so ordinary code pushes spend none."""
    notes = []
    if fixture_dir:
        charts = {}
        for f in pathlib.Path(fixture_dir).glob('*.json'):
            svc, kind = f.stem.rsplit('-', 1)
            charts[(svc, kind)] = json.loads(f.read_text())
        return charts, notes, None
    cached = None
    if cache and cache.exists():
        try:
            cached = json.loads(cache.read_text())
        except ValueError:
            cached = None
    if cached and not force and (time.time() - cached['fetchedAtUnix']) / 86400 < max_age_days:
        return ({tuple(k.rsplit('-', 1)): v for k, v in cached['charts'].items()},
                ['Streaming Availability: reused cached charts'], cached['fetchedAtUnix'])
    cfg = sa_config()
    if not cfg:
        return {}, ['Streaming Availability key not set'], None
    base, headers = cfg
    charts = {}
    for svc in SA_SERVICES:
        for kind in ('movie', 'series'):
            try:
                q = urllib.parse.urlencode({'country': 'au', 'service': svc, 'show_type': kind})
                data = get_json(f'{base}/shows/top?{q}', headers)
                time.sleep(1.2)
            except Exception as e:  # noqa: BLE001 - one service failing must not stop the rest
                notes.append(f'{NAMES[svc]} {kind}: {type(e).__name__} {getattr(e, "code", "")}'.strip())
                continue
            if isinstance(data, list) and data:
                charts[(svc, kind)] = data
    if charts and cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({'fetchedAtUnix': int(time.time()),
                                     'charts': {f'{s}-{k}': v for (s, k), v in charts.items()}}))
        return charts, notes, int(time.time())
    if not charts and cached:  # API down: fall back to the last good charts
        return ({tuple(k.rsplit('-', 1)): v for k, v in cached['charts'].items()},
                notes + ['Streaming Availability: using the last saved charts'], cached['fetchedAtUnix'])
    return charts, notes, None


def sa_where(show):
    """Subscription links in Australia from a Streaming Availability show object."""
    out = {}
    for opt in (show.get('streamingOptions') or {}).get('au', []) or []:
        svc = (opt.get('service') or {}).get('id')
        if svc and opt.get('type') in ('subscription', 'addon', 'free') and svc not in out:
            out[svc] = opt.get('link') or ''
    return out


# ---------- source 3: TMDB popularity on AU services with no chart (optional) ----------

def tmdb_lists(fixture_dir):
    key = os.environ.get('TMDB_API_KEY', '').strip()
    if not fixture_dir and not key:
        return {}, ['TMDB key not set (optional)']
    lists, notes = {}, []

    def call(path, **params):
        if fixture_dir:
            name = path.strip('/').replace('/', '-') + ('-' + params['with_watch_providers'] if 'with_watch_providers' in params else '')
            f = pathlib.Path(fixture_dir) / f'{name}.json'
            return json.loads(f.read_text()) if f.exists() else {}
        headers = {'Accept': 'application/json'}
        if key.startswith('ey'):  # v4 read access token
            headers['Authorization'] = f'Bearer {key}'
        else:
            params['api_key'] = key
        time.sleep(0.15)
        return get_json(f'https://api.themoviedb.org/3{path}?{urllib.parse.urlencode(params)}', headers)

    try:
        for kind, tk in (('movie', 'movie'), ('series', 'tv')):
            provs = call(f'/watch/providers/{tk}', watch_region='AU').get('results', [])
            ids = {p['provider_name']: p['provider_id'] for p in provs}
            for name, svc in TMDB_PROVIDERS.items():
                if name not in ids:
                    continue
                res = call(f'/discover/{tk}', watch_region='AU', with_watch_providers=str(ids[name]),
                           with_watch_monetization_types='flatrate', sort_by='popularity.desc',
                           include_adult='false', **{'vote_count.gte': '50'}).get('results', [])[:10]
                items = []
                for r in res:
                    ext = call(f'/{tk}/{r["id"]}/external_ids')
                    items.append({'tmdb': f'{tk}/{r["id"]}', 'imdb': ext.get('imdb_id') or None,
                                  'title': r.get('title') or r.get('name'),
                                  'year': int((r.get('release_date') or r.get('first_air_date') or '0')[:4] or 0) or None,
                                  'lang': r.get('original_language'), 'countries': r.get('origin_country') or []})
                if items:
                    lists[(svc, kind)] = items
    except Exception as e:  # noqa: BLE001
        notes.append(f'TMDB: {type(e).__name__} {getattr(e, "code", "")}'.strip())
    return lists, notes


# ---------- source 4: IMDb datasets ----------

def imdb_index(basics, ratings, wanted_titles, wanted_ids):
    """Ratings for wanted ids, and title -> candidate ids for Netflix chart titles."""
    if not basics or not ratings:
        return {}, {}
    rating = {}
    with gzip.open(ratings, 'rt', encoding='utf-8', newline='') as f:
        for r in csv.DictReader(f, delimiter='\t', quoting=csv.QUOTE_NONE):
            rating[r['tconst']] = (float(r['averageRating']), int(r['numVotes']))
    info, by_title = {}, {}
    types = {'movie': {'movie', 'tvMovie'}, 'series': {'tvSeries', 'tvMiniSeries'}}
    with gzip.open(basics, 'rt', encoding='utf-8', newline='') as f:
        for r in csv.DictReader(f, delimiter='\t', quoting=csv.QUOTE_NONE):
            tt, ttype = r['tconst'], r['titleType']
            kind = 'movie' if ttype in types['movie'] else 'series' if ttype in types['series'] else None
            if kind is None:
                continue
            hit = tt in wanted_ids
            keys = {(kind, norm(r['primaryTitle'])), (kind, norm(r['originalTitle']))}
            matched = [k for k in keys if k in wanted_titles]
            if not hit and not matched:
                continue
            score, votes = rating.get(tt, (None, 0))
            year = int(r['startYear']) if r['startYear'].isdigit() else None
            info[tt] = {'title': r['primaryTitle'], 'year': year, 'score': score, 'votes': votes,
                        'genres': [g for g in r['genres'].split(',') if g != '\\N'], 'type': ttype}
            for k in matched:
                by_title.setdefault(k, []).append(tt)
    return info, by_title


def pick_imdb(cands, info, this_year):
    good = [c for c in cands if info[c]['votes'] >= 200]
    if not good:
        return None
    recent = [c for c in good if (info[c]['year'] or 0) >= this_year - 2]
    return max(recent or good, key=lambda c: info[c]['votes'])


# ---------- combine ----------

def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--basics')
    p.add_argument('--ratings')
    p.add_argument('--netflix-tsv', help='local copy of all-weeks-countries.tsv (default: download)')
    p.add_argument('--sa-fixture', help='directory of saved /shows/top responses (testing)')
    p.add_argument('--tmdb-fixture', help='directory of saved TMDB responses (testing)')
    p.add_argument('--today', help='YYYY-MM-DD (testing)')
    p.add_argument('--cache-dir', default=str(ROOT / 'cache'), help='where API results are kept between pipelines')
    p.add_argument('--force', action='store_true', help='call the APIs even if the cache is fresh')
    p.add_argument('--max-age-days', type=float, default=13)
    p.add_argument('--out', default=str(ROOT / 'Top20_Android.html'))
    p.add_argument('--json', default=str(ROOT / 'top20.json'))
    a = p.parse_args()
    today = datetime.date.fromisoformat(a.today) if a.today else datetime.date.today()

    sources, notes = {}, []
    try:
        nf_week, nf = netflix_charts(a.netflix_tsv)
        sources['netflix_official'] = {'ok': True, 'week': nf_week}
    except Exception as e:  # noqa: BLE001
        nf_week, nf = None, {}
        sources['netflix_official'] = {'ok': False}
        notes.append(f'Netflix Top 10 file: {type(e).__name__}')
    sa, sa_notes, sa_at = sa_charts(a.sa_fixture, pathlib.Path(a.cache_dir) / 'top20_sa.json' if a.cache_dir else None,
                                    a.force, a.max_age_days)
    notes += sa_notes
    sources['streaming_availability'] = {'ok': bool(sa), 'lists': sorted(f'{s}-{k}' for s, k in sa),
                                         'fetched': datetime.date.fromtimestamp(sa_at).isoformat() if sa_at else None}
    tm, tm_notes = tmdb_lists(a.tmdb_fixture)
    notes += tm_notes
    sources['tmdb'] = {'ok': bool(tm), 'lists': sorted(f'{s}-{k}' for s, k in tm)}

    # Netflix chart titles are matched to IMDb ids: first via the API's Netflix list, then IMDb.
    sa_by_title = {}
    for (svc, kind), lst in sa.items():
        for show in lst:
            sa_by_title.setdefault((kind, norm(show.get('title'))), show)
    wanted_titles = {(kind, norm(e['title'])) for (_, kind), lst in nf.items() for e in lst}
    wanted_ids = {s.get('imdbId') for lst in sa.values() for s in lst} | {i['imdb'] for lst in tm.values() for i in lst}
    wanted_ids.discard(None)
    info, by_title = imdb_index(a.basics, a.ratings, wanted_titles, wanted_ids)
    sources['imdb'] = {'ok': bool(info)}

    india = set()
    if INDIA.exists():
        d = json.loads(INDIA.read_text())
        india = set(d.get('wikidata', [])) | set(d.get('akas', []))

    items = {}

    def item(kind, imdb, title, year=None):
        k = imdb or f'{kind}:{norm(title)}'
        it = items.setdefault(k, {'kind': kind, 'imdb': imdb, 'title': title, 'year': year, 'svc': {},
                                  'charts': [], 'where': {}, 'sa': None})
        if year and not it['year']:
            it['year'] = year
        return it

    def credit(it, svc, pts, label):
        it['svc'][svc] = max(it['svc'].get(svc, 0), pts)
        it['charts'].append(label)

    for (svc, kind), lst in sa.items():
        for rank, show in enumerate(lst, 1):
            it = item(kind, show.get('imdbId'), show.get('title'), show.get('releaseYear') or show.get('firstAirYear'))
            credit(it, svc, points(rank, len(lst)), {'svc': svc, 'rank': rank, 'src': 'official'})
            if isinstance(show.get('rating'), int):
                it['sa'] = show['rating']
            for wsvc, link in sa_where(show).items():
                it['where'].setdefault(wsvc, link)
            it['where'].setdefault(svc, '')

    for label in ('this', 'last'):
        for kind in ('movie', 'series'):
            lst = nf.get((label, kind), [])
            for e in lst:
                key = (kind, norm(e['title']))
                imdb = (sa_by_title.get(key) or {}).get('imdbId') or pick_imdb(by_title.get(key, []), info, today.year)
                it = item(kind, imdb, e['title'])
                pts = points(e['rank'], len(lst))
                if label == 'this':
                    credit(it, 'netflix', pts, {'svc': 'netflix', 'rank': e['rank'], 'src': 'netflix', 'weeks': e['weeks']})
                    it['where'].setdefault('netflix', '')
                else:
                    it['bonus_last'] = round(pts * 0.25, 3)
                    it['last_rank'] = e['rank']

    for (svc, kind), lst in tm.items():
        for rank, e in enumerate(lst, 1):
            if e['lang'] in ('hi', 'ta', 'te', 'ml', 'kn', 'bn', 'mr', 'pa') or 'IN' in e['countries']:
                continue
            it = item(kind, e['imdb'], e['title'], e['year'])
            credit(it, svc, round(points(rank, len(lst)) * TMDB_WEIGHT, 3), {'svc': svc, 'rank': rank, 'src': 'tmdb'})
            it['where'].setdefault(svc, '')

    out = {'movie': [], 'series': []}
    for it in items.values():
        if it['imdb'] in india:
            continue
        if not it['svc']:  # only on last week's Netflix chart
            continue
        meta = info.get(it['imdb']) or {}
        if meta:
            it['title'] = it['title'] or meta['title']
            it['year'] = it['year'] or meta['year']
        chart = sum(it['svc'].values()) + (it.get('bonus_last', 0) if 'netflix' in it['svc'] else 0)
        q, qsrc = None, None
        if meta.get('score') is not None and meta.get('votes', 0) >= MIN_VOTES:
            q, qsrc = meta['score'], 'imdb'
        elif it['sa'] is not None:
            q, qsrc = it['sa'] / 10, 'sa'
        bonus = round(min(max((q - 6.0) * 1.5, 0), 4.5), 2) if q is not None else 0
        best = {}
        for c in sorted(it['charts'], key=lambda c: (c['rank'], c['src'] != 'netflix')):
            best.setdefault(c['svc'], c)  # one chip per service: its best rank
        charts = sorted(best.values(), key=lambda c: (c['src'] == 'tmdb', c['rank']))
        out[it['kind']].append({
            'title': it['title'], 'year': it['year'], 'imdb': it['imdb'],
            'imdbScore': meta.get('score'), 'imdbVotes': meta.get('votes'), 'saRating': it['sa'],
            'genres': meta.get('genres', [])[:3], 'charts': charts, 'lastRank': it.get('last_rank'),
            'where': [{'svc': s, 'name': NAMES.get(s, s.title()), 'link': l if l.startswith('https://') else ''}
                      for s, l in it['where'].items() if s in NAMES],
            'chartPts': round(chart, 2), 'bonus': bonus, 'bonusFrom': qsrc,
            'total': round(chart + bonus, 2)})
    for kind in out:
        out[kind].sort(key=lambda x: (-x['total'], -x['chartPts'], x['title'] or ''))
        out[kind] = out[kind][:20]
        for i, x in enumerate(out[kind], 1):
            x['rank'] = i

    payload = {'built': today.isoformat(), 'netflixWeek': nf_week, 'sources': sources, 'notes': notes,
               'names': NAMES, 'movies': out['movie'], 'shows': out['series']}
    pathlib.Path(a.json).write_text(json.dumps(payload, ensure_ascii=False, indent=1))
    data = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
    html = TEMPLATE.read_text().replace('@@DATA@@', data)
    pathlib.Path(a.out).write_text(html)
    print(json.dumps({'movies': len(out['movie']), 'shows': len(out['series']), 'sources': sources,
                      'notes': notes}, ensure_ascii=False))


if __name__ == '__main__':
    main()
