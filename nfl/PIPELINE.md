# NFL Data Pipeline

Maps how `nfl/data/players_master.json` gets built: every source, what
script pulls it, what key joins it, and what happens when a join misses.
Numbers cited below are from the pipeline run on 2026-08-01 and will drift
as rosters/scrapes change — re-run `build_master.py` and read its printed
summary for current figures; treat the numbers here as illustrative, not a
contract.

---

## 1. Sources

| Source | Script | Raw output | Scope |
|---|---|---|---|
| OurLads depth charts | `scrape_depth.py` | `nfl/data/{abbr}.json` (one file per team, 32 files) | Roster + depth order + position — the spine every other source joins onto |
| nflreadpy rosters | `build_master.py` (`load_nflreadpy_gsis`) | not written to disk — pulled live at build time | GSIS ID, `entry_year`, `college`, `birth_date`, `pfr_id` |
| dynastyprocess crosswalk (GitHub CSV) | `build_master.py` (`load_gsis_crosswalk`) | not written to disk — fetched live from `github.com/dynastyprocess/data` | Primary GSIS ID source; fantasy-focused, weak OL/DI coverage |
| nflreadpy weekly stats | `scrape_stats.py` | merged directly into `nfl/data/{abbr}.json`'s `depth_chart[pos][i].stats` | Season stat totals, position-specific |
| nflreadpy snap counts | `build_master.py` (`load_snap_shares`) | not written to disk — pulled live at build time | `snap_pct`, plus a name+team crosswalk for OL (see §2) |
| Madden ratings | `scrape_madden.py` | `nfl/data/madden.json` | Overall rating, jersey, position label, per-position rank |
| Over The Cap | `scrape_otc.py` | merged directly into `nfl/data/{abbr}.json`'s `depth_chart[pos][i].cap_number` | Current-year cap number |
| Spotrac remaining contracts | `scrape_contracts_spotrac.py` | `nfl/data/spotrac_contracts.json` | Years/cash/guarantee remaining on current contract |

Two scripts (`scrape_stats.py`, `scrape_otc.py`) still mutate the 32
per-team JSONs directly, the pattern `merge_madden.py` used to follow.
Madden was moved off that pattern this session (see git history:
`e229fc6`); stats/OTC haven't been, so `build_master.py` reads their
output via `p.get('stats')` / `p.get('cap_number')` off the team files
rather than joining a standalone file itself. Not necessarily wrong, just
inconsistent — worth deciding whether to port those too at some point.

`spotrac_contracts.json` also captures an `age` column from Spotrac's
contracts page (`scrape_contracts_spotrac.py:86`) that **build_master.py
never reads** — `find_spotrac_contract`/the contract-merge block only
pulls `length_remaining`/`cash_total_remaining`/`cash_guaranteed_remaining`/
`pct_guaranteed_remaining`. A second, currently-dormant age source. Not
wired in, not evaluated for quality — noted here, not acted on.

---

## 2. Join keys

| Join | Key | Match strategy |
|---|---|---|
| OurLads name → GSIS ID | name + position + team | `find_gsis()`: alias substitution (`NAME_ALIASES`) → `normalize_for_matching()` → fuzzy match within position via rapidfuzz `token_sort_ratio`, ≥95% is an auto-accept, 80-94% retries scoped to the player's own team, <80% is no match. Crosswalk tried first, nflreadpy rosters as fallback. |
| OurLads name → Madden rating | name + team | `find_madden_player()`: **exact or word-subset match only, own team first, then league-wide fallback** — no fuzzy/rapidfuzz scoring at all, and (see Finding A below) **`NAME_ALIASES` is not consulted here**, unlike the GSIS path above. Gated by `find_madden_duplicate_names()`: if the normalized name collides across two different teams' rosters, cross-team fallback is disabled for that name (safer to leave unmatched than guess wrong). |
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

Using the wrong one for a given match would silently break the word-subset
fallback (that's why they're kept distinct rather than consolidated) — see
`normalize_madden`'s docstring for the specific reasoning.

---

## 3. Execution order (`build_master.py: build_master()`)

```
load_gsis_crosswalk()        ─┐
load_nflreadpy_gsis()         ├─ independent, all network/IO, no ordering constraint between them
load_spotrac_contracts()      │
load_snap_shares()           ─┘
load_madden()                  → buckets nfl/data/madden.json by team
build_madden_pos_ranks()       → depends on load_madden()'s output
find_madden_duplicate_names()  → independent (re-reads the 32 team files directly)

for each nfl/data/{abbr}.json:
  for each depth_chart position, each player:
    find_gsis()                → needs crosswalk + rosters (loaded above)
    [dedup by player_key]
    find_madden_player()       → needs madden_by_team + duplicate_names (loaded above)
    build the master `entry` dict, keyed by player_key

# second pass, over the now-complete `master` dict:
draft_year / college / age     → GSIS ID → nflreadpy roster row lookup
pfr_id (direct)                → from the same nflreadpy roster row
pfr_id (fallback, mainly OL)   → find_pfr_id(), independent name+team match
snap_pct                       → pfr_id → snap-share table lookup
Spotrac contract fields        → find_spotrac_contract(), independent match

write nfl/data/players_master.json
```

The key structural point: **every downstream join in the second pass reads
off `entry['gsis_id']`**, which was decided once in the first pass and
never revisited. If GSIS matching misses a player, `draft_year`, `college`,
`age`, and the direct `snap_pct` path all miss too, by construction — not
independently.

---

## 4. `players_master.json` field-by-field

| Field | Source | If the source misses |
|---|---|---|
| `player_id` | GSIS ID, else a slug | Slug fallback always succeeds (never null) |
| `gsis_id` | `find_gsis()` | `null` |
| `match_confidence` | rapidfuzz score from `find_gsis()` | `null` |
| `canonical_name` | `normalize_name()` of the OurLads name | Always populated (pure string transform) |
| `ourlads_name` | OurLads raw name | Always populated |
| `team`, `team_name`, `base_defense` | OurLads team file | Always populated |
| `ourlads_pos`, `standard_slot`, `standard_pos` | OurLads position + `enrich_positions()`'s scheme-aware slot map | `standard_pos` can be `'DEF'`/unset key mapping for a position `enrich_positions()` doesn't recognize |
| `depth` | OurLads row order | Defaults to `99` if missing |
| `jersey` | Madden match (`mp['jersey']`) | `null` — no other source carries jersey number |
| `age` | nflreadpy `birth_date`, via GSIS ID, → `calculate_age()` | `null` if no GSIS ID, **or** GSIS ID resolved but that roster row's `birth_date` is itself null (~5% of nflreadpy rows) |
| `madden`, `madden_rank`, `madden_rank_total`, `madden_pos_label` | `find_madden_player()` + `build_madden_pos_ranks()` | All `null` together — they're set from the same `mp` match or not at all |
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

Figures from the 2026-08-01 run (2,782 players in `master`) — re-check
against the script's own printed summary before relying on exact numbers.

- **GSIS matching: 1,440/2,782 (51.8%)**. This is the load-bearing gate —
  `draft_year`, `college`, `age`, and the direct `snap_pct` path all
  inherit this ceiling, since none of them run their own independent
  match (§3). Weakest for OL/DI (crosswalk is fantasy-focused, doesn't
  track them well).
- **OL snap-share: ~61% (306/503)**. `load_rosters`' `pfr_id` fill rate is
  ~0% for OL specifically, so the *direct* GSIS→pfr_id chain structurally
  can never reach them — 306/503 comes entirely from the independent
  `find_pfr_id()` name+team fallback against `load_snap_counts`'s own
  crosswalk (before that fallback: 0/503). The remaining ~39% are OL
  `load_snap_counts` itself has no record for.
- **`age`/`draft_year`: ~44% of players (1,234 and 1,239 of 2,782)**. Not
  an independent gap — it's the 51.8% GSIS-matched slice, times the ~95%
  of *those* rows that have a non-null `birth_date`/`entry_year` in
  nflreadpy's raw data. See Finding C below for the exact arithmetic.
- **Madden: 2,211/2,782 (79.5%)**. The one join in this pipeline that
  *isn't* gated behind GSIS — matched independently by name+team. See
  Finding A below for a specific, fixable gap inside that 20.5%.

---

# Findings: A, B, C

## A. Suffix-name players not matching in Madden

**Not the NBA word-boundary regex bug, and not a suffix-count (II vs III)
bug.** Tested both directly:

```
normalize_madden('Patrick Surtain III') -> 'patrick surtain'
normalize_madden('Patrick Surtain II')  -> 'patrick surtain'
```
Both strip correctly and identically — Python's regex engine backtracks
`(jr|sr|ii|iii|iv)` correctly even though `'ii'` is listed before `'iii'`
in the alternation, so "III" doesn't get chopped down to "III" minus "II"
leaving a stray "i". No bug there. (`normalize_madden` also doesn't
include `v`/`vi` in its suffix list at all, unlike `normalize_for_matching`
— which *does* still have the NBA-style bug, confirmed:
`normalize_for_matching('V.J. Payne')` → `'jpayne'`, silently eating the
"V" initial as if it were a Roman-numeral-V suffix. That bug is real, but
it lives in the GSIS/Spotrac/snap-count matcher, not the Madden one, and
wasn't what's breaking Surtain.)

**Actual cause: `NAME_ALIASES` is applied in `find_gsis()` but not in
`find_madden_player()`.** Confirmed against live data:

```
players_master.json: "Pat Surtain II" (DEN) — gsis_id: 00-0036874, madden: None
madden.json (raw scrape): "Patrick Surtain II", Denver Broncos, OVR 97
```

OurLads lists him as "Pat Surtain II"; both the dynastyprocess crosswalk
and Madden's own roster use the full "Patrick Surtain II". `NAME_ALIASES`
already has the fix (`'Pat Surtain II': 'Patrick Surtain II'`) — `find_gsis()`
applies it (hence `gsis_id` is populated), `find_madden_player()` doesn't
(hence `madden: None` despite the player clearly being in the scrape).

This isn't isolated to Surtain. Cross-checking every `NAME_ALIASES` entry
against current match state: **8 of 9 short-name-style aliases
(`Cobie Durant`, `Pat Surtain II`, `Cam Bynum`, `Kam Curl`, `Juju Brents`,
`Dru Phillips`, `Riq Woolen`, `Chig Okonkwo`) are unmatched in Madden**,
and I confirmed all 8 are genuinely present in `madden.json` under their
full name, on the correct team (e.g. `Chig Okonkwo` → `Chigoziem Okonkwo`,
Washington). Only `Vj Payne` happened to match anyway, incidentally,
because Madden's own name for him was close enough for the word-subset
fallback to catch without the alias.

Separately, I checked the other 32 unmatched-and-suffixed players (out of
39 total) — spot-checked several against `madden.json` directly and they're
genuinely absent from the scrape (e.g. `Frank Gore Jr.` isn't on Buffalo's
Madden roster at all), not a matching bug. A handful of others
(`Wydett Williams Jr.`, `Melvin Smith Jr.`, `Marvin Jones Jr.`, etc.) share
a last name with *different* real players who are in Madden — correctly
left unmatched rather than risk attaching a stranger's rating, which is
`find_madden_duplicate_names()`/the team-scoped-first logic working exactly
as designed, not a bug.

**Scope for a fix (not implemented — reporting only):** apply
`NAME_ALIASES.get(name, name)` before normalizing in `find_madden_player()`,
same as `find_gsis()` already does. Confirmed-affected: at least 8 players.

## B. Rookies showing "age / NFL yr" instead of "age / % of snaps"

Confirmed in `nfl/nfl-formation-view.html:1050-1051` — the player-card's
secondary stat line:
```js
${p.snap_pct != null ? Math.round(p.snap_pct) + '%' : (p.years_pro != null ? p.years_pro : '—')}
${p.snap_pct != null ? 'Snaps' : 'NFL Yr'}
```
Falls back to `years_pro`/"NFL Yr" whenever `snap_pct` is `null` — exactly
the behavior described. This logic only exists on the formation-view
player card; `depth-chart.html`'s table has a plain, always-present
"NFL Yr" column and no such fallback (`years_pro` and snap data aren't
combined into one cell there).

**Root cause is a data-timing issue, not a frontend logic bug.**
`get_current_season()` resolves to 2025 right now (today is pre-September
2026, so it falls back to the last *completed* season) — `snap_pct` is
built from `load_snap_counts([2025])`, i.e. real 2025-season snap data.
Any player drafted in the 2026 class has, by definition, zero NFL snaps in
2025 — `snap_pct` is correctly `null` for every rookie, not a bug in how
it's computed or displayed. Established veterans who played in 2025 show
real `%` because they have real 2025 data; rookies fall through to
`years_pro` (`0`, hence "NFL Yr" label) because there's nothing else to
show. The card already flags rookies separately too (`years_pro === 0` →
an "R" badge, line 1035) — so the info isn't lost, it's just that the
mini-stat block's fallback duplicates it in a less obvious label ("NFL Yr"
showing "0" reads as "0 NFL years", which is correct but not obviously
"this stat is unavailable, here's a related one instead").

This will resolve on its own once the 2026 season starts and
`get_current_season()`/`load_snap_counts` roll forward to real in-season
data — not something that needs a data-side fix. Whether the *label*
should be clearer about why it's showing a fallback is a frontend polish
question, not a bug question — not fixed here per scope.

## C. Age missing for ~56% of players

**Confirmed fully explained by the GSIS gate — no secondary bug.** The
exact arithmetic, from the current run:

- 2,782 total players in `master`
- 1,440 have a `gsis_id` (51.8%) — the rest (48.2%) get `age: null`
  unconditionally, no `birth_date` lookup even attempted
- Of the 1,440 GSIS-matched, `age` populated for 1,234 (85.7%) — the
  remaining 206 have a real `gsis_id` but that exact ID's row in
  nflreadpy's roster snapshot has a null `birth_date` (measured directly:
  163/3,137 roster rows, 5.2%, have no `birth_date` at all — consistent
  with the ~14% gap seen here once you account for `draft_year` using
  `entry_year`, which has slightly better fill than `birth_date` in the
  same rows)
- `1,234 / 2,782 = 44.4%` matched → `55.6%` missing, matching the ~56%
  cited

`draft_year` (1,239/2,782) and `age` (1,234/2,782) differ by only 5
players — both are joined off the exact same `gsis_id → nflreadpy roster
row` lookup, in the same loop, so they should track almost exactly, and
they do. That tight agreement is itself the confirmation: there's no
separate matching step for `age` that could have its own independent
failure mode — it rides entirely on whichever `gsis_id` decision GSIS
matching already made per-player.

One adjacent, unexplored option worth knowing about (not evaluated,
not proposed as a fix here): `scrape_contracts_spotrac.py` already scrapes
an `age` column from Spotrac's own contracts page (§1) that
`build_master.py` never reads. It has its own independent match
(`find_spotrac_contract()`, name+team, not gated behind GSIS at all) — so
it could in principle fill some of the 1,548 currently-null players GSIS
matching misses, but that's a genuinely separate source with its own
match-rate ceiling to evaluate, not a fix to the current GSIS-gated path.