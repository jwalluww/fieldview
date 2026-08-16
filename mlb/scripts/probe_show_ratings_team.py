"""
mlb/scripts/probe_show_ratings_team.py

Two checks: (1) full nav list, specifically hunting for Diamond Dynasty
so we know it's not lurking somewhere past the first 20 links, and
(2) one real team page's table structure -- headers, row shape, actual
values -- before designing the 30-team scraper.
"""
from curl_cffi import requests as cffi_requests
from bs4 import BeautifulSoup

session = cffi_requests.Session(impersonate="chrome120")
resp = session.get("https://www.theshowratings.com/", timeout=30)

soup = BeautifulSoup(resp.text, "html.parser")
all_links = [(l.get_text(strip=True), l["href"]) for l in soup.find_all("a", href=True) if l.get_text(strip=True)]

print(f"total nav links: {len(all_links)}")
dd_hits = [(t, h) for t, h in all_links if "diamond" in t.lower() or "diamond" in h.lower()]
print(f"\n'diamond' matches in text/href: {dd_hits}")

print("\nfull link list:")
for text, href in all_links:
    print(f"  {text} -> {href}")

team_link = next((h for t, h in all_links if "diamondback" in t.lower()), None)
print(f"\nusing team link: {team_link}")

if team_link:
    team_url = team_link if team_link.startswith("http") else f"https://www.theshowratings.com{team_link}"
    resp2 = session.get(team_url, timeout=30)
    print(f"team page status: {resp2.status_code}")
    soup2 = BeautifulSoup(resp2.text, "html.parser")
    tables = soup2.find_all("table")
    print(f"tables on team page: {len(tables)}")
    for i, t in enumerate(tables):
        headers = [th.get_text(strip=True) for th in t.find_all("th")]
        rows = t.find_all("tr")
        print(f"  table {i}: id={t.get('id')}, class={t.get('class')}, headers={headers}, row_count={len(rows)}")
        for r in t.find_all("tr")[1:3]:
            cells = [c.get_text(strip=True) for c in r.find_all(["td", "th"])]
            print(f"    sample row: {cells}")
    with open("show_ratings_team_probe.html", "w", encoding="utf-8") as f:
        f.write(resp2.text)
