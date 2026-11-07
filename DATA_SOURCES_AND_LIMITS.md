# Data provenance and limits

Snapshot date: 7 November 2026.

| Item | Count |
|---|---:|
| Final qualifying records | 37,844 |
| Default results after genre/country rules | 21,890 |
| IMDb movie/short records imported with 1,000+ votes | 56,562 |
| IMDb imported records meeting 6.0+ | 37,287 |
| AU JW records processed | 57,065 |
| RT title-search records processed | 91,057 |
| RT film pages with checked review counts | 395 |
| Checked RT films present in the final app | 394 |
| Films with AU classification metadata | 17,935 |
| English original-language group | 18,988 |
| Foreign original-language group | 14,107 |
| Unknown original language | 4,749 |

## Sources

- IMDb official non-commercial bulk title basics/ratings datasets: https://datasets.imdbws.com/ and https://developer.imdb.com/non-commercial-datasets/ . Import types are movie, tvMovie, video, short and tvShort. This is the eligible movie subset, not IMDb's complete multi-million-record database.
- JustWatch AU public catalogue/GraphQL: https://www.justwatch.com/au and https://apis.justwatch.com/graphql . The snapshot includes valid pages plus a 1,000-vote recovery pass for years that hit pagination limits. It is not a guaranteed complete AU catalogue. Production-country and offer metadata can be missing.
- RT public title search and public film scorecards: https://www.rottentomatoes.com/ . The title search caps results per year; it does not provide review counts. Only 395 film-page count checks completed before access restrictions. Most displayed RT scores therefore cannot qualify a film through RT alone. This is intentionally disclosed rather than treating an unknown count as sufficient.
- Wikidata original-language statements: https://www.wikidata.org/wiki/Property:P364 matched through IMDb identifiers https://www.wikidata.org/wiki/Property:P345 . English grouping uses the English entity, ISO `en` or an explicitly recorded English subclass. Some films have multiple original languages. Missing or ambiguous matches remain Unknown. This says nothing about dubbed audio/subtitle options on a service.

At this snapshot there is 1 independently RT-qualified film that fails the IMDb score/count route: Venom: Let There Be Carnage passes through its checked Popcornmeter. The OR logic also has synthetic boundary tests. Do not mistake the OR feature for comprehensive RT-only catalogue coverage.

Review counts are sample-size filters, not a guarantee of quality or that a rating matches the user's taste. Audience bands are lower bounds, not exact counts. A missing service link means no confirmed inclusion was loaded, not proof of unavailability. Some alternate titles/editions remain unmatched.

Four Indian animated films with missing country tags were explicitly marked IN using their known IMDb IDs in the fusion script. Other unknown production countries are allowed by the user's latest default. No language is guessed from country, title spelling or an alternate translated title.

This handover contains factual metadata, not downloaded film media, posters or critic-review text. Preserve the included IMDb attribution and source notices. The package is for the user's individual personal project; it does not grant upstream data licences or publisher API access.

## Trailers, "More like this", Coming up and people search (added 7 Nov 2026)

- **Actor/director search** (`tools/build_people.py` → `_site/people.json`): IMDb non-commercial bulk files `title.principals` and `name.basics`, downloaded in CI with the other IMDb files. Directors plus the first five billed cast for titles on the Movies and TV pages. `site/extras.js` adds the names to the search text and shows them on each row; tapping a name searches for it.
- **Trailer and More like this**: TMDB API, looked up on demand by `worker/index.js` at `/api/title` (`/find` by IMDb id, then videos + recommendations) and cached at the edge for 7 days. Needs the `TMDB_API_KEY` CI variable, which the deploy job sets as a Worker secret. Suggestions are matched back to the site's own catalogue by title and year (±1); unmatched ones say "Not in your list". TMDB attribution is shown wherever its data appears.
- **Coming up**: TVmaze API (no key, CC BY-SA), on demand via `/api/tvnext`, cached 6 hours at the edge and in the browser. Uses the shows liked on For you (`foryou-v1` in localStorage). Air dates are TVmaze's, usually the home network's, so Australian dates can differ.
- Nothing here is scraped; all calls are documented public APIs, made only when someone taps or opens a page.
