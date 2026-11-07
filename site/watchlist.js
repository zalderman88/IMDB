/* Watch list: a "Watch list" tick on every title (Movies, TV, For you, New, Top 20) and the
   watchlist.html page that shows what you ticked. Saved in this browser only (localStorage
   'watchlist-v1'), like the other settings, so each phone or browser has its own list.
   Loaded with <script src="watchlist.js" defer> on every page. Rows are found the same way
   posters.js and extras.js find them (li[data-id] with an IMDb id) and the page's own
   rendering code is never changed. */
(function () {
  'use strict';
  var KEY = 'watchlist-v1';
  var listeners = [];

  function read() {
    try {
      var s = JSON.parse(localStorage.getItem(KEY) || 'null');
      if (s && Array.isArray(s.items)) return s.items.filter(function (x) { return x && /^tt\d+$/.test(x.id); });
    } catch (e) { /* private window or bad data: start empty */ }
    return [];
  }
  var items = read();
  function write() {
    try { localStorage.setItem(KEY, JSON.stringify({ v: 1, items: items })); } catch (e) { /* storage blocked */ }
    changed();
  }
  function changed() { listeners.forEach(function (f) { try { f(items); } catch (e) { /* keep going */ } }); }
  function index(id) { for (var i = 0; i < items.length; i++) if (items[i].id === id) return i; return -1; }

  var api = {
    all: function () { return items.slice(); },
    has: function (id) { return index(id) > -1; },
    add: function (item) { if (!item || !/^tt\d+$/.test(item.id) || api.has(item.id)) return; item.added = item.added || Date.now(); items.push(item); write(); },
    remove: function (id) { var i = index(id); if (i < 0) return null; var gone = items.splice(i, 1)[0]; write(); return gone; },
    restore: function (item, at) { if (!item || api.has(item.id)) return; items.splice(Math.min(at == null ? items.length : at, items.length), 0, item); write(); },
    indexOf: index,
    onChange: function (f) { listeners.push(f); },
    // New-season alerts for TV shows: { alert: true, seen: <latest season aired when checked> }
    setAlert: function (id, on) {
      var i = index(id); if (i < 0) return;
      var it = items[i];
      if (!on) { delete it.alert; delete it.seen; write(); return; }
      it.alert = true; delete it.seen; write();
      api.seasonInfo(id).then(function (v) { baseline(id, v); });
    },
    seasonsSeen: function (id) {  // "Got it" on an alert: the current season becomes the new baseline
      var i = index(id); if (i < 0) return;
      api.seasonInfo(id).then(function (v) { if (v && v.prev && index(id) > -1) { items[index(id)].seen = v.prev.season; write(); } });
    },
    setWatched: function (id, on) { var i = index(id); if (i < 0) return; delete items[i].back; if (on) items[i].watched = Date.now(); else delete items[i].watched; write(); },
    seasonInfo: seasonInfo,
    seasonStatus: seasonStatus
  };
  window.WatchList = api;

  // ---------- TV seasons (TVmaze, through the Worker's /api/tvnext, cached here for 6 hours) ----------
  var NEXT_KEY = 'watchlist-tvnext-v1', NEXT_TTL = 6 * 3600 * 1000, nextStore = {}, pending = {};
  try { nextStore = JSON.parse(localStorage.getItem(NEXT_KEY) || '{}') || {}; } catch (e) { nextStore = {}; }
  function seasonInfo(id) {
    var c = nextStore[id];
    if (c && Date.now() - c.at < NEXT_TTL) return Promise.resolve(c.v);
    if (!/^https?:$/.test(location.protocol)) return Promise.resolve(c ? c.v : null);
    if (pending[id]) return pending[id];
    pending[id] = fetch('/api/tvnext?imdb=' + id, { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (v) {
        delete pending[id];
        if (v && v.imdb === id) {
          nextStore[id] = { at: Date.now(), v: v };
          for (var k in nextStore) if (Date.now() - nextStore[k].at > 14 * 86400000) delete nextStore[k];
          try { localStorage.setItem(NEXT_KEY, JSON.stringify(nextStore)); } catch (e) { /* full or blocked */ }
          return v;
        }
        return c ? c.v : null;
      })
      .catch(function () { delete pending[id]; return c ? c.v : null; });
    return pending[id];
  }
  function baseline(id, v) {
    var i = index(id);
    if (i < 0 || !items[i].alert || items[i].seen != null || !v || !v.found) return;
    items[i].seen = v.prev ? v.prev.season : 0;
    write();
  }
  var dateFmt = new Intl.DateTimeFormat('en-AU', { day: 'numeric', month: 'short', year: 'numeric' });
  function when(e) {
    var d = e.airstamp ? new Date(e.airstamp) : e.airdate ? new Date(e.airdate + 'T12:00:00') : null;
    return d && !isNaN(d) ? dateFmt.format(d) : '';
  }
  // What to say about a show's seasons. kind: new (a season came out since alerts were turned on),
  // soon (a new season has a date), airing, ended, quiet, unknown.
  function seasonStatus(it, v) {
    if (!v || !v.found) return { kind: 'unknown', text: v ? 'No season dates found for this show' : '' };
    var prev = v.prev, next = v.next;
    if (it && it.alert && it.seen != null && prev && prev.season > it.seen)
      return { kind: 'new', season: prev.season, text: 'Season ' + prev.season + ' is out' + (prev.number > 1 ? ' (' + prev.number + ' episodes so far)' : '') };
    if (next && (next.number === 1 || (prev && next.season > prev.season)))
      return { kind: 'soon', season: next.season, text: 'Season ' + next.season + (when(next) ? ' starts ' + when(next) : ' is coming, date not set yet') };
    if (next) return { kind: 'airing', season: next.season, text: 'Season ' + next.season + ' is on now · next episode ' + (when(next) || 'date not set') };
    if (/ended/i.test(v.status || '')) return { kind: 'ended', text: 'Ended' + (prev ? ' after season ' + prev.season : '') };
    return { kind: 'quiet', text: 'No new season announced yet' + (prev ? ' · last episode ' + when(prev) : '') };
  }
  addEventListener('storage', function (e) { if (e.key === KEY) { items = read(); changed(); } });

  // ---------- styles (shared by every page; uses each page's colour tokens) ----------
  var css = document.createElement('style');
  css.textContent = [
    '.wl-tick{display:inline-flex;align-items:center;gap:7px;width:max-content;min-height:36px;margin:6px 0 2px;padding:5px 12px 5px 9px;border:1px solid var(--line);border-radius:18px;background:transparent;color:var(--muted);font-size:13px;font-weight:650;line-height:1.2;cursor:pointer;user-select:none;-webkit-tap-highlight-color:transparent}',
    '.wl-tick input{appearance:none;-webkit-appearance:none;flex:none;width:18px;height:18px;margin:0;border:1.5px solid var(--muted);border-radius:5px;background:transparent;display:grid;place-content:center;cursor:pointer}',
    '.wl-tick input::after{content:"";width:9px;height:5px;margin-top:-2px;border:solid var(--on-accent,#fff);border-width:0 0 2px 2px;transform:rotate(-45deg);opacity:0}',
    '.wl-tick input:checked{background:var(--accent);border-color:var(--accent)}.wl-tick input:checked::after{opacity:1}',
    '.wl-tick:hover{color:var(--ink);border-color:var(--accent)}',
    '.wl-tick.on{color:var(--accent);border-color:var(--accent);background:var(--green-bg,transparent)}',
    '.wl-tick:has(input:focus-visible){outline:3px solid var(--focus);outline-offset:2px}',
    '.wl-tick input:focus-visible{outline:none}',
    '.mode-switch .wl-n{display:inline-grid;place-content:center;min-width:19px;height:19px;margin-left:5px;padding:0 5px;border-radius:10px;background:var(--accent);color:var(--on-accent,#fff);font-size:11px;font-weight:800;font-family:Inter,system-ui,sans-serif;letter-spacing:0}',
    '.mode-switch a[aria-current=page] .wl-n{background:var(--on-accent,#fff);color:var(--accent)}',
    '.wl-alerts{display:grid;gap:8px;margin:0 0 16px}',
    '.wl-alert{display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding:12px 14px;border:1px solid var(--accent);border-radius:12px;background:var(--green-bg,var(--surface));color:var(--ink);font-size:14px}',
    '.wl-alert .wl-msg{flex:1 1 200px;min-width:0}.wl-alert b{font-weight:750}',
    '.wl-alert a,.wl-alert button{min-height:38px;padding:6px 14px;border-radius:999px;font:inherit;font-size:13px;font-weight:700;cursor:pointer;text-decoration:none;display:inline-flex;align-items:center}',
    '.wl-alert a{background:var(--accent);color:var(--on-accent,#fff)}.wl-alert button{border:1px solid var(--line);background:transparent;color:var(--ink)}'
  ].join('\n');
  document.head.appendChild(css);

  // ---------- reading a row ----------
  function ttOf(li) { var m = /tt\d+/.exec(li.dataset.id || ''); return m && m[0]; }
  function heading(li) { return li.querySelector('h2, h3'); }
  function txt(node) { return node ? node.textContent.replace(/\s+/g, ' ').trim() : ''; }
  function kindOf(li) {
    if (li.dataset.kind) return li.dataset.kind === 'tv' || li.dataset.kind === 'series' ? 'tv' : 'movie';
    var k = li.querySelector('.kind');
    if (k) return /\b(tv|series)\b/.test(k.className) ? 'tv' : 'movie';
    if (document.getElementById('shows')) return 'tv';
    return 'movie';
  }
  function titleOf(li) {
    var h = heading(li); if (!h) return '';
    var a = h.querySelector('a'); if (a) return txt(a);
    var c = h.cloneNode(true); c.querySelectorAll('.kind, .yr, .wl-tick').forEach(function (n) { n.remove(); });
    return txt(c);
  }
  function yearOf(li) {
    var spots = ['.yr', '.score.released strong', '.movie-meta', '.meta'];
    for (var i = 0; i < spots.length; i++) {
      var m = /\b(18|19|20)\d{2}(\s*[–-]\s*((18|19|20)\d{2})?)?/.exec(txt(li.querySelector(spots[i])));
      if (m) return m[0].replace(/\s+/g, '');
    }
    return '';
  }
  function scoreOf(li) {
    var s = li.querySelector('.score.imdb strong, .scores strong, .imdb strong, .imdbs strong');
    var v = s && parseFloat(s.textContent);
    return v > 0 && v <= 10 ? v : null;
  }
  // Rotten Tomatoes: Movies rows have Tomatometer/Popcornmeter blocks with review-page links; For you shows "RT 94%".
  function rtOf(li) {
    var out = {};
    function pct(sel) { var s = li.querySelector(sel); var v = s && parseInt(s.textContent.replace(/[^0-9]/g, ''), 10); return v >= 0 && v <= 100 && /\d/.test(s.textContent) ? v : null; }
    var c = pct('.score.critics strong'); if (c == null) c = pct('.scores .rt');
    var a = pct('.score.audience strong');
    if (c != null) out.critics = c;
    if (a != null) out.audience = a;
    var link = li.querySelector('.score.critics a[href*="rottentomatoes.com"], .score.audience a[href*="rottentomatoes.com"], a[href*="rottentomatoes.com/m/"], a[href*="rottentomatoes.com/tv/"]');
    if (link) out.rt = link.href;
    return out;
  }
  function genresOf(li) {
    var g = txt(li.querySelector('.movie-genres'));
    if (g && !/unknown/i.test(g)) return g.split(' · ').slice(0, 3);
    return [];
  }
  function posterOf(li) {
    var img = li.querySelector('.pf-poster img, img.poster');
    var src = img && (img.currentSrc || img.src);
    return src && /^https:/.test(src) ? src : '';
  }
  function itemOf(li) {
    var id = ttOf(li);
    var it = { id: id, title: titleOf(li) || id, kind: kindOf(li), year: yearOf(li) };
    var sc = scoreOf(li); if (sc) it.score = sc;
    var g = genresOf(li); if (g.length) it.genres = g;
    var rt = rtOf(li); for (var k in rt) it[k] = rt[k];
    var p = posterOf(li); if (p) it.poster = p;
    var page = location.pathname.split('/').pop() || 'index.html';
    if (page !== 'watchlist.html') it.from = page;
    return it;
  }

  // ---------- the tick ----------
  function tick(li) {
    var id = ttOf(li);
    var label = document.createElement('label');
    label.className = 'wl-tick';
    var box = document.createElement('input');
    box.type = 'checkbox';
    box.dataset.wl = id;
    var span = document.createElement('span');
    span.textContent = 'Watch list';
    label.append(box, span);
    label.addEventListener('click', function (ev) { ev.stopPropagation(); });
    box.addEventListener('change', function () {
      if (box.checked) api.add(itemOf(li));
      else if (window.WatchListPage) window.WatchListPage.removed(id);
      else api.remove(id);
    });
    sync(box);
    return label;
  }
  function sync(box) {
    var on = api.has(box.dataset.wl);
    box.checked = on;
    box.parentNode.classList.toggle('on', on);
    box.title = on ? 'On your watch list (tap to remove)' : 'Add to your watch list';
  }
  // Titles already on the list pick up scores and links they were saved without (e.g. added from Top 20).
  function refresh(li, id) {
    if (window.WatchListPage) return;
    var i = index(id); if (i < 0) return;
    var it = items[i], fresh = itemOf(li), changed = false;
    ['score', 'critics', 'audience', 'rt', 'year', 'poster'].forEach(function (k) {
      if (fresh[k] != null && fresh[k] !== '' && it[k] !== fresh[k] && (it[k] == null || it[k] === '' || k === 'score' || k === 'critics' || k === 'audience' || k === 'rt')) { it[k] = fresh[k]; changed = true; }
    });
    if (!it.genres && fresh.genres) { it.genres = fresh.genres; changed = true; }
    if (changed) write();
  }
  function decorate(li) {
    if (li.dataset.wl) return;
    var id = ttOf(li); if (!id) return;
    refresh(li, id);
    var h = heading(li); if (!h) return;
    li.dataset.wl = '1';
    var row = li.querySelector('.wl-ticks');
    if (row) row.prepend(tick(li)); else h.after(tick(li));
  }
  function scan(root) {
    if (!root.querySelectorAll) return;
    if (root.matches && root.matches('li[data-id]')) decorate(root);
    root.querySelectorAll('li[data-id]').forEach(decorate);
  }

  // ---------- nav tab count ----------
  function badge() {
    document.querySelectorAll('.mode-switch a[href="watchlist.html"]').forEach(function (a) {
      var n = a.querySelector('.wl-n');
      if (!items.length) { if (n) n.remove(); a.removeAttribute('aria-label'); return; }
      if (!n) { n = document.createElement('span'); n.className = 'wl-n'; n.setAttribute('aria-hidden', 'true'); a.append(n); }
      n.textContent = items.length > 99 ? '99+' : String(items.length);
      a.setAttribute('aria-label', 'Watch list, ' + items.length + (items.length === 1 ? ' title' : ' titles'));
    });
  }

  api.onChange(function () {
    document.querySelectorAll('input[data-wl]').forEach(sync);
    badge();
    clearTimeout(recheck); recheck = setTimeout(checkAlerts, 300);
  });

  function start() {
    badge();
    checkAlerts();
    var main = document.querySelector('main') || document.body;
    scan(main);
    new MutationObserver(function (list) {
      list.forEach(function (m) { m.addedNodes.forEach(function (n) { if (n.nodeType === 1) scan(n); }); });
    }).observe(main, { childList: true, subtree: true });
  }
  // ---------- new-season banner on every page ----------
  var box = null, checking = false, recheck = null;
  // A watched TV show comes back (no longer greyed out) when an episode airs after it was marked watched.
  var reviving = false;
  function aired(e) { var d = e && (e.airstamp ? Date.parse(e.airstamp) : e.airdate ? Date.parse(e.airdate + 'T23:59:00') : NaN); return isNaN(d) ? 0 : d; }
  function checkWatched() {
    var list = items.filter(function (x) { return x.kind === 'tv' && x.watched; }).slice(0, 60);
    if (reviving || !list.length) return;
    reviving = true;
    var i = 0, changed = false;
    function worker() {
      if (i >= list.length) return Promise.resolve();
      var it = list[i++];
      return seasonInfo(it.id).then(function (v) {
        var k = index(it.id), cur = items[k];
        if (!cur || !cur.watched || !v || !v.prev) return;
        var t = aired(v.prev);
        if (t > cur.watched && t <= Date.now()) {
          delete cur.watched;
          cur.back = { season: v.prev.season, number: v.prev.number, at: t };
          changed = true;
        }
      }).then(worker);
    }
    Promise.all([worker(), worker(), worker()]).then(function () { reviving = false; if (changed) write(); });
  }
  function checkAlerts() {
    checkWatched();
    var watched = items.filter(function (x) { return x.kind === 'tv' && x.alert; }).slice(0, 60);
    if (checking || !watched.length) { showAlerts([]); return; }
    checking = true;
    var out = [], i = 0;
    function worker() {
      if (i >= watched.length) return Promise.resolve();
      var it = watched[i++];
      return seasonInfo(it.id).then(function (v) {
        baseline(it.id, v);
        var cur = items[index(it.id)] || it, s = seasonStatus(cur, v);
        if (s.kind === 'new') out.push({ it: cur, s: s });
      }).then(worker);
    }
    Promise.all([worker(), worker(), worker()]).then(function () { checking = false; showAlerts(out); });
  }
  function noteBadge(n) {
    document.querySelectorAll('.mode-switch a[href="notifications.html"]').forEach(function (a) {
      var b = a.querySelector('.wl-n');
      if (!n) { if (b) b.remove(); a.removeAttribute('aria-label'); return; }
      if (!b) { b = document.createElement('span'); b.className = 'wl-n'; b.setAttribute('aria-hidden', 'true'); a.append(b); }
      b.textContent = String(n);
      a.setAttribute('aria-label', 'Notifications, ' + n + (n === 1 ? ' new season' : ' new seasons'));
    });
  }
  function showAlerts(list) {
    noteBadge(list.length);
    if (/notifications\.html$/.test(location.pathname)) list = [];  // that page lists them itself
    if (!list.length) { if (box) box.remove(); box = null; return; }
    var head = document.querySelector('header.masthead');
    if (!head) return;
    if (!box) { box = document.createElement('section'); box.className = 'wl-alerts'; box.setAttribute('aria-label', 'New seasons'); box.setAttribute('role', 'status'); }
    if (head.nextElementSibling !== box) head.after(box);
    box.replaceChildren();
    list.forEach(function (x) {
      var row = document.createElement('div'); row.className = 'wl-alert';
      var msg = document.createElement('span'); msg.className = 'wl-msg';
      var b = document.createElement('b'); b.textContent = x.it.title;
      msg.append('🔔 New season: ', b, ' · ' + x.s.text);
      var go = document.createElement('a'); go.href = 'notifications.html'; go.textContent = 'Notifications';
      var ok = document.createElement('button'); ok.type = 'button'; ok.textContent = 'Got it';
      ok.addEventListener('click', function () { api.seasonsSeen(x.it.id); row.remove(); if (!box.children.length) { box.remove(); box = null; } });
      row.append(msg);
      row.append(go);
      row.append(ok);
      box.append(row);
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
