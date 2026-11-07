"""Refresh research/imdb/movies_1k.json from IMDb's official non-commercial datasets.

Only IMDb facts change (title, year, runtime, genres, rating, votes). Streaming offers,
Rotten Tomatoes facts, classifications and languages are left exactly as snapshotted.

Usage:
  python tools/refresh_imdb.py                 # download from datasets.imdbws.com
  python tools/refresh_imdb.py --basics b.tsv.gz --ratings r.tsv.gz   # local files
"""
import argparse
import csv
import datetime
import gzip
import io
import json
import pathlib
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / 'research/imdb/movies_1k.json'
SNAPSHOT = ROOT / 'research/source_snapshot.json'
URLS = {'basics': 'https://datasets.imdbws.com/title.basics.tsv.gz',
        'ratings': 'https://datasets.imdbws.com/title.ratings.tsv.gz'}
TYPES = {'movie', 'tvMovie', 'video', 'short', 'tvShort'}
MIN_VOTES = 1000
csv.field_size_limit(sys.maxsize)


def rows(source):
    if source.startswith('https://'):
        req = urllib.request.Request(source, headers={'User-Agent': 'movie-finder-refresh/1.0'})
        raw = urllib.request.urlopen(req, timeout=300)
    else:
        raw = open(source, 'rb')
    with gzip.open(raw, 'rt', encoding='utf-8', newline='') as f:
        yield from csv.DictReader(f, delimiter='\t', quoting=csv.QUOTE_NONE)


def num(value, kind):
    return None if value in (None, '', '\\N') else kind(value)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--basics', default=URLS['basics'])
    p.add_argument('--ratings', default=URLS['ratings'])
    a = p.parse_args()

    ratings = {}
    for r in rows(a.ratings):
        votes = int(r['numVotes'])
        if votes >= MIN_VOTES:
            ratings[r['tconst']] = (float(r['averageRating']), votes)

    films = []
    for b in rows(a.basics):
        rating = ratings.get(b['tconst'])
        if not rating or b['titleType'] not in TYPES:
            continue
        year = num(b['startYear'], int)
        if year is None:  # snapshot schema always has a year
            continue
        films.append({'imdbId': b['tconst'], 'title': b['primaryTitle'], 'originalTitle': b['originalTitle'],
                      'type': b['titleType'], 'year': year, 'runtime': num(b['runtimeMinutes'], int),
                      'genres': [] if b['genres'] in ('', '\\N') else b['genres'].split(','),
                      'score': rating[0], 'votes': rating[1], 'adult': b['isAdult'] == '1'})
    films.sort(key=lambda m: m['imdbId'])

    previous = json.loads(OUT.read_text()) if OUT.exists() else []
    if len(films) < 0.9 * len(previous):
        raise SystemExit(f'Refusing to write: only {len(films):,} IMDb records versus {len(previous):,} before. '
                         'The download is probably truncated; the previous snapshot is kept.')
    # One record per line keeps git diffs small.
    OUT.write_text('[\n' + ',\n'.join(json.dumps(m, ensure_ascii=False) for m in films) + '\n]\n')

    snap = json.loads(SNAPSHOT.read_text())
    snap['imdbAsOf'] = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    SNAPSHOT.write_text(json.dumps(snap, indent=2) + '\n')
    print(json.dumps({'imdbRecords': len(films), 'previous': len(previous), 'imdbAsOf': snap['imdbAsOf']}))


if __name__ == '__main__':
    main()
