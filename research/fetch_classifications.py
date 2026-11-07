import concurrent.futures
import json
import pathlib
import time
from fetch_movies import request

BASE=pathlib.Path(__file__).parent
CACHE=BASE/'classifications';CACHE.mkdir(exist_ok=True)
selected={m['id'] for m in json.loads((BASE/'extended_catalogue.json').read_text())['movies']}
jw={}
for node in json.loads((BASE/'jw_consolidated.json').read_text())['movies']:
    iid=(node['content'].get('externalIds') or {}).get('imdbId')
    ident='imdb:'+iid if iid else 'jw:'+node['id']
    if ident in selected:jw[node['id']]=ident

ids=sorted(jw)
batches=[ids[i:i+100] for i in range(0,len(ids),100)]
print(json.dumps({'titles':len(ids),'batches':len(batches)}),flush=True)

def fetch_batch(item):
    index,ids=item;path=CACHE/f'batch_{index:04}.json'
    if path.exists():return json.loads(path.read_text())
    query='query { '+' '.join(f'n{i}:node(id:{json.dumps(mid)}) {{ id ... on Movie {{ content(country:AU,language:en) {{ title ageCertification externalIds {{imdbId}} }} }} }}' for i,mid in enumerate(ids))+' }'
    for attempt in range(3):
        try:
            d=request(query)
            if d.get('errors'):raise ValueError(str(d['errors']))
            path.write_text(json.dumps(d,ensure_ascii=False))
            return d
        except Exception:
            if attempt==2:raise
            time.sleep(attempt+1)

classification={};done=0
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
    for d in ex.map(fetch_batch,enumerate(batches)):
        for n in (d.get('data') or {}).values():
            if not n or not n.get('content'):continue
            classification[n['id']]={'id':jw[n['id']],'classification':n['content'].get('ageCertification')}
        done+=1
        if done%10==0:print(json.dumps({'batchesDone':done,'batches':len(batches),'titles':len(classification)}),flush=True)

(BASE/'classification_movies.json').write_text(json.dumps(classification,ensure_ascii=False))
print(json.dumps({'finished':True,'titles':len(classification),'known':sum(bool(n['classification']) for n in classification.values())}),flush=True)
