// Service worker for the installed app (Add to home screen). It does not cache the site: every
// page still comes fresh from the Worker so Cloudflare Access sign-in keeps working. It only
// shows a friendly page instead of Chrome's error when the phone is offline.
const OFFLINE = `<!doctype html><html lang="en-AU"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#14181c">
<title>Offline · Movie Finder</title></head>
<body style="margin:0;min-height:100vh;display:grid;place-items:center;background:#14181c;color:#e6edf3;font:16px system-ui,sans-serif;text-align:center">
<div style="padding:24px"><h1 style="font-size:22px;margin:0 0 8px">You're offline</h1>
<p style="color:#8b98a5;margin:0 0 20px">Movie Finder needs the internet. Reconnect and try again.</p>
<button onclick="location.reload()" style="background:#00c46a;color:#06140c;border:0;border-radius:999px;padding:10px 22px;font:600 15px system-ui">Try again</button></div>
</body></html>`;

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));
self.addEventListener('fetch', event => {
  if (event.request.mode !== 'navigate') return; // files, data and /api/ go straight to the network
  event.respondWith(
    fetch(event.request).catch(() =>
      new Response(OFFLINE, { headers: { 'Content-Type': 'text/html; charset=utf-8' } }))
  );
});
