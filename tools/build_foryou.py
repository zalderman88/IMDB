#!/usr/bin/env python3
"""Build the For You page (foryou.html) from the already-built movie and TV finder pages.

It reads the embedded catalogue JSON from both pages, keeps a compact pool of titles
(no new facts: only IMDb ids, titles, years, genres, IMDb scores/votes, existing RT
critic scores and existing JustWatch AU subscription flags), and writes a self-contained
page whose recommendations are computed in the browser from the viewer's own likes.

Usage: python tools/build_foryou.py [--movies Australian_Movies_Android.html]
       [--tv TV_Shows_Android.html] [--out ForYou_Android.html] [--require-tv]
"""
import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / 'research/foryou_template.html'
CATALOGUE = re.compile(r'<script id="catalogue" type="application/json">(.*?)</script>', re.S)
METADATA = re.compile(r'<script id="metadata" type="application/json">(.*?)</script>', re.S)
PROVIDERS = ['nfx', 'prv', 'pmp', 'stn', 'dnp', 'mxx', 'atp', 'bng', 'sbs', 'abc']

# One genre vocabulary for movies (already tidied) and TV (raw IMDb spellings).
SPLIT = {'Mystery & thriller': ['Mystery', 'Thriller'], 'Music & Musical': ['Music', 'Musical']}
RENAME = {'sci fi': 'Science fiction', 'film noir': 'Film noir', 'talk show': 'Talk show',
          'reality tv': 'Reality TV', 'game show': 'Game show'}


def read_json(html, pattern, label):
    m = pattern.search(html)
    if not m:
        raise SystemExit(f'No {label} JSON found')
    return json.loads(m.group(1).replace('<\\/', '</'))


def tidy(genres):
    out = []
    for g in genres or []:
        for part in SPLIT.get(g, [g]):
            key = part.replace('-', ' ').strip().lower()
            name = RENAME.get(key, part.replace('-', ' ').strip().capitalize())
            if name not in out:
                out.append(name)
    return out


def num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--movies', default=str(ROOT / 'Australian_Movies_Android.html'))
    p.add_argument('--tv', default=str(ROOT / 'TV_Shows_Android.html'))
    p.add_argument('--out', default=str(ROOT / 'ForYou_Android.html'))
    p.add_argument('--require-tv', action='store_true', help='Fail if the TV page is missing')
    a = p.parse_args()

    movie_html = pathlib.Path(a.movies).read_text()
    movies = read_json(movie_html, CATALOGUE, 'movie catalogue')
    movie_meta = read_json(movie_html, METADATA, 'movie metadata')
    tv_path = pathlib.Path(a.tv)
    if tv_path.exists():
        tv_html = tv_path.read_text()
        shows, tv_meta = read_json(tv_html, CATALOGUE, 'TV catalogue'), read_json(tv_html, METADATA, 'TV metadata')
    elif a.require_tv:
        raise SystemExit(f'{tv_path} is missing')
    else:
        print(f'Note: {tv_path} not found, building For You with movies only', file=sys.stderr)
        shows, tv_meta = [], {}

    vocab = {}

    def gidx(genres):
        return [vocab.setdefault(g, len(vocab)) for g in tidy(genres)]

    pool = []
    # Movies: feature films only, same default exclusions as the movie finder
    # (known Indian productions hidden, suspicious 9.0+/under-10k-vote ratings hidden).
    for m in movies:
        if (m.get('kind') or 'movie') != 'movie' or 'IN' in (m.get('countries') or []):
            continue
        if not num(m.get('votes')) or m['votes'] < 1000 or not num(m.get('score')):
            continue
        if m['score'] >= 9 and m['votes'] < 10000 and not num(m.get('critics')) and not num(m.get('audience')):
            continue
        tt = m['id'].split(':')[-1]
        offers = ''.join(str(i) for i, code in enumerate(PROVIDERS) if (m.get('offers') or {}).get(code))
        pool.append(['m', tt, m['title'], m.get('year') or 0, gidx(m.get('genres')), m['score'], m['votes'],
                     m['critics'] if num(m.get('critics')) and num(m.get('criticCount')) and m['criticCount'] >= 50 else None,
                     offers, m.get('info') if str(m.get('info', '')).startswith('https://www.justwatch.com/') else None])
    n_movies = len(pool)
    for s in shows:
        if not num(s.get('score')) or not num(s.get('votes')) or s['votes'] < 1000:
            continue
        if s['score'] >= 9 and s['votes'] < 10000:
            continue
        pool.append(['t', s['id'], s['title'], s.get('startYear') or 0, gidx(s.get('genres')), s['score'], s['votes'],
                     s.get('lastYear') or s.get('endYear') or 0, s.get('type') or 'tvSeries', None])
    if len(vocab) > 31:
        raise SystemExit(f'{len(vocab)} genres; the page packs genres into a 31-bit mask')

    meta = {'genres': list(vocab), 'providers': PROVIDERS, 'movies': n_movies, 'shows': len(pool) - n_movies,
            'movieChecked': movie_meta.get('checked') or movie_meta.get('imdbAsOf'),
            'tvChecked': tv_meta.get('imdbAsOf')}
    data = json.dumps(pool, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
    html = TEMPLATE.read_text().replace('@@META@@', json.dumps(meta, ensure_ascii=False).replace('</', '<\\/'))
    html = html.replace('@@DATA@@', data)
    pathlib.Path(a.out).write_text(html)
    print(json.dumps({'movies': n_movies, 'shows': len(pool) - n_movies, 'genres': len(vocab),
                      'bytes': len(html.encode())}))


if __name__ == '__main__':
    main()
