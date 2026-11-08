import collections
import html
import json
import pathlib
import re
import datetime
from zoneinfo import ZoneInfo
from movie_data_utils import norm,aliases
from title_quality import load_india,drop_reason

BASE=pathlib.Path(__file__).parent
ROOT=BASE.parent
OUT=ROOT/'Australian_Movies_Android.html'
providers={'nfx':'Netflix','prv':'Prime Video','pmp':'Paramount+','stn':'Stan','dnp':'Disney+','mxx':'HBO Max','atp':'Apple TV','bng':'Binge','sbs':'SBS On Demand','abc':'ABC iview'}  # bng/sbs/abc come from the live TMDB sweep
snapshot=json.loads((BASE/'source_snapshot.json').read_text())
today=datetime.date.fromisoformat(snapshot['dataAsOf'])
imdb_asof=datetime.date.fromisoformat(snapshot['imdbAsOf']) if snapshot.get('imdbAsOf') else today
checked_label=f'{today.day} {today:%B %Y}'
imdb=json.loads((BASE/'imdb/movies_1k.json').read_text())
rt_source=json.loads((BASE/'rt_movies.json').read_text())
rt=rt_source['movies']
genre_names=json.loads((ROOT/'genres.json').read_text())
countries_missing_indian={'tt6442436','tt6442694','tt6442774','tt6442766'}
adult_ids={x['imdbId'] for x in imdb if x['adult']}

def genres(values):
    names={'Sci-Fi':'Science fiction','Science-Fiction':'Science fiction','Science Fiction':'Science fiction',
           'Kids & Family':'Family','Kids & family':'Family','War & Military':'War','Mystery & Thriller':'Mystery & thriller',
           'Documentaries':'Documentary','Film-Noir':'Film noir','Reality-TV':'Reality TV','Talk-Show':'Talk show'}
    result=set()
    for value in values:
        if value=='Action & Adventure':result.update(['Action','Adventure'])
        elif value not in ['European','Made in Europe'] and value:result.add(names.get(value,value))
    return sorted(result)

movies={}
for m in imdb:
    if m['adult']:continue
    ident='imdb:'+m['imdbId']
    movies[ident]={'id':ident,'title':m['title'],'originalTitle':m['originalTitle'],'aliases':[],
        'year':m['year'],'runtime':m['runtime'],'genres':genres(m['genres']),'countries':[],
        'score':m['score'],'votes':m['votes'],'imdb':'https://www.imdb.com/title/'+m['imdbId']+'/',
        'rt':None,'critics':None,'criticCount':None,'audience':None,'audienceCount':None,
        'certifiedFresh':False,'verifiedHot':False,'offers':{},'kind':m['type']}

# Include every cached page, including valid pages before a catalogue pagination cap.
jw={node['id']:node for node in json.loads((BASE/'jw_consolidated.json').read_text())['movies']}

official=set(movies)
for node in jw.values():
    c=node['content'];imdb_id=(c.get('externalIds') or {}).get('imdbId')
    if imdb_id in adult_ids:continue
    ident='imdb:'+imdb_id if imdb_id else 'jw:'+node['id']
    if re.match(r'^(?:WWE|UFC|AEW|NXT)(?:\s|:)',c['title']):continue
    g=genres([genre_names.get(x['shortName'],x['shortName']) for x in c.get('genres',[])])
    scoring=c.get('scoring') or {}
    if ident not in movies:
        movies[ident]={'id':ident,'title':c['title'],'originalTitle':c.get('originalTitle'),'aliases':[],
            'year':c.get('originalReleaseYear'),'runtime':c.get('runtime'),'genres':g,'countries':[],
            'score':scoring.get('imdbScore'),'votes':scoring.get('imdbVotes'),
            'imdb':'https://www.imdb.com/title/'+imdb_id+'/' if imdb_id else None,
            'rt':None,'critics':None,'criticCount':None,'audience':None,'audienceCount':None,
            'certifiedFresh':False,'verifiedHot':False,'offers':{},'kind':'movie'}
    m=movies[ident]
    for alias in [c['title'],c.get('originalTitle')]:
        if alias and alias not in {m['title'],m.get('originalTitle')} and alias not in m['aliases']:m['aliases'].append(alias)
    if not m['genres']:m['genres']=g
    else:m['genres']=sorted(set(m['genres'])|({'Horror','Romance','Documentary'}&set(g)))
    m['countries']=sorted(set(m['countries'])|set(c.get('productionCountries') or []))
    if imdb_id in countries_missing_indian:m['countries']=sorted(set(m['countries'])|{'IN'})
    m['info']='https://www.justwatch.com'+c['fullPath']
    if not m.get('runtime'):m['runtime']=c.get('runtime')
    if m.get('year') is None:m['year']=c.get('originalReleaseYear')
    # Keep IMDb's bulk ratings authoritative where present.
    if ident not in official:
        m['score']=scoring.get('imdbScore');m['votes']=scoring.get('imdbVotes')
    if m.get('critics') is None:m['critics']=scoring.get('tomatoMeter')
    m['certifiedFresh']=bool(scoring.get('certifiedFresh'))
    for offer in node.get('offers',[]):
        code=offer['package']['shortName']
        if code in providers and offer['monetizationType']=='FLATRATE':
            m['offers'][code]=html.unescape(offer['standardWebURL'])

# Live where-to-watch (TMDB watch providers, refreshed each scheduled build) replaces the
# 7 Nov 2026 JustWatch offers when a complete sweep exists. JustWatch deep links are kept for
# services that still list the film; other services link to TMDB's AU watch page.
from streaming_au import load_live
live=load_live()
if live:
    for m in movies.values():
        iid=m['id'][5:] if m['id'].startswith('imdb:') else None
        now_on=live['movies'].get(iid,{}) if iid else {}
        m['offers']={c:(m['offers'].get(c) or url) for c,url in sorted(now_on.items()) if c in providers}

idx=collections.defaultdict(set)
for ident,m in movies.items():
    for title in [m['title'],m.get('originalTitle')]+m['aliases']:
        if norm(title):idx[(norm(title),m.get('year'))].add(ident)

rt_counts={}
for path in (BASE/'rt_counts').glob('*.json'):
    c=json.loads(path.read_text())
    if c.get('countVerified'):rt_counts[c['vanity']]=c

mapped=collections.defaultdict(list);unmatched=[];ambiguous=0
for m in rt:
    if not m.get('vanity'):continue
    hits=set()
    for title in aliases(m,'rt'):
        hits.update(idx.get((norm(title),m.get('releaseYear')),set()))
    if len(hits)==1:mapped[next(iter(hits))].append(m)
    elif not hits:unmatched.append(m)
    else:ambiguous+=1

def attach(movie,r):
    scoring=r.get('rottenTomatoes') or {}
    movie['rt']='https://www.rottentomatoes.com/m/'+r['vanity']
    movie['rtId']=r['emsId']
    movie['critics']=scoring.get('criticsScore')
    movie['audience']=scoring.get('audienceScore')
    movie['certifiedFresh']=bool(scoring.get('certifiedFresh'))
    movie['verifiedHot']=bool(scoring.get('verifiedHot'))
    movie['genres']=sorted(set(movie.get('genres') or genres(r.get('genres',[])))|({'Horror','Romance','Documentary'}&set(genres(r.get('genres',[])))))
    if r['vanity'] in rt_counts:
        count=rt_counts[r['vanity']]
        for key in ['critics','criticCount','audience','audienceCount','audienceCountText','audienceBanded','audienceType','certifiedFresh','verifiedHot','criticsUrl','audienceUrl']:
            movie[key]=count.get(key)
        movie['rtCountsChecked']=True
        movie['rtCheckedDate']=count.get('checked')

for ident,candidates in mapped.items():
    if len({x['emsId'] for x in candidates})>1:
        checked=[x for x in candidates if x['vanity'] in rt_counts]
        if len(checked)!=1:ambiguous+=1;continue
        candidates=checked
    attach(movies[ident],candidates[0])

for r in unmatched:
    if r['vanity'] not in rt_counts:continue
    ident='rt:'+r['emsId']
    m={'id':ident,'title':r['title'],'aliases':list(aliases(r,'rt')-{r['title']}),
       'year':r.get('releaseYear'),'runtime':r.get('runTime'),'genres':genres(r.get('genres',[])),'countries':[],
       'score':None,'votes':None,'imdb':None,'criticCount':None,'audienceCount':None,'offers':{},'kind':'movie'}
    attach(m,r);movies[ident]=m

def classification(value):
    value=re.sub(r'\s+','',str(value or '')).upper()
    canonical={'G':'G','PG':'PG','M':'M','MA':'MA15+','MA15':'MA15+','MA15+':'MA15+',
               'R':'R18+','R18':'R18+','R18+':'R18+','X18':'X18+','X18+':'X18+',
               'CTC':'Unclassified','NR':'Unclassified','UNRATED':'Unclassified','NOTRATED':'Unclassified'}
    return canonical.get(value)

classifications={}
path=BASE/'classification_movies.json'
if path.exists():classifications=json.loads(path.read_text())
for m in movies.values():m['classifications']=[]
for entry in classifications.values():
    value=classification(entry.get('classification'))
    if entry['id'] in movies and value:
        target=movies[entry['id']]['classifications']
        if value not in target:target.append(value)
for m in movies.values():m['classifications'].sort()

language_file=BASE/'language_movies.json'
language_data=json.loads(language_file.read_text()) if language_file.exists() else {'movies':{}}
for m in movies.values():
    iid=m['id'].split(':',1)[1] if m['id'].startswith('imdb:') else None
    entry=language_data['movies'].get(iid,{})
    m['languageGroup']=entry.get('languageGroup','unknown')
    m['languageLabels']=[l['label'] for l in entry.get('languages',[])]
    if entry:m['languageSourceUrl']=entry.get('sourceUrl')

# Database floor (Zac, 8 Nov 2026): IMDb 5.0+ so lower-rated films can be found by search.
# The default IMDb filter stays at 6.0 (default_route and the page's slider value).
def passes(m):
    return (m.get('votes') or 0)>=1000 and (((m.get('score') or 0)>=5) or ((m.get('critics') or 0)>=60 and (m.get('criticCount') or 0)>=50) or ((m.get('audience') or 0)>=60 and (m.get('audienceCount') or 0)>=1000))

india=load_india()
dropped=collections.Counter()
selected=[]
for m in movies.values():
    if not passes(m):continue
    reason=drop_reason(m,india)
    if reason:dropped[reason]+=1;continue
    selected.append(m)
selected.sort(key=lambda x:(-(x.get('score') or 0),-(x.get('votes') or 0),x['title']))
def default_route(m):
    # Default route: IMDb only (Zac, Nov 2026). Tomatometer and Popcornmeter start unticked.
    return (m.get('score') or 0)>=6 and (m.get('votes') or 0)>=1000
default_movies=[m for m in selected if default_route(m) and m.get('languageGroup','unknown') in ('english','unknown') and m['genres'] and not set(m['genres'])&{'Horror','Romance','Documentary'}]
manifest=json.loads((BASE/'rt_count_manifest.json').read_text())
meta={'checked':checked_label,'checkedISO':today.isoformat(),'imdbAsOf':imdb_asof.isoformat(),'total':len(selected),'defaultResults':len(default_movies),'defaultCountryFilter':'exclude','defaultLanguage':'english','dropped':dict(dropped),'defaultLanguage':'english','dropped':dict(dropped),
      'imdbMovieRecordsImported':len(imdb),'imdbBulkQualified':sum(not m['adult'] and m['score']>=6 for m in imdb),
      'justWatchRecords':len(jw),'rtSearchRecords':len(rt),'rtReviewCountsChecked':len(rt_counts),
      'rtCheckedInFinal':sum(bool(m.get('rtCountsChecked')) for m in selected),
      'rtReviewCountCoverageComplete':False,'rtSearchCoverageComplete':False,
      'knownAustralianClassifications':sum(bool(m['classifications']) for m in selected),
      'classificationCounts':dict(collections.Counter(c for m in selected for c in m['classifications'])),
      'languageCounts':dict(collections.Counter(m['languageGroup'] for m in selected)),
      'rtOnlyQualifiers':sum(not ((m.get('score') or 0)>=5 and (m.get('votes') or 0)>=1000) for m in selected),
      'ambiguousMatchesSkipped':ambiguous,'streamingLive':live['label'] if live else None,'sourceCounts':{c:sum(c in m['offers'] for m in default_movies) for c in providers},
      'coverageText':f'IMDb bulk data was checked across {len(imdb):,} records with at least 1,000 votes; only feature films and TV movies are kept. {len(jw):,} JustWatch Australia movie records and {len(rt):,} RT search records were processed. Review counts were confirmed for {len(rt_counts):,} RT film pages before access limits interrupted further checks. Unconfirmed RT counts cannot qualify a movie. Left out entirely: {dropped["type"]:,} shorts and videos, {dropped["india"]:,} Indian productions and {dropped["suspicious"]+dropped["unconfirmed"]:,} suspicious or unconfirmed ratings. The default English-language view with genre exclusions shows {len(default_movies):,} movies; the file contains {len(selected):,} qualifying records before genre and country filters.',
      'coverageRows':[['IMDb records imported (1,000+ votes, all title types)',len(imdb)],['IMDb records meeting 6.0+ (all countries/genres)',sum(not m['adult'] and m['score']>=6 for m in imdb)],['JustWatch AU movie records processed',len(jw)],['Rotten Tomatoes search records processed',len(rt)],['RT film pages with confirmed counts',len(rt_counts)],['RT count-checked titles in this file',sum(bool(m.get('rtCountsChecked')) for m in selected)],['Films with an Australian classification',sum(bool(m['classifications']) for m in selected)],['Qualifying records in this file',len(selected)],['Left out: shorts, TV shorts, videos, specials',dropped['type']],['Left out: Indian productions',dropped['india']],['Left out: IMDb 8.5+ from under 10,000 votes, no RT score',dropped['suspicious']],['Left out: unconfirmed by JustWatch, RT or Wikidata, under 25,000 votes',dropped['unconfirmed']],['Results with your default language and genre settings',len(default_movies)]]}
years=[m['year'] for m in selected if isinstance(m.get('year'),int)]
minyear=min(years);maxyear=max(years)
automation_file=BASE/'movie_refresh_automation.json'
if automation_file.exists():meta['refresh']=json.loads(automation_file.read_text())
# Unknown (None) facts are left out of the page to keep index.html well under Cloudflare's 25 MiB
# per-file limit; the page and the Python checks treat a missing key the same as null.
payload=json.dumps([{k:v for k,v in m.items() if v is not None} for m in selected],ensure_ascii=False,separators=(',',':')).replace('<','\\u003c')
meta_payload=json.dumps(meta,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c')
template=(BASE/'movie_finder_template.html').read_text()
for key,value in {'@@MINYEAR@@':str(minyear),'@@MAXYEAR@@':str(maxyear),'@@DATA@@':payload,'@@META@@':meta_payload}.items():template=template.replace(key,value)
if imdb_asof!=today:
    template=template.replace('Australia · 7 November 2026',f'Australia · IMDb {imdb_asof.day} {imdb_asof:%b %Y} · streaming &amp; RT {today.day} {today:%b %Y}')
else:
    template=template.replace('Australia · 7 November 2026','Australia · '+checked_label)
template=template.replace('Used with permission. For individual personal use.','Used with permission. For personal, non-commercial use.')
if meta.get('refresh',{}).get('is_enabled'):
    r=meta['refresh']
    template=template.replace('Monthly refresh is being set up. Download the latest file after a refresh; existing downloaded copies stay unchanged.',
        f'<strong>Automatic refresh:</strong> {html.escape(r["description"])}. IMDb ratings and votes last updated {imdb_asof.day} {imdb_asof:%B %Y}. '
        +(f'Australian streaming availability last updated {live["label"]} from TMDB (JustWatch data). Rotten Tomatoes, classification and language facts are from the {checked_label} snapshot and are not refreshed automatically. ' if live else
        f'Australian streaming availability, Rotten Tomatoes, classification and language facts are from the {checked_label} snapshot and are not refreshed automatically. ')+
        f'<a href="{html.escape(r["latestUrl"])}" target="_blank" rel="noopener noreferrer">Open the latest version</a>. Downloaded copies stay unchanged.')
refresh_recipe={
    'purpose':'Refresh this personal movie-finder HTML in place, preserving the UI and Library identity.',
    'targetLibraryFileId':'libfile_fde3_f-9b018754a2088191bb68dcffe313bf7b_494f369d3c308191a01a1e92a2d1c1ec',
    'defaultCountryFilter':'exclude','defaultCountryLabel':'Exclude India · allow unknown countries','dataElement':'script#catalogue','metadataElement':'script#metadata','country':'AU',
    'providers':providers,'offerTypes':['FLATRATE'],
    'globalMinimumIMDbVotes':1000,'defaultQualification':{'logic':'OR','IMDb':{'minScore':6.0,'minVotes':1000},'Tomatometer':{'minScore':60,'minCriticReviews':50},'Popcornmeter':{'minScore':60,'minAudienceRatingsLowerBound':1000}},
    'sources':{'imdbRatings':'https://datasets.imdbws.com/title.ratings.tsv.gz','imdbBasics':'https://datasets.imdbws.com/title.basics.tsv.gz','imdbDocs':'https://developer.imdb.com/non-commercial-datasets/','justWatchGraphql':'https://apis.justwatch.com/graphql','rtBrowse':'https://www.rottentomatoes.com/browse/movies_at_home/'},
    'justWatchFields':'id objectType content(country:AU,language:en){title originalTitle originalReleaseYear runtime fullPath ageCertification genres{shortName} productionCountries externalIds{imdbId} scoring{imdbScore imdbVotes tomatoMeter certifiedFresh}} offers(country:AU,platform:WEB,filter:{packages:["nfx","prv","pmp","stn","dnp","mxx","atp"],monetizationTypes:[FLATRATE]}){standardWebURL monetizationType package{shortName}}',
    'justWatchPagination':'popularTitles(country:AU,first:100,after:$after,sortBy:POPULAR,filter:{objectTypes:[MOVIE],releaseYear:{min:$lo,max:$hi}}). Split ranges to stay below pagination limits; refine oversized years into appropriate vote/rating buckets and deduplicate ids. Every film needs at least 1,000 IMDb votes; an IMDb score below 6.0 must not remove a film that qualifies through RT.',
    'classifications':'Query grounded AU nodes with node(id:$id){...on Movie{content(country:AU,language:en){ageCertification externalIds{imdbId}}}}. Preserve Unknown; never convert US MPAA classifications into Australian ones.',
    'rtSearch':'The public browse page contains the client-side algoliaSearch configuration. Use only its permitted public title-search API; movie records expose releaseYear, genres, vanity, emsId and rottenTomatoes scores/badges. The public search has a 1,000-result cap per year. Label coverage partial; do not claim a full database export or bypass access controls.',
    'rtReviewCounts':'The public movie page has script#media-scorecard-json. criticsScore.reviewCount is the critic count. Use audienceScore.scorePercent with its corresponding bandedRatingCount and reviewsPageUrl. A 1,000+ band is a lower bound, not an exact count. Verified and all-audience groups cannot be mixed. Use conservative request rates; stop further film-page requests immediately on HTTP 403 or 429. Never retry through another channel to evade access limits.',
    'staleData':'Keep last-known RT facts with their actual rtCheckedDate if a refresh is blocked, and show that they were not refreshed. Do not replace old checked dates with the run date. Do not invent missing counts or let them qualify films.',
    'identityMatching':'Use IMDb identifiers where present, otherwise exact normalized title/alias and release year only when unambiguous. Skip ambiguous matches; never fabricate direct review URLs.',
    'validation':'Check independent OR score gates and minimum review counts; nine service filters; year range; Australian classification multiselect; 16 broad genre groups with exclusion winning over inclusion; reset; sorting; review links; pagination; offline functionality. Replace the same Library file only after validation.',
    'languageFilter':'Default all. Match original-language facts through IMDb P345 identifiers and Wikidata P364. English means English is one of the recorded original languages; Foreign means known original languages without English. Do not infer languages from countries or title spelling. Preserve Unknown separately. This is not a dubbed-audio availability filter.',
    'fullDatabaseLimitation':'IMDb bulk datasets cover eligible movie records. A complete RT database is not available in this file; a complete authorised RT data feed/export would be required to claim full coverage.'}
recipe_payload=json.dumps(refresh_recipe,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c')
template=template.replace('<script id="metadata"', '<script id="refresh-recipe" type="application/json">'+recipe_payload+'</script>\n<script id="metadata"',1)
assert not re.search(r'@@[A-Z]+@@',template)
OUT.write_text(template)
(BASE/'extended_catalogue.json').write_text(json.dumps({'metadata':meta,'movies':selected},ensure_ascii=False))
print(json.dumps(meta,ensure_ascii=False),flush=True)
print('file',OUT.stat().st_size,flush=True)
