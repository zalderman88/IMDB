"""Match original-language facts through IMDb IDs in Wikidata, never countries."""
import xml.etree.ElementTree as ET
import datetime
import gzip
import io
import json
import pathlib
import re
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

BASE=pathlib.Path(__file__).parent
movies=json.loads((BASE/'extended_catalogue.json').read_text())['movies']
wanted={m['id'].split(':',1)[1] for m in movies if m['id'].startswith('imdb:')}
query='SELECT ?film ?imdb ?language WHERE { ?film wdt:P364 ?language; wdt:P345 ?imdb. }'
url='https://query.wikidata.org/sparql?'+urllib.parse.urlencode({'query':query,'format':'tsv'})
headers={'User-Agent':'PersonalMovieFinder/1.0 (personal movie metadata research)','Accept':'text/tab-separated-values','Accept-Encoding':'gzip'}
matches={};rows=0
print(json.dumps({'wantedIMDbIds':len(wanted),'status':'Fetching original-language facts'}),flush=True)
with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=55) as response:
    stream=gzip.GzipFile(fileobj=response) if response.headers.get('Content-Encoding')=='gzip' else response
    for event,element in ET.iterparse(stream,events=('end',)):
        if not element.tag.endswith('}result'):continue
        row={binding.attrib['name']:next(iter(binding)).text for binding in element}
        rows+=1
        iid=row.get('imdb') or ''
        if iid not in wanted:
            element.clear();continue
        language=row.get('language') or ''
        film=row.get('film') or ''
        lang=language.rsplit('/',1)[-1];fid=film.rsplit('/',1)[-1]
        if not re.fullmatch(r'Q\d+',lang) or not re.fullmatch(r'Q\d+',fid):continue
        entry=matches.setdefault(iid,{'films':set(),'languageIds':set()})
        entry['films'].add(fid);entry['languageIds'].add(lang);element.clear()

if not matches:raise RuntimeError('No language matches were retrieved; do not treat this as a complete language import')

language_ids=sorted({lang for entry in matches.values() for lang in entry['languageIds']})
print(json.dumps({'sourceRows':rows,'matchedIMDbIds':len(matches),'languageEntities':len(language_ids)}),flush=True)
languages={}
for offset in range(0,len(language_ids),100):
    values=' '.join('wd:'+lid for lid in language_ids[offset:offset+100])
    q='SELECT ?language ?languageLabel ?code ?isEnglish WHERE { VALUES ?language { '+values+' } OPTIONAL { ?language wdt:P218 ?code. } BIND(EXISTS { ?language wdt:P279* wd:Q1860. } AS ?isEnglish) SERVICE wikibase:label { bd:serviceParam wikibase:language "en". } }'
    u='https://query.wikidata.org/sparql?'+urllib.parse.urlencode({'query':q,'format':'json'})
    req=urllib.request.Request(u,headers={'User-Agent':headers['User-Agent'],'Accept':'application/sparql-results+json'})
    with urllib.request.urlopen(req,timeout=50) as response:data=json.load(response)
    for row in data['results']['bindings']:
        lid=row['language']['value'].rsplit('/',1)[-1]
        code=row.get('code',{}).get('value')
        label=row.get('languageLabel',{}).get('value',lid)
        english=lid=='Q1860' or code=='en' or row.get('isEnglish',{}).get('value')=='true'
        languages[lid]={'id':lid,'label':label,'code':code,'isEnglish':english}

out={};ambiguous=[]
for iid,entry in matches.items():
    if len(entry['films'])!=1:
        ambiguous.append(iid);continue
    records=[languages[lid] for lid in sorted(entry['languageIds']) if lid in languages]
    if not records:continue
    film=next(iter(entry['films']))
    out[iid]={'languages':records,'languageGroup':'english' if any(l['isEnglish'] for l in records) else 'foreign',
              'source':'Wikidata P345/P364','sourceUrl':'https://www.wikidata.org/wiki/'+film}

result={'checked':datetime.datetime.now(ZoneInfo('Australia/Perth')).date().isoformat(),
        'source':'https://query.wikidata.org/sparql','property':'P364 original language of film or TV show',
        'sourceRows':rows,'matched':len(out),'ambiguousSkipped':ambiguous,'movies':out}
(BASE/'language_movies.json').write_text(json.dumps(result,ensure_ascii=False))
print(json.dumps({'finished':True,'matched':len(out),'ambiguousSkipped':len(ambiguous),
                  'english':sum(m['languageGroup']=='english' for m in out.values()),
                  'foreign':sum(m['languageGroup']=='foreign' for m in out.values())}),flush=True)
