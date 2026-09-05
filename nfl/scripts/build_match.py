"""Phase 2: recreate build_master.py's matching logic against the DuckDB
tables Phase 1 (build_db.py) loaded, writing results into a `player_match`
table -- one row per final (post-dedup) player, keyed to the winning raw
ourlads_players.row_id.

Reuses build_master.py's pure matching functions and constants directly
(find_gsis, find_madden_player, _match_in_df, find_pfr_id,
find_spotrac_contract, NAME_ALIASES, STAT_MAP, position maps, etc.) so the
matching RULES are literally the same code, not a transcription. Only the
data-loading side is swapped from live scrapes/JSON files to the DB
snapshot Phase 1 captured. build_master.py itself is untouched and still
runs standalone -- this script is additive, run side by side with it for
Phase 2's parity verification.
"""
import os
import re

import duckdb
import pandas as pd

from build_master import (
    SEASON, NAME_ALIASES, SKIP_POSITIONS, MADDEN_TEAM_MAP, SNAP_POS_MAP,
    SPOTRAC_POS_MAP, CROSSWALK_POS_ALIASES, ROSTERS_POS_ALIASES,
    normalize_team, build_madden_pos_ranks, find_madden_player, find_gsis,
    find_pfr_id, find_spotrac_contract, find_roster_gsis_for_ol,
)
from name_utils import normalize_name, normalize_for_matching, normalize_madden

DB_PATH = os.path.join('nfl', 'data', 'fieldview.duckdb')


def load_madden_from_db(con):
    """DB-backed equivalent of build_master.load_madden() -- same output
    shape (dict of team abbr -> list of normalized madden player dicts),
    sourced from the madden_ratings table instead of madden.json directly."""
    df = con.execute("SELECT * FROM madden_ratings").fetchdf()
    by_team = {}
    for _, p in df.iterrows():
        abbr = MADDEN_TEAM_MAP.get(p.get('team.label', ''))
        if not abbr:
            continue
        full_name = f"{p['firstName']} {p['lastName']}"
        by_team.setdefault(abbr, []).append({
            "full_name": full_name,
            "normalized": normalize_madden(full_name),
            "overall": p['overallRating'],
            "jersey": p.get('jerseyNum'),
            "age": p.get('age'),
            "years_pro": p.get('yearsPro'),
            "position": p.get('position.shortLabel', ''),
        })
    return by_team


def find_madden_duplicate_names_from_db(con):
    """DB-backed equivalent of build_master.find_madden_duplicate_names() --
    reads the ourlads_players table (all rows, all positions, mirroring the
    original's unfiltered read of every nfl/data/*.json depth_chart entry)
    instead of the team files directly."""
    df = con.execute("SELECT abbr, name FROM ourlads_players").fetchdf()
    teams_by_name = {}
    for _, row in df.iterrows():
        key = normalize_madden(row['name'])
        teams_by_name.setdefault(key, set()).add(row['abbr'])
    return {name for name, teams in teams_by_name.items() if len(teams) > 1}


def load_gsis_crosswalk_from_db(con):
    df = con.execute("SELECT * FROM gsis_crosswalk").fetchdf()
    df = df[df['gsis_id'].notna()].copy()
    df['team_norm'] = df['team'].apply(normalize_team)
    df['name_norm'] = df['name'].apply(
        lambda n: normalize_for_matching(normalize_name(str(n))))
    return df


def load_nflreadpy_rosters_from_db(con):
    df = con.execute("SELECT * FROM nflreadpy_rosters").fetchdf()
    df = df[df['gsis_id'].notna()].copy()
    df = df.rename(columns={'full_name': 'player_name'})
    df['name_norm'] = df['player_name'].apply(
        lambda n: normalize_for_matching(normalize_name(str(n))))
    df['team_norm'] = df['team'].apply(normalize_team)
    df['position'] = df['position'].fillna('')
    return df


def load_spotrac_contracts_from_db(con):
    df = con.execute("SELECT * FROM spotrac_contracts").fetchdf()
    df['standard_pos'] = df['pos'].map(SPOTRAC_POS_MAP)
    df = df[df['standard_pos'].notna()].copy()
    df['row_idx'] = df.index
    return df


def load_snap_shares_from_db(con):
    snaps = con.execute("SELECT * FROM snap_counts").fetchdf()

    total_snaps = (snaps['offense_snaps'].fillna(0)
                   + snaps['defense_snaps'].fillna(0)
                   + snaps['st_snaps'].fillna(0))
    played = snaps[total_snaps > 0]

    season_avg = played.groupby('pfr_player_id').agg(
        offense_pct=('offense_pct', 'mean'),
        defense_pct=('defense_pct', 'mean'),
    )

    crosswalk = snaps[snaps['pfr_player_id'].notna()][
        ['player', 'team', 'position', 'pfr_player_id']
    ].drop_duplicates(subset='pfr_player_id', keep='last').copy()
    crosswalk['standard_pos'] = crosswalk['position'].map(SNAP_POS_MAP)
    crosswalk = crosswalk[crosswalk['standard_pos'].notna()]
    crosswalk['name_norm'] = crosswalk['player'].apply(
        lambda n: normalize_for_matching(normalize_name(str(n))))
    crosswalk['team_norm'] = crosswalk['team'].apply(normalize_team)

    return season_avg, crosswalk


def load_penalties_from_db(con):
    """Season penalty counts (Offensive Holding + False Start only --
    see build_db.py's load_penalties()) keyed by gsis_id -- already in
    the right format, no name/team matching needed."""
    df = con.execute("SELECT * FROM penalties").fetchdf()
    return df.groupby('penalty_player_id').size().to_dict()


def build_match():
    con = duckdb.connect(DB_PATH)

    crosswalk = load_gsis_crosswalk_from_db(con)
    rosters = load_nflreadpy_rosters_from_db(con)
    spotrac_df = load_spotrac_contracts_from_db(con)
    snap_shares, snap_crosswalk = load_snap_shares_from_db(con)
    penalty_counts = load_penalties_from_db(con)

    madden_by_team = load_madden_from_db(con)
    madden_pos_ranks = build_madden_pos_ranks(madden_by_team)
    all_madden_players = [p for players in madden_by_team.values() for p in players]
    madden_duplicate_names = find_madden_duplicate_names_from_db(con)

    ourlads = con.execute(
        "SELECT * FROM ourlads_players ORDER BY row_id"
    ).fetchdf()

    master = {}  # player_key -> match result dict (mirrors build_master's dedup)

    for _, p in ourlads.iterrows():
        if p['ourlads_pos'] in SKIP_POSITIONS:
            continue

        raw_name = p['name']
        if not raw_name:
            continue

        canonical_name = normalize_name(raw_name)
        standard_pos = p['standard_pos'] or ''
        abbr = p['abbr']

        gsis_id, confidence = find_gsis(
            canonical_name, standard_pos, abbr, crosswalk, rosters)

        if gsis_id:
            player_key = gsis_id
        else:
            safe = re.sub(r'[^a-z0-9]', '-', normalize_for_matching(canonical_name))
            safe = re.sub(r'-+', '-', safe).strip('-')
            player_key = f"{safe}-{standard_pos.lower()}-{abbr.lower()}"

        depth = p['depth'] if pd.notna(p['depth']) else 99
        if player_key in master:
            if depth >= master[player_key]['depth']:
                continue

        madden_is_dup = normalize_madden(raw_name) in madden_duplicate_names
        mp = find_madden_player(raw_name, madden_by_team.get(abbr, []),
                                 all_madden_players,
                                 allow_cross_team=not madden_is_dup)
        madden_rank_info = madden_pos_ranks.get(mp["normalized"]) if mp else None

        master[player_key] = {
            'row_id': int(p['row_id']),
            'player_key': player_key,
            'depth': depth,
            'canonical_name': canonical_name,
            'team': abbr,
            'standard_pos': standard_pos,
            'gsis_id': gsis_id,
            'match_confidence': confidence,
            'match_source': 'gsis' if gsis_id else None,
            'madden': mp['overall'] if mp else None,
            'madden_jersey': mp['jersey'] if mp else None,
            'madden_rank': madden_rank_info['rank'] if madden_rank_info else None,
            'madden_rank_total': madden_rank_info['total'] if madden_rank_info else None,
            'madden_pos_label': madden_rank_info['pos'] if madden_rank_info else None,
        }

    # draft_year/college/years_pro/age, keyed off the gsis_id already resolved
    entry_year_by_gsis, college_by_gsis, pfr_id_by_gsis, birth_date_by_gsis = {}, {}, {}, {}
    dedup_rosters = rosters.drop_duplicates(subset='gsis_id', keep='first')
    for _, row in dedup_rosters.iterrows():
        gid = row['gsis_id']
        if not gid:
            continue
        entry_year = row.get('entry_year')
        entry_year_by_gsis[gid] = int(entry_year) if pd.notna(entry_year) else None
        college = row.get('college')
        college_by_gsis[gid] = college if pd.notna(college) else None
        pfr_id = row.get('pfr_id')
        pfr_id_by_gsis[gid] = pfr_id if pd.notna(pfr_id) else None
        birth_date = row.get('birth_date')
        birth_date_by_gsis[gid] = birth_date if pd.notna(birth_date) else None

    from season_utils import calculate_age
    for entry in master.values():
        gid = entry.get('gsis_id')
        # OL never has a gsis_id from our own matching (find_gsis() skips OL
        # entirely) -- recover one via an independent name+team match against
        # nflreadpy's own roster data instead, so OL can reach the same bio
        # dicts every other position already uses. Local variable only --
        # entry['gsis_id'] itself is untouched, so match_source/
        # match_confidence keep accurately reflecting OL was never primarily
        # GSIS-matched. Mirrors build_master.py's identical handling.
        if gid is None and entry['standard_pos'] == 'OL':
            gid = find_roster_gsis_for_ol(entry['canonical_name'], entry['team'], rosters)
        entry_year = entry_year_by_gsis.get(gid) if gid else None
        entry['draft_year'] = entry_year
        entry['college'] = college_by_gsis.get(gid) if gid else None
        # Clamp to 0 -- matches build_master.py's existing fix for the same
        # edge case (a player whose entry_year is the season that hasn't
        # "started" yet by get_current_season()'s Sept 1 rule shouldn't show
        # negative years of experience). build_match.py was missing this.
        entry['years_pro'] = max(0, SEASON - entry_year) if entry_year is not None else None
        birth_date = birth_date_by_gsis.get(gid) if gid else None
        entry['age'] = calculate_age(birth_date)
        entry['penalty_count'] = penalty_counts.get(gid, 0) if gid else None

    # snap_pct: gsis->pfr_id chain first, independent name+team fuzzy match
    # against the snap-count crosswalk second (closes the OL gap)
    def snap_pct_for(pfr_id):
        if snap_shares is None or not pfr_id or pfr_id not in snap_shares.index:
            return None
        row = snap_shares.loc[pfr_id]
        candidates = [v for v in (row['offense_pct'], row['defense_pct']) if pd.notna(v)]
        return round(max(candidates) * 100, 1) if candidates else None

    pfr_id_direct = {}
    for key, entry in master.items():
        gid = entry.get('gsis_id')
        pfr_id_direct[key] = pfr_id_by_gsis.get(gid) if gid else None

    for key, entry in master.items():
        if pfr_id_direct[key] is not None:
            continue
        pfr_id, _ = find_pfr_id(entry['canonical_name'], entry['standard_pos'],
                                 entry['team'], snap_crosswalk)
        if pfr_id:
            pfr_id_direct[key] = pfr_id

    for key, entry in master.items():
        entry['snap_pct'] = snap_pct_for(pfr_id_direct[key])

    # Spotrac remaining-contract fuzzy match
    for entry in master.values():
        row_idx, _ = find_spotrac_contract(
            entry['canonical_name'], entry['standard_pos'], entry['team'], spotrac_df)
        if row_idx is not None:
            row = spotrac_df.loc[row_idx]
            years_remaining = int(row['length_remaining']) if pd.notna(row['length_remaining']) else None
            cash_total = float(row['cash_total_remaining']) if pd.notna(row['cash_total_remaining']) else None
            cash_guaranteed = float(row['cash_guaranteed_remaining']) if pd.notna(row['cash_guaranteed_remaining']) else None
            entry['years_remaining'] = years_remaining
            entry['cash_total_remaining'] = cash_total
            entry['cash_guaranteed_remaining'] = cash_guaranteed
            entry['avg_annual_remaining'] = (
                cash_total / years_remaining
                if cash_total is not None and years_remaining else None
            )
        else:
            entry['years_remaining'] = None
            entry['cash_total_remaining'] = None
            entry['cash_guaranteed_remaining'] = None
            entry['avg_annual_remaining'] = None

    match_df = pd.DataFrame(list(master.values()))
    con.register('_tmp_match', match_df)
    con.execute("CREATE OR REPLACE TABLE player_match AS SELECT * FROM _tmp_match")
    con.unregister('_tmp_match')
    con.close()

    total = len(match_df)
    gsis_matched = match_df['gsis_id'].notna().sum()
    madden_matched = match_df['madden'].notna().sum()
    print(f"player_match: {total} players")
    print(f"GSIS matched: {gsis_matched} ({gsis_matched / total * 100:.1f}%)")
    print(f"Madden matched: {madden_matched} ({madden_matched / total * 100:.1f}%)")


if __name__ == '__main__':
    build_match()
