import requests
from bs4 import BeautifulSoup
import json
import os
import re

TEAMS = [
    {"name": "Arizona Cardinals",   "abbr": "ARZ"},
    {"name": "Atlanta Falcons",     "abbr": "ATL"},
    {"name": "Baltimore Ravens",    "abbr": "BAL"},
    {"name": "Buffalo Bills",       "abbr": "BUF"},
    {"name": "Carolina Panthers",   "abbr": "CAR"},
    {"name": "Chicago Bears",       "abbr": "CHI"},
    {"name": "Cincinnati Bengals",  "abbr": "CIN"},
    {"name": "Cleveland Browns",    "abbr": "CLE"},
    {"name": "Dallas Cowboys",      "abbr": "DAL"},
    {"name": "Denver Broncos",      "abbr": "DEN"},
    {"name": "Detroit Lions",       "abbr": "DET"},
    {"name": "Green Bay Packers",   "abbr": "GB"},
    {"name": "Houston Texans",      "abbr": "HOU"},
    {"name": "Indianapolis Colts",  "abbr": "IND"},
    {"name": "Jacksonville Jaguars","abbr": "JAX"},
    {"name": "Kansas City Chiefs",  "abbr": "KC"},
    {"name": "Las Vegas Raiders",   "abbr": "LV"},
    {"name": "Los Angeles Chargers","abbr": "LAC"},
    {"name": "Los Angeles Rams",    "abbr": "LAR"},
    {"name": "Miami Dolphins",      "abbr": "MIA"},
    {"name": "Minnesota Vikings",   "abbr": "MIN"},
    {"name": "New England Patriots","abbr": "NE"},
    {"name": "New Orleans Saints",  "abbr": "NO"},
    {"name": "New York Giants",     "abbr": "NYG"},
    {"name": "New York Jets",       "abbr": "NYJ"},
    {"name": "Philadelphia Eagles", "abbr": "PHI"},
    {"name": "Pittsburgh Steelers", "abbr": "PIT"},
    {"name": "San Francisco 49ers", "abbr": "SF"},
    {"name": "Seattle Seahawks",    "abbr": "SEA"},
    {"name": "Tampa Bay Buccaneers","abbr": "TB"},
    {"name": "Tennessee Titans",    "abbr": "TEN"},
    {"name": "Washington Commanders","abbr": "WAS"},
]

SKIP_POSITIONS = {'PUP', 'IR', 'NFI', 'PUP-R', 'EXE', 'RES', 'KR', 'PR', 'LS', 'K', 'P', 'KO', 'PK'}

# Standard slot mapping per scheme
# Each entry: ourlads_code -> (standard_slot, standard_pos)
SLOT_MAP_34 = {
    'LDE':  ('LE',     'DI'),
    'RDE':  ('RE',     'DI'),
    'NT':   ('NT',     'DI'),
    'DT':   ('RE',     'DI'),   # BAL/BUF style — DT is the RE side
    'LOLB': ('LOLB',  'EDGE'),
    'ROLB': ('ROLB',  'EDGE'),
    'RUSH': ('ROLB',  'EDGE'),  # SEA
    'WLB':  ('ILB_L', 'LB'),
    'MLB':  ('ILB_R', 'LB'),
    'LILB': ('ILB_L', 'LB'),
    'RILB': ('ILB_R', 'LB'),
    'LCB':  ('LCB',   'CB'),
    'RCB':  ('RCB',   'CB'),
    'SS':   ('SS',    'S'),
    'FS':   ('FS',    'S'),
    'NB':   ('NB',    None),    # resolved from Madden position
}

SLOT_MAP_43 = {
    'LDE':  ('LE',    'EDGE'),
    'RDE':  ('RE',    'EDGE'),
    'DE':   ('LE',    'EDGE'),
    'LDT':  ('LDT',   'DI'),
    'RDT':  ('RDT',   'DI'),
    'NT':   ('LDT',   'DI'),    # JAX
    'DT':   ('RDT',   'DI'),    # JAX
    'WLB':  ('WILL',  'LB'),
    'WILL': ('WILL',  'LB'),
    'MLB':  ('MIKE',  'LB'),
    'MIKE': ('MIKE',  'LB'),
    'SLB':  ('SAM',   'LB'),
    'SAM':  ('SAM',   'LB'),
    'LCB':  ('LCB',   'CB'),
    'RCB':  ('RCB',   'CB'),
    'SS':   ('SS',    'S'),
    'FS':   ('FS',    'S'),
    'NB':   ('NB',    None),    # resolved from Madden position
}

# For 3-4 teams using generic DE key — first player is LE, rest are LE depth
# DT key handles RE side separately
SLOT_MAP_34_DE_AS_LE = {
    'DE':   ('LE',    'DI'),
}

OFF_SLOT_MAP = {
    'QB':  ('QB',  'QB'),
    'LWR': ('LWR', 'WR'),
    'RWR': ('RWR', 'WR'),
    'SWR': ('SWR', 'WR'),
    'WR':  ('LWR', 'WR'),
    'FL':  ('SWR', 'WR'),
    'SE':  ('RWR', 'WR'),
    'LT':  ('LT',  'OL'),
    'LG':  ('LG',  'OL'),
    'C':   ('C',   'OL'),
    'RG':  ('RG',  'OL'),
    'RT':  ('RT',  'OL'),
    'OT':  ('LT',  'OL'),
    'LOT': ('LT',  'OL'),
    'ROT': ('RT',  'OL'),
    'TE':  ('TE',  'TE'),
    'RB':  ('RB',  'RB'),
    'HB':  ('RB',  'RB'),
    'TB':  ('RB',  'RB'),
    'FB':  ('FB',  'RB'),
}

def clean_name(name):
    # Remove OurLads suffix junk (draft year, trade info, etc.)
    name = re.sub(r'\s+\S*[\d/]\S*$', '', name).strip()
    # Flip Last, First to First Last
    if ',' in name:
        parts = name.split(',', 1)
        name = parts[1].strip() + ' ' + parts[0].strip()
    # Proper case, but preserve known suffixes
    suffixes = {'II', 'III', 'IV', 'V', 'Jr', 'Jr.', 'Sr', 'Sr.', 'DJ', 'AJ', 'CJ', 'TJ', 'OJ', 'BJ'}
    words = name.split()
    cased = []
    for word in words:
        if word.upper() in {s.upper() for s in suffixes}:
            # Find the canonical casing for this suffix
            for s in suffixes:
                if word.upper() == s.upper():
                    cased.append(s)
                    break
        else:
            cased.append(word.capitalize())
    return ' '.join(cased)

def enrich_positions(depth_chart, base_defense):
    """Add standard_slot and standard_pos to every player."""
    is_34 = '3-4' in (base_defense or '')
    slot_map = SLOT_MAP_34 if is_34 else SLOT_MAP_43

    for ourlads_pos, players in depth_chart.items():
        if ourlads_pos in SKIP_POSITIONS:
            continue

        # Offense
        if ourlads_pos in OFF_SLOT_MAP:
            standard_slot, standard_pos = OFF_SLOT_MAP[ourlads_pos]
            for p in players:
                p['standard_slot'] = standard_slot
                p['standard_pos'] = standard_pos
            continue

        # Defense — generic DE in 3-4 maps to LE
        if is_34 and ourlads_pos == 'DE':
            for p in players:
                p['standard_slot'] = 'LE'
                p['standard_pos'] = 'DI'
            continue

        # Defense — standard map
        if ourlads_pos in slot_map:
            standard_slot, standard_pos = slot_map[ourlads_pos]
            for p in players:
                p['standard_slot'] = standard_slot
                # NB: use Madden position if available, else default
                if standard_pos is None:
                    madden_pos = p.get('madden_pos_label', '')
                    if madden_pos in ('SS', 'FS', 'HB'):
                        p['standard_pos'] = 'S'
                    else:
                        p['standard_pos'] = 'CB'
                else:
                    p['standard_pos'] = standard_pos
        else:
            # Unknown position — leave unset for now
            for p in players:
                p.setdefault('standard_slot', ourlads_pos)
                p.setdefault('standard_pos', 'DEF')

def scrape_depth_chart(team):
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    print(f"Fetching {team['name']} depth chart from OurLads...")
    url = f"https://www.ourlads.com/nfldepthcharts/depthchart/{team['abbr']}"
    try:
        response = requests.get(url, headers=headers, timeout=10)
    except requests.exceptions.RequestException as e:
        print(f"ERROR: Network error — {e}")
        return None

    if response.status_code != 200:
        print(f"ERROR: Got status code {response.status_code}")
        return None

    soup = BeautifulSoup(response.text, "html.parser")

    # OurLads depth chart table
    base_tag = soup.find("b", string=lambda t: t and t.startswith("Base"))
    base_defense = base_tag.get_text(strip=True) if base_tag else "Base 4-3"
    print(f"  Defense scheme: {base_defense}")
    rows = soup.select("tr.row-dc-wht, tr.row-dc-grey")

    if not rows:
        print("ERROR: No depth chart rows found — OurLads may have changed their HTML structure")
        print("Tip: Open the URL in your browser and inspect the table element")
        return None

    depth_chart = {}

    last_position = None
    
    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 2:
            continue

        position = cols[0].get_text(strip=True)

        # Continuation row — no position label, extends previous position
        if not position and last_position:
            position = last_position
        elif not position:
            continue
        else:
            last_position = position

        players = []
        for col in cols[2::2]:
            player_tag = col.find("a")
            if player_tag:
                player_name = player_tag.get_text(strip=True)
                if player_name:
                    is_injured = 'lc_red' in player_tag.get('class', [])
                    raw_suffix = ''
                    suffix_match = re.search(r'\s+(\S*[\d/]\S*)$', player_name)
                    if suffix_match:
                        raw_suffix = suffix_match.group(1)
                    players.append({
                        "name": clean_name(player_name),
                        "depth": len(players) + 1,
                        "injured": is_injured,
                        "attainment": raw_suffix if raw_suffix else None
                    })

        if players:
            if position in depth_chart:
                # Extend existing position with continuation row players
                existing_count = len(depth_chart[position])
                for p in players:
                    p["depth"] = existing_count + p["depth"]
                depth_chart[position].extend(players)
            else:
                depth_chart[position] = players

    # Remove non-position roster designations
    for skip in list(depth_chart.keys()):
        if skip in SKIP_POSITIONS:
            del depth_chart[skip]

    enrich_positions(depth_chart, base_defense)

    return {
        "team": team["name"],
        "abbr": team["abbr"],
        "source": "OurLads",
        "base_defense": base_defense,
        "depth_chart": depth_chart
    }


def save_json(data, abbr):
    os.makedirs("data", exist_ok=True)
    filepath = f"data/{abbr.lower()}.json"
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Saved to {filepath}")


if __name__ == "__main__":
    import time
    for team in TEAMS:
        result = scrape_depth_chart(team)
        if result:
            save_json(result, team["abbr"])
            print(f"Success: {team['name']} — {len(result['depth_chart'])} positions\n")
        else:
            print(f"FAILED: {team['name']}\n")
        time.sleep(5)  # be polite to OurLads, don't hammer them