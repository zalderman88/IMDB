# Automatic refresh (GitLab CI to Cloudflare)

`.gitlab-ci.yml` runs from a GitLab pipeline schedule **twice a week** (cron `0 4 * * 2,5`, Australia/Perth: Tuesday and Friday 4:00 am), on every push to `main`, and on demand (**Build > Pipelines > Run pipeline**). It needs CI/CD variables `CLOUDFLARE_API_TOKEN` (Account > Workers Scripts > Edit) and `CLOUDFLARE_ACCOUNT_ID`.

Each run:

1. Downloads IMDb's official non-commercial datasets (`title.basics.tsv.gz`, `title.ratings.tsv.gz`, `title.episode.tsv.gz`) once and rewrites `research/imdb/movies_1k.json` (`tools/refresh_imdb.py`). It refuses to write if the result has under 90% of the previous record count.
2. Builds the TV series data (`tools/refresh_tv.py` writes `research/imdb/tv_1k.json`: series/miniseries with 1,000+ votes, start/end years, the latest episode year and season counts).
3. Rebuilds the movie and TV apps from the snapshots (`rebuild.py`).
4. Runs `tools/check_refresh.py`: every film has 1,000+ IMDb votes and passes a score route, the catalogue has not shrunk by more than 5%, and streaming/RT/classification/language facts are unchanged (baseline `data/non_imdb_facts.json`).
5. Runs the Node functional tests, then the TV checks: at least 1,000 qualifying shows, the offline fixture test (`tests/test_tv_pipeline.py`) and the TV UI checks (`tests/verify_tv_finder.mjs`).
6. Deploys `_site/` to the Cloudflare Worker `zac-movies` with `wrangler deploy` (static assets, wrangler.jsonc): movies at https://zac-movies.zalderman.workers.dev/ and TV at /tv.html. Cloudflare Access limits the site to allow-listed emails.

If any step fails, nothing is deployed and the previous site stays up. The refreshed IMDb data is not committed back; each run starts from the official datasets, so the repo does not grow.

## What is not refreshed automatically

- **Australian streaming availability (JustWatch)**, **Rotten Tomatoes scores/counts**, **AU classifications** and **original languages** stay at the 7 November 2026 snapshot. The JustWatch and RT harvesters use unofficial endpoints/pages without an API agreement, and RT blocked page checks; running them unattended from CI servers would not respect those sources' terms. The site states the snapshot date for these facts.
- A new film that crosses the 1,000-vote / 6.0 threshold does appear, but without streaming offers, RT data or language until a manual refresh (see REFRESH_GUIDE.md).

## ChatGPT task

The original monthly ChatGPT task (1st of each month, Perth time) still exists in ChatGPT and updates the ChatGPT copy only. It is not connected to this repo. Turn it off in ChatGPT if you only want this version.

## New on streaming (new.html)

`new.html` lists movies and series added to Australian **subscription** streaming services in the last 31 days, with on/off checkboxes per service (saved in the browser under `new-streaming-v1`). The data comes from the official **Streaming Availability API** by Movie of the Night (https://www.movieofthenight.com/about/api), not from scraping:

1. `tools/fetch_new_streaming.py` calls `/countries/au` once and `/changes?change_type=new` for new titles and new seasons (25 changes a page, at most 80 pages a run). It needs the masked CI/CD variable `STREAMING_AVAILABILITY_API_KEY` (free plan, 1,000 requests a month). Without it the page says it is not set up yet and the build still passes.
2. Scheduled and manual pipelines always fetch. Pushes to `main` reuse the GitLab CI cache (`cache/new_streaming.json`) if it is under 13 days old, so code changes don't spend requests. On HTTP 401/403/429 it stops and keeps the previous data.
3. `tools/build_new_streaming.py` adds IMDb ratings from the official `title.ratings` dataset and writes `new.html`. `tests/test_new_streaming.py` checks both scripts offline against a fake API.

## Top 20 (top20.html)

`tools/build_top20.py` ranks the 20 most popular movies and TV shows across Australian streaming
services. Sources (no scraping; published files and documented APIs only):

1. Netflix's official weekly Top 10 for Australia (`all-weeks-countries.tsv` from netflix.com/tudum/top10), no key.
2. The services' own AU top lists from the Streaming Availability API `GET /shows/top` (Netflix, Prime Video,
   Disney+, Apple TV+, Paramount+, HBO Max), using the same `STREAMING_AVAILABILITY_API_KEY` as the New page.
   About 12 requests per scheduled run; cached in `cache/top20_sa.json` so code pushes spend none.
3. Optional `TMDB_API_KEY`: TMDB popularity for titles on AU services with no chart (Stan, Binge, Foxtel Now,
   BritBox, ABC iview, SBS On Demand, Shudder, DocPlay), counted at 60%.
4. IMDb ratings/votes from the datasets the build already downloads (also used to identify Netflix titles).

Scoring: 10 points for #1 down to 1 for #10 on each chart; best chart per service; services add up; Netflix
adds 25% of last week's points; quality bonus (IMDb - 6) x 1.5, capped at 4.5, needs 1,000+ votes. India is
excluded. A source failing never fails the build; the page lists which sources worked. Tests: `tests/test_top20.py`.

### TMDB: live where-to-watch, and New without a second key

`tools/fetch_tmdb_au.py` sweeps TMDB's official API (`/discover` with `watch_region=AU`, subscription only) for Netflix, Prime Video, Disney+, Stan, Paramount+, HBO Max, Apple TV, Binge and Foxtel Now, then looks up IMDb ids (cached). It needs the masked CI/CD variable `TMDB_API_KEY` (v3 key or v4 read token). The result `cache/tmdb_au.json` is kept by the GitLab CI cache.

* **Where to watch:** when a complete sweep exists, `research/streaming_au.py` replaces the 7 Nov 2026 JustWatch offers on the movie page (JustWatch deep links are kept where the service still has the film; others link to TMDB's AU watch page) and adds services to TV shows. `tools/check_refresh.py` then stops comparing `offers` with the baseline. Without a key nothing changes.
* **New page:** TMDB has no "date added", so a title counts as new when it appears on a service it wasn't on at the previous sweep. The first sweep is the baseline. The Streaming Availability data is used instead if that key is ever added.
* The first sweep makes roughly 1,500 discover calls and up to 20,000 IMDb-id lookups (about 10 minutes); later sweeps only look up new titles. On HTTP 401/403 it stops and keeps the previous data; an incomplete sweep never replaces a complete one.
