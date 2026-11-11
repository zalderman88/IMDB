"""Build research/imdb/tv_1k.json from IMDb's official non-commercial datasets.

Writes every TV series / miniseries with 1,000+ IMDb votes (adult titles omitted), with the
facts the TV finder needs: start/end year, the latest year an episode aired (from
title.episode joined to each episode's startYear), season and episode counts, genres,
runtime, rating and votes. Qualification is applied later by research/build_tv.py.

Usage:
  python tools/refresh_tv.py                     # download from datasets.imdbws.com
  python tools/refresh_tv.py --basics b.tsv.gz --ratings r.tsv.gz --episode e.tsv.gz
"""
import argparse
import csv
import datetime
import gzip
import json
import pathlib
import shutil
import sys
import tempfile
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / 'research/imdb/tv_1k.json'
SNAPSHOT = ROOT / 'research/tv_snapshot.json'
URLS = {'basics': 'https://datasets.imdbws.com/title.basics.tsv.gz',
        'ratings': 'https://datasets.imdbws.com/title.ratings.tsv.gz',
        'episode': 'https://datasets.imdbws.com/title.episode.tsv.gz'}
TYPES = {'tvSeries', 'tvMiniSeries'}
MIN_VOTES = 1000
csv.field_size_limit(sys.maxsize)


def local(source, tmp):
    """Return a local path for a dataset, downloading it once if it is a URL."""
    if not source.startswith('https://'):
        return source
    path = pathlib.Path(tmp) / source.rsplit('/', 1)[1]
    if not path.exists():
        req = urllib.request.Request(source, headers={'User-Agent': 'movie-finder-refresh/1.0'})
        with urllib.request.urlopen(req, timeout=300) as r, open(path, 'wb') as f:
            shutil.copyfileobj(r, f, 1 << 20)
    return str(path)


def rows(path):
    with gzip.open(path, 'rt', encoding='utf-8', newline='') as f:
        yield from csv.DictReader(f, delimiter='\t', quoting=csv.QUOTE_NONE)


def num(value):
    return None if value in (None, '', '\\N') else int(value)


def key(tconst):
    return int(tconst[2:])


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for name, url in URLS.items():
        p.add_argument('--' + name, default=url)
    p.add_argument('--cache', help='Directory to keep downloads in (default: a temporary directory)')
    p.add_argument('--out', default=str(OUT), help='Output JSON (default: research/imdb/tv_1k.json)')
    p.add_argument('--snapshot', default=str(SNAPSHOT), help='Snapshot-date JSON to update')
    a = p.parse_args()
    out_path, snap_path = pathlib.Path(a.out), pathlib.Path(a.snapshot)
    this_year = datetime.datetime.now(datetime.timezone.utc).year

    with tempfile.TemporaryDirectory() as tmp:
        cache = a.cache or tmp
        pathlib.Path(cache).mkdir(parents=True, exist_ok=True)
        basics, ratings_path, episode = (local(getattr(a, n), cache) for n in ('basics', 'ratings', 'episode'))

        ratings = {}
        for r in rows(ratings_path):
            votes = int(r['numVotes'])
            if votes >= MIN_VOTES:
                ratings[r['tconst']] = (float(r['averageRating']), votes)

        # Pass 1: the series themselves.
        shows = {}
        for b in rows(basics):
            if b['titleType'] not in TYPES or b['isAdult'] == '1':
                continue
            rating = ratings.get(b['tconst'])
            start = num(b['startYear'])
            if not rating or start is None:
                continue
            shows[key(b['tconst'])] = {
                'imdbId': b['tconst'], 'title': b['primaryTitle'], 'originalTitle': b['originalTitle'],
                'type': b['titleType'], 'startYear': start, 'endYear': num(b['endYear']),
                'runtime': num(b['runtimeMinutes']),
                'genres': [] if b['genres'] in ('', '\\N') else b['genres'].split(','),
                'score': rating[0], 'votes': rating[1]}

        # Pass 2: which episodes belong to those series, and their season numbers.
        parent_of = {}
        for e in rows(episode):
            parent = key(e['parentTconst'])
            if parent in shows:
                parent_of[key(e['tconst'])] = (parent, num(e['seasonNumber']))

        # Pass 3: each episode's air year from title.basics.
        stats = {k: {'episodes': 0, 'last': None, 'seasons': {}} for k in shows}
        for b in rows(basics):
            if b['titleType'] != 'tvEpisode':
                continue
            link = parent_of.get(key(b['tconst']))
            if not link:
                continue
            parent, season = link
            s = stats[parent]
            year = num(b['startYear'])
            if year is not None and year > this_year:
                year = None  # announced future episodes do not count as released
            if year is not None:
                s['episodes'] += 1
                s['last'] = year if s['last'] is None else max(s['last'], year)
                if season is not None:
                    first = s['seasons'].get(season)
                    s['seasons'][season] = year if first is None else min(first, year)

    out = []
    for k, show in shows.items():
        s = stats[k]
        seasons = s['seasons']
        latest = max(seasons) if seasons else None
        show.update({'episodes': s['episodes'], 'lastEpisodeYear': s['last'], 'seasons': len(seasons),
                     'latestSeason': latest, 'latestSeasonYear': seasons.get(latest) if latest else None,
                     'seasonsSince2020': sum(1 for y in seasons.values() if y >= 2020)})
        out.append(show)
    out.sort(key=lambda m: m['imdbId'])

    previous = json.loads(out_path.read_text()) if out_path.exists() else []
    if len(out) < 0.9 * len(previous):
        raise SystemExit(f'Refusing to write: only {len(out):,} IMDb TV records versus {len(previous):,} before. '
                         'The download is probably truncated; the previous snapshot is kept.')
    if len(out) < 5000:
        print(f'Warning: only {len(out):,} TV records; expected well over 10,000 from the full datasets.')
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text('[\n' + ',\n'.join(json.dumps(m, ensure_ascii=False) for m in out) + '\n]\n')

    snap = json.loads(snap_path.read_text()) if snap_path.exists() else {}
    snap['imdbAsOf'] = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    snap_path.write_text(json.dumps(snap, indent=2) + '\n')
    print(json.dumps({'imdbTvRecords': len(out), 'previous': len(previous),
                      'withEpisodeYears': sum(1 for m in out if m['lastEpisodeYear']),
                      'imdbAsOf': snap['imdbAsOf']}))


if __name__ == '__main__':
    main()
