#!/usr/bin/env python3
"""Offline test of the TMDB AU sweep, live where-to-watch and the TMDB New page, against a fake API.

Run: python tests/test_tmdb_au.py
"""
import gzip
import http.server
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import threading
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'research'))
sys.path.insert(0, str(ROOT / 'tools'))

PROVIDERS = {'movie': [{'provider_id': 8, 'provider_name': 'Netflix'}, {'provider_id': 21, 'provider_name': 'Stan'},
                       {'provider_id': 2, 'provider_name': 'Apple TV'}, {'provider_id': 350, 'provider_name': 'Apple TV Plus'},
                       {'provider_id': 999, 'provider_name': 'Netflix Kids'}],
             'tv': [{'provider_id': 8, 'provider_name': 'Netflix'}, {'provider_id': 385, 'provider_name': 'Binge'}]}
# catalogue[(kind, provider id)] = list of tmdb ids; the test edits it between sweeps.
CAT = {('movie', '8'): [1, 2, 3], ('movie', '21'): [2], ('tv', '8'): [10], ('tv', '385'): [11], ('movie', '2|350'): []}
LANG = {3: 'hi'}
SEEN = []


def item(kind, i):
    d = {'id': i, 'overview': f'About {i}', 'poster_path': f'/p{i}.jpg', 'genre_ids': [18], 'popularity': 10.0,
         'original_language': LANG.get(i, 'en')}
    if kind == 'movie':
        d.update(title=f'Movie {i}', release_date='2025-05-01')
    else:
        d.update(name=f'Show {i}', first_air_date='2024-02-02')
    return d


class Fake(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, body, code=200):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = dict(urllib.parse.parse_qsl(u.query))
        SEEN.append(u.path)
        if q.get('api_key') != 'k3y' and self.headers.get('Authorization') != 'Bearer eyJtoken':
            return self.send({'status_code': 7}, 401)
        if m := re.fullmatch(r'/3/watch/providers/(movie|tv)', u.path):
            assert q['watch_region'] == 'AU'
            return self.send({'results': PROVIDERS[m[1]]})
        if m := re.fullmatch(r'/3/discover/(movie|tv)', u.path):
            assert q['with_watch_monetization_types'] == 'flatrate' and q['watch_region'] == 'AU'
            ids = CAT.get((m[1], q['with_watch_providers']), [])
            page, per = int(q['page']), 2
            chunk = ids[(page - 1) * per: page * per]
            return self.send({'page': page, 'results': [item(m[1], i) for i in chunk],
                              'total_pages': max(1, -(-len(ids) // per)), 'total_results': len(ids)})
        if m := re.fullmatch(r'/3/(movie|tv)/(\d+)/external_ids', u.path):
            return self.send({'imdb_id': f'tt{9000000 + int(m[2])}'})
        if m := re.fullmatch(r'/3/genre/(movie|tv)/list', u.path):
            return self.send({'genres': [{'id': 18, 'name': 'Drama'}]})
        return self.send({}, 404)


def run(args, env):
    r = subprocess.run([sys.executable, *args], cwd=ROOT, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout + r.stderr


def main():
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        out = tmp / 'tmdb.json'
        env = {k: v for k, v in os.environ.items() if k != 'TMDB_API_KEY'}
        env.update(NO_PROXY='127.0.0.1', no_proxy='127.0.0.1')
        assert 'no TMDB_API_KEY' in run(['tools/fetch_tmdb_au.py', '--out', str(out)], env)
        env.update(TMDB_API_KEY='k3y', TMDB_API_BASE=f'http://127.0.0.1:{srv.server_address[1]}/3')

        # First sweep = baseline: nothing is new.
        run(['tools/fetch_tmdb_au.py', '--out', str(out), '--workers', '2'], env)
        d = json.loads(out.read_text())
        assert d['complete'] and d['previousAtUnix'] is None
        assert d['providers']['nfx']['tmdb'] == [8] and d['providers']['atp']['tmdb'] == [2, 350]
        assert 'bng' in d['providers'] and 'stn' in d['providers']
        assert d['titles']['m2']['on'] == {'nfx': 0, 'stn': 0}
        assert d['imdb']['t10'] == 'tt9000010'
        lookups = sum('/external_ids' in p for p in SEEN)

        import streaming_au
        live = streaming_au.load_live(out)
        assert live['movies']['tt9000002'] == {
            'nfx': 'https://www.themoviedb.org/movie/2/watch?locale=AU',
            'stn': 'https://www.themoviedb.org/movie/2/watch?locale=AU'}
        assert live['tv']['tt9000011'] == {'bng': 'https://www.themoviedb.org/tv/11/watch?locale=AU'}

        # Cached and fresh: no requests without --force.
        n = len(SEEN)
        assert 'not fetching' in run(['tools/fetch_tmdb_au.py', '--out', str(out)], env) and len(SEEN) == n

        # Second sweep: movie 4 arrives on Netflix, movie 2 leaves Stan and arrives nowhere else,
        # show 10 arrives on Binge. Only the new ones get a first-seen time; known ids are not re-looked-up.
        CAT[('movie', '8')] = [1, 2, 3, 4]
        CAT[('movie', '21')] = []
        CAT[('tv', '385')] = [11, 10]
        run(['tools/fetch_tmdb_au.py', '--out', str(out), '--force', '--workers', '2'], env)
        d2 = json.loads(out.read_text())
        assert d2['previousAtUnix'] == d['fetchedAtUnix']
        assert d2['titles']['m4']['on']['nfx'] == d2['fetchedAtUnix']
        assert d2['titles']['m2']['on'] == {'nfx': 0}
        assert d2['titles']['t10']['on'] == {'nfx': 0, 'bng': d2['fetchedAtUnix']}
        assert sum('/external_ids' in p for p in SEEN) == lookups + 1  # only m4

        # New page from TMDB: m4 and t10 (Binge); m3 is Hindi -> dropped.
        LANG[4] = 'en'
        ratings = tmp / 'r.tsv.gz'
        with gzip.open(ratings, 'wt') as f:
            f.write('tconst\taverageRating\tnumVotes\ntt9000004\t7.2\t4000\n')
        page = tmp / 'new.html'
        run(['tools/build_new_streaming.py', '--data', str(tmp / 'none.json'), '--tmdb', str(out),
             '--ratings', str(ratings), '--out', str(page)], env)
        html = page.read_text()
        rows = json.loads(html.split('<script id="catalogue" type="application/json">')[1].split('</script>')[0])
        meta = json.loads(html.split('<script id="metadata" type="application/json">')[1].split('</script>')[0])
        assert meta['state'] == 'ok' and meta['mode'] == 'tmdb', meta
        assert sorted(r[0] for r in rows) == ['Movie 4', 'Show 10'], rows
        m4 = next(r for r in rows if r[0] == 'Movie 4')
        assert m4[9:11] == [7.2, 4000] and m4[7] == 'https://image.tmdb.org/t/p/w185/p4.jpg' and m4[5] == ['Drama']

        # Baseline-only data says tracking has started.
        run(['tools/build_new_streaming.py', '--data', str(tmp / 'none.json'), '--tmdb', str(out) + '.x',
             '--out', str(page)], env)
        assert '"state":"no-key"' in page.read_text()
        b = dict(d); b['previousAtUnix'] = None
        (tmp / 'b.json').write_text(json.dumps(b))
        run(['tools/build_new_streaming.py', '--data', str(tmp / 'none.json'), '--tmdb', str(tmp / 'b.json'),
             '--out', str(page)], env)
        assert '"state":"baseline"' in page.read_text()

        # Bad key keeps the previous sweep; v4 bearer tokens work.
        before = out.read_text()
        env['TMDB_API_KEY'] = 'bad'
        assert 'HTTP 401' in run(['tools/fetch_tmdb_au.py', '--out', str(out), '--force'], env)
        assert out.read_text() == before
        env['TMDB_API_KEY'] = 'eyJtoken'
        run(['tools/fetch_tmdb_au.py', '--out', str(out), '--force', '--workers', '2'], env)
        assert json.loads(out.read_text())['complete']
    srv.shutdown()
    print('tmdb-au tests passed')


if __name__ == '__main__':
    main()
