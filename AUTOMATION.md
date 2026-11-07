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
