# FieldView — Claude Code Context

Multi-Sport intelligence platform.
Live at https://jwalluww.github.io/fieldview/
Repo: https://github.com/jwalluww/fieldview (public)
Purpose: FieldView is the primary website for sports analytics. Each sport will have a FieldView and a TableView. NFL has FormationView, NBA has CourtView, NHL has IceView, MLB has DiamondView, MLS has PitchView (EPL will also have PitchView). This view will show all the players in their positions on the playing field with important metrics & statistics and substitutions. TableView for each sport will be a table with statistics. Eventually, ReView will be created for each sport. FieldView is for before the game - understanding where players play on the field. ReView is for after the game - replays, highlights, tweets, stats, box scores, etc. - a one-stop-shop for what happened last night or last week in the sport in general.
Flow: As of 8/1, I am working on NFL & NBA for FormationView & CourtView and getting rosters lined up and stats together. Would love to get these cleaner before moving on. Next step after these look good will be other sports and the table views. Then I will hit up ReView.

---

## Stack
- Frontend: Plain HTML/CSS/JS — no React, no frameworks
- Backend: Python 3.11 scrapers
- Hosting: GitHub Pages
- Automation: GitHub Actions (runs Tuesdays at 10am UTC)
- Dev environment: Windows, VS Code + Claude Code extension (chat panel)

---

## File Map

### Frontend
- `index.html` — home page, entry cards (shared across sports)
- `nfl/nfl-formation-view.html` — formation view, player cards on field
- `nfl/depth-chart.html` — OOTP-style data table

### Scripts
- `nfl/scripts/scrape_depth.py` — OurLads depth chart scraper
- `nfl/scripts/scrape_madden.py` — Madden ratings scraper, writes `nfl/data/madden.json` (replaced `merge_madden.py`, which no longer exists in the repo — this File Map entry was stale)
- `nfl/scripts/scrape_otc.py` — Over The Cap contract data
- `nfl/scripts/scrape_stats.py` — nflreadpy season stats
- `nfl/scripts/scrape_contracts_spotrac.py` — Spotrac remaining-contract data (years/cash/APY), single-page league-wide scrape
- `nfl/scripts/build_db.py` — DuckDB raw ingestion: loads every scraper's current output into `nfl/data/fieldview.duckdb`, unmodified (one table per source, `row_id` + `loaded_at`). Also fetches the GSIS crosswalk CSV and nflreadpy rosters/snap counts live and caches them as tables instead of re-fetching per run.
- `nfl/scripts/build_match.py` — matching. Imports `find_gsis`/`find_madden_player`/`find_pfr_id`/`find_spotrac_contract` and alias/position-map constants **directly from `build_master.py`** (not reimplemented) and runs them against the DB tables `build_db.py` loaded, writing a `player_match` table.
- `nfl/scripts/export_master.py` — joins `player_match` back to the raw `ourlads_players` table and writes `players_master.json` in the production schema. Takes an output path as its first CLI arg.
- `nfl/scripts/build_master.py` — **not run by the production pipeline anymore** (see `nfl/PIPELINE.md`). Kept only because `build_match.py` imports its matching functions directly; still runs standalone and produces byte-identical output to the DB path.
- `nfl/scripts/season_utils.py` — `get_current_season()`, resolves the active NFL season dynamically from today's date
- `nfl/scripts/resolve_names.py` — diagnostic: fuzzy name match review
- `nfl/scripts/audit_positions.py` — diagnostic: position mapping review

### Data
- `nfl/data/arz.json` ... `nfl/data/was.json` — 32 team JSON files (OurLads source)
- `nfl/data/madden.json` — Madden ratings source
- `nfl/data/players_master.json` — canonical player registry (GSIS-keyed)
- `nfl/data/fieldview.duckdb` — gitignored, rebuilt by `build_db.py` every run; holds the raw per-source tables `build_match.py`/`export_master.py` read

Full pipeline detail (sources, join keys, execution order, current match-rate numbers): `nfl/PIPELINE.md`.

All NFL scripts are invoked from the repo root (e.g. `python nfl/scripts/scrape_depth.py`) and their internal `data/...` references are written as `nfl/data/...` accordingly — cwd stays the repo root, not `nfl/`.

### Frontend (NBA)
- `nba/court-view.html` — starting five in half-court zones + rotation list ranked by minutes, hardwood court background (not a re-skinned field); renamed from `formation.html`
- `nba/player-table.html` — sortable/filterable player table, mirrors `nfl/depth-chart.html`'s pattern

### Scripts (NBA)
- `nba/scripts/fetch_stats.py` — nba_api season averages (`leaguedashplayerstats`) + roster bio (`commonteamroster`, all 30 teams), writes `nba/data/nba_stats.json`. Also computes the MPG-derived `rotation_status` fallback (starter >=24 MPG, rotation >=15, else bench) that `build_nba_master.py` uses when a player isn't covered by the depth chart.
- `nba/scripts/scrape_2kratings.py` — 2kratings.com per-team pages (table `id="lists-table"`, no all-players index — 30 separate team-page fetches), writes `nba/data/nba_ratings_2k.json`
- `nba/scripts/scrape_contracts_spotrac.py` (NBA version, distinct file from `nfl/scripts/scrape_contracts_spotrac.py`) — spotrac.com/nba/contracts/remaining, single-page league-wide scrape, writes `nba/data/contracts_nba.json`
- `nba/scripts/scrape_nbadepthcharts.py` — nbadepthcharts.com's published Google Sheet (CSV export), writes `nba/data/nba_depth_chart.json`. See "NBA Depth Chart Source" below.
- `nba/scripts/build_nba_db.py` — DuckDB raw ingestion: loads `nba_stats.json`/`contracts_nba.json`/`nba_ratings_2k.json`/`nba_depth_chart.json` into `nba/data/fieldview.duckdb`, unmodified (one table per source, `row_id` + `loaded_at`). No live pulls here — every NBA source is already a static file by this point.
- `nba/scripts/build_nba_match.py` — matching (join + resolve). Imports `resolve_position`/`resolve_rotation`/`resolve_team`/`format_salary` **directly from `build_nba_master.py`** (not reimplemented) and runs them against the DB tables `build_nba_db.py` loaded, writing a `player_match` table. Note: the actual fuzzy name matching for NBA already happened upstream, inside each scraper (see below) — this script only joins already-matched sources by `player_id`.
- `nba/scripts/export_nba_master.py` — joins `player_match` back to `nba_stats` and writes `nba_players_master.json` in the production schema. Takes an output path as its first CLI arg.
- `nba/scripts/build_nba_master.py` — **not run by the production pipeline anymore** (see `nba/PIPELINE.md`). Kept only because `build_nba_match.py` imports its resolution functions directly; still runs standalone and produces byte-identical output to the DB path. See "NBA Two-Tier Resolution" below for what it (and now `build_nba_match.py`) actually resolves.
- `nba/scripts/name_utils.py` — shared `normalize_name()`/`normalize_for_matching()`/`NBA_NAME_ALIASES`, used by every NBA scraper that fuzzy-matches against `nba_stats.json` (2k ratings, Spotrac contracts, depth chart) — this is where NBA's real name matching lives, not in the master-build step

### Data (NBA)
- `nba/data/nba_stats.json` — real scraped output from `fetch_stats.py`, league-wide (587 players as of the last run), keyed by nba_api `PLAYER_ID`
- `nba/data/nba_ratings_2k.json` — `{ratings: [...], unmatched: [...]}`, 2K overall ratings matched to `player_id`
- `nba/data/contracts_nba.json` — `{contracts: [...], unmatched: [...]}`, Spotrac remaining-contract data matched to `player_id`
- `nba/data/nba_depth_chart.json` — `{last_changed, depth_chart: [...], unmatched: [...]}`, nbadepthcharts.com starter/rotation tiers matched to `player_id`
- `nba/data/nba_players_master.json` — canonical merged player registry, keyed by `player_id` (string). This is real data produced by the DB pipeline (`build_nba_db.py` → `build_nba_match.py` → `export_nba_master.py`), and it's what both `court-view.html` and `player-table.html` read. Fields: `player_id, name, team, position, jersey_number, height, weight, ppg, rpg, apg, mpg, games_played, games_started, rotation_status, rotation_source, depth_rank, overall_rating, contract_salary, contract_years_remaining`
- `nba/data/fieldview.duckdb` — gitignored, rebuilt by `build_nba_db.py` every run; holds the raw per-source tables `build_nba_match.py`/`export_nba_master.py` read

Full pipeline detail (sources, join keys, execution order, current match-rate numbers): `nba/PIPELINE.md`.

NBA scripts are also invoked from the repo root (e.g. `python nba/scripts/fetch_stats.py`), same convention as NFL.

### NBA Data Pipeline Order
`fetch_stats.py` first (everything else matches against its player universe), then `scrape_contracts_spotrac.py` / `scrape_2kratings.py` / `scrape_nbadepthcharts.py` in any order (all independent of each other), then **`build_nba_db.py` → `build_nba_match.py` → `export_nba_master.py nba/data/nba_players_master.json`** last. Matches `.github/workflows/scrape.yml`'s `scrape-nba` job exactly — confirmed against the live workflow file, including that `scrape_nbadepthcharts.py` **is** in that job (a prior version of this doc claimed it wasn't; that was stale, not current).

---

## Data Pipeline Order
Run locally or via GitHub Actions in this exact order (matches `scrape.yml`'s `scrape` job, confirmed against the live workflow file):
1. scrape_depth.py
2. scrape_otc.py
3. scrape_stats.py (uses the `nflreadpy` package, not `nfl_data_py`)
4. scrape_madden.py
5. scrape_contracts_spotrac.py
6. **build_db.py** — raw ingestion into `nfl/data/fieldview.duckdb` (also fetches the GSIS crosswalk + nflreadpy rosters/snap counts live, caching them as DB tables)
7. **build_match.py** — matching, importing functions from `build_master.py` directly
8. **export_master.py nfl/data/players_master.json** — writes the final production file

`resolve_names.py` and `audit_positions.py` are diagnostic only — run locally when investigating match quality, not part of the pipeline. `build_master.py` itself is no longer a pipeline step — see `nfl/PIPELINE.md` §0 for why it's still in the repo.

No need to delete JSONs before running — scrapers overwrite cleanly.

---

## Player JSON Schema (per-team files)
name, depth, injured, attainment, jersey, madden, age, years_pro,
cap_number, stats, stats_season, standard_slot, standard_pos,
madden_rank, madden_rank_total, madden_pos_label

## players_master.json Schema (canonical)
player_id (GSIS if matched, else name-pos-team slug),
gsis_id, match_confidence, canonical_name, ourlads_name,
team, team_name, base_defense, ourlads_pos, standard_slot, standard_pos, depth,
jersey, age, years_pro (computed: current_season - entry_year, via nflreadpy's load_rosters; current_season resolved dynamically via nfl/scripts/season_utils.get_current_season(), not a hardcoded constant), draft_year, college, madden, madden_rank,  madden_rank_total, madden_pos_label, cap_number, attainment, injured, stats (normalized keys), stats_season, nflreadpy_name, match_source,
years_remaining, cash_total_remaining, cash_guaranteed_remaining, avg_annual_remaining (all from Spotrac, fuzzy-matched — no shared ID),
snap_pct (nflreadpy load_snap_counts; matched via pfr_id — GSIS-chain first, independent name+team fuzzy match against the snap-count crosswalk as a second pass for gaps like OL, whose pfr_id is 0% populated in load_rosters)

`standard_pos` values: `QB, WR, RB, TE, OL, EDGE, DI, LB, CB, S`
Special teams (K, P, KR, PR, KO, PK, LS, PT, H) are stripped from pipeline entirely.

---

## Stat Key Normalization
Stats are normalized by position in `build_master.py` via `STAT_MAP`. Canonical keys:
- Passing: `CMP, ATT, PASS_YDS, PASS_TDS, INT, SACK, RUSH_YDS`
- Rushing: `CAR, RUSH_YDS, RUSH_TDS, REC, REC_YDS, TGT, YAC`
- Receiving: `TGT, REC, REC_YDS, REC_TDS, YAC`
- Defense: `TKL, SACK, INT, PBU, TFL, QB_HIT`

Frontend `STAT_COLS` in `nfl/depth-chart.html` uses these canonical keys.

---

## GSIS Matching Pipeline
- GSIS ID is the NFL's own official player-ID system, not something inherently weak on any position — what's actually weak on OL/DI is the **dynastyprocess crosswalk**, the one community-maintained, fantasy-oriented CSV this pipeline uses as its primary GSIS *source*. That distinction matters: it's a source-quality limitation, not a GSIS limitation.
- Primary source: dynastyprocess crosswalk CSV (fantasy-focused, good QB/WR/RB/TE coverage, poor OL/DI coverage)
- Fallback: nflreadpy roster data via `import_weekly_rosters`
- OL skipped entirely from GSIS matching by design (not in the fantasy crosswalk) — 0% OL match rate is intentional, not a gap
- Matching logic: strip to bare letters, no spaces/punctuation/suffixes, fuzzy match within position group first, team as tiebreaker only
- Both the crosswalk and the nflreadpy-rosters fallback get their own `EDGE`/`DI` position-alias translation (`CROSSWALK_POS_ALIASES`/`ROSTERS_POS_ALIASES` in `build_master.py`) before filtering — neither source uses this project's EDGE/DI split natively (crosswalk tags `DE`/small `DL`; rosters collapses both into one `DL` bucket), so without the alias a position-filtered search would silently return zero candidates regardless of name quality. This fix is responsible for most of the match-rate jump below.
- Name aliases handled via `NAME_ALIASES` dict in `build_master.py`
- `None` alias value = force no-match (wrong player in crosswalk)

### Team abbreviation map (dynastyprocess → OurLads)
`ARI→ARZ, KCC→KC, LVR→LV, TBB→TB, SFO→SF, GNB→GB, NOR→NO, NWE→NE`

### Current match results (2026-08-03 run — re-run `build_match.py` for current figures)
- 2,782 total players, 2,082 GSIS matched (74.8%) — up from ~51% before the EDGE/DI alias fix above
- Madden: 2,218/2,782 (79.7%), matched independently by name+team, not gated behind GSIS
- Most remaining unmatched are OL (skipped by design) + defensive depth
- Skill position (QB/WR/RB/TE) unmatched: 15
- **CB/S has the same taxonomy-collapse problem EDGE/DI had, currently unfixed**: nflreadpy rosters (the GSIS fallback source) has *zero* rows tagged `CB` or `S` — all defensive backs use a generic `DB` tag there, so the fallback path can never match a CB/S player at all. A known, accepted limitation, not yet addressed. Full detail: `nfl/PIPELINE.md` §5.

---

## NBA Stats Scraper (nba/scripts/fetch_stats.py)
- stats.nba.com fingerprints on header *completeness*, not just User-Agent — a thin/hand-rolled header dict gets the connection dropped outright even with a convincing UA string. The header set in the script (full Sec-Ch-Ua/Accept-Encoding/Pragma set, not just User-Agent+Referer) was verified against a live pull — don't trim it down.
- `games_started` has no bulk NBA stats endpoint — only `playercareerstats`, one call per player (~580 extra calls for the full league). Decided against pulling it (too slow, too much extra rate-limit exposure for one field). `rotation_status` is derived from minutes-per-game alone instead: starter if MPG >= 24, rotation if MPG >= 15, else bench. **Starting guess, not a settled rule** — revisit once real usage patterns are known.
- Season format is `"YYYY-YY"` (e.g. `"2025-26"`), named by the year it starts (Oct–June) — before October, "current season" resolves to the prior year's, same shape as `nfl/scripts/season_utils.py` but with an October cutoff instead of September.
- Every call goes through an exponential-backoff retry wrapper — stats.nba.com throttles/blocks aggressively, budget for retries not a single clean pull.

---

## NBA Depth Chart Source (nba/scripts/scrape_nbadepthcharts.py)
- Source: nbadepthcharts.com, which embeds a published Google Sheet via iframe. RotoWire was tried first and ruled out — 25/30 teams paywalled ("Our [Team] depth chart is reserved for RotoWire subscribers"). CraftedNBA confirmed viable as a future fallback/cross-check but not used here.
- Fetched via the sheet's own CSV export URL (`.../pub?gid=...&single=true&output=csv`) — plain `requests.get`, no headless browser needed. The `pubhtml` viewer is JS-rendered (Google's Waffle viewer) and xlsx/ods/gviz exports all 400/404 for this "pub" doc ID (it's not a real spreadsheetId) — CSV is the only viable static export.
- Structure: 30 team blocks, each laying out 4 depth tiers (STARTERS/2ND STRING/3RD STRING/OTHER) as 4 fixed-width column groups (name/pos/MPG/GP) side by side — not a per-position table. Parsed by **fixed column position**, not the sheet's own sub-header text, because Washington's sub-header row is corrupted at the source (reads "Player, Team, Update, Description..." instead of "STARTERS, 2ND STRING...") while its underlying data columns are unaffected. Tiers also don't all end on the same row — Memphis' OTHER column runs 4 rows past its other 3 tiers, overlapping rows that also hold that team's REMAINING FA / GONE notes in earlier columns.
- Status flags: the sheet's legend defines 5 (New Team/Rookie/Two-Way/Injured/Unsigned), all color-coded on the live site. Only **Rookie** survives into the CSV as plain text (a "(pick#)" suffix on the name, paired with "--"/"--" MPG/GP) — the other 4 are color-only and would need a headless browser to read. Decided against that dependency; `status_flags` in the output is Rookie-only for now.
- Name-matching edge cases found and fixed via `NBA_NAME_ALIASES` in `name_utils.py`: "Ron Holland" (sheet omits nba_api's "II" suffix) and "Egor Dёmin" (sheet's copy has a Cyrillic 'е'/U+0451 where nba_api has a Latin 'ë'/U+00EB — visually identical, not unified by accent-folding since they're different base letters, not different accents on the same one).
- Match rate: 440/518 (84.9%) as of the last run. Of the 78 unmatched, 59 are 2025 draft picks not yet in `nba_stats.json`'s roster snapshot (real timing gap) and 19 are veterans genuinely absent from that snapshot entirely (real data-source ceiling, not a matching bug).

### Staleness Tracking
- `last_changed` in `nba_depth_chart.json` is computed by diffing each run's parsed `depth_chart` list against the previous run's output — unchanged data carries `last_changed` forward, changed data bumps it to today.
- Deliberately not using nbadepthcharts.com's own displayed "Last updated" date — confirmed it just prints today's date via JS on every page load, regardless of actual data freshness.
- Surfaced on `court-view.html` next to the "Starting Five" label (small, unobtrusive text, not a banner) — fetched once at page load via `loadDepthChartMeta()`, fails silently (empty caption, no console error) if the file 404s or `last_changed` is missing/malformed.

---

## NBA Two-Tier Resolution (build_nba_master.py, imported by build_nba_match.py)
- `resolve_rotation()` and `resolve_team()` both follow the same layering: if a player has a `nba_depth_chart.json` match (by `player_id`), that source wins — `rotation_status` maps the sheet's tier onto the existing 3-value enum (`DEPTH_RANK_TO_STATUS`: 1→starter, 2→rotation, 3/4→bench), `rotation_source` is `"nbadepthchart.com"`, and `depth_rank` (1-4) is populated. Otherwise it falls back to `nba_stats.json`'s MPG-derived `rotation_status` / roster-snapshot `team`, with `rotation_source: "mpg_derived"` and `depth_rank: null`.
- Not a flat replacement — both tiers coexist by design, so `rotation_source` is always debuggable per player rather than silently ambiguous. Every player gets a non-null `rotation_status`.
- Concrete reason this matters: nbadepthcharts.com reflects trades faster than `nba_stats.json`'s roster snapshot. As of the last merge, 87 players had their `team` corrected this way (e.g. a mid-offseason trade showing the player's new team instead of the stale snapshot team) — that number will drift as both sources update, it's illustrative, not a fixed constant.

---

## NBA Team Logos (court-view.html)
- Header + team-switcher dropdown use real logo images (`ESPN_TEAM_CODES` → `teamLogoUrl()`), not the old color-swatch circles.
- `cdn.nba.com` (the official source) was tried first and ruled out — it returns 200 to a plain HTTP GET but fails with `ERR_HTTP2_PROTOCOL_ERROR` on **actual browser navigation** (verified via Playwright, not just a `requests` check), so it would break for real visitors despite looking fine in a quick test.
- ESPN's CDN (`a.espncdn.com/i/teamlogos/nba/500/{code}.png`) verified working both ways, all 30 codes. Two exceptions to our internal `TEAM_ABBRS`: New Orleans is `no` (not `nop`), Utah is `utah` (not `uta`) — verified against the live CDN, not guessed. Documented as a code comment directly on `ESPN_TEAM_CODES` in `court-view.html`, not only here.

---

## NBA Navigation
- `index.html` defaults to the NFL state (`currentSport = 'nfl'` in static markup) and now reads `?sport=` from the URL at load to initialize into NBA state instead, via the existing `selectSport()` function — a plain visit to `index.html` is unaffected.
- Both NBA pages' logo/back buttons link to `../index.html?sport=nba` (previously bare `../index.html`, which always landed on the NFL-default hub regardless of which sport you came from). NFL's own back button deliberately untouched.
- `formation.html` renamed to `court-view.html` (page title, nav button labels, index.html's card label/href all updated). Cross-links fixed in `player-table.html`, `index.html`, and comments in `build_nba_master.py`.

---

## CourtView Frontend Interactions (court-view.html)
- **Hover stat popup**: `mouseenter`/`mouseleave` attached directly per rendered node (both court cards and rotation rows) rather than event delegation — avoids the mouseover/mouseout bubbling-flicker problem. Re-attached after every `renderCourt()`/`renderRotation()` call via `attachPopupHandlers()`. Positioning (`positionPopup()`) anchors right of the hovered element, flips left if it would clip the right edge, clamps both axes to the viewport.
- **Click-to-substitute**: clicking a rotation-list player swaps them into their position's court slot. `manualStarters` (`{pos: playerId}`) is pure frontend view state — reset on every team switch, never written back to `nba_players_master.json`. `getStarter(pos)` checks it before falling back to the existing MPG-based starter logic, so the swapped-out starter's return to the rotation list (re-sorted by MPG) falls out of the existing reactive render pipeline for free.
- **Known gap, not forgotten**: no undo path for a single substitution short of switching teams away and back. Deferred to a future instruction that will also rework starter layout and substitution mechanics more generally.

---

## Formation View
- Team selector persisted via localStorage, overridden by URL params
- Formation sharing via URL: `?team=KC&unit=defense&pkg=nickel`
- Offense/defense toggle, 11/12 personnel, base/nickel defense
- Auto-detects 3-4 vs 4-3 from `base_defense` field in team JSON
- Package keys: `11, 12, base43, base34, nickel, nickel34`
- Player cards: Madden color gradient, hover card (stats/cap/age), substitution dropdown
- Tags: INJ, R (rookie), attainment
- Mobile responsive (v1 — functional, not polished)
- `syncFieldHeight()` called after render to fix mobile field scaling

---

## Depth Chart Table
- Loads all 32 teams at once from `players_master.json` (wired this session — was per-team JSONs)
- OOTP-style view tabs: Overview, Financial, Madden Ratings, Passing, Rushing, Receiving, Defense
- Sortable columns, nulls always sort last
- Filters: search, team, unit, position, depth
- Sticky header/filter bar (dynamic offset via `updateStickyOffset()`)
- Two position columns: ourlads_pos (specific slot) + standard_pos (group badge)
- Special teams positions removed from display
- Mobile: card list layout below 600px breakpoint

---

## Conventions & Gotchas
- OurLads abbreviations: `ARZ` (not ARI), `JAX` (not JAC)
- Team JSON can come out as a list or dict — normalize with `if type(team_data) is list: team_data = team_data[0]`
- Minimal targeted edits only — no unrelated refactors, no adjacent "improvements"
- Match existing code style even if you'd write it differently
- No speculative features or config beyond what's asked
- Plain HTML/CSS/JS only — no React, no build tools
- Live Server (VS Code extension by Ritwick Dey) for local dev preview

---

## Known Outstanding Bugs
- OL snap-share coverage sits at ~61% (306/504) — real data-source ceiling (import_snap_counts/PFR crosswalk coverage for OL specifically), not considered worth chasing further
- NFL: CB/S has the same position-taxonomy-collapse problem EDGE/DI had (see GSIS Matching Pipeline) — nflreadpy rosters (the GSIS fallback source) tags all defensive backs generically as `DB`, with no `CB`/`S` split at all, so that fallback path structurally can never match a CB/S player. Known, not fixed — same bug class as EDGE/DI, just not yet addressed for this position group.
- NBA: no undo path for a single court substitution short of switching teams away and back (see CourtView Frontend Interactions) — deferred, not forgotten

**Note on this list:** the previous version of this entry claimed `scrape_nbadepthcharts.py` "is not yet in `scrape.yml`'s `scrape-nba` job" — checked the live workflow file directly and it's already there (has been since the job was last edited). That claim was stale, not current; removed rather than left in place. Both NFL and NBA also moved off a single build-script pipeline this round (`build_master.py`/`build_nba_master.py` → DB-backed multi-script pipelines) — see `nfl/PIPELINE.md` / `nba/PIPELINE.md` for the current architecture, not the file map history above.

---

## Roadmap

**In Progress**
- ⬜ NBA CourtView zone alignment — replace dead-center-under-hoop `COURT_ZONES` with offset post positions (fix drafted, pending Claude Code apply + verify)
- ⬜ Guard/Wing/Big data source — researching Cleaning the Glass's G/W/B convention; verify `nba_api`'s `commonplayerinfo` endpoint's coarser `POSITION` field as a possible existing source before building a manual mapping
- ⬜ Rank NBA players by position, surfaced on court — mirrors the NFL depth-chart-by-position ranking, applied to CourtView
- ⬜ Tactical stat selection — figuring out which few stats actually matter per view; feeds both CourtView hover/bench cards and TableView columns, so solve once and both inherit it

**Up Next**
- ⬜ Opponent overlay (NFL) — same-team offense+defense on the field simultaneously first, then a real versus view (your team's offense against an actual opponent's defense)
- ⬜ Additional data sources (advanced metrics): PFF grades, RAS scores, combine data, EPA/DVOA — via `nflreadpy` (see PIPELINE notes: `load_ftn_charting()`, `load_nextgen_stats()`, `load_participation()`, `load_combine()` are all already free and unused)
- ⬜ TableView stat/view-package refinement — right stat columns and filter presets to actually run an analysis or scan the league quickly, not just look at a roster
- ⬜ Popover `.subs-name` truncation fix — small, same width/font treatment `.bench-name` already got
- ⬜ NBA Big/Wing/Guard bucket UI — once the data source item above is settled

**Backlog**
- ⬜ Multi-sport expansion — MLB/NHL/MLS/EPL (once NFL/NBA are genuinely the finished template to copy, not before)
- ⬜ ReView overview — replays, highlights, box scores, tweets, podcasts; comes after FormationView/CourtView/TableView are dialed in, per original sequencing
- ⬜ Mobile responsiveness pass — desktop-only is the explicit call for now
- ⬜ NBA table view column cleanup (same treatment NFL's table view already got)

**Wish List**
- ⬜ Player comparison
- ⬜ Historical rating trends

**Not in FieldView - called ReView:** League leaderboards, game reviews, highlights, replays, podcasts, tweets — these belong in a separate media/highlights page down the road. Called ReView for being able to review the past day/week of games, highlights, box scores, stats, tweets, drama, reddit posts, podcasts, etc. Just to catch up on the league and all it's action.

---

## NFLDATAPY
nflreadpy — yes, a few of these are genuinely worth grabbing, and one of them actually shortcuts your own roadmap:

load_ftn_charting() — this is the one I'd flag hardest. Your roadmap lists PFF as a future paid data source, but FTN's charted stats (pressure rate, missed tackles, target quality, that kind of PFF-style manual charting) are free and already in nflreadpy. Worth trying before you go looking for a PFF scrape.
load_nextgen_stats() — real tracking-derived metrics (separation, time to throw, closing speed, etc.). This is exactly the kind of "surprising, layered" data that makes a player comparison view actually interesting instead of just a stat table.
load_participation() — personnel groupings and snap-level participation. This one's relevant specifically to formation view and your planned "opponent overlay" — it's literally per-play personnel package data, which is the same shape of information your formation view already visualizes.
load_combine() — combine results, already on your roadmap as a separate source, but it's just sitting here for free too.

load_contracts() also exists here (OTC data) — you already have a working Spotrac/OTC pipeline for that, so I wouldn't switch just to consolidate, but worth knowing it's redundant with what you built rather than a gap.

---

## Workflow Notes
- Use this chat (claude.ai) for architecture decisions, debugging with context, pushback
- Use Claude Code (VS Code chat panel) for direct file edits
- Front-load thinking in chat → hand Claude Code a crisp specific instruction
- Start a new chat when switching to a new sport or major new feature area
- Paste this CLAUDE.md at the top of any new chat to restore context