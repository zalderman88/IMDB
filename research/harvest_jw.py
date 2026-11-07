import datetime
from zoneinfo import ZoneInfo
"""Cache the AU movie catalogue without service or rating restrictions."""
import concurrent.futures
import json
import pathlib
import queue
import threading
import time

from fetch_movies import request

BASE = pathlib.Path(__file__).parent
CACHE = BASE / 'jw_global'
CACHE.mkdir(exist_ok=True)
QUERY = '''query Catalogue($after:String,$lo:Int!,$hi:Int!) {
  popularTitles(country:AU,first:100,after:$after,sortBy:POPULAR,
    filter:{objectTypes:[MOVIE],releaseYear:{min:$lo,max:$hi}}) {
    totalCount pageInfo {hasNextPage endCursor}
    edges { node { id objectType content(country:AU,language:en) {
      title originalTitle originalReleaseYear runtime fullPath
      genres {shortName} productionCountries externalIds {imdbId}
      scoring {imdbScore imdbVotes tomatoMeter certifiedFresh}
    } offers(country:AU,platform:WEB,filter:{
      packages:["nfx","prv","pmp","stn","dnp","mxx","atp"],
      monetizationTypes:[FLATRATE]}) {
      standardWebURL monetizationType package {shortName}
    } } }
  }
}'''
jobs = queue.Queue()
jobs.put((1800, datetime.datetime.now(ZoneInfo('Australia/Perth')).year))
lock = threading.Lock()
nodes = {}
leaves = []
errors = []
started = time.monotonic()

def fetch(lo, hi, page, after):
    path = CACHE / f'{lo}_{hi}_{page:03}.json'
    if path.exists():
        return json.loads(path.read_text())
    for attempt in range(4):
        try:
            result = request(QUERY, {'after':after,'lo':lo,'hi':hi})
            if result.get('errors'):
                raise RuntimeError(str(result['errors']))
            path.write_text(json.dumps(result,ensure_ascii=False))
            return result
        except Exception:
            if attempt == 3:
                raise
            time.sleep(1 + attempt * 2)

def worker():
    while True:
        item = jobs.get()
        try:
            if item is None:
                return
            lo, hi = item
            result = fetch(lo, hi, 1, None)['data']['popularTitles']
            total = result['totalCount']
            if total > 1100 and lo < hi:
                mid = (lo + hi) // 2
                jobs.put((lo,mid));jobs.put((mid+1,hi))
                continue
            found = {e['node']['id']:e['node'] for e in result['edges']}
            page = 1
            cursor = result['pageInfo']['endCursor']
            while result['pageInfo']['hasNextPage']:
                page += 1
                result = fetch(lo,hi,page,cursor)['data']['popularTitles']
                for e in result['edges']:
                    found[e['node']['id']] = e['node']
                next_cursor = result['pageInfo']['endCursor']
                if cursor == next_cursor or not result['edges']:
                    raise RuntimeError(f'Pagination stalled for {lo}-{hi}')
                cursor = next_cursor
            record={'min':lo,'max':hi,'expected':total,'retrieved':len(found),'pages':page,'complete':len(found)==total}
            with lock:
                nodes.update(found);leaves.append(record)
                print(json.dumps({'leaf':record,'totalRetrieved':len(nodes),'seconds':round(time.monotonic()-started)}),flush=True)
        except Exception as exc:
            with lock:
                errors.append({'range':item,'error':str(exc)})
                print(json.dumps({'ERROR':errors[-1]}),flush=True)
        finally:
            jobs.task_done()

with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    workers = [pool.submit(worker) for _ in range(2)]
    jobs.join()
    for _ in workers:jobs.put(None)
    for f in workers:f.result()

out={'scope':'JustWatch AU movie catalogue, all rating levels and all services, release years 1800–2026',
     'complete':not errors and all(x['complete'] for x in leaves),'leaves':leaves,'errors':errors,'movies':list(nodes.values())}
(BASE/'jw_global_movies.json').write_text(json.dumps(out,ensure_ascii=False))
print(json.dumps({'finished':True,'complete':out['complete'],'count':len(nodes),'errors':errors}),flush=True)
