"""Offline check of tools/build_people.py on tiny synthetic IMDb files (nothing is downloaded)."""
import gzip
import json
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
PRINCIPALS = [
    ('tconst', 'ordering', 'nconst', 'category', 'job', 'characters'),
    ('tt0000001', '1', 'nm0000001', 'actor', r'\N', '["A"]'),
    ('tt0000001', '2', 'nm0000002', 'actress', r'\N', '["B"]'),
    ('tt0000001', '3', 'nm0000009', 'composer', r'\N', r'\N'),
    ('tt0000001', '4', 'nm0000003', 'director', r'\N', r'\N'),
    ('tt0000002', '1', 'nm0000001', 'actor', r'\N', '["C"]'),
    *[('tt0000002', str(i + 2), f'nm00001{i:02d}', 'actor', r'\N', r'\N') for i in range(8)],
    ('tt0000003', '1', 'nm0000004', 'actor', r'\N', r'\N'),  # not on the site
    ('tt0000004', '1', 'nm0000005', 'actor', r'\N', r'\N'),  # TV show
]
NAMES = [('nconst', 'primaryName', 'birthYear', 'deathYear', 'primaryProfession', 'knownForTitles'),
         ('nm0000001', 'Ana Áctor', r'\N', r'\N', 'actor', r'\N'),
         ('nm0000002', 'Bea Lead', r'\N', r'\N', 'actress', r'\N'),
         ('nm0000003', 'Dee Rector', r'\N', r'\N', 'director', r'\N'),
         ('nm0000004', 'Not Listed', r'\N', r'\N', 'actor', r'\N'),
         ('nm0000005', 'Tv Star', r'\N', r'\N', 'actor', r'\N'),
         ('nm0000009', 'Com Poser', r'\N', r'\N', 'composer', r'\N'),
         *[(f'nm00001{i:02d}', f'Extra {i}', r'\N', r'\N', 'actor', r'\N') for i in range(8)]]


def gz(path, rows):
    with gzip.open(path, 'wt', encoding='utf-8') as f:
        for r in rows:
            f.write('\t'.join(r) + '\n')


def page(path, ids):
    data = json.dumps([{'id': i, 'title': i} for i in ids])
    path.write_text(f'<html><script id="catalogue" type="application/json">{data}</script></html>', encoding='utf-8')


def main():
    with tempfile.TemporaryDirectory() as d:
        d = pathlib.Path(d)
        gz(d / 'p.tsv.gz', PRINCIPALS)
        gz(d / 'n.tsv.gz', NAMES)
        page(d / 'movies.html', ['jw:tt0000001', 'tt0000002'])
        page(d / 'tv.html', ['tt0000004'])
        out = d / 'people.json'
        subprocess.run([sys.executable, str(ROOT / 'tools' / 'build_people.py'), '--principals', str(d / 'p.tsv.gz'),
                        '--names', str(d / 'n.tsv.gz'), '--movies', str(d / 'movies.html'), '--tv', str(d / 'tv.html'),
                        '--out', str(out), '--min-titles', '3'], check=True)
        p = json.loads(out.read_text(encoding='utf-8'))
        name = lambda role, t: [p['names'][i] for i in p[role].get(t, [])]
        assert name('a', 'tt0000001') == ['Ana Áctor', 'Bea Lead'], name('a', 'tt0000001')
        assert name('d', 'tt0000001') == ['Dee Rector']
        assert len(name('a', 'tt0000002')) == 5 and name('a', 'tt0000002')[0] == 'Ana Áctor', 'cast capped at 5, billing order kept'
        assert name('a', 'tt0000004') == ['Tv Star']
        assert 'tt0000003' not in p['a'] and 'Not Listed' not in p['names'] and 'Com Poser' not in p['names']
        assert p['names'][0] == 'Ana Áctor', 'most-credited name first'
        # Refuses to write a near-empty index.
        r = subprocess.run([sys.executable, str(ROOT / 'tools' / 'build_people.py'), '--principals', str(d / 'p.tsv.gz'),
                            '--names', str(d / 'n.tsv.gz'), '--movies', str(d / 'movies.html'), '--tv', str(d / 'tv.html'),
                            '--out', str(d / 'x.json'), '--min-titles', '50'])
        assert r.returncode != 0 and not (d / 'x.json').exists()
    print('people index checks passed')


if __name__ == '__main__':
    main()
