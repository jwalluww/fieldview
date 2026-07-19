import json
import glob
import re
import os
import pandas as pd
from rapidfuzz import fuzz, process

# Known name mismatches between OurLads and crosswalk
# Format: 'ourlads_canonical_name': 'crosswalk_name'
NAME_ALIASES = {
    'Kam Curl': 'Kamren Curl',
    'Juju Brents': 'Julius Brents',
    'Chig Okonkwo': 'Chigoziem Okonkwo',
    'Pat Surtain II': 'Patrick Surtain II',
    'Cam Bynum': 'Cameron Bynum',
    'C.J. Gardner-Johnson': 'C.J. Gardner-Johnson',  # check exact crosswalk spelling
    'Cj Stroud': 'C.J. Stroud',
    'Aj Brown': 'A.J. Brown',
    'Tj Hockenson': 'T.J. Hockenson',
    'Tj Watt': 'T.J. Watt',
    'Dj Moore': 'D.J. Moore',
    'Dj Reader': 'D.J. Reader',
    'Kj Hamler': 'K.J. Hamler',
    'Kj Osborn': 'K.J. Osborn',
    'Gus Edwards': 'Kenneth Edwards',  # common nickname mismatches
    'Riq Woolen': 'Tariq Woolen',
    'Dru Phillips': 'Andru Phillips',
    'Cobie Durant': 'Decobie Durant',
    'Vj Payne': 'V.J. Payne',
    # Forced no-matches (wrong players in crosswalk)
    'Matt Hibner': None,
    'Mike Jackson': None,
    'Joshua Metellus': None,
}

SKIP_POSITIONS = {'KR', 'PR', 'KO', 'PK', 'LS', 'K', 'P', 'PT', 'H'}

TEAM_ABB_MAP = {
    'ARI': 'ARZ', 'KCC': 'KC',  'LVR': 'LV',
    'TBB': 'TB',  'SFO': 'SF',  'GNB': 'GB',
    'NOR': 'NO',  'NWE': 'NE',
}

def normalize_team(abbr):
    return TEAM_ABB_MAP.get(abbr, abbr)

def normalize_name(name):
    if not name:
        return name
    name = name.strip()
    # Fix true initials (AJ, BJ, CJ) BEFORE title case
    # But NOT roman numerals (II, III) — exclude repeated same letter
    name = re.sub(r'\b([A-Z])([A-Z])\b',
                  lambda m: m.group(1) + '.' + m.group(2) + '.'
                  if m.group(1) != m.group(2) else m.group(0), name)
    name = name.title()
    # Fix apostrophe casing
    name = re.sub(r"'([a-z])", lambda m: "'" + m.group(1).upper(), name)
    # Fix hyphenated
    name = re.sub(r'-([a-z])', lambda m: '-' + m.group(1).upper(), name)
    # Fix suffixes — must run AFTER title case
    name = re.sub(r'\b(Jr|Sr)\.', r'\1', name)
    name = re.sub(r'\b(Jr|Sr)\b', r'\1.', name)
    name = re.sub(r'\b(Ii|Iii|Iv|Vi)\b',
              lambda m: {'Ii': 'II', 'Iii': 'III', 'Iv': 'IV', 'Vi': 'VI'}[m.group(0)], name)
    return name

def normalize_for_matching(name):
    """Strip everything except letters, lowercase, no spaces."""
    if not name:
        return ''
    name = name.lower()
    # Remove suffixes entirely before stripping
    name = re.sub(r'\b(jr|sr|ii|iii|iv|vi|v)\b', '', name)
    # Strip everything that isn't a letter
    name = re.sub(r'[^a-z]', '', name)
    return name

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
    """Pull GSIS IDs from nflreadpy play-by-play data."""
    try:
        import nfl_data_py as nfl
        print("Available nfl_data_py functions:", [f for f in dir(nfl) if not f.startswith('_')])
        rosters = nfl.import_weekly_rosters(years=[2025])
        rosters = rosters[rosters['player_id'].notna()].copy()
        rosters = rosters.rename(columns={'player_id': 'gsis_id', 'player_name': 'player_name'})
        rosters = rosters[rosters['gsis_id'].notna()]
        rosters['name_norm'] = rosters['player_name'].apply(
            lambda n: normalize_for_matching(normalize_name(str(n))))
        rosters['team_norm'] = rosters['team'].apply(normalize_team)
        rosters['position'] = rosters['position'].fillna('')
        print(f"Loaded nflreadpy rosters: {len(rosters)} players")
        return rosters
    except Exception as e:
        print(f"Warning: nflreadpy roster load failed ({e})")
        return None

# In find_gsis, add nflreadpy as fallback
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
                          team_col='team_norm', id_col='gsis_id')
    if result[0]:
        return result

    if roster_df is not None:
        result = _match_in_df(name_norm, standard_pos, team, roster_df,
                              pos_col='position', name_col='name_norm',
                              team_col='team_norm', id_col='gsis_id')
        if result[0]:
            return result

    return None, None

def _match_in_df(name_norm, standard_pos, team, df, 
                 pos_col, name_col, team_col, id_col):
    """Shared matching logic for any dataframe source."""
    if df is None:
        return None, None

    pos_df = df[df[pos_col] == standard_pos]
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
    
    master = {}
    low_confidence = []
    unmatched = []

    for filepath in sorted(glob.glob(os.path.join('data', '*.json'))):
        # Skip master file if it exists from a previous run
        if 'master' in filepath:
            continue
        with open(filepath, 'r') as f:
            team_data = json.load(f)

        if type(team_data) is list:
            team_data = team_data[0]  # Handle case where JSON is a list with one dict

        abbr = team_data.get('abbr', '')
        team_name = team_data.get('team', '')

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

                entry = {
                    'player_id': player_key,
                    'gsis_id': gsis_id,
                    'match_confidence': confidence,
                    'canonical_name': canonical_name,
                    'ourlads_name': raw_name,
                    'team': abbr,
                    'team_name': team_name,
                    'ourlads_pos': ourlads_pos,
                    'standard_pos': standard_pos,
                    'depth': p.get('depth', 99),
                    'jersey': p.get('jersey'),
                    'age': p.get('age'),
                    'years_pro': p.get('years_pro'),
                    'madden': p.get('madden'),
                    'madden_rank': p.get('madden_rank'),
                    'madden_rank_total': p.get('madden_rank_total'),
                    'madden_pos_label': p.get('madden_pos_label'),
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

    # Write master
    with open('data/players_master.json', 'w') as f:
        json.dump(master, f, indent=2)

    print(f"\nBuilt master: {len(master)} players")
    print(f"GSIS matched: {sum(1 for p in master.values() if p['gsis_id'])}")
    print(f"Unmatched:    {len(unmatched)}")
    print(f"Low confidence (<95%): {len(low_confidence)}")

    print(f"\nUnmatched ({min(len(unmatched), 20)} shown):")
    for p in unmatched[:20]:
        print(f"  {p['name']:35} {p['pos']:6} {p['team']}")

    print(f"\nLow confidence ({min(len(low_confidence), 20)} shown):")
    for p in low_confidence[:20]:
        print(f"  {p['canonical']:35} {p['pos']:6} {p['team']}  ({p['confidence']}%)")

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