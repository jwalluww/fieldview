import requests
import re
import json

# Adjust this URL if scrape_depth.py uses a different pattern for CLE's OurLads page
URL = "https://www.ourlads.com/nfldepthcharts/depthchart/CLE"

resp = requests.get(URL, headers={"User-Agent": "Mozilla/5.0"})
html = resp.text

# Check for the two players in the raw page text
names_to_check = ["Shedeur Sanders", "Mason Graham"]

print("=== Raw OurLads page check ===")
for name in names_to_check:
    idx = html.find(name)
    if idx == -1:
        print(f"{name}: NOT FOUND on page (name format may differ, e.g. last-first)")
        continue
    # print a chunk of surrounding HTML so we can eyeball the experience/rookie field
    snippet = html[idx-50:idx+300]
    snippet = re.sub(r'\s+', ' ', snippet)
    print(f"\n{name}:")
    print(f"  ...{snippet}...")

# Compare against local JSON
print("\n=== Local nfl/data/cle.json check ===")
with open("nfl/data/cle.json") as f:
    data = json.load(f)
if isinstance(data, list):
    data = data[0]

for player in data.get("players", []):
    if player.get("name") in names_to_check:
        print(f"{player.get('name')}: years_pro={player.get('years_pro')!r}, "
              f"attainment={player.get('attainment')!r}")