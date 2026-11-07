"""Checks for the Coming soon page (tools/build_coming_soon.py) with a fake TMDB, no network."""
import datetime as dt
import json
import pathlib
import re
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
import build_coming_soon as cs  # noqa: E402

T = dt.date.today()
d = lambda n: (T + dt.timedelta(days=n)).isoformat()


class FakeApi:
    count = 0

    def get(self, path, **p):
        self.count += 1
        if path.startswith('/watch/providers/'):
            return {'results': [{'provider_id': 8, 'provider_name': 'Netflix'}, {'provider_id': 21, 'provider_name': 'Stan'},
                                {'provider_id': 134, 'provider_name': 'Foxtel Now'}]}
        if path == '/discover/movie':
            if p.get('with_watch_providers'):
                return {'total_pages': 1, 'results': [{'id': 1}, {'id': 5}]}
            if p.get('with_release_type') == '4':
                return {'total_pages': 1, 'results': [{'id': 2}]}
            return {'total_pages': 1, 'results': [{'id': 3}, {'id': 4}]}
        if path == '/discover/tv':
            if p.get('with_watch_providers'):
                return {'total_pages': 1, 'results': [{'id': 10}, {'id': 11}]}
            return {'total_pages': 1, 'results': [{'id': 12}]}
        movies = {
            1: dict(title='Netflix Original', release_date=d(10), wp=[8]),
            2: dict(title='Digital Film', release_date=d(-60), wp=[], rd=[(3, d(-60)), (4, d(20))]),
            3: dict(title='Cinema Film', release_date=d(30), wp=[], rd=[(3, d(30))]),
            4: dict(title='Indian Film', release_date=d(5), wp=[8], lang='hi'),
            5: dict(title='Old Film', release_date='2001-01-01', wp=[8]),
        }
        shows = {
            10: dict(name='Returning Show', first_air_date='2019-01-01', next={'episode_number': 1, 'season_number': 3, 'air_date': d(7)}, wp=[21]),
            11: dict(name='Daily Show', first_air_date='2015-01-01', next={'episode_number': 40, 'season_number': 9, 'air_date': d(1)}, wp=[8]),
            12: dict(name='Brand New Show', first_air_date=d(3), wp=[], networks=[{'name': 'HBO'}]),
        }
        m = re.match(r'/(movie|tv)/(\d+)$', path)
        kind, i = m.group(1), int(m.group(2))
        x = (movies if kind == 'movie' else shows)[i]
        out = {'id': i, 'overview': 'Plot.', 'poster_path': '/p.jpg', 'original_language': x.get('lang', 'en'),
               'genres': [{'name': 'Drama'}], 'popularity': 10 + i, 'external_ids': {'imdb_id': f'tt{i:07d}'},
               'watch/providers': {'results': {'AU': {'link': 'https://www.themoviedb.org/x/watch?locale=AU',
                                                      'flatrate': [{'provider_id': w} for w in x['wp']]}}}}
        if kind == 'movie':
            out.update(title=x['title'], release_date=x['release_date'],
                       release_dates={'results': [{'iso_3166_1': 'AU', 'release_dates': [{'type': t, 'release_date': v + 'T00:00:00.000Z'} for t, v in x.get('rd', [])]}]})
        else:
            out.update(name=x['name'], first_air_date=x['first_air_date'], next_episode_to_air=x.get('next'), networks=x.get('networks', []))
        return out


data = cs.fetch(FakeApi(), 180, workers=2)
by = {x['title']: x for x in data['items']}
assert set(by) == {'Netflix Original', 'Digital Film', 'Cinema Film', 'Returning Show', 'Brand New Show'}, sorted(by)
assert by['Netflix Original']['what'] == 'streaming' and by['Netflix Original']['services'] == ['nfx'] and by['Netflix Original']['date'] == d(10)
assert by['Digital Film']['what'] == 'digital' and by['Digital Film']['date'] == d(20)
assert by['Cinema Film']['what'] == 'cinema' and by['Cinema Film']['services'] == []
assert by['Returning Show']['what'] == 'season' and by['Returning Show']['season'] == 3 and by['Returning Show']['services'] == ['stn']
assert by['Brand New Show']['what'] == 'premiere' and by['Brand New Show']['network'] == 'HBO'
assert 'fxn' not in data['services'], 'Foxtel Now must stay off (Zac removed it)'

items, meta = cs.build(data)
assert [x['date'] for x in items] == sorted(x['date'] for x in items)
html = cs.render(items, meta)
assert '@@' not in html and 'id="cs-list"' in html and 'aria-current="page">Coming soon</a>' in html
for s in ('watchlist.js', 'extras.js', 'account.js', 'my-services-v1'):
    assert s in html, s
blob = json.loads(re.search(r'<script id="catalogue" type="application/json">(.*?)</script>', html, re.S).group(1))
assert len(blob) == 5

# No key and no cache: still a page that says it isn't set up.
items, meta = cs.build(None)
assert meta['state'] == 'no-key' and items == [] and '@@' not in cs.render(items, meta)

# Every page links to Coming soon once.
for name in ['movie_finder', 'tv_finder', 'foryou', 'new_streaming', 'top20', 'watchlist', 'notifications']:
    t = (ROOT / f'research/{name}_template.html').read_text(encoding='utf-8')
    assert t.count('href="coming.html"') == 1, name + ': missing Coming soon nav link'
print('coming soon tests passed')
