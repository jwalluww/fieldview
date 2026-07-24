import json
import os

TEAMS = [
    "ARZ","ATL","BAL","BUF","CAR","CHI","CIN","CLE","DAL","DEN",
    "DET","GB","HOU","IND","JAX","KC","LAC","LAR","LV","MIA",
    "MIN","NE","NO","NYG","NYJ","PHI","PIT","SF","SEA","TB","TEN","WAS"
]

OFF_POSITIONS = {'QB','LWR','RWR','SWR','LT','LG','C','RG','RT','TE','RB','FB','HB','WR','FL','SE','OT','LOT','ROT','TB'}
ST_POSITIONS  = {'PT','PK','LS','H','KO','PR','KR','K','P'}

print(f"{'TEAM':<6} {'SCHEME':<12} {'DEF POSITIONS'}")
print("-" * 80)

for abbr in TEAMS:
    filepath = f"nfl/data/{abbr.lower()}.json"
    if not os.path.exists(filepath):
        print(f"{abbr:<6} FILE NOT FOUND")
        continue

    with open(filepath) as f:
        data = json.load(f)

    scheme = data.get("base_defense", "?")
    def_pos = [
        pos for pos in data["depth_chart"].keys()
        if pos not in OFF_POSITIONS and pos not in ST_POSITIONS
    ]
    print(f"{abbr:<6} {scheme:<12} {', '.join(def_pos)}")