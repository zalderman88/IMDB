import asyncio
import collections
import html
import httpx
import json
import pathlib
import time
import urllib.request
from movie_data_utils import aliases,norm,scorecard

BASE=pathlib.Path(__file__).parent
CACHE=BASE/'rt_counts';CACHE.mkdir(exist_ok=True)
raw=json.loads((BASE/'rt_movies.json').read_text())['movies']
imdb=json.loads((BASE/'imdb/movies_1k.json').read_text())
by_id={x['imdbId']:x for x in imdb};idx=collections.defaultdict(set)
for x in imdb:
    for title in aliases(x,'imdb'):
        if norm(title):idx[(norm(title),x['year'])].add(x['imdbId'])

candidates=[]
for m in raw:
    rt=m.get('rottenTomatoes') or {}
    if max(rt.get('criticsScore') or 0,rt.get('audienceScore') or 0)<60:continue
    if set(m.get('genres',[]))&{'Horror','Romance','Documentary'}:continue
    ids=set()
    for t in aliases(m,'rt'):ids.update(idx.get((norm(t),m.get('releaseYear')),set()))
    linked=by_id[next(iter(ids))] if len(ids)==1 else None
    votes=linked['votes'] if linked else 0
    candidates.append((votes,m,linked))

# The public RT search does not provide a full database or review counts.
# Verify a useful, explicit subset; all unchecked counts remain unknown.
core=sorted(candidates,key=lambda x:-x[0])[:2200]
additional=sorted([x for x in candidates if x[2] is not None and x[2]['score']<6],key=lambda x:-x[0])[:600]
recent=sorted([x for x in candidates if x[1].get('releaseYear',0)>=2024 and x[1].get('rottenTomatoes',{}).get('certifiedFresh')],key=lambda x:-x[0])[:350]
selected={x[1]['emsId']:x[1] for x in core+additional+recent}

for slug,file in [('shawshank_redemption','rt_shawshank.html'),('dune_part_two','rt_dune2.html')]:
    try:(CACHE/(slug+'.json')).write_text(json.dumps(scorecard((BASE/file).read_text(),slug),ensure_ascii=False))
    except Exception:pass

async def main():
    start=time.monotonic();done=0;errors=[];sem=asyncio.Semaphore(2);blocked=False
    async with httpx.AsyncClient(timeout=40,trust_env=False,proxy=urllib.request.getproxies().get('https'),
        limits=httpx.Limits(max_connections=2,max_keepalive_connections=2),follow_redirects=True,
        headers={'User-Agent':'Mozilla/5.0','Accept-Encoding':'gzip, deflate'}) as client:
        async def get(m):
            nonlocal done,blocked
            slug=m['vanity'];path=CACHE/(slug+'.json')
            if path.exists():done+=1;return
            async with sem:
                if blocked:return
                for attempt in range(3):
                    try:
                        r=await client.get('https://www.rottentomatoes.com/m/'+slug)
                        if r.status_code in (403,429):
                            blocked=True;errors.append({'vanity':slug,'status':r.status_code});return
                        r.raise_for_status();data=scorecard(r.text,slug);data['emsId']=m['emsId'];data['expectedTitle']=m['title']
                        path.write_text(json.dumps(data,ensure_ascii=False));done+=1
                        if done%100==0:print(json.dumps({'verified':done,'selected':len(selected),'seconds':round(time.monotonic()-start),'errors':len(errors)}),flush=True)
                        return
                    except Exception as e:
                        if attempt==2:errors.append({'vanity':slug,'error':str(e)});return
                        await asyncio.sleep(attempt+1)
        await asyncio.gather(*(get(m) for m in selected.values()))
    manifest={'verified':done,'selected':len(selected),'allQualifyingCandidates':len(candidates),'complete':False,'selection':'2,200 highest IMDb vote counts plus up to 600 IMDb-below-6.0 candidates and 350 recent Certified Fresh candidates; deduplicated','errors':errors}
    (BASE/'rt_count_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False))
    print(json.dumps({'finished':True,**manifest}),flush=True)

asyncio.run(main())
