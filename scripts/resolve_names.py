import json
import re
from rapidfuzz import fuzz, process

# pip install rapidfuzz

def normalize_for_matching(name):
    """Strip punctuation, lowercase, for fuzzy comparison only."""
    name = name.lower()
    name = re.sub(r'[^a-z0-9 ]', '', name)
    name = re.sub(r'\b(jr|sr|ii|iii|iv)\b', '', name)
    return re.sub(r'\s+', ' ', name).strip()

def resolve(master, external_players):
    """
    external_players: list of dicts with keys:
        - name: str
        - standard_pos: str  (use same pos groups: QB, WR, RB, etc.)
        - team: str (optional, used as secondary signal only)
        - source: str
        - [any extra fields to merge]
    
    Returns updated master with match info.
    """
    # Group master by standard_pos for position-first matching
    by_pos = {}
    for pid, player in master.items():
        pos = player['standard_pos']
        if pos not in by_pos:
            by_pos[pos] = []
        by_pos[pos].append((pid, normalize_for_matching(player['canonical_name'])))
    
    unmatched = []
    low_confidence = []
    
    for ext in external_players:
        ext_name_norm = normalize_for_matching(ext['name'])
        ext_pos = ext.get('standard_pos', '')
        ext_team = ext.get('team', '')
        
        # Step 1: try exact match within same position
        candidates = by_pos.get(ext_pos, [])
        exact = [(pid, name) for pid, name in candidates if name == ext_name_norm]
        
        if len(exact) == 1:
            pid = exact[0][0]
            master[pid].update({
                'nflreadpy_name': ext['name'],
                'match_confidence': 100,
                'match_source': ext.get('source', 'external'),
                **{k: v for k, v in ext.items() 
                   if k not in ('name', 'standard_pos', 'team', 'source')}
            })
            continue
        
        # Step 2: fuzzy match within same position
        if candidates:
            names = [name for _, name in candidates]
            result = process.extractOne(ext_name_norm, names, scorer=fuzz.token_sort_ratio)
            
            if result and result[1] >= 90:
                idx = names.index(result[0])
                pid = candidates[idx][0]
                master[pid].update({
                    'nflreadpy_name': ext['name'],
                    'match_confidence': result[1],
                    'match_source': ext.get('source', 'external'),
                    **{k: v for k, v in ext.items() 
                       if k not in ('name', 'standard_pos', 'team', 'source')}
                })
                if result[1] < 95:
                    low_confidence.append({
                        'external': ext['name'],
                        'matched_to': master[pid]['canonical_name'],
                        'confidence': result[1],
                        'pos': ext_pos,
                        'team': ext_team
                    })
                continue
            
            # Step 3: try team as tiebreaker for low confidence
            if result and result[1] >= 75 and ext_team:
                team_candidates = [(pid, name) for pid, name in candidates 
                                   if master[pid]['team'] == ext_team]
                if team_candidates:
                    t_names = [name for _, name in team_candidates]
                    t_result = process.extractOne(
                        ext_name_norm, t_names, scorer=fuzz.token_sort_ratio)
                    if t_result and t_result[1] >= 80:
                        idx = t_names.index(t_result[0])
                        pid = team_candidates[idx][0]
                        master[pid].update({
                            'nflreadpy_name': ext['name'],
                            'match_confidence': t_result[1],
                            'match_source': ext.get('source', 'external'),
                            **{k: v for k, v in ext.items() 
                               if k not in ('name', 'standard_pos', 'team', 'source')}
                        })
                        low_confidence.append({
                            'external': ext['name'],
                            'matched_to': master[pid]['canonical_name'],
                            'confidence': t_result[1],
                            'pos': ext_pos,
                            'team': ext_team,
                            'note': 'team tiebreaker used'
                        })
                        continue
        
        unmatched.append(ext)
    
    return master, unmatched, low_confidence


if __name__ == '__main__':
    # Load master
    with open('data/players_master.json', 'r') as f:
        master = json.load(f)
    
    # TODO: load your external source here
    # Example structure nflreadpy would produce:
    # external_players = [
    #     {'name': 'A.J. Brown', 'standard_pos': 'WR', 'team': 'PHI', 
    #      'source': 'nflreadpy', 'stats': {...}},
    # ]
    external_players = []  # plug in your source here
    
    master, unmatched, low_confidence = resolve(master, external_players)
    
    # Save updated master
    with open('data/players_master.json', 'w') as f:
        json.dump(master, f, indent=2)
    
    # Report
    print(f"\nUnmatched ({len(unmatched)}):")
    for p in unmatched:
        print(f"  {p['name']:30} {p.get('standard_pos','?'):6} {p.get('team','?')}")
    
    print(f"\nLow confidence matches ({len(low_confidence)}):")
    for m in low_confidence:
        note = m.get('note', '')
        print(f"  {m['external']:30} -> {m['matched_to']:30} ({m['confidence']}%) {note}")