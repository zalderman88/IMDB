# Accepted requirements and defaults

## Scope and browser behaviour

Movies for Australian streaming accounts, regardless of production country, with known Indian productions excluded by default. The expanded catalogue can be browsed without a service restriction; selecting services restricts to their recorded Australian subscription inclusions. The initial four services were Netflix, Prime Video, Paramount+ and Stan; Disney+, HBO Max and Apple TV subscription were added. Amazon Prime is the existing Prime Video service, not a duplicate provider.

Detailed list rows, not tiles; Android touch controls; search, dark theme, pagination, saved filter preferences, direct review links where genuinely matched and filtered CSV export.

## Independent rating routes

| Route | Default score minimum | Default count minimum | Score slider |
|---|---:|---:|---|
| IMDb | 6.0 | 1,000 IMDb votes | 6.0–10.0, step 0.1 |
| Tomatometer | 60% | 50 critic reviews | 60–100%, step 1 |
| Popcornmeter (off by default) | 60% | 1,000 audience ratings | 60–100%, step 1 |

Every film must first have at least 1,000 IMDb votes. The three route checkboxes select which scores can qualify a film within that eligible list. A film passes if ANY selected route has both its score and count minimum. A low/missing score in another system cannot veto it. Each route's count minimum is adjustable upward. Unknown counts cannot pass. Banded audience counts use their lower bound. The displayed audience score and its count must describe the same verified/all-audience group.

Certified Fresh and Verified Hot are reported source designations, not inferred from a high percentage. Fresh/Hot correspond to scores of at least 60% for their respective measures. The user's phrase "certified hot" is displayed using RT's actual name, Verified Hot.

## Other filters

- Country: **Exclude India · allow unknown countries** (`exclude`), both fresh/default state and Reset. Optional `strict` requires known non-Indian production countries; `all` removes the country restriction.
- Language: All languages (`all`, default), English (`english`), Foreign language (`foreign`), Unknown (`unknown`). English includes multilingual films with English among the recorded original languages. Foreign means recorded original languages exist and none is English. Unknown is kept separate. This does not filter streamer dubbing/subtitle tracks.
- Australian classifications: multi-select G, PG, M, MA15+, R18+, X18+, Unclassified and Unknown. None selected means all. Use AU metadata and preserve unknowns; do not map US R/PG-13 to AU ratings.
- Year: two sliders set inclusive minimum/maximum years. Moving a handle past the other moves the other bound as well. A separate option includes unknown years.
- Services: any selected service matches; none selected browses the expanded catalogue. Subscription inclusions only, with rental/purchase/add-on channels excluded.
- Genres: 16 high-level categories, not a large subgenre checklist. An included category matches any selected inclusion; exclusions always win. A comedy-horror can match Comedy, but is removed by a Horror exclusion. Default exclusions: Romance, Horror, Documentary.
- Reset: clear search, service/classification selections and genre inclusions; restore all years, All languages, country `exclude`, the three score/count defaults and the three genre exclusions. Theme is a separate preference.
- Sorting: IMDb, Tomatometer, Popcornmeter and release year in either direction; IMDb votes in either direction; most critic reviews; most audience ratings; title A–Z. Missing numeric values sort last.

Browser-stored preferences override fresh defaults after the user chooses settings. A fresh open and Reset are both tested with the latest country/language defaults.
