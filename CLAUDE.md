# FieldView — Claude Code Context

Multi-sport intelligence platform. Live at `jwalluww.github.io/fieldview/` (GitHub Pages).

Repo: https://github.com/jwalluww/fieldview (public)

Purpose: each sport gets a FieldView (players on the field/court/pitch in their real positions, with substitutions) and a TableView (sortable/filterable stat table). A future ReView (replays, box scores, highlights) comes after every sport's FieldView/TableView are dialed in — not started yet, tracked in Roadmap only.

**Current status, verified against the real repo (2026-08-31), not carried forward from any prior summary:**
- **NFL, NBA, MLB, NHL** — FieldView + TableView shipped, real data, **all six sports now have real GitHub Actions automation** (`scrape.yml`'s `scrape`/`scrape-nba`/`scrape-mlb`/`scrape-nhl`/`scrape-epl`/`scrape-mls` jobs). NFL/NBA's ratings sources (Madden, 2K) are fully or partially live. **MLB's and NHL's fan-ratings scrapers (theshowratings.com, nhlratings.net) are now both live in the cloud job too**, both routed through the ScraperAPI proxy — MLB confirmed 728/779 (93.5%) and NHL confirmed 855/1266 (67.5%) `overall_rating` coverage from real cloud runs.
- **EPL, MLS** — FieldView + TableView shipped, real data (fantasy.premierleague.com + sofifa.com for EPL; ESPN's core API + American Soccer Analysis + sofifa.com for MLS). **Local orchestrators now exist** (`run_epl.bat`, `run_mls.bat`), each individually verified clean (EPL: 2/2 standalone runs; MLS: 2/2 standalone runs, one absorbing a real transient ASA API timeout via fail-and-continue exactly as designed) and both added as steps 5–6 of `run_all.bat`. **Not yet confirmed**: a full six-sport `run_all.bat` chain has never completed in one sitting — two attempts were killed by session/host restarts before finishing, not by a pipeline error, so this remains genuinely open, not resolved. **`scrape-epl` and `scrape-mls` jobs now exist in scrape.yml, confirmed via a live `workflow_dispatch` run** (both completed clean, numbers matched known baselines within normal week-to-week drift).
- **ReView** — not started, any sport.

---

## Stack
- Frontend: Plain HTML/CSS/JS — no React, no build tools
- Backend: Python 3.11 scrapers, `duckdb`/`pandas` for the match/join layer
- Hosting: GitHub Pages
- Automation: GitHub Actions, `.github/workflows/scrape.yml`, one workflow file holding six jobs (`scrape`=NFL, `scrape-nba`, `scrape-mlb`, `scrape-nhl`, `scrape-epl`, `scrape-mls`), all triggered by a **single shared schedule** (`cron: '0 10 * * 2'` — every Tuesday 10am UTC) plus manual `workflow_dispatch`. No per-job stagger exists — all six fire at the same time.
  - **Push resilience**: all six jobs now do `git pull --rebase && git push` instead of a bare push, added after a real collision was traced to the repo owner's own manual local commit script (an old morning `git add . && commit && push` habit, since retired) landing mid-run. This substantially reduces the collision risk but doesn't eliminate the category — any other future ad-hoc local push during a run window could still theoretically collide.
- Local orchestration: `run_nfl.bat` / `run_nba.bat` / `run_mlb.bat` / `run_nhl.bat` / `run_epl.bat` / `run_mls.bat` each run that sport's full pipeline end-to-end locally (fail-and-continue per step, never git add/commit/push); `run_all.bat` chains all six and prints one aggregate summary. `run_epl.bat` and `run_mls.bat` are newly built and each individually confirmed clean standalone — but the full six-sport `run_all.bat` chain has not yet completed successfully end-to-end (two attempts were interrupted by session/host restarts before finishing; not a code-level failure, but still unverified as a full chain).
  - **Local vs. cloud dependency, post-automation status**: now that all six sports have real scrape.yml jobs, most local .bat orchestrators are redundant for regular use but still valuable for testing script changes before pushing (this is how every fix this session got verified pre-cloud). Three pieces of data are genuinely load-bearing locally, not just redundant, and must NOT be deleted or allowed to stop running:
    - NFL Spotrac contract data (`scrape_contracts_spotrac.py`) — never wired into the `scrape` cloud job; `years_remaining`/`cash_total_remaining`/etc. only refresh via a local `run_nfl.bat`.
    - NBA real stats (`fetch_stats.py`) — permanently local-only by structural necessity, stats.nba.com blocks the GitHub-hosted runner's IP specifically, not a temporary limitation.
    - NBA 2K ratings (`scrape_2kratings.py` via Task Scheduler) — local by choice, not necessity; cloud has no fallback for this data at all.
  Everything else (`run_mlb.bat`, `run_nhl.bat`, `run_epl.bat`, `run_mls.bat`) is now fully covered by its cloud job — safe to stop running regularly, but keep the files for local pre-push testing rather than deleting them. Pattern for retiring a redundant local job: disable, don't delete (see NHL's ratings Task Scheduler job as the precedent) — costs nothing to leave in place, everything to rebuild from scratch if a cloud path ever breaks.
- Task Scheduler (Windows, local machine only): two real scheduled tasks exist — `FieldView NBA 2K Ratings Scrape` (daily 09:15, via `nba/scripts/schedule_2kratings_scrape.bat`) is still Enabled/Ready. `FieldView NHL Ratings Scrape` (daily 09:00, via `nhl/scripts/schedule_ratings_scrape.bat`) is now **Disabled** (not deleted — task still exists, just switched off) now that NHL ratings run via the cloud job instead. Both confirmed via live `schtasks /query`, not assumed from either script's own comments.
- Data pipelines land in DuckDB directly where the source is a live API (statsapi.mlb.com, nhl-api-py) — no intermediate JSON dump for the *join* layer, though the raw scrape output is still written to JSON first in every sport. EPL/MLS deviate further: **EPL has a DuckDB layer** (`epl/data/fieldview.duckdb`, `build_epl_db.py` → `build_epl_match.py` → `export_epl_master.py`) but **MLS has none** — `mls/scripts/build_mls_match.py` reads/writes JSON directly, no DB step, by design (a two-way name join doesn't need SQL).

---

## Site Infrastructure

**Custom domain — attempted, dropped**: a `CNAME` at the repo root once pointed `www.fieldview.com` at GitHub Pages, but this never resolved — DNS check ran indefinitely, and it turned out someone else already owns `fieldview.com`, with no path found to actually acquire it. Dropped; the site runs on the default `jwalluww.github.io/fieldview/` URL, matching the header of this doc. Revisit only if a different domain is chosen.

**Analytics**: Google Analytics (GA4), `gtag.js`, Measurement ID `G-TP0M77Z31N`, present on every real HTML page in the repo (`index.html` + every sport's FieldView + player-table file) — confirmed present on `epl/pitch-view.html`, `epl/player-table.html`, `mls/pitch-view.html`, `mls/player-table.html` too, same snippet as every other page. **This already shipped without needing a custom domain** — AdSense was the reason a domain was originally wanted, not GA.

**Monetization notes, factual not advisory**: AdSense has no minimum traffic requirement, but does require a real top-level domain, not a shared `github.io` subdomain — worth knowing if AdSense is still a goal, since the domain plan above was meant to unblock it and that attempt didn't pan out. Premium networks (Mediavine, Raptive/AdThrive) gate by traffic instead — Mediavine's classic threshold is ~50,000 sessions/month — but check each network's current site directly when actually approaching that point, not from memory.

**Resolved**: `index.html`'s stale `'Mock Data'` tags on the NBA and MLB cards are fixed — both now read `'Live Subs'`, matching the tag convention already used on NFL's card, verified against the real shipped substitution UI on both `court-view.html` and `diamond-view.html`.

---

## Workflow Notes
- Use this chat (claude.ai) for architecture decisions, debugging with context, pushback.
- Use Claude Code (VS Code chat panel) for implementation, real data verification, and live reconnaissance against external sites/APIs.
- **Reconnaissance against live external systems belongs in Claude Code, handed off as one broader investigation task** — this chat's sandbox has no working browser and a locked-down network. Splitting recon into one probe-per-question wastes round trips; hand off one combined investigation and let Claude Code adjust/retry in its own loop.
- **For real scripts, give Claude Code a precise spec with verified facts and named edge cases, rather than full verbatim code written blind in chat.** Chat can't execute or test what it writes. Real bugs caught only because Claude Code tested its own code, across every sport built so far: MLB's blanket-zero `batting_stats` leaking pitchers into batting orders, a `position_group` mislabel, NHL's silent bulk-endpoint truncation, and a sofifa pagination bug plus a token-overlap name-matcher that normalized before tokenizing, both caught by actually running the code against real data rather than trusting it on inspection.
- **Long-running local verification (e.g. a full multi-sport `run_all.bat` pass) should be run in the foreground, watched directly by the user** — backgrounding it through a tool session risks the process getting silently killed by a session/host restart mid-run, which happened twice in a row with zero pipeline-level cause. A background run that dies early looks identical to a hang; don't assume the pipeline itself is at fault before checking whether the process even survived.
- Chat's real value-add: cross-cutting consistency a per-file view might miss — "extract this into a shared file, a second sport needs it now" (`nfl/scripts/season_utils.py`, `nba/scripts/name_utils.py`, `mlb/scripts/statsapi_utils.py`, `shared/scripts/scrape_sofifa.py` + `shared/scripts/soccer_name_utils.py`, deliberately built shared from the start since EPL/MLS both needed the same sofifa scraper and name-matching approach).
- Start a new chat when switching to a new sport or major new feature area.
- End every investigation or implementation task (in this chat or in Claude
  Code) with a short plain-language TLDR: what was broken, what changed, why
  it matters — a few sentences, no jargon or file names, something a
  non-technical read could follow. This is IN ADDITION to the full technical
  report, not a replacement for it. Label it 'TLDR:' at the very end.

---

## Key Cross-Sport Learnings

- **"Verify the real field/column names before writing normalize logic" has paid off on every sport built so far**, including EPL/MLS: FPL's real `element_type`/`first_name`/`second_name` shape, ESPN's core-API athlete shape, ASA's real `itscalledsoccer` column names (`primary_assists` not `assists`, `minutes_played` not `minutes`) were all confirmed live before a matching script got written, catching real mismatches (MLS's `position_group` turned out to be single-letter ESPN codes `G/D/M/F`, not FPL's 3-letter `GKP/DEF/MID/FWD` — a genuinely different enum between the two soccer builds, not just relabeling).
- **Silent bulk-endpoint truncation and pagination bugs are a recurring, not one-off, class of bug.** NFL/MLB's `/v1/stats` needed a bigger `limit`/`playerPool=all`. NHL's `/stats/rest` hard-caps at 100 rows regardless of `limit`, needing real `start`-based pagination. `shared/scripts/scrape_sofifa.py`'s first real run assumed a 30-row page size (from an undercounted recon grep) and silently double-fetched 50% of every page. Fixed by incrementing the offset by the actual row count parsed per page instead of a hardcoded constant, which is now self-correcting if the real page size ever changes again. **Lesson generalized: never hardcode a page-size increment from an assumption — increment by what the page actually returned.**
- **Anti-bot protection is not one problem with one fix, and is not always as hard as the last site made it look.** theshowratings.com/2kratings.com/nhlratings.net all needed real work (TLS impersonation, and for MLB, a paid proxy). sofifa.com turned out to need **none of that**: its entire gate is a complete-looking `User-Agent` string, no TLS fingerprinting, no proxy. **Don't assume the hardest-won fix from the last site is the default difficulty for the next one; test the cheapest thing (a real header) before reaching for TLS impersonation or a proxy.**
- **A numeric ID in a photo/asset URL can be a real join key, or a lookalike fake — verify against 2-3 known real players by hand every time, in both directions.** theshowratings.com's photo URL embeds MLB's real `person_id` (a genuine win). nhlratings.net's superficially similar photo URL is actually the site's own WordPress post ID (a fake). sofifa's player-listing URL has **two** numbers — `/player/{sofifa_id}/{slug}/{version_id}/` — and only the first is a real per-player ID; the trailing number is a fixed game-version/squad-update ID, identical across every row on a page. Caught by checking Haaland/Messi/Salah by hand before trusting the pattern.
- **When two or more real sources disagree on "who's on which team" or "which teams exist," that's real signal, not noise to average away — dig into *why* before building a join around it.** NHL's roster-vs-stats team disagreement (different-season snapshots, by API design) is the precedent. EPL's FPL-vs-sofifa 20-team lists disagreed on 3 clubs (FPL's 2026-27 season includes Coventry/Hull/Ipswich, sofifa's FC26 database still carries Burnley/West Ham/Wolves — a real squad-snapshot lag). MLS's ESPN-32-vs-ASA-31-vs-sofifa-30 team-count mismatch turned out to be **ESPN counting 2 fake exhibition "clubs"** and **ASA carrying one real defunct club** (Chivas USA) never filtered out — all three sources agree on the same 30 real current clubs once each side's own padding is excluded.
- **A per-zone-independent "pick the best player for this slot" function silently breaks the moment two zones share one candidate pool.** NHL's `ice-view.html` computes each rink zone's starter independently; harmless there because its forward trio each maps to a distinct position code. EPL/MLS's 4-3-3 formation has 4 DEF and 3 MID/FWD zones each sharing one pool — copying that pattern verbatim would have shown the *same* player 3-4 times per team. Fixed with a `computeStarters()` that resolves the whole XI in one pass, claiming players zone-by-zone. **Any future FieldView with more than one zone per position-group pool needs this pattern, not the older per-zone one.**
- **A join population is never automatically "the roster" just because a bulk endpoint returned it — check for contamination before trusting the count.** MLS's ESPN bulk athlete list returned raw rows that included Arsenal FC's actual EPL squad under a stray `team_id`, plus rows tagged to fake exhibition teams. **Always sanity-check a bulk population's team/league tags before treating its row count as ground truth.**
- **A live re-run of the same pipeline will produce different real numbers than the original build, and that's expected, not a regression.** EPL's FPL roster grew from 604 to 623 players and its sofifa match rate shifted from 65.7% to 64.2% between the original build and a later orchestrator run — same for MLS's ESPN roster (1057→1065 raw) and both its match rates. Live sports rosters and third-party databases both update continuously; don't chase small drift as a bug unless it's a large or directional shift.
- **Any table view with a separate mobile card-list rendering path needs every function that changes the filtered result set to trigger that mobile re-render, not just the sort function.** NFL's `depth-chart.html` had `applyFilters()` update the desktop table correctly but never call `renderMobileList()` — changing a filter on mobile silently failed to refresh the visible cards until the next resize event. Caught while porting NBA's filter pattern to NFL's, fixed by mirroring NBA's `applyFilters()`, which already called both. Worth checking this explicitly on every sport's TableView, not just assuming parity.

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
- `build_match.py` — Phase 2: matching. **Imports its matching functions/alias constants directly from `build_master.py`** rather than reimplementing them
- `export_master.py <output_path>` — Phase 3: joins `player_match` back to `ourlads_players`, writes `players_master.json`
- `build_master.py` — confirmed not run standalone in the production pipeline — kept only because `build_match.py` imports its functions
- `name_utils.py`, `season_utils.py` — shared helpers
- `audit_positions.py`, `diag_positions.py`, `ourlads_check.py`, `resolve_names.py`, `master_check.py` — diagnostic-only, not in the pipeline

### Real pipeline order (`.github/workflows/scrape.yml`, `scrape` job, verbatim)
`scrape_depth.py` → `scrape_otc.py` → `scrape_stats.py` → `scrape_madden.py` → `build_db.py` → `build_match.py` → `export_master.py nfl/data/players_master.json` → commit (with `git pull --rebase && push`).
**Note: `scrape_contracts_spotrac.py` is not invoked by this cloud job at all** — Spotrac data only refreshes when `build_db.py`'s live-cached table is rebuilt some other way (e.g. `run_nfl.bat`, which does include it locally).

### Real current numbers (2,786 total players, verified live)
- GSIS-matched: 2,052 (73.7%); fallback slug ID: 734 (26.3%)
- Madden: 2,099 (75.3%)
- `snap_pct`: 1,709 (61.3%) — OL alone: 302/503 (60.0%), consistent with the documented real ceiling
- `age`: 2,030 (72.9%); `draft_year`: 2,040 (73.2%); Spotrac remaining contract: 2,575 (92.4%)
- **`cap_number` 0%-coverage gap (12/32 teams) is fixed**: `scrape_otc.py` now also parses each team's Injured Reserve / Physically Unable to Perform tables (found by `<h5>` heading text, not CSS class — those rows use a simpler two-`<td>` structure than the main cap table), and matches them through a shared `NAME_ALIASES` constant in `name_utils.py`. All 32 team files now have non-zero `cap_number` coverage (e.g. MIA: 50/50, 100%).

### Schema
`players_master.json` top-level keys (30): `player_id, gsis_id, match_confidence, canonical_name, ourlads_name, team, team_name, base_defense, ourlads_pos, standard_slot, standard_pos, depth, jersey, madden, madden_rank, madden_rank_total, madden_pos_label, cap_number, attainment, injured, stats, stats_season, nflreadpy_name, match_source, draft_year, college, years_pro, age, snap_pct, years_remaining, cash_total_remaining, cash_guaranteed_remaining, avg_annual_remaining`.

`standard_pos` values: `QB, WR, RB, TE, OL, EDGE, DI, LB, CB, S`. Special teams (K, P, KR, PR, KO, PK, LS, PT, H) are stripped from the pipeline entirely.

### GSIS Matching
- Primary source: dynastyprocess crosswalk CSV. Fallback: nflreadpy `import_weekly_rosters`.
- OL skipped from GSIS matching entirely by design — the crosswalk source doesn't carry OL at all.
- Both sources get their own `EDGE`/`DI` position-alias translation before filtering — this fix is responsible for most of the historical match-rate jump (from ~51% to the current 73.7%).
- **CB/S taxonomy gap, confirmed still real**: the fallback path tags all DBs generically as `DB`. In practice this barely dents the real match rate (CB 73.9%, S 78.5%) because the *primary* crosswalk source carries real `CB`/`S` tags directly.

---

## NBA (CourtView) — shipped, positionless substitution fully live

### File Map
- `nba/court-view.html` — starting five in half-court zones + rotation list ranked by minutes
- `nba/player-table.html` — sortable/filterable player table

### Scripts (`nba/scripts/`)
- `fetch_stats.py` — nba_api season averages + roster bio, writes `nba_stats.json`. **Runs locally/manually only** — stats.nba.com blocks the hosted GitHub Actions runner's IP specifically.
- `scrape_2kratings.py` — 2kratings.com per-team scraper, retry+fallback+**daily-trickle** (3 random teams/run against a persisted rolling pool). **Runs locally only**, via the registered Task Scheduler job — not in the cloud job (doubling the writer doesn't add coverage, it only doubles push-collision risk against the same rolling-pool state file).
- `scrape_contracts_spotrac.py` — Spotrac remaining-contract data, single-page league-wide
- `scrape_nbadepthcharts.py` — nbadepthcharts.com's published Google Sheet CSV export
- `build_nba_db.py` → `build_nba_match.py` → `export_nba_master.py <output_path>`
- `build_nba_master.py` — kept for its resolver functions, not run standalone in production
- `name_utils.py` — shared `normalize_name()`/`normalize_for_matching()`/`NBA_NAME_ALIASES`
- `schedule_2kratings_scrape.bat` — Task Scheduler entry point

### Real pipeline order (`scrape-nba` job, verbatim)
`scrape_contracts_spotrac.py` → `scrape_nbadepthcharts.py` → `build_nba_db.py` → `build_nba_match.py` → `export_nba_master.py nba/data/nba_players_master.json` → commit (rebase-safe push). `fetch_stats.py` and `scrape_2kratings.py` are both present only as commented-out lines — confirmed neither runs in the cloud job.

### Substitution — confirmed fully positionless, shipped
The subs-popover pool has no position filter at all. Any bench player can fill any court zone — a deliberate design choice for basketball's positional fluidity, explicitly **not** the pattern EPL/MLS's PitchView follows (those gate substitution to same-group only).

### 2K Ratings — real current status
`nba_ratings_2k.json`: 500 records, 482 matched (96.4%), spanning all 30 teams cumulatively across trickle cycles. The Task Scheduler job is genuinely registered and Enabled/Ready, though its last recorded run result code was non-zero — not yet investigated.

**LeBron James's `rating: null` issue is resolved** — his real current record shows `overall_rating: 91`.

### Real current numbers (587 total players)
`overall_rating`: 478 (81.4%). `contract_salary`: 438 (74.6%). `rotation_source`: `nbadepthchart.com` 444 (75.6%), `mpg_derived` 143 (24.4%).

### Schema
`nba_players_master.json` keys: `player_id, name, team, position, jersey_number, height, weight, ppg, rpg, apg, mpg, games_played, games_started, rotation_status, rotation_source, depth_rank, overall_rating, contract_salary, contract_years_remaining`.

### NBA Position Ranking (court-view.html)
`computePositionRanks(players)` computes each player's league-wide rank within their position group by 2K `overall_rating` (e.g. `PF 3/46`). Players with no rating get no badge at all — never a placeholder. This exact convention was carried forward into EPL/MLS's PitchView.

### Table Filters (player-table.html)
Team and Position filters upgraded from single-value `<select>` dropdowns to NFL `depth-chart.html`'s multiselect checkbox pattern (multiple teams/positions selectable at once). Group shortcuts: Team → All Eastern/All Western (15/15 split); Position → Guards (PG/SG)/Wings (SF)/Bigs (PF/C). Status filter (Starter/Rotation/Bench) left as single-select — NBA-only, no NFL equivalent to match.

---

## MLB (DiamondView) — shipped, ratings now live in the cloud

### File Map
- `mlb/diamond-view.html`, `mlb/player-table.html`

### Scripts (`mlb/scripts/`)
- `scrape_roster.py` — statsapi.mlb.com, all 30 teams' rosters+bio, loads directly into `fieldview.duckdb` (no separate `build_db.py` step)
- `scrape_stats.py` — bulk `playerPool=all` hitting/pitching pull
- `scrape_ratings.py` — theshowratings.com, 30 team pages, via the ScraperAPI proxy (see ScraperAPI section below)
- `build_mlb_match.py` → `export_mlb_master.py <output_path>`
- `statsapi_utils.py` — shared `fetch_with_retry`

### Real pipeline order (`scrape-mlb` job, verbatim)
`scrape_roster.py` → `scrape_stats.py` → `scrape_ratings.py` → `build_mlb_match.py` → `export_mlb_master.py mlb/data/mlb_players_master.json` → commit (rebase-safe push). `scrape_ratings.py` now runs here too, same ScraperAPI-proxy pattern as NHL's — confirmed via a real triggered `workflow_dispatch` run: 28/30 teams scraped fresh through the proxy, 2 (San Francisco, Texas) fell back to their existing stale rows after both fresh attempts failed, exactly as the retry+fallback design intends.

### Real current numbers (779 total players, confirmed from a live cloud run)
`overall_rating` (theshowratings.com match): 728 (93.5%). Stats present (batting or pitching): comparable to the prior local baseline (777/780, 99.6%), not re-verified this pass.

**SF Giants coverage outlier, investigated**: SF sits at 61.5% (16/26) matched, well below the rest of the league (88–100%). Confirmed via a real person_id-level diff (the join key here is `mlbam_id`, not fuzzy name matching) that this isn't a matching bug: theshowratings.com's own "San Francisco Giants" team page carries 41 rows, several of them players statsapi's roster currently has on other teams entirely (e.g. Aroldis Chapman/BOS, Luis Arraez/PHI, Robbie Ray/SD) — a real source-vs-source roster-snapshot lag, same shape as EPL's FPL-vs-sofifa mismatch. No fix proposed yet — this is a source-freshness question, not a code defect.

### Schema
`mlb_players_master.json` keys: `player_id, name, team, team_abbr, position, position_group, position_group_source, player_type, jersey_number, height, weight, bats, throws, batting_stats, pitching_stats, match_source, overall_rating, potential`.

`position_group` distribution: `standalone: 478, IF: 166, OF: 135, null: 1` (Ohtani, `player_type='two_way'`). Cristian Pache: `position='OF'`, `position_group_source='defaulted'`.

---

## NHL (IceView) — shipped, ratings now live via ScraperAPI

### File Map
- `nhl/ice-view.html`, `nhl/player-table.html`

### Scripts (`nhl/scripts/`)
- `scrape_roster.py` — all 32 teams via nhl-api-py, uses `season_utils.resolve_seasons()`'s roster-season id
- `scrape_stats.py` — league-wide skater/goalie stats, uses `resolve_seasons()`'s stats-season id, paginated via `start`
- `build_nhl_match.py` → `export_nhl_master.py <output_path>`
- `scrape_ratings.py` — nhlratings.net, now a full 32-team pull in one run via the ScraperAPI proxy (replaced an earlier retry+fallback+daily-trickle design — no more 3-team-a-day sampling needed now that the proxy actually clears the block)
- `schedule_ratings_scrape.bat` — Task Scheduler entry point; the registered task now sits **Disabled** (not deleted) since ratings run via the cloud job instead

### Season resolution (`season_utils.py`, fixed 2026-08-31)
`resolve_seasons()` finds the real "current" season by querying the API's standings manifest directly, not by guessing from today's date, and can return roster/stats seasons a cycle apart during the offseason gap (rosters move to the upcoming season as free agency/trades happen; stats stay on the season that just ended until the new one has actually played games). Replaces an earlier version that only advanced `stats_season` once a season fully finished (~June) — which would have kept serving the *prior* season's stats for the entire ~8-month span of every new NHL season, a real staleness bug, not just an inconvenience.

### Real pipeline order (`scrape-nhl` job, verbatim)
`scrape_roster.py` → `scrape_stats.py` → `scrape_ratings.py` (via ScraperAPI, `SCRAPERAPI_KEY` secret) → `build_nhl_match.py` → `export_nhl_master.py nhl/data/nhl_players_master.json` → commit (rebase-safe push).

### Ratings — no longer blocked
`nhlratings.net` is cleared via the same ScraperAPI proxy MLB's ratings scraper uses, confirmed live across all 32 teams. `overall_rating` populated: 855/1266 (67.5%).

### Real current numbers (1,266 total players)
Matched to skater/goalie stats: 896 (70.8%). Roster-vs-stats team disagreement remains real and current (different-season snapshot design), not a new problem.

### Schema
`nhl_players_master.json` keys: `player_id, name, team_abbr, position_group, position_code, jersey_number, shoots_catches, height_in_inches, weight_in_pounds, birth_date, birth_city, birth_country, birth_state_province, skater_stats, goalie_stats, stats_source, overall_rating, potential`.

---

## EPL (PitchView) — shipped

### File Map
- `epl/pitch-view.html` — fixed 4-3-3 starting XI + bench ranked by minutes
- `epl/player-table.html` — Overview/Stats/Fantasy tabs
- `run_epl.bat` (repo root) — local orchestrator, runs the full pipeline below end-to-end; confirmed clean twice, standalone

### Scripts
- `epl/scripts/scrape_fpl.py` — pulls `fantasy.premierleague.com/api/bootstrap-static/` (no auth, no key, tolerates rapid repeated pulls with no throttling observed), writes `epl/data/epl_players.json`.
- `shared/scripts/scrape_sofifa.py` — **shared with MLS**, takes a league id (`13`=EPL, `39`=MLS) and output path as CLI args. Paginates `/players?type=all&lg[0]={id}`, real page size 60 (self-correcting increment). No proxy/impersonation needed — a real, complete `User-Agent` string alone clears it.
- `shared/scripts/soccer_name_utils.py` — **shared with MLS**, `normalize_name()`/`normalize_for_matching()`/`SOCCER_NAME_ALIASES`.
- `epl/scripts/build_epl_db.py` → `build_epl_match.py` → `export_epl_master.py <output_path>` — the only soccer sport with a real DuckDB layer. Matching is 3-tier: exact name+team → unique name-only → team-scoped token-overlap.

### Real pipeline order (`scrape-epl` job, verbatim)
Mirrors `run_epl.bat`'s step order exactly. Confirmed via a live `workflow_dispatch` run: 626 FPL players, 400 matched to sofifa (63.9%) — consistent with prior baselines, normal week-to-week drift.

### Real current numbers
Confirmed via two separate live runs — numbers drift between them, which is expected (live rosters and sofifa's own database both update; see Key Cross-Sport Learnings), not a regression:
- **Original build**: 604 FPL players, 397 matched to sofifa (65.7%).
- **Latest orchestrator run** (`run_epl.bat`): 623 FPL players, 400 matched to sofifa (64.2%) — 328 via name+team, 37 via unique name-only, 35 via team-scoped token overlap, 223 unmatched.
- The cloud run above (626/400, 63.9%) sits in this same range — no meaningful shift.

Of the original build's unmatched pool, 99 sat on 3 clubs (Coventry/Hull/Ipswich) sofifa's FC26 database didn't carry that season; the rest were a mix of genuine academy/fringe players and real transfer/loan-timing mismatches (spot-checked several, confirmed genuinely absent, not a matching bug). Not re-verified against the newer 223-unmatched count — worth re-checking if this becomes a focus.

### Schema
`epl_players_master.json` keys: `player_id, name, web_name, team, team_short, position_group, standard_pos, overall_rating, potential, sofifa_id, match_source, stats{...}`. `position_group` = FPL's coarse `GKP/DEF/MID/FWD`. `standard_pos` = sofifa's granular slot (`ST/CAM/CM/CDM/LM/RM/LW/RW/LB/RB/CB/GK`) when matched, else `null`.

### PitchView frontend
Fixed 4-3-3 for every team. Starting XI ranked by real `stats.minutes` within each of 4 position-group pools, resolved via a single-pass `computeStarters()`. Substitution is same-group-only. Null-rating players show a gray dot and "–", never a placeholder. Team logos: `a.espncdn.com/i/teamlogos/soccer/500/{espn_numeric_id}.png`, all 20 clubs verified live.

---

## MLS (PitchView) — shipped, reuses EPL's PitchView component

### File Map
- `mls/pitch-view.html`, `mls/player-table.html` (Overview/Stats/Advanced tabs)
- `run_mls.bat` (repo root) — local orchestrator, runs the full pipeline below end-to-end; confirmed clean twice standalone (one run correctly absorbed a real transient ASA API timeout via fail-and-continue rather than failing the whole run)

### Scripts
- `mls/scripts/scrape_espn_roster.py` — ESPN's **core** API (`sports.core.api.espn.com`). No bulk full-object athlete endpoint exists — pulls a bulk ref list (2 calls) then loops individual athlete-detail calls. Confirmed safe at full scale (a real ~1000-call run: 0 errors, 0 throttling, ~70-80s total). Filters out contaminating rows (exhibition-team/stray-team_id) before writing.
- `mls/scripts/fetch_asa_stats.py` — uses the official `itscalledsoccer` PyPI package. Pulls `get_player_xgoals(leagues="mls", season_name="2026")` + `get_players()`/`get_teams()` for bio/name resolution. A mid-season-transferred player can get a `team_id` as a *list* of every club played for — handled by leaving that player's team unresolved for matching rather than guessing.
- `shared/scripts/scrape_sofifa.py` — same shared script as EPL, run with `lg[0]=39`.
- `mls/scripts/build_mls_match.py` — **two independent joins** against the ESPN roster base population: ESPN↔ASA (by name) and ESPN↔sofifa (by name), each with its own separately-reported match rate. No DuckDB layer — reads/writes JSON directly.
- `mls/scripts/export_mls_master.py <output_path>`

### Real pipeline order (`scrape-mls` job, verbatim)
Mirrors `run_mls.bat`'s step order exactly. Confirmed via a live `workflow_dispatch` run: 1019 base population, ESPN↔ASA 753/1019 (73.9%), ESPN↔sofifa 780/1019 (76.5%) — consistent with prior baselines.

### Real current numbers
Confirmed via two separate live runs — same expected drift pattern as EPL:
- **Original build**: 1057 raw ESPN athletes → 1010 base population after filtering. ESPN↔ASA 747/1010 (74.0%). ESPN↔sofifa 780/1010 (77.2%).
- **Latest orchestrator run** (`run_mls.bat`): 1065 raw ESPN athletes → 1018 base population after filtering (same exclusion logic, 47 rows). ESPN↔ASA 745/1018 (73.2%) — 720 via name+team, 18 via unique name-only, 7 via token overlap, 273 unmatched. ESPN↔sofifa 779/1018 (76.5%) — 718 via name+team, 16 via unique name-only, 45 via token overlap, 239 unmatched. 16 ASA stat rows spanned multiple teams mid-season, same unresolved-team-for-matching handling as before.

ASA's match ceiling remains a real, not-fixable-via-matching limit: ASA only carries stat rows for players who've logged minutes, a smaller pool than the full roster by design. The 31-vs-32-vs-30 team-count question is fully resolved — see Key Cross-Sport Learnings.

### Schema
`mls_players_master.json` keys: `player_id, name, team, team_abbreviation, jersey, age, height, weight, citizenship, position_group, standard_pos, overall_rating, potential, sofifa_id, sofifa_match_source, asa_player_id, asa_match_source, stats{...}`. `position_group` = ESPN's coarse single-letter code (`G/D/M/F`). `stats` is ASA's xgoals block and can be entirely null — a separate nullability axis from `overall_rating`'s. Real ASA field names: `goals`, `primary_assists` (not `assists`), `minutes_played` (not `minutes`), `points_added` (used as the closest analog to EPL's FPL `form`).

### PitchView frontend
Same fixed-4-3-3, single-pass `computeStarters()`, same-group-only substitution, same null-rating convention as EPL — ported directly. All 30 teams swept programmatically: 11/11 starters filled, 0 empty zones, 0 duplicates. Team logos: same CDN pattern, reconfirmed live specifically for `usa.1`.

---

## ScraperAPI — real status

**Used by two scripts now**: `mlb/scripts/scrape_ratings.py` (theshowratings.com) and `nhl/scripts/scrape_ratings.py` (nhlratings.net), both now running in their sport's cloud job (`scrape-mlb`, `scrape-nhl`).

- Key handling: read via `os.environ.get("SCRAPERAPI_KEY")` only, raises immediately if unset. No hardcoded key anywhere.
- Proxy URL pattern: `http://api.scraperapi.com?api_key={key}&url={target}`.
- **Real free-tier terms, corrected**: the free plan is **1,000 credits per month, recurring** — not one-time as a prior pass of this doc claimed. No card on file, so no charge risk either way.
- **Real combined volume**: MLB's ~30 requests/week (one per team page) is roughly ~130 requests/month; NHL's 32-team weekly run is roughly ~139 requests/month. Combined, well under the 1,000/month recurring cap, indefinitely, not a depleting pool with an end date. NBA's 2K ratings remain on the local Task Scheduler trickle by choice, not because ScraperAPI's volume would be a problem there too.
- **User preference, explicit**: no credit card on file, staying on the free tier by choice, not by necessity.
- NBA 2K ratings' local-only status is a "by choice" designation, not a leftover — see the Stack section's "Local vs. cloud dependency" bullet.

---

## Conventions & Gotchas
- OurLads abbreviations: `ARZ` (not ARI), `JAX` (not JAC)
- Team JSON can come out as a list or dict — normalize with `if type(team_data) is list: team_data = team_data[0]`
- Minimal targeted edits only — no unrelated refactors, no adjacent "improvements"
- Match existing code style even if you'd write it differently
- No speculative features or config beyond what's asked
- Plain HTML/CSS/JS only — no React, no build tools
- A plain `python -m http.server` + headless Playwright is what's been used to verify FieldView/PlayerTable pages end-to-end against real data (screenshot + console-error check + programmatic all-teams sweep) before calling a build done.
- ESPN's soccer team-logo CDN uses the **numeric ESPN team id**, not a 3-letter code, under an `i/teamlogos/soccer/500/{id}.png` path — a different addressing scheme from every other sport's `i/teamlogos/{sport}/500/{code}.png`.
- **Scraper hardening pattern**: anti-bot protection isn't one problem with one fix, and isn't always as hard as the last one — test a real, complete header set with plain `requests` before reaching for `curl_cffi` impersonation, and reach for a paid proxy only if a full-scale run still won't clear.
- **Silent bulk-endpoint truncation and pagination assumptions are the single most repeated bug class in this project** — never hardcode a page-size/limit assumption without confirming it against a real multi-page fetch first.
- **Graceful degradation over all-or-nothing**, for both scrapers and frontends: Madden's retry+cooldown+fallback-to-last-known-data pattern is the model for scrapers hitting a site that might block; EPL/MLS's "No Player" dashed placeholder is the model for frontends.

---

## Known Outstanding Bugs
*(retired since the last pass, confirmed resolved: NBA positionless substitution; LeBron James `overall_rating: null` (now 91); `index.html`'s stale 'Mock Data' tags (now 'Live Subs'); MLB's dead `probe_*.py` files (deleted); NFL's 12/32-team `cap_number` gap (IR/PUP parsing + shared name aliases added); NHL's ratings block (ScraperAPI proxy clears it, all 32 teams); NHL's stats-season staleness bug (`resolve_seasons()` would have served the prior season's stats for ~8 months after each new season started — fixed 2026-08-31); EPL/MLS's scrape.yml automation added and confirmed live (scrape-epl, scrape-mls jobs); NBA's `.subs-name` popover truncation (widened `.subs-pop` to 184px); NBA's no-undo-path for court substitutions (single-level undo added, zone-keyed, clears on team switch); NBA's Team/Position filters upgraded from single-select to NFL's multiselect pattern (with Eastern/Western and Guards/Wings/Bigs group shortcuts); NFL's dead `.filter-select` CSS removed; NFL's mobile filter-refresh bug fixed as a bonus find during that same investigation (`applyFilters()` now calls `renderMobileList()`, matching NBA's existing pattern))*

- **NFL**: OL snap-share coverage sits at ~60% (302/503) — real data-source ceiling, not worth chasing further.
- **NFL**: CB/S taxonomy gap in the nflreadpy-rosters GSIS fallback (all DBs tagged generically `DB`) — real but low-impact.
- **NBA**: 2K ratings Task Scheduler job's last recorded run had a non-zero result code — task is registered and Enabled/Ready, but worth checking why the last run didn't report clean success. **Genuinely unresolved**: Task Scheduler history logging was checked and found disabled (`Microsoft-Windows-TaskScheduler/Operational` log, `IsEnabled: False`) — both `schtasks /query` and `Get-ScheduledTaskInfo` only expose the *most recent* run's result, not a history, so the specific past non-zero code isn't recoverable. A manual re-run (including one under a full 3-team block) reproduced a clean exit 0, and the script has no `sys.exit()` call anywhere in it — whatever caused the historical non-zero code was most likely a one-off unhandled exception, not a reproducible bug. Added basic error logging (`nba/data/2kratings_errors.log`) so a future occurrence leaves a trail. Worth enabling Task Scheduler history logging (needs an elevated/admin session) if this recurs.
- **NBA**: `scrape_2kratings.py` has never completed a full 30-team run in one pass — cumulative trickle coverage across cycles has reached all 30 teams, but no single run has.
- **MLB**: SF Giants sits at 61.5% `overall_rating` coverage vs. the league's 88-100% — confirmed a real theshowratings.com roster-snapshot lag, not a matching bug (see MLB section). Decision: no sport-specific fix. `overall_rating`/`potential` aren't currently rendered anywhere in MLB's frontend to begin with — `diamond-view.html`'s field dot uses AVG/ERA, not the Show rating, and `player-table.html` has no rating column — so there's no user-visible gap for SF's lower coverage to actually show up in yet, and the underlying source-snapshot lag is expected to self-correct regardless. Not treated as an open bug going forward.
- **EPL/MLS**: cloud automation now exists and is confirmed working independently for both sports. The full six-sport `run_all.bat` chain has still never completed in one sitting (two attempts interrupted by session/host restarts, not a pipeline error) — lower priority now that each sport also refreshes independently via its own cloud job regardless of whether the full local chain ever completes.

---

## Roadmap

**Up Next**
- ⬜ Confirm a full six-sport `run_all.bat` chain completes end-to-end in one watched, foreground run (not yet achieved — two attempts interrupted by session/host restarts, unrelated to the pipeline itself) — note this is no longer a freshness blocker for EPL/MLS specifically, both now refresh weekly via their own independent cloud jobs regardless
- ⬜ NBA 2K Task Scheduler job's non-zero last-run result code — root cause not fully resolved (see Known Outstanding Bugs); enabling Task Scheduler history logging would help if it recurs, needs an elevated/admin session to turn on
- ⬜ Opponent overlay (NFL)
- ⬜ Additional NFL data sources via `nflreadpy`: `load_ftn_charting()`, `load_nextgen_stats()`, `load_participation()`, `load_combine()` — all free, unused
- ⬜ TableView stat/view-package refinement across all sports

**Future State**
- ⬜ ReView — replays, highlights, box scores, tweets, podcasts; comes after every sport's FieldView/TableView are dialed in. Not started for any sport.
- ⬜ Mobile responsiveness pass — desktop-only is the explicit call for now
- ⬜ A real custom domain, if AdSense monetization is ever pursued — the earlier `fieldview.com` attempt didn't pan out (see Site Infrastructure); GA4 is already live and doesn't need this, only AdSense does

**Dropped**
- ~~NBA Big/Wing/Guard bucket UI~~ — superseded by the now-shipped positionless substitution.
- ~~OOTP as an MLB ratings source~~ — legal exposure too high. Dropped in favor of theshowratings.com.
- Historical rating trends - not a part of the scope or goal of this website
- Player comparison - not a part of the scope or goal of this website
- A `CNAME` at the repo root pointing the custom domain `www.fieldview.com` — didn't work, someone else appears to own `fieldview.com` and there was no clear path to buy it; DNS check just ran forever. Site stays on the default GitHub Pages URL.
- MLB SF Giants ratings-coverage gap — decided not to build a source-specific fix; `overall_rating` isn't currently displayed anywhere in MLB's frontend, so there's no user-visible gap to address, and it's a source-side snapshot lag expected to self-correct.

**Not in FieldView — called ReView:** League leaderboards, game reviews, highlights, replays, podcasts, tweets.