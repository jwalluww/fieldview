# FieldView — Claude Code Context

Multi-Sport intelligence platform.
Live at https://jwalluww.github.io/fieldview/
Repo: https://github.com/jwalluww/fieldview (public)
Purpose: FieldView is the primary website for sports analytics. Each sport will have a FieldView and a TableView. NFL has FormationView, NBA has CourtView, NHL has IceView, MLB has DiamondView, MLS has PitchView (EPL will also have PitchView). This view will show all the players in their positions on the playing field with important metrics & statistics and substitutions. TableView for each sport will be a table with statistics. Eventually, ReView will be created for each sport. FieldView is for before the game - understanding where players play on the field. ReView is for after the game - replays, highlights, tweets, stats, box scores, etc. - a one-stop-shop for what happened last night or last week in the sport in general.

Flow: NFL and NBA FormationView/CourtView are in good shape — layout, sizing, backgrounds, and substitution UX have all been through real design-and-ship rounds. MLB (DiamondView) shipped a full first pass this round — roster, stats, and both views built and verified; ratings blocked pending a Cloudflare cooldown, same status class as NBA's 2K ratings. NHL (IceView) recon is complete — one-team roster and league-wide skater/goalie stats verified in the DB, season-resolution logic built and confirmed live; still ahead is scaling the roster pull to all 32 teams and building the match/export pipeline.

---

## Stack
- Frontend: Plain HTML/CSS/JS — no React, no frameworks
- Backend: Python 3.11 scrapers
- Hosting: GitHub Pages
- Automation: GitHub Actions (runs Tuesdays at 10am UTC) — note `fetch_stats.py` (NBA) is no longer part of the cloud job, see NBA Stats Scraper section below
- Dev environment: Windows, VS Code + Claude Code extension (chat panel)
- Data pipelines land in DuckDB directly where the source is a live API (statsapi.mlb.com, nhl-api-py) — no intermediate JSON dump. Where the source is a scrape needing careful parsing (theshowratings.com), same DuckDB-first approach once past the network layer.

---

## Workflow Notes
- Use this chat (claude.ai) for architecture decisions, debugging with context, pushback.
- Use Claude Code (VS Code chat panel) for implementation, real data verification, and live reconnaissance against external sites/APIs.
- **Reconnaissance against live external systems belongs in Claude Code, handed off as one broader investigation task — not run as a sequence of probe scripts round-tripped through chat.** This chat's sandbox has no working browser and a locked-down network (package registries only, not arbitrary sites/APIs), so any live fact-finding has to go through Claude Code anyway. Splitting it into one probe-per-question wastes round trips; Claude Code can investigate, adjust, and retry inside its own loop and report back once. (MLB's stats-endpoint and ratings-site recon both got done this way properly late in that build; NHL's kickoff recon was handed off as one combined task from the start.)
- **For real scripts, give Claude Code a precise spec with verified facts and named edge cases, rather than full verbatim code written blind in chat.** Chat can't execute or test what it writes — a real bug shipped this way mid-MLB-build (a `fetch_with_retry` helper written without a `timeout` parameter, then called with `timeout=30` anyway, would've thrown immediately). Claude Code, writing and testing its own implementation, independently caught two more substantive bugs later in the same build with zero chat involvement: a blanket-zero `batting_stats` block leaking pure pitchers into batting orders, and a `position_group` mislabel (`'CF'` instead of the group `'OF'`) that would've silently broken one player's substitution eligibility. Neither would've been caught by chat writing code blind.
- Chat's actual value-add on the implementation side is cross-cutting consistency a per-file view might miss: flagging "extract this into a shared file, a second script needs it now" (this is what produced `nfl/scripts/season_utils.py`, `nba/scripts/name_utils.py`, and `mlb/scripts/statsapi_utils.py`), or "these two tables aren't 1:1, don't treat a mismatch as a bug" ahead of time.
- Front-load thinking in chat → hand Claude Code a crisp specific instruction (spec, not code, where the code needs testing to be trusted).
- Start a new chat when switching to a new sport or major new feature area.
- Paste this CLAUDE.md at the top of any new chat to restore context.

---

## Key Cross-Sport Learnings
- **"Verify the real field/column names before writing normalize logic" has paid off on every sport so far** — NFL's EDGE/DI position-alias gap, MLB's stats endpoint field names, NHL's roster/stats shapes were all confirmed against real source code or real API responses before a matching script got written, not assumed from memory or documentation summaries.
- **Silent bulk-endpoint truncation is 3-for-3, but the fix mechanism isn't always the same**: NFL/MLB's `/v1/stats` just needed a bigger `limit`/`playerPool=all` param. NHL's skater/goalie stats endpoints are different — confirmed live that they hard-cap each response at 100 rows server-side *regardless* of the `limit` value passed (tried up to 100000, still 100 back), so the real fix was pagination via the `start` param, not a bigger limit. Worth checking which kind of cap a new bulk endpoint has, not just whether one exists.
- **`curl_cffi` with `impersonate="chrome120"` is the standing fix for Cloudflare/TLS-fingerprint blocks**, now confirmed working on two separate fan-ratings sites (theshowratings.com, and originally attempted on 2kratings.com) after plain `requests` got 403'd on both. Confirmed the block operates at the TLS-handshake layer, not the HTTP-header layer — header tuning alone doesn't fix it.
- **Anti-bot cooldowns are real and compounding**: repeated attempts during an active block extend it rather than get past it, on both 2kratings.com and theshowratings.com. Standing rule: one clean test, then stop and wait hours/overnight if blocked — don't retry same-day.
- **A "population mismatch" between a roster snapshot and a season-stats pull is expected, not a bug**: MLB's `statsapi_stats_hitting`/`statsapi_stats_pitching` (702/799 players, includes anyone who played in 2026 at all — including traded/released players) don't 1:1 match `statsapi_roster` (782 players, today's snapshot only). `mlb_players_master.json` uses roster as the base population deliberately, since DiamondView's job is showing today's team, not full-season history.
- **A numeric ID buried in an unrelated-looking asset URL can be a real, reliable join key** — theshowratings.com's player photo `data-src` (`ketel-marte-606466-80x80.png`) embeds the actual MLB Advanced Media `person_id`, confirmed by direct match against `statsapi_roster`. If MLB ratings ever gets unblocked, that means zero fuzzy name matching needed — a cleaner situation than NBA's 2K ratings ever achieved. Worth checking for the same pattern on any new fan-ratings site (NHL's candidates included).

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

## 2K Ratings Scraper (nba/scripts/scrape_2kratings.py) — full 30-team run still blocked, but daily-trickle mode is working
- Started failing with 403 Forbidden mid-run (8/30 teams succeeded, then blocked for the rest of that run) — a different failure signature than `fetch_stats.py`'s timeout (a hard rejection, not a hang).
- Ruled out request speed (existing ~1–1.5s delay between requests was already reasonable) and thin headers (added a full browser-realistic header set + `requests.Session()` for cookie persistence) — neither fixed it. A rerun immediately after actually failed *faster* (blocked on request 1), which pointed at an active IP-level cooldown from the first failed run, not a header gap.
- **Confirmed via direct browser test that the site itself loads fine from the same machine/IP** while the script still gets 403'd even with a full session and complete headers — this rules out a site-wide block or outage and points specifically at **TLS fingerprinting**: Cloudflare-class protection checks the TLS handshake (cipher order, extensions, JA3 signature) before HTTP headers are even read, and Python's `requests`/`urllib3` has a detectably different handshake than real Chrome regardless of what headers are set on top.
- Fix in progress: swapped to `curl_cffi` (`session = requests.Session(impersonate="chrome120")` from the `curl_cffi.requests` module), which mimics Chrome's real TLS/HTTP2 fingerprint rather than just its headers. A single-page test came back clean (real HTML, no 403).
- **Status: still not fully working as of the last attempt.** A full 30-team run with the `curl_cffi` fix got through only 1 team before a 403, worse than the original 8-team run. Suspected cause: repeated debugging attempts within the same day likely compounded/extended an IP-level block or reputation flag, rather than the fix itself being wrong. Confirmed elsewhere in this project (MLB's ratings scraper hit the same pattern — see below) that `curl_cffi` genuinely does work on this class of block when given a real cooldown first.
- **Next steps, not yet done:** stop testing entirely for several hours / overnight before trying again — every attempt during an active block, including failed ones, likely extends it. Diagnostic logging on 403s (server/retry-after/cf-ray headers) already added. 403-specific retry count already reduced to 2.
- Don't consider this fixed until a full 30-team run completes clean after a genuine cooldown period.
- **Re-tested this session (after widening per-team pacing to 8-15s, matching NHL/MLB's fix)**: still blocked, still fast — 1/30 teams (ATL) succeeded, blocked starting team 2 (BKN), same "blocked on the 2nd request" shape as before. Confirms pacing alone doesn't touch this block, consistent with it being TLS-fingerprint-class, not volume-based. Not retried same-day.
- **Real bug found last session, fixed this session**: `fetch_with_retry()` used to exhaust its blocked-retry budget, log, and fall through without raising or returning a response, so the caller's `BeautifulSoup(html, ...)` call crashed with `TypeError: Incoming markup is of an invalid type: None`. Now raises the last exception on exhaustion, same as Madden's version.
- **Rebuilt as retry+fallback+daily-trickle this session, mirroring `nfl/scripts/scrape_madden.py`'s actual pattern**: per-team fetch retries (now raising cleanly, see bug fix above), one same-run cooldown retry for whatever's still failed, then fall back to that team's existing rows already in `nba_ratings_2k.json` rather than writing empty. Layered under a persisted rolling-pool state file (`nba/data/ratings_2k_scrape_state.json`) sampling only 3 random teams per run, upserted immediately. Explicitly local-only (not in `scrape.yml`'s `scrape-nba` job), with a `.bat` (`schedule_2kratings_scrape.bat`) adding a random 0-30min delay and a suggested-not-registered `schtasks` command in the script's tail comment.
- **First real trickle-mode test, run this session — genuine partial success**: picked `['MIL', 'CHA', 'DET']`. MIL and DET scraped clean (17 rows each); CHA blocked on both the initial pass and the cooldown retry (8 total 403s), fell back to its existing 18 rows from a prior run rather than going empty. Merged file: **518 records across all 30 teams, 509/518 matched (98.3%)**. Real, if minor, data-quality flag surfaced along the way (not investigated further, same "flag don't chase" treatment as the NHL Bobrovsky-on-Toronto anomaly): MIL's fresh pull includes Tyler Herro, a real Miami Heat player — likely the fan site's own team-assignment lag, not a scraper/matching bug, since the record matched correctly to the right `player_id` regardless of which team page it was listed under.
- **Confirmed next session: that first cycle run was a manual test invocation, not a scheduled one.** `schtasks /query` for this machine showed zero FieldView-related tasks registered at all before this session — the schtasks command documented in the script's tail comment had only ever been written for review, never actually run. Also surfaced a real schema gap while trying to verify MIL/DET's freshness independently: `nba_ratings_2k.json` records carried no timestamp at all, so "were these two actually fresh" could only be answered from a console log already scrolled away, not from the file itself. Fixed by adding `loaded_at` to the record schema (fresh records get one at scrape time; stale-carryover records keep their original).
- **`FieldView NBA 2K Ratings Scrape` now genuinely registered** in Windows Task Scheduler (daily, 09:15, via `schedule_2kratings_scrape.bat`) — confirmed via `schtasks /query /v` showing `Status: Ready` and a real `Next Run Time`, not just the command being printed. Real caveat, not yet addressed: `Logon Mode: Interactive only` — this task will not fire if the machine is locked or logged out at its scheduled time, only if an interactive session is active. Worth revisiting (`schtasks /change /RU ... /RP ...` or recreating with "run whether user is logged on or not") if it turns out to matter in practice.

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
- **Index page background:** per-sport texture, generated at runtime as inline SVG data URIs — real yard-line ticks for NFL, vertical wood-grain planks + a faint free-throw-key/circle accent for NBA, a rotated dirt-tan infield diamond + home plate dot + mow-line stripes for MLB (`nflTexture()`/`nbaTexture()`/`mlbTexture()`/`placeholderTexture()`/`applyFieldBackground(sport)`). `SPORTS` config's old `background: {stripeA, stripeB}` fields were removed as dead weight — nothing reads them anymore.

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

## MLB (DiamondView) — first pass shipped

### Data sources, verified before building anything
- **Roster + bio**: `statsapi.mlb.com` (MLB's own public API, no key required). Verified real via the actively-maintained `MLB-StatsAPI` Python wrapper (841 stars, commits into 2025) before writing anything against it — endpoint definitions confirmed from its actual source, not docs summaries.
  - `GET /v1/teams` — team list, real `abbreviation` field
  - `GET /v1/teams/{teamId}/roster?rosterType=active` — roster, jersey number, position code/abbreviation/name, status
  - `GET /v1/people?personIds=...` (bulk) — height, weight, birth date, `batSide`/`pitchHand` codes, primary position
- **Stats**: same `statsapi.mlb.com`, `GET /v1/stats?stats=season&group=hitting|pitching&sportIds=1&season=YYYY&limit=2000&playerPool=all`. **`playerPool=all` is load-bearing** — without it, the endpoint silently returns only "qualified" players (142 hitters / 55 pitchers in a real test), not the full league. With it: 702 hitters, 799 pitchers, in 2 calls total instead of ~780 individual per-player hydrate calls (the only pattern the wrapper library's own source code proved out).
- **pybaseball**: confirmed active on GitHub (commits into 2026) but PyPI release is stale (2.2.7, Sept 2023 — install from git if ever used). Not used as primary source: pybaseball has no bulk roster/bio function (no `commonteamroster` equivalent), so `statsapi.mlb.com` covers both roster+bio and stats in one source, closer to nba_api's dual role than pybaseball's stats-only role.
- **Ratings**: `theshowratings.com`. Confirmed base/live ratings only — no Diamond Dynasty content anywhere in a full 325-link nav dump, exactly what was wanted. Official `theshow.com/roster_updates` page intentionally not scraped (first-party licensed data, higher legal exposure than a fan site). OOTP ruled out entirely — extracting ratings from a paid game's files for redistribution in a public repo was judged too legally exposed, dropped as a source before any code was written.

### Real column names confirmed (don't assume, these came from live `DESCRIBE` output)
- Hitting (41 cols): `avg, obp, slg, ops, babip, stolenBasePercentage` are VARCHAR; `homeRuns, rbi, hits, runs, strikeOuts, stolenBases`, etc. are BIGINT. `plateAppearances` is the real PA field name.
- Pitching (69 cols): `era, whip, inningsPitched, strikeoutsPer9Inn, walksPer9Inn, winPercentage` are VARCHAR; `wins, losses, saves, strikeOuts, battersFaced`, etc. are BIGINT.
- Both stats tables' own `team` object lacks an `abbreviation` field (unlike the roster endpoint's) — resolved via join to `statsapi_teams.abbreviation` on `team_id` where needed, though the final master JSON sources `team`/`team_abbr` from the roster join instead, since roster reflects today's team and a mid-season-traded player's stats-table team could be stale.

### Position taxonomy — clean, no EDGE/DI-style collapse
Real distribution from `statsapi_roster` (782 rows): `P 390, C 63, CF 48, 2B 48, RF 45, LF 44, SS 42, 3B 41, 1B 38, DH 21`, plus two real singleton edge cases:
- `TWP` (1 player, Ohtani) — MLB Stats API's actual official two-way-player tag. `player_type: "two_way"`, `position_group: null` (doesn't force a fielding slot).
- `OF` (1 player, Cristian Pache) — generic outfield tag, not LF/CF/RF specific. `position_group` stays `"OF"` (the clean group value, so OF-zone substitution gating works normally for him) with `position_group_source: "defaulted"` flagging that his specific field zone wasn't in the source data — DiamondView defaults his on-field zone display to CF specifically. (An earlier version of this pipeline wrote `position_group` itself as the literal string `"CF"`, which would have broken his OF-zone substitution eligibility; caught and fixed — see `mlb/scripts/` pipeline below.)

`position_group` mapping used throughout: IF = `1B/2B/3B/SS`, OF = `LF/CF/RF` (defaulted-OF included), standalone = `C/P/DH`.

### mlb/scripts/ pipeline
- `scrape_roster.py` — all 30 teams, 780 roster rows / 780 people rows (exact parity). Retry/backoff wrapper originally local, extracted to `mlb/scripts/statsapi_utils.py`'s `fetch_with_retry()` once `scrape_stats.py` needed it too — same pattern as `season_utils.py`/`name_utils.py`.
- `scrape_stats.py` — bulk `playerPool=all` pull, 702 hitting / 799 pitching rows.
- `build_mlb_match.py` — joins `statsapi_roster` + `statsapi_people` (bio) + left-joins hitting/pitching stats on `person_id`. Roster is the base population (not the full roster∪stats union, which is 1,382 distinct players — most of the extra ~600 are players no longer on any current roster). Derives `position_group` (with the Pache/TWP handling above) and `player_type` (`batter`/`pitcher`/`two_way`, keyed off `position_abbreviation`). One real bug found and fixed here mid-project: Pache's `position_group` was originally written as the literal string `'CF'` instead of the group `'OF'`, silently breaking his OF-zone substitution eligibility — caught, fixed, pipeline re-run, verified.
- `export_mlb_master.py <output_path>` — writes `mlb/data/mlb_players_master.json`. 782 players. Fields: `player_id, name, team, team_abbr, position, position_group, position_group_source, player_type, jersey_number, height, weight, bats, throws, batting_stats, pitching_stats, match_source`. Match rate: 779/782 = 99.6% have a stats match (either group), better than NFL's or NBA's first-pass match rates.
- `scrape_ratings.py` — written, not yet run to completion. Reuses the `curl_cffi` Chrome-120 session confirmed working against `theshowratings.com` (see below). **Real discovery**: the player photo `data-src` on each team page embeds the actual MLB Advanced Media `person_id` (e.g. `ketel-marte-606466-80x80.png` → `606466`, confirmed by direct match against `statsapi_roster`) — meaning ratings can join on a plain numeric ID with zero fuzzy name matching once unblocked. Currently Cloudflare-blocked (0/30 teams on the last attempt, same IP-cooldown pattern as 2K ratings) — script is correct and ready, just waiting on a genuine multi-hour/overnight cooldown before the next attempt. **Do not retry same-day.**

### theshowratings.com Scraper — RESOLVED via ScraperAPI proxy (Part 3)
- Plain `requests` gets a real Cloudflare 403 block page (not a JS-shell — 75KB of styled HTML, `Server: cloudflare`, real `cf-ray` header).
- `curl_cffi` with `impersonate="chrome120"` confirmed working on a single clean test (200 OK, real content, 30 team links + Top 100 list found, static server-rendered HTML — no headless browser needed for parsing once past the TLS check).
- Team page structure: `table.table-striped`, columns `#, Player, OVR, POT` (POT is a letter grade, not numeric — handle separately from OVR). 50 rows per team (full org depth, not just active 26-man). `Player` cell is nested markup (photo `data-src` with the ID, name in an `<a>`, jersey/team/position/handedness in a `<span class="entry-subtext-font">`) — parse by real element, not by mashed-together `.text`.
- Got Cloudflare-blocked again mid-session on a full run attempt, even from a previously-working URL path, confirming an IP-level cooldown rather than anything path-specific. Standing rule going forward: one clean test only, then stop for hours/overnight if blocked — repeated attempts during an active block compound it (same lesson already learned from 2K ratings).
- **Blocked a third consecutive session, immediately again**: 0/30 teams, 403 on team 1 (`arizona-diamondbacks`), same shape as the prior two attempts — no longer "worked once then degraded," it's now failing on the very first request every time.
- **Real, non-obvious finding this session: a genuine headless-Chromium (Playwright) session gets the identical 403, not just curl_cffi.** Built a one-page prototype (`mlb/scripts/probe_show_ratings_playwright.py`, kept in the repo; its throwaway JSON output was not) that launched real Chromium, navigated to the same Arizona team page, and logged every network response. Result: `status=403`, page title `'403 - Forbidden'`, body text exactly `"403 - Forbidden\n\nAccess to this page is forbidden."` — byte-identical block page to curl_cffi's, not a JS interactive challenge (no "Checking your browser"/"Just a moment" content, confirmed absent). Only 4 network responses total (the blocked main doc + 3 unrelated Google Fonts assets already cached from elsewhere on the page shell) — no XHR/fetch JSON endpoint ever fired, because the page never got past the 403 to run its own scripts. **This is real evidence the block is not TLS-fingerprint-specific** (a real, unspoofed Chromium TLS handshake got the same 403 curl_cffi's impersonated one did) — it points at IP-reputation or session-level blocking instead. Not yet investigated further (residential proxy, different network, or a real multi-day cooldown are the remaining untried options) — flagged here rather than guessed at.
- **Proxy rebuild (Part 3) — real, working fix, confirmed this session.** `SCRAPERAPI_KEY` (read from the environment, never hardcoded/committed) routes requests through `http://api.scraperapi.com?api_key={key}&url={target}` instead of curl_cffi direct. Single-page test cleared first — real 183KB page (vs. the ~52-byte block page), not another 403 — before spending a full run on it. **Full 30-team run then completed clean: 1346 rows, 30/30 teams fresh** (Washington Nationals needed one same-run cooldown retry, same Part 1 retry+fallback pattern as the NHL/NBA rebuilds). First time this site has ever been fully collected in this project.
- **Real bug found and fixed along the way, dormant since this script was first written**: `parse_team_page()` read the photo/name from `tds[0]` and OVR/POT from `tds[1]`/`tds[2]` — but `tds[0]` is actually the row-counter cell (`"1."`), and the real cells are `tds[1]`/`tds[2]`/`tds[3]`. This never surfaced before because every prior run got Cloudflare-blocked before reaching real content to parse against — the proxy is what finally exposed it. Confirmed against real markup via a one-off saved response before fixing (not guessed).
- **747/1346 rows (55.5%) join to `statsapi_roster.person_id` directly** — expected, not a match-rate problem: theshowratings.com's team pages pull the full org depth (~40-51 rows per team, confirmed live: Detroit highest at 51, Cleveland lowest at 40), not just the 26-man active roster `statsapi_roster` tracks. The mlbam_id join itself is confirmed solid on real players (Ketel Marte 606466, Corbin Carroll 682998, Geraldo Perdomo 672695 all matched correctly).
- **Joined into `mlb_players_master.json` this session**: `build_mlb_match.py` left-joins `show_ratings` onto the roster population by `person_id` (deduped defensively by most-recent `loaded_at` — zero duplicates in the current pull, but the dedup runs unconditionally rather than only once a duplicate is actually observed). Real result: **745/782 roster players (95.3%) carry a rating** — a different, higher number than the 747/1346 (55.5%) reported last round, since that measured from the ratings-rows side (mostly non-roster org depth), not from the roster's own perspective. Unmatched players get `overall_rating`/`potential` = null, never dropped/defaulted.

### MLB Team Logos (diamond-view.html, player-table.html)
- ESPN's MLB CDN (`a.espncdn.com/i/teamlogos/mlb/500/{code}.png`) — same pattern as NBA, verified live rather than assumed. Two real exceptions found: Arizona is `ari` (not `az`), Chicago White Sox is `chw` (not `cws`) — same class of exception as NBA's `no`/`utah`. Athletics' `ath` and legacy `oak` codes are byte-identical images, either works. All 30 codes verified returning 200 before wiring in.

### DiamondView Frontend (mlb/diamond-view.html)
- Mirrors `court-view.html`'s real patterns rather than reinventing: `DIAMOND_ZONES` (percentage-offset positioning, analog to `COURT_ZONES`), `ZONE_ORDER`, `ESPN_TEAM_CODES`/`teamLogoUrl()`, `getStarter()`/`substitutePlayer()`, `attachPopupHandlers()`'s per-node hover pattern, two-column `.left-col`/`.right-col` layout.
- 9 fielding zones (P/C/1B/2B/3B/SS/LF/CF/RF) — **held up correctly on the first real render**, no retuning needed (unlike NBA's `COURT_ZONES`, which needed a real correction once rendered at size). DH is not a field zone by design — bats but fields no position, appears in the batting-order sidebar only.
- **Substitution gated by `position_group`**: IF-for-IF, OF-for-OF (using the position_group values resolved in the data layer — Pache's stays the clean `"OF"` group value, so he participates in OF-zone subbing like any other outfielder), C/P/DH standalone (no cross-group subbing). Mirrors `substitutePlayer()`'s explicit-target-zone approach.
- **Batting order** — no real daily-lineup source exists (would need a separate scraper, out of scope for now), so it's derived: batters ranked by plate appearances descending, pitchers split into starters (`gamesStarted > 0`) vs. bullpen. Validated against two real teams (NYY, LAD) — order and starter/bullpen split matched real rotations. Same "derived, not sourced" category as NBA's MPG-based `rotation_status` before real depth-chart data existed.
- **Ohtani (`TWP`) P-zone fix**: originally excluded from the P-zone substitution pool entirely (gated on exact `position === 'P'`, and his position is `'TWP'`) despite a real ERA. Fixed by additionally allowing `player_type === 'two_way'`, scoped to the P-zone pool only — verified he now appears and can be placed there, and verified C/SS zone pools are unaffected (no two_way leak into standalone or other group pools).
- **Real bug found and fixed during this build (data-layer symptom, not a design flaw)**: `statsapi.mlb.com` gives every rostered player, including pure pitchers, a present `batting_stats` block — all zeros, since it's a blanket per-roster-player hitting line rather than omitted for non-hitters. Was leaking 3 zero-stat pitchers into each team's batting order. Fixed with a `pa > 0` gate, and the hover-popup's batter/pitcher branching was rebased on `player_type` instead of "does a stats object exist," since the latter is unreliable given this quirk.

### PlayerTable (mlb/player-table.html)
- Mirrors `nfl/depth-chart.html`'s `VIEWS`/`STAT_COLS` position-dependent-columns pattern, **not** `nba/player-table.html`'s flat single-column-set approach — MLB's batting/pitching stats are as disjoint as NFL's passing/rushing/receiving/defense split, unlike NBA's uniform PPG/RPG/APG block.
- **Deliberate simplification from NFL's pattern**: used real named columns per tab instead of NFL's generic `stat1`–`stat5` slot mechanism. NFL's genericity earns its complexity by reusing one column-rendering path across 4 different views; MLB only has 2 stat-bearing tabs (Batting, Pitching) that never share columns, so the abstraction wouldn't pay for itself — direct application of the project's own "no abstraction for single-use code" rule.
- 3 tabs: Overview / Batting / Pitching. Real field names confirmed against live records before wiring: `pa→plateAppearances, hr→homeRuns, rbi, avg, obp, slg, ops` (batting); `w→wins, l→losses, era, whip, so→strikeOuts, ip→inningsPitched` (pitching).
- **Sort fix, tested both ways, not just implemented**: `avg/obp/slg/ops/era/whip` (and proactively `ip`, same VARCHAR shape) need `parseFloat()`, not string comparison. AVG/OBP/SLG/OPS showed no visible difference in practice (values are consistently `.XXX`/`1.XXX` shaped, so ASCII ordering happens to coincide with numeric ordering here) — but ERA and IP showed real, serious divergence: naive string-sort ranked ERAs of 10.13/10.50/11.57/19.29 directly ahead of legitimate 2.00–2.08 arms, and IP's naive "top 10" was topped by a 9.0-inning reliever ahead of every 140+ inning starter. `ip` added to the float-sort set even though it wasn't in the original ask, based on recognizing the same underlying VARCHAR-decimal shape.
- **Null handling deliberately diverges from NFL's**: NFL treats `0` as null for sort-last purposes; MLB does not — a real `0 HR` or `0 SO` is meaningful data, not missing data. Only true `null`/`''` sorts last here.
- Reuses `diamond-view.html`'s already-corrected `ESPN_TEAM_CODES` map verbatim (ari/chw fixes included) rather than rediscovering it.

### MLB Index Page Texture
- `mlbTexture()` in `index.html`: rotated infield-diamond shape with dirt-tan fill (`#c9995f`, `fill-opacity: 0.05`), home-plate dot, faint mow-line stripes across the field. Enlarged from an initial pass (viewBox 700→900, diamond rect 300×300→500×500) and given real fill instead of an empty outline, per direct feedback that the first version was too small/bland. `stroke-linejoin="round"` applied proactively, reusing the same miter-join-artifact fix already found and applied to `diamond-view.html`'s own infield dirt shape — same shape, same bug, fixed once it was recognized rather than waiting for it to resurface a second time.

---

## NHL (IceView) — kickoff, in progress

### Data sources, verified before building anything
- **Package**: `nhl-api-py` (PyPI, own summary says "Updated for 2025/2026"). GitHub `coreyjs/nhl-api-py`, not archived, active commits into May 2026, 146 stars — confirmed real and current before designing anything, same discipline as MLB's kickoff.
- **Two API bases confirmed from the wrapper's real source**: `api-web.nhle.com/v1/` (modern web API — roster, standings, player landing pages) and `api.nhle.com/stats/rest/` (dedicated stats REST API, uses a `cayenneExp` filter-expression query language unique to this API).
- **Roster**: `GET /v1/roster/{team_abbr}/{season}` — returns players grouped into `forwards`/`defensemen`/`goalies`, **not** a flat list. This confirms the project's original NBA-analog hypothesis for real, not just structurally guessed. Real fields per the library's docstrings: `id, firstName.default, lastName.default, sweaterNumber, positionCode, birthDate, birthCountry`.
- **Bulk stats**: `skater_stats_summary()` → `GET .../en/skater/summary` with a `cayenneExp` filter (e.g. `gameTypeId=2 and seasonId<=20252026 and seasonId>=20252026`), league-wide but **not** in one call — see the Gotcha below. Goalies get a separate `goalie_stats_summary()` / `en/goalie/{type}` — same batting/pitching-style split logic as MLB, since save percentage/GAA aren't skater stats.
- **Gotcha, a different shape than MLB's**: confirmed live that both stats endpoints hard-cap each response at **100 rows server-side regardless of the `limit` value passed** (tried up to 100000, still 100 back) — this isn't a settable default like NFL/MLB's `limit=50`, it's a real page-size ceiling. Full coverage requires paging with `start` in increments of 100 until an empty page comes back. Confirmed real: 940 skaters / 98 goalies league-wide for the 2025-26 season this way.
- **Season format is `YYYYYYYY`** (e.g. `"20252026"`) — different from MLB's plain year and NBA's `"YYYY-YY"`. `nhl/scripts/season_utils.py`'s `resolve_seasons()` is built and confirmed live: it calls `standings.season_standing_manifest()` (real per-season end dates) and picks the most recently completed season, rather than guessing an Oct/April cutoff. **Real, non-obvious finding**: roster and stats need two *different* season ids during the offseason — confirmed live on 2026-08-18 (~6 weeks before 2026-27 puck drop) that TOR's roster under the prior season id (`20252026`) returns a stale 18 players (departed UFAs still listed, incoming signees not yet added), while the upcoming season id (`20262027`) returns the fuller/current 25-player roster. Stats endpoints are the mirror image — the upcoming season id returns zero rows until games are actually played, so stats has to use the prior/completed season id. `resolve_seasons()` returns both (`roster_season`, `stats_season`) so each script uses the right one.

### Ratings sources — nhlratings.net probed, structure confirmed
- **Official**: `ea.com/games/nhl/ratings` — reported populated only starting with NHL 27; currently empty/not useful as a source.
- **Fan-made**: `nhlratings.net` — structure fully confirmed (see below), but **blocked again this session, real run attempted**. Plain `requests.get()` returned clean 200s for the first several requests during the original structure probe, then blocked mid-session — see prior round's notes. This session: swapped `scrape_ratings.py` to `curl_cffi` (Chrome-120 impersonation) on top of its already-set 8-15s per-team pacing, and ran it for real. Result: **1/32 teams (ANA, 37 rows) succeeded, blocked starting team 2 (Boston)** — real Cloudflare 403 (`cf-ray: a2e0a8a1a97af60f-ORD`, `cf-cache-status: BYPASS`, freshly computed). Not retried same-day; the partial 1-team `nhl_ratings` table was discarded, not committed (see "ship only complete runs" note below). 34/37 of ANA's scraped rows matched to `nhl_roster` by name (91.9%) before the DB write was reverted — matching pipeline itself works fine, the block is what's stopping this. Structure confirmed before any block hit: 32 per-team pages (`/teams/{team-slug}`), each with a main roster table (TOR: 29 rows) plus a small second table for IR/non-roster players (TOR: 1 row), plus separate `/lists/{position}` pages (centers, defensemen, goalies, etc.) and individual player pages at a bare name-slug URL (`/william-nylander`, no numeric ID in the URL itself).
- **No clean join key here, unlike MLB — confirmed, not assumed**: player photo URLs do embed a numeric ID (`{name-slug}-{NUMBER}-80x80.png`), which looked promising, but checking it against 2 real players proved it's a different ID space entirely from the NHL API's `playerId`: William Nylander is site-ID `3114736` vs. NHL API `8477939`; Auston Matthews is site-ID `4024123` vs. NHL API `8479318`. Digit counts aren't even consistent across players (some as short as `5160`), which points to this being the site's own internal WordPress post ID, not a stable external player ID. `nhl/scripts/scrape_ratings.py` matches by name+team instead (`nhl/scripts/name_utils.py`, ported from NBA's), same approach as NBA's 2kratings.com/Spotrac — this is not a repeat of MLB's clean-ID win.
- **Caveat found, not chased down**: TOR's team page lists Sergei Bobrovsky (real-life Florida's goalie) as a Maple Leaf. Likely means this "NHL 27" ratings data has its own update/roster cadence that can lag or diverge from live NHL transactions — same class of staleness risk as NBA 2K ratings, worth a sanity check against `nhl_roster` once a real scraper/matcher exists, not investigated further this round.
- **theshowratings.com re-tested this session, confirmed blocked again**: one clean, controlled full-run attempt of `mlb/scripts/scrape_ratings.py` (its existing `curl_cffi` Chrome-120 session, unchanged) got a real 403 on the very first team (`arizona-diamondbacks`), 0/30 teams completed. A plain `requests.get()` to the bare homepage earlier the same session *had* returned a clean 200 (cached, `cf-cache-status: HIT`) — but that's a cached static page, not evidence the deeper team pages are unblocked. **Status unchanged from before: still blocked, not resolved, not retried same-day.** Left in Known Outstanding Bugs.
- **All three ratings scripts' per-team delay now at 8-15s** (`nhl/scripts/scrape_ratings.py` from 1.5s, `mlb/scripts/scrape_ratings.py` from 2.5s, both prior round; `nba/scripts/scrape_2kratings.py` from ~1-1.5s, added this round after it was missed the first time) — none run more than roughly weekly and ratings barely move day to day, so there's no reason to hurry. Documented in each script's comments as *not* expected to fix a TLS-fingerprint block by itself but as insurance against a separate, request-volume-triggered cooldown.
- **All three sites re-attempted for real this round (one clean try each, stopped at first block, no retries), all three still blocked**: `nhlratings.net` 1/32 teams before block (see above); `2kratings.com` 1/30 teams (ATL) before block on team 2, then the script crashed on a pre-existing bug (see 2K Ratings Scraper section — `fetch_with_retry` doesn't raise/return cleanly once its blocked-retry budget is exhausted); `theshowratings.com` 0/30, blocked immediately on team 1 for the third session in a row, and a Playwright headless-Chromium prototype got the identical 403 (see theshowratings.com section) — real evidence this one specific block isn't TLS-fingerprint-based. No site produced a complete run, so no ratings data was committed this round; only the pacing/curl_cffi script changes and the Playwright prototype were.
- **Rebuilt as retry+fallback+daily-trickle this round, mirroring `nfl/scripts/scrape_madden.py`'s actual pattern (not reinvented)**: per-team fetch retries, then one same-run cooldown retry for whatever's still failed, then fall back to that team's existing rows already in the ratings table/JSON rather than writing empty and erasing known-good data. Layered under a persisted rolling-pool state file (`nhl/data/ratings_scrape_state.json`) that samples only 3 random teams per run and upserts them immediately — a deliberately much gentler footprint than a 32-team sweep, meant to survive this exact class of volume-triggered block. Explicitly local-only (not in `scrape.yml`), with a `.bat` (`schedule_ratings_scrape.bat`) adding a random 0-30min delay and a suggested-not-registered `schtasks` command in each script's tail comment.
- **First real trickle-mode test, run this session**: picked `['PHI', 'CHI', 'WPG']` — all 3 blocked on both the initial pass and the cooldown retry (12 total 403s, same `cf-cache-status: BYPASS` signature as the full-run block above). No existing data for any of the three to fall back to, so `nhl_ratings` was correctly left untouched rather than written empty — the merge logic held up under a total-failure case. Pool advanced to 29 remaining regardless (by design — a permanently-blocked team shouldn't get retried forever ahead of its rotation). Not retried further this session.
- **Confirmed next session: `nhl_ratings` genuinely does not exist** (checked live via `information_schema.tables`, not assumed from the state file) — consistent with the total-failure outcome above, not a bug. That first cycle run was a manual test invocation, not a scheduled one -- `schtasks /query` showed zero FieldView-related tasks registered on this machine at all beforehand.
- **`FieldView NHL Ratings Scrape` now genuinely registered** in Windows Task Scheduler (daily, 09:00, via `schedule_ratings_scrape.bat`) — confirmed via `schtasks /query /v` showing `Status: Ready` and a real `Next Run Time`, not just the command being printed. Same `Logon Mode: Interactive only` caveat as the NBA task below — won't fire while the machine is locked/logged out.

### Status
- **`nhl_roster`**: **811 rows, all 32 teams** (scaled up this session — `TEST_ABBR` gate removed, team list now comes from a live `teams.teams()` call). By `position_group`: 468 forwards, 260 defensemen, 83 goalies. Per-team counts ranged 20–39 (ANA highest at 39 — offseason roster-building is uneven across teams by design, not a bug). `sweater_number` missing on 42/811 rows (5.2% — rare, not common; these are incoming signees not yet assigned a number, matches the single-team pattern seen last session). Season resolved to `20262027`. Real columns unchanged from last session: `row_id, team_abbr, season, position_group, player_id, first_name, last_name, sweater_number, position_code, shoots_catches, height_in_inches, weight_in_pounds, birth_date, birth_city, birth_country, birth_state_province, loaded_at`.
- **`nhl_stats_skaters`**: 940 rows, league-wide, season `20252026`. Real columns: `assists, evGoals, evPoints, faceoffWinPct, gameWinningGoals, gamesPlayed, goals, lastName, otGoals, penaltyMinutes, playerId, plusMinus, points, pointsPerGame, positionCode, ppGoals, ppPoints, seasonId, shGoals, shPoints, shootingPct, shootsCatches, shots, skaterFullName, teamAbbrevs, timeOnIcePerGame, row_id, loaded_at`.
- **`nhl_stats_goalies`**: 98 rows, league-wide, season `20252026`. Real columns: `assists, gamesPlayed, gamesStarted, goalieFullName, goals, goalsAgainst, goalsAgainstAverage, lastName, losses, otLosses, penaltyMinutes, playerId, points, savePct, saves, seasonId, shootsCatches, shotsAgainst, shutouts, teamAbbrevs, ties, timeOnIce, wins, row_id, loaded_at`.
- **Coverage/limit finding — a different fix than NFL/MLB's**: both stats endpoints hard-cap at 100 rows per response no matter what `limit` value is passed (tested up to 100000). `scrape_stats.py` achieves full coverage via real pagination (`fetch_all_pages()`, `start` incrementing by 100 until an empty page returns), not a bigger limit value.
- **Season resolution — two different, both-correct answers, confirmed live on 2026-08-18**: `season_utils.py`'s `resolve_seasons()` returns `("20262027", "20252026")` as `(roster_season, stats_season)`. Roster uses the *upcoming* season id because during the NHL offseason it's the fuller/more current roster. Stats uses the *prior/completed* season id because the upcoming season id returns zero stat rows until games are actually played. Both scripts already pull the correct season for their own endpoint.
- **ID space confirmed shared between roster and stats, verified by name not just by type**: `nhl_roster.player_id` and `nhl_stats_skaters.playerId` are the same NHL API id space — checked 5 real players joined on that id (Brent Burns, Corey Perry, Alex Ovechkin, Evgeni Malkin, Sidney Crosby) and all 5 names matched the same person on both sides. Same clean join key `build_nhl_match.py` can rely on directly, no fuzzy matching needed for this pairing.
- **Roster-vs-stats team disagreement is expected here too, and unusually large — same MLB lesson, bigger number**: of 703 skaters joined on `player_id`/`playerId`, 164 (23.3%) show a different team between `nhl_roster.team_abbr` and `nhl_stats_skaters.teamAbbrevs`. Broken down for real: 50 are multi-team aggregate stat rows (e.g. `teamAbbrevs: "STL,NJD"`) where the roster team *is* one of the listed teams — an in-season trade correctly tracked, not a disagreement. The other 114 have zero overlap at all — genuine team changes between the stats season (2025-26, frozen) and the roster season (2026-27, live offseason movement), expected given the two tables are deliberately pulled from different seasons (see season-resolution finding above). **`nhl_roster` should be trusted as the source of truth for "current team," never `teamAbbrevs`** — identical conclusion to MLB's roster-vs-season-stats gap, just a much bigger fraction here (23% vs. MLB's smaller gap) because NHL's roster/stats seasons are a full cycle apart by design, not just a same-season snapshot-timing gap.
- **`build_nhl_match.py`/`export_nhl_master.py` built and run**: `nhl_players_master.json` written, **811 players**, matched to skater/goalie stats **779/811 (96.1%)** — better than NFL's/NBA's first-pass rates, close to MLB's 99.6%. The 32/811 unmatched are `roster_only` (no 20252026 games — expected, mostly offseason signees not on any 2025-26 roster). Shipped without ratings (`nhl_ratings` table doesn't exist yet — `scrape_ratings.py` hasn't completed a run, see Ratings sources above); `build_nhl_match.py` checks for the table's existence and joins it automatically once it does, same "ship without it, backfill later" precedent as MLB's first DiamondView pass. Schema: `player_id, name, team_abbr, position_group, position_code, jersey_number, shoots_catches, height_in_inches, weight_in_pounds, birth_date, birth_city, birth_country, birth_state_province, skater_stats, goalie_stats, stats_source, overall_rating, potential`.
- **Still ahead, not started**: an actual `nhlratings.net` scraper run (script built and ready, blocked pending a real cooldown — see Ratings sources above).

### IceView Frontend (nhl/ice-view.html)
- Mirrors `diamond-view.html`/`court-view.html`'s real patterns rather than reinventing: `ICE_ZONES` (percentage-offset positioning, analog to `DIAMOND_ZONES`/`COURT_ZONES`), `ZONE_ORDER`, `ESPN_TEAM_CODES`/`teamLogoUrl()`, `getStarter()`/`substitutePlayer()`, `attachPopupHandlers()`'s per-node hover pattern, two-column `.left-col`/`.right-col` layout.
- **6 rink zones**: LW, C, RW, D, D, G — two generic `D1`/`D2` slots (internal keys, both display as plain "D"), not L-D/R-D specific. Confirmed live before building: `nhl_roster.position_code` has no L-D/R-D split, just a single `D` value for all 260 defensemen. Rough placeholder positions on the first render, not yet corrected visually (same starting point `COURT_ZONES` had before its real-size retune).
- **Starters**: forward zones (LW/C/RW) ranked by `timeOnIcePerGame` descending within their real `position_code` (L/C/R) — confirmed live these are the only forward position codes in the source data, no separate LW/RW code exists. Either D zone takes any `position_code === 'D'` player, also by TOI. Goalie starter is highest `gamesStarted`, mirroring DiamondView's `P`-zone starter logic.
- **Substitution — positionless within group, same shape as MLB's C/P/DH**: forward pool positionless across LW/C/RW (gated on `position_group === 'forward'`), D pool positionless across both D zones (`position_group === 'defenseman'`), G standalone (exact `position_code === 'G'` match only, no cross-group subbing).
- **Bench & rotation list**: everyone else in one combined list (mirrors CourtView's single bench-by-minutes list, not DiamondView's two-list batting/pitching split), sorted by `timeOnIcePerGame` descending. Goalies carry no `timeOnIcePerGame` (that's a skater-only stat) and sink to the bottom of a TOI-sorted list — accepted as fine for a first pass given a roster usually has one clear backup goalie, not corrected further this round.
- **No 0-99 rating yet** (`nhlratings.net` still blocked, see Ratings sources above) — dot color/display value is driven by rate stats instead, same spirit as DiamondView's AVG/ERA-driven `battingColor`/`pitchingColor` before a single overall rating existed: `skaterColor()`/dot text uses `pointsPerGame`/`points`, `goalieColor()`/dot text uses `savePct` (displayed banker's-style as `.906`, the real hockey broadcast convention, same trick as batting average's leading-zero strip).
- **Two derived display helpers, confirmed against real data before writing them**: `formatToi(seconds)` — `timeOnIcePerGame` comes back in seconds, not minutes or a formatted string (confirmed live: McDavid's `1379.13` == 22:59) — and `formatHeight(inches)` — `height_in_inches` is a raw integer (unlike MLB's pre-formatted `"6' 2\""` string from statsapi.mlb.com), converted to `5'11"` style for the popup bio line.
- **ESPN team-logo codes verified live, not assumed**: all 32 return real 200s. Three exceptions found, same class as NBA's `no`/`utah` and MLB's `ari`/`chw`: Los Angeles is `la` (not `lak`), San Jose is `sj` (not `sjs`), Tampa Bay is `tb` (not `tbl`). New Jersey stayed the full `njd` — checked directly rather than assumed from the other three-letter-to-two-letter pattern, since it would have been wrong to extrapolate.

### PlayerTable (nhl/player-table.html)
- Mirrors `mlb/player-table.html`'s real-named-columns-per-tab pattern, **not** `nba/player-table.html`'s flat single-column-set approach — NHL's skater/goalie stats are as disjoint as MLB's batting/pitching (a defenseman's `+/-` and a goalie's `GAA` share no columns), unlike NBA's uniform PPG/RPG/APG block.
- 3 tabs: Overview / Skaters / Goalies. Skaters tab includes both forwards and defensemen (gated on `position_group !== 'goalie'`), not just forwards.
- **Confirmed no MLB-style VARCHAR problem before assuming it away**: spot-checked `nhl_players_master.json` directly — `faceoffWinPct`, `pointsPerGame`, `shootingPct`, `timeOnIcePerGame`, `goalsAgainstAverage` (`3.06601`), `savePct` (`0.88319`) all came back as real JSON numbers, not formatted strings like statsapi.mlb.com's rate stats. `toSortVal()` needs no `FLOAT_SORT_COLS`-style `parseFloat` coercion set here — plain `<`/`>` comparison already sorts correctly.
- **Null handling matches MLB's convention, not NFL's**: a real `0` (0 goals, 0 PIM) is meaningful NHL data, not missing data. Only true `null`/`''` sorts last.
- Reuses `ice-view.html`'s already-verified `ESPN_TEAM_CODES` map verbatim (la/sj/tb exceptions included) rather than re-deriving it.
- 5 real `position_code` filter values (`C, L, R, D, G`), with `L`/`R` displayed as `LW`/`RW` in the filter checkboxes and mobile card labels — the underlying filter value stays the raw source code, only the label is friendlier.

---

## Conventions & Gotchas
- OurLads abbreviations: `ARZ` (not ARI), `JAX` (not JAC)
- Team JSON can come out as a list or dict — normalize with `if type(team_data) is list: team_data = team_data[0]`
- Minimal targeted edits only — no unrelated refactors, no adjacent "improvements"
- Match existing code style even if you'd write it differently
- No speculative features or config beyond what's asked
- Plain HTML/CSS/JS only — no React, no build tools
- Live Server (VS Code extension by Ritwick Dey) for local dev preview
- **Scraper hardening pattern**: stats.nba.com (IP-blocking cloud runners), 2kratings.com and theshowratings.com (both TLS-fingerprinting plain `requests`) all point at the same lesson — anti-bot protection increasingly operates below the HTTP-header layer (source IP reputation, TLS handshake fingerprint) where header tuning alone can't fix it. Check IP/TLS-layer causes before re-tuning headers a third or fourth time on any new source. **Correction, not fully "fixed" after all**: `curl_cffi` genuinely cleared 2kratings.com and theshowratings.com on isolated single-page tests early on, but repeated full 30-team runs since then have failed on both, and theshowratings.com's block was confirmed this session to also catch a real headless-Chromium (Playwright) session with an unspoofed TLS handshake — meaning at least that block isn't purely TLS-fingerprint-based, so `curl_cffi` alone isn't the complete fix it looked like initially.
- **Silent bulk-endpoint truncation** is 3-for-3, but not always the same fix: NFL/MLB's `/v1/stats` just needs a bigger `limit`/`playerPool=all`; NHL's `/stats/rest` skater/goalie endpoints hard-cap at 100 rows per response regardless of `limit`, requiring real pagination via `start`. Check which kind of cap a new bulk endpoint has, not just whether one exists.

---

## Known Outstanding Bugs
- OL snap-share coverage sits at ~61% (306/504) — real data-source ceiling (import_snap_counts/PFR crosswalk coverage for OL specifically), not considered worth chasing further
- NFL: CB/S has the same position-taxonomy-collapse problem EDGE/DI had (see GSIS Matching Pipeline) — nflreadpy rosters (the GSIS fallback source) tags all defensive backs generically as `DB`, with no `CB`/`S` split at all, so that fallback path structurally can never match a CB/S player. Known, not fixed — same bug class as EDGE/DI, just not yet addressed for this position group.
- NBA: no undo path for a single court substitution short of switching teams away and back — deferred, not forgotten
- NBA: `.subs-name` popover text truncation — see CourtView Frontend Interactions above
- NBA: LeBron James `rating: null` in `nba_players_master.json` — suspected 2kratings.com name-match bug, same class as previously-fixed Surtain/Woolen/Cyrillic-character bugs. Not yet checked against `nba_ratings_2k.json`'s `unmatched` array.
- NBA: `scrape_2kratings.py`'s full 30-team run is still blocked (never completed one in this project). Rebuilt this session as a retry+fallback+daily-trickle scraper (see 2K Ratings Scraper section above) — a real 3-team trickle run this session got 2/3 fresh + 1 stale-carryover, 518/518 records preserved, 98.3% matched. Considered working at the trickle scale, not resolved at the full-run scale (and doesn't need to be, given the new design).
- ~~MLB: `scrape_ratings.py` (theshowratings.com) blocked~~ — **RESOLVED this session** via a ScraperAPI proxy rebuild (Part 3), see theshowratings.com Scraper section above. Full 30-team run completed clean (1346 rows). Remaining follow-up (not a bug): join `show_ratings` into `mlb_players_master.json`, not yet done.
- NHL: `scrape_ratings.py` (nhlratings.net) rebuilt as retry+fallback+daily-trickle this session (see NHL Ratings sources section above). A real 3-team trickle test still got blocked on all 3 (12 total 403s) — the site is still in an active cooldown from the full-run attempts. Merge/fallback logic held up correctly under total failure (left `nhl_ratings` untouched rather than writing empty). Not resolved at the site level; the new trickle design is built and tested, waiting on the site's cooldown to actually lift.

---

## Roadmap

**In Progress**
- ⬜ NHL expansion — `ice-view.html`/`player-table.html` built this round (mirroring DiamondView/CourtView and MLB's player-table patterns respectively), `nhl_players_master.json` built (811 players, 96.1% matched to stats), roster (811 rows, all 32 teams) and league-wide stats (940 skaters, 98 goalies) verified in `nhl/data/fieldview.duckdb`, season-resolution utility (`season_utils.py`) built and confirmed live. Shipped without ratings — `nhlratings.net` scraper is built (`scrape_ratings.py`, name+team fuzzy matching, no clean ID join) but still blocked as of the last trickle-mode test. Unlike MLB's theshowratings.com (resolved this session via a ScraperAPI proxy), nhlratings.net hasn't been tried through a proxy yet — worth considering if the site's own cooldown doesn't lift.
- ⬜ 2K ratings scraper TLS block — `curl_cffi` fix confirmed working in principle (proven out on MLB's ratings site this round), full 30-team NBA run still not confirmed clean after a real cooldown period.
- ~~MLB ratings join~~ — **done this session**, see theshowratings.com Scraper section above. `mlb_players_master.json` now carries `overall_rating`/`potential` for 745/782 roster players (95.3%).
- ⬜ Tactical stat selection — still just ongoing thinking; feeds both CourtView/DiamondView hover/bench cards and TableView columns, so solve once and all sports inherit it.

**Up Next**
- ⬜ Opponent overlay (NFL) — same-team offense+defense on the field simultaneously first, then a real versus view (your team's offense against an actual opponent's defense)
- ⬜ Additional NFL data sources (advanced metrics): PFF grades, RAS scores, combine data, EPA/DVOA — via `nflreadpy` (see PIPELINE notes: `load_ftn_charting()`, `load_nextgen_stats()`, `load_participation()`, `load_combine()` are all already free and unused)
- ⬜ NFL age source swap — switch primary age field from OurLads to Spotrac contract data; Spotrac's contract pages likely carry better OL age/bio coverage than OurLads' depth-chart pages do, worth testing against the current 74.8% GSIS match context once picked up.
- ⬜ TableView stat/view-package refinement — right stat columns and filter presets to actually run an analysis or scan the league quickly, not just look at a roster
- ⬜ Popover `.subs-name` truncation fix — small, same width/font treatment `.bench-name` already got
- ⬜ LeBron James `rating: null` investigation — check `nba_ratings_2k.json`'s `unmatched` array before trusting the position-rank feature's edge cases further
- ⬜ NBA positionless substitution — design drafted, not yet confirmed applied/verified

**Backlog**
- ⬜ MLS/EPL expansion (soccer) — last of the four remaining sports, after NHL. Ratings side is actually the strongest candidate of all four (sofifa.com/EA FC is a large, well-known, scrapable database), but the free stats/roster API landscape is more fragmented than pybaseball/NHL's API/nba_api — pick after NHL proves out the process a third time.
- ⬜ ReView overview — replays, highlights, box scores, tweets, podcasts; comes after FormationView/CourtView/DiamondView/TableView are dialed in, per original sequencing
- ⬜ Mobile responsiveness pass — desktop-only is the explicit call for now
- ⬜ NBA table view column cleanup (same treatment NFL's and MLB's table views already got)

**Wish List**
- ⬜ Player comparison
- ⬜ Historical rating trends

**Dropped**
- ~~NBA Big/Wing/Guard bucket UI~~ — no usable existing data source found after checking `nba_api`'s `commonplayerinfo` coarse position field and Cleaning the Glass's convention. Superseded by positionless substitution instead of built as originally planned.
- ~~OOTP as an MLB ratings source~~ — extracting ratings data from a paid commercial game's local files for redistribution in a public repo judged too legally exposed. Dropped before any code was written, in favor of theshowratings.com (a fan site already redistributing that data, same legal category as 2kratings.com).

**Not in FieldView - called ReView:** League leaderboards, game reviews, highlights, replays, podcasts, tweets — these belong in a separate media/highlights page down the road. Called ReView for being able to review the past day/week of games, highlights, box scores, stats, tweets, drama, reddit posts, podcasts, etc. Just to catch up on the league and all it's action.

---

## NFLDATAPY
nflreadpy — yes, a few of these are genuinely worth grabbing, and one of them actually shortcuts your own roadmap:

load_ftn_charting() — this is the one I'd flag hardest. Your roadmap lists PFF as a future paid data source, but FTN's charted stats (pressure rate, missed tackles, target quality, that kind of PFF-style manual charting) are free and already in nflreadpy. Worth trying before you go looking for a PFF scrape.
load_nextgen_stats() — real tracking-derived metrics (separation, time to throw, closing speed, etc.). This is exactly the kind of "surprising, layered" data that makes a player comparison view actually interesting instead of just a stat table.
load_participation() — personnel groupings and snap-level participation. This one's relevant specifically to formation view and your planned "opponent overlay" — it's literally per-play personnel package data, which is the same shape of information your formation view already visualizes.
load_combine() — combine results, already on your roadmap as a separate source, but it's just sitting here for free too.

load_contracts() also exists here (OTC data) — you already have a working Spotrac/OTC pipeline for that, so I wouldn't switch just to consolidate, but worth knowing it's redundant with what you built rather than a gap.