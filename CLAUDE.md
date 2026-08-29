# FieldView — Claude Code Context

Multi-sport intelligence platform. Live at `jwalluww.github.io/fieldview/` (GitHub Pages); a `CNAME` at the repo root points the custom domain `www.fieldview.com` at it.
Repo: https://github.com/jwalluww/fieldview (public)

Purpose: each sport gets a FieldView (players on the field/court/pitch in their real positions, with substitutions) and a TableView (sortable/filterable stat table). A future ReView (replays, box scores, highlights) comes after every sport's FieldView/TableView are dialed in — not started yet, tracked in Roadmap only.

**Current status, verified against the real repo (2026-08-29), not carried forward from any prior summary:**
- **NFL, NBA, MLB, NHL** — FieldView + TableView shipped, real data, **all four now have real GitHub Actions automation** (`scrape.yml`'s `scrape`/`scrape-nba`/`scrape-mlb`/`scrape-nhl` jobs). NFL/NBA's ratings sources (Madden, 2K) are fully or partially live; MLB's and NHL's fan-ratings scrapers (theshowratings.com, nhlratings.net) are real and built but only theshowratings.com has actually cleared its site's block — NHL's is still fully blocked at the site level, shipped without ratings.
- **EPL, MLS** — FieldView + TableView shipped this round, real data (fantasy.premierleague.com + sofifa.com for EPL; ESPN's core API + American Soccer Analysis + sofifa.com for MLS). **No cloud automation yet for either** — every EPL/MLS script is still run by hand, no `scrape.yml` job, no local orchestrator `.bat` file (unlike the other four sports, which each have one).
- **ReView** — not started, any sport.

---

## Stack
- Frontend: Plain HTML/CSS/JS — no React, no build tools
- Backend: Python 3.11 scrapers, `duckdb`/`pandas` for the match/join layer
- Hosting: GitHub Pages
- Automation: GitHub Actions, `.github/workflows/scrape.yml`, one workflow file holding four jobs (`scrape`=NFL, `scrape-nba`, `scrape-mlb`, `scrape-nhl`), all triggered by a **single shared schedule** (`cron: '0 10 * * 2'` — every Tuesday 10am UTC) plus manual `workflow_dispatch`. No per-job stagger exists — all four fire at the same time.
- Local orchestration: `run_nfl.bat` / `run_nba.bat` / `run_mlb.bat` / `run_nhl.bat` each run that sport's full pipeline end-to-end locally (fail-and-continue per step, never git add/commit/push); `run_all.bat` chains all four and prints one aggregate summary. **No `run_epl.bat`/`run_mls.bat` exist** — those two sports are still run script-by-script by hand.
- Task Scheduler (Windows, local machine only): two real, currently-registered scheduled tasks — `FieldView NBA 2K Ratings Scrape` (daily 09:15, via `nba/scripts/schedule_2kratings_scrape.bat`) and `FieldView NHL Ratings Scrape` (daily 09:00, via `nhl/scripts/schedule_ratings_scrape.bat`). Both confirmed via live `schtasks /query`, not assumed from either script's own comments (NHL's `scrape_ratings.py` file comment claims this is only a "suggested, not registered" command — that comment is now stale; the task is genuinely registered).
- Data pipelines land in DuckDB directly where the source is a live API (statsapi.mlb.com, nhl-api-py) — no intermediate JSON dump for the *join* layer, though the raw scrape output is still written to JSON first in every sport. EPL/MLS deviate further: **EPL has a DuckDB layer** (`epl/data/fieldview.duckdb`, `build_epl_db.py` → `build_epl_match.py` → `export_epl_master.py`) but **MLS has none** — `mls/scripts/build_mls_match.py` reads/writes JSON directly, no DB step, by design (a two-way name join doesn't need SQL).

---

## Site Infrastructure

**Custom domain**: `www.fieldview.com` via `CNAME`, pointed at GitHub Pages — added to satisfy Google AdSense's rejection of shared `github.io` subdomains, and as a general credibility upgrade.

**Analytics**: Google Analytics (GA4), `gtag.js`, Measurement ID `G-TP0M77Z31N`, present on every real HTML page in the repo (`index.html` + every sport's FieldView + player-table file) — confirmed present on `epl/pitch-view.html`, `epl/player-table.html`, `mls/pitch-view.html`, `mls/player-table.html` too, added as part of this round's builds, same snippet as every other page.

**Monetization notes, factual not advisory**: AdSense has no minimum traffic requirement. Premium networks (Mediavine, Raptive/AdThrive) gate by traffic — Mediavine's classic threshold is ~50,000 sessions/month — but check each network's current site directly when actually approaching that point, not from memory.

**A real, known, currently-uncorrected inconsistency**: `index.html`'s `SPORTS.nba.formationFeatures` and `SPORTS.mlb.formationFeatures` both still literally include the tag `'Mock Data'` — stale from before either sport had real scraped data. Both sports' underlying data has been real for a long time; only the display tag never got updated. Not fixed as part of this doc pass — flagged here so it doesn't get missed.

---

## Workflow Notes
- Use this chat (claude.ai) for architecture decisions, debugging with context, pushback.
- Use Claude Code (VS Code chat panel) for implementation, real data verification, and live reconnaissance against external sites/APIs.
- **Reconnaissance against live external systems belongs in Claude Code, handed off as one broader investigation task** — this chat's sandbox has no working browser and a locked-down network. Splitting recon into one probe-per-question wastes round trips; hand off one combined investigation and let Claude Code adjust/retry in its own loop.
- **For real scripts, give Claude Code a precise spec with verified facts and named edge cases, rather than full verbatim code written blind in chat.** Chat can't execute or test what it writes. Real bugs caught only because Claude Code tested its own code, across every sport built so far: MLB's blanket-zero `batting_stats` leaking pitchers into batting orders, a `position_group` mislabel, NHL's silent bulk-endpoint truncation, and — this round — a sofifa pagination bug (assumed page size from an undercounted grep, causing 50%-overlapping fetches) and a token-overlap name-matcher that normalized before tokenizing and could never find a shared token, both caught by actually running the code against real data rather than trusting it on inspection.
- Chat's real value-add: cross-cutting consistency a per-file view might miss — "extract this into a shared file, a second sport needs it now" (`nfl/scripts/season_utils.py`, `nba/scripts/name_utils.py`, `mlb/scripts/statsapi_utils.py`, and this round's `shared/scripts/scrape_sofifa.py` + `shared/scripts/soccer_name_utils.py`, deliberately built shared from the start since EPL/MLS both needed the same sofifa scraper and name-matching approach).
- Start a new chat when switching to a new sport or major new feature area.

---

## Key Cross-Sport Learnings

- **"Verify the real field/column names before writing normalize logic" has paid off on every sport built so far**, including this round's EPL/MLS work: FPL's real `element_type`/`first_name`/`second_name` shape, ESPN's core-API athlete shape, ASA's real `itscalledsoccer` column names (`primary_assists` not `assists`, `minutes_played` not `minutes`) were all confirmed live before a matching script got written, catching real mismatches (MLS's `position_group` turned out to be single-letter ESPN codes `G/D/M/F`, not FPL's 3-letter `GKP/DEF/MID/FWD` — a genuinely different enum between the two soccer builds, not just relabeling).
- **Silent bulk-endpoint truncation and pagination bugs are a recurring, not one-off, class of bug.** NFL/MLB's `/v1/stats` needed a bigger `limit`/`playerPool=all`. NHL's `/stats/rest` hard-caps at 100 rows regardless of `limit`, needing real `start`-based pagination. This round, `shared/scripts/scrape_sofifa.py`'s first real run assumed a 30-row page size (from an undercounted recon grep) and silently double-fetched 50% of every page — 1055 rows for only 545 unique players on the first EPL pull. Fixed by incrementing the offset by the actual row count parsed per page instead of a hardcoded constant, which is now self-correcting if the real page size ever changes again. **Lesson generalized: never hardcode a page-size increment from an assumption — increment by what the page actually returned.**
- **Anti-bot protection is not one problem with one fix, and is not always as hard as the last site made it look.** theshowratings.com/2kratings.com/nhlratings.net all needed real work (TLS impersonation, and for MLB, a paid proxy). sofifa.com — hit fresh this round for EPL/MLS — turned out to need **none of that**: its entire gate is a complete-looking `User-Agent` string, no TLS fingerprinting, no proxy. The apparent block seen first via Windows `curl.exe` was a **client-side artifact** (a schannel TLS-handshake quirk), not a real site protection — confirmed by the fact that plain Python `requests` with a real UA string got a clean 200 on the identical URL, repeatably. **Don't assume the hardest-won fix from the last site is the default difficulty for the next one; test the cheapest thing (a real header) before reaching for TLS impersonation or a proxy.**
- **A numeric ID in a photo/asset URL can be a real join key, or a lookalike fake — verify against 2-3 known real players by hand every time, in both directions.** theshowratings.com's photo URL embeds MLB's real `person_id` (a genuine win). nhlratings.net's superficially similar photo URL is actually the site's own WordPress post ID (a fake). This round: sofifa's player-listing URL has **two** numbers — `/player/{sofifa_id}/{slug}/{version_id}/` — and only the first is a real per-player ID; the trailing number is a fixed game-version/squad-update ID, identical across every row on a page. Caught by checking Haaland/Messi/Salah by hand before trusting the pattern, exactly the discipline that caught nhlratings.net's fake ID two sports ago.
- **When two or more real sources disagree on "who's on which team" or "which teams exist," that's real signal, not noise to average away — dig into *why* before building a join around it.** NHL's roster-vs-stats team disagreement (different-season snapshots, by API design) is the precedent. This round produced two more, both run to ground rather than assumed: (1) EPL's FPL-vs-sofifa 20-team lists disagreed on 3 clubs — turned out FPL's 2026-27 season genuinely includes Coventry/Hull/Ipswich while sofifa's FC26 database still carries Burnley/West Ham/Wolves, a real squad-snapshot lag, not a bug; (2) MLS's ESPN-32-vs-ASA-31-vs-sofifa-30 team-count mismatch turned out to be **ESPN counting 2 fake exhibition "clubs"** (`MLS All-Stars`, `Liga MX All-Stars`) and **ASA carrying one real defunct club** (Chivas USA, folded 2014) that was never filtered out — all three sources agree on the same 30 real current clubs once each side's own padding is excluded.
- **A per-zone-independent "pick the best player for this slot" function silently breaks the moment two zones share one candidate pool** — found and fixed this round, not carried over as a known limitation. NHL's `ice-view.html` computes each rink zone's starter independently; harmless there because its forward trio each maps to a distinct position code, and even its two D-zones sharing one pool go unnoticed (D1/D2 render identically either way). EPL/MLS's 4-3-3 formation has 4 DEF and 3 MID/FWD zones each sharing one pool — copying that pattern verbatim would have shown the *same* player 3-4 times per team. Fixed with a `computeStarters()` that resolves the whole XI in one pass, claiming players zone-by-zone. **Any future FieldView with more than one zone per position-group pool needs this pattern, not the older per-zone one.**
- **A join population is never automatically "the roster" just because a bulk endpoint returned it — check for contamination before trusting the count.** MLS's ESPN bulk athlete list returned 1057 rows, but 42 of them were Arsenal FC's actual EPL squad (leaked in under a stray team_id that turned out to be Arsenal's real `eng.1` ESPN team ID, confirmed by cross-referencing against this same project's own EPL logo lookup — a nice, unplanned cross-check), plus 5 more tagged to the fake exhibition teams above. Real population after filtering: 1010, not 1057. **Always sanity-check a bulk population's team/league tags before treating its row count as ground truth.**

---

## NFL (FormationView) — shipped

### File Map
- `index.html` — home page, entry cards for all sports
- `nfl/nfl-formation-view.html` — formation view, player cards on field
- `nfl/depth-chart.html` — OOTP-style data table

### Scripts (`nfl/scripts/`) — 16 files, real inventory confirmed by reading each
- `scrape_depth.py` — OurLads depth chart scraper → 32 team JSON files (the spine dataset)
- `scrape_otc.py` — Over The Cap contract data, merges `cap_number` into team files
- `scrape_stats.py` — nflreadpy season stats (not `nfl_data_py`)
- `scrape_madden.py` — Madden ratings scraper
- `scrape_contracts_spotrac.py` — Spotrac remaining-contract data (years/cash/APY)
- `build_db.py` — Phase 1: raw ingestion into `nfl/data/fieldview.duckdb`; also live-fetches the GSIS crosswalk CSV and nflreadpy rosters/snap counts and caches them as tables
- `build_match.py` — Phase 2: matching. **Imports its matching functions/alias constants directly from `build_master.py`** (confirmed via the actual `import` statements) rather than reimplementing them
- `export_master.py <output_path>` — Phase 3: joins `player_match` back to `ourlads_players`, writes `players_master.json`
- `build_master.py` — **confirmed not run standalone in the production pipeline** — kept only because `build_match.py` imports its functions; still runnable standalone for parity checks
- `name_utils.py`, `season_utils.py` — shared helpers
- `audit_positions.py`, `diag_positions.py`, `ourlads_check.py`, `resolve_names.py`, `master_check.py` — diagnostic-only, not in the pipeline
- `merge_madden.py` **does not exist** — an older doc's reference to it is stale; `build_master.py`'s Madden team-map is noted in its own comments as "ported from the old `merge_madden.py`," confirming it as historical, not current.

### Real pipeline order (`.github/workflows/scrape.yml`, `scrape` job, verbatim)
`scrape_depth.py` → `scrape_otc.py` → `scrape_stats.py` → `scrape_madden.py` → `build_db.py` → `build_match.py` → `export_master.py nfl/data/players_master.json` → commit.
**Note: `scrape_contracts_spotrac.py` is not invoked by this cloud job at all** — Spotrac data only refreshes when `build_db.py`'s live-cached table is rebuilt some other way (e.g. `run_nfl.bat`, which does include it locally). `nfl/PIPELINE.md` exists with fuller architecture/join-key detail — its cited match-rate figures are older and don't match current numbers below (expected drift, not an error in the doc).

### Real current numbers (2,786 total players, verified live)
- GSIS-matched: 2,052 (73.7%); fallback slug ID: 734 (26.3%)
- Madden: 2,099 (75.3%)
- `snap_pct`: 1,709 (61.3%) — OL alone: 302/503 (60.0%), consistent with the documented real ceiling
- `age`: 2,030 (72.9%); `draft_year`: 2,040 (73.2%); Spotrac remaining contract: 2,575 (92.4%)
- **Real, newly-confirmed gap**: `cap_number` is entirely absent (0 players) in 12/32 team files (ARZ, CAR, CHI, GB, HOU, IND, JAX, MIA, NYJ, PIT, SF, TB) — `scrape_otc.py` isn't currently covering these teams. Not previously documented; worth investigating.

### Schema
`players_master.json` top-level keys (30): `player_id, gsis_id, match_confidence, canonical_name, ourlads_name, team, team_name, base_defense, ourlads_pos, standard_slot, standard_pos, depth, jersey, madden, madden_rank, madden_rank_total, madden_pos_label, cap_number, attainment, injured, stats, stats_season, nflreadpy_name, match_source, draft_year, college, years_pro, age, snap_pct, years_remaining, cash_total_remaining, cash_guaranteed_remaining, avg_annual_remaining`.

Per-team JSON files carry a **smaller** real field set than the master file: `name, depth, injured, attainment, standard_slot, standard_pos, stats, stats_season, cap_number` — `jersey`, `madden`, `age`, `years_pro` only exist post-match, in `players_master.json`, not in the raw team files (a stale doc claimed these were team-file fields; confirmed they are not).

`standard_pos` values: `QB, WR, RB, TE, OL, EDGE, DI, LB, CB, S`. Special teams (K, P, KR, PR, KO, PK, LS, PT, H) are stripped from the pipeline entirely.

### GSIS Matching
- Primary source: dynastyprocess crosswalk CSV (good QB/WR/RB/TE coverage, poor OL/DI). Fallback: nflreadpy `import_weekly_rosters`.
- OL skipped from GSIS matching entirely by design — `find_gsis()` explicitly returns `None` for `standard_pos == 'OL'`, confirmed 0/503 OL players have `gsis_id`. Not a bug; the crosswalk source itself doesn't carry OL.
- Both sources get their own `EDGE`/`DI` position-alias translation before filtering (`CROSSWALK_POS_ALIASES`/`ROSTERS_POS_ALIASES` in `build_master.py`) — this fix is responsible for most of the historical match-rate jump (from ~51% to the current 73.7%).
- **CB/S taxonomy gap, confirmed still real**: `CROSSWALK_POS_ALIASES`/`ROSTERS_POS_ALIASES` only alias `EDGE`/`DI`, not `CB`/`S` — nflreadpy's roster fallback tags all DBs generically as `DB`. In practice this barely dents the real match rate (CB 73.9%, S 78.5%, both close to the 73.7% overall average) because the *primary* crosswalk source does carry real `CB`/`S` tags directly — the gap is specifically in the fallback path for players the primary source misses, not a broad hole.

---

## NBA (CourtView) — shipped, positionless substitution now fully live

### File Map
- `nba/court-view.html` — starting five in half-court zones + rotation list ranked by minutes
- `nba/player-table.html` — sortable/filterable player table

### Scripts (`nba/scripts/`)
- `fetch_stats.py` — nba_api season averages + roster bio, writes `nba_stats.json`. **Runs locally/manually only** — stats.nba.com blocks the hosted GitHub Actions runner's IP specifically (confirmed: identical code succeeds locally, fails only on the runner), so it's deliberately commented out of `scrape-nba`.
- `scrape_2kratings.py` — 2kratings.com per-team scraper, retry+fallback+**daily-trickle** (3 random teams/run against a persisted rolling pool). **Runs locally only**, via the registered Task Scheduler job — not in the cloud job (a commented-out line explains why: doubling the writer doesn't add coverage, it only doubles push-collision risk against the same rolling-pool state file).
- `scrape_contracts_spotrac.py` — Spotrac remaining-contract data, single-page league-wide
- `scrape_nbadepthcharts.py` — nbadepthcharts.com's published Google Sheet CSV export
- `build_nba_db.py` — Phase 1: raw ingestion of the 4 JSON sources above into `fieldview.duckdb`
- `build_nba_match.py` — Phase 2: matching, importing `resolve_position`/`resolve_rotation`/`resolve_team`/`format_salary` from `build_nba_master.py`
- `export_nba_master.py <output_path>` — Phase 3: writes `nba_players_master.json`
- `build_nba_master.py` — same role as NFL's `build_master.py`: not run standalone in production, kept for its resolver functions
- `name_utils.py` — shared `normalize_name()`/`normalize_for_matching()`/`NBA_NAME_ALIASES`
- `schedule_2kratings_scrape.bat` — Task Scheduler entry point, adds a random 0-30min delay before running `scrape_2kratings.py`

### Real pipeline order (`scrape-nba` job, verbatim)
`scrape_contracts_spotrac.py` → `scrape_nbadepthcharts.py` → `build_nba_db.py` → `build_nba_match.py` → `export_nba_master.py nba/data/nba_players_master.json` → commit. `fetch_stats.py` and `scrape_2kratings.py` are both present only as commented-out lines — confirmed neither runs in the cloud job.

### Substitution — confirmed fully positionless, not "in progress"
An older draft note described this as "in progress, not yet confirmed shipped." **Verified false by reading the current code**: the subs-popover pool in `nba/court-view.html` is `teamPlayers.filter(p => !allStarterIds.has(p.id))` with no position filter at all (labeled "Sub in (any position)"), and `substitutePlayer()` sets `manualStarters[targetPos] = p.id` unconditionally with no position check. Any bench player can fill any court zone. This is real, shipped behavior — a deliberate design choice for basketball's positional fluidity, and explicitly **not** the pattern EPL/MLS's PitchView follows (those gate substitution to same-group only, since soccer positions aren't interchangeable the way basketball's are).

### 2K Ratings — real current status
`nba_ratings_2k.json`: 500 records, 482 matched (96.4%), spanning all 30 teams cumulatively across trickle cycles. `ratings_2k_scrape_state.json`: cycle 1, 12 teams remaining in the current rolling pool. **No single run has ever covered all 30 teams at once** (best single-run result remains far below 30), but the *cumulative* trickle has now reached full 30-team coverage in the data file — a real, meaningful distinction from "still incomplete." The Task Scheduler job is genuinely registered and Enabled/Ready, though its last recorded run result code was non-zero — worth a closer look, not yet investigated.

**LeBron James's `rating: null` issue is resolved** — his real current record shows `overall_rating: 91`. Remove from any outstanding-bugs list.

### Real current numbers (587 total players)
`overall_rating`: 478 (81.4%). `contract_salary`: 438 (74.6%). `rotation_source`: `nbadepthchart.com` 444 (75.6%), `mpg_derived` 143 (24.4%).

### Schema
`nba_players_master.json` keys: `player_id, name, team, position, jersey_number, height, weight, ppg, rpg, apg, mpg, games_played, games_started, rotation_status, rotation_source, depth_rank, overall_rating, contract_salary, contract_years_remaining`.

### NBA Position Ranking (court-view.html)
`computePositionRanks(players)` computes each player's league-wide rank within their position group by 2K `overall_rating` (e.g. `PF 3/46`), displayed under starters' names and replacing the plain position letter on bench rows. Players with no rating get no badge at all — never a placeholder. This exact convention (never fabricate a placeholder for missing rating data) is the one EPL/MLS's PitchView explicitly carried forward.

---

## MLB (DiamondView) — shipped, ratings real but local-only

### File Map
- `mlb/diamond-view.html`, `mlb/player-table.html`

### Scripts (`mlb/scripts/`)
- `scrape_roster.py` — statsapi.mlb.com, all 30 teams' rosters+bio, loads directly into `fieldview.duckdb` (no separate `build_db.py` step, unlike NFL/NBA)
- `scrape_stats.py` — bulk `playerPool=all` hitting/pitching pull
- `scrape_ratings.py` — theshowratings.com, 30 team pages, via the ScraperAPI proxy (see ScraperAPI section below). Its join key (the `person_id` embedded in each player's photo URL) doesn't depend on the roster/stats tables at all.
- `build_mlb_match.py` — Phase 2: joins roster+bio+stats, left-joins `show_ratings` if that table exists
- `export_mlb_master.py <output_path>` — Phase 3
- `statsapi_utils.py` — shared `fetch_with_retry`
- `probe_show_ratings.py`, `probe_show_ratings_cell.py`, `probe_show_ratings_cffi.py`, `probe_show_ratings_playwright.py`, `probe_show_ratings_team.py`, `probe_stats.py` — **confirmed dead**, explicitly labeled "throwaway" in their own docstrings, not referenced by the pipeline or `scrape.yml`. Still present in the repo; a housekeeping opportunity, not a functional issue.

### Real pipeline order (`scrape-mlb` job, verbatim — this job is real and exists)
`scrape_roster.py` → `scrape_stats.py` → `build_mlb_match.py` → `export_mlb_master.py mlb/data/mlb_players_master.json` → commit. **`scrape_ratings.py` is deliberately excluded** from this cloud job, per an inline comment — stays local-only pending a decision on whether the ScraperAPI proxy's cost/quota justifies a weekly cloud run too (see ScraperAPI section for the real numbers to make that call with). `build_mlb_match.py` ships correctly without it; ratings just won't refresh from the cloud job alone.

### Real current numbers (780 total players — down from an earlier 782, real roster drift, not an error)
`overall_rating` (theshowratings.com match): 730 (93.6%, down from an earlier 95.3%/745-of-782 — expected drift as rosters change, not a regression to chase). Stats present (batting or pitching): 777 (99.6%).

### Schema
`mlb_players_master.json` keys: `player_id, name, team, team_abbr, position, position_group, position_group_source, player_type, jersey_number, height, weight, bats, throws, batting_stats, pitching_stats, match_source, overall_rating, potential`.

`position_group` distribution: `standalone: 478, IF: 166, OF: 135, null: 1` (Ohtani). Two edge cases confirmed still live and unchanged: Ohtani (`position='TWP'`, `position_group=null`, `player_type='two_way'`); Cristian Pache (`position='OF'`, `position_group='OF'`, `position_group_source='defaulted'`).

---

## NHL (IceView) — shipped, ratings fully blocked at the site level

### File Map
- `nhl/ice-view.html`, `nhl/player-table.html`

### Scripts (`nhl/scripts/`)
- `scrape_roster.py` — all 32 teams via nhl-api-py, uses the **upcoming** season id
- `scrape_stats.py` — league-wide skater/goalie stats, uses the **prior completed** season id, paginated via `start` (the API hard-caps at 100 rows/response regardless of `limit`)
- `build_nhl_match.py` — joins roster (base population) + stats, joins `nhl_ratings` automatically if that table exists
- `export_nhl_master.py <output_path>`
- `scrape_ratings.py` — nhlratings.net, retry+fallback+daily-trickle (mirrors Madden's pattern)
- `name_utils.py`, `season_utils.py` — shared helpers
- `schedule_ratings_scrape.bat` — Task Scheduler entry point

Both `scrape_roster.py` and `scrape_stats.py` load directly into `fieldview.duckdb` themselves, same no-separate-`build_db.py` pattern as MLB.

### Real pipeline order (`scrape-nhl` job, verbatim — real job, exists)
`scrape_roster.py` → `scrape_stats.py` → `build_nhl_match.py` → `export_nhl_master.py nhl/data/nhl_players_master.json` → commit. `scrape_ratings.py` is deliberately excluded, same local-only reasoning as MLB's ratings scraper.

### Ratings — still genuinely, currently blocked (not resolved)
No `nhl_ratings` table exists in `fieldview.duckdb`, and no ratings JSON output exists anywhere in `nhl/data`. `ratings_scrape_state.json` shows cycle 1 (started 2026-08-21) with 17/32 teams still remaining in the pool — meaning roughly 5 trickle runs have executed and every attempted team failed with **no existing data to fall back to**. Every player's `overall_rating` field exists on the schema (ready to be joined the moment ratings data shows up) but is currently always `null` across all 1,268 players. **Real correction to the script's own internal comment**: `scrape_ratings.py` claims the Task Scheduler entry is only a "suggested, not registered" command — that's stale; `FieldView NHL Ratings Scrape` is genuinely registered and active (confirmed via `schtasks /query`).

### Real current numbers (1,268 total players)
Matched to skater/goalie stats: 895 (70.6%). Roster-vs-stats team disagreement remains real and current: a direct join shows 198/810 matched skaters (24.4%) with a different team between the two tables — consistent with the documented by-design different-season snapshot reasoning, not a new problem.

### Schema
`nhl_players_master.json` keys: `player_id, name, team_abbr, position_group, position_code, jersey_number, shoots_catches, height_in_inches, weight_in_pounds, birth_date, birth_city, birth_country, birth_state_province, skater_stats, goalie_stats, stats_source, overall_rating, potential`.

---

## EPL (PitchView) — shipped this round

### File Map
- `epl/pitch-view.html` — fixed 4-3-3 starting XI + bench ranked by minutes
- `epl/player-table.html` — Overview/Stats/Fantasy tabs

### Scripts
- `epl/scripts/scrape_fpl.py` — pulls `fantasy.premierleague.com/api/bootstrap-static/` (no auth, no key, tolerates rapid repeated pulls with no throttling observed), writes `epl/data/epl_players.json`. Keeps real season-stat fields (`minutes, goals_scored, assists, clean_sheets, form, bonus, ...`) under their real FPL names, drops pure FPL-game-mechanics fields (price-change tracking, dreamteam voting, `*_rank`/`*_rank_type`).
- `shared/scripts/scrape_sofifa.py` — **shared with MLS**, takes a league id (`13`=EPL, `39`=MLS) and output path as CLI args. Paginates `/players?type=all&lg[0]={id}`, real page size 60 (self-correcting increment, see Key Cross-Sport Learnings). No proxy/impersonation needed — a real, complete `User-Agent` string alone clears it.
- `shared/scripts/soccer_name_utils.py` — **shared with MLS**, `normalize_name()`/`normalize_for_matching()`/`SOCCER_NAME_ALIASES`. Alias dict keys are the base-population source's name (FPL's for EPL, ESPN's for MLS); values are the matched source's name (sofifa for both; ASA too for MLS).
- `epl/scripts/build_epl_db.py` → `build_epl_match.py` → `export_epl_master.py <output_path>` — the only soccer sport with a real DuckDB layer. Matching is 3-tier: exact name+team → unique name-only → team-scoped token-overlap (for partial/abbreviated legal names, e.g. sofifa's "Gabriel dos S. Magalhães" vs FPL's "...dos Santos Magalhães").

### Real current numbers (604 total players, base population = FPL roster)
Matched to sofifa (rating + granular position): **397 (65.7%)**. Of the unmatched 207: 99 sit on 3 clubs (Coventry/Hull/Ipswich) sofifa's FC26 database doesn't carry at all this season (see Key Cross-Sport Learnings); the rest are a mix of genuine academy/fringe players not in sofifa's rated pool and real transfer/loan-timing mismatches (spot-checked several — confirmed genuinely absent from sofifa, not a matching bug).

### Schema
`epl_players_master.json` keys: `player_id, name, web_name, team, team_short, position_group, standard_pos, overall_rating, potential, sofifa_id, match_source, stats{...}`. `position_group` = FPL's coarse `GKP/DEF/MID/FWD`. `standard_pos` = sofifa's granular slot (`ST/CAM/CM/CDM/LM/RM/LW/RW/LB/RB/CB/GK`) when matched, else `null` — **deliberately the reverse of NFL's `ourlads_pos`(specific)/`standard_pos`(group) naming**, since in soccer the granular label is the conventional "standard" way a position is discussed.

### PitchView frontend
Fixed 4-3-3 for every team (no tactical detection, matching NBA/NHL's fixed-zone simplification). Starting XI ranked by real `stats.minutes` within each of 4 position-group pools (GKP/DEF/MID/FWD), positionless within a group — resolved via a single-pass `computeStarters()` (see Key Cross-Sport Learnings for why per-zone-independent resolution breaks here). Substitution is same-group-only. Hover popup shows Goals/Assists/Minutes/Form plus sofifa OVR/POT when present. Null-rating players show a gray dot and "–", never a placeholder. Team logos: `a.espncdn.com/i/teamlogos/soccer/500/{espn_numeric_id}.png`, all 20 clubs verified live, no naming exceptions needed (unlike NBA/MLB's few oddball cases).

---

## MLS (PitchView) — shipped this round, reuses EPL's PitchView component

### File Map
- `mls/pitch-view.html`, `mls/player-table.html` (Overview/Stats/Advanced tabs)

### Scripts
- `mls/scripts/scrape_espn_roster.py` — ESPN's **core** API (`sports.core.api.espn.com`), not the `site.api.espn.com` host (which returns a real, network-level Akamai 403 for this project's egress IP, confirmed not soccer-specific). No bulk full-object athlete endpoint exists anywhere on this API — pulls the bulk **ref list** (2 calls, `.../seasons/2026/athletes?limit=1000`, 1057 raw ids) then loops individual athlete-detail calls. Confirmed safe at full scale: a real complete 1057-call run hit 0 errors, 0 throttling, ~71.8s total. Filters out 47 contaminating rows before writing (see Key Cross-Sport Learnings) — real population is 1010, not 1057.
- `mls/scripts/fetch_asa_stats.py` — uses the official `itscalledsoccer` PyPI package (MIT, maintained by American Soccer Analysis themselves) rather than raw HTTP — real added value: built-in retry/backoff, a day-long response cache, pandas DataFrames. Pulls `get_player_xgoals(leagues="mls", season_name="2026")` (797 rows) + `get_players()`/`get_teams()` for bio/name resolution (ASA's `player_id`/`team_id` have no name inline in the xgoals call). **Real gotcha found and fixed**: a mid-season-transferred player gets one row with `team_id` as a *list* of every club played for (15/797 rows) — crashed the first run; fixed by leaving that player's team unresolved for matching rather than guessing.
- `shared/scripts/scrape_sofifa.py` — same shared script as EPL, run with `lg[0]=39` → `mls/data/mls_sofifa.json` (836 players).
- `mls/scripts/build_mls_match.py` — **two independent joins** against the ESPN roster base population: ESPN↔ASA (by name) and ESPN↔sofifa (by name), each with its own separately-reported match rate. No DuckDB layer — reads/writes JSON directly.
- `mls/scripts/export_mls_master.py <output_path>`

### Real current numbers (1010 total players, post-filtering)
- ESPN↔ASA (stats): **747 (74.0%)**. Real ceiling, not a matching failure: ASA only has 797 stat rows total for the whole league (players who logged minutes this season) against 1010 rostered players — every one of the 263 unmatched was verified genuinely absent from ASA's stat pool entirely, zero were present-but-missed.
- ESPN↔sofifa (rating + granular position): **780 (77.2%)**. 24 real same-team nickname/spelling/transliteration aliases found and added to `SOCCER_NAME_ALIASES` this round (e.g. "Daniel Musovski" = sofifa's "Danny Musovski," both Seattle Sounders).
- The 31-vs-32-vs-30 team-count question is fully resolved — see Key Cross-Sport Learnings; not a renamed/relocated club, a real definitional difference between the three sources.

### Schema
`mls_players_master.json` keys: `player_id, name, team, team_abbreviation, jersey, age, height, weight, citizenship, position_group, standard_pos, overall_rating, potential, sofifa_id, sofifa_match_source, asa_player_id, asa_match_source, stats{...}`. `position_group` = ESPN's coarse single-letter code (`G/D/M/F` — 104/325/311/270 players — genuinely different from EPL's 3-letter FPL codes, not just a relabeling). `stats` is ASA's xgoals block and can be **entirely null** (263/1010) — a wholly separate nullability axis from `overall_rating`'s (230/1010 null); 132 players have neither. Real ASA field names: `goals`, **`primary_assists`** (not `assists`), **`minutes_played`** (not `minutes`), `points_added` (used as the closest analog to EPL's FPL `form` in the popup/table).

### PitchView frontend
Same fixed-4-3-3, single-pass `computeStarters()`, same-group-only substitution, same null-rating gray-dot/"–" convention as EPL — ported directly, not rebuilt. All 30 teams swept programmatically: 11/11 starters filled, 0 empty zones, 0 duplicates (MLS squads are deep enough that no team ever hits the graceful-degradation "No Player" fallback EPL's 3 forward-thin teams do hit). Team logos: same `a.espncdn.com/i/teamlogos/soccer/500/{espn_numeric_id}.png` pattern, reconfirmed live specifically for `usa.1` rather than assumed from EPL's `eng.1` pattern (Chicago 182, Inter Miami 20232, LAFC 18966, San Diego 22529, Charlotte 21300, all spot-checked 200 with real image bytes).

---

## ScraperAPI — real status

**Used by exactly one script in the entire repo**: `mlb/scripts/scrape_ratings.py` (theshowratings.com). **Not used anywhere else** — NHL's `nhl/scripts/scrape_ratings.py` (nhlratings.net) does not use it or any other proxy; it's still fully blocked at the site level with no proxy attempt made yet. No other sport's scrapers touch it.

- Key handling: read via `os.environ.get("SCRAPERAPI_KEY")` only, raises immediately if unset. **No hardcoded key anywhere** — confirmed by grepping the whole repo.
- Proxy URL pattern: `http://api.scraperapi.com?api_key={key}&url={target}`.
- **Real free-tier terms, confirmed live from scraperapi.com's own pricing page (not assumed)**: the free plan grants **1,000 free API credits, one-time, capped at 5 concurrent connections**; more testing credits require contacting their support directly. No confirmed recurring monthly free allotment.
- **What that means for the open "is it worth running weekly via the cloud too" question** (raised in `scrape.yml`'s and `run_mlb.bat`'s own comments, still unresolved): MLB's full 30-team ratings run uses ~30 requests (one per team page). At 1,000 free credits, that's **~33 full runs** before hitting the free-tier ceiling — roughly 33 weeks if run weekly, well under a year. Whether that's "worth it" depends on whether a paid tier would be needed afterward; that pricing wasn't checked as part of this pass.

---

## Conventions & Gotchas
- OurLads abbreviations: `ARZ` (not ARI), `JAX` (not JAC)
- Team JSON can come out as a list or dict — normalize with `if type(team_data) is list: team_data = team_data[0]`
- Minimal targeted edits only — no unrelated refactors, no adjacent "improvements"
- Match existing code style even if you'd write it differently
- No speculative features or config beyond what's asked
- Plain HTML/CSS/JS only — no React, no build tools
- Live Server (VS Code extension by Ritwick Dey) for local dev preview; a plain `python -m http.server` + headless Playwright is what's actually been used this round to verify FieldView/PlayerTable pages end-to-end against real data (screenshot + console-error check + programmatic all-teams sweep) before calling a build done.
- ESPN's soccer team-logo CDN uses the **numeric ESPN team id**, not a 3-letter code, under an `i/teamlogos/soccer/500/{id}.png` path — a different addressing scheme from every other sport's `i/teamlogos/{sport}/500/{code}.png`, confirmed for both `eng.1` and `usa.1`.
- **Scraper hardening pattern**: anti-bot protection isn't one problem with one fix, and isn't always as hard as the last one — test a real, complete header set with plain `requests` before reaching for `curl_cffi` impersonation, and reach for a paid proxy only if a full-scale run still won't clear (see Key Cross-Sport Learnings' sofifa entry for how big a difference this made this round).
- **Silent bulk-endpoint truncation and pagination assumptions are the single most repeated bug class in this project** (NFL/MLB's `limit` param, NHL's hard 100-row cap, this round's sofifa page-size assumption) — never hardcode a page-size/limit assumption without confirming it against a real multi-page fetch first, and prefer incrementing by the actually-returned count over a hardcoded constant where possible.
- **Graceful degradation over all-or-nothing**, for both scrapers and frontends: Madden's retry+cooldown+fallback-to-last-known-data pattern is the model for scrapers hitting a site that might block; EPL/MLS's "No Player" dashed placeholder for a real thin-position-group is the model for frontends — never drop a team or player just because one zone/field can't be filled.

---

## Known Outstanding Bugs
*(retired since the last pass, confirmed resolved: NBA positionless substitution — shipped, not in-progress; LeBron James `overall_rating: null` — resolved, now 91)*

- **NFL**: OL snap-share coverage sits at ~60% (302/503) — real data-source ceiling, not worth chasing further.
- **NFL**: CB/S taxonomy gap in the nflreadpy-rosters GSIS fallback (all DBs tagged generically `DB`) — real but low-impact (CB/S match rates are in line with the overall average via the primary crosswalk source).
- **NFL, newly found this pass**: `cap_number` is 0% populated in 12/32 team files — `scrape_otc.py` isn't covering these teams. Not previously documented.
- **NBA**: no undo path for a single court substitution short of switching teams away and back.
- **NBA**: `.subs-name` popover text truncation on long names.
- **NBA**: 2K ratings Task Scheduler job's last recorded run had a non-zero result code — task is registered and Enabled/Ready, but worth checking why the last run didn't report clean success.
- **NBA**: `scrape_2kratings.py` has never completed a full 30-team run in one pass — cumulative trickle coverage across cycles has reached all 30 teams, but no single run has.
- **MLB**: `mlb/scripts/probe_show_ratings*.py` (5 files) and `probe_stats.py` are confirmed-dead throwaway diagnostics, still present in the repo — housekeeping, not a functional bug.
- **NHL**: ratings scraper (nhlratings.net) is still fully blocked at the site level — a real trickle test got 0/32 teams with nothing to fall back to. A ScraperAPI-style proxy (MLB's fix) hasn't been tried here yet; now that ScraperAPI's real free-tier cost is known (see above), this is a concretely evaluable option rather than an open unknown.
- **EPL/MLS**: no cloud automation (`scrape.yml` job) or local orchestrator (`run_epl.bat`/`run_mls.bat`) exists for either sport yet — every script is still run by hand.
- **Site-wide**: `index.html`'s NBA and MLB cards both still show a stale `'Mock Data'` feature tag despite both sports having real data for a long time.

---

## Roadmap

**Up Next**
- ⬜ `scrape.yml` automation for EPL and MLS (no jobs exist yet — the two newest sports are the two least automated)
- ⬜ `run_epl.bat` / `run_mls.bat` local orchestrators, matching the other four sports' pattern
- ⬜ NHL ratings via a ScraperAPI-style proxy — now a concretely costed option (~33 free runs at MLB's per-run request volume), not an open unknown
- ⬜ Decide whether MLB's ratings scraper is worth running weekly via the cloud too, now that the free-tier math is known
- ⬜ Fix `index.html`'s stale `'Mock Data'` tags on the NBA and MLB cards
- ⬜ NFL `cap_number` 0%-coverage gap on 12/32 teams (newly found, not yet investigated)
- ⬜ NBA 2K Task Scheduler job's non-zero last-run result code (task is registered/active, but the last run apparently didn't report clean success)
- ⬜ Opponent overlay (NFL)
- ⬜ Additional NFL data sources via `nflreadpy`: `load_ftn_charting()`, `load_nextgen_stats()`, `load_participation()`, `load_combine()` — all free, unused
- ⬜ TableView stat/view-package refinement across all sports
- ⬜ Popover `.subs-name` truncation fix (NBA)
- ⬜ MLB `probe_show_ratings*.py`/`probe_stats.py` cleanup (confirmed dead, still present)
- ⬜ NBA table view column cleanup

**Future State**
- ⬜ ReView — replays, highlights, box scores, tweets, podcasts; comes after every sport's FieldView/TableView are dialed in. Not started for any sport.
- ⬜ Mobile responsiveness pass — desktop-only is the explicit call for now

**Dropped**
- ~~NBA Big/Wing/Guard bucket UI~~ — superseded by the now-shipped positionless substitution.
- ~~OOTP as an MLB ratings source~~ — legal exposure too high. Dropped in favor of theshowratings.com.
- Historical rating trends - not a part of the scope or goal of this website
- Player comparison - not a part of the scope or goal of this website

**Not in FieldView — called ReView:** League leaderboards, game reviews, highlights, replays, podcasts, tweets.