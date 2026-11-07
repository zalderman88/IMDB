import concurrent.futures
import json
import pathlib
import time
import ast
module=ast.parse((pathlib.Path(__file__).parent/"harvest_jw.py").read_text())
QUERY=next(ast.literal_eval(node.value) for node in module.body if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="QUERY" for t in node.targets))
from fetch_movies import request

BASE=pathlib.Path(__file__).parent
root=json.loads((BASE/'jw_global_movies.json').read_text())
years=sorted({e['range'][0] for e in root['errors']})
QUERY=QUERY.replace('releaseYear:{min:$lo,max:$hi}', 'releaseYear:{min:$lo,max:$hi},imdbVotes:{min:1000}')
CACHE=BASE/'jw_1k';CACHE.mkdir(exist_ok=True)

def fetch_year(year):
    nodes={};after=None;page=0;expected=None
    while True:
        page+=1;path=CACHE/f'{year}_{page:03}.json'
        if path.exists():d=json.loads(path.read_text())
        else:
            for attempt in range(3):
                try:
                    d=request(QUERY,{'lo':year,'hi':year,'after':after})
                    if d.get('errors'):raise ValueError(str(d['errors']))
                    path.write_text(json.dumps(d,ensure_ascii=False));break
                except Exception:
                    if attempt==2:raise
                    time.sleep(attempt+1)
        pop=d['data']['popularTitles'];expected=pop['totalCount'] if expected is None else expected
        for e in pop['edges']:nodes[e['node']['id']]=e['node']
        if not pop['pageInfo']['hasNextPage']:break
        cursor=pop['pageInfo']['endCursor']
        if cursor==after or not pop['edges']:raise ValueError(f'Pagination stalled {year}')
        after=cursor
    record={'year':year,'expected':expected,'retrieved':len(nodes),'complete':len(nodes)==expected}
    print(json.dumps(record),flush=True);return record

with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
    results=list(ex.map(fetch_year,years))
(BASE/'jw_1k_manifest.json').write_text(json.dumps(results))
