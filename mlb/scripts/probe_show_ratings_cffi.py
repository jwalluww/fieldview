"""
mlb/scripts/probe_show_ratings_cffi.py — ONE test, not a full run

If this also gets blocked, STOP. Don't retry today -- per the NBA 2K
Ratings notes, repeated attempts during an active Cloudflare block
likely extend the block rather than get past it.
"""
from curl_cffi import requests as cffi_requests
from bs4 import BeautifulSoup

session = cffi_requests.Session(impersonate="chrome120")
resp = session.get("https://www.theshowratings.com/", timeout=30)

print(f"status: {resp.status_code}")
print(f"content length: {len(resp.text)}")

if resp.status_code == 200:
    soup = BeautifulSoup(resp.text, "html.parser")
    print(f"page title: {soup.title.string if soup.title else 'none'}")
    tables = soup.find_all("table")
    print(f"tables found: {len(tables)}")
    nav_links = [l.get_text(strip=True) for l in soup.find_all("a", href=True) if l.get_text(strip=True)]
    print(f"nav links (first 20): {nav_links[:20]}")
    with open("show_ratings_probe_cffi.html", "w", encoding="utf-8") as f:
        f.write(resp.text)
else:
    print("Still blocked. STOP -- do not retry. Reporting headers for reference only:")
    print(dict(resp.headers))
