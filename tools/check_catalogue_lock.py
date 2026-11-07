"""Ensure UI/filter edits preserve the existing movies and rating/count facts."""
import hashlib,json,pathlib,re
root=pathlib.Path(__file__).resolve().parent.parent
text=(root/'Australian_Movies_Android.html').read_text()
data=json.loads(re.search(r'<script id="catalogue"[^>]*>(.*?)</script>',text,re.S).group(1))
assert all((m.get('votes') or 0)>=1000 for m in data),'Global 1,000 IMDb-vote minimum violated'
rows=[{k:v for k,v in m.items() if not k.startswith('language')} for m in sorted(data,key=lambda m:m['id'])]
current={'filmCount':len(data),'minimumIMDbVotes':1000,'sha256OfNonLanguageMovieFacts':hashlib.sha256(json.dumps(rows,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()}
assert current==json.loads((root/'data/catalogue_lock.json').read_text()),'Movies or existing movie facts changed; a UI/filter edit must preserve them'
print(json.dumps({'catalogueLock':'passed','films':len(data),'minimumIMDbVotes':1000}))
