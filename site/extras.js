// Add-ons shared by the Movies, TV and For you pages:
//  - search by actor or director (people.json, built from IMDb bulk files by tools/build_people.py)
//  - "Trailer" and "More like this" on each title (TMDB, via the Worker at /api/title)
//  - "Coming up" next-episode dates for TV shows you liked on For you (TVmaze, via /api/tvnext)
// Loaded with <script src="extras.js" defer> after each page's own script. It reads the page's
// globals (DATA, normalize, apply, items, byId) when they exist and never edits page state
// other than the search text and each row's extra bar.
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const page = $('movies') ? 'movies' : $('shows') ? 'tv' : $('picks') ? 'foryou' : null;
  if (!page) return;
  const LIST = $(page === 'movies' ? 'movies' : page === 'tv' ? 'shows' : 'picks');
  const g = globalThis;
  const hasData = () => { try { return Array.isArray(DATA); } catch { return false; } };
  const pageData = () => { try { return DATA; } catch { return []; } };
  const forYouItems = () => { try { return items; } catch { return []; } };
  const norm = s => String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  const tt = id => String(id || '').split(':').pop();
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; };
  const btn = (label, cls) => { const b = el('button', 'xf-btn' + (cls ? ' ' + cls : ''), label); b.type = 'button'; return b; };
  const ext = (label, href, cls) => { const a = el('a', cls || '', label); a.href = href; a.target = '_blank'; a.rel = 'noopener noreferrer'; return a; };

  // ---------- styles ----------
  const css = `
.xf-bar{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin-top:8px}
.xf-credits{margin:6px 0 0;color:var(--muted);font-size:13px;line-height:1.5}
.xf-credits b{font-weight:600;color:var(--muted)}
.xf-name{background:none;border:0;padding:0;margin:0;font:inherit;color:var(--ink);text-decoration:underline;text-decoration-color:var(--line);text-underline-offset:3px;cursor:pointer}
.xf-name:hover{text-decoration-color:var(--accent)}
.xf-btn{min-height:36px;padding:6px 12px;border-radius:18px;border:1px solid var(--line);background:transparent;color:var(--ink);font:inherit;font-size:13px;font-weight:600;cursor:pointer}
.xf-btn:hover,.xf-btn[aria-expanded=true]{border-color:var(--accent);color:var(--accent)}
.xf-btn:disabled{opacity:.6;cursor:default}
.xf-next{font-size:13px;color:var(--accent);font-weight:600}
.xf-recs{margin-top:8px;padding:10px 12px;border:1px solid var(--line);border-radius:10px;background:var(--soft);font-size:13px}
.xf-recs ol{margin:0;padding:0;list-style:none;display:grid;gap:6px}
.xf-recs li{display:flex;justify-content:space-between;gap:10px;align-items:baseline}
.xf-recs li a{color:var(--ink)}
.xf-recs .xf-sc{color:var(--muted);white-space:nowrap;font-size:12px}
.xf-recs .xf-out{color:var(--muted)}
.xf-src{margin:8px 0 0;color:var(--muted);font-size:11px}
.xf-src a{color:var(--muted)}
.xf-dialog{width:min(920px,calc(100vw - 24px));padding:0;border:1px solid var(--line);border-radius:12px;background:var(--surface);color:var(--ink)}
.xf-dialog::backdrop{background:rgba(0,0,0,.72)}
.xf-dialog .xf-head{display:flex;justify-content:space-between;align-items:center;gap:8px;padding:10px 12px}
.xf-dialog h2{margin:0;font-size:15px}
.xf-frame{position:relative;width:100%;aspect-ratio:16/9;background:#000}
.xf-frame iframe{position:absolute;inset:0;width:100%;height:100%;border:0}
.xf-dialog .xf-src{padding:0 12px 10px}
.xf-coming{margin:14px 0;padding:14px 16px;border-radius:12px;background:var(--surface);border:1px solid var(--line)}
.xf-coming h2{margin:0 0 4px;font-size:17px}
.xf-coming ol{margin:8px 0 0;padding:0;list-style:none;display:grid;gap:8px}
.xf-coming li{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;font-size:14px}
.xf-coming .xf-when{color:var(--accent);font-weight:650;white-space:nowrap}
.xf-coming .xf-muted,.xf-coming p{color:var(--muted);font-size:13px;margin:6px 0 0}
`;
  document.head.append(Object.assign(el('style'), { textContent: css }));

  // ---------- people search ----------
  let people = null, peopleLoading = null;
  function loadPeople() {
    if (peopleLoading) return peopleLoading;
    peopleLoading = fetch('people.json', { credentials: 'same-origin' })
      .then(r => (r.ok ? r.json() : null))
      .then(p => {
        if (!p || !Array.isArray(p.names)) return null;
        people = p;
        if (hasData() && (page === 'movies' || page === 'tv')) {
          for (const m of pageData()) {
            const id = tt(m.id), ids = [...(p.d[id] || []), ...(p.a[id] || [])];
            if (ids.length && typeof m._search === 'string') m._search += ' ' + norm(ids.map(i => p.names[i]).join(' '));
          }
          const s = $('search');
          if (s && s.value.trim() && typeof g.apply === 'function') g.apply();
        }
        for (const li of LIST.querySelectorAll('li[data-id]')) addCredits(li);
        return p;
      })
      .catch(() => null);
    return peopleLoading;
  }
  function searchFor(name) {
    if (page === 'foryou') {
      const it = byIdSafe(currentRowId);
      location.href = (it && it.kind === 't' ? 'tv.html' : 'index.html') + '?q=' + encodeURIComponent(name);
      return;
    }
    const s = $('search');
    if (!s) return;
    s.value = name;
    s.dispatchEvent(new Event('input', { bubbles: true }));
    s.scrollIntoView({ block: 'start', behavior: 'smooth' });
  }
  let currentRowId = null;
  function addCredits(li) {
    if (!people || li.querySelector('.xf-credits')) return;
    const id = tt(li.dataset.id), d = people.d[id] || [], a = people.a[id] || [];
    if (!d.length && !a.length) return;
    const p = el('p', 'xf-credits');
    const names = (label, list) => {
      p.append(el('b', '', label + ' '));
      list.forEach((i, n) => {
        if (n) p.append(', ');
        const b = el('button', 'xf-name', people.names[i]); b.type = 'button';
        b.title = 'Show everything with ' + people.names[i];
        b.addEventListener('click', () => { currentRowId = id; searchFor(people.names[i]); });
        p.append(b);
      });
    };
    if (d.length) names(d.length > 1 ? 'Directors' : 'Director', d.slice(0, 2));
    if (d.length && a.length) p.append(' · ');
    if (a.length) names('With', a.slice(0, 3));
    const bar = li.querySelector('.xf-bar');
    bar ? bar.before(p) : anchor(li).append(p);
  }
  function setupSearch() {
    if (page !== 'movies' && page !== 'tv') return;
    const s = $('search');
    if (!s) return;
    s.placeholder = page === 'movies' ? 'Find a film, actor, director, year or genre…' : 'Find a show, actor, year or genre…';
    s.addEventListener('focus', loadPeople, { once: true });
    const q = new URLSearchParams(location.search).get('q');
    if (q) { s.value = q.slice(0, 80); loadPeople().then(() => s.dispatchEvent(new Event('input', { bubbles: true }))); }
  }

  // ---------- TMDB trailer + recommendations ----------
  const titleCache = new Map();
  function titleInfo(id, kind) {
    const key = kind + ':' + id;
    if (!titleCache.has(key)) {
      titleCache.set(key, fetch('/api/title?imdb=' + id + '&kind=' + kind, { credentials: 'same-origin' })
        .then(async r => { const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(r.status === 503 ? 'nokey' : (j.error || 'HTTP ' + r.status)); return j; })
        .catch(e => { titleCache.delete(key); throw e; }));
    }
    return titleCache.get(key);
  }
  const failText = e => (e.message === 'nokey' ? 'TMDB not set up yet' : 'Couldn’t load, try again');
  const TMDB_NOTE = () => {
    const p = el('p', 'xf-src', 'From ');
    p.append(ext('TMDB', 'https://www.themoviedb.org/'), '. This product uses the TMDB API but is not endorsed or certified by TMDB.');
    return p;
  };

  let dialog = null;
  function showTrailer(title, t) {
    if (!dialog) {
      dialog = el('dialog', 'xf-dialog');
      dialog.addEventListener('close', () => { const f = dialog.querySelector('iframe'); if (f) f.remove(); });
      dialog.addEventListener('click', e => { if (e.target === dialog) dialog.close(); });
    }
    const head = el('div', 'xf-head'), close = btn('Close');
    close.addEventListener('click', () => dialog.close());
    head.append(el('h2', '', title + ' · ' + (t.type || 'Trailer')), close);
    const frame = el('div', 'xf-frame'), f = el('iframe');
    f.src = 'https://www.youtube-nocookie.com/embed/' + encodeURIComponent(t.key) + '?autoplay=1&rel=0';
    f.allow = 'autoplay; encrypted-media; picture-in-picture; fullscreen';
    f.allowFullscreen = true; f.title = title + ' trailer'; f.referrerPolicy = 'strict-origin-when-cross-origin';
    frame.append(f);
    const note = TMDB_NOTE();
    note.prepend(ext('Open on YouTube ↗', 'https://www.youtube.com/watch?v=' + encodeURIComponent(t.key)), ' · ');
    dialog.replaceChildren(head, frame, note);
    if (!dialog.isConnected) document.body.append(dialog);
    dialog.showModal();
  }

  let catalogue = null;
  function catalogueIndex() {
    if (catalogue) return catalogue;
    catalogue = new Map();
    const add = (kind, title, year, rec) => {
      if (!title) return;
      const k = kind + '|' + norm(title).replace(/[^a-z0-9]+/g, ' ').trim();
      for (const y of [year, year - 1, year + 1]) if (!catalogue.has(k + '|' + y)) catalogue.set(k + '|' + y, rec);
    };
    if (page === 'foryou') {
      for (const it of forYouItems()) add(it.kind === 't' ? 'tv' : 'movie', it.title, it.year, { id: it.id, score: it.score, critics: it.critics });
    } else if (hasData()) {
      const kind = page === 'tv' ? 'tv' : 'movie';
      for (const m of pageData()) {
        const rec = { id: tt(m.id), score: m.score, critics: m.critics };
        add(kind, m.title, m.year || m.startYear, rec);
        if (m.originalTitle && m.originalTitle !== m.title) add(kind, m.originalTitle, m.year || m.startYear, rec);
      }
    }
    return catalogue;
  }
  function findInCatalogue(r) {
    const idx = catalogueIndex(), k = r.kind + '|';
    for (const t of [r.title, r.original]) {
      if (!t || !r.year) continue;
      const hit = idx.get(k + norm(t).replace(/[^a-z0-9]+/g, ' ').trim() + '|' + r.year);
      if (hit) return hit;
    }
    return null;
  }
  function recsPanel(info) {
    const box = el('div', 'xf-recs');
    const recs = info.recs || [];
    if (!recs.length) { box.append(el('p', 'xf-out', 'TMDB has no suggestions for this one.'), TMDB_NOTE()); return box; }
    const scored = recs.map(r => ({ r, hit: findInCatalogue(r) }));
    scored.sort((a, b) => (!!b.hit - !!a.hit));
    const ol = el('ol');
    for (const { r, hit } of scored.slice(0, 10)) {
      const li = el('li'), name = (r.title || '') + (r.year ? ' (' + r.year + ')' : '');
      if (hit) {
        li.append(ext(name, 'https://www.imdb.com/title/' + hit.id + '/'));
        const sc = [];
        if (typeof hit.score === 'number') sc.push('IMDb ' + hit.score.toFixed(1));
        if (typeof hit.critics === 'number') sc.push('RT ' + hit.critics + '%');
        li.append(el('span', 'xf-sc', sc.join(' · ') || 'In your list'));
      } else {
        li.append(ext(name, 'https://www.themoviedb.org/' + r.kind + '/' + r.tmdb, 'xf-out'));
        li.append(el('span', 'xf-sc', 'Not in your list'));
      }
      ol.append(li);
    }
    box.append(ol, TMDB_NOTE());
    return box;
  }

  // ---------- TVmaze next episodes ----------
  const NEXT_KEY = 'extras-tvnext-v1', NEXT_TTL = 6 * 3600 * 1000;
  let nextStore = {};
  try { nextStore = JSON.parse(localStorage.getItem(NEXT_KEY)) || {}; } catch { nextStore = {}; }
  function saveNext() { try { localStorage.setItem(NEXT_KEY, JSON.stringify(nextStore)); } catch {} }
  function tvNext(id) {
    const c = nextStore[id];
    if (c && Date.now() - c.at < NEXT_TTL) return Promise.resolve(c.v);
    return fetch('/api/tvnext?imdb=' + id, { credentials: 'same-origin' })
      .then(r => (r.ok ? r.json() : null))
      .then(v => { if (v) { nextStore[id] = { at: Date.now(), v }; saveNext(); } return v; })
      .catch(() => null);
  }
  async function mapLimit(list, n, fn) {
    const out = new Array(list.length); let i = 0;
    await Promise.all(Array.from({ length: Math.min(n, list.length) }, async () => { while (i < list.length) { const k = i++; out[k] = await fn(list[k]); } }));
    return out;
  }
  function likedTv() {
    let likes = [];
    try { const s = JSON.parse(localStorage.getItem('foryou-v1')); if (s && Array.isArray(s.likes)) likes = s.likes; } catch {}
    if (page === 'foryou') {
      const by = new Map(forYouItems().map(it => [it.id, it]));
      return likes.filter(id => by.get(id) && by.get(id).kind === 't').map(id => ({ id, title: by.get(id).title }));
    }
    if (page === 'tv' && hasData()) {
      const by = new Map(pageData().map(m => [tt(m.id), m]));
      return likes.filter(id => by.has(id)).map(id => ({ id, title: by.get(id).title }));
    }
    return [];
  }
  const fmtDate = (stamp, date) => {
    const d = stamp ? new Date(stamp) : date ? new Date(date + 'T12:00:00') : null;
    if (!d || isNaN(d)) return 'Date unknown';
    const days = Math.round((new Date(d.toDateString()) - new Date(new Date().toDateString())) / 864e5);
    const label = d.toLocaleDateString('en-AU', { weekday: 'short', day: 'numeric', month: 'short', year: d.getFullYear() !== new Date().getFullYear() ? 'numeric' : undefined });
    return label + (days === 0 ? ' · today' : days === 1 ? ' · tomorrow' : days > 1 && days < 60 ? ' · in ' + days + ' days' : '');
  };
  const epCode = e => 'S' + e.season + (e.number != null ? 'E' + e.number : ' special');
  let comingBox = null, comingBusy = false;
  async function renderComing() {
    if (comingBusy || (page !== 'tv' && page !== 'foryou')) return;
    comingBusy = true;
    try {
      const shows = likedTv().slice(0, 40);
      if (!comingBox) {
        comingBox = el('section', 'xf-coming'); comingBox.setAttribute('aria-label', 'Coming up for shows you like');
        const anchorSection = LIST.closest('section');
        (anchorSection || LIST).before(comingBox);
      }
      if (!shows.length) {
        if (page === 'tv') {
          comingBox.replaceChildren(el('h2', '', 'Coming up'));
          const p = el('p', '', 'Like some shows on ');
          p.append(Object.assign(el('a', '', 'For you'), { href: 'foryou.html' }), ' and their next episode dates will show here.');
          comingBox.append(p);
          comingBox.hidden = false;
        } else comingBox.hidden = true;
        return;
      }
      comingBox.hidden = false;
      if (!comingBox.childElementCount) comingBox.append(el('h2', '', 'Coming up for shows you like'), el('p', '', 'Checking episode dates…'));
      const results = await mapLimit(shows, 3, s => tvNext(s.id).then(v => ({ ...s, v })));
      const now = Date.now() - 864e5;
      const upcoming = results.filter(x => x.v && x.v.next && (Date.parse(x.v.next.airstamp || x.v.next.airdate) || Infinity) >= now)
        .sort((a, b) => (Date.parse(a.v.next.airstamp || a.v.next.airdate) || Infinity) - (Date.parse(b.v.next.airstamp || b.v.next.airdate) || Infinity));
      const waiting = results.filter(x => x.v && x.v.found && !upcoming.includes(x) && x.v.status !== 'Ended');
      const ended = results.filter(x => x.v && x.v.status === 'Ended').length;
      const unknown = results.filter(x => !x.v || !x.v.found).length;
      const parts = [el('h2', '', 'Coming up for shows you like')];
      if (upcoming.length) {
        const ol = el('ol');
        for (const x of upcoming) {
          const li = el('li'), left = el('span');
          left.append(ext(x.title, x.v.url || 'https://www.imdb.com/title/' + x.id + '/'), ' · ' + epCode(x.v.next) + (x.v.next.name ? ' “' + x.v.next.name + '”' : '') + (x.v.network ? ' · ' + x.v.network : ''));
          li.append(left, el('span', 'xf-when', fmtDate(x.v.next.airstamp, x.v.next.airdate)));
          ol.append(li);
        }
        parts.push(ol);
      } else parts.push(el('p', '', 'No dated episodes coming up for your liked shows yet.'));
      if (waiting.length) parts.push(el('p', 'xf-muted', 'Still running, no date yet: ' + waiting.map(x => x.title).join(', ') + '.'));
      const extra = [];
      if (ended) extra.push(ended + ' ended');
      if (unknown) extra.push(unknown + ' not found on TVmaze');
      const src = el('p', 'xf-src', (extra.length ? extra.join(' · ') + ' · ' : '') + 'Episode dates from ');
      src.append(ext('TVmaze', 'https://www.tvmaze.com/'), ', updated every few hours. Australian air dates can differ.');
      parts.push(src);
      comingBox.replaceChildren(...parts);
      for (const x of results) if (x.v && x.v.next) nextById.set(x.id, x.v);
      for (const li of LIST.querySelectorAll('li[data-id]')) addNext(li);
    } finally { comingBusy = false; }
  }
  const nextById = new Map();
  function addNext(li) {
    const v = nextById.get(tt(li.dataset.id)), bar = li.querySelector('.xf-bar');
    if (!v || !v.next || !bar || bar.querySelector('.xf-next')) return;
    bar.append(el('span', 'xf-next', 'Next: ' + epCode(v.next) + ' · ' + fmtDate(v.next.airstamp, v.next.airdate)));
  }

  // ---------- per-row bar ----------
  function byIdSafe(id) { try { return byId.get(id); } catch { return null; } }
  function kindOf(li) {
    if (page === 'tv') return 'tv';
    if (page === 'movies') return 'movie';
    const it = byIdSafe(tt(li.dataset.id));
    return it && it.kind === 't' ? 'tv' : 'movie';
  }
  function anchor(li) { return li.querySelector('.movie-info') || li; }
  function titleOf(li) { const a = li.querySelector('h2 a, h3 a'); return a ? a.textContent : 'Trailer'; }
  function decorate(li) {
    if (li.dataset.xf || !/^tt\d+$/.test(tt(li.dataset.id))) return;
    li.dataset.xf = '1';
    const id = tt(li.dataset.id), kind = kindOf(li), bar = el('div', 'xf-bar');
    const trailer = btn('▶ Trailer'), more = btn('More like this');
    more.setAttribute('aria-expanded', 'false');
    trailer.addEventListener('click', async () => {
      const label = trailer.textContent; trailer.disabled = true; trailer.textContent = 'Loading…';
      try {
        const info = await titleInfo(id, kind);
        trailer.disabled = false;
        if (info.trailer) { trailer.textContent = label; showTrailer(titleOf(li), info.trailer); }
        else { trailer.textContent = 'No trailer on TMDB'; trailer.disabled = true; }
      } catch (e) { trailer.disabled = false; trailer.textContent = failText(e); setTimeout(() => { trailer.textContent = label; }, 4000); }
    });
    more.addEventListener('click', async () => {
      const open = li.querySelector('.xf-recs');
      if (open) { open.remove(); more.setAttribute('aria-expanded', 'false'); return; }
      const label = more.textContent; more.disabled = true; more.textContent = 'Loading…';
      try {
        const info = await titleInfo(id, kind);
        bar.after(recsPanel(info)); more.setAttribute('aria-expanded', 'true');
        more.textContent = label;
      } catch (e) { more.textContent = failText(e); setTimeout(() => { more.textContent = label; }, 4000); }
      finally { more.disabled = false; }
    });
    bar.append(trailer, more);
    const actions = li.querySelector(':scope > .actions');
    if (actions) actions.before(bar); else anchor(li).append(bar);
    addCredits(li);
    addNext(li);
  }

  function scan() { for (const li of LIST.querySelectorAll('li[data-id]')) decorate(li); }
  new MutationObserver(scan).observe(LIST, { childList: true, subtree: true });
  scan();
  setupSearch();
  const idle = g.requestIdleCallback || (f => setTimeout(f, 1200));
  idle(() => loadPeople(), { timeout: 4000 });
  renderComing();
  if (page === 'foryou') {
    document.addEventListener('click', e => { if (e.target.closest && e.target.closest('.like, .nope, [data-unlike], .rated button')) setTimeout(renderComing, 400); });
  }
  addEventListener('storage', e => { if (e.key === 'foryou-v1') renderComing(); });
})();
