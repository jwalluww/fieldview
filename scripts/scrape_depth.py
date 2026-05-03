import requests
from bs4 import BeautifulSoup
import json
import os
import re

TEAM = {
    "name": "Buffalo Bills",
    "abbr": "BUF",
    "ourlads_url": "https://www.ourlads.com/nfldepthcharts/depthchart/BUF"
}

def clean_name(name):
    name = re.sub(r'\s+\S*[\d/]\S*$', '', name).strip()
    if ',' in name:
        parts = name.split(',', 1)
        name = parts[1].strip() + ' ' + parts[0].strip()
    return name

def scrape_depth_chart(team):
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    print(f"Fetching {team['name']} depth chart from OurLads...")
    response = requests.get(team["ourlads_url"], headers=headers)

    if response.status_code != 200:
        print(f"ERROR: Got status code {response.status_code}")
        return None

    soup = BeautifulSoup(response.text, "html.parser")

    # OurLads depth chart table
    rows = soup.select("tr.row-dc-wht, tr.row-dc-grey")

    if not rows:
        print("ERROR: No depth chart rows found — OurLads may have changed their HTML structure")
        print("Tip: Open the URL in your browser and inspect the table element")
        return None

    depth_chart = {}

    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 2:
            continue

        position = cols[0].get_text(strip=True)
        if not position:
            continue

        players = []
        for col in cols[2::2]:  # start at index 2, skip every other td
            player_tag = col.find("a")
            if player_tag:
                player_name = player_tag.get_text(strip=True)
                if player_name:
                    players.append({
                        "name": clean_name(player_name),
                        "depth": len(players) + 1
                    })

        if players:
            depth_chart[position] = players

    return {
        "team": team["name"],
        "abbr": team["abbr"],
        "source": "OurLads",
        "depth_chart": depth_chart
    }


def save_json(data, abbr):
    os.makedirs("data", exist_ok=True)
    filepath = f"data/{abbr.lower()}.json"
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Saved to {filepath}")


if __name__ == "__main__":
    result = scrape_depth_chart(TEAM)
    if result:
        save_json(result, TEAM["abbr"])
        print(f"\nSuccess! Found {len(result['depth_chart'])} positions")
        print("\nPositions found:")
        for pos, players in result["depth_chart"].items():
            starter = players[0]["name"] if players else "?"
            print(f"  {pos:<6} — {starter} + {len(players)-1} backup(s)")