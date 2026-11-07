#!/usr/bin/env python3
"""Build the New on streaming page (new.html).

Two possible sources, both from official APIs:
  * cache/new_streaming.json from tools/fetch_new_streaming.py (Streaming Availability API,
    exact "added" dates), used when present; otherwise
  * cache/tmdb_au.json from tools/fetch_tmdb_au.py (TMDB watch providers): a title is new when
    it appeared on a service since the previous fortnightly sweep (TMDB has no added date).
This step is
offline: it adds IMDb ratings from IMDb's official title.ratings dataset when --ratings is
given, packs one row per title, and fills research/new_streaming_template.html. With no
data file (no API key yet) it still writes a page that says it is not set up yet.

Usage: python tools/build_new_streaming.py [--data cache/new_streaming.json]
       [--tmdb cache/tmdb_au.json] [--ratings /tmp/imdb/title.ratings.tsv.gz]
       [--out New_Streaming_Android.html]
"""
import argparse
import datetime as dt
import gzip
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'research'))
import title_quality  # noqa: E402  shared clean-up rules (India, suspicious ratings)
TEMPLATE = ROOT / 'research/new_streaming_template.html'


def load_ratings(path, wanted):
    out = {}
    if not path or not wanted:
        return out
    with gzip.open(path, 'rt', encoding='utf-8') as f:
        next(f, None)
        for line in f:
            tt, _, rest = line.partition('\t')
            if tt in wanted:
                score, votes = rest.rstrip('\n').split('\t')[:2]
                try:
                    out[tt] = (round(float(score), 1), int(votes))
                except ValueError:
                    pass
    return out


INDIAN_LANGS = {'hi', 'ta', 'te', 'ml', 'kn', 'mr', 'bn', 'pa', 'gu', 'or', 'as'}
WINDOW_DAYS = 45


def build_tmdb(data, ratings_path=None, imdb_as_of=None, india=None):
    """Rows for titles that appeared on a service since the previous TMDB sweep."""
    if not data or not data.get('titles'):
        return [], {'state': 'no-key', 'services': []}
    codes = list(data.get('providers') or {})
    sidx = {c: i for i, c in enumerate(codes)}
    services = [{'id': c, 'name': data['providers'][c]['name'], 'color': None} for c in codes]
    base = {'services': services, 'fetchedAt': data.get('fetchedAtUnix'), 'from': data.get('previousAtUnix'),
            'source': 'TMDB', 'sourceUrl': 'https://www.themoviedb.org/', 'imdbAsOf': imdb_as_of, 'mode': 'tmdb'}
    if not data.get('previousAtUnix'):
        return [], {**base, 'state': 'baseline'}
    cutoff = data['fetchedAtUnix'] - WINDOW_DAYS * 86400
    genres, imdb = data.get('genres') or {}, data.get('imdb') or {}
    picked = {k: t for k, t in data['titles'].items() if any(v and v >= cutoff for v in (t.get('on') or {}).values())}
    ratings = load_ratings(ratings_path, {imdb[k] for k in picked if imdb.get(k)})
    india = india or title_quality.load_india()
    rows, dropped = [], {}
    for k, t in picked.items():
        iid = imdb.get(k) or None
        score, votes = ratings.get(iid, (None, None))
        reason = title_quality.tv_drop_reason({'id': iid, 'score': score, 'votes': votes}, india)
        if not reason and (t.get('lang') in INDIAN_LANGS or (k[0] == 'm' and iid in india.akas)):
            reason = 'india'
        if reason:
            dropped[reason] = dropped.get(reason, 0) + 1
            continue
        url = f"https://www.themoviedb.org/{'movie' if k[0] == 'm' else 'tv'}/{k[1:]}/watch?locale=AU"
        adds = sorted(([sidx[c], v, url, 0] for c, v in t['on'].items() if v and v >= cutoff and c in sidx),
                      key=lambda x: -x[1])
        year = int(t['date'][:4]) if t.get('date') and t['date'][:4].isdigit() else 0
        rows.append([t.get('title') or 'Untitled', 'movie' if k[0] == 'm' else 'series', year, 0, 0,
                     [genres.get(str(g)) for g in t.get('genres') or [] if genres.get(str(g))][:4],
                     t.get('overview'), f"https://image.tmdb.org/t/p/w185{t['poster']}" if t.get('poster') else None,
                     iid, score, votes, adds])
    rows.sort(key=lambda r: (-r[11][0][1], -(r[10] or 0)))
    return rows, {**base, 'state': 'ok', 'dropped': dropped}


def build(data, ratings_path=None, imdb_as_of=None, india=None):
    if data is None:
        return [], {'state': 'no-key', 'services': []}
    if data.get('error') or not data.get('services'):
        return [], {'state': 'error', 'services': []}
    services = data['services']
    sidx = {s['id']: i for i, s in enumerate(services)}
    shows = data.get('shows') or {}
    adds = {}
    for c in data.get('changes') or []:
        if c.get('show') in shows and c.get('service') in sidx and c.get('ts'):
            season = c.get('season') if c.get('item') == 'season' else 0
            adds.setdefault(c['show'], set()).add((sidx[c['service']], int(c['ts']), c.get('link') or None, season or 0))
    wanted = {shows[k]['imdbId'] for k in adds if shows[k].get('imdbId')}
    ratings = load_ratings(ratings_path, wanted)
    india = india or title_quality.load_india()
    rows, dropped = [], {}
    for sid, a in adds.items():
        s = shows[sid]
        score, votes = ratings.get(s.get('imdbId'), (None, None))
        # Same rules as the finders: India always out (Wikidata list; for films also IMDb's
        # alternative-title pattern, as there is no country data here) and suspicious ratings out.
        iid = s.get('imdbId')
        reason = title_quality.tv_drop_reason({'id': iid, 'score': score, 'votes': votes}, india)
        if not reason and s.get('type') == 'movie' and iid in india.akas:
            reason = 'india'
        if reason:
            dropped[reason] = dropped.get(reason, 0) + 1
            continue
        # Keep the newest entry per service+season (a title can be re-added).
        best = {}
        for svc, ts, link, season in a:
            k = (svc, season)
            if k not in best or ts > best[k][1]:
                best[k] = (svc, ts, link, season)
        rows.append([s.get('title'), s.get('type'), s.get('year') or 0, s.get('lastYear') or 0, s.get('seasons') or 0,
                     s.get('genres') or [], s.get('overview'), s.get('poster'), s.get('imdbId'), score, votes,
                     sorted((list(x) for x in best.values()), key=lambda x: -x[1])])
    rows.sort(key=lambda r: -max(x[1] for x in r[11]))
    meta = {'state': 'ok', 'services': [{'id': s['id'], 'name': s['name'], 'color': s.get('color')} for s in services],
            'fetchedAt': data.get('fetchedAtUnix'), 'from': data.get('windowFromUnix'),
            'source': data.get('source'), 'sourceUrl': data.get('sourceUrl'), 'imdbAsOf': imdb_as_of,
            'truncated': data.get('truncated') or [], 'dropped': dropped}
    return rows, meta


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--data', default=str(ROOT / 'cache/new_streaming.json'))
    p.add_argument('--tmdb', default=str(ROOT / 'cache/tmdb_au.json'))
    p.add_argument('--ratings', help="IMDb title.ratings.tsv.gz (optional)")
    p.add_argument('--out', default=str(ROOT / 'New_Streaming_Android.html'))
    a = p.parse_args()
    path = pathlib.Path(a.data)
    data = json.loads(path.read_text()) if path.exists() else None
    imdb_as_of = dt.date.today().isoformat() if a.ratings else None
    tmdb = pathlib.Path(a.tmdb)
    if (data is None or data.get('error')) and tmdb.exists():
        rows, meta = build_tmdb(json.loads(tmdb.read_text()), a.ratings, imdb_as_of)
    else:
        rows, meta = build(data, a.ratings, imdb_as_of)
    esc = lambda o: json.dumps(o, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
    html = TEMPLATE.read_text().replace('@@META@@', esc(meta)).replace('@@DATA@@', esc(rows))
    pathlib.Path(a.out).write_text(html)
    print(json.dumps({'state': meta['state'], 'titles': len(rows), 'services': len(meta['services']),
                      'rated': sum(1 for r in rows if r[9] is not None), 'dropped': meta.get('dropped', {}),
                      'bytes': len(html.encode())}))


if __name__ == '__main__':
    main()
