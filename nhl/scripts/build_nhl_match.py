"""nhl/scripts/build_nhl_match.py

Phase 2 (NHL): joins the raw nhl_* tables Phase 1 (scrape_roster.py,
scrape_stats.py, and optionally scrape_ratings.py) loaded into
fieldview.duckdb, and writes a resolved player_match table back to the
same DB -- same role as mlb/scripts/build_mlb_match.py.

Base population is nhl_roster (811 rows, all 32 teams), NOT the stats
tables -- same reasoning as MLB: roster is "who's on a team today"
(well, this offseason's build-out), stats are a frozen snapshot of the
last completed season (20252026), pulled deliberately from a different
season than the roster (20262027) per nhl/scripts/season_utils.py.
A rookie/offseason signee with no 20252026 games is a valid
no-stats-yet row, not an error.

team/team_abbr are sourced from nhl_roster ONLY, never from the stats
tables' teamAbbrevs -- confirmed live that 164/703 (23.3%) of matched
skaters disagree between the two, and 114 of those are real team
changes between the stats season and the roster season (expected,
given the two tables are pulled from different seasons by design).
Same MLB lesson (roster beats season-stats for "current team"), just a
much bigger fraction here.

Ratings (nhl_ratings, from scrape_ratings.py) are joined in only if
that table exists in the DB -- it's currently blocked by nhlratings.net
returning a real Cloudflare 403 mid-session (see scrape_ratings.py's
docstring), so this ships without ratings for now, same precedent as
MLB's first DiamondView pass shipping without theshowratings.com data.
"""
import os

import duckdb
import pandas as pd

DB_PATH = os.path.join('nhl', 'data', 'fieldview.duckdb')

# Columns stripped out of the raw stats rows before they're embedded as
# skater_stats/goalie_stats -- everything else is real, unmodified
# NHL stats-API data under its own field names. teamAbbrevs is
# deliberately dropped here too (not just unused) -- see module
# docstring for why it can't be trusted as "current team".
STATS_ADMIN_COLS = {
    'row_id', 'playerId', 'loaded_at', 'teamAbbrevs',
    'lastName', 'skaterFullName', 'goalieFullName',
    'positionCode', 'shootsCatches',
}


def clean(v):
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return None
    return v.item() if hasattr(v, 'item') else v


def stats_dict(row):
    return {k: clean(v) for k, v in row.items() if k not in STATS_ADMIN_COLS}


def table_exists(con, name):
    return con.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_name = ?", [name]
    ).fetchone() is not None


def build_match():
    con = duckdb.connect(DB_PATH)

    roster = con.execute("""
        SELECT player_id, team_abbr, position_group, first_name, last_name,
               sweater_number, position_code, shoots_catches,
               height_in_inches, weight_in_pounds, birth_date,
               birth_city, birth_country, birth_state_province
        FROM nhl_roster
        ORDER BY row_id
    """).fetchdf()

    skaters = con.execute("SELECT * FROM nhl_stats_skaters").fetchdf()
    goalies = con.execute("SELECT * FROM nhl_stats_goalies").fetchdf()

    has_ratings = table_exists(con, 'nhl_ratings')
    ratings_by_id = {}
    if has_ratings:
        ratings = con.execute(
            "SELECT * FROM nhl_ratings WHERE player_id IS NOT NULL"
        ).fetchdf()
        ratings_by_id = {int(r['player_id']): r for _, r in ratings.iterrows()}

    con.close()

    skaters_by_id = {int(r['playerId']): r for _, r in skaters.iterrows()}
    goalies_by_id = {int(r['playerId']): r for _, r in goalies.iterrows()}

    matches = []
    for _, r in roster.iterrows():
        pid = int(r['player_id'])

        skater_row = skaters_by_id.get(pid)
        goalie_row = goalies_by_id.get(pid)
        if skater_row is not None:
            stats_source = 'skater'
        elif goalie_row is not None:
            stats_source = 'goalie'
        else:
            stats_source = 'roster_only'

        entry = {
            'player_id': pid,
            'name': f"{clean(r['first_name'])} {clean(r['last_name'])}",
            'team_abbr': clean(r['team_abbr']),
            'position_group': clean(r['position_group']),
            'position_code': clean(r['position_code']),
            'jersey_number': clean(r['sweater_number']),
            'shoots_catches': clean(r['shoots_catches']),
            'height_in_inches': clean(r['height_in_inches']),
            'weight_in_pounds': clean(r['weight_in_pounds']),
            'birth_date': clean(r['birth_date']),
            'birth_city': clean(r['birth_city']),
            'birth_country': clean(r['birth_country']),
            'birth_state_province': clean(r['birth_state_province']),
            'skater_stats': stats_dict(skater_row) if skater_row is not None else None,
            'goalie_stats': stats_dict(goalie_row) if goalie_row is not None else None,
            'stats_source': stats_source,
        }

        rating_row = ratings_by_id.get(pid)
        entry['overall_rating'] = clean(rating_row['overall_rating']) if rating_row is not None else None
        entry['potential'] = clean(rating_row['potential']) if rating_row is not None else None

        matches.append(entry)

    match_df = pd.DataFrame(matches)
    con = duckdb.connect(DB_PATH)
    con.register('_tmp_match', match_df)
    con.execute("CREATE OR REPLACE TABLE player_match AS SELECT * FROM _tmp_match")
    con.unregister('_tmp_match')
    con.close()

    total = len(match_df)
    matched_stats = (match_df['stats_source'] != 'roster_only').sum()
    rated = match_df['overall_rating'].notna().sum()
    print(f"player_match: {total} players")
    print(f"Matched to skater/goalie stats: {matched_stats} / {total} ({matched_stats / total:.1%})")
    print(f"Ratings joined: {'yes' if has_ratings else 'no (nhl_ratings table not present)'}"
          + (f" -- {rated} / {total} rated" if has_ratings else ""))


if __name__ == '__main__':
    build_match()
