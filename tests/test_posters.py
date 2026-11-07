"""Offline checks for tools/fetch_posters.py output format (no network)."""
import json, pathlib, sys, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / 'tools'))
import fetch_posters as fp

assert fp.short('https://upload.wikimedia.org/wikipedia/en/thumb/a/ab/X.jpg/250px-X.jpg') == 'w:en/thumb/a/ab/X.jpg/250px-X.jpg'
assert fp.short('https://static.tvmaze.com/uploads/images/medium_portrait/1/2.jpg') == 'm:medium_portrait/1/2.jpg'
assert fp.short('https://thumb.wikimedia.org/wikipedia/en/thumb/1/1c/A.jpg/250px-A.jpg?utm_source=x') == 'w:en/thumb/1/1c/A.jpg/250px-A.jpg'
assert fp.short('http://evil.example/x.jpg') == ''
long = 'First sentence is here. ' * 40
out = fp.first_paragraph(long + '\nSecond paragraph.')
assert len(out) <= fp.SYNOPSIS_CHARS and out.endswith('.') and 'Second' not in out
with tempfile.TemporaryDirectory() as d:
    cache = {'tt0000001': {'p': 'w:a.jpg', 'o': 'Film.', 'u': 'w:Film'}, 'tt0000002': {'p': 'm:b.jpg', 'o': ''},
             'tt0000003': {'p': '', 'o': 'Text only.', 'u': 'm:shows/3/x'}, 'tt0000004': {'p': '', 'o': ''}}
    fp.write_outputs(pathlib.Path(d), list(cache) + ['tt0000005'], cache)
    idx = json.loads((pathlib.Path(d) / 'index.json').read_text())
    assert idx['p'] == {'tt0000001': 'w:a.jpg', 'tt0000002': '!m:b.jpg', 'tt0000003': ''}, idx
    s1 = json.loads((pathlib.Path(d) / f'syn/{1 % idx["shards"]}.json').read_text())
    assert s1 == {'tt0000001': ['Film.', 'w:Film']}
print('Poster output test passed')

# TMDB lookup against a fake server (no key or network needed).
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if 'api_key=bad' in self.path:
            self.send_response(401); self.end_headers(); return
        tt = self.path.split('/find/')[1].split('?')[0]
        body = {'movie_results': [], 'tv_results': []}
        if tt == 'tt0000001':
            body['movie_results'] = [{'id': 11, 'poster_path': '/abc.jpg', 'overview': 'A film.'}]
        elif tt == 'tt0000002':
            body['tv_results'] = [{'id': 22, 'poster_path': '/def.jpg', 'overview': ''}]
        data = json.dumps(body).encode()
        self.send_response(200); self.end_headers(); self.wfile.write(data)


srv = ThreadingHTTPServer(('127.0.0.1', 0), Fake)
threading.Thread(target=srv.serve_forever, daemon=True).start()
fp.TMDB = f'http://127.0.0.1:{srv.server_port}'
lim = fp.Limiter(500)
assert fp.tmdb('tt0000001', 'good', lim) == ('t:abc.jpg', 'A film.', 't:movie/11')
assert fp.tmdb('tt0000002', 'good', lim) == ('t:def.jpg', '', 't:tv/22')
assert fp.tmdb('tt0000009', 'good', lim) == ('', '', '')
try:
    fp.tmdb('tt0000001', 'bad', lim); raise SystemExit('401 not raised')
except fp.AuthError:
    pass
import datetime as dt, time
cache = {'tt0000002': {'p': 'w:x/250px-y.jpg', 'o': 'Wiki text.', 'u': 'w:Y', 't': '2026-11-01'}}
fp.tmdb_pass(['tt0000001', 'tt0000002'], cache, 'good', time.monotonic() + 30, dt.date(2026, 11, 7))
fp.tmdb_pass(['tt0000009'], cache, 'bad', time.monotonic() + 30, dt.date(2026, 11, 7))  # must not raise
with tempfile.TemporaryDirectory() as d:
    fp.write_outputs(pathlib.Path(d), ['tt0000001', 'tt0000002'], cache)
    idx = json.loads((pathlib.Path(d) / 'index.json').read_text())['p']
    assert idx == {'tt0000001': 't:abc.jpg', 'tt0000002': 't:def.jpg'}, idx  # TMDB poster, Wikipedia text kept
    syn = json.loads((pathlib.Path(d) / f'syn/2.json').read_text())
    assert syn == {'tt0000002': ['Wiki text.', 'w:Y']}, syn
srv.shutdown()
print('TMDB test passed')
