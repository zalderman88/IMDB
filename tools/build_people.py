"""Build _site/people.json: directors and top-billed cast for every title on the site.

Lets the search boxes find titles by actor or director (site/extras.js loads it on demand).
Reads the IMDb non-commercial bulk files title.principals and name.basics, keeping only
titles that are in the built Movies and TV pages, so the output stays small.

Usage: python tools/build_people.py --principals title.principals.tsv.gz --names name.basics.tsv.gz
       [--movies Australian_Movies_Android.html] [--tv TV_Shows_Android.html] [--out _site/people.json]
"""
import argparse
import gzip
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CATALOGUE = re.compile(r'<script id="catalogue" type="application/json">(.*?)</script>', re.S)
CAST_PER_TITLE = 5
ROLE = {'director': 'd', 'actor': 'a', 'actress': 'a', 'self': 'a'}


def title_ids(path, required):
    p = pathlib.Path(path)
    if not p.exists():
        if required:
            raise SystemExit(f'Missing {p}')
        print(f'{p} not found, skipped', file=sys.stderr)
        return set()
    m = CATALOGUE.search(p.read_text(encoding='utf-8'))
    if not m:
        raise SystemExit(f'No catalogue JSON in {p}')
    data = json.loads(m.group(1).replace('<\\/', '</'))
    return {str(r['id']).split(':')[-1] for r in data if isinstance(r, dict) and r.get('id')}


def tsv(path, keys):
    """Yield rows (as dicts) whose given column is in keys; skips other lines without splitting them."""
    with gzip.open(path, 'rt', encoding='utf-8', newline='') as f:
        header = f.readline().rstrip('\n').split('\t')
        for line in f:
            key = line[:line.find('\t')]
            if key not in keys:
                continue
            yield dict(zip(header, line.rstrip('\n').split('\t')))


def build(principals, names, ids):
    credits = {}  # tconst -> {'d': [nconst], 'a': [nconst]}
    for r in tsv(principals, ids):
        t = r['tconst']
        role = ROLE.get(r.get('category'))
        if not role:
            continue
        c = credits.setdefault(t, {'d': [], 'a': []})
        n = r.get('nconst')
        if role == 'a' and len(c['a']) >= CAST_PER_TITLE:
            continue
        if n and n not in c[role]:
            c[role].append(n)
    wanted = {n for c in credits.values() for lst in c.values() for n in lst}
    label = {}
    for r in tsv(names, wanted):
        n = r['nconst']
        if r.get('primaryName') not in (None, '', r'\N'):
            label[n] = r['primaryName']
    # Most-credited names first keeps common indexes short.
    count = {}
    for c in credits.values():
        for lst in c.values():
            for n in lst:
                if n in label:
                    count[n] = count.get(n, 0) + 1
    order = sorted(count, key=lambda n: (-count[n], label[n]))
    index = {n: i for i, n in enumerate(order)}
    out = {'names': [label[n] for n in order], 'd': {}, 'a': {}}
    for t in sorted(credits):
        for role in ('d', 'a'):
            lst = [index[n] for n in credits[t][role] if n in index]
            if lst:
                out[role][t] = lst
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--principals', required=True)
    p.add_argument('--names', required=True)
    p.add_argument('--movies', default=str(ROOT / 'Australian_Movies_Android.html'))
    p.add_argument('--tv', default=str(ROOT / 'TV_Shows_Android.html'))
    p.add_argument('--out', default=str(ROOT / '_site' / 'people.json'))
    p.add_argument('--min-titles', type=int, default=1000, help='fail if fewer titles get credits')
    a = p.parse_args()
    ids = title_ids(a.movies, True) | title_ids(a.tv, False)
    out = build(a.principals, a.names, ids)
    covered = len(set(out['d']) | set(out['a']))
    print(f'people.json: {len(out["names"]):,} names, credits for {covered:,} of {len(ids):,} titles')
    if covered < a.min_titles:
        raise SystemExit(f'Only {covered} titles have credits (expected {a.min_titles}+); not writing')
    dest = pathlib.Path(a.out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, separators=(',', ':'), ensure_ascii=False), encoding='utf-8')


if __name__ == '__main__':
    main()
