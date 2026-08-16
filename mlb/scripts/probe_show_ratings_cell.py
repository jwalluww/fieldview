"""
mlb/scripts/probe_show_ratings_cell.py

Dumps the RAW HTML (not .text) of the first few Player cells so we can
see the real nested element structure -- separate spans with classes
vs. one blob of concatenated text nodes. Parsing strategy depends
entirely on which one this actually is.
"""
from curl_cffi import requests as cffi_requests
from bs4 import BeautifulSoup

session = cffi_requests.Session(impersonate="chrome120")
resp = session.get("https://www.theshowratings.com/teams/arizona-diamondbacks", timeout=30)

soup = BeautifulSoup(resp.text, "html.parser")
table = soup.find("table", class_="table-striped")
rows = table.find_all("tr")[1:4]  # header + first 3 player rows

for i, row in enumerate(rows):
    cells = row.find_all("td")
    player_cell = cells[1] if len(cells) > 1 else None  # column 1 = "Player"
    print(f"=== row {i} raw HTML ===")
    print(player_cell.prettify() if player_cell else "no cell found")
    print()
