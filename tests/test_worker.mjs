// Offline checks of worker/index.js with a fake fetch (no network, no TMDB key needed).
import assert from 'node:assert/strict';
import worker from '../worker/index.js';

const calls = [];
globalThis.fetch = async (url, init = {}) => {
  const u = new URL(url); calls.push({ u, init });
  const ok = body => new Response(JSON.stringify(body), { status: 200, headers: { 'content-type': 'application/json' } });
  if (u.hostname === 'api.themoviedb.org') {
    if (u.pathname === '/3/find/tt0000001') return ok({ movie_results: [{ id: 11 }], tv_results: [] });
    if (u.pathname === '/3/find/tt0000002') return ok({ movie_results: [], tv_results: [{ id: 22 }] });
    if (u.pathname === '/3/find/tt0000009') return ok({ movie_results: [], tv_results: [] });
    if (u.pathname === '/3/movie/11') return ok({
      videos: { results: [
        { site: 'YouTube', key: 'teaser12345', type: 'Teaser', official: true },
        { site: 'Vimeo', key: '999', type: 'Trailer' },
        { site: 'YouTube', key: 'trailer1234', type: 'Trailer', official: true, name: 'Official Trailer' },
        { site: 'YouTube', key: 'bad key!', type: 'Trailer', official: true },
      ] },
      recommendations: { results: [
        { id: 5, title: 'Rec One', original_title: 'Rec Uno', release_date: '2001-02-03', media_type: 'movie' },
        { id: 6, title: 'Adult', adult: true, media_type: 'movie' },
        { id: 7, name: 'A Show', first_air_date: '', media_type: 'tv' },
      ] },
    });
    if (u.pathname === '/3/tv/22') return ok({ videos: { results: [] }, recommendations: { results: [] } });
  }
  if (u.hostname === 'api.tvmaze.com') {
    if (u.pathname === '/lookup/shows' && u.searchParams.get('imdb') === 'tt0000002') return ok({ id: 77 });
    if (u.pathname === '/lookup/shows') return new Response('', { status: 404 });
    if (u.pathname === '/shows/77') return ok({ id: 77, name: 'Show', status: 'Running', url: 'https://www.tvmaze.com/shows/77/show',
      webChannel: { name: 'Apple TV' }, _embedded: { nextepisode: { season: 3, number: 1, name: 'Back', airdate: '2026-12-01', airstamp: '2026-12-01T09:00:00+00:00' } } });
  }
  return new Response('nope', { status: 500 });
};

const env = { TMDB_API_KEY: '0123456789abcdef0123456789abcdef', ASSETS: { fetch: () => new Response('static file') } };
const get = async (path, e = env) => { const r = await worker.fetch(new Request('https://site' + path), e, {}); return [r.status, r.headers.get('content-type')?.includes('json') ? await r.json() : await r.text()]; };

assert.deepEqual(await get('/index.html'), [200, 'static file']);
assert.equal((await get('/api/title?imdb=nope'))[0], 400);
assert.equal((await get('/api/title?imdb=tt0000001', { ASSETS: env.ASSETS }))[0], 503, 'no key -> 503');
assert.equal((await get('/api/other?imdb=tt0000001'))[0], 404);

let [s, j] = await get('/api/title?imdb=tt0000001&kind=movie');
assert.equal(s, 200);
assert.deepEqual(j.trailer, { key: 'trailer1234', name: 'Official Trailer', type: 'Trailer' }, 'official YouTube trailer beats teaser');
assert.deepEqual(j.recs.map(r => [r.title, r.kind, r.year, r.original]), [['Rec One', 'movie', 2001, 'Rec Uno'], ['A Show', 'tv', null, '']]);
assert.ok(calls.some(c => c.u.searchParams.get('api_key') === env.TMDB_API_KEY), 'v3 key sent as api_key');

[s, j] = await get('/api/title?imdb=tt0000002&kind=movie');
assert.equal(j.kind, 'tv', 'falls back to TV results'); assert.equal(j.trailer, null);
[s, j] = await get('/api/title?imdb=tt0000009');
assert.deepEqual([s, j.found], [200, false]);

calls.length = 0;
await get('/api/title?imdb=tt0000001', { ...env, TMDB_API_KEY: 'x'.repeat(200) });
assert.ok(calls.every(c => c.init.headers.authorization === 'Bearer ' + 'x'.repeat(200) && !c.u.searchParams.get('api_key')), 'v4 token sent as Bearer');

[s, j] = await get('/api/tvnext?imdb=tt0000002');
assert.equal(j.network, 'Apple TV'); assert.equal(j.next.season, 3); assert.equal(j.prev, null);
[s, j] = await get('/api/tvnext?imdb=tt0000001');
assert.deepEqual([s, j.found], [200, false]);
console.log('worker checks passed');
