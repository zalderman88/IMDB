"""Shared catalogue clean-up rules (Zac, 7 Nov 2026). Used by the movie, TV and For You builders.

1. Title types: movies keep IMDb `movie` and `tvMovie` only. Shorts, TV shorts, videos and
   TV specials are dropped from the published data entirely.
2. India is always excluded. A film is Indian if JustWatch lists India as a production
   country. When JustWatch has no country: Wikidata's country of origin includes India, or
   IMDb's alternative-title data has the Indian pattern below and the recorded original
   language is unknown or an Indian language. TV (no JustWatch data) uses Wikidata only,
   because IMDb gives every TV series the same Indian alternative titles.
3. Suspicious ratings are dropped: IMDb 8.5+ from under 10,000 votes with no Rotten
   Tomatoes score, and films no other source can confirm (no JustWatch country, no RT score,
   no recorded language) unless they have 25,000+ IMDb votes.
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
INDIA_TITLES = ROOT / 'research/imdb/india_titles.json'

MOVIE_KINDS = {'movie', 'tvMovie'}
INDIAN_LANGUAGES = {'Hindi', 'Tamil', 'Telugu', 'Malayalam', 'Kannada', 'Marathi', 'Bangla', 'Bengali',
                    'Punjabi', 'Gujarati', 'Odia', 'Assamese', 'Bhojpuri', 'Tulu', 'Konkani'}
SUSPECT_SCORE, SUSPECT_VOTES = 8.5, 10000
UNCONFIRMED_VOTES = 25000


def akas_pattern(regions):
    """True when IMDb alternative titles look like an Indian release.

    `regions` maps region code -> number of alternative titles. IMDb adds one generic
    English title for AU/CA/GB/IE/IN/NZ/US/ZA to almost everything, so a single IN title means
    nothing. Indian films typically carry two or more IN titles (an Indian-language one) and
    few other regions; Hollywood films also have several IN titles (dubs) but 30+ regions.
    Checked against 22,000 films with a known JustWatch country: 95% of flagged films are Indian.
    """
    india = regions.get('IN', 0)
    spread = len([r for r in regions if r not in ('\\N', 'XWW', 'XWG')])
    return (india >= 3 and spread < 30) or (india >= 2 and spread < 15)


class India:
    def __init__(self, path=INDIA_TITLES):
        path = pathlib.Path(path)
        data = json.loads(path.read_text()) if path.exists() else {}
        self.wikidata = set(data.get('wikidata', []))
        self.akas = set(data.get('akas', []))


def load_india(path=INDIA_TITLES):
    return India(path)


def num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def is_indian(m, india):
    """m: movie record from the builder (countries, languageLabels, id)."""
    countries = m.get('countries') or []
    if 'IN' in countries:
        return True
    if countries:
        return False
    iid = m['id'].split(':', 1)[1] if str(m.get('id', '')).startswith('imdb:') else m.get('imdbId')
    if iid in india.wikidata:
        return True
    if iid not in india.akas:
        return False
    langs = set(m.get('languageLabels') or [])
    return not langs or bool(langs & INDIAN_LANGUAGES)


def has_rt(m):
    return num(m.get('critics')) or num(m.get('audience'))


def suspicious(m):
    return num(m.get('score')) and m['score'] >= SUSPECT_SCORE and (m.get('votes') or 0) < SUSPECT_VOTES and not has_rt(m)


def unconfirmed(m):
    return (not m.get('countries') and not has_rt(m) and (m.get('languageGroup') or 'unknown') == 'unknown'
            and (m.get('votes') or 0) < UNCONFIRMED_VOTES)


def drop_reason(m, india):
    """Why a movie is left out of the published data, or None to keep it."""
    if (m.get('kind') or 'movie') not in MOVIE_KINDS:
        return 'type'
    if is_indian(m, india):
        return 'india'
    if suspicious(m):
        return 'suspicious'
    if unconfirmed(m):
        return 'unconfirmed'
    return None


def tv_drop_reason(s, india):
    """TV has only IMDb facts: no country, language or RT. Wikidata India list and rating rule."""
    if s.get('id', s.get('imdbId')) in india.wikidata:
        return 'india'
    if num(s.get('score')) and s['score'] >= SUSPECT_SCORE and (s.get('votes') or 0) < SUSPECT_VOTES:
        return 'suspicious'
    return None
