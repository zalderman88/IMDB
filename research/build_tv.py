"""Build the offline TV finder (TV_Shows_Android.html) from research/imdb/tv_1k.json.

Inclusion (Zac, 7 Nov 2026): TV series or miniseries with 1,000+ IMDb votes that
  * have IMDb 6.0+ and aired in 2020 or later (first aired 2020+, or started earlier but
    has an end year or an episode released in 2020 or later), or
  * first aired in 2000 or later and have IMDb above 8.0.
No network access. Facts other than IMDb's are not collected for TV.
"""
import argparse
import datetime
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'research/imdb/tv_1k.json'
SNAPSHOT = ROOT / 'research/tv_snapshot.json'
TEMPLATE = ROOT / 'research/tv_finder_template.html'
sys.path.insert(0, str(ROOT / 'research'))
from title_quality import SUSPECT_SCORE, SUSPECT_VOTES, load_india, tv_drop_reason  # noqa: E402
from streaming_au import load_live  # noqa: E402
OUT = ROOT / 'TV_Shows_Android.html'
EXTRACT = ROOT / 'research/tv_catalogue.json'

MIN_VOTES = 1000
RECENT_YEAR, RECENT_SCORE = 2020, 6.0
ACCLAIMED_START, ACCLAIMED_ABOVE = 2000, 8.0
DEFAULT_EXCLUDED = {'Romance', 'Horror', 'Documentary'}
# Same broad groups as the movie finder, plus two TV-only ones. Keep in step with the template.
GROUP_RULES = [('Action & adventure', r'\b(action|adventure)\b'), ('Animation', r'animat|anime'),
               ('Comedy', r'comedy|comic|satire|slapstick'), ('Crime & thriller', r'crime|thriller|mystery|noir|suspense|detective'),
               ('Documentary', r'documentar|non[ -]?fiction'), ('Drama & biography', r'drama|biograph'),
               ('Family', r'family|children|kids'), ('Fantasy', r'fantasy'),
               ('History & war', r'\b(war|history|historical|military|period)\b'), ('Horror', r'horror'),
               ('Music & musicals', r'music|concert'), ('Reality & game shows', r'reality|game[ -]?show'),
               ('Romance', r'romance|romantic'), ('Science fiction', r'sci[ -]?fi|science[ -]?fiction'),
               ('Sport', r'sport'), ('Talk & news', r'talk[ -]?show|\bnews\b'), ('Western', r'western')]


def groups(genres):
    out = set()
    for g in genres:
        text = g.lower()
        hits = {name for name, pattern in GROUP_RULES if re.search(pattern, text)}
        out |= hits or {'Other'}
    return out


def last_year(s):
    years = [y for y in (s['startYear'], s.get('endYear'), s.get('lastEpisodeYear')) if y]
    return max(years)


def routes(s):
    votes_ok = (s.get('votes') or 0) >= MIN_VOTES
    score = s.get('score') or 0
    recent = votes_ok and score >= RECENT_SCORE and last_year(s) >= RECENT_YEAR
    acclaimed = votes_ok and score > ACCLAIMED_ABOVE and s['startYear'] >= ACCLAIMED_START
    return recent, acclaimed


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', default=str(SOURCE))
    p.add_argument('--snapshot', default=str(SNAPSHOT))
    p.add_argument('--out', default=str(OUT))
    p.add_argument('--extract', default=str(EXTRACT))
    p.add_argument('--min-shows', type=int, default=0, help='Fail if fewer shows qualify (guards a broken download)')
    a = p.parse_args()
    source, snapshot = pathlib.Path(a.source), pathlib.Path(a.snapshot)
    if not source.exists():
        raise SystemExit('research/imdb/tv_1k.json is missing. Run python tools/refresh_tv.py first '
                         '(downloads IMDb official datasets).')
    shows = json.loads(source.read_text())
    snap = json.loads(snapshot.read_text()) if snapshot.exists() else {}
    asof = datetime.date.fromisoformat(snap.get('imdbAsOf', '2026-11-07'))

    india = load_india()
    live = load_live()  # where-to-watch from the TMDB sweep, when a complete one exists
    dropped = {'india': 0, 'suspicious': 0}
    selected = []
    for s in shows:
        if s.get('adult'):
            continue
        recent, acclaimed = routes(s)
        if not (recent or acclaimed):
            continue
        reason = tv_drop_reason(s, india)
        if reason:
            dropped[reason] += 1
            continue
        rec = {'id': s['imdbId'], 'title': s['title'], 'type': s['type'], 'startYear': s['startYear'],
               'endYear': s.get('endYear'), 'lastYear': last_year(s), 'seasons': s.get('seasons') or 0,
               'seasonsSince2020': s.get('seasonsSince2020') or 0, 'episodes': s.get('episodes') or 0,
               'runtime': s.get('runtime'), 'genres': s.get('genres') or [], 'score': s['score'], 'votes': s['votes'],
               'imdb': 'https://www.imdb.com/title/' + s['imdbId'] + '/', 'recent': recent, 'acclaimed': acclaimed}
        if s.get('originalTitle') and s['originalTitle'] != s['title']:
            rec['originalTitle'] = s['originalTitle']
        if live:
            rec['offers'] = {c: u for c, u in sorted(live['tv'].get(s['imdbId'], {}).items()) if c not in ('fxn', 'bbx', 'shd')}
        selected.append(rec)
    selected.sort(key=lambda r: (-r['score'], -r['votes'], r['title']))
    if len(selected) < a.min_shows:
        raise SystemExit(f'Only {len(selected):,} TV shows qualified (minimum {a.min_shows:,}); not publishing.')

    default = [r for r in selected if (g := groups(r['genres'])) and not g & DEFAULT_EXCLUDED]
    suspect = dropped['suspicious']
    recent_n = sum(r['recent'] for r in selected)
    acclaimed_only = sum(r['acclaimed'] and not r['recent'] for r in selected)
    checked = f'{asof.day} {asof:%B %Y}'
    meta = {
        'imdbAsOf': asof.isoformat(), 'total': len(selected), 'defaultResults': len(default),
        'streamingLive': live['label'] if live else None,
        'recent': recent_n, 'acclaimedOnly': acclaimed_only, 'suspectHidden': suspect, 'indiaDropped': dropped['india'],
        'rules': {'minVotes': MIN_VOTES, 'recentYear': RECENT_YEAR, 'recentMinScore': RECENT_SCORE,
                  'acclaimedStartYear': ACCLAIMED_START, 'acclaimedScoreAbove': ACCLAIMED_ABOVE},
        'coverageText': (f'IMDb data checked {checked}: {len(shows):,} TV series and miniseries with at least '
                         f'1,000 votes were read. {recent_n:,} aired in 2020 or later with IMDb 6.0+, and '
                         f'{acclaimed_only:,} more are listed only because they first aired in 2000 or later with IMDb '
                         f'above 8.0. Left out entirely: {dropped["india"]:,} Indian shows (Wikidata country of origin) '
                         f'and {suspect:,} likely vote-stuffed shows (IMDb {SUSPECT_SCORE}+ from under {SUSPECT_VOTES:,} votes). '
                         f'With the default genre exclusions, {len(default):,} shows are listed.'),
        'coverageRows': [['IMDb TV series/miniseries read (1,000+ votes)', len(shows)],
                         ['Aired 2020 or later, IMDb 6.0+', recent_n],
                         ['Listed only as acclaimed (2000+, above 8.0)', acclaimed_only],
                         ['Shows in this file', len(selected)],
                         ['Left out: Indian shows', dropped['india']],
                         ['Left out: IMDb 8.5+ from under 10,000 votes', suspect],
                         ['Results with the default exclusions', len(default)]],
        'refreshText': ('IMDb ratings, votes and episode years refresh automatically twice a week (Tuesday and '
                        'Friday, around 4:00 am Perth time) from IMDb\'s official datasets.'),
        'sources': {'imdbBasics': 'https://datasets.imdbws.com/title.basics.tsv.gz',
                    'imdbRatings': 'https://datasets.imdbws.com/title.ratings.tsv.gz',
                    'imdbEpisode': 'https://datasets.imdbws.com/title.episode.tsv.gz',
                    'imdbDocs': 'https://developer.imdb.com/non-commercial-datasets/'}}

    start_years = [r['startYear'] for r in selected] or [ACCLAIMED_START]
    last_years = [r['lastYear'] for r in selected] or [RECENT_YEAR]
    html = TEMPLATE.read_text()
    if live:
        html = html.replace('Australian streaming services, Rotten Tomatoes scores', 'Rotten Tomatoes scores').replace(
            '<p><strong>Not covered yet.</strong>',
            f'<p><strong>Where to watch</strong> on Australian subscription services was updated {live["label"]} '
            f'from TMDB (JustWatch data), and refreshes with each scheduled build.</p><p><strong>Not covered yet.</strong>', 1)
    data = json.dumps(selected, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
    for k, v in {'@@MINYEAR@@': min(start_years), '@@MAXYEAR@@': max(max(start_years), max(last_years)),
                 '@@LASTMIN@@': min(last_years), '@@CHECKED@@': checked,
                 '@@META@@': json.dumps(meta, ensure_ascii=False).replace('</', '<\\/'), '@@DATA@@': data}.items():
        html = html.replace(k, str(v))
    pathlib.Path(a.out).write_text(html)
    pathlib.Path(a.extract).write_text(json.dumps({'metadata': meta, 'shows': selected}, ensure_ascii=False) + '\n')
    print(json.dumps({k: meta[k] for k in ('imdbAsOf', 'total', 'defaultResults', 'recent', 'acclaimedOnly', 'suspectHidden')}))


if __name__ == '__main__':
    main()
