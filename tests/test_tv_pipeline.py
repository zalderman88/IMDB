"""Offline end-to-end check of the TV pipeline on a tiny synthetic IMDb dataset.

Runs tools/refresh_tv.py on fixture .tsv.gz files, builds the TV page into a temp folder,
checks exactly which shows qualify, then runs the Node UI checks on that page.
Nothing is downloaded and nothing in the repo is overwritten.
"""
import gzip
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
N = r'\N'
# tconst, type, title, adult, start, end, runtime, genres
BASICS = [
    ('tt0000101', 'tvSeries', 'Old Show Back For More', 0, 2015, N, 45, 'Drama'),       # recent via 2021 episode
    ('tt0000102', 'tvSeries', 'Acclaimed Finished', 0, 2010, 2015, 50, 'Crime,Drama'),  # acclaimed only
    ('tt0000103', 'tvSeries', 'Nineties Classic', 0, 1995, 1999, 25, 'Comedy'),         # too old for both
    ('tt0000104', 'tvSeries', 'Boundary Six', 0, 2022, N, 30, 'Comedy'),                # 6.0 boundary
    ('tt0000105', 'tvSeries', 'Below Six', 0, 2022, N, 30, 'Comedy'),                   # 5.9
    ('tt0000106', 'tvSeries', 'Exactly Eight', 0, 2005, 2010, 40, 'Drama'),             # 8.0 is not above 8.0
    ('tt0000107', 'tvMiniSeries', 'Stuffed Votes', 0, 2021, 2021, 60, 'Drama'),         # 9.5, 2,000 votes
    ('tt0000108', 'movie', 'A Film', 0, 2021, N, 120, 'Drama'),                         # not TV
    ('tt0000109', 'tvSeries', 'Too Few Votes', 0, 2021, N, 30, 'Drama'),                # 999 votes
    ('tt0000110', 'tvSeries', 'Adult Show', 1, 2021, N, 30, 'Drama'),
    ('tt0000111', 'tvSeries', 'Announced Revival', 0, 2018, N, 30, 'Drama'),            # only a future episode after 2018
    ('tt0000112', 'tvSeries', 'Romantic Return', 0, 2016, N, 30, 'Drama,Romance'),      # recent, hidden by genre default
    ('tt0000113', 'tvSeries', 'Ended In 2020', 0, 2012, 2020, 30, 'Action'),            # recent via end year
    ('tt0000114', 'tvSeries', 'Grief Style Video', 0, 2026, N, 30, 'Drama'),            # 9.9 with 1,900 votes
    ('tt0000115', 'tvSeries', 'Popular Nine', 0, 2019, N, 50, 'Sci-Fi'),                # 9.1 with 50,000: not suspect
    ('tt0000116', 'tvSeries', 'Talk Tonight', 0, 2021, N, 60, 'Talk-Show'),
]
RATINGS = {'tt0000101': (7.0, 5000), 'tt0000102': (8.5, 20000), 'tt0000103': (9.0, 100000), 'tt0000104': (6.0, 1000),
           'tt0000105': (5.9, 50000), 'tt0000106': (8.0, 30000), 'tt0000107': (9.5, 2000), 'tt0000108': (9.0, 9000),
           'tt0000109': (7.0, 999), 'tt0000110': (7.0, 9000), 'tt0000111': (7.0, 9000), 'tt0000112': (7.5, 9000),
           'tt0000113': (6.5, 4000), 'tt0000114': (9.9, 1900), 'tt0000115': (9.1, 50000), 'tt0000116': (6.2, 1500)}
# episode tconst, parent, season, number, year
EPISODES = [('tt0001011', 'tt0000101', 1, 1, 2015), ('tt0001012', 'tt0000101', 1, 2, 2016), ('tt0001013', 'tt0000101', 2, 1, 2019),
            ('tt0001014', 'tt0000101', 3, 1, 2021), ('tt0001015', 'tt0000101', 3, 2, 2022),
            ('tt0001021', 'tt0000102', 1, 1, 2010), ('tt0001022', 'tt0000102', 2, 1, 2015),
            ('tt0001111', 'tt0000111', 1, 1, 2018), ('tt0001112', 'tt0000111', 2, 1, 2099),
            ('tt0001121', 'tt0000112', 1, 1, 2016), ('tt0001122', 'tt0000112', 2, 1, 2020)]
# 107 and 114 qualify but are dropped as likely vote-stuffed (IMDb 8.5+ from under 10,000 votes).
EXPECTED = {'tt0000101': (True, False), 'tt0000102': (False, True), 'tt0000104': (True, False),
            'tt0000112': (True, False), 'tt0000113': (True, False), 'tt0000115': (False, True),
            'tt0000116': (True, False)}


def write(path, header, rows):
    with gzip.open(path, 'wt', encoding='utf-8', newline='') as f:
        f.write('\t'.join(header) + '\n')
        for r in rows:
            f.write('\t'.join(str(v) for v in r) + '\n')


def main():
    tmp = pathlib.Path(tempfile.mkdtemp(prefix='tvfixture-'))
    try:
        basics = [(t, ty, ti, ti, a, s, e, rt, g) for t, ty, ti, a, s, e, rt, g in BASICS]
        basics += [(e, 'tvEpisode', 'Episode', 'Episode', 0, y, N, 30, 'Drama') for e, _, _, _, y in EPISODES]
        write(tmp / 'basics.tsv.gz', ['tconst', 'titleType', 'primaryTitle', 'originalTitle', 'isAdult', 'startYear',
                                      'endYear', 'runtimeMinutes', 'genres'], basics)
        write(tmp / 'ratings.tsv.gz', ['tconst', 'averageRating', 'numVotes'], [(k, *v) for k, v in RATINGS.items()])
        write(tmp / 'episode.tsv.gz', ['tconst', 'parentTconst', 'seasonNumber', 'episodeNumber'],
              [(e, p, s, n) for e, p, s, n, _ in EPISODES])
        run = lambda *a: subprocess.run([sys.executable, *map(str, a)], check=True, cwd=ROOT, capture_output=True, text=True)
        run(ROOT / 'tools/refresh_tv.py', '--basics', tmp / 'basics.tsv.gz', '--ratings', tmp / 'ratings.tsv.gz',
            '--episode', tmp / 'episode.tsv.gz', '--out', tmp / 'tv_1k.json', '--snapshot', tmp / 'snap.json')
        raw = {s['imdbId']: s for s in json.loads((tmp / 'tv_1k.json').read_text())}
        assert set(raw) == {k for k, v in RATINGS.items() if v[1] >= 1000} - {'tt0000108', 'tt0000110'}, sorted(raw)
        s101 = raw['tt0000101']
        assert (s101['lastEpisodeYear'], s101['seasons'], s101['seasonsSince2020'], s101['episodes']) == (2022, 3, 1, 5), s101
        assert raw['tt0000111']['lastEpisodeYear'] == 2018, 'future episode must not count'

        html = tmp / 'tv.html'
        run(ROOT / 'research/build_tv.py', '--source', tmp / 'tv_1k.json', '--snapshot', tmp / 'snap.json',
            '--out', html, '--extract', tmp / 'tv_catalogue.json')
        built = json.loads((tmp / 'tv_catalogue.json').read_text())
        got = {s['id']: (s['recent'], s['acclaimed']) for s in built['shows']}
        assert got == EXPECTED, f'qualification mismatch:\n got {got}\n want {EXPECTED}'
        meta = built['metadata']
        # Default view hides Romance (112); the two 9.0+/<10k titles (107, 114) are not in the data at all.
        assert meta['defaultResults'] == len(EXPECTED) - 1, meta
        assert meta['suspectHidden'] == 2, meta
        subprocess.run(['node', str(ROOT / 'tests/verify_tv_finder.mjs'), str(html), '--fixture'], check=True, cwd=ROOT)
        print(json.dumps({'tvPipelineFixture': 'passed', 'shows': len(got), 'defaultResults': meta['defaultResults']}))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    main()
