#!/usr/bin/env python3
"""Fetch titles newly added to Australian subscription streaming services.

Source: the Streaming Availability API by Movie of the Night (official API, free plan
1,000 requests a month). Docs: https://docs.movieofthenight.com/resource/changes
No scraping: this only calls the documented JSON API with the user's own key.

The key comes from the CI/CD variable STREAMING_AVAILABILITY_API_KEY (key from
https://developers.movieofthenight.com/). A RapidAPI key also works if it is saved as
RAPIDAPI_KEY instead. With no key the script exits 0 and leaves any cached file alone,
so the rest of the build still runs.

The /changes endpoint only reaches 31 days back, so every run fetches the whole window
again; nothing has to be committed back to the repo. The result is written to --out
(default cache/new_streaming.json, kept between pipelines by the GitLab CI cache).

Request budget: 1 call for the AU service list plus at most --max-pages calls (25
changes a page). If --out is younger than --max-age-days the script does nothing, so
ordinary code pushes reuse the cached data instead of spending requests; scheduled and
manual pipelines pass --force.

Usage: python tools/fetch_new_streaming.py [--out cache/new_streaming.json]
       [--force] [--max-age-days 13] [--max-pages 80] [--days 31]
"""
import argparse
import datetime as dt
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
DIRECT = ('https://api.movieofthenight.com/v4', 'X-API-Key')
RAPID = ('https://streaming-availability.p.rapidapi.com', 'X-RapidAPI-Key')
COUNTRY = 'au'


class Stop(Exception):
    """The API refused (quota, auth); stop making requests."""


def api(base, header, key, path, params, log):
    url = f'{base}{path}?{urllib.parse.urlencode(params)}'
    headers = {header: key, 'Accept': 'application/json', 'User-Agent': 'movie-finder-refresh/1.0'}
    if header == RAPID[1]:
        headers['X-RapidAPI-Host'] = 'streaming-availability.p.rapidapi.com'
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=40) as r:
                log['requests'] += 1
                return json.load(r)
        except urllib.error.HTTPError as e:
            log['requests'] += 1
            if e.code in (401, 403, 429):
                raise Stop(f'HTTP {e.code} on {path}: {e.read(300).decode("utf-8", "replace")}')
            if e.code >= 500 and attempt < 2:
                time.sleep(5 * (attempt + 1))
                continue
            raise Stop(f'HTTP {e.code} on {path}')
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < 2:
                time.sleep(5 * (attempt + 1))
                continue
            raise Stop(f'Network error on {path}: {e}')


def pick_image(image_set):
    for kind in ('verticalPoster', 'verticalBackdrop', 'horizontalPoster'):
        imgs = (image_set or {}).get(kind) or {}
        for size in ('w240', 'w360', 'w480', 'w300', 'w600'):
            if imgs.get(size):
                return imgs[size]
    return None


def compact_show(s):
    is_series = s.get('showType') == 'series'
    return {
        'id': s.get('id'),
        'imdbId': s.get('imdbId') if str(s.get('imdbId', '')).startswith('tt') else None,
        'title': s.get('title') or s.get('originalTitle') or 'Untitled',
        'type': 'series' if is_series else 'movie',
        'year': s.get('firstAirYear') if is_series else s.get('releaseYear'),
        'lastYear': s.get('lastAirYear') if is_series else None,
        'seasons': s.get('seasonCount') if is_series else None,
        'genres': [g.get('name') for g in s.get('genres') or [] if g.get('name')][:4],
        'overview': (s.get('overview') or '').strip()[:400] or None,
        'poster': pick_image(s.get('imageSet')),
        'cast': (s.get('cast') or [])[:3],
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--out', default=str(ROOT / 'cache/new_streaming.json'))
    p.add_argument('--force', action='store_true', help='Fetch even if the cached file is fresh')
    p.add_argument('--max-age-days', type=float, default=13)
    p.add_argument('--max-pages', type=int, default=80, help='Most /changes pages per run (25 changes each)')
    p.add_argument('--days', type=int, default=31, help='How far back to look (the API allows up to 31)')
    a = p.parse_args()
    out = pathlib.Path(a.out)

    if out.exists() and not a.force:
        try:
            age = (time.time() - json.loads(out.read_text())['fetchedAtUnix']) / 86400
        except (ValueError, KeyError):
            age = 999
        if age < a.max_age_days:
            print(f'new-on-streaming: cached data is {age:.1f} days old, not fetching (use --force)')
            return

    if os.environ.get('STREAMING_AVAILABILITY_API_KEY'):
        base, header = os.environ.get('STREAMING_API_BASE', DIRECT[0]), DIRECT[1]  # base override is for tests
        key = os.environ['STREAMING_AVAILABILITY_API_KEY'].strip()
    elif os.environ.get('RAPIDAPI_KEY'):
        base, header = RAPID
        key = os.environ['RAPIDAPI_KEY'].strip()
    else:
        print('new-on-streaming: no STREAMING_AVAILABILITY_API_KEY set, skipping fetch '
              '(the page will say it is not set up yet)')
        return

    log = {'requests': 0}
    now = int(time.time())
    since = now - min(a.days, 31) * 86400 + 3600  # stay safely inside the 31-day limit
    try:
        country = api(base, header, key, f'/countries/{COUNTRY}', {'output_language': 'en'}, log)
        services = []
        for svc in country.get('services') or []:
            if (svc.get('streamingOptionTypes') or {}).get('subscription'):
                services.append({'id': svc['id'], 'name': svc.get('name') or svc['id'],
                                 'color': svc.get('themeColorCode'), 'home': svc.get('homePage')})
        if not services:
            raise Stop('No AU subscription services in /countries response')
        catalogs = ','.join(f"{s['id']}.subscription" for s in services[:32])

        shows, entries, pages, truncated = {}, [], 0, []
        for item_type in ('show', 'season'):
            cursor = None
            while True:
                if pages >= a.max_pages:
                    truncated.append(item_type)
                    break
                params = {'country': COUNTRY, 'change_type': 'new', 'item_type': item_type,
                          'catalogs': catalogs, 'from': since, 'to': now, 'order_direction': 'desc',
                          'output_language': 'en'}
                if cursor:
                    params['cursor'] = cursor
                page = api(base, header, key, '/changes', params, log)
                pages += 1
                for sid, show in (page.get('shows') or {}).items():
                    shows.setdefault(sid, compact_show(show))
                for c in page.get('changes') or []:
                    if c.get('streamingOptionType') != 'subscription' or not c.get('timestamp'):
                        continue
                    entries.append({'show': c.get('showId'), 'service': (c.get('service') or {}).get('id'),
                                    'item': c.get('itemType'), 'season': c.get('season'),
                                    'ts': c['timestamp'], 'link': c.get('link')})
                if not page.get('hasMore') or not page.get('nextCursor'):
                    break
                cursor = page['nextCursor']
    except Stop as e:
        print(f'new-on-streaming: fetch stopped: {e}', file=sys.stderr)
        if out.exists():
            print('new-on-streaming: keeping the previous cached data', file=sys.stderr)
        else:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps({'error': str(e)[:300], 'fetchedAtUnix': 0}))
        return

    data = {
        'source': 'Streaming Availability API by Movie of the Night',
        'sourceUrl': 'https://www.movieofthenight.com/about/api',
        'country': COUNTRY,
        'fetchedAt': dt.datetime.fromtimestamp(now, dt.timezone.utc).isoformat(timespec='seconds'),
        'fetchedAtUnix': now,
        'windowFromUnix': since,
        'requests': log['requests'],
        'truncated': truncated,
        'services': services,
        'shows': {sid: s for sid, s in shows.items() if any(e['show'] == sid for e in entries)},
        'changes': entries,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')))
    tmp.replace(out)
    print(json.dumps({'requests': log['requests'], 'services': len(services), 'changes': len(entries),
                      'shows': len(data['shows']), 'truncated': truncated}))


if __name__ == '__main__':
    main()
