"""Build the Watch list page (watchlist.html).

The page has no data of its own: the list lives in each browser (localStorage 'watchlist-v1',
see site/watchlist.js). It reuses the For You page's <style> block so the Slate & Green look
and the nav stay in step with the other pages without a second copy to maintain.

Usage: python tools/build_watchlist.py [--out _site/watchlist.html]
"""
import argparse
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
FORYOU = ROOT / 'research/foryou_template.html'
TEMPLATE = ROOT / 'research/watchlist_template.html'


def build() -> str:
    style = re.search(r'<style>.*?</style>', FORYOU.read_text(encoding='utf-8'), re.S)
    if not style:
        raise SystemExit('No <style> block found in ' + str(FORYOU))
    page = TEMPLATE.read_text(encoding='utf-8')
    if page.count('@@STYLE@@') != 1:
        raise SystemExit('watchlist_template.html must contain @@STYLE@@ once')
    return page.replace('@@STYLE@@', style.group(0))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--out', default=str(ROOT / 'Watchlist_Android.html'))
    out = pathlib.Path(ap.parse_args().out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(), encoding='utf-8')
    print('Wrote', out)


if __name__ == '__main__':
    main()
