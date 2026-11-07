"""Checks for an automated IMDb refresh, used instead of the UI-only catalogue lock.

The lock (data/catalogue_lock.json) proves a UI change left movie facts untouched. An IMDb
refresh is meant to change ratings and votes, so this check instead confirms:
  * every film still has at least 1,000 IMDb votes and passes a score/count route;
  * the catalogue did not collapse (a truncated download or broken join);
  * non-IMDb facts (streaming offers, RT, classifications, languages) were not altered.
"""
import json
import pathlib
import re

root = pathlib.Path(__file__).resolve().parent.parent
text = (root / 'Australian_Movies_Android.html').read_text()
data = json.loads(re.search(r'<script id="catalogue"[^>]*>(.*?)</script>', text, re.S).group(1))
lock = json.loads((root / 'data/catalogue_lock.json').read_text())
baseline_path = root / 'data/non_imdb_facts.json'


def passes(m):
    return (m.get('votes') or 0) >= 1000 and ((m.get('score') or 0) >= 6
        or ((m.get('critics') or 0) >= 60 and (m.get('criticCount') or 0) >= 50)
        or ((m.get('audience') or 0) >= 60 and (m.get('audienceCount') or 0) >= 1000))


assert all((m.get('votes') or 0) >= 1000 for m in data), 'Global 1,000 IMDb-vote minimum violated'
assert all(passes(m) for m in data), 'A film no longer passes any score/count route'
assert len(data) >= 0.95 * lock['filmCount'], f'Catalogue shrank from {lock["filmCount"]:,} to {len(data):,}'

KEYS = ('offers', 'rt', 'critics', 'criticCount', 'audience', 'audienceCount', 'certifiedFresh',
        'verifiedHot', 'rtCheckedDate', 'classifications', 'languageGroup')
meta = json.loads(re.search(r'<script id="metadata"[^>]*>(.*?)</script>', text, re.S).group(1))
if meta.get('streamingLive'):
    # Where-to-watch is refreshed from TMDB on purpose, so it is not compared to the baseline.
    KEYS = tuple(k for k in KEYS if k != 'offers')
facts = {m['id']: {k: m.get(k) for k in KEYS} for m in data}
baseline = json.loads(baseline_path.read_text())
changed = [i for i, f in facts.items() if i in baseline and {k: baseline[i].get(k) for k in KEYS} != f]
# A corrected IMDb title/year can legitimately change an RT title match for a handful of films.
assert len(changed) <= 0.01 * len(baseline), f'{len(changed)} films had non-IMDb facts altered, e.g. {changed[:3]}'
if changed:print(f'Warning: {len(changed)} films had non-IMDb facts altered, e.g. {changed[:5]}')
print(json.dumps({'refreshCheck': 'passed', 'films': len(data), 'baselineFilms': lock['filmCount'],
                  'newFilms': sum(i not in baseline for i in facts),
                  'droppedFilms': sum(i not in facts for i in baseline)}))
