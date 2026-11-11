# How it works

## Offline build

`rebuild.py` sets a package-relative Python import path and calls `research/build_extended_movies.py`. The builder reads the included normalized source snapshots, matches identities, attaches metadata, applies the base qualification predicate and fills `research/movie_finder_template.html`. It writes the complete root HTML and `research/extended_catalogue.json`. No network call is made by the normal rebuild.

`data/catalogue.json`, `data/metadata.json` and `data/refresh_recipe.json` are convenient extracts of the shipped snapshot. The source snapshots under `research/` are the inputs to the full fusion builder. For a data change, update those inputs and rebuild; do not assume editing only the convenience extracts will change the app.

The exported builder uses `research/source_snapshot.json` for its date so rebuilding on a later day does not imply the data was refreshed. The public transport helper is `fetch_movies.request`. The former scratch-only paths were removed from the exported build and tests. The original JW per-page caches were consolidated into one deduplicated JSON source without changing their movie facts.

## Identity and qualification

1. All app results must have at least 1,000 IMDb votes. Start from IMDb movie, TV movie, video, short and TV short records with at least 1,000 votes; omit adult-marked IMDb records.
2. Match JW records through IMDb IDs, using JW scores as fallback only where no official imported record exists. Attach AU offers, countries, genres, runtime and viewing URLs. Exclude obvious WWE/UFC/AEW/NXT event broadcasts from movie records.
3. RT title matches use exact normalized title/alias AND release year when unambiguous. Ambiguous cases are skipped. Confirmed scorecards supply count/badge facts and genuine reviews-page URLs. No RT URL is invented from a film title.
4. Attach AU classification facts from already grounded JW node IDs. Attach original-language facts from Wikidata P345 IMDb identifiers and P364 language statements; skip ambiguous Wikidata film-ID matches.
5. Keep records that can pass at least one base score-and-count route. Browser sliders/count controls then narrow this set. Genre/country/service/year/language/classification filters are applied by the browser, so changing them does not refetch data.

## Browser runtime

The HTML contains CSS, JavaScript and three inert JSON blocks: `catalogue`, `metadata`, `refresh-recipe`. There is no framework, backend, API key, runtime fetch, service worker or PWA installation package.

`majorGenres()` groups raw genres in the background. `criteria()` reads controls. `routes()` evaluates the three independent score/count paths. `matchesFilters()` combines their OR result with the other filters. `comparator()` handles ordering and missing values. `apply()` filters/sorts the full embedded catalogue and resets pagination. `render()` draws only 50 rows at first; Show more appends 50. Search still covers every record.

Movie content is written through DOM text nodes; links are accepted as HTTPS URLs. Country and language facts are independent. A missing country is permitted by default; a missing language is shown as Unknown. Saved settings use a namespaced `localStorage` key where the browser permits it; storage failure is caught.

The list renders IMDb/Tomatometer/Popcornmeter together. An unchecked/unknown RT count cannot qualify a film through RT, but an IMDb-qualified film can still display its sourced RT percentage. A stale RT date is displayed if the overall snapshot is later than that film's checked date.

## Functional verification

`tests/verify_movie_finder.mjs` runs the actual embedded runtime in Node's VM with a small DOM harness. It checks boundary cases, independent OR routes, 123 slider positions, adjustable counts, services, grouped genres, classifications, language, years, country defaults, reset, sorting, pagination, links, persistence and CSV actions.

These tests do not prove pixel-level Android appearance or long-lived local-file restoration after a Chrome restart. Full browser rendering could not be executed in the original environment. A real Android browser check remains useful after layout changes.

## Posters and synopses

`tools/fetch_posters.py` runs in CI after the pages are built. It reads IMDb ids from the built Movies and TV catalogues, looks up new ones (TMDB `/find` by IMDb id when the masked CI variable `TMDB_API_KEY` is set, about 35 requests a second; then, for titles TMDB doesn't fully cover, Wikidata P345 → English Wikipedia lead image and first paragraph; TVmaze by IMDb id for TV shows still missing a poster), and writes `_site/posters/index.json` (poster per title, about 1.5 MB) plus 512 synopsis shards in `_site/posters/syn/`. Lookups are cached in `cache/posters.json.gz` (GitLab CI cache, shared with New on streaming) on top of the committed seed `data/posters_seed.json.gz`; titles with nothing found are retried after 60 days. Lookups stop after a time budget and never fail the build.

`site/posters.js` and `site/posters.css` are linked from all three templates. The script fetches `posters/index.json` after the page loads and decorates list rows (`li[data-id]`) as they are added, using a MutationObserver, so the templates' own rendering code is untouched. Tapping a row (or its Synopsis button) loads one ~30 KB shard and expands the synopsis with a source link. Rows with no poster or synopsis are left exactly as before, and the pages work unchanged when the files are missing (for example a downloaded copy opened offline). Images are hotlinked from image.tmdb.org, upload.wikimedia.org and static.tvmaze.com with lazy loading. TMDB's required notice ("This product uses the TMDB API but is not endorsed or certified by TMDB") is added to each page's Coverage section.
