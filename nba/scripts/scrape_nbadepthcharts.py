import csv
import io
import json
import os
import re
import sys
from datetime import date

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from name_utils import normalize_name, normalize_for_matching, NBA_NAME_ALIASES

# nbadepthcharts.com embeds this published Google Sheet in an iframe. The
# doc id below is the "pub" web id from that iframe src, not a real
# spreadsheetId -- xlsx/ods/gviz exports all 404/400 for this id (verified
# live), only the CSV export works. The pubhtml viewer is JS-rendered
# (Google's Waffle viewer), not static markup, so the sheet's color-coded
# status flags (Two-Way/Injured/Unsigned/New Team -- see the legend at
# nbadepthcharts.com) can't be read without a headless browser. Only
# Rookie survives into the CSV as plain text, via a "(pick#)" suffix on
# the name paired with "--"/"--" MPG/GP -- confirmed against real 2025/26
# draftees (AJ Dybantsa (1), Cameron Boozer (3), etc). Decided against
# adding a headless-browser dependency for the other 4 flags; revisit if
# Justin wants them badly enough to justify it.
DOC_ID = "2PACX-1vTi9up0zyRwtsmYQjpMgyUVvR0LMhiG76bZkhe4V7dw7pxf6wm2jww_fxzCijIXFN-ogn-CqUhjj2l0"
GID = "699250664"
CSV_URL = f"https://docs.google.com/spreadsheets/d/e/{DOC_ID}/pub?gid={GID}&single=true&output=csv"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

STATS_PATH = os.path.join("nba", "data", "nba_stats.json")
OUT_PATH = os.path.join("nba", "data", "nba_depth_chart.json")

# The sheet's own ALL-CAPS team headers -> standard abbreviation (same
# abbreviations used in scrape_2kratings.py's TEAM_SLUGS). Read directly
# off the fetched sheet, including its quirks ("CAVS" not "CAVALIERS",
# "TRAILBLAZERS" as one word for Portland) -- not slugified/guessed.
TEAM_HEADERS = {
    "ATLANTA HAWKS": "ATL",
    "BOSTON CELTICS": "BOS",
    "BROOKLYN NETS": "BKN",
    "CHARLOTTE HORNETS": "CHA",
    "CHICAGO BULLS": "CHI",
    "CLEVELAND CAVS": "CLE",
    "DALLAS MAVERICKS": "DAL",
    "DENVER NUGGETS": "DEN",
    "DETROIT PISTONS": "DET",
    "GOLDEN STATE WARRIORS": "GSW",
    "HOUSTON ROCKETS": "HOU",
    "INDIANA PACERS": "IND",
    "LOS ANGELES CLIPPERS": "LAC",
    "LOS ANGELES LAKERS": "LAL",
    "MEMPHIS GRIZZLIES": "MEM",
    "MIAMI HEAT": "MIA",
    "MILWAUKEE BUCKS": "MIL",
    "MINNESOTA TIMBERWOLVES": "MIN",
    "NEW ORLEANS PELICANS": "NOP",
    "NEW YORK KNICKS": "NYK",
    "OKLAHOMA CITY THUNDER": "OKC",
    "ORLANDO MAGIC": "ORL",
    "PHILADELPHIA 76ERS": "PHI",
    "PHOENIX SUNS": "PHX",
    "PORTLAND TRAILBLAZERS": "POR",
    "SACRAMENTO KINGS": "SAC",
    "SAN ANTONIO SPURS": "SAS",
    "TORONTO RAPTORS": "TOR",
    "UTAH JAZZ": "UTA",
    "WASHINGTON WIZARDS": "WAS",
}

# Each team block lays out 4 depth tiers as 4 fixed-width column groups
# (name, pos, mpg, gp) side by side: STARTERS, 2ND STRING, 3RD STRING,
# OTHER. Column ROLES are fixed by position, not by the sheet's own
# sub-header text -- confirmed by inspection that at least one team's
# sub-header row is corrupted at the source (Washington's reads "Player,
# Team, Update, Description..." instead of "STARTERS, 2ND STRING..."),
# while the underlying data columns are unaffected.
TIERS = [
    (0, 1),   # STARTERS
    (4, 2),   # 2ND STRING
    (8, 3),   # 3RD STRING
    (12, 4),  # OTHER
]

ROOKIE_PICK_RE = re.compile(r"^(.*\S)\s*\((\d+)\)\s*$")


def fetch_csv_rows():
    resp = requests.get(CSV_URL, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return list(csv.reader(io.StringIO(resp.text)))


def parse_cell(raw_name):
    """Split a name cell into (name, draft_pick). A trailing "(N)" is
    nbadepthcharts.com's own convention for an unsigned rookie (paired with
    "--"/"--" MPG/GP for that player) -- N is their draft pick number.
    "OPEN ..." marks a vacant roster slot, not a real player."""
    raw_name = (raw_name or "").strip()
    if not raw_name or raw_name.upper().startswith("OPEN") or not any(c.isalpha() for c in raw_name):
        return None, None
    m = ROOKIE_PICK_RE.match(raw_name)
    if m:
        return m.group(1), int(m.group(2))
    return raw_name, None


def parse_sheet(rows):
    """Walk the flat row list, splitting on the sheet's own ALL-CAPS team
    header rows, then reading each of the 4 depth tiers as an independent
    column group -- tiers don't all end on the same row (e.g. Memphis'
    OTHER column runs 4 rows past its other 3 tiers, overlapping rows that
    also hold that team's REMAINING FA / GONE notes in earlier columns)."""
    header_idxs = [i for i, row in enumerate(rows) if row and row[0].strip() in TEAM_HEADERS]
    records = []
    for n, start in enumerate(header_idxs):
        team = TEAM_HEADERS[rows[start][0].strip()]
        end = header_idxs[n + 1] if n + 1 < len(header_idxs) else len(rows)
        for row in rows[start + 2:end]:  # skip team header + sub-header rows
            for col, depth_rank in TIERS:
                if col >= len(row):
                    continue
                cell = row[col].strip()
                if not cell or cell.upper().startswith(("REMAINING FA", "GONE")):
                    continue
                name, draft_pick = parse_cell(cell)
                if name is None:
                    continue
                pos = row[col + 1].strip() if col + 1 < len(row) else ""
                records.append({
                    "sheet_name": name,
                    "team": team,
                    "position": pos or None,
                    "depth_rank": depth_rank,
                    "status_flags": ["rookie"] if draft_pick is not None else [],
                    "draft_pick": draft_pick,
                })
    return records


def load_nba_players():
    with open(STATS_PATH, encoding="utf-8") as f:
        stats = json.load(f)
    return list(stats.values())


def build_match_index(players):
    by_name = {}
    by_name_team = {}
    for p in players:
        key = normalize_for_matching(p["name"])
        by_name.setdefault(key, []).append(p)
        by_name_team[(key, p["team"])] = p
    return by_name, by_name_team


def find_match(record, by_name, by_name_team):
    lookup_name = NBA_NAME_ALIASES.get(record["sheet_name"], record["sheet_name"])
    if lookup_name is None:
        return None  # forced no-match (wrong player, don't guess)
    name_norm = normalize_for_matching(normalize_name(lookup_name))

    exact = by_name_team.get((name_norm, record["team"]))
    if exact:
        return exact

    candidates = by_name.get(name_norm, [])
    if len(candidates) == 1:
        return candidates[0]
    return None


def compute_last_changed(depth_chart):
    """The sheet has no reliable self-reported update date -- its
    displayed "Last updated" date is just today's date via JS, regardless
    of actual data freshness. Track staleness ourselves by diffing this
    run's parsed output against the previous run's."""
    today = date.today().isoformat()
    if not os.path.exists(OUT_PATH):
        return today
    try:
        with open(OUT_PATH, encoding="utf-8") as f:
            previous = json.load(f)
    except (json.JSONDecodeError, OSError):
        return today
    if previous.get("depth_chart", []) == depth_chart:
        return previous.get("last_changed", today)
    return today


def main():
    print(f"Fetching {CSV_URL} ...")
    rows = fetch_csv_rows()
    records = parse_sheet(rows)
    print(f"Parsed {len(records)} depth-chart entries across {len(TEAM_HEADERS)} teams")

    players = load_nba_players()
    by_name, by_name_team = build_match_index(players)
    print(f"Matching against {len(players)} players from nba_stats.json")

    matched = 0
    unmatched = []
    depth_chart = []
    for record in records:
        p = find_match(record, by_name, by_name_team)
        depth_chart.append({
            "player_id": p["player_id"] if p else None,
            "team": record["team"],
            "position": record["position"],
            "depth_rank": record["depth_rank"],
            "status_flags": record["status_flags"],
            "sheet_name": record["sheet_name"],
            "draft_pick": record["draft_pick"],
        })
        if p:
            matched += 1
        else:
            unmatched.append({
                "sheet_name": record["sheet_name"],
                "team": record["team"],
                "position": record["position"],
                "draft_pick": record["draft_pick"],
            })

    depth_chart.sort(key=lambda r: (r["team"], r["depth_rank"], r["position"] or "", r["sheet_name"]))

    last_changed = compute_last_changed(depth_chart)
    output = {
        "last_changed": last_changed,
        "depth_chart": depth_chart,
        "unmatched": unmatched,
    }

    os.makedirs(os.path.join("nba", "data"), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    pct = (matched / len(records) * 100) if records else 0
    print(f"\nMatched: {matched} / {len(records)} ({pct:.1f}%)")
    print(f"Unmatched: {len(unmatched)}")
    print(f"last_changed: {last_changed}")
    print(f"Saved to {OUT_PATH}")


if __name__ == "__main__":
    main()
