#!/usr/bin/env python3
"""Find a poster and a short synopsis for every title on the built Movies and TV pages.

Sources, best first:
  0. TMDB /find by IMDb id (poster + overview), when the TMDB_API_KEY CI variable is set.
  1. Wikidata maps each IMDb id (property P345) to its English Wikipedia article.
  2. Wikipedia gives that article's lead image (usually the poster) and first paragraph.
  3. TV shows still without a poster are looked up on TVmaze by IMDb id.

Answers are kept in a gzipped cache so later refreshes only look up new titles, plus
titles that had nothing last time (after RECHECK_MISSING_DAYS). The repo ships a seed
cache (data/posters_seed.json.gz); CI keeps its own updated copy in cache/ (GitLab CI cache).
Titles with nothing found simply show without a poster or synopsis.

Writes into --out (normally _site/posters):
  index.json      {"v":1,"shards":N,"p":{"tt0111161":"w:en/thumb/8/81/X.jpg/250px-X.jpg", ...}}
                  a value starting "!" has a poster but no synopsis; "" has a synopsis but no poster;
                  titles with neither are left out
                  "t:" = TMDB poster path (https://image.tmdb.org/t/p/<size>/...), "w:" = https://upload.wikimedia.org/wikipedia/,
                  "m:" = https://static.tvmaze.com/uploads/images/
  syn/<n>.json    {"tt0111161":["Synopsis text", "w:The_Shawshank_Redemption"], ...}, n = int(id) % N
                  second item is the source page ("t:" TMDB path, "w:" Wikipedia article, "m:" TVmaze show path)

Images are hotlinked from Wikimedia/TVmaze, not copied. The build never fails because of
these sources: on errors it keeps going with whatever is cached.

Usage: python tools/fetch_posters.py [--cache cache/posters.json.gz] [--out _site/posters]
                                     [--budget-minutes 20]
"""
import argparse
import concurrent.futures as cf
import datetime as dt
import gzip
import html
import os
import threading
import json
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
MOVIE_PAGE, TV_PAGE = 'Australian_Movies_Android.html', 'TV_Shows_Android.html'
SEED = ROOT / 'data/posters_seed.json.gz'
CATALOGUE = re.compile(r'<script id="catalogue" type="application/json">(.*?)</script>', re.S)
TT = re.compile(r'tt\d{5,}')
SHARDS = 512
RECHECK_MISSING_DAYS = 60
SYNOPSIS_CHARS = 600
UA = 'ZacMovieFinder/1.0 (https://zac-movies.zalderman.workers.dev; private personal site)'
WIKIDATA = 'https://query.wikidata.org/sparql'
WIKIPEDIA = 'https://en.wikipedia.org/w/api.php'
TVMAZE = 'https://api.tvmaze.com/lookup/shows?imdb='
TMDB = os.environ.get('TMDB_API_BASE', 'https://api.themoviedb.org/3')  # override only for tests
PREFIX = {'w:': 'https://upload.wikimedia.org/wikipedia/', 'm:': 'https://static.tvmaze.com/uploads/images/'}


def ids_from(page):
    path = ROOT / page
    if not path.exists():
        print(f'Note: {page} not found, skipping', file=sys.stderr)
        return []
    m = CATALOGUE.search(path.read_text())
    out = []
    for rec in json.loads(m.group(1).replace('<\\/', '</')) if m else []:
        for field in ('id', 'imdb'):
            hit = TT.search(str(rec.get(field) or ''))
            if hit:
                out.append(hit.group(0))
                break
    return out


def load(path):
    try:
        with gzip.open(path, 'rt') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        print(f'Warning: {path} unreadable ({e})', file=sys.stderr)
        return {}


def save(path, cache):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    with gzip.open(tmp, 'wt') as f:
        json.dump(cache, f, separators=(',', ':'), ensure_ascii=False, sort_keys=True)
    tmp.replace(path)


def get(url, data=None, tries=5):
    headers = {'User-Agent': UA, 'Accept': 'application/json'}
    if data is not None:
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
        data = urllib.parse.urlencode(data).encode()
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data, headers), timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code in (429, 503, 502, 504, 500):
                time.sleep(min(float(e.headers.get('Retry-After') or 0) or 5 * 2 ** attempt, 120))
                continue
            raise
        except (urllib.error.URLError, TimeoutError, ValueError, ConnectionError):
            time.sleep(3 * 2 ** attempt)
    raise RuntimeError(f'gave up on {url[:80]}')


def short(url):
    if (url or '')[:2] in PREFIX or (url or '').startswith('t:'):
        return url
    url = (url or '').split('?')[0].replace('https://thumb.wikimedia.org/', 'https://upload.wikimedia.org/')
    for code, prefix in PREFIX.items():
        if url.startswith(prefix):
            return code + url[len(prefix):]
    return url if url.startswith('https://') else ''


def first_paragraph(text):
    text = re.sub(r'\s+', ' ', (text or '').split('\n')[0]).strip()
    if len(text) <= SYNOPSIS_CHARS:
        return text
    cut = text[:SYNOPSIS_CHARS]
    end = max(cut.rfind('. '), cut.rfind('." '))
    return cut[:end + 1] if end > 200 else cut.rsplit(' ', 1)[0] + '…'


def wikidata_titles(ids):
    """IMDb id -> English Wikipedia article title."""
    out = {}
    for i in range(0, len(ids), 400):
        batch = ids[i:i + 400]
        q = ('SELECT ?imdb ?name WHERE { VALUES ?imdb { %s } ?item wdt:P345 ?imdb . '
             '?article schema:about ?item ; schema:isPartOf <https://en.wikipedia.org/> ; schema:name ?name . }'
             % ' '.join(f'"{t}"' for t in batch))
        res = get(WIKIDATA, {'query': q, 'format': 'json'})
        for b in (res or {}).get('results', {}).get('bindings', []):
            out.setdefault(b['imdb']['value'], b['name']['value'])
        time.sleep(1)
    return out


def wikipedia_pages(titles):
    """Up to 20 article titles -> {requested title: (thumbnail url, first paragraph, final title)}."""
    res = get(WIKIPEDIA, {'action': 'query', 'format': 'json', 'formatversion': '2', 'redirects': '1',
                          'prop': 'extracts|pageimages', 'exintro': '1', 'explaintext': '1', 'exlimit': '20',
                          'piprop': 'thumbnail', 'pithumbsize': '250', 'pilicense': 'any', 'pilimit': '20',
                          'titles': '|'.join(titles)}) or {}
    query = res.get('query', {})
    back = {t: t for t in titles}
    for step in ('normalized', 'redirects'):
        for n in query.get(step, []):
            for orig, cur in list(back.items()):
                if cur == n['from']:
                    back[orig] = n['to']
    pages = {p['title']: p for p in query.get('pages', []) if not p.get('missing')}
    out = {}
    for orig, final in back.items():
        p = pages.get(final)
        if p:
            out[orig] = (short((p.get('thumbnail') or {}).get('source', '')), first_paragraph(p.get('extract')), final)
    return out


def tvmaze(tt):
    show = get(TVMAZE + tt, tries=4)
    if not show:
        return None
    img = short(((show.get('image') or {}).get('medium')) or '')
    summary = first_paragraph(html.unescape(re.sub(r'<[^>]+>', ' ', show.get('summary') or '')))
    url = show.get('url') or ''
    return img, summary, 'm:' + url.split('tvmaze.com/')[-1] if url else ''


class AuthError(Exception):
    pass


class Limiter:
    def __init__(self, rate):
        self.gap, self.lock, self.next = 1.0 / rate, threading.Lock(), time.monotonic()

    def wait(self):
        with self.lock:
            now = time.monotonic()
            self.next = max(self.next, now) + self.gap
            delay = self.next - self.gap - now
        if delay > 0:
            time.sleep(delay)


def tmdb(tt, key, limiter):
    """IMDb id -> (poster path, overview, source) from TMDB, ('', '', '') if not there, None on error."""
    url = f'{TMDB}/find/{tt}?external_source=imdb_id&language=en-US'
    headers = {'Accept': 'application/json', 'User-Agent': UA}
    if key.startswith('eyJ'):
        headers['Authorization'] = 'Bearer ' + key  # v4 read access token
    else:
        url += '&api_key=' + urllib.parse.quote(key)
    for attempt in range(5):
        limiter.wait()
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20) as r:
                data = json.load(r)
            break
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise AuthError('TMDB rejected the key (HTTP 401)')
            if e.code == 404:
                return ('', '', '')
            if e.code == 429 or e.code >= 500:
                time.sleep(float(e.headers.get('Retry-After') or 2 ** attempt))
                continue
            return None
        except (urllib.error.URLError, TimeoutError, ValueError, ConnectionError):
            time.sleep(2 ** attempt)
    else:
        return None
    for group, kind in (('movie_results', 'movie'), ('tv_results', 'tv')):
        for hit in data.get(group) or []:
            poster, overview = hit.get('poster_path') or '', (hit.get('overview') or '').strip()
            if poster or overview:
                return ('t:' + poster.lstrip('/') if poster else '', first_paragraph(overview),
                        f't:{kind}/{hit.get("id")}')
    return ('', '', '')


def tmdb_pass(ids, cache, key, deadline, today):
    """Fill k/tp/to/tu fields from TMDB for titles not checked yet (or found empty 60+ days ago)."""
    def wanted(t):
        e = cache.get(t) or {}
        if 'k' not in e:
            return True
        return not (e.get('tp') or e.get('to')) and (today - dt.date.fromisoformat(e['k'])).days >= RECHECK_MISSING_DAYS
    todo = [t for t in ids if wanted(t)]
    print(f'  TMDB: {len(todo):,} titles to look up')
    limiter, done = Limiter(35), 0
    with cf.ThreadPoolExecutor(12) as pool:
        it, running = iter(todo), {}

        def top_up():
            while len(running) < 36 and time.monotonic() < deadline:
                t = next(it, None)
                if t is None:
                    return
                running[pool.submit(tmdb, t, key, limiter)] = t
        top_up()
        try:
            while running:
                finished, _ = cf.wait(running, return_when=cf.FIRST_COMPLETED)
                for f in finished:
                    t = running.pop(f)
                    res = f.result()
                    if res is None:
                        continue
                    e = cache.setdefault(t, {})
                    e.update({'tp': res[0], 'to': res[1], 'tu': res[2] if res[1] else '', 'k': today.isoformat()})
                    done += 1
                    if done % 5000 == 0:
                        print(f'  TMDB: {done:,}/{len(todo):,}')
                top_up()
        except AuthError as e:
            print(f'Warning: {e}. Check the TMDB_API_KEY CI variable; using other sources only.', file=sys.stderr)
            for f in running:
                f.cancel()
    found = sum(1 for t in todo if (cache.get(t) or {}).get('tp'))
    print(f'  TMDB: looked up {done:,}, {found:,} with a poster')


def due(entry, today):
    if 't' not in entry:
        return True
    if (entry.get('p') and entry.get('o')) or (entry.get('tp') and entry.get('to')):
        return False
    return (today - dt.date.fromisoformat(entry.get('t', '2000-01-01'))).days >= RECHECK_MISSING_DAYS


def write_outputs(out, ids, cache):
    (out / 'syn').mkdir(parents=True, exist_ok=True)
    posters, shards = {}, [{} for _ in range(SHARDS)]
    for tt in ids:
        c = cache.get(tt) or {}
        e = {'p': c.get('tp') or short(c.get('p')), 'o': c.get('to') or c.get('o', ''),
             'u': c.get('tu') if c.get('to') else c.get('u', '')}
        if e.get('p') or e.get('o'):
            posters[tt] = ('' if e.get('o') else '!') + e.get('p', '')
        if e.get('o'):
            shards[int(tt[2:]) % SHARDS][tt] = [e['o'], e.get('u', '')]
    (out / 'index.json').write_text(json.dumps({'v': 1, 'shards': SHARDS, 'p': posters}, separators=(',', ':')))
    for i, shard in enumerate(shards):
        (out / 'syn' / f'{i}.json').write_text(json.dumps(shard, separators=(',', ':'), ensure_ascii=False))
    print(f'Posters: {sum(1 for v in posters.values() if v.strip("!")):,} posters ({sum(1 for v in posters.values() if v.startswith(("t:", "!t:"))):,} from TMDB) and {sum(map(len, shards)):,} synopses for {len(ids):,} titles')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cache', default=str(ROOT / 'cache/posters.json.gz'))
    ap.add_argument('--out', default=str(ROOT / '_site/posters'))
    ap.add_argument('--budget-minutes', type=float, default=20)
    ap.add_argument('--movies', default=MOVIE_PAGE)
    ap.add_argument('--tv', default=TV_PAGE)
    ap.add_argument('--offline', action='store_true', help='no lookups, only write outputs from the cache')
    a = ap.parse_args()

    movie_ids, tv_ids = ids_from(a.movies), ids_from(a.tv)
    ids = list(dict.fromkeys(movie_ids + tv_ids))
    cache_path, out = pathlib.Path(a.cache), pathlib.Path(a.out)
    cache = load(SEED)
    cache.update(load(cache_path))
    today = dt.date.today()
    deadline = time.monotonic() + a.budget_minutes * 60
    key = os.environ.get('TMDB_API_KEY', '').strip()
    print(f'Posters: {len(ids):,} titles, {len(cache):,} cached')
    if key and not a.offline:
        try:
            tmdb_pass(ids, cache, key, deadline - a.budget_minutes * 60 * 0.4, today)  # leave time for the fallbacks
        except Exception as e:
            print(f'Warning: TMDB lookup stopped early ({e})', file=sys.stderr)
        save(cache_path, cache)
    # Wikipedia/TVmaze only for titles TMDB didn't fully cover
    todo = [t for t in ids if not ((cache.get(t) or {}).get('tp') and (cache.get(t) or {}).get('to'))
            and (t not in cache or due(cache[t], today))]
    print(f'  Fallback sources: {len(todo):,} titles to look up')

    def remember(tt, poster, text, source):
        old = cache.get(tt) or {}
        cache[tt] = {k: v for k, v in old.items() if k in ('k', 'tp', 'to', 'tu')}
        cache[tt] |= {'p': poster or old.get('p', ''), 'o': text or old.get('o', ''),
                     'u': source if text else old.get('u', ''), 't': today.isoformat()}

    if todo and not a.offline:
        try:
            titles = wikidata_titles(todo)
            print(f'  Wikidata: {len(titles):,} of {len(todo):,} have an English Wikipedia article')
            by_title = {}
            for tt, title in titles.items():
                by_title.setdefault(title, []).append(tt)
            names = list(by_title)
            batches = [names[i:i + 20] for i in range(0, len(names), 20)]
            with cf.ThreadPoolExecutor(3) as pool:
                futures = {}
                for b in batches:
                    futures[pool.submit(lambda b=b: None if time.monotonic() > deadline else wikipedia_pages(b))] = b
                for n, f in enumerate(cf.as_completed(futures), 1):
                    try:
                        found = f.result()
                    except Exception as e:  # one bad batch must not stop the rest
                        print(f'  Wikipedia batch failed: {e}', file=sys.stderr)
                        continue
                    if found is None:
                        continue
                    for name in futures[f]:
                        poster, text, final = found.get(name, ('', '', name))
                        for tt in by_title[name]:
                            remember(tt, poster, text, 'w:' + final.replace(' ', '_'))
                    if n % 200 == 0:
                        print(f'  Wikipedia: {n:,}/{len(batches):,} batches')
                        save(cache_path, cache)
            for tt in todo:  # nothing on Wikipedia: note the check so it waits before retrying
                if tt not in titles:
                    remember(tt, '', '', '')
            tv_set = set(tv_ids)
            def has(t, f):
                e = cache.get(t) or {}
                return e.get('t' + f) or e.get(f)
            need_tv = [t for t in todo if t in tv_set and not (has(t, 'p') and has(t, 'o'))]
            got = 0
            for tt in need_tv:
                if time.monotonic() > deadline:
                    break
                res = tvmaze(tt)
                time.sleep(0.55)  # TVmaze allows about 20 calls per 10 seconds
                if res:
                    remember(tt, *res)
                    got += 1
            print(f'  TVmaze: filled {got:,} of {len(need_tv):,} TV shows')
        except Exception as e:
            print(f'Warning: poster lookup stopped early ({e}); using what was found', file=sys.stderr)
        if time.monotonic() > deadline:
            print('  Time budget used up; the rest will be looked up on the next refresh')
        save(cache_path, cache)
    write_outputs(out, ids, cache)


if __name__ == '__main__':
    main()
