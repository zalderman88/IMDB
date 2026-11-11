// Signed-in account chip, shared by every page: shows the email Cloudflare Access signed you in
// with, next to the theme button, plus a Log out link. Reads /cdn-cgi/access/get-identity
// (served by Cloudflare Access, not the Worker); shows nothing when opened offline or unlocked.
// Also makes the site installable as a phone app: registers sw.js and adds an "Install app" link
// beside Log out (Chrome's install prompt where offered, otherwise short how-to steps).
(() => {
  'use strict';
  let installPrompt = null;
  const standalone = () => matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;
  window.addEventListener('beforeinstallprompt', e => { e.preventDefault(); installPrompt = e; });
  window.addEventListener('appinstalled', () => {
    installPrompt = null;
    document.querySelectorAll('.acct-install').forEach(a => a.remove());
  });
  if ('serviceWorker' in navigator && window.isSecureContext) {
    navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(() => {});
  }
  const installHelp = () => {
    const ios = /iPhone|iPad|iPod/.test(navigator.userAgent);
    alert(ios
      ? 'To install: tap the Share button in Safari, then "Add to Home Screen".'
      : 'To install: open the browser menu (⋮ at the top right in Chrome), then tap "Install app" or "Add to home screen".');
  };
  const installLink = () => {
    const a = document.createElement('a');
    a.className = 'acct-install';
    a.href = '#install';
    a.textContent = 'Install app';
    a.addEventListener('click', ev => {
      ev.preventDefault();
      if (!installPrompt) { installHelp(); return; }
      const p = installPrompt;
      installPrompt = null;
      p.prompt();
      p.userChoice.then(c => { if (c.outcome === 'accepted') a.remove(); }).catch(() => {});
    });
    return a;
  };
  const theme = document.getElementById('theme');
  if (!theme || !/^https?:$/.test(location.protocol)) return;
  fetch('/cdn-cgi/access/get-identity', { credentials: 'same-origin', cache: 'no-store' })
    .then(r => (r.ok ? r.json() : null))
    .then(id => {
      const email = id && typeof id.email === 'string' ? id.email : '';
      if (!email) return;
      const style = document.createElement('style');
      style.textContent = `
.acct-tools{display:flex;align-items:center;gap:10px;min-width:0}
.acct{display:flex;flex-direction:column;align-items:flex-end;min-width:0;font-size:12px;line-height:1.35;text-align:right}
.acct-email{color:var(--muted);max-width:42vw;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.acct-out{color:var(--accent);font-weight:600;text-decoration:none;padding:2px 0}
.acct-out:hover,.acct-install:hover{text-decoration:underline}
.acct-links{display:flex;gap:12px;justify-content:flex-end;white-space:nowrap}
.acct-install{color:var(--accent);font-weight:600;text-decoration:none;padding:2px 0}`;
      document.head.appendChild(style);
      const box = document.createElement('div');
      box.className = 'acct';
      const who = document.createElement('span');
      who.className = 'acct-email';
      who.textContent = email;
      who.title = 'Signed in as ' + email;
      const out = document.createElement('a');
      out.className = 'acct-out';
      out.href = '/cdn-cgi/access/logout';
      out.textContent = 'Log out';
      const links = document.createElement('div');
      links.className = 'acct-links';
      if (!standalone()) links.append(installLink());
      links.append(out);
      box.append(who, links);
      const tools = document.createElement('div');
      tools.className = 'acct-tools';
      theme.replaceWith(tools);
      tools.append(box, theme);
    })
    .catch(() => {});
})();
