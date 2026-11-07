import datetime
from zoneinfo import ZoneInfo
import re
import unicodedata

def norm(text):
    text=unicodedata.normalize('NFKD',str(text or '')).casefold()
    return ''.join(c for c in text if c.isalnum())

def aliases(movie,source):
    if source=='rt':
        return set([movie.get('title','')]+movie.get('titles',[])+movie.get('aka',[]))
    return {movie.get('title',''),movie.get('originalTitle','')}

def percent(value):
    if value is None:return None
    m=re.search(r'\d+(?:\.\d+)?',str(value))
    return float(m.group()) if m else None

def scorecard(text,slug):
    import json
    m=re.search(r'<script\b[^>]*id="media-scorecard-json"[^>]*>(.*?)</script>',text,re.S)
    if not m:raise ValueError('Scorecard not present')
    card=json.loads(m.group(1));critics=card.get('criticsScore') or {};aud=card.get('audienceScore') or {}
    count_text=aud.get('bandedRatingCount') or ''
    count_match=re.search(r'([\d,]+)',count_text)
    count=int(count_match.group(1).replace(',','')) if count_match and not re.search(r'(?:fewer|less|under|<)',count_text,re.I) else None
    cc=critics.get('reviewCount')
    if not isinstance(cc,int):cc=critics.get('ratingCount')
    overlay=card.get('overlay') or {}
    return {'vanity':slug,'critics':percent(critics.get('scorePercent')),'criticCount':cc if isinstance(cc,int) else None,
            'audience':percent(aud.get('scorePercent')),'audienceCount':count,'audienceCountText':count_text,
            'audienceBanded':'+' in count_text,'audienceType':'verified' if 'verified' in count_text.lower() else 'all',
            'certifiedFresh':bool(critics.get('certified')),'verifiedHot':bool(aud.get('certified')) and 'verified' in count_text.lower(),
            'criticsUrl':'https://www.rottentomatoes.com'+(critics.get('reviewsPageUrl') or '/m/'+slug+'/reviews'),
            'audienceUrl':'https://www.rottentomatoes.com'+(aud.get('reviewsPageUrl') or '/m/'+slug+'/reviews/all-audience'),
            'title':re.sub(r'\s*\|\s*Rotten Tomatoes.*$','',re.search(r'<title>(.*?)</title>',text,re.S).group(1)).strip(),
            'checked':datetime.datetime.now(ZoneInfo('Australia/Perth')).date().isoformat(),'countVerified':True}
