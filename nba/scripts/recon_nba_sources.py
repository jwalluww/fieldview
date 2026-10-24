"""NBA stats-source recon probe (research only -- writes nothing to the repo).

Hits each candidate source once and logs status, latency, row counts and field
names, then runs the freshness check (2026 rookies + players traded since August,
names taken from nba_ratings_2k.json) and the id-crosswalk coverage against
nba_stats.json. Meant to run from a GitHub Actions runner (nba-recon.yml) but
works locally too. Never prints secrets (BALLDONTLIE_API_KEY is only sent as a
header and its presence is reported as yes/no).
"""
import json
import os
import re
import sys
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
HEADERS = {
    "User-Agent": UA,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
}
HTML_HEADERS = dict(HEADERS, Accept="text/html,application/xhtml+xml,*/*;q=0.8")

ESPN_SITE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
ESPN_BYATHLETE = ("https://site.web.api.espn.com/apis/common/v3/sports/basketball/nba/"
                  "statistics/byathlete?region=us&lang=en&contentorigin=espn&isqualified=false"
                  "&limit=500&sort=offensive.avgPoints%3Adesc&seasontype=2")
ESPN_CORE = "https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba"
BBR = "https://www.basketball-reference.com/leagues"

# Freshness sample: 5 rookies and 3 veterans from nba_ratings_2k.json's
# `unmatched` array (team = the 2K27 team). Veterans were chosen as players on a
# team that is not an obvious long-term home; the report shows each source's team
# next to 2K's so a post-August move is visible rather than assumed.
ROOKIES = {"Kingston Flemings": "ATL", "Cameron Boozer": "MEM", "AJ Dybantsa": "WAS",
           "Darryn Peterson": "UTA", "Caleb Wilson": "CHI"}
VETERANS = {"Ben Simmons": "SAC", "Mario Hezonja": "CLE", "Georges Niang": "GSW"}

ESPN_ABBR_FIX = {"GS": "GSW", "NO": "NOP", "NY": "NYK", "SA": "SAS", "UTAH": "UTA",
                 "WSH": "WAS", "PHO": "PHX", "BRK": "BKN", "CHO": "CHA", "BKN": "BKN"}

results = []


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b\.?", "", s.lower())
    return re.sub(r"[^a-z]", "", s)


def get(label, url, headers=HEADERS, **kw):
    t = time.time()
    try:
        r = requests.get(url, headers=headers, timeout=40, **kw)
        ms = int((time.time() - t) * 1000)
        print(f"[{label}] {r.status_code} {ms}ms {len(r.content)}B {url[:110]}", flush=True)
        results.append({"label": label, "status": r.status_code, "ms": ms, "bytes": len(r.content)})
        return r
    except Exception as e:
        print(f"[{label}] ERROR {type(e).__name__}: {str(e)[:120]} {url[:110]}", flush=True)
        results.append({"label": label, "status": "ERR", "error": type(e).__name__})
        return None


def section(t):
    print(f"\n===== {t} =====", flush=True)


def probe_espn():
    section("ESPN")
    teams = {}
    r = get("espn teams", f"{ESPN_SITE}/teams")
    if not r or r.status_code != 200:
        return {}
    for t in r.json()["sports"][0]["leagues"][0]["teams"]:
        teams[t["team"]["id"]] = ESPN_ABBR_FIX.get(t["team"]["abbreviation"], t["team"]["abbreviation"])
    print("teams:", len(teams))
    roster = {}  # norm name -> (team, id, display, jersey)
    n = 0
    fields = None
    for tid, abbr in teams.items():
        r = get("espn roster", f"{ESPN_SITE}/teams/{tid}/roster")
        if not r or r.status_code != 200:
            continue
        j = r.json()
        if fields is None:
            print("season:", j.get("season"))
        for a in j.get("athletes", []):
            fields = fields or sorted(a.keys())
            roster[norm(a["displayName"])] = (abbr, a["id"], a["displayName"], a.get("jersey"))
            n += 1
        time.sleep(0.2)
    print("roster rows:", n, "athlete fields:", fields)
    stats = {}
    for season in ("2027", "2026"):
        page, rows = 1, []
        while True:
            r = get(f"espn byathlete {season} p{page}", f"{ESPN_BYATHLETE}&season={season}&page={page}")
            if not r or r.status_code != 200:
                break
            j = r.json()
            rows += j["athletes"]
            if page >= j["pagination"]["pages"]:
                break
            page += 1
        if rows:
            cats = {c["name"]: c["names"] for c in j["categories"]}
            print(f"byathlete {season}: {len(rows)} players; served season "
                  f"{j.get('requestedSeason', {}).get('displayName')}; categories {cats}")
            stats[season] = rows
    # per-athlete core stats: this is where PER/VORP/TS%/USG/GS live
    sample = None
    for season in ("2027", "2026"):
        r = get(f"espn core athlete stats {season}", f"{ESPN_CORE}/seasons/{season}/types/2/athletes/4065733/statistics/0")
        if r and r.status_code == 200:
            cats = r.json()["splits"]["categories"]
            names = {c["name"]: [s["name"] for s in c["stats"]] for c in cats}
            want = ["gamesPlayed", "gamesStarted", "avgMinutes", "PER", "VORP", "trueShootingPct",
                    "usageRate", "reboundRate", "assistRatio", "turnoverRatio"]
            have = {w for ns in names.values() for w in ns}
            print(f"core stats {season}: advanced present {[w for w in want if w in have]}, "
                  f"missing {[w for w in want if w not in have]}; BPM present: {'BPM' in have}")
            sample = sample or season
    r = get("espn core athletes list", f"{ESPN_CORE}/seasons/2027/athletes?limit=1000")
    if r and r.status_code == 200:
        print("core athlete refs:", r.json().get("count"))
    return {"roster": roster, "stats": stats}


def probe_bbr():
    section("Basketball-Reference")
    out = {}
    for pg, tid in (("per_game", "per_game_stats"), ("advanced", "advanced")):
        r = get(f"bbr {pg}", f"{BBR}/NBA_2027_{pg}.html", HTML_HEADERS)
        time.sleep(4)  # crawl-delay 3, limit 20/min
        if not r or r.status_code != 200:
            continue
        t = BeautifulSoup(r.text, "html.parser").find("table", id=tid)
        if not t:
            print("table not found", tid)
            continue
        rows = []
        for tr in t.find("tbody").find_all("tr"):
            if "thead" in (tr.get("class") or []):
                continue
            row = {td.get("data-stat"): td.get_text(strip=True) for td in tr.find_all(["td", "th"])}
            c = tr.find("td", {"data-stat": "name_display"})
            row["bbr_id"] = c.get("data-append-csv") if c else None
            rows.append(row)
        print(f"{pg}: {len(rows)} rows; fields {sorted(rows[0].keys())}")
        out[pg] = rows
    # fallback season availability
    r = get("bbr 2026 advanced", f"{BBR}/NBA_2026_advanced.html", HTML_HEADERS)
    return out


def probe_cdn():
    section("cdn.nba.com")
    for lab, u in (("cdn schedule", "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json"),
                   ("cdn scoreboard", "https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json"),
                   ("cdn playerindex", "https://cdn.nba.com/static/json/staticData/playerIndex.json")):
        h = dict(HEADERS, Referer="https://www.nba.com/", Origin="https://www.nba.com")
        r = get(lab, u, h)
        if r is not None and r.status_code != 200:
            print("  body:", r.text[:100].replace("\n", " "))


def probe_balldontlie():
    section("balldontlie")
    r = get("bdl keyless players", "https://api.balldontlie.io/v1/players?per_page=1")
    key = os.environ.get("BALLDONTLIE_API_KEY")
    print("key present:", bool(key))
    if key:
        h = dict(HEADERS, Authorization=key)
        r = get("bdl keyed players", "https://api.balldontlie.io/v1/players?per_page=100", h)
        if r and r.status_code == 200:
            print("fields:", sorted(r.json()["data"][0].keys()))


def probe_stats_nba_control():
    section("stats.nba.com control (expected to fail from a runner)")
    h = {"User-Agent": UA, "Referer": "https://www.nba.com/", "Origin": "https://www.nba.com",
         "Accept": "application/json, text/plain, */*"}
    try:
        t = time.time()
        r = requests.get("https://stats.nba.com/stats/commonallplayers?LeagueID=00&Season=2026-27&IsOnlyCurrentSeason=1",
                         headers=h, timeout=20)
        print(f"[stats.nba.com] {r.status_code} {int((time.time()-t)*1000)}ms")
    except Exception as e:
        print(f"[stats.nba.com] ERROR {type(e).__name__} (blocked/timeout as documented)")


def freshness(espn, bbr):
    section("Freshness check (2K27 team vs source team)")
    espn_r = espn.get("roster", {})
    bbr_rows = {}
    for row in (bbr.get("per_game") or []):
        bbr_rows.setdefault(norm(row.get("name_display")), []).append(row.get("team_name_abbr"))
    espn_stat = {}
    for season, rows in espn.get("stats", {}).items():
        for a in rows:
            espn_stat.setdefault(season, {})[norm(a["athlete"]["displayName"])] = a["athlete"].get("teamShortName") or a["athlete"].get("teamName")
    print(f"{'player':20} {'2K':4} {'ESPN roster':12} {'ESPN stats27':12} {'BBR27':12}")
    for grp, d in (("rookie", ROOKIES), ("vet", VETERANS)):
        for name, t2k in d.items():
            k = norm(name)
            e = espn_r.get(k, ("-",))[0]
            es = espn_stat.get("2027", {}).get(k, "-")
            b = "/".join(bbr_rows.get(k, ["-"]))
            print(f"{name:20} {t2k:4} {e:12} {str(es):12} {b:12} ({grp})")


def crosswalk(espn, bbr):
    section("Crosswalk coverage vs nba_stats.json (name only, then name+team)")
    path = os.path.join("nba", "data", "nba_stats.json")
    if not os.path.exists(path):
        return
    base = json.load(open(path, encoding="utf-8"))
    names = {}
    for pid, p in base.items():
        names.setdefault(norm(p["name"]), []).append(p)
    for lab, keys in (("ESPN roster", set(espn.get("roster", {}))),
                      ("BBR per_game", {norm(r.get("name_display")) for r in (bbr.get("per_game") or [])})):
        if not keys:
            continue
        hit = sum(1 for k in keys if k in names)
        uniq = sum(1 for k in keys if len(names.get(k, [])) == 1)
        print(f"{lab}: {len(keys)} names; {hit} found in nba_stats.json ({uniq} unique); "
              f"{sum(1 for k in names if k in keys)}/{len(names)} of nba_stats universe present")


if __name__ == "__main__":
    print("python", sys.version.split()[0], "| runner:", os.environ.get("RUNNER_NAME", "local"))
    try:
        print("egress ip class:", requests.get("https://api.ipify.org", timeout=10).text.split(".")[0] + ".x.x.x")
    except Exception:
        pass
    espn = probe_espn()
    bbr = probe_bbr()
    probe_cdn()
    probe_balldontlie()
    probe_stats_nba_control()
    freshness(espn, bbr)
    crosswalk(espn, bbr)
    section("Summary")
    for r in results:
        pass
    ok = sum(1 for r in results if r["status"] == 200)
    print(f"{ok}/{len(results)} requests returned 200")
