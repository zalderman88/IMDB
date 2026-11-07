#!/usr/bin/env python3
"""Offline test of the New on streaming fetch + build, against a local fake API.

Run: python tests/test_new_streaming.py
"""
import gzip
import http.server
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent.parent
NOW = int(time.time())

COUNTRY = {'countryCode': 'au', 'name': 'Australia', 'services': [
    {'id': 'netflix', 'name': 'Netflix', 'homePage': 'https://www.netflix.com/', 'themeColorCode': '#E50914',
     'streamingOptionTypes': {'addon': False, 'buy': False, 'rent': False, 'free': False, 'subscription': True}},
    {'id': 'stan', 'name': 'Stan', 'homePage': 'https://www.stan.com.au/', 'themeColorCode': '#0072FB',
     'streamingOptionTypes': {'addon': False, 'buy': False, 'rent': False, 'free': False, 'subscription': True}},
    {'id': 'apple', 'name': 'Apple TV', 'homePage': 'https://tv.apple.com/', 'themeColorCode': '#000000',
     'streamingOptionTypes': {'addon': False, 'buy': True, 'rent': True, 'free': False, 'subscription': False}},
]}


def show(i, kind):
    return {'itemType': 'show', 'showType': kind, 'id': str(i), 'imdbId': f'tt{1000000 + i}', 'tmdbId': f'movie/{i}',
            'title': f'Title {i}', 'overview': f'Overview {i}.', 'releaseYear': 2025, 'firstAirYear': 2024,
            'lastAirYear': 2026, 'seasonCount': 2, 'genres': [{'id': 'drama', 'name': 'Drama'}],
            'cast': ['A', 'B'], 'rating': 70,
            'imageSet': {'verticalPoster': {'w240': f'https://cdn.example/{i}.jpg'}}}


def change(i, svc, kind, item='show', season=None, opt='subscription'):
    c = {'changeType': 'new', 'itemType': item, 'showId': str(i), 'showType': kind,
         'service': {'id': svc, 'name': svc}, 'streamingOptionType': opt, 'timestamp': NOW - i * 3600,
         'link': f'https://{svc}.example/{i}'}
    if season:
        c['season'] = season
    return c


PAGES = {
    ('show', None): {'changes': [change(1, 'netflix', 'movie'), change(2, 'stan', 'series'),
                                 change(1, 'stan', 'movie'), change(9, 'netflix', 'movie', opt='free')],
                     'shows': {'1': show(1, 'movie'), '2': show(2, 'series'), '9': show(9, 'movie')},
                     'hasMore': True, 'nextCursor': 'p2?&x'},
    ('show', 'p2?&x'): {'changes': [change(3, 'netflix', 'movie')], 'shows': {'3': show(3, 'movie')}, 'hasMore': False},
    ('season', None): {'changes': [change(4, 'netflix', 'series', 'season', 3)], 'shows': {'4': show(4, 'series')},
                       'hasMore': False},
}
SEEN = []


class Fake(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = dict(urllib.parse.parse_qsl(u.query))
        SEEN.append((u.path, q))
        if self.headers.get('X-API-Key') != 'test-key':
            self.send_response(401); self.end_headers(); return
        if u.path == '/v4/countries/au':
            body = COUNTRY
        elif u.path == '/v4/changes':
            assert q['country'] == 'au' and q['change_type'] == 'new', q
            assert q['catalogs'] == 'netflix.subscription,stan.subscription', q['catalogs']
            assert NOW - int(q['from']) <= 31 * 86400, 'from must be inside 31 days'
            body = PAGES[(q['item_type'], q.get('cursor'))]
        else:
            self.send_response(404); self.end_headers(); return
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(data)


def run(args, env):
    r = subprocess.run([sys.executable, *args], cwd=ROOT, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout + r.stderr


def main():
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{srv.server_address[1]}/v4'
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        env = {k: v for k, v in os.environ.items() if k not in ('STREAMING_AVAILABILITY_API_KEY', 'RAPIDAPI_KEY', 'TMDB_API_KEY')}
        env['NO_PROXY'] = env['no_proxy'] = '127.0.0.1'
        cache, page = tmp / 'new.json', tmp / 'new.html'

        # 1. No key: skip quietly, page says not set up.
        out = run(['tools/fetch_new_streaming.py', '--out', str(cache)], env)
        assert 'no STREAMING_AVAILABILITY_API_KEY' in out and not cache.exists()
        run(['tools/build_new_streaming.py', '--data', str(cache), '--tmdb', str(tmp / 'no-tmdb.json'), '--out', str(page)], env)
        assert '"state":"no-key"' in page.read_text()

        # 2. With key: fetch both item types, follow the cursor, keep subscription only.
        env.update(STREAMING_AVAILABILITY_API_KEY='test-key', STREAMING_API_BASE=base)
        run(['tools/fetch_new_streaming.py', '--out', str(cache)], env)
        d = json.loads(cache.read_text())
        assert d['requests'] == 4, d['requests']
        assert [s['id'] for s in d['services']] == ['netflix', 'stan']
        assert sorted(d['shows']) == ['1', '2', '3', '4'], sorted(d['shows'])  # '9' was free-only
        assert len(d['changes']) == 5

        # 3. Fresh cache: no requests unless --force.
        n = len(SEEN)
        out = run(['tools/fetch_new_streaming.py', '--out', str(cache)], env)
        assert 'not fetching' in out and len(SEEN) == n
        run(['tools/fetch_new_streaming.py', '--out', str(cache), '--force', '--max-pages', '1'], env)
        assert json.loads(cache.read_text())['truncated'] == ['show', 'season']

        # 4. Bad key: keep the old cache.
        before = cache.read_text()
        env['STREAMING_AVAILABILITY_API_KEY'] = 'wrong'
        out = run(['tools/fetch_new_streaming.py', '--out', str(cache), '--force'], env)
        assert 'HTTP 401' in out and cache.read_text() == before

        # 5. Build with IMDb ratings.
        cache.write_text(json.dumps(d))
        ratings = tmp / 'r.tsv.gz'
        with gzip.open(ratings, 'wt') as f:
            f.write('tconst\taverageRating\tnumVotes\ntt1000001\t7.8\t12345\ntt1000003\t6.1\t900\n')
        out = run(['tools/build_new_streaming.py', '--data', str(cache), '--tmdb', str(tmp / 'no-tmdb.json'), '--ratings', str(ratings), '--out', str(page)], env)
        html = page.read_text()
        rows = json.loads(html.split('<script id="catalogue" type="application/json">')[1].split('</script>')[0])
        by = {r[0]: r for r in rows}
        assert by['Title 1'][9:11] == [7.8, 12345] and len(by['Title 1'][11]) == 2  # Netflix + Stan
        assert by['Title 4'][11][0][3] == 3  # season 3
        assert by['Title 2'][9] is None
        assert rows[0][0] == 'Title 1', 'newest first'
        assert '@@' not in html

        # 6. Shared clean-up rules: India (Wikidata, or IMDb akas for films) and suspicious ratings.
        sys.path.insert(0, str(ROOT / 'research'))
        sys.path.insert(0, str(ROOT / 'tools'))
        import build_new_streaming as b
        india = b.title_quality.India(tmp / 'none.json')
        india.wikidata, india.akas = {'tt1000002'}, {'tt1000003'}
        with gzip.open(ratings, 'wt') as f:
            f.write('tconst\taverageRating\tnumVotes\ntt1000001\t9.1\t500\n')
        rows, meta = b.build(d, ratings, None, india)
        assert rows and {r[0] for r in rows} == {'Title 4'}, [r[0] for r in rows]
        assert meta['dropped'] == {'india': 2, 'suspicious': 1}, meta['dropped']
    srv.shutdown()
    print('new-on-streaming tests passed')


if __name__ == '__main__':
    main()
