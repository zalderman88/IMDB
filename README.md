# Movie Finder (Australia)

**Live site (private, Cloudflare Access): https://zac-movies.zalderman.workers.dev/** — searchable IMDb + Rotten Tomatoes movie finder for Australian streaming services. **TV finder: https://zac-movies.zalderman.workers.dev/tv.html** — IMDb series and miniseries that aired from 2020, plus shows from 2000 onwards rated above 8.0 (see USER_REQUIREMENTS.md). Works on Android and desktop browsers. IMDb ratings refresh automatically twice a week; see [AUTOMATION.md](AUTOMATION.md).

The built HTML is not committed. Run `python rebuild.py` to create `Australian_Movies_Android.html` locally, or download it from the live site. The TV page needs the IMDb TV snapshot first: run `python tools/refresh_tv.py` (downloads about 250 MB of official IMDb datasets), then `python rebuild.py` also writes `TV_Shows_Android.html`.

---

## Handover notes

Ready-to-open app: **Australian_Movies_Android.html**. Unzip first, then open it in a browser. The browser needs no installation, server, Python or Node to use the app. Filtering/search work offline; external review/streaming links need the internet.

For Claude, start with **CLAUDE_HANDOFF_PROMPT.txt** and **CLAUDE.md**.

## Latest requested defaults

- Country: **Exclude India · allow unknown countries**. Fresh opens and Reset filters use `country=exclude`.
- Original language: **All languages**. English, Foreign language and Unknown are optional filters.
- Exclude Romance, Horror and Documentary; all years; no service/classification restriction.
- Every film needs at least **1,000 IMDb votes**. Within that existing list, qualify by IMDb 6.0+ **OR** Tomatometer 60%+ with 50+ critic reviews. Popcornmeter (60%+ with 1,000+ audience ratings) is available but off by default (changed 7 Nov 2026 at the user's request).

This is a filter/metadata change only: no films were added or removed, and no existing ratings or counts changed. See CATALOGUE_INTEGRITY.json and tools/check_catalogue_lock.py.

Browser-saved preferences can override defaults after a user changes a filter; Reset restores the defaults above.

## Snapshot

Data checked: 7 November 2026. This package contains **37,844 qualifying records**, with **21,890 default results** before any additional filters. It processes 56,562 IMDb movie/short records, 57,065 AU JustWatch records and 91,057 RT search records. RT review counts were checked on 395 pages; 394 of those are in the final app. RT coverage is partial. See DATA_SOURCES_AND_LIMITS.md.

## Rebuild and verify offline

Python 3.10+ and Node.js 18+ are sufficient; there are no npm dependencies.

```sh
python rebuild.py --verify
```

Or run `python rebuild.py` to rebuild without the Node checks. Run `node tests/verify_movie_finder.mjs` to check the existing app. Node 24 was used for the exported checks. The scripts locate the package relative to their own files and do not require the original workspace path.

## Package map

| Path | Purpose |
|---|---|
| Australian_Movies_Android.html | Complete working app, including embedded movie data |
| research/movie_finder_template.html | Editable HTML/CSS/JavaScript UI template |
| research/build_extended_movies.py | Data fusion, qualification and HTML generation |
| research/imdb/movies_1k.json | Imported IMDb records with 1,000+ votes |
| research/jw_consolidated.json | Deduplicated AU metadata/offers snapshot |
| research/rt_movies.json | Partial RT title-search snapshot |
| research/rt_counts/ | Checked score/count/badge facts from individual RT pages |
| research/classification_movies.json | AU classifications, matched through known JW nodes |
| research/language_movies.json | Original-language facts, matched by IMDb IDs |
| data/ | Extracted final data, metadata and refresh recipe for easy inspection |
| tests/verify_movie_finder.mjs | Browser-logic checks using a lightweight DOM harness |
| research/tv_finder_template.html, research/build_tv.py | TV finder UI template and builder (writes TV_Shows_Android.html, published as tv.html) |
| tools/refresh_tv.py | Builds research/imdb/tv_1k.json from IMDb basics/ratings/episode datasets |
| tests/test_tv_pipeline.py, tests/verify_tv_finder.mjs | Offline TV fixture test and TV UI checks |
| .gitlab-ci.yml | Twice-weekly IMDb refresh and Cloudflare deploy |
| tools/refresh_imdb.py, tools/check_refresh.py | IMDb dataset refresh and post-refresh checks |
| REFRESH_GUIDE.md | Source-refresh procedure and remaining acquisition gaps |
| ARCHITECTURE.md | How the runtime, source matching and filters work |

The very large official gzip downloads and redundant per-page caches are omitted. The normalized input snapshots needed for an offline rebuild are included. No API credentials, browser sessions, account cookies or private transfer helpers are bundled.
