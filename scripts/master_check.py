import json

with open('data/players_master.json') as f:
    master = json.load(f)

players = list(master.values())
print(f"Total players: {len(players)}")

# Check base_defense presence (relevant to the fix above)
has_base_defense = sum(1 for p in players if p.get('base_defense'))
print(f"Players with base_defense field: {has_base_defense}")

# Spot-check the Justin Jefferson collision case
jeffersons = [p for p in players if p.get('canonical_name', '').lower() == 'justin jefferson']
print(f"\nJustin Jefferson entries found: {len(jeffersons)}")
for p in jeffersons:
    print(f"  player_id={p.get('player_id')} team={p.get('team')} pos={p.get('standard_pos')} gsis={p.get('gsis_id')}")

# Check for any duplicate player_ids (would break the "no dupes on field" logic upstream)
ids = [p.get('player_id') for p in players]
dupes = set(i for i in ids if ids.count(i) > 1)
print(f"\nDuplicate player_ids: {len(dupes)}")
if dupes:
    print(list(dupes)[:10])

# Spot-check one team's full roster count (sanity check against known OurLads position counts)
team_check = 'IND'
team_players = [p for p in players if p.get('team') == team_check]
print(f"\n{team_check} roster count in master: {len(team_players)}")