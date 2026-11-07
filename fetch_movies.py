"""Public JustWatch GraphQL request transport; no credentials bundled."""
import json
import urllib.request
import urllib.error

def request(query,variables=None):
    payload=json.dumps({'query':query,'variables':variables or {}}).encode()
    req=urllib.request.Request('https://apis.justwatch.com/graphql',data=payload,
        headers={'Content-Type':'application/json','User-Agent':'Mozilla/5.0',
                 'Origin':'https://www.justwatch.com'})
    try:
        with urllib.request.urlopen(req,timeout=55) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        detail=e.read().decode()
        print(detail,flush=True)
        raise
