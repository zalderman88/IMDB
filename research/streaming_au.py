"""Live Australian where-to-watch from the TMDB sweep (tools/fetch_tmdb_au.py -> cache/tmdb_au.json).

Used by the movie and TV builders. Returns None when there is no complete sweep (no TMDB key
yet, or the sweep was cut short), so the pages keep the 7 Nov 2026 JustWatch snapshot.
"""
import datetime as dt
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
CACHE = ROOT / 'cache/tmdb_au.json'


def load_live(path=CACHE):
    path = pathlib.Path(path)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except ValueError:
        return None
    if not data.get('complete') or not data.get('titles'):
        return None
    out = {'m': {}, 't': {}}
    imdb = data.get('imdb') or {}
    for key, t in data['titles'].items():
        iid = imdb.get(key)
        if not iid:
            continue
        kind, tmdb_id = key[0], key[1:]
        url = f"https://www.themoviedb.org/{'movie' if kind == 'm' else 'tv'}/{tmdb_id}/watch?locale=AU"
        dest = out[kind].setdefault(iid, {})
        for code in t.get('on') or {}:
            dest.setdefault(code, url)
    when = dt.datetime.fromtimestamp(data['fetchedAtUnix'], dt.timezone.utc).astimezone(
        dt.timezone(dt.timedelta(hours=8))).date()
    return {'movies': out['m'], 'tv': out['t'], 'date': when,
            'label': f'{when.day} {when:%B %Y}', 'providers': data.get('providers') or {}}
