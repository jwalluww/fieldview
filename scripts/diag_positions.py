import json

TEAMS = ['ind', 'sea', 'cle', 'cin']

for team in TEAMS:
    with open(f'data/{team}.json') as f:
        data = json.load(f)
    if isinstance(data, list):
        data = data[0]

    print(f"\n=== {team.upper()} ===")
    print(f"base_defense: {data.get('base_defense')}")

    for player in data.get('players', []):
        pos = player.get('standard_pos')
        if pos == 'LB':
            print(f"  {player.get('name'):30} "
                  f"ourlads_slot={player.get('standard_slot')!r:15} "
                  f"depth={player.get('depth')}")