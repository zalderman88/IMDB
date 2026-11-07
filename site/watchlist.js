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
    onChange: function (f) { listeners.push(f); }
  };
  window.WatchList = api;
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
    '.mode-switch a[aria-current=page] .wl-n{background:var(--on-accent,#fff);color:var(--accent)}'
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
  function decorate(li) {
    if (li.dataset.wl) return;
    var id = ttOf(li); if (!id) return;
    var h = heading(li); if (!h) return;
    li.dataset.wl = '1';
    h.after(tick(li));
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
  });

  function start() {
    badge();
    var main = document.querySelector('main') || document.body;
    scan(main);
    new MutationObserver(function (list) {
      list.forEach(function (m) { m.addedNodes.forEach(function (n) { if (n.nodeType === 1) scan(n); }); });
    }).observe(main, { childList: true, subtree: true });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
