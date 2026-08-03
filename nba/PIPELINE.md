# NBA Data Pipeline

Maps how `nba/data/nba_players_master.json` gets built: every source, what
script pulls it, what key joins it, and what happens when a join misses.

Numbers cited below are from the pipeline run on 2026-08-03 (`python
nba/scripts/build_nba_db.py && python nba/scripts/build_nba_match.py`)
and will drift as rosters/scrapes change — re-run those two scripts and
read their printed summaries for current figures; treat the numbers here
as illustrative, not a contract.

---

## 0. Architecture: DuckDB-backed, three scripts — and a key difference from NFL

Same shape as the NFL pipeline, but **NBA's fuzzy name matching doesn't
live in the master-build step at all** — it's already done, upstream, by
each individual scraper:

- `scrape_contracts_spotrac.py`, `scrape_2kratings.py`, and
  `scrape_nbadepthcharts.py` each independently fuzzy-match their own
  scraped names against `nba_stats.json`'s player universe (using shared
  helpers in `nba/scripts/name_utils.py`) and bake the result — a real
  `player_id`, or `null` if unmatched — directly into their own output
  file. By the time any of `contracts_nba.json` / `nba_ratings_2k.json`
  / `nba_depth_chart.json` reaches the master-build step, matching is
  already finished.
- `build_nba_master.py`'s job (and now `build_nba_match.py`'s) is just to
  **join four already-matched sources by `player_id`** and resolve the
  handful of places they can disagree (which position label to trust,
  which `team`/`rotation_status` to trust when nbadepthcharts.com and the
  stats snapshot disagree). No fuzzy matching happens at this stage —
  `resolve_position()`, `resolve_rotation()`, `resolve_team()`, and
  `format_salary()` are the whole of it.

The three scripts:

1. **`build_nba_db.py`** — raw ingestion. Loads `nba_stats.json`,
   `contracts_nba.json`, `nba_ratings_2k.json`, and `nba_depth_chart.json`
   into `nba/data/fieldview.duckdb`, unmodified, one table per source,
   each with a `row_id` (preserving the source file's own order — needed
   because a few sources have genuine duplicate `player_id` rows, see
   §5) and a `loaded_at` timestamp. Unlike NFL, **there are no live API
   pulls inside this step at all** — every NBA source is already a
   static file on disk by the time this runs; `nba_stats.json` itself is
   the one live-pulled source, and it's `fetch_stats.py`'s job, upstream
   of this pipeline entirely.

   **A finding from building this**: each source's own `"unmatched"`
   list (e.g. `contracts_nba.json["unmatched"]`) is a **fully redundant
   subset** of that same source's main list — verified directly (bag-equal
   comparison): every "unmatched" entry's fields exactly match some row
   in the main list that has `player_id: null`. The main list already
   contains every scraped record, matched and unmatched alike; the
   "unmatched" list is just a simplified projection of the same null-`
   player_id` rows for the scraper's own diagnostic printout. Because of
   this, `build_nba_db.py` ingests only the main list per source (4
   tables total, not 7) — ingesting "unmatched" too would double-count
   the same records, not add coverage.
2. **`build_nba_match.py`** — matching (in the "join + resolve" sense
   above). **Imports `resolve_position`, `resolve_rotation`,
   `resolve_team`, and `format_salary` directly from
   `build_nba_master.py`** rather than reimplementing the rules — same
   approach as NFL's `build_match.py`. Writes one row per `nba_stats`
   player into a `player_match` table.
3. **`export_nba_master.py`** — export. Joins `player_match` back to
   `nba_stats` (for passthrough fields: name, jersey number, height,
   weight, per-game stats, games played/started) and writes
   `nba/data/nba_players_master.json` in the exact schema described in
   §4. Takes the output path as a CLI arg; the production workflow
   passes `nba/data/nba_players_master.json` explicitly.

**`build_nba_master.py`'s own status:** it is **not run by the
production workflow** (`scrape.yml`'s "Build NBA player master" step was
replaced by the three scripts above). It's kept in the repo only because
`build_nba_match.py` imports its resolution functions directly —
deleting it would break Phase 2 of the pipeline, not just remove a
redundant script. It still runs standalone if invoked directly (`python
nba/scripts/build_nba_master.py`) and produces byte-identical output to
the DB path.

Verified end-to-end at migration time: DB-path output is byte-identical
to a fresh `build_nba_master.py` run's output, and the site renders
identically against it. See git history for the full phase-by-phase
verification (raw ingestion row counts → matching parity diff → export
parity diff → production dry run).

---

## 1. Sources

| Source | Script | Raw output | Scope |
|---|---|---|---|
| nba_api season stats + roster bio | `fetch_stats.py` | `nba/data/nba_stats.json` → `nba_stats` table | The player universe every other source matches against. `name, team, ppg, rpg, apg, mpg, games_played, games_started, position (coarse), jersey_number, height, weight`, plus an MPG-derived `rotation_status` fallback |
| Spotrac remaining contracts | `scrape_contracts_spotrac.py` (NBA version) | `nba/data/contracts_nba.json` → `nba_contracts` table | Years/cash/guarantee remaining, granular position (PG/SG/SF/PF/C). Already `player_id`-matched by this scraper, not by the master-build step |
| 2kratings.com overall ratings | `scrape_2kratings.py` | `nba/data/nba_ratings_2k.json` → `nba_ratings` table | 2K overall rating. Already `player_id`-matched by this scraper |
| nbadepthcharts.com depth tiers | `scrape_nbadepthcharts.py` | `nba/data/nba_depth_chart.json` → `nba_depth_chart` table | Starter/rotation/bench tier (`depth_rank` 1-4), current team (faster than `nba_stats.json`'s roster snapshot to reflect trades). Already `player_id`-matched by this scraper |

All four are static files on disk before `build_nba_db.py` ever runs —
no live pulls happen inside the DB-build or matching steps for NBA,
unlike NFL (which still fetches the GSIS crosswalk and nflreadpy data
live inside `build_db.py`).

---

## 2. Join keys

| Join | Key | Match strategy |
|---|---|---|
| Spotrac name → `player_id` | name + team | Done inside `scrape_contracts_spotrac.py` itself (`find_match()`): alias substitution (`NBA_NAME_ALIASES`) → `normalize_for_matching()` → fuzzy match, team-qualified first, name-only fallback only if unambiguous. No position filtering at any point — see §5 for why that matters. |
| 2kratings.com name → `player_id` | name + team | Same pattern, inside `scrape_2kratings.py`. |
| nbadepthcharts.com sheet name → `player_id` | name + team | Same pattern, inside `scrape_nbadepthcharts.py`. |
| `player_id` → position | `resolve_position(nba_pos, contract_pos)` | Prefers Spotrac's granular position (PG/SG/SF/PF/C) if present; otherwise falls back to a coarse-group guess (`COARSE_POSITION_FALLBACK`) from whichever of `nba_stats`/Spotrac has a coarse label (G/F/C-style). Not a real position determination for players with no granular source — a last-resort guess, by the code's own comment. |
| `player_id` → `rotation_status`/`rotation_source`/`depth_rank` | `resolve_rotation(pid, mpg_derived_status, depth_by_id)` | Two-tier: if `nba_depth_chart` has this `player_id`, its tier wins (`DEPTH_RANK_TO_STATUS` maps 1→starter, 2→rotation, 3/4→bench), `rotation_source: "nbadepthchart.com"`. Otherwise falls back to `nba_stats.json`'s own MPG-derived guess (starter ≥24 MPG, rotation ≥15, else bench), `rotation_source: "mpg_derived"`. Every player gets a non-null `rotation_status` either way. |
| `player_id` → `team` | `resolve_team(pid, stats_team, depth_by_id)` | Same two-tier preference: `nba_depth_chart`'s team wins if present (catches trades faster than the stats snapshot), else the `nba_stats` roster-snapshot team. |
| `player_id` → `contract_salary`/`contract_years_remaining` | `format_salary(cash_total_remaining, length_remaining)` + direct passthrough | `format_salary` returns `null` if either input is falsy — **including a real `0`, not just `null`** (a handful of matched contracts have `$0`/`0 years` remaining and correctly produce no salary string, not a matching failure; see §5). |

---

## 3. Execution order

```
python nba/scripts/fetch_stats.py                 → writes nba_stats.json
                                                      (everything else matches against this)
python nba/scripts/scrape_contracts_spotrac.py     → writes contracts_nba.json (already player_id-matched)
python nba/scripts/scrape_2kratings.py             → writes nba_ratings_2k.json (already player_id-matched)
python nba/scripts/scrape_nbadepthcharts.py        → writes nba_depth_chart.json (already player_id-matched)
  (these three are independent of each other, any order)

python nba/scripts/build_nba_db.py
  → loads all four files, unmodified, into nba/data/fieldview.duckdb:
    nba_stats, nba_contracts, nba_ratings, nba_depth_chart
    (each with row_id + loaded_at; "unmatched" sub-lists skipped, see §0)

python nba/scripts/build_nba_match.py
  → imports resolve_position / resolve_rotation / resolve_team /
    format_salary directly from build_nba_master.py
  → builds {player_id: row} dicts from nba_contracts/nba_ratings/
    nba_depth_chart, ordered by row_id so a duplicate player_id resolves
    the same way Python's {row["player_id"]: row for row in list} would
    (last row in file order wins)
  → for each nba_stats player: resolve position/rotation/team, look up
    contract + rating by player_id
  → writes the player_match table (one row per nba_stats player)

python nba/scripts/export_nba_master.py nba/data/nba_players_master.json
  → JOIN player_match ON nba_stats (via player_id)
  → reassembles the exact schema in §4
  → writes nba/data/nba_players_master.json
```

Unlike NFL, there's no single "gate" field everything downstream depends
on (no equivalent of GSIS ID) — position, rotation, team, rating, and
contract are five independently-resolved fields, each with its own
match/fallback path, not a cascade off one shared key.

---

## 4. `nba_players_master.json` field-by-field

| Field | Source | If the source misses |
|---|---|---|
| `player_id` | `nba_stats` (nba_api `PLAYER_ID`) | Never null — this is the anchor universe |
| `name` | `nba_stats` | Always populated |
| `team` | `resolve_team()` | Falls back to `nba_stats`'s roster-snapshot team; effectively never null |
| `position` | `resolve_position()` | `null` if neither Spotrac nor `nba_stats` has any position info at all |
| `jersey_number`, `height`, `weight` | `nba_stats` | `null` — no fallback source for these |
| `ppg`, `rpg`, `apg`, `mpg`, `games_played`, `games_started` | `nba_stats` | `null`/`0` per nba_api's own gaps (`games_started` in particular has no bulk endpoint, see CLAUDE.md) |
| `rotation_status`, `rotation_source`, `depth_rank` | `resolve_rotation()` | Never null for `rotation_status` (MPG-derived fallback always applies); `depth_rank` is `null` when `rotation_source` is `"mpg_derived"` |
| `overall_rating` | `nba_ratings`, by `player_id` | `null` if unmatched |
| `contract_salary`, `contract_years_remaining` | `nba_contracts`, by `player_id`, via `format_salary()` | `null` if unmatched, **or** matched but `cash_total_remaining`/`length_remaining` is `0` (see §5) |

---

## 5. Known match-rate ceilings

Figures from the 2026-08-03 run (587 players in `player_match`, from
`nba_stats.json`'s universe) — from `build_nba_match.py`'s own printed
summary. Re-run it for current figures.

- **Position-taxonomy check, done early rather than assumed away**: NFL's
  DB migration found a large, fixable match-rate gap caused by
  EDGE/DI-vs-DE/DL/DT position-label mismatches between sources. Checked
  whether NBA has anything analogous by reading all three matching
  scrapers' `find_match()` functions directly: **none of them filter or
  gate on position at any point** — matching is pure name(+team) fuzzy
  match, full stop. There is no equivalent bug class possible here,
  because there's no position-based search-space restriction to get
  wrong in the first place. Confirmed, not assumed.
- **Contracts: 416/587 (70.9%)** get a real `contract_salary`. This
  number is smaller than it first looks like it should be, for two
  separate, confirmed reasons:
  - 3 `player_id`s appear more than once in `contracts_nba.json`'s raw
    523-row scrape with genuinely different values per row (not scrape
    duplicates of the same data — e.g. a trade mid-scrape). The "last
    row in file order wins" join collapses these the same way
    `build_nba_master.py`'s own dict-comprehension join always did — 523
    scraped rows → 440 distinct matched players.
  - `format_salary()`'s `if not x` check treats a real `$0`/`0 years`
    remaining the same as missing data — roughly two dozen of the 440
    matched contracts have a zero (not null) `cash_total_remaining` or
    `length_remaining` and correctly produce no salary string. Not a
    matching failure, a real "nothing left on this deal" case (e.g. an
    expiring minimum contract).
- **2K ratings: 514/587 (87.6%)**. Clean 1:1 — no duplicate `player_id`s
  in this source, so the scraper's own match count and the final
  populated-field count agree exactly.
- **Rotation source: 440/587 (75.0%) from nbadepthcharts.com**, the
  remaining 147/587 (25.0%) from the MPG-derived fallback — every player
  still gets a non-null `rotation_status` either way, unlike NFL's fields
  which go genuinely null on a miss. Of `nba_depth_chart`'s own 78
  unmatched rows (out of 518 scraped): the majority are 2025 draft picks
  not yet present in `nba_stats.json`'s roster snapshot at scrape time
  (a real timing gap between the two sources, not a matching bug), with
  a smaller number of veterans genuinely absent from that snapshot
  entirely (a real data-source ceiling). See `scrape_nbadepthcharts.py`'s
  own module docs / CLAUDE.md's "NBA Depth Chart Source" section for the
  detailed breakdown.
- **No OL-style "intentionally skipped" position** exists on the NBA
  side — every player in `nba_stats.json`'s universe goes through all
  four resolution steps regardless of position, so there's no analog to
  NFL's "OL skipped from GSIS matching by design."
