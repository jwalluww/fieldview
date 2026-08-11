# FieldView — Claude Code Context

Multi-Sport intelligence platform.
Live at https://jwalluww.github.io/fieldview/
Repo: https://github.com/jwalluww/fieldview (public)
Purpose: FieldView is the primary website for sports analytics. Each sport will have a FieldView and a TableView. NFL has FormationView, NBA has CourtView, NHL has IceView, MLB has DiamondView, MLS has PitchView (EPL will also have PitchView). This view will show all the players in their positions on the playing field with important metrics & statistics and substitutions. TableView for each sport will be a table with statistics. Eventually, ReView will be created for each sport. FieldView is for before the game - understanding where players play on the field. ReView is for after the game - replays, highlights, tweets, stats, box scores, etc. - a one-stop-shop for what happened last night or last week in the sport in general.
Flow: NFL and NBA FormationView/CourtView are in good shape — layout, sizing, backgrounds, and substitution UX have all been through real design-and-ship rounds. Branching into MLB now (DiamondView) as the next sport, ahead of the original "finish NFL/NBA fully first" sequencing — an intentional call, not drift, made because NFL/NBA are stable enough to serve as a real template.

---

## Stack
- Frontend: Plain HTML/CSS/JS — no React, no frameworks
- Backend: Python 3.11 scrapers
- Hosting: GitHub Pages
- Automation: GitHub Actions (runs Tuesdays at 10am UTC) — note `fetch_stats.py` (NBA) is no longer part of the cloud job, see NBA Stats Scraper section below
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
- `nba/scripts/fetch_stats.py` — nba_api season averages (`leaguedashplayerstats`) + roster bio (`commonteamroster`, all 30 teams), writes `nba/data/nba_stats.json`. **Runs locally/manually only as of this round — removed from the GitHub Actions `scrape-nba` job.** See NBA Stats Scraper section below for why.
- `nba/scripts/scrape_2kratings.py` — 2kratings.com per-team pages (table `id="lists-table"`, no all-players index — 30 separate team-page fetches), writes `nba/data/nba_ratings_2k.json`. **Currently blocked by TLS fingerprinting mid-fix — see 2K Ratings Scraper section below, this is an open issue, not resolved.**
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
`fetch_stats.py` first — **now run locally/manually, not in the cloud job** — then `scrape_contracts_spotrac.py` / `scrape_2kratings.py` / `scrape_nbadepthcharts.py` in any order (all independent of each other), then **`build_nba_db.py` → `build_nba_match.py` → `export_nba_master.py nba/data/nba_players_master.json`** last, still in the cloud job. The `scrape-nba` job in `scrape.yml` runs off whatever `nba_stats.json` is currently committed rather than a fresh cloud pull.

---

## Data Pipeline Order (NFL)
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
- **GitHub Actions IP block (resolved):** the script started failing exclusively on the hosted Actions runner — read-timeout after 6 retries, no successful requests at all that run — while working perfectly when run locally on the same day with the same code. Confirmed as an IP-level issue (cloud/datacenter IPs like GitHub-hosted runners get treated worse by stats.nba.com than residential IPs), not a header/code problem, since identical code succeeded locally and failed only on the runner. Fixed by pulling `fetch_stats.py` out of the cloud `scrape-nba` job — it now runs locally/manually only, with the rest of the NBA pipeline (`build_nba_db.py` → `build_nba_match.py` → `export_nba_master.py`) continuing in the cloud off whichever `nba_stats.json` is currently committed. Confirmed working again as of this round.
- `games_started` has no bulk NBA stats endpoint — only `playercareerstats`, one call per player (~580 extra calls for the full league). Decided against pulling it (too slow, too much extra rate-limit exposure for one field). `rotation_status` is derived from minutes-per-game alone instead: starter if MPG >= 24, rotation if MPG >= 15, else bench. **Starting guess, not a settled rule** — revisit once real usage patterns are known.
- Season format is `"YYYY-YY"` (e.g. `"2025-26"`), named by the year it starts (Oct–June) — before October, "current season" resolves to the prior year's, same shape as `nfl/scripts/season_utils.py` but with an October cutoff instead of September.
- Every call goes through an exponential-backoff retry wrapper — stats.nba.com throttles/blocks aggressively, budget for retries not a single clean pull.

---

## 2K Ratings Scraper (nba/scripts/scrape_2kratings.py) — OPEN ISSUE, not resolved
- Started failing with 403 Forbidden mid-run (8/30 teams succeeded, then blocked for the rest of that run) — a different failure signature than `fetch_stats.py`'s timeout (a hard rejection, not a hang).
- Ruled out request speed (existing ~1–1.5s delay between requests was already reasonable) and thin headers (added a full browser-realistic header set + `requests.Session()` for cookie persistence) — neither fixed it. A rerun immediately after actually failed *faster* (blocked on request 1), which pointed at an active IP-level cooldown from the first failed run, not a header gap.
- **Confirmed via direct browser test that the site itself loads fine from the same machine/IP** while the script still gets 403'd even with a full session and complete headers — this rules out a site-wide block or outage and points specifically at **TLS fingerprinting**: Cloudflare-class protection checks the TLS handshake (cipher order, extensions, JA3 signature) before HTTP headers are even read, and Python's `requests`/`urllib3` has a detectably different handshake than real Chrome regardless of what headers are set on top.
- Fix in progress: swapped to `curl_cffi` (`session = requests.Session(impersonate="chrome120")` from the `curl_cffi.requests` module), which mimics Chrome's real TLS/HTTP2 fingerprint rather than just its headers. A single-page test came back clean (real HTML, no 403).
- **Status as of this session: still not fully working.** A full 30-team run with the `curl_cffi` fix got through only 1 team before a 403, worse than the original 8-team run. Suspected cause: repeated debugging attempts within the same day (original run, immediate retry, isolated test, full run) likely compounded/extended whatever IP-level block or reputation flag got triggered, rather than the fix itself being wrong.
- **Next steps, not yet done:** (1) stop testing entirely for several hours / overnight before trying again — every attempt during an active block, including failed ones, likely extends it; (2) added diagnostic logging on 403s to print `server`, `retry-after`, and `cf-ray` response headers so the next attempt has real data instead of another guess; (3) reduced 403-specific retry count from 4 to 2 so a future blocked run fails fast instead of hammering the block further.
- Don't consider this fixed until a full 30-team run completes clean after a genuine cooldown period.

---

## NBA Position Ranking (court-view.html)
- `computePositionRanks(players)` computes each player's league-wide rank within their position group (`PG/SG/SF/PF/C`) by 2K `overall_rating`, e.g. `PF 3/46` — mirrors NFL's `madden_pos_label` convention exactly. Computed once, client-side, in `loadAllPlayers()` right after `allPlayers` is built — league-wide across all 30 teams, not per-team.
- Displayed under the player name on court starters, and replacing the plain position letter in `.bench-meta` for bench rows (falls back to plain `p.pos` if no rank exists, never blank).
- Players with no `overall_rating` get no badge at all — not an "NR" placeholder. Confirmed for real: **LeBron James currently has `rating: null`** and gets no badge. This is very likely a data bug, not a real gap — 2kratings.com rates every rotation player, so a total unknown missing a rating is expected but the actual GOAT-tier active superstar missing one is a canary, same shape as the Surtain/Woolen NFL alias bugs already fixed in this project. **Not yet investigated** — check `nba_ratings_2k.json`'s `unmatched` array for his name before trusting the position-rank feature's edge cases further; if found there, it's likely a one-line `NBA_NAME_ALIASES` fix.
- Ties (equal ratings) get sequential ranks based on JS's stable sort order, not a shared "tied" rank — intentional, not a bug.
- 514/587 league players ranked as of the last run; the other 73 have no 2K rating (LeBron included, see above).

---

## NBA Substitution — positionless (in progress, not yet confirmed shipped)
- Original click-to-sub only offered same-position bench players. Abandoned the Guard/Wing/Big bucket idea after research turned up no usable existing data source (`nba_api`'s `commonplayerinfo` coarse `POSITION` field and Cleaning the Glass's G/W/B convention were the two candidates considered; neither panned out as buildable within the current pipeline). **Positionless subbing was chosen as the replacement**, not an addition — any bench player can sub into any court slot now, which also fits the earlier project conclusion that NBA position labels matter less than NFL's.
- This requires more than deleting the position filter, because of a real duplicate-player bug the filter was accidentally preventing: without it, a manually-placed player could also get auto-selected again for their *natural* position elsewhere on court. Fix design (drafted, not yet confirmed applied):
  - `getStarter(pos)`'s natural-fallback path now excludes any player id already placed via `manualStarters` in a *different* zone.
  - The subs popover excludes all 5 currently-resolved starters (not just the clicked zone's own starter), computed via `getStarter()` across `ZONE_ORDER`.
  - `substitutePlayer(pid, targetPos)` now takes the target zone explicitly (the clicked slot) rather than deriving it from the incoming player's own position, since that assumption breaks once positions aren't required to match.
- The position-rank badge (`PG 5/90` etc.) still shows the player's *real* position regardless of which zone they're standing in — useful now, since you can see at a glance that the player in the C slot is actually a point guard.

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
- **Index page background:** replaced the old abstract same-shape-different-color stripe gradient with literal per-sport texture, generated at runtime as inline SVG data URIs — real yard-line ticks for NFL, vertical wood-grain planks + a faint free-throw-key/circle accent for NBA (`nflTexture()`/`nbaTexture()`/`placeholderTexture()`/`applyFieldBackground(sport)`). `SPORTS` config's old `background: {stripeA, stripeB}` fields were removed as dead weight — nothing reads them anymore.

---

## CourtView Frontend Interactions (court-view.html)
- **Layout:** two-column — `.left-col` (compact court, currently 598px wide, 64px starter dots) + `.right-col` (full bench/rotation list, all players visible with zero scroll at 1280×900). Bench rows show PPG/RPG/APG/MPG per player, not just minutes.
- **Court zone alignment (resolved):** `COURT_ZONES` was a "loose" percentage approximation that looked fine small but became visibly off once the court render doubled in size. Corrected to offset post positions instead of a dead-center-under-the-hoop `C` — confirmed good by direct visual check against the real render.
- **Substitution — now positionless**, see "NBA Substitution" section above for the full design and current (unconfirmed-shipped) status. `manualStarters` (`{pos: playerId}`) remains pure frontend view state — reset on every team switch, never written back to `nba_players_master.json`.
- **Hover stat popup**: `mouseenter`/`mouseleave` attached directly per rendered node (both court cards and rotation rows) rather than event delegation — avoids the mouseover/mouseout bubbling-flicker problem. Re-attached after every `renderCourt()`/`renderRotation()` call via `attachPopupHandlers()`. Positioning (`positionPopup()`) anchors right of the hovered element, flips left if it would clip the right edge, clamps both axes to the viewport.
- **Known gap, not forgotten**: `.subs-name` in the substitution popover still truncates long names ("Sandro Mamuk...") — a separate, smaller class from `.bench-name` that didn't get the same width/font treatment in the sizing round. Small follow-up, not urgent.

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
- **Scraper hardening pattern (new):** two separate scraper incidents this round (stats.nba.com IP-blocking cloud runners, 2kratings.com TLS-fingerprinting `requests`) reinforce the same lesson already documented for stats.nba.com — anti-bot protection increasingly operates below the HTTP-header layer (source IP reputation, TLS handshake fingerprint) where header tuning alone can't fix it. When a new sport's scrapers hit similar walls, check IP/TLS-layer causes before re-tuning headers a third or fourth time.

---

## Known Outstanding Bugs
- OL snap-share coverage sits at ~61% (306/504) — real data-source ceiling (import_snap_counts/PFR crosswalk coverage for OL specifically), not considered worth chasing further
- NFL: CB/S has the same position-taxonomy-collapse problem EDGE/DI had (see GSIS Matching Pipeline) — nflreadpy rosters (the GSIS fallback source) tags all defensive backs generically as `DB`, with no `CB`/`S` split at all, so that fallback path structurally can never match a CB/S player. Known, not fixed — same bug class as EDGE/DI, just not yet addressed for this position group.
- NBA: no undo path for a single court substitution short of switching teams away and back — deferred, not forgotten
- NBA: `.subs-name` popover text truncation — see CourtView Frontend Interactions above
- NBA: LeBron James `rating: null` in `nba_players_master.json` — suspected 2kratings.com name-match bug, same class as previously-fixed Surtain/Woolen/Cyrillic-character bugs. Not yet checked against `nba_ratings_2k.json`'s `unmatched` array.
- NBA: `scrape_2kratings.py` currently blocked mid-fix (TLS fingerprinting) — see 2K Ratings Scraper section above. Not resolved as of this round.

---

## Roadmap

**In Progress**
- ⬜ MLB expansion kickoff — DiamondView + stats/ratings pipeline, following the same 5-script shape as NFL/NBA (scrape rosters/stats → scrape ratings → build_mlb_db → build_mlb_match → export_mlb_master). Intentionally jumps ahead of the original "finish NFL/NBA fully first" sequencing.
- ⬜ NBA positionless substitution — design drafted (see section above), not yet confirmed applied/verified
- ⬜ 2K ratings scraper TLS block — `curl_cffi` fix in progress, full run not yet confirmed clean after a real cooldown period
- ⬜ Tactical stat selection — still just ongoing thinking; feeds both CourtView hover/bench cards and TableView columns, so solve once and both inherit it

**Up Next**
- ⬜ NHL expansion — second sport after MLB; public NHL stats API is the cleanest data layer of the remaining candidates, structurally closer to NBA (fluid positions, bench-heavy) than to NFL/MLB. Open question, not yet verified: whether a 2K-ratings-equivalent fan site exists for EA's NHL game.
- ⬜ Opponent overlay (NFL) — same-team offense+defense on the field simultaneously first, then a real versus view (your team's offense against an actual opponent's defense)
- ⬜ Additional NFL data sources (advanced metrics): PFF grades, RAS scores, combine data, EPA/DVOA — via `nflreadpy` (see PIPELINE notes: `load_ftn_charting()`, `load_nextgen_stats()`, `load_participation()`, `load_combine()` are all already free and unused)
- ⬜ TableView stat/view-package refinement — right stat columns and filter presets to actually run an analysis or scan the league quickly, not just look at a roster
- ⬜ Popover `.subs-name` truncation fix — small, same width/font treatment `.bench-name` already got
- ⬜ LeBron James `rating: null` investigation — check `nba_ratings_2k.json`'s `unmatched` array before trusting the position-rank feature's edge cases further

**Backlog**
- ⬜ MLS/EPL expansion (soccer) — last of the four remaining sports, after MLB and NHL. Ratings side is actually the strongest candidate of all four (sofifa.com/EA FC is a large, well-known, scrapable database), but the free stats/roster API landscape is more fragmented than pybaseball/NHL's API/nba_api — pick after the other two sports prove out the process.
- ⬜ ReView overview — replays, highlights, box scores, tweets, podcasts; comes after FormationView/CourtView/TableView are dialed in, per original sequencing
- ⬜ Mobile responsiveness pass — desktop-only is the explicit call for now
- ⬜ NBA table view column cleanup (same treatment NFL's table view already got)

**Wish List**
- ⬜ Player comparison
- ⬜ Historical rating trends

**Dropped**
- ~~NBA Big/Wing/Guard bucket UI~~ — no usable existing data source found after checking `nba_api`'s `commonplayerinfo` coarse position field and Cleaning the Glass's convention. Superseded by positionless substitution instead of built as originally planned.

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