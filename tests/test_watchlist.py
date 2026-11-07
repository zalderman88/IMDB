"""Checks for the Watch list page and the tick script it relies on."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
import build_watchlist  # noqa: E402

page = build_watchlist.build()
assert '@@STYLE@@' not in page and page.count('<style>') == 2, 'For You styles not inlined'
assert 'id="wl-list"' in page and 'watchlist.js' in page and 'extras.js' in page
for name in ['movie_finder', 'tv_finder', 'foryou', 'new_streaming', 'top20']:
    t = (ROOT / f'research/{name}_template.html').read_text(encoding='utf-8')
    assert t.count('<a href="watchlist.html">Watch list</a>') == 1, name + ': missing Watch list nav link'
    assert '<script src="watchlist.js" defer></script>' in t, name + ': missing watchlist.js'
js = (ROOT / 'site/watchlist.js').read_text(encoding='utf-8')
assert "'watchlist-v1'" in js
print('watchlist tests passed')
