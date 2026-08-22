"""mlb/scripts/build_mlb_match.py

Phase 2 (MLB): joins the raw statsapi_* tables Phase 1
(scrape_roster.py, scrape_stats.py) loaded into fieldview.duckdb, and
writes a resolved player_match table back to the same DB -- same role
as nfl/scripts/build_match.py and nba/scripts/build_nba_match.py.

Base population is today's active roster (statsapi_roster, 782 rows as
of the last pull), NOT the full statsapi_stats_hitting/pitching
person_id union (1,382 as of the last check). Season stats include
anyone who played in 2026 at all, including traded/released/optioned
players no longer on any 30-man roster -- left-joining stats onto
roster keeps player_match aligned with "who's on a team today", which
is what DiamondView needs. A rookie/late call-up with zero 2026 games
is a valid null-stats row, not an error.

Position taxonomy is clean here (no NFL EDGE/DI-style collapse):
  IF = 1B/2B/3B/SS, OF = LF/CF/RF, standalone = C/P/DH
Two known single-player edge cases, confirmed against the live data
(not assumed):
  - Shohei Ohtani (position_abbreviation 'TWP') has no fielding
    position -- player_type 'two_way', position_group left null rather
    than forced into a slot. DiamondView's own call how to render that,
    not this script's.
  - Cristian Pache (generic 'OF', no L/C/R split in the source) keeps
    position_group='OF' (so OF-zone substitution gating still works
    normally for him), tagged position_group_source='defaulted' so
    DiamondView knows to default his specific field zone to CF rather
    than treating him as indistinguishable from a real CF.

match_source records where each player's stat rows came from -- the
useful "provenance" signal here, since (unlike NFL/NBA) there's only
one vendor and no fuzzy name matching, just data availability:
'both', 'hitting', 'pitching', or 'roster_only' (no 2026 games yet).

Ratings (show_ratings, from theshowratings.com via scrape_ratings.py's
ScraperAPI proxy -- see CLAUDE.md's theshowratings.com Scraper section)
are left-joined onto the roster population by person_id, same clean-ID
join theshowratings.com already gave this pipeline. Checked live before
joining: zero duplicate person_id rows in the current show_ratings
pull, but a traded player could plausibly appear on two teams' org-
depth pages in a future run, so the dedup (keep the row with the max
loaded_at per person_id) runs unconditionally rather than only after a
duplicate is actually observed. Unmatched roster players get
overall_rating/potential = null, same convention as batting_stats/
pitching_stats for a player with no stats yet -- never dropped, never
defaulted.
"""
import os

import duckdb
import pandas as pd

DB_PATH = os.path.join('mlb', 'data', 'fieldview.duckdb')

POSITION_GROUP_MAP = {
    '1B': 'IF', '2B': 'IF', '3B': 'IF', 'SS': 'IF',
    'LF': 'OF', 'CF': 'OF', 'RF': 'OF',
    'C': 'standalone', 'P': 'standalone', 'DH': 'standalone',
}

# Administrative/join columns stripped out of the raw stats rows before
# they're embedded as batting_stats/pitching_stats -- everything else is
# real, unmodified statsapi.mlb.com stat data under its own field names.
STATS_ADMIN_COLS = {'row_id', 'person_id', 'full_name', 'team_id', 'team_abbr', 'resolved_team_abbr', 'group', 'loaded_at'}


def resolve_position_group(position_abbr):
    if position_abbr == 'OF':
        # Group stays 'OF' (clean 3-value enum: IF/OF/standalone) so
        # substitution gating on position_group works uniformly -- the
        # specific "which OF zone" default (CF) is a frontend rendering
        # decision, not a data-layer field. position_group_source is the
        # debug flag that this player's OF slot wasn't in the source data.
        return 'OF', 'defaulted'
    group = POSITION_GROUP_MAP.get(position_abbr)
    return (group, 'mapped') if group else (None, None)


def resolve_player_type(position_abbr):
    if position_abbr == 'P':
        return 'pitcher'
    if position_abbr == 'TWP':
        return 'two_way'
    return 'batter'


def clean(v):
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return None
    return v.item() if hasattr(v, 'item') else v


def stats_dict(row):
    return {k: clean(v) for k, v in row.items() if k not in STATS_ADMIN_COLS}


def build_match():
    con = duckdb.connect(DB_PATH)

    roster = con.execute("""
        SELECT r.person_id, r.team_id, r.team_abbr, t.name AS team_name, r.full_name,
               r.jersey_number, r.position_abbreviation, r.position_name,
               p.height, p.weight, p.bat_side, p.pitch_hand, p.birth_date
        FROM statsapi_roster r
        LEFT JOIN statsapi_people p ON p.person_id = r.person_id
        LEFT JOIN statsapi_teams t ON t.id = r.team_id
        ORDER BY r.row_id
    """).fetchdf()

    hitting = con.execute("""
        SELECT h.*, t.abbreviation AS resolved_team_abbr
        FROM statsapi_stats_hitting h
        LEFT JOIN statsapi_teams t ON t.id = h.team_id
    """).fetchdf()

    pitching = con.execute("""
        SELECT pt.*, t.abbreviation AS resolved_team_abbr
        FROM statsapi_stats_pitching pt
        LEFT JOIN statsapi_teams t ON t.id = pt.team_id
    """).fetchdf()

    ratings_exists = con.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_name = 'show_ratings'"
    ).fetchone() is not None
    ratings = con.execute("SELECT * FROM show_ratings").fetchdf() if ratings_exists else pd.DataFrame()

    con.close()

    hitting_by_id = {int(r['person_id']): r for _, r in hitting.iterrows()}
    pitching_by_id = {int(r['person_id']): r for _, r in pitching.iterrows()}

    ratings_by_id = {}
    ratings_dupes = 0
    if not ratings.empty:
        # Pick one row per person_id deterministically (most recent
        # loaded_at) rather than let a duplicate silently fan the join
        # out into multiple output rows for the same player.
        ratings_sorted = ratings.sort_values('loaded_at')
        for _, r in ratings_sorted.iterrows():
            pid = int(r['person_id'])
            if pid in ratings_by_id:
                ratings_dupes += 1
            ratings_by_id[pid] = r  # later (more recent) row wins

    matches = []
    for _, r in roster.iterrows():
        pid = int(r['person_id'])
        pos_abbr = clean(r['position_abbreviation'])
        position_group, position_group_source = resolve_position_group(pos_abbr)

        hit_row = hitting_by_id.get(pid)
        pitch_row = pitching_by_id.get(pid)
        rating_row = ratings_by_id.get(pid)
        if hit_row is not None and pitch_row is not None:
            match_source = 'both'
        elif hit_row is not None:
            match_source = 'hitting'
        elif pitch_row is not None:
            match_source = 'pitching'
        else:
            match_source = 'roster_only'

        matches.append({
            'person_id': pid,
            'name': clean(r['full_name']),
            'team': clean(r['team_name']),
            'team_abbr': clean(r['team_abbr']),
            'position': pos_abbr,
            'position_name': clean(r['position_name']),
            'position_group': position_group,
            'position_group_source': position_group_source,
            'player_type': resolve_player_type(pos_abbr),
            'jersey_number': clean(r['jersey_number']),
            'height': clean(r['height']),
            'weight': clean(r['weight']),
            'bats': clean(r['bat_side']),
            'throws': clean(r['pitch_hand']),
            'batting_stats': stats_dict(hit_row) if hit_row is not None else None,
            'pitching_stats': stats_dict(pitch_row) if pitch_row is not None else None,
            'match_source': match_source,
            'overall_rating': clean(rating_row['ovr']) if rating_row is not None else None,
            'potential': clean(rating_row['pot']) if rating_row is not None else None,
        })

    match_df = pd.DataFrame(matches)
    con = duckdb.connect(DB_PATH)
    con.register('_tmp_match', match_df)
    con.execute("CREATE OR REPLACE TABLE player_match AS SELECT * FROM _tmp_match")
    con.unregister('_tmp_match')
    con.close()

    total = len(match_df)
    matched_stats = (match_df['match_source'] != 'roster_only').sum()
    matched_ratings = match_df['overall_rating'].notna().sum()
    twp = match_df[match_df['player_type'] == 'two_way']['name'].tolist()
    defaulted = match_df[match_df['position_group_source'] == 'defaulted']['name'].tolist()
    print(f"player_match: {total} players")
    print(f"Matched to hitting and/or pitching stats: {matched_stats} / {total} ({matched_stats / total:.1%})")
    if ratings_exists:
        print(f"Matched to show_ratings: {matched_ratings} / {total} ({matched_ratings / total:.1%})"
              + (f" -- {ratings_dupes} duplicate person_id row(s) in show_ratings resolved by most-recent loaded_at" if ratings_dupes else ""))
    else:
        print("show_ratings table not present -- overall_rating/potential are null for everyone")
    print(f"two_way players: {twp}")
    print(f"defaulted position_group (generic OF -> CF): {defaulted}")


if __name__ == '__main__':
    build_match()
