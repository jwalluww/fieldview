import json
import glob
import re
import os
import pandas as pd
from rapidfuzz import fuzz, process
from season_utils import get_current_season, calculate_age
from name_utils import (
    normalize_name, normalize_for_matching, normalize_madden,
    NAME_ALIASES as SHARED_NAME_ALIASES,
)

SEASON = get_current_season()

# Known name mismatches between OurLads and crosswalk.
# Genuine nickname/legal-name aliases live in name_utils.NAME_ALIASES
# (shared with scrape_otc.py's OTC contract matching) -- only the
# crosswalk-specific "forced no-match" entries stay local here, since
# they mean "this OurLads name matches the WRONG player in the GSIS
# crosswalk specifically," which says nothing about whether other
# sources (Madden, OTC) have the same problem.
NAME_ALIASES = {
    **SHARED_NAME_ALIASES,
    # Forced no-matches (wrong players in crosswalk)
    'Matt Hibner': None,
    'Mike Jackson': None,
    'Joshua Metellus': None,
    'Greg Rousseau': 'Gregory Rousseau',
}

SKIP_POSITIONS = {'KR', 'PR', 'KO', 'PK', 'LS', 'K', 'P', 'PT', 'H'}

TEAM_ABB_MAP = {
    'ARI': 'ARZ', 'KCC': 'KC',  'LVR': 'LV',
    'TBB': 'TB',  'SFO': 'SF',  'GNB': 'GB',
    'NOR': 'NO',  'NWE': 'NE',
}

def normalize_team(abbr):
    return TEAM_ABB_MAP.get(abbr, abbr)

# Full team name -> our abbreviation, as used in madden.json's team.label
# field. Ported from the old merge_madden.py's TEAM_MAP.
MADDEN_TEAM_MAP = {
    "Arizona Cardinals": "ARZ",
    "Atlanta Falcons": "ATL",
    "Baltimore Ravens": "BAL",
    "Buffalo Bills": "BUF",
    "Carolina Panthers": "CAR",
    "Chicago Bears": "CHI",
    "Cincinnati Bengals": "CIN",
    "Cleveland Browns": "CLE",
    "Dallas Cowboys": "DAL",
    "Denver Broncos": "DEN",
    "Detroit Lions": "DET",
    "Green Bay Packers": "GB",
    "Houston Texans": "HOU",
    "Indianapolis Colts": "IND",
    "Jacksonville Jaguars": "JAX",
    "Kansas City Chiefs": "KC",
    "Las Vegas Raiders": "LV",
    "Los Angeles Chargers": "LAC",
    "Los Angeles Rams": "LAR",
    "Miami Dolphins": "MIA",
    "Minnesota Vikings": "MIN",
    "New England Patriots": "NE",
    "New Orleans Saints": "NO",
    "New York Giants": "NYG",
    "New York Jets": "NYJ",
    "Philadelphia Eagles": "PHI",
    "Pittsburgh Steelers": "PIT",
    "San Francisco 49ers": "SF",
    "Seattle Seahawks": "SEA",
    "Tampa Bay Buccaneers": "TB",
    "Tennessee Titans": "TEN",
    "Washington Commanders": "WAS",
}

def load_madden(path):
    """Load madden.json and bucket by team abbr. Ported from the old
    merge_madden.py's load_madden()."""
    if not os.path.exists(path):
        print(f"Warning: {path} not found, skipping Madden merge")
        return {}
    with open(path) as f:
        players = json.load(f)

    by_team = {}
    for p in players:
        team_label = p.get("team", {}).get("label", "")
        abbr = MADDEN_TEAM_MAP.get(team_label)
        if not abbr:
            continue
        by_team.setdefault(abbr, []).append({
            "full_name": f"{p['firstName']} {p['lastName']}",
            "normalized": normalize_madden(f"{p['firstName']} {p['lastName']}"),
            "overall": p["overallRating"],
            "jersey": p.get("jerseyNum"),
            "age": p.get("age"),
            "years_pro": p.get("yearsPro"),
            "position": p.get("position", {}).get("shortLabel", ""),
        })
    return by_team

def build_madden_pos_ranks(madden_by_team):
    """Ported from the old merge_madden.py's build_pos_ranks()."""
    all_players = [p for players in madden_by_team.values() for p in players]
    by_position = {}
    for p in all_players:
        by_position.setdefault(p["position"], []).append(p)
    pos_ranks = {}
    for pos, players in by_position.items():
        sorted_players = sorted(players, key=lambda x: x["overall"], reverse=True)
        for rank, player in enumerate(sorted_players, 1):
            pos_ranks[player["normalized"]] = {
                "rank": rank,
                "total": len(sorted_players),
                "pos": pos
            }
    return pos_ranks

def find_madden_duplicate_names(team_abbrs):
    """Normalized names that appear in more than one team's depth chart.

    For these, a Madden entry that only turns up via the cross-team
    fallback usually belongs to the OTHER, different real person who
    happens to share the name — not this player. Safer to leave them
    unmatched than to risk attaching a stranger's rating.

    Ported from the old merge_madden.py's find_duplicate_names()."""
    teams_by_name = {}
    for abbr in team_abbrs:
        filepath = f"nfl/data/{abbr.lower()}.json"
        if not os.path.exists(filepath):
            continue
        with open(filepath) as f:
            team_data = json.load(f)
        for players in team_data["depth_chart"].values():
            for player in players:
                key = normalize_madden(player["name"])
                teams_by_name.setdefault(key, set()).add(abbr)
    return {name for name, teams in teams_by_name.items() if len(teams) > 1}

def find_madden_player(name, team_madden_players, all_madden_players, allow_cross_team=True):
    """Ported from the old merge_madden.py's find_madden_player(). Applies
    NAME_ALIASES the same short-name substitution find_gsis() does (e.g.
    "Pat Surtain II" -> "Patrick Surtain II") -- without it, players whose
    OurLads name is a nickname/short form never match here even though
    find_gsis() resolves them fine via the same alias.

    Deliberately does NOT honor NAME_ALIASES' None ("forced no-match")
    entries the way find_gsis() does -- those exist because the GSIS
    crosswalk specifically has the wrong player under that name, which
    says nothing about whether Madden's own roster has the same problem.
    Confirmed at least one (Mike Jackson, CAR) already matches correctly
    in Madden despite being a forced GSIS no-match; honoring None here
    would have silently regressed him from matched to unmatched."""
    lookup_name = NAME_ALIASES.get(name)
    target = normalize_madden(lookup_name if lookup_name is not None else name)
    target_words = set(target.split())
    # Prefer a match within the player's own team first, to avoid colliding
    # with a different real person who happens to share the same name on
    # another team (e.g. two different "Justin Jefferson"s).
    for mp in team_madden_players:
        if mp["normalized"] == target:
            return mp
    for mp in team_madden_players:
        if target_words and target_words.issubset(set(mp["normalized"].split())):
            return mp
    if not allow_cross_team:
        return None
    # Fall back to a league-wide search (handles recent trades/signings not
    # yet reflected under the right team in the Madden export). Only safe
    # when the name isn't shared by a different real player elsewhere.
    for mp in all_madden_players:
        if mp["normalized"] == target:
            return mp
    for mp in all_madden_players:
        if target_words and target_words.issubset(set(mp["normalized"].split())):
            return mp
    return None

STAT_MAP = {
    'QB': {
        'YDS': 'PASS_YDS', 'TDs': 'PASS_TDS', 'TDS': 'PASS_TDS',
        'INTs': 'INT', 'INTS': 'INT',
        'SACKS': 'SACK', 'CMP': 'CMP', 'ATT': 'ATT',
        'RU YDS': 'RUSH_YDS', 'RU TDs': 'RUSH_TDS',
    },
    'RB': {
        'CAR': 'CAR', 'RU YDS': 'RUSH_YDS', 'RU TDs': 'RUSH_TDS',
        'REC': 'REC', 'RE YDS': 'REC_YDS', 'RE TDs': 'REC_TDS',
        'TGT': 'TGT', 'YDS': 'RUSH_YDS', 'YAC': 'YAC',
    },
    'WR': {
        'TGT': 'TGT', 'REC': 'REC', 'YDS': 'REC_YDS',
        'TDs': 'REC_TDS', 'TDS': 'REC_TDS',
        'YAC': 'YAC', 'RE YDS': 'REC_YDS',
    },
    'TE': {
        'TGT': 'TGT', 'REC': 'REC', 'YDS': 'REC_YDS',
        'TDs': 'REC_TDS', 'TDS': 'REC_TDS',
        'YAC': 'YAC', 'RE YDS': 'REC_YDS',
    },
    'EDGE': {
        'TKL': 'TKL', 'SACKS': 'SACK', 'SACK': 'SACK',
        'TFL': 'TFL', 'QB HIT': 'QB_HIT', 'PD': 'PBU',
        'INTs': 'INT',
    },
    'DI': {
        'TKL': 'TKL', 'SACKS': 'SACK', 'SACK': 'SACK',
        'TFL': 'TFL', 'QB HIT': 'QB_HIT',
    },
    'LB': {
        'TKL': 'TKL', 'SACKS': 'SACK', 'SACK': 'SACK',
        'TFL': 'TFL', 'QB HIT': 'QB_HIT',
        'PD': 'PBU', 'INTs': 'INT', 'INT': 'INT',
    },
    'CB': {
        'TKL': 'TKL', 'INTs': 'INT', 'INT': 'INT',
        'PD': 'PBU', 'TFL': 'TFL',
    },
    'S': {
        'TKL': 'TKL', 'INTs': 'INT', 'INT': 'INT',
        'PD': 'PBU', 'TFL': 'TFL',
        'SACKS': 'SACK', 'QB HIT': 'QB_HIT',
    },
    'OL': {},
}

def normalize_stats(stats, standard_pos):
    pos_map = STAT_MAP.get(standard_pos, {})
    normalized = {}
    for k, v in stats.items():
        canonical = pos_map.get(k) or pos_map.get(k.upper()) or k
        normalized[canonical] = v
    return normalized

# Spotrac position codes -> this project's standard_pos values.
# K/P/LS intentionally excluded — special teams aren't in our standard_pos
# set (stripped from the OurLads side via SKIP_POSITIONS too).
SPOTRAC_POS_MAP = {
    'QB': 'QB',
    'RB': 'RB', 'FB': 'RB',
    'WR': 'WR',
    'TE': 'TE',
    'T': 'OL', 'LT': 'OL', 'RT': 'OL', 'G': 'OL', 'C': 'OL', 'OL': 'OL',
    'ED': 'EDGE', 'DE': 'EDGE',
    'DL': 'DI', 'DT': 'DI',
    'LB': 'LB', 'OLB': 'LB', 'ILB': 'LB', 'WLB': 'LB',
    'CB': 'CB',
    'S': 'S', 'SS': 'S',
}

def load_spotrac_contracts():
    """Load Spotrac remaining-contract data and index it for fuzzy matching."""
    path = os.path.join('nfl', 'data', 'spotrac_contracts.json')
    if not os.path.exists(path):
        print("Warning: nfl/data/spotrac_contracts.json not found, skipping contract merge")
        return None
    try:
        with open(path, 'r') as f:
            records = json.load(f)
        df = pd.DataFrame(records)
        df['standard_pos'] = df['pos'].map(SPOTRAC_POS_MAP)
        df = df[df['standard_pos'].notna()].copy()
        df['row_idx'] = df.index
        print(f"Loaded Spotrac contracts: {len(df)} usable records (of {len(records)} total)")
        return df
    except Exception as e:
        print(f"Warning: could not load Spotrac contracts ({e}), skipping contract merge")
        return None

def find_spotrac_contract(name, standard_pos, team, spotrac_df):
    """Fuzzy-match a player against Spotrac contracts (no shared ID to join on)."""
    if spotrac_df is None:
        return None, None
    name_norm = normalize_for_matching(name)
    return _match_in_df(name_norm, standard_pos, team, spotrac_df,
                         pos_col='standard_pos', name_col='name_norm',
                         team_col='team', id_col='row_idx')

def load_gsis_crosswalk():
    """Pull dynastyprocess crosswalk and index by (normalized_name, position, team)."""
    url = "https://github.com/dynastyprocess/data/raw/master/files/db_playerids.csv"
    try:
        df = pd.read_csv(url)
        df = df[df['gsis_id'].notna()]
        df['team_norm'] = df['team'].apply(normalize_team)
        df['name_norm'] = df['name'].apply(
            lambda n: normalize_for_matching(normalize_name(str(n))))
        print(f"Loaded crosswalk: {len(df)} players with GSIS IDs")
        return df
    except Exception as e:
        print(f"Warning: could not load crosswalk ({e}), skipping GSIS matching")
        return None
    
def load_nflreadpy_gsis():
    """Pull GSIS IDs from nflreadpy roster data.

    Pulls SEASON and SEASON+1 together, not just SEASON. get_current_season()
    resolves to the last COMPLETED season until September, so anyone who
    entered the league after that snapshot (rookies, UDFAs, offseason
    signings) structurally can't be in it -- even though nflreadpy's own
    SEASON+1 roster pull is often already populated well before kickoff.
    Confirmed directly: of a sample of "no real candidate anywhere" players
    against the SEASON-only pool, ~90% resolved to an exact name+team match
    once SEASON+1 was included. Duplicate gsis_id rows across the two
    seasons for continuing players are harmless here -- they just match to
    the same real person twice."""
    try:
        import nflreadpy as nfl
        try:
            rosters = nfl.load_rosters([SEASON, SEASON + 1]).to_pandas()
        except Exception:
            # SEASON+1 may not have any roster data yet this early in the
            # offseason -- fall back to SEASON alone rather than losing
            # the whole load over it.
            rosters = nfl.load_rosters([SEASON]).to_pandas()
        rosters = rosters[rosters['gsis_id'].notna()].copy()
        rosters = rosters.rename(columns={'full_name': 'player_name'})
        rosters['name_norm'] = rosters['player_name'].apply(
            lambda n: normalize_for_matching(normalize_name(str(n))))
        rosters['team_norm'] = rosters['team'].apply(normalize_team)
        rosters['position'] = rosters['position'].fillna('')
        print(f"Loaded nflreadpy rosters: {len(rosters)} players")
        return rosters
    except Exception as e:
        print(f"Warning: nflreadpy roster load failed ({e})")
        return None

# import_snap_counts' own position labels -> this project's standard_pos.
# More granular than import_weekly_rosters' position column (which is only
# QB/RB/WR/TE/OL/DL/LB/DB/K/P/LS) — needed because that coarser rosters
# source has a 0% pfr_id fill rate for OL specifically (every other
# position is 75-99%), so OL can never get a pfr_id through it at all.
SNAP_POS_MAP = {
    'QB': 'QB',
    'RB': 'RB', 'HB': 'RB', 'FB': 'RB',
    'WR': 'WR',
    'TE': 'TE',
    'T': 'OL', 'G': 'OL', 'C': 'OL', 'OL': 'OL',
    'DE': 'EDGE',
    'DL': 'DI', 'DT': 'DI', 'NT': 'DI',
    'LB': 'LB',
    'CB': 'CB', 'DB': 'CB',
    'S': 'S', 'FS': 'S', 'SS': 'S',
}

def load_snap_shares():
    """Aggregate weekly snap counts to a per-player season average, keyed
    by pfr_player_id. Also returns a name+team crosswalk built from this
    same snap-count data (player/team/position/pfr_player_id) for the
    independent match path — since import_snap_counts has real pfr_id
    coverage for OL where import_weekly_rosters does not."""
    try:
        import nflreadpy as nfl
        snaps = nfl.load_snap_counts([SEASON]).to_pandas()

        # A player-week with 0 total snaps means they didn't play that week
        # (bye/inactive/injured) — drop those so the season average isn't
        # dragged down by weeks they weren't even on the field.
        total_snaps = (snaps['offense_snaps'].fillna(0)
                        + snaps['defense_snaps'].fillna(0)
                        + snaps['st_snaps'].fillna(0))
        played = snaps[total_snaps > 0]

        season_avg = played.groupby('pfr_player_id').agg(
            offense_pct=('offense_pct', 'mean'),
            defense_pct=('defense_pct', 'mean'),
        )
        print(f"Loaded snap counts: {len(snaps)} weekly rows -> "
              f"{len(season_avg)} players with a season average")

        crosswalk = snaps[snaps['pfr_player_id'].notna()][
            ['player', 'team', 'position', 'pfr_player_id']
        ].drop_duplicates(subset='pfr_player_id', keep='last').copy()
        crosswalk['standard_pos'] = crosswalk['position'].map(SNAP_POS_MAP)
        crosswalk = crosswalk[crosswalk['standard_pos'].notna()]
        crosswalk['name_norm'] = crosswalk['player'].apply(
            lambda n: normalize_for_matching(normalize_name(str(n))))
        crosswalk['team_norm'] = crosswalk['team'].apply(normalize_team)

        return season_avg, crosswalk
    except Exception as e:
        print(f"Warning: snap counts load failed ({e})")
        return None, None

# In find_gsis, add nflreadpy as fallback
# Our scheme-aware EDGE/DI split doesn't exist in either external source's
# own position taxonomy -- an exact-string position filter returns zero
# candidates for every EDGE/DI player regardless of name quality (confirmed:
# Micah Parsons, Aidan Hutchinson, Nick Bosa, and Joey Bosa are all in the
# crosswalk with valid GSIS IDs, all tagged position='DE'). Same pattern
# already used for the snap-count crosswalk's SNAP_POS_MAP above, just as
# an alias LIST here instead of a load-time column translation, because
# nflreadpy rosters' single 'DL' bucket can't be split 1:1 into EDGE vs DI
# the way a straight .map() column translation would need.
CROSSWALK_POS_ALIASES = {
    'EDGE': ['DE'],
    'DI': ['DT', 'DL'],  # crosswalk's own 'DL' is a tiny (~10-row) legacy bucket
}
ROSTERS_POS_ALIASES = {
    'EDGE': ['DL'],
    'DI': ['DL'],  # rosters can't distinguish EDGE from DI at all -- both
                   # share the one 'DL' bucket, so both search the same pool
    'OL': ['OL'],  # confirmed against real nflreadpy roster data --
                   # position is already the coarse 'OL' bucket here (T/G/C
                   # aren't split out), unlike Spotrac/snap-count's raw data
}

def find_gsis(name, standard_pos, team, crosswalk_df, roster_df=None):
    # OL not in fantasy crosswalk — skip entirely
    if standard_pos == 'OL':
        return None, None

    if crosswalk_df is None:
        return None, None

    # Apply alias BEFORE normalization
    lookup_name = NAME_ALIASES.get(name, name)
    if lookup_name is None:
        return None, None
    name_norm = normalize_for_matching(lookup_name)

    result = _match_in_df(name_norm, standard_pos, team, crosswalk_df,
                          pos_col='position', name_col='name_norm',
                          team_col='team_norm', id_col='gsis_id',
                          pos_aliases=CROSSWALK_POS_ALIASES)
    if result[0]:
        return result

    if roster_df is not None:
        result = _match_in_df(name_norm, standard_pos, team, roster_df,
                              pos_col='position', name_col='name_norm',
                              team_col='team_norm', id_col='gsis_id',
                              pos_aliases=ROSTERS_POS_ALIASES)
        if result[0]:
            return result

    return None, None

def find_roster_gsis_for_ol(name, team, roster_df):
    """Independent name+team fuzzy match against nflreadpy's own roster
    data to recover an OL player's real gsis_id directly -- not gated
    behind find_gsis()'s hard OL skip. nflreadpy's raw data has real
    gsis_ids for OL players; our own matching just never looks them up
    for this position. Returns a gsis_id (or None), meant to feed the
    SAME entry_year_by_gsis/college_by_gsis/birth_date_by_gsis dicts
    already used for every other position -- not a separate lookup
    path, and NOT written back into entry['gsis_id'] itself (that field
    should keep accurately reflecting that OL was never primarily
    GSIS-matched; this is a secondary, bio-only recovery)."""
    if roster_df is None:
        return None
    name_norm = normalize_for_matching(name)
    gid, _ = _match_in_df(name_norm, 'OL', team, roster_df,
                          pos_col='position', name_col='name_norm',
                          team_col='team_norm', id_col='gsis_id',
                          pos_aliases=ROSTERS_POS_ALIASES)
    return gid

def find_pfr_id(name, standard_pos, team, snap_crosswalk):
    """Independent name+team fuzzy match against the import_snap_counts
    crosswalk to find a pfr_id directly — not gated behind a GSIS match.
    OL is skipped entirely by find_gsis() (not in the fantasy-focused GSIS
    crosswalk) AND has 0% pfr_id coverage in import_weekly_rosters, so this
    snap-count-sourced crosswalk is the only path that can give OL players
    a pfr_id (and therefore a snap_pct) at all."""
    if snap_crosswalk is None:
        return None, None
    name_norm = normalize_for_matching(name)
    return _match_in_df(name_norm, standard_pos, team, snap_crosswalk,
                         pos_col='standard_pos', name_col='name_norm',
                         team_col='team_norm', id_col='pfr_player_id')

def find_espn_qbr(name, team, qbr_df):
    """Fuzzy-match a QB against ESPN's QBR leaderboard. No shared ID --
    ESPN athlete IDs have no crosswalk anywhere in this pipeline, same
    situation find_spotrac_contract() solves for Spotrac. qbr_df is
    QB-only by construction (ESPN's own leaderboard only lists QBs),
    so standard_pos is hardcoded, not passed in."""
    if qbr_df is None or len(qbr_df) == 0:
        return None, None
    name_norm = normalize_for_matching(name)
    return _match_in_df(name_norm, 'QB', team, qbr_df,
                         pos_col='standard_pos', name_col='name_norm',
                         team_col='team_norm', id_col='row_idx')

def _match_in_df(name_norm, standard_pos, team, df,
                 pos_col, name_col, team_col, id_col, pos_aliases=None):
    """Shared matching logic for any dataframe source.

    pos_aliases, if given, maps standard_pos -> the literal position
    value(s) this specific source's pos_col actually uses (see
    CROSSWALK_POS_ALIASES / ROSTERS_POS_ALIASES above). Sources that
    already pre-translate their own position column to our standard_pos
    values at load time (Spotrac, snap-counts) don't pass this and keep
    the plain exact-match behavior."""
    if df is None:
        return None, None

    pos_values = pos_aliases.get(standard_pos, [standard_pos]) if pos_aliases else [standard_pos]
    pos_df = df[df[pos_col].isin(pos_values)]
    if pos_df.empty:
        return None, None

    names = pos_df[name_col].tolist()
    result = process.extractOne(name_norm, names, scorer=fuzz.token_sort_ratio)
    if not result:
        return None, None

    score = result[1]
    if score >= 95:
        idx = names.index(result[0])
        return pos_df.iloc[idx][id_col], score

    if score >= 80:
        team_df = pos_df[pos_df[team_col] == team]
        if not team_df.empty:
            t_names = team_df[name_col].tolist()
            t_result = process.extractOne(
                name_norm, t_names, scorer=fuzz.token_sort_ratio)
            if t_result and t_result[1] >= 80:
                idx = t_names.index(t_result[0])
                return team_df.iloc[idx][id_col], t_result[1]

    return None, score

def build_master():
    crosswalk = load_gsis_crosswalk()
    rosters = load_nflreadpy_gsis()
    spotrac_df = load_spotrac_contracts()
    snap_shares, snap_crosswalk = load_snap_shares()

    madden_by_team = load_madden(os.path.join('nfl', 'data', 'madden.json'))
    madden_pos_ranks = build_madden_pos_ranks(madden_by_team)
    all_madden_players = [p for players in madden_by_team.values() for p in players]
    madden_duplicate_names = find_madden_duplicate_names(MADDEN_TEAM_MAP.values())

    master = {}
    low_confidence = []
    unmatched = []

    for filepath in sorted(glob.glob(os.path.join('nfl', 'data', '*.json'))):
        # Skip master file if it exists from a previous run
        if 'master' in filepath:
            continue
        with open(filepath, 'r') as f:
            team_data = json.load(f)

        if type(team_data) is list:
            team_data = team_data[0]  # Handle case where JSON is a list with one dict

        abbr = team_data.get('abbr', '')
        team_name = team_data.get('team', '')
        base_defense = team_data.get('base_defense', '')

        for ourlads_pos, players in team_data.get('depth_chart', {}).items():
            if ourlads_pos in SKIP_POSITIONS:
                continue

            for p in players:
                raw_name = p.get('name', '')
                if not raw_name:
                    continue

                canonical_name = normalize_name(raw_name)
                standard_pos = p.get('standard_pos', '')

                # GSIS lookup
                gsis_id, confidence = find_gsis(
                    canonical_name, standard_pos, abbr, crosswalk, rosters)

                # Use GSIS as key if found, else fall back to name-pos-team
                if gsis_id:
                    player_key = gsis_id
                else:
                    safe = re.sub(r'[^a-z0-9]', '-',
                                  normalize_for_matching(canonical_name))
                    safe = re.sub(r'-+', '-', safe).strip('-')
                    player_key = f"{safe}-{standard_pos.lower()}-{abbr.lower()}"

                # Duplicate handling: keep starter (lower depth)
                if player_key in master:
                    if p.get('depth', 99) >= master[player_key].get('depth', 99):
                        continue

                # Madden lookup — team-scoped first, cross-team fallback
                # only when this name isn't shared by another team's player
                # (find_madden_duplicate_names). Matched against raw_name,
                # same input the old merge_madden.py used, not canonical_name.
                madden_is_dup = normalize_madden(raw_name) in madden_duplicate_names
                mp = find_madden_player(raw_name, madden_by_team.get(abbr, []), all_madden_players,
                                         allow_cross_team=not madden_is_dup)
                madden_rank_info = madden_pos_ranks.get(mp["normalized"]) if mp else None

                entry = {
                    'player_id': player_key,
                    'gsis_id': gsis_id,
                    'match_confidence': confidence,
                    'canonical_name': canonical_name,
                    'ourlads_name': raw_name,
                    'team': abbr,
                    'team_name': team_name,
                    'base_defense': base_defense,
                    'ourlads_pos': ourlads_pos,
                    'standard_slot': p.get('standard_slot', ourlads_pos),
                    'standard_pos': standard_pos,
                    'depth': p.get('depth', 99),
                    'jersey': mp['jersey'] if mp else None,
                    # 'age' is added later, from nflreadpy's birth_date (see
                    # the draft_year/college pass below) -- Madden's roster
                    # page doesn't expose age at all.
                    'madden': mp['overall'] if mp else None,
                    'madden_rank': madden_rank_info['rank'] if madden_rank_info else None,
                    'madden_rank_total': madden_rank_info['total'] if madden_rank_info else None,
                    'madden_pos_label': madden_rank_info['pos'] if madden_rank_info else None,
                    'cap_number': p.get('cap_number'),
                    'attainment': p.get('attainment'),
                    'injured': p.get('injured', False),
                    'stats': normalize_stats(
                        p.get('stats', {}), standard_pos),
                    'stats_season': p.get('stats_season'),
                    'nflreadpy_name': None,
                    'match_source': 'gsis' if gsis_id else None,
                }
                master[player_key] = entry

                # Track match quality
                if gsis_id and confidence and confidence < 95:
                    low_confidence.append({
                        'canonical': canonical_name,
                        'gsis_id': gsis_id,
                        'confidence': confidence,
                        'pos': standard_pos,
                        'team': abbr,
                    })
                elif not gsis_id:
                    unmatched.append({
                        'name': canonical_name,
                        'pos': standard_pos,
                        'team': abbr,
                    })

    # Merge draft_year/college and recompute years_pro from nflreadpy roster
    # data — joined on the GSIS ID already resolved above, not a new
    # name-based match. nflreadpy has no distinct "draft year" column, so
    # entry_year (season first on an NFL roster) is used for both.
    entry_year_by_gsis = {}
    college_by_gsis = {}
    pfr_id_by_gsis = {}
    birth_date_by_gsis = {}
    if rosters is not None:
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

    draft_matched = 0
    age_matched = 0
    ol_bio_recovered = 0
    for entry in master.values():
        gid = entry.get('gsis_id')
        # OL never has a gsis_id from our own matching (find_gsis() skips
        # OL entirely) -- recover one via an independent name+team match
        # against nflreadpy's own roster data instead, so OL can reach
        # the exact same entry_year_by_gsis/college_by_gsis/
        # birth_date_by_gsis dicts every other position already uses.
        # This is a LOCAL variable only, used just for this bio lookup --
        # entry['gsis_id'] itself is untouched, so match_source/
        # match_confidence keep accurately reflecting that OL was never
        # primarily GSIS-matched.
        if gid is None and entry['standard_pos'] == 'OL':
            gid = find_roster_gsis_for_ol(entry['canonical_name'], entry['team'], rosters)
            if gid is not None:
                ol_bio_recovered += 1
        entry_year = entry_year_by_gsis.get(gid) if gid else None
        entry['draft_year'] = entry_year
        entry['college'] = college_by_gsis.get(gid) if gid else None
        # Clamp to 0 -- a player whose entry_year is the season that
        # technically hasn't "started" yet by get_current_season()'s
        # Sept 1 rule (e.g. drafted into next season, pipeline runs in
        # late August) is still a real rookie with 0 years of
        # experience, not a player with negative experience.
        entry['years_pro'] = max(0, SEASON - entry_year) if entry_year is not None else None
        if entry_year is not None:
            draft_matched += 1
        # age (real calendar age, from nflreadpy's birth_date) replaces what
        # used to come from Madden's own age field -- Madden's team-roster
        # page doesn't expose age (only ~2,000 individual player pages do,
        # not worth that crawl), but nflreadpy has 94.9% birth_date coverage
        # among GSIS-matched rosters, so this is the same GSIS join already
        # used for draft_year/college, not a new match pass.
        birth_date = birth_date_by_gsis.get(gid) if gid else None
        entry['age'] = calculate_age(birth_date)
        if entry['age'] is not None:
            age_matched += 1

    # Snap share — first pass: gsis_id -> pfr_id (from rosters, above) ->
    # season snap average. This is the ORIGINAL chain, and it structurally
    # can never reach OL: find_gsis() skips OL entirely (not in the
    # fantasy-focused GSIS crosswalk), so OL players never get a gsis_id
    # and always fell back to years_pro. Second pass below closes that gap
    # with an independent name+team fuzzy match against the roster data
    # directly (same precedence pattern already used for Spotrac matching),
    # not gated behind a GSIS match at all.
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

    ol_matched_before = sum(
        1 for key, entry in master.items()
        if entry['standard_pos'] == 'OL' and snap_pct_for(pfr_id_direct[key]) is not None
    )

    fuzzy_pfr_matched = 0
    for key, entry in master.items():
        if pfr_id_direct[key] is not None:
            continue
        pfr_id, _ = find_pfr_id(entry['canonical_name'], entry['standard_pos'], entry['team'], snap_crosswalk)
        if pfr_id:
            pfr_id_direct[key] = pfr_id
            fuzzy_pfr_matched += 1

    snap_matched = 0
    ol_matched_after = 0
    for key, entry in master.items():
        pct = snap_pct_for(pfr_id_direct[key])
        entry['snap_pct'] = pct
        if pct is not None:
            snap_matched += 1
            if entry['standard_pos'] == 'OL':
                ol_matched_after += 1

    # Merge Spotrac remaining-contract data — no shared ID with GSIS/OurLads,
    # so this gets its own fuzzy-match pass, reusing the same _match_in_df
    # logic (position match first, team as tiebreaker only) already
    # established for the GSIS crosswalk.
    contract_matched = 0
    contract_unmatched = []

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
                if cash_total is not None and years_remaining
                else None
            )
            contract_matched += 1
        else:
            entry['years_remaining'] = None
            entry['cash_total_remaining'] = None
            entry['cash_guaranteed_remaining'] = None
            entry['avg_annual_remaining'] = None
            contract_unmatched.append({
                'name': entry['canonical_name'],
                'pos': entry['standard_pos'],
                'team': entry['team'],
            })

    # Write master
    with open('nfl/data/players_master.json', 'w') as f:
        json.dump(master, f, indent=2)

    print(f"\nBuilt master: {len(master)} players")
    print(f"GSIS matched: {sum(1 for p in master.values() if p['gsis_id'])}")
    print(f"Madden matched: {sum(1 for p in master.values() if p['madden'] is not None)} / {len(master)}")
    print(f"Unmatched:    {len(unmatched)}")
    print(f"Low confidence (<95%): {len(low_confidence)}")
    print(f"draft_year/college matched (via GSIS): {draft_matched} / {len(master)}")
    print(f"age matched (via GSIS/nflreadpy birth_date): {age_matched} / {len(master)}")
    ol_total_bio = sum(1 for e in master.values() if e['standard_pos'] == 'OL')
    ol_age_matched = sum(1 for e in master.values() if e['standard_pos'] == 'OL' and e['age'] is not None)
    print(f"  OL bio recovered via independent name+team match: {ol_bio_recovered} / {ol_total_bio}")
    print(f"  OL age matched — after independent match: {ol_age_matched} / {ol_total_bio}")
    print(f"snap_pct matched (total): {snap_matched} / {len(master)}")
    print(f"  matched via independent name+team pfr_id fuzzy match: {fuzzy_pfr_matched}")
    ol_total = sum(1 for e in master.values() if e['standard_pos'] == 'OL')
    print(f"  OL snap_pct matched — before independent match: {ol_matched_before} / {ol_total}")
    print(f"  OL snap_pct matched — after independent match:  {ol_matched_after} / {ol_total}")

    print(f"\nUnmatched ({min(len(unmatched), 20)} shown):")
    for p in unmatched[:20]:
        print(f"  {p['name']:35} {p['pos']:6} {p['team']}")

    print(f"\nLow confidence ({min(len(low_confidence), 20)} shown):")
    for p in low_confidence[:20]:
        print(f"  {p['canonical']:35} {p['pos']:6} {p['team']}  ({p['confidence']}%)")

    print(f"\nSpotrac contracts matched: {contract_matched}")
    print(f"Spotrac contracts unmatched: {len(contract_unmatched)}")

    skill_pos_contracts = {'QB', 'WR', 'RB', 'TE'}
    skill_contract_unmatched = [p for p in contract_unmatched if p['pos'] in skill_pos_contracts]
    print(f"\nSkill position unmatched (Spotrac contracts): {len(skill_contract_unmatched)}")
    for p in skill_contract_unmatched[:30]:
        print(f"  {p['name']:35} {p['pos']:6} {p['team']}")

    # After loading crosswalk, check specific names
    check = ['Mike Jackson', 'Mitch Tinsley', 'Dax Hill', 
            'Vj Payne', 'Riq Woolen', 'Dru Phillips',
            'Matt Hibner', 'Cobie Durant', 'Joshua Metellus']
    for n in check:
        norm = normalize_for_matching(n)
        matches = crosswalk[crosswalk['name_norm'].str.contains(norm[:6], na=False)]
        if not matches.empty:
            print(f"\n{n} ({norm}):")
            print(matches[['name','position','team','gsis_id']].to_string())

    non_ol_unmatched = [p for p in unmatched if p['pos'] != 'OL']
    print(f"Non-OL unmatched: {len(non_ol_unmatched)}")
    print("\nNon-OL unmatched (first 30):")
    for p in non_ol_unmatched[:30]:
        print(f"  {p['name']:35} {p['pos']:6} {p['team']}")

    skill_pos = {'QB', 'WR', 'RB', 'TE'}
    skill_unmatched = [p for p in unmatched if p['pos'] in skill_pos]
    print(f"\nSkill position unmatched (QB/WR/RB/TE): {len(skill_unmatched)}")
    for p in skill_unmatched[:30]:
        print(f"  {p['name']:35} {p['pos']:6} {p['team']}")

if __name__ == '__main__':
    build_master()