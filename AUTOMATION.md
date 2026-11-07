# Automatic refresh (GitHub Actions)

`.github/workflows/refresh.yml` runs **twice a week** (Monday and Thursday 20:00 UTC, which is Tuesday and Friday around 4:00 am Perth time), on every push to `main`, and on demand from the Actions tab (**Run workflow**).

Each run:

1. Downloads IMDb's official non-commercial datasets (`title.basics.tsv.gz`, `title.ratings.tsv.gz`) and rewrites `research/imdb/movies_1k.json` (`tools/refresh_imdb.py`). It refuses to write if the result has under 90% of the previous record count.
2. Rebuilds the app from the snapshots (`rebuild.py`).
3. Runs `tools/check_refresh.py`: every film has 1,000+ IMDb votes and passes a score route, the catalogue has not shrunk by more than 5%, and streaming/RT/classification/language facts are unchanged (baseline `data/non_imdb_facts.json`).
4. Runs the Node functional tests.
5. Publishes the result to GitHub Pages: https://zalderman88.github.io/IMDB/

If any step fails, nothing is deployed and the previous site stays up. The refreshed IMDb data is not committed back; each run starts from the official datasets, so the repo does not grow.

## What is not refreshed automatically

- **Australian streaming availability (JustWatch)**, **Rotten Tomatoes scores/counts**, **AU classifications** and **original languages** stay at the 7 November 2026 snapshot. The JustWatch and RT harvesters use unofficial endpoints/pages without an API agreement, and RT blocked page checks; running them unattended from GitHub's servers would not respect those sources' terms. The site states the snapshot date for these facts.
- A new film that crosses the 1,000-vote / 6.0 threshold does appear, but without streaming offers, RT data or language until a manual refresh (see REFRESH_GUIDE.md).

## ChatGPT task

The original monthly ChatGPT task (1st of each month, Perth time) still exists in ChatGPT and updates the ChatGPT copy only. It is not connected to this repo. Turn it off in ChatGPT if you only want this version.
