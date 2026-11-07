/* Posters and tap-to-expand synopses for the Movies, TV and For You lists.
   Data comes from posters/index.json and posters/syn/<n>.json (built by tools/fetch_posters.py).
   The pages work exactly as before if these files are missing (for example offline). */
(function () {
  'use strict';
  var PREFIX = { 'w:': 'https://upload.wikimedia.org/wikipedia/', 'm:': 'https://static.tvmaze.com/uploads/images/' };
  var SOURCE = { 't:': ['TMDB', 'https://www.themoviedb.org/'], 'w:': ['Wikipedia', 'https://en.wikipedia.org/wiki/'], 'm:': ['TVmaze', 'https://www.tvmaze.com/'] };
  var index = null, shards = {};

  function full(code) {
    var p = code && code.slice(0, 2);
    if (p === 't:') return 'https://image.tmdb.org/t/p/w185/' + code.slice(2);
    return PREFIX[p] ? PREFIX[p] + code.slice(2) : '';
  }
  // small (1x list), large (2x list and the expanded view)
  function sized(url, small) {
    if (url.indexOf('image.tmdb.org') > -1) return url.replace('/w185/', small ? '/w92/' : '/w342/');
    return url.replace(/\/\d+px-([^/]+)$/, '/' + (small ? 120 : 250) + 'px-$1');
  }
  function ttOf(li) { var m = /tt\d+/.exec(li.dataset.id || ''); return m && m[0]; }
  function shard(tt) {
    var n = parseInt(tt.slice(2), 10) % index.shards;
    if (!shards[n]) shards[n] = fetch('posters/syn/' + n + '.json').then(function (r) { return r.ok ? r.json() : {}; }).catch(function () { delete shards[n]; return {}; });
    return shards[n];
  }

  function poster(tt) {
    var url = full(index.p[tt].replace(/^!/, ''));
    if (!url) return null;
    var box = document.createElement('span');
    box.className = 'pf-poster';
    box.setAttribute('aria-hidden', 'true');
    var img = document.createElement('img');
      img.loading = 'lazy';
      img.decoding = 'async';
      img.alt = '';
      img.referrerPolicy = 'no-referrer';
      if (/\/\d+px-|image\.tmdb\.org/.test(url)) { img.src = sized(url, true); img.srcset = sized(url, true) + ' 1x, ' + sized(url, false) + ' 2x'; }
      else img.src = url;
      img.onerror = function () { box.classList.add('pf-none'); img.remove(); };
      box.append(img);
    return box;
  }

  function toggle(li) {
    var tt = ttOf(li), panel = li.querySelector(':scope > .pf-synopsis');
    var open = !li.classList.contains('pf-open');
    li.classList.toggle('pf-open', open);
    var btn = li.querySelector('.pf-more');
    if (btn) { btn.setAttribute('aria-expanded', String(open)); btn.firstChild.textContent = open ? 'Less' : 'Synopsis'; }
    var img = li.querySelector('.pf-poster img');
    if (open && img && img.srcset) img.src = img.srcset.split(', ')[1].split(' ')[0];
    if (!open || panel.dataset.loaded) return;
    panel.dataset.loaded = '1';
    panel.textContent = 'Loading…';
    shard(tt).then(function (s) {
      var e = s[tt];
      panel.textContent = '';
      if (!e) { panel.append(text('p', 'pf-empty', 'No synopsis found for this title.')); return; }
      panel.append(text('p', '', e[0]));
      var src = SOURCE[(e[1] || '').slice(0, 2)];
      if (src) {
        var credit = text('p', 'pf-credit', 'From ');
        var a = text('a', '', src[0]);
        a.href = src[1] + e[1].slice(2);
        a.target = '_blank';
        a.rel = 'noopener noreferrer';
        credit.append(a);
        panel.append(credit);
      }
    });
  }
  function text(tag, cls, t) { var e = document.createElement(tag); if (cls) e.className = cls; e.textContent = t; return e; }

  function decorate(li) {
    if (li.dataset.pf || !index) return;
    var tt = ttOf(li);
    if (!tt || !(tt in index.p)) return;  // nothing found: leave the row as it was
    li.dataset.pf = '1';
    var head = li.querySelector('.movie-info') || li;
    var pic = poster(tt);
    if (pic) { li.classList.add('pf-has-poster'); if (head === li) li.prepend(pic); else head.prepend(pic); }
    if (index.p[tt].charAt(0) === '!') return;  // poster only, no synopsis to expand
    li.classList.add('pf-row');
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'pf-more';
    btn.setAttribute('aria-expanded', 'false');
    btn.append('Synopsis', text('span', 'pf-caret', '▾'));
    var panel = text('div', 'pf-synopsis', '');
    panel.setAttribute('aria-live', 'polite');
    if (head === li) {
      var anchor = li.querySelector(':scope > .actions');
      li.insertBefore(btn, anchor);
      li.insertBefore(panel, anchor);
    } else {
      head.append(btn);
      head.after(panel);
    }
    btn.addEventListener('click', function (ev) { ev.stopPropagation(); toggle(li); });
    li.addEventListener('click', function (ev) {
      if (ev.target.closest('a,button,input,select,label,summary,.pf-synopsis')) return;
      if (window.getSelection && String(window.getSelection())) return;
      toggle(li);
    });
  }
  function scan(root) {
    if (!index || !root.querySelectorAll) return;
    if (root.matches && root.matches('li[data-id]')) decorate(root);
    root.querySelectorAll('li.movie-row[data-id], li.card[data-id]').forEach(decorate);
  }

  function credit() {
    var host = document.getElementById('about') || document.querySelector('main');
    if (!host || document.querySelector('.pf-attrib')) return;
    var p = text('p', 'pf-attrib', 'Posters and synopses come from ');
    [['TMDB', 'https://www.themoviedb.org/'], ['Wikipedia', 'https://en.wikipedia.org/'], ['Wikidata', 'https://www.wikidata.org/'], ['TVmaze', 'https://www.tvmaze.com/']].forEach(function (s, i) {
      if (i) p.append(i === 3 ? ' and ' : ', ');
      var a = text('a', '', s[0]); a.href = s[1]; a.target = '_blank'; a.rel = 'noopener noreferrer'; p.append(a);
    });
    p.append('. This product uses the TMDB API but is not endorsed or certified by TMDB. Wikipedia text is shared under CC BY-SA; posters belong to their studios. Titles with nothing found are shown without them.');
    host.append(p);
  }

  fetch('posters/index.json').then(function (r) { return r.ok ? r.json() : null; }).then(function (data) {
    if (!data || !data.p || !Object.keys(data.p).length) return;
    index = data;
    document.documentElement.classList.add('has-posters');
    scan(document.body);
    credit();
    new MutationObserver(function (list) {
      list.forEach(function (m) { m.addedNodes.forEach(function (n) { if (n.nodeType === 1) scan(n); }); });
    }).observe(document.body, { childList: true, subtree: true });
  }).catch(function () {});
})();
