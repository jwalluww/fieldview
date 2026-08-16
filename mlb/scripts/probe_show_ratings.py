"""
mlb/scripts/probe_show_ratings.py — throwaway, delete once we know the shape

Pure reconnaissance, no assumptions: is this static HTML (requests+bs4
works) or JS-rendered (need Selenium/Playwright)? One page with
everyone, or per-team pages like 2kratings? And where's the base/live
ratings section vs. Diamond Dynasty, since that's the split you
actually care about.
"""
import requests
from bs4 import BeautifulSoup

resp = requests.get("https://www.theshowratings.com/", timeout=30, headers={
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
})
print(f"status: {resp.status_code}")
print(f"content length: {len(resp.text)}")

soup = BeautifulSoup(resp.text, "html.parser")
print(f"page title: {soup.title.string if soup.title else 'none'}")

nav_links = soup.find_all("a", href=True)
print(f"\ntotal links found: {len(nav_links)}")
for link in nav_links[:40]:
    text = link.get_text(strip=True)
    if text:
        print(f"  {text} -> {link['href']}")

tables = soup.find_all("table")
print(f"\ntables in raw HTML: {len(tables)}")
for i, t in enumerate(tables[:3]):
    print(f"  table {i}: id={t.get('id')}, class={t.get('class')}, rows={len(t.find_all('tr'))}")

script_srcs = [s.get("src", "") for s in soup.find_all("script", src=True)]
js_hints = [s for s in script_srcs if any(k in s.lower() for k in ["next", "react", "_next", "vue", "app.js"])]
print(f"\nJS framework script hints: {js_hints[:5]}")

with open("show_ratings_probe.html", "w", encoding="utf-8") as f:
    f.write(resp.text)
print("\nfull HTML saved to show_ratings_probe.html for manual inspection")
