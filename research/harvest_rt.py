import datetime
from zoneinfo import ZoneInfo
"""Collect movie metadata from the public Rotten Tomatoes title search."""
import concurrent.futures
import json
import pathlib
import queue
import re
import threading
import time
import urllib.request

BASE=pathlib.Path(__file__).parent
CACHE=BASE/'rt_years';CACHE.mkdir(exist_ok=True)
config=json.loads(re.search(r'"algoliaSearch":(\{[^}]+\})',(BASE/'rt_browse.html').read_text()).group(1))
URL='https://'+config['aId'].lower()+'-dsn.algolia.net/1/indexes/content_rt/query'
HEADERS={'Content-Type':'application/json','x-algolia-application-id':config['aId'],'x-algolia-api-key':config['sId']}
ATTRS=['emsId','type','title','titles','vanity','releaseYear','genres','runTime','rottenTomatoes','aka']
jobs=queue.Queue();jobs.put((1800,datetime.datetime.now(ZoneInfo('Australia/Perth')).year))
lock=threading.Lock();nodes={};leaves=[];errors=[];started=time.monotonic()

def fetch(lo,hi):
    path=CACHE/f'{lo}_{hi}.json'
    if path.exists():return json.loads(path.read_text())
    payload={'query':'','filters':f'isEmsSearchable = 1 AND type:movie AND releaseYear >= {lo} AND releaseYear <= {hi}',
             'hitsPerPage':1000,'attributesToHighlight':[],'attributesToRetrieve':ATTRS}
    for attempt in range(4):
        try:
            req=urllib.request.Request(URL,data=json.dumps(payload).encode(),headers=HEADERS)
            with urllib.request.urlopen(req,timeout=40) as r:result=json.load(r)
            path.write_text(json.dumps(result,ensure_ascii=False));return result
        except Exception:
            if attempt==3:raise
            time.sleep(1+attempt*2)

def worker():
    while True:
        item=jobs.get()
        try:
            if item is None:return
            lo,hi=item;d=fetch(lo,hi)
            if d['nbHits']>1000 and lo<hi:
                mid=(lo+hi)//2;jobs.put((lo,mid));jobs.put((mid+1,hi));continue
            record={'min':lo,'max':hi,'totalSearchMatches':d['nbHits'],'retrieved':len(d['hits']),
                    'complete':d['exhaustiveNbHits'] and len(d['hits'])==d['nbHits']}
            with lock:
                for x in d['hits']:
                    old=nodes.get(x['emsId'])
                    if old and x.get('title') not in old.setdefault('titles',[]):old['titles'].append(x['title'])
                    else:nodes[x['emsId']]=x
                leaves.append(record)
                print(json.dumps({'leaf':record,'unique':len(nodes),'seconds':round(time.monotonic()-started)}),flush=True)
        except Exception as exc:
            with lock:errors.append({'range':item,'error':str(exc)});print(json.dumps({'ERROR':errors[-1]}),flush=True)
        finally:jobs.task_done()

with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    fs=[pool.submit(worker) for _ in range(2)];jobs.join()
    for _ in fs:jobs.put(None)
    for f in fs:f.result()

out={'scope':'Rotten Tomatoes public searchable movie records, years 1800–2026; per-year search cap 1000',
     'complete':not errors and all(x['complete'] for x in leaves),'leaves':leaves,'errors':errors,'movies':list(nodes.values())}
(BASE/'rt_movies.json').write_text(json.dumps(out,ensure_ascii=False))
print(json.dumps({'finished':True,'count':len(nodes),'cappedYears':[x for x in leaves if not x['complete']],'errors':errors}),flush=True)
