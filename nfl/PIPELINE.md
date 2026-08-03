# NFL Data Pipeline

Maps how `nfl/data/players_master.json` gets built: every source, what
script pulls it, what key joins it, and what happens when a join misses.

Numbers cited below are from the pipeline run on 2026-08-03 (`python
nfl/scripts/build_db.py && python nfl/scripts/build_match.py`) and will
drift as rosters/scrapes change — re-run those two scripts and read their
printed summaries for current figures; treat the numbers here as
illustrative, not a contract.

---

## 0. Architecture: DuckDB-backed, four scripts

As of the DuckDB migration, three scripts build `players_master.json`,
not one:

1. **`build_db.py`** — raw ingestion. Loads every source's current output
   (the 32 `nfl/data/{abbr}.json` team files, `madden.json`,
   `spotrac_contracts.json`) into `nfl/data/fieldview.duckdb`, plus three
   sources that used to be pulled live at build time — the dynastyprocess
   GSIS crosswalk CSV, nflreadpy rosters, nflreadpy snap counts — are now
   fetched once here and cached as DB tables (`gsis_crosswalk`,
   `nflreadpy_rosters`, `snap_counts`) instead of being re-fetched on
   every run. No matching, no joins — one table per source, unmodified,
   with a `loaded_at` timestamp.
2. **`build_match.py`** — matching. **Imports `find_gsis`,
   `find_madden_player`, `find_pfr_id`, `find_spotrac_contract`, and
   every alias/position-map constant directly from `build_master.py`**
   rather than reimplementing the rules — the matching logic is literally
   the same code, only the data source changed (DB tables instead of
   live scrapes/files). Writes results to a `player_match` table, one row
   per final (post-depth-dedup) player.
3. **`export_master.py`** — export. Joins `player_match` back to the raw
   `ourlads_players` table (for passthrough fields like `cap_number`,
   `stats`, `attainment`) and writes `nfl/data/players_master.json` in
   the exact schema described in §4. Takes the output path as a CLI arg;
   the production workflow passes `nfl/data/players_master.json`
   explicitly.

**`build_master.py`'s own status:** it is **not run by the production
workflow** (`scrape.yml`'s "Build player master" step was replaced by
the three scripts above). It's kept in the repo only because
`build_match.py` imports its matching functions directly — deleting it
would break Phase 2 of the pipeline, not just remove a redundant script.
It still runs standalone if invoked directly (`python
nfl/scripts/build_master.py`) and produces an identical
`players_master.json` to the DB path — useful for local debugging or as
a sanity check, not because anything currently depends on running it.

Verified end-to-end at migration time: DB-path output is byte-identical
to a fresh `build_master.py` run's output, and the site renders
identically against it. See git history for the full phase-by-phase
verification (raw ingestion row counts → matching parity diff → export
parity diff → production dry run).

---

## 1. Sources

| Source | Script | Raw output | Scope |
|---|---|---|---|
| OurLads depth charts | `scrape_depth.py` | `nfl/data/{abbr}.json` (one file per team, 32 files) → `ourlads_players` table | Roster + depth order + position — the spine every other source joins onto |
| nflreadpy rosters | `scrape_stats.py`'s season pull; cached by `build_db.py` into `nflreadpy_rosters` | `nfl/data/fieldview.duckdb` (was: pulled live at build time, not written to disk) | GSIS ID, `entry_year`, `college`, `birth_date`, `pfr_id` |
| dynastyprocess crosswalk (GitHub CSV) | `build_db.py` (`load_gsis_crosswalk`) | `nfl/data/fieldview.duckdb`'s `gsis_crosswalk` table (was: fetched live every run, not cached) | Primary GSIS ID source; community-maintained, fantasy-oriented — see the framing note in §5 |
| nflreadpy weekly stats | `scrape_stats.py` | merged directly into `nfl/data/{abbr}.json`'s `depth_chart[pos][i].stats` | Season stat totals, position-specific |
| nflreadpy snap counts | `build_db.py` (`load_snap_counts`) | `nfl/data/fieldview.duckdb`'s `snap_counts` table (was: pulled live at build time, not written to disk) | `snap_pct`, plus a name+team crosswalk for OL (see §2) |
| Madden ratings | `scrape_madden.py` | `nfl/data/madden.json` → `madden_ratings` table | Overall rating, jersey, position label, per-position rank |
| Over The Cap | `scrape_otc.py` | merged directly into `nfl/data/{abbr}.json`'s `depth_chart[pos][i].cap_number` | Current-year cap number |
| Spotrac remaining contracts | `scrape_contracts_spotrac.py` | `nfl/data/spotrac_contracts.json` → `spotrac_contracts` table | Years/cash/guarantee remaining on current contract |

Two scripts (`scrape_stats.py`, `scrape_otc.py`) still mutate the 32
per-team JSONs directly, the pattern `merge_madden.py` used to follow
before it was split out. `build_db.py`'s `ourlads_players` table reads
their output via the same `stats`/`cap_number` fields off the team
files, faithfully, rather than joining a standalone table — same
inconsistency as before the DB migration, not something this migration
changed or was meant to fix.

`spotrac_contracts.json` also captures an `age` column from Spotrac's
contracts page (`scrape_contracts_spotrac.py:86`) that neither
`build_master.py` nor `build_match.py` reads — the contract-merge logic
only pulls `length_remaining`/`cash_total_remaining`/
`cash_guaranteed_remaining`/`pct_guaranteed_remaining`. A second,
currently-dormant age source. Not wired in, not evaluated for quality —
noted here, not acted on.

---

## 2. Join keys

Unchanged from before the migration — same functions, same rules,
imported by `build_match.py` rather than run inline.

| Join | Key | Match strategy |
|---|---|---|
| OurLads name → GSIS ID | name + position + team | `find_gsis()`: alias substitution (`NAME_ALIASES`) → `normalize_for_matching()` → fuzzy match within position via rapidfuzz `token_sort_ratio`, ≥95% is an auto-accept, 80-94% retries scoped to the player's own team, <80% is no match. Crosswalk tried first, nflreadpy rosters as fallback — **both now apply `CROSSWALK_POS_ALIASES`/`ROSTERS_POS_ALIASES` for EDGE/DI** (see §5). |
| OurLads name → Madden rating | name + team | `find_madden_player()`: exact or word-subset match only, own team first, then league-wide fallback — no fuzzy/rapidfuzz scoring at all. **Now applies `NAME_ALIASES` the same way `find_gsis()` does** (fixed since this doc was last written — see §5). Gated by `find_madden_duplicate_names()`: if the normalized name collides across two different teams' rosters, cross-team fallback is disabled for that name. |
| player_key (master dict key) | GSIS ID if resolved, else `{normalized-name}-{standard_pos}-{team}` slug | Whichever player already holds a given key keeps it; a later duplicate only overwrites if its `depth` is lower (i.e. it's the starter). |
| GSIS ID → `draft_year`/`college`/`birth_date`(→`age`)/`pfr_id` | GSIS ID | Direct dict lookup against nflreadpy rosters, deduped `keep='first'` per GSIS ID. No matching involved — either the GSIS ID exists as a roster row or it doesn't. |
| `pfr_id` → `snap_pct` | `pfr_id` (from the lookup above) | Direct index into a season-average snap-share table. |
| Any player missing a `pfr_id` (mainly OL — `load_rosters`' `pfr_id` fill rate is ~0% for OL specifically) → `snap_pct` | name + team | `find_pfr_id()`: independent fuzzy match (same rapidfuzz strategy as GSIS) against `load_snap_counts`' own player/team/position columns, which have real OL coverage where `load_rosters` doesn't. Second, structurally separate path — not gated behind a GSIS match at all. |
| OurLads name → Spotrac remaining contract | name + position + team | `find_spotrac_contract()`, same `_match_in_df` rapidfuzz strategy as GSIS (own-team retry at 80-94%). No shared ID; Spotrac has none to offer. |

**Name normalization is not one function** — three coexist in
`nfl/scripts/name_utils.py`, each shaped for a different match:
- `normalize_for_matching()` — strips ALL whitespace too (`"pat surtain"` →
  `"patsurtain"`). Used for GSIS/Spotrac/snap-count matching.
- `normalize_madden()` — keeps single spaces between words. Used only for
  Madden matching, because `find_madden_player()`'s word-subset fallback
  needs to split the string into separate word tokens, which a
  space-stripped string can't do.
- `normalize_name()` — a *display* formatter (title-case, fixes A.J./Jr./II
  casing), not used for matching at all.

---

## 3. Execution order

```
python nfl/scripts/scrape_depth.py            ─┐
python nfl/scripts/scrape_otc.py                ├─ mutate the 32 team files directly
python nfl/scripts/scrape_stats.py             ─┘
python nfl/scripts/scrape_madden.py             → writes madden.json
python nfl/scripts/scrape_contracts_spotrac.py  → writes spotrac_contracts.json

python nfl/scripts/build_db.py
  → loads all of the above + fetches gsis_crosswalk (live CSV),
    nflreadpy_rosters, snap_counts (both live nflreadpy pulls)
  → writes nfl/data/fieldview.duckdb: ourlads_players, madden_ratings,
    spotrac_contracts, gsis_crosswalk, nflreadpy_rosters, snap_counts
    (each with a row_id and loaded_at)

python nfl/scripts/build_match.py
  → imports find_gsis / find_madden_player / find_pfr_id /
    find_spotrac_contract / NAME_ALIASES / position-alias maps
    directly from build_master.py
  → reads the DB tables build_db.py just wrote (no live fetches here)
  → for each ourlads_players row (in row_id order, mirroring the
    original file-iteration order so depth-based dedup ties break
    identically):
      find_gsis()                → needs crosswalk + rosters
      [dedup by player_key: lower `depth` wins]
      find_madden_player()       → needs madden_by_team + duplicate_names
      → resolved fields written to the `player_match` table
  # second pass, over the now-complete set of matched players:
  draft_year / college / age     → GSIS ID → nflreadpy roster row lookup
  pfr_id (direct)                → from the same nflreadpy roster row
  pfr_id (fallback, mainly OL)   → find_pfr_id(), independent name+team match
  snap_pct                       → pfr_id → snap-share table lookup
  Spotrac contract fields        → find_spotrac_contract(), independent match
  → writes the player_match table

python nfl/scripts/export_master.py nfl/data/players_master.json
  → JOIN player_match ON ourlads_players (via row_id)
  → reassembles the exact schema in §4
  → writes nfl/data/players_master.json
```

The key structural point, unchanged from before the migration: **every
downstream join in the second pass reads off the player's `gsis_id`**,
which was decided once in the first pass and never revisited. If GSIS
matching misses a player, `draft_year`, `college`, `age`, and the direct
`snap_pct` path all miss too, by construction — not independently.

---

## 4. `players_master.json` field-by-field

Unchanged by the migration — same schema, same fallback rules, now
produced by a `JOIN` in `export_master.py` instead of a Python dict
build in `build_master.py`.

| Field | Source | If the source misses |
|---|---|---|
| `player_id` | GSIS ID, else a slug | Slug fallback always succeeds (never null) |
| `gsis_id` | `find_gsis()` | `null` |
| `match_confidence` | rapidfuzz score from `find_gsis()` | `null` |
| `canonical_name` | `normalize_name()` of the OurLads name | Always populated (pure string transform) |
| `ourlads_name` | OurLads raw name | Always populated |
| `team`, `team_name`, `base_defense` | OurLads team file | Always populated |
| `ourlads_pos`, `standard_slot`, `standard_pos` | OurLads position + scheme-aware slot map | `standard_pos` can be an unset key for a position the map doesn't recognize |
| `depth` | OurLads row order | Defaults to `99` if missing |
| `jersey` | Madden match (`mp['jersey']`) | `null` — no other source carries jersey number |
| `age` | nflreadpy `birth_date`, via GSIS ID, → `calculate_age()` | `null` if no GSIS ID, **or** GSIS ID resolved but that roster row's `birth_date` is itself null |
| `madden`, `madden_rank`, `madden_rank_total`, `madden_pos_label` | `find_madden_player()` + `build_madden_pos_ranks()` | All `null` together — they're set from the same match or not at all |
| `cap_number` | OTC, merged into the team file by `scrape_otc.py` | `null` |
| `attainment` | OurLads (contract-year/trade suffix junk it couldn't classify) | `null` |
| `injured` | OurLads (red-text row detection) | Defaults to `False` |
| `stats`, `stats_season` | nflreadpy weekly stats, merged into the team file by `scrape_stats.py` | `{}` / `null` |
| `draft_year` | nflreadpy roster `entry_year`, via GSIS ID | `null` under the same conditions as `age` |
| `college` | nflreadpy roster `college`, via GSIS ID | `null` under the same conditions as `age` |
| `years_pro` | Computed: `SEASON - draft_year` | `null` if `draft_year` is `null` |
| `snap_pct` | Direct: GSIS→pfr_id→snap-share table. Fallback: independent name+team fuzzy match (`find_pfr_id()`) when the direct path has no `pfr_id` | `null` if both paths miss |
| `years_remaining`, `cash_total_remaining`, `cash_guaranteed_remaining`, `avg_annual_remaining` | Spotrac, via `find_spotrac_contract()` | All `null` together |

---

## 5. Known match-rate ceilings

Figures from the 2026-08-03 run (2,782 players in `player_match`) — from
`build_match.py`'s own printed summary. Re-run it for current figures.

- **GSIS matching: 2,082/2,782 (74.8%)**. This is the load-bearing gate —
  `draft_year`, `college`, `age`, and the direct `snap_pct` path all
  inherit this ceiling, since none of them run their own independent
  match (§3). **Up from 51.8% (1,440/2,782) as of this doc's last
  version** — the EDGE/DI position-taxonomy fix (below) accounts for
  essentially all of that jump.
- **A framing correction, since this was previously stated confusingly:
  GSIS itself is the NFL's own official player-ID system, not something
  inherently weak on any position group.** What's weak on OL/DI
  specifically is the **dynastyprocess crosswalk** — the one
  community-maintained, fantasy-oriented CSV this pipeline uses as its
  primary GSIS *source*. OL is skipped from GSIS matching entirely by
  design (`find_gsis()`: `if standard_pos == 'OL': return None, None`) —
  0% GSIS match rate for OL is intentional, not a gap, because the
  crosswalk doesn't carry OL rows worth searching at all.
- **EDGE/DI position-taxonomy mismatch: fixed.** Neither the
  dynastyprocess crosswalk nor nflreadpy rosters use this project's own
  EDGE/DI split — the crosswalk tags edge rushers/interior linemen `DE`
  and a small `DL` bucket, and nflreadpy rosters collapses both into one
  `DL` bucket with no distinction at all. `CROSSWALK_POS_ALIASES`/
  `ROSTERS_POS_ALIASES` in `build_master.py` translate our `EDGE`/`DI`
  search into the *source's* position labels before filtering, so a
  search for an EDGE player also considers rows the source tagged `DE`;
  a DI search also considers `DT`/`DL`. This one alias fix is
  responsible for the bulk of the 51.8% → 74.8% jump above.
- **CB/S position-taxonomy collapse: known, not fixed.** The same class
  of problem exists for cornerbacks/safeties and is currently
  unaddressed — confirmed directly against the DB tables:
  - `gsis_crosswalk`: 1,301 rows tagged `CB`, 1,106 tagged `S`, but 146
    tagged only the generic `DB` (ambiguous between the two).
  - `nflreadpy_rosters` (the GSIS fallback source): **zero** rows tagged
    `CB` or `S` — all 1,178 defensive-back rows use the generic `DB`
    tag exclusively. Since `ROSTERS_POS_ALIASES` has no `CB`/`S` entries
    (only `EDGE`/`DI`), a search for `standard_pos == 'CB'` or `'S'`
    against this fallback source structurally can never match anything
    — it's searching for a label (`CB`/`S`) that literally doesn't
    exist in that table.
  - `snap_counts` has the same pattern: 2,594 `CB`, 1,998 `S`, but 588
    generic `DB` + 8 `FS` rows outside that split.

  This is the same structural bug class as EDGE/DI, unfixed for CB/S —
  a known, accepted limitation for now, not something this migration
  changed.
- **OL snap-share: ~61% (306/503)**. `load_rosters`' `pfr_id` fill rate is
  ~0% for OL specifically, so the *direct* GSIS→pfr_id chain structurally
  can never reach them — 306/503 comes entirely from the independent
  `find_pfr_id()` name+team fallback against `load_snap_counts`'s own
  crosswalk (before that fallback: 0/503). The remaining ~39% are OL
  `load_snap_counts` itself has no record for. Same known ceiling as
  before the migration, unrelated to the EDGE/DI fix (snap matching
  doesn't use `CROSSWALK_POS_ALIASES`/`ROSTERS_POS_ALIASES` at all).
- **`age`/`draft_year`: 74.0%/74.3% (2,058 and 2,067 of 2,782)**. Not an
  independent gap — it's the 74.8% GSIS-matched slice, times ~99% of
  *those* rows having a non-null `birth_date`/`entry_year` in
  nflreadpy's raw data (2,058/2,082 and 2,067/2,082 respectively — a
  much tighter fill-within-match rate than before the EDGE/DI fix,
  since the newly-matched EDGE/DI population happens to have good
  roster-data coverage).
- **Madden: 2,218/2,782 (79.7%)**. The one join in this pipeline that
  *isn't* gated behind GSIS — matched independently by name+team.
  `find_madden_player()` now applies `NAME_ALIASES` the same way
  `find_gsis()` does (previously it didn't — a real, confirmed gap
  affecting at least 8 short-name players like "Pat Surtain II" →
  "Patrick Surtain II"; fixed since this doc's last version).
- **Spotrac remaining contracts: 2,555/2,782 (91.8%)**, independent of
  GSIS — the highest-coverage match in the pipeline, since it's a
  direct name+team fuzzy match against a large league-wide scrape.
