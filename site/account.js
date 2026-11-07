// Signed-in account chip, shared by every page: shows the email Cloudflare Access signed you in
// with, next to the theme button, plus a Log out link. Reads /cdn-cgi/access/get-identity
// (served by Cloudflare Access, not the Worker); shows nothing when opened offline or unlocked.
(() => {
  'use strict';
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
.acct-out:hover{text-decoration:underline}`;
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
      box.append(who, out);
      const tools = document.createElement('div');
      tools.className = 'acct-tools';
      theme.replaceWith(tools);
      tools.append(box, theme);
    })
    .catch(() => {});
})();
