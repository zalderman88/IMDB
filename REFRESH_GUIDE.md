# Updating the data

## UI-only work

Edit `research/movie_finder_template.html`; run `python rebuild.py --verify`. This rebuilds from the included snapshots and preserves their date. It does not make source data current.

## Existing monthly routine

The active ChatGPT task is documented in AUTOMATION.md. It can read the embedded `refresh-recipe`, refresh what is accessible, validate and replace the original saved HTML. Copying this ZIP to Claude does not transfer that task. Do not create another schedule without the user's request.

## Manual live-refresh procedure

Perform this in a new copy/versioned work directory so a failed refresh does not destroy the working snapshots. The following is a procedure, not a claim that every upstream source offers a complete export.

1. Download the current IMDb title.ratings.tsv.gz and title.basics.tsv.gz from the official dataset URLs. Join on `tconst`; keep the supported movie types with >=1,000 votes; preserve primary/original titles, year, runtime, genres, adult flag, rating and vote count in the schema of `research/imdb/movies_1k.json`. IMDb AKAs language fields are translated-title metadata and must NOT be treated as original-language facts.
2. Retrieve AU JW movie metadata with `research/harvest_jw.py`. It uses 100-title pages, splits year ranges and records incomplete leaves. `research/repair_jw.py` retries oversized year buckets for IMDb-vote-qualified records. That recovery pass is not a full independent RT universe. Extend acquisition only with legitimate source filters; never label an incomplete harvest complete.
3. After fresh JW pages exist, run `python tools/consolidate_jw_cache.py` to create `research/jw_consolidated.json`. Do not overwrite the good consolidated snapshot with empty results. Old per-page caches must not be mistaken for a new monthly acquisition.
4. Download the current public RT browse page into `research/rt_browse.html`; `research/harvest_rt.py` discovers its current public client search configuration and retrieves the permitted movie search results. The raw page and public search configuration were deliberately not bundled, because they can change. The API has caps; keep the partial-coverage flags.
5. RT review-count refresh uses `research/fetch_rt_counts.py` and optional `pip install -r requirements-refresh.txt`. Its exported concurrency is reduced to two, and it stops new film-page requests at the first HTTP 403/429. It checks a selected subset, not every RT record. It skips cached scorecards, so checking old cached facts again requires an explicit controlled cache-refresh change; do not merely run it and claim old facts were newly verified. Retain old checked dates on fallback. Do not evade restrictions with alternate access channels.
6. Build once to produce `research/extended_catalogue.json`, then use `research/fetch_classifications.py` to attach AU classification facts for grounded JW nodes. It reads the consolidated snapshot. Rebuild after this completes.
7. `research/fetch_languages.py` matches the current final IMDb IDs to Wikidata original-language facts. It streams the SPARQL XML response and retains only matching films, then resolves language labels/groups. It is a live network operation; it is not needed for normal rebuilds. Validate that known English and foreign examples are present, and preserve Unknown/ambiguous cases.
8. Update `research/source_snapshot.json` only after genuine source work. Preserve separate RT last-check dates and show a coverage/source-status gap if any acquisition was blocked. Keep old working records with accurate dates rather than inventing new facts.
9. Only an explicitly authorised data refresh may replace the existing movie universe; update the catalogue lock after confirming its new records still meet the global vote floor and score/count rules. For UI/filter changes leave the lock intact. Run `python rebuild.py --verify`; inspect the browser if available. Check current source totals, unknown counts and genuine links. Refresh the convenience extracts under `data/` if distributing another handover. 

The live scripts are implementation references adapted for portability, not a guarantee of future upstream API schemas. They can require maintenance when public fields/caps change. A complete authorised RT feed/export would be required before claiming complete RT database coverage.

## Runtime vs download updates

The browser never refreshes this dataset in the background. An updated saved/hosted HTML must replace the old file, or the user must download the new version. There is no service worker or backend in this export. The original Get latest version link requires the user's original ChatGPT account and is not a public hosting URL.
