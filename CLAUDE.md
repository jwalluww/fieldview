# FieldView — Claude Code Context

NFL (and soon multi-sport) intelligence platform.
Live at https://jwwalluww.github.io/fieldview/
Repo: https://github.com/jwwalluww/fieldview (public)

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
- `index.html` — home page, entry cards
- `nfl-formation-view.html` — formation view, player cards on field
- `depth-chart.html` — OOTP-style data table

### Scripts
- `scripts/scrape_depth.py` — OurLads depth chart scraper
- `scripts/merge_madden.py` — merges Madden ratings + position ranks
- `scripts/scrape_otc.py` — Over The Cap contract data
- `scripts/scrape_stats.py` — nflreadpy 2025 season stats
- `scripts/build_master.py` — builds players_master.json with GSIS matching
- `scripts/resolve_names.py` — diagnostic: fuzzy name match review
- `scripts/audit_positions.py` — diagnostic: position mapping review

### Data
- `data/arz.json` ... `data/was.json` — 32 team JSON files (OurLads source)
- `data/madden.json` — Madden ratings source
- `data/players_master.json` — canonical player registry (GSIS-keyed)

---

## Data Pipeline Order
Run locally or via GitHub Actions in this exact order:
1. scrape_depth.py
2. scrape_otc.py
3. scrape_stats.py
4. merge_madden.py
5. build_master.py

`resolve_names.py` and `audit_positions.py` are diagnostic only — run locally when investigating match quality, not part of the pipeline.

No need to delete JSONs before running — scrapers overwrite cleanly. `build_master.py` skips any file with "master" in the name.

**Note:** `build_master.py` not yet added to `scrape.yml`. When ready, add it after merge_madden step and add `pandas rapidfuzz` to the pip install line.

---

## Player JSON Schema (per-team files)
name, depth, injured, attainment, jersey, madden, age, years_pro,
cap_number, stats, stats_season, standard_slot, standard_pos,
madden_rank, madden_rank_total, madden_pos_label

## players_master.json Schema (canonical)
player_id (GSIS if matched, else name-pos-team slug),
gsis_id, match_confidence, canonical_name, ourlads_name,
team, team_name, base_defense, ourlads_pos, standard_slot, standard_pos, depth,
jersey, age, years_pro, madden, madden_rank,  madden_rank_total, madden_pos_label, cap_number, attainment, injured, stats (normalized keys), stats_season, nflreadpy_name, match_source

`standard_pos` values: `QB, WR, RB, TE, OL, EDGE, DI, LB, CB, S`
Special teams (K, P, KR, PR, KO, PK, LS, PT, H) are stripped from pipeline entirely.

---

## Stat Key Normalization
Stats are normalized by position in `build_master.py` via `STAT_MAP`. Canonical keys:
- Passing: `CMP, ATT, PASS_YDS, PASS_TDS, INT, SACK, RUSH_YDS`
- Rushing: `CAR, RUSH_YDS, RUSH_TDS, REC, REC_YDS, TGT, YAC`
- Receiving: `TGT, REC, REC_YDS, REC_TDS, YAC`
- Defense: `TKL, SACK, INT, PBU, TFL, QB_HIT`

Frontend `STAT_COLS` in `depth-chart.html` uses these canonical keys.

---

## GSIS Matching Pipeline
- Primary source: dynastyprocess crosswalk CSV (fantasy-focused, good QB/WR/RB/TE coverage, poor OL/DI coverage)
- Fallback: nflreadpy roster data (attribute name TBD — `import_rosters` is broken)
- OL skipped entirely from GSIS matching (not in fantasy crosswalk)
- Matching logic: strip to bare letters, no spaces/punctuation/suffixes, fuzzy match within position group first, team as tiebreaker only
- Name aliases handled via `NAME_ALIASES` dict in `build_master.py`
- `None` alias value = force no-match (wrong player in crosswalk)

### Team abbreviation map (dynastyprocess → OurLads)
`ARI→ARZ, KCC→KC, LVR→LV, TBB→TB, SFO→SF, GNB→GB, NOR→NO, NWE→NE`

### Current match results
- 2770 total players, 1370 GSIS matched (~50%)
- Most unmatched are OL + defensive depth (expected, no stats anyway)
- Skill position (QB/WR/RB/TE) unmatched count not yet measured — next diagnostic step

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

### Known formation bug
Colts, Seahawks, and other hybrid-scheme teams missing a defender in formation view. OurLads lists their positions differently and `standard_slot` mapping doesn't cover all cases. Needs investigation of raw JSON vs POS_ALIAS mapping.

---

## Depth Chart Table
- Loads all 32 teams at once from individual team JSONs (will switch to `players_master.json`)
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
- `Jr./Sr.` double-period in name normalization (`Paris Johnson Jr..`)
- Missing aliases: `Riq Woolen, Dru Phillips, Cobie Durant, Vj Payne`
- Force no-match needed for bad crosswalk hits: `Matt Hibner, Mike Jackson, Joshua Metellus`
- `nflreadpy import_rosters` attribute error — correct function name unknown, needs investigation
- Skill-position unmatched count not yet run
- `build_master.py` not yet added to `scrape.yml`
- Frontend still reading per-team JSONs, not yet wired to `players_master.json`
- the `nfl-formation-view.html` still loads from per-team JSONs too, not just `depth`-chart.html`. When you wire the frontend to `players_master.json`, both files need updating. Worth noting in the bug list so it doesn't get missed.

---

## Roadmap (priority order)
1. ⬜ Finish player identity pipeline (fix bugs above, get skill-pos unmatched count)
2. ⬜ Wire `depth-chart.html` to `players_master.json`, but the formation view loads differently (single team at a time on demand) vs the depth chart (all 32 at once). They'll need different loading strategies even though both read from the same source. Formation view stays as single-team fetch, just hits master instead of team file.
3. ⬜ Fix formation view hybrid scheme bug (Colts, Seahawks missing defender)
4. ⬜ Opponent overlay — same-team offense+defense simultaneously, then versus view
5. ⬜ Additional data sources: PFF grades, RAS scores, combine data, EPA/DVOA
6. ⬜ Player comparison
7. ⬜ Historical rating trends
8. ⬜ Multi-sport expansion — MLB first, then NHL/NBA/MLS/EPL

**Not in FieldView scope:** League leaderboards, game reviews, highlights, replays, podcasts, tweets — these belong in a separate media/highlights page down the road. Called ReView for being able to review the past day/week of games, highlights, box scores, stats, tweets, drama, reddit posts, podcasts, etc. Just to catch up on the league and all it's action.

---

## Workflow Notes
- Use this chat (claude.ai) for architecture decisions, debugging with context, pushback
- Use Claude Code (VS Code chat panel) for direct file edits
- Front-load thinking in chat → hand Claude Code a crisp specific instruction
- Start a new chat when switching to a new sport or major new feature area
- Paste this CLAUDE.md at the top of any new chat to restore context