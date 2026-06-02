import json
import glob
import re
import os

SKIP_POSITIONS = {'KR', 'PR', 'KO', 'PK', 'LS', 'K', 'P', 'PT', 'H'}

# Position-aware stat key normalization
STAT_MAP = {
    'QB': {
        'YDS': 'PASS_YDS', 'TDs': 'PASS_TDS', 'INTs': 'INT',
        'SACKS': 'SACK', 'CMP': 'CMP', 'ATT': 'ATT',
        'RU YDS': 'RUSH_YDS',
    },
    'RB': {
        'CAR': 'CAR', 'RU YDS': 'RUSH_YDS', 'RU TDs': 'RUSH_TDS',
        'REC': 'REC', 'RE YDS': 'REC_YDS', 'TGT': 'TGT',
        'YDS': 'RUSH_YDS',  # RB context = rushing
    },
    'WR': {
        'TGT': 'TGT', 'REC': 'REC', 'YDS': 'REC_YDS',
        'TDs': 'REC_TDS', 'YAC': 'YAC', 'RE YDS': 'REC_YDS',
    },
    'TE': {
        'TGT': 'TGT', 'REC': 'REC', 'YDS': 'REC_YDS',
        'TDs': 'REC_TDS', 'YAC': 'YAC', 'RE YDS': 'REC_YDS',
    },
    'EDGE': {
        'TKL': 'TKL', 'SACKS': 'SACK', 'SACK': 'SACK',
        'TFL': 'TFL', 'QB HIT': 'QB_HIT', 'PD': 'PBU',
    },
    'DI': {
        'TKL': 'TKL', 'SACKS': 'SACK', 'SACK': 'SACK',
        'TFL': 'TFL', 'QB HIT': 'QB_HIT',
    },
    'LB': {
        'TKL': 'TKL', 'SACKS': 'SACK', 'SACK': 'SACK',
        'TFL': 'TFL', 'QB HIT': 'QB_HIT', 'PD': 'PBU',
        'INTs': 'INT', 'INT': 'INT',
    },
    'CB': {
        'TKL': 'TKL', 'INTs': 'INT', 'INT': 'INT',
        'PD': 'PBU', 'PBU': 'PBU', 'TFL': 'TFL',
    },
    'S': {
        'TKL': 'TKL', 'INTs': 'INT', 'INT': 'INT',
        'PD': 'PBU', 'PBU': 'PBU', 'TFL': 'TFL',
        'SACKS': 'SACK', 'QB HIT': 'QB_HIT',
    },
    'OL': {},  # OL has no meaningful stats currently
}

def normalize_stats(stats, standard_pos):
    pos_map = STAT_MAP.get(standard_pos, {})
    normalized = {}
    for k, v in stats.items():
        canonical_key = pos_map.get(k) or pos_map.get(k.upper()) or k
        normalized[canonical_key] = v
    return normalized

def normalize_name(name):
    if not name:
        return name
    name = name.strip()
    
    # Fix AJ/BJ style BEFORE title case while still all-caps
    name = re.sub(r'\b([A-Z])([A-Z])\b', r'\1.\2.', name)
    
    # Now title case
    name = name.title()
    
    # Fix O'connell -> O'Connell style (letter after apostrophe)
    name = re.sub(r"'([a-z])", lambda m: "'" + m.group(1).upper(), name)
    
    # Fix hyphenated: Davis-gaither -> Davis-Gaither
    name = re.sub(r'-([a-z])', lambda m: '-' + m.group(1).upper(), name)
    
    # Fix suffixes — strip trailing period first to avoid doubles
    def fix_suffix(m):
        s = m.group(0).rstrip('.')
        replacements = {
            'Jr': 'Jr.', 'Sr': 'Sr.', 'Ii': 'II', 
            'Iii': 'III', 'Iv': 'IV', 'Vi': 'VI'
        }
        return replacements.get(s, s)
    
    name = re.sub(r'\b(Jr\.?|Sr\.?|Ii|Iii|Iv|Vi)\b', fix_suffix, name)
    
    return name

def make_player_id(name, standard_pos, team_abbr):
    """Stable ID: normalized name + position group + team."""
    clean = re.sub(r'[^a-z0-9]', '-', name.lower())
    clean = re.sub(r'-+', '-', clean).strip('-')
    return f"{clean}-{standard_pos.lower()}-{team_abbr.lower()}"

def build_master():
    master = {}
    data_dir = 'data'
    
    for filepath in glob.glob(os.path.join(data_dir, '*.json')):
        with open(filepath, 'r') as f:
            team_data = json.load(f)

        if type(team_data) is list:
            team_data = team_data[0]
        
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
                player_id = make_player_id(canonical_name, standard_pos, abbr)
                
                # If duplicate ID exists, keep higher depth (starter takes priority)
                if player_id in master:
                    existing_depth = master[player_id].get('depth', 99)
                    if p.get('depth', 99) >= existing_depth:
                        continue
                
                master[player_id] = {
                    'player_id': player_id,
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
                    'stats': normalize_stats(p.get('stats', {}), standard_pos),
                    'stats_season': p.get('stats_season'),
                    # Match tracking — filled by resolver
                    'nflreadpy_name': None,
                    'match_confidence': None,
                    'match_source': None,
                }
    
    # Write master
    with open('data/players_master.json', 'w') as f:
        json.dump(master, f, indent=2)
    
    print(f"Built master with {len(master)} players")
    
    # Print name normalization samples so you can sanity check
    samples = [(v['ourlads_name'], v['canonical_name']) 
               for v in master.values() 
               if v['ourlads_name'] != v['canonical_name']]
    print(f"\nName normalizations ({len(samples)} changes):")
    for raw, canon in sorted(samples)[:20]:
        print(f"  {raw!r:35} -> {canon!r}")

if __name__ == '__main__':
    build_master()