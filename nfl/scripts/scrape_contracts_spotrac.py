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
# robots.txt: `User-agent: *` sets `Crawl-delay: 5`; honored between the 32 per-team requests (~3 min).
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
        # the team cell holds the abbreviation twice (two spans) in the filtered tables: take the first
        team_raw = tds[2].get_text("|", strip=True).split("|")[0]

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


MIN_ROWS = 1500   # per-team pulls total ~1,900-2,000; fewer than this is a failed/blocked pull
MIN_TEAMS = 30
PAGE_CAP = 100    # the unfiltered page and any filtered view are cut at 100 rows


def fetch_team_slugs(html):
    """Team filter values (ari, atl, ...) read from the page's own <select name=team>."""
    soup = BeautifulSoup(html, "html.parser")
    sel = soup.find("select", attrs={"name": "team"})
    if sel is None:
        raise RuntimeError("team filter <select> not found")
    return [o.get("value") for o in sel.find_all("option") if o.get("value")]


def main():
    out_path = os.path.join("nfl", "data", "spotrac_contracts.json")
    print(f"Fetching {URL} ...")
    # Spotrac now serves only the first 100 rows of the league-wide table (it used to serve all
    # ~4,500), so pull one filtered table per team (a team has ~60 rows, under the cap).
    # Keep-old guard: any fetch/parse failure, a short table or too few teams leaves the existing
    # snapshot untouched and exits 0 (a Spotrac outage must never block the NFL job).
    try:
        resp = requests.get(URL, headers=HEADERS, timeout=30)
        if resp.status_code != 200:
            print(f"GUARD: Spotrac returned HTTP {resp.status_code}; keeping existing {out_path}")
            return
        slugs = fetch_team_slugs(resp.text)
        records, teams_ok = [], 0
        for slug in slugs:
            time.sleep(CRAWL_DELAY)
            r = requests.post(f"{URL}/_/team/{slug}", data="ajax=table", timeout=30,
                              headers={**HEADERS, "Content-Type": "application/x-www-form-urlencoded"})
            if r.status_code != 200:
                print(f"  {slug}: HTTP {r.status_code} -- skipped")
                continue
            rows = parse_table(r.text)
            if len(rows) >= PAGE_CAP:
                print(f"  WARNING {slug}: {len(rows)} rows hit the {PAGE_CAP}-row cap; rows beyond it are missing")
            records.extend(rows)
            teams_ok += 1
    except Exception as e:
        print(f"GUARD: Spotrac fetch/parse failed ({e}); keeping existing {out_path}")
        return
    seen, deduped = set(), []
    for rec in records:
        key = (rec["name_norm"], rec["team"], rec["pos"])
        if key not in seen:
            seen.add(key)
            deduped.append(rec)
    records = deduped
    print(f"Parsed {len(records)} contract records from {teams_ok} teams")
    if teams_ok < MIN_TEAMS or len(records) < MIN_ROWS:
        print(f"GUARD: {teams_ok} teams / {len(records)} rows (< {MIN_TEAMS} / {MIN_ROWS}); keeping existing {out_path}")
        return

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)
    print(f"Saved to {out_path}")


if __name__ == "__main__":
    main()
