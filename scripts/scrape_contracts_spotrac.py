import json
import os
import re
import sys
import time

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_master import normalize_name, normalize_for_matching, normalize_team

URL = "https://www.spotrac.com/nfl/contracts/remaining"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
# robots.txt: `User-agent: *` sets `Crawl-delay: 5`. The whole league is on
# this one page (confirmed 3663 rows, no pagination), so a single request
# normally never needs it — kept only in case this script grows a retry
# or a second request later.
CRAWL_DELAY = 5


def fetch_page():
    resp = requests.get(URL, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.text


def parse_money(text):
    text = (text or "").strip()
    if not text:
        return None
    cleaned = re.sub(r"[$,]", "", text)
    try:
        return int(cleaned)
    except ValueError:
        return None


def parse_pct(text):
    text = (text or "").strip().rstrip("%")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_int(text):
    text = (text or "").strip()
    return int(text) if text.isdigit() else None


def parse_table(html):
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id="table", class_="table")
    if table is None:
        table = soup.select_one("table.dataTable.rounded-top")
    if table is None:
        raise RuntimeError("Could not find the contracts table on the page")

    tbody = table.find("tbody")
    records = []
    for row in tbody.find_all("tr"):
        tds = row.find_all("td")
        if len(tds) < 8:
            continue

        name_tag = tds[0].find("a")
        raw_name = name_tag.get_text(strip=True) if name_tag else tds[0].get_text(strip=True)
        if not raw_name:
            continue

        canonical_name = normalize_name(raw_name)
        team_raw = tds[2].get_text(strip=True)

        records.append({
            "name": canonical_name,
            "spotrac_name": raw_name,
            "name_norm": normalize_for_matching(canonical_name),
            "pos": tds[1].get_text(strip=True),
            "team": normalize_team(team_raw),
            "age": parse_int(tds[3].get_text(strip=True)),
            "length_remaining": parse_int(tds[4].get_text(strip=True)),
            "cash_total_remaining": parse_money(tds[5].get_text(strip=True)),
            "cash_guaranteed_remaining": parse_money(tds[6].get_text(strip=True)),
            "pct_guaranteed_remaining": parse_pct(tds[7].get_text(strip=True)),
        })
    return records


def main():
    print(f"Fetching {URL} ...")
    html = fetch_page()

    records = parse_table(html)
    print(f"Parsed {len(records)} contract records")

    out_path = os.path.join("data", "spotrac_contracts.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)
    print(f"Saved to {out_path}")


if __name__ == "__main__":
    main()
