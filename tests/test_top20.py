#!/usr/bin/env python3
"""Offline checks for tools/build_top20.py: scoring, merging across services, IMDb matching,
India exclusion and the page build. Uses small made-up fixtures, no network."""
import gzip
import json
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
INDIA = json.loads((ROOT / 'research/imdb/india_titles.json').read_text())['wikidata'][0]


def show(title, imdb, year, rating, svc, kind='movie'):
    return {'itemType': 'show', 'showType': kind, 'imdbId': imdb, 'title': title, 'releaseYear': year,
            'firstAirYear': year, 'rating': rating,
            'streamingOptions': {'au': [{'service': {'id': svc}, 'type': 'subscription',
                                         'link': f'https://example.com/{svc}/{imdb}'}]}}


def main():
    with tempfile.TemporaryDirectory() as t:
        t = pathlib.Path(t)
        head = 'country_name\tcountry_iso2\tweek\tcategory\tweekly_rank\tshow_title\tseason_title\tcumulative_weeks_in_top_10\n'
        rows = [('2026-11-01', 'Films', 1, 'Alpha Film', 2), ('2026-11-01', 'Films', 2, 'Old Classic', 1),
                ('2026-11-01', 'Films', 3, 'Indian Hit', 1),
                ('2026-10-25', 'Films', 1, 'Old Classic', 1),
                ('2026-11-01', 'TV', 1, 'Beta Show', 1)]
        tsv = head + ''.join(f'Australia\tAU\t{w}\t{c}\t{r}\t{n}\tN/A\t{k}\n' for w, c, r, n, k in rows)
        tsv += 'Brazil\tBR\t2026-11-01\tFilms\t1\tNot Here\tN/A\t1\n'
        (t / 'nf.tsv').write_text(tsv)
        sa = t / 'sa'
        sa.mkdir()
        (sa / 'prime-movie.json').write_text(json.dumps([show('Prime Only', 'tt9000001', 2026, 70, 'prime'),
                                                          show('Alpha Film', 'tt9000010', 2026, 80, 'prime')]))
        basics = 'tconst\ttitleType\tprimaryTitle\toriginalTitle\tisAdult\tstartYear\tendYear\truntimeMinutes\tgenres\n'
        basics += 'tt9000010\tmovie\tAlpha Film\tAlpha Film\t0\t2026\t\\N\t100\tAction\n'
        basics += 'tt9000020\tmovie\tOld Classic\tOld Classic\t0\t1980\t\\N\t100\tDrama\n'
        basics += 'tt9000021\tmovie\tOld Classic\tOld Classic\t0\t2005\t\\N\t100\tDrama\n'
        basics += f'{INDIA}\tmovie\tIndian Hit\tIndian Hit\t0\t2026\t\\N\t100\tDrama\n'
        basics += 'tt9000030\ttvSeries\tBeta Show\tBeta Show\t0\t2026\t\\N\t50\tComedy\n'
        ratings = 'tconst\taverageRating\tnumVotes\ntt9000010\t8.0\t5000\ntt9000020\t8.5\t90000\n'
        ratings += f'tt9000021\t5.0\t300\n{INDIA}\t7.0\t9000\ntt9000030\t6.0\t500\n'
        with gzip.open(t / 'b.gz', 'wt') as f:
            f.write(basics)
        with gzip.open(t / 'r.gz', 'wt') as f:
            f.write(ratings)
        out, js = t / 'top20.html', t / 'top20.json'
        r = subprocess.run([sys.executable, str(ROOT / 'tools/build_top20.py'), '--netflix-tsv', str(t / 'nf.tsv'),
                            '--sa-fixture', str(sa), '--basics', str(t / 'b.gz'), '--ratings', str(t / 'r.gz'),
                            '--today', '2026-11-07', '--cache-dir', str(t / 'cache'), '--out', str(out), '--json', str(js)],
                           capture_output=True, text=True, env={'PATH': '/usr/bin:/bin'})
        assert r.returncode == 0, r.stderr
        d = json.loads(js.read_text())
        movies = {m['title']: m for m in d['movies']}
        # Alpha: Netflix #1 (10) + Prime #2 (5) = 15, plus (8.0-6)*1.5 = 3 bonus.
        a = movies['Alpha Film']
        assert a['rank'] == 1 and a['chartPts'] == 15 and a['bonus'] == 3 and a['total'] == 18, a
        assert [c['svc'] for c in a['charts']] == ['netflix', 'prime'], a['charts']
        assert {w['svc'] for w in a['where']} == {'netflix', 'prime'}
        # Old Classic: #2 of 3 -> 6.667 points, + a quarter of last week's #1 (10 * 0.25 = 2.5);
        # matched to the 1980 film (the 2005 one has under 200 votes), bonus (8.5-6)*1.5 = 3.75.
        o = movies['Old Classic']
        assert o['imdb'] == 'tt9000020' and o['chartPts'] == 9.17 and o['bonus'] == 3.75, o
        assert 'Indian Hit' not in movies, 'India must be excluded'
        assert 'Not Here' not in movies
        # Beta Show: under 1,000 IMDb votes, so no quality bonus.
        b = d['shows'][0]
        assert b['title'] == 'Beta Show' and b['bonus'] == 0 and b['imdbScore'] == 6.0
        assert d['netflixWeek'] == '2026-11-01'
        html = out.read_text()
        assert '@@DATA@@' not in html and 'aria-current="page">Top 20</a>' in html
        # No keys and no fixtures: the build still succeeds with Netflix only.
        r = subprocess.run([sys.executable, str(ROOT / 'tools/build_top20.py'), '--netflix-tsv', str(t / 'nf.tsv'),
                            '--cache-dir', str(t / 'empty'), '--out', str(out), '--json', str(js)],
                           capture_output=True, text=True, env={'PATH': '/usr/bin:/bin'})
        assert r.returncode == 0, r.stderr
        d = json.loads(js.read_text())
        assert not d['sources']['streaming_availability']['ok'] and d['movies'][0]['title'] == 'Alpha Film'
    print('top20 tests passed')


if __name__ == '__main__':
    main()
