// Worker in front of the static site. Static files are served as before; /api/* answers
// on-demand lookups for site/extras.js and caches them at the edge.
//   /api/title?imdb=tt0111161&kind=movie|tv  -> TMDB trailer + recommendations (needs secret TMDB_API_KEY)
//   /api/tvnext?imdb=tt0903747               -> TVmaze next/previous episode (no key)
// Cloudflare Access protects the whole hostname, so these routes are private too.

const TMDB = 'https://api.themoviedb.org/3';
const TVMAZE = 'https://api.tvmaze.com';
const DAY = 86400;

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (!url.pathname.startsWith('/api/')) return env.ASSETS.fetch(request);
    if (request.method !== 'GET') return json({ error: 'method' }, 405);
    const imdb = url.searchParams.get('imdb') || '';
    if (!/^tt\d{5,10}$/.test(imdb)) return json({ error: 'bad imdb id' }, 400);
    try {
      if (url.pathname === '/api/title') {
        if (!env.TMDB_API_KEY) return json({ error: 'TMDB key not set' }, 503);
        const kind = url.searchParams.get('kind') === 'tv' ? 'tv' : 'movie';
        return await cached(ctx, `title/${kind}/${imdb}/v1`, 7 * DAY, () => titleInfo(env.TMDB_API_KEY, imdb, kind));
      }
      if (url.pathname === '/api/tvnext') {
        return await cached(ctx, `tvnext/${imdb}/v1`, DAY / 4, () => tvNext(imdb));
      }
      return json({ error: 'not found' }, 404);
    } catch (e) {
      return json({ error: String(e.message || e) }, 502);
    }
  },
};

function json(body, status = 200, maxAge = 0) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'cache-control': maxAge ? `private, max-age=${Math.min(maxAge, 3600)}` : 'no-store',
    },
  });
}

// Edge cache keyed on a synthetic URL so results are shared between Zac and his dad.
async function cached(ctx, key, ttl, compute) {
  const cache = globalThis.caches && caches.default;
  const cacheKey = new Request('https://cache.zac-movies.internal/' + key);
  if (cache) {
    const hit = await cache.match(cacheKey);
    if (hit) return json(await hit.json(), 200, ttl);
  }
  const body = await compute();
  if (cache) {
    const store = new Response(JSON.stringify(body), { headers: { 'cache-control': `public, max-age=${ttl}` } });
    const p = cache.put(cacheKey, store);
    if (ctx && ctx.waitUntil) ctx.waitUntil(p); else await p;
  }
  return json(body, 200, ttl);
}

async function getJson(url, headers = {}) {
  for (let attempt = 0; attempt < 3; attempt++) {
    const r = await fetch(url, { headers: { accept: 'application/json', 'user-agent': 'zac-movies/1.0', ...headers } });
    if (r.status === 404) return null;
    if (r.status === 429 && attempt < 2) { await new Promise(res => setTimeout(res, 1500 * (attempt + 1))); continue; }
    if (!r.ok) throw new Error(`${new URL(url).hostname} ${r.status}`);
    return r.json();
  }
}

function tmdbFetch(key, path, params = {}) {
  const u = new URL(TMDB + path);
  for (const [k, v] of Object.entries(params)) u.searchParams.set(k, v);
  const headers = {};
  // v4 read access tokens are long JWTs; v3 keys are 32 hex characters.
  if (key.length > 40) headers.authorization = 'Bearer ' + key; else u.searchParams.set('api_key', key);
  return getJson(u.toString(), headers);
}

function pickTrailer(videos) {
  const list = (videos && videos.results || []).filter(v => v.site === 'YouTube' && /^[\w-]{6,20}$/.test(v.key || ''));
  const rank = v => (v.type === 'Trailer' ? 0 : v.type === 'Teaser' ? 2 : 4) + (v.official ? 0 : 1);
  list.sort((a, b) => rank(a) - rank(b) || String(b.published_at || '').localeCompare(String(a.published_at || '')));
  const v = list.find(x => ['Trailer', 'Teaser', 'Clip'].includes(x.type)) || null;
  return v && { key: v.key, name: v.name || 'Trailer', type: v.type };
}

export async function titleInfo(key, imdb, kind) {
  const found = await tmdbFetch(key, `/find/${imdb}`, { external_source: 'imdb_id' });
  let hit = null, type = kind;
  if (found) {
    const order = kind === 'tv' ? ['tv', 'movie'] : ['movie', 'tv'];
    for (const t of order) { const r = found[t + '_results']; if (r && r.length) { hit = r[0]; type = t; break; } }
  }
  if (!hit) return { imdb, found: false, trailer: null, recs: [] };
  const d = await tmdbFetch(key, `/${type}/${hit.id}`, { append_to_response: 'videos,recommendations', language: 'en-US' });
  if (!d) return { imdb, found: false, trailer: null, recs: [] };
  const recs = (d.recommendations && d.recommendations.results || [])
    .filter(r => (r.title || r.name) && !r.adult)
    .slice(0, 16)
    .map(r => {
      const t = r.media_type === 'tv' || (!r.media_type && type === 'tv') ? 'tv' : 'movie';
      const date = r.release_date || r.first_air_date || '';
      return { tmdb: r.id, kind: t, title: r.title || r.name, original: r.original_title || r.original_name || '', year: /^\d{4}/.test(date) ? +date.slice(0, 4) : null };
    });
  return { imdb, found: true, tmdb: hit.id, kind: type, trailer: pickTrailer(d.videos), recs };
}

function ep(e) {
  return e ? { season: e.season, number: e.number, name: e.name || '', airdate: e.airdate || null, airstamp: e.airstamp || null } : null;
}

export async function tvNext(imdb) {
  const show = await getJson(`${TVMAZE}/lookup/shows?imdb=${imdb}`);
  if (!show) return { imdb, found: false };
  const full = await getJson(`${TVMAZE}/shows/${show.id}?embed[]=nextepisode&embed[]=previousepisode`);
  const s = full || show, em = s._embedded || {};
  return {
    imdb, found: true, tvmaze: s.id, url: s.url || null, name: s.name, status: s.status || null,
    network: (s.webChannel && s.webChannel.name) || (s.network && s.network.name) || null,
    next: ep(em.nextepisode), prev: ep(em.previousepisode),
  };
}
