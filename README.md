# FieldView

FieldView shows every team's players lined up in their real positions (on the field, court, ice, diamond or pitch) with substitutions and video-game overall ratings, next to a sortable, filterable stat table for the same players.

**Live:** https://jwalluww.github.io/fieldview/

## Sports

| Sport | Field view | Table view |
|---|---|---|
| NFL | FormationView (offense and defense, plus a 2027 mock-draft rookie installer) | Player table |
| NBA | CourtView | Player table |
| MLB | DiamondView | Player table |
| NHL | IceView | Player table |
| Premier League | PitchView (formation switcher) | Player table |
| MLS | PitchView (formation switcher) | Player table |

Desktop only by choice; small screens get a notice.

## Stack

Plain HTML/CSS/JS on GitHub Pages (no framework, no build step), fed by Python scrapers that run weekly in GitHub Actions and commit flat JSON files the pages `fetch()`.

## Data credits

nflverse, OurLads, OverTheCap, ESPN, Basketball-Reference, nba2kapi / 2kratings, MLB Stats API, MLB The Show, NHL API, nhlratings.net, Fantasy Premier League (FPL), American Soccer Analysis, EA Sports (Madden, EA FC), PFN and Mock Draft Hero.

**Data belongs to its sources.** FieldView is not affiliated with or endorsed by the NFL, NBA, MLB, NHL, MLS, Premier League, EA Sports, 2K or their teams; team names and logos are trademarks of their owners.

## Privacy

Anonymous usage stats via Google Analytics (GA4); preferences stay in your browser. See [privacy.html](privacy.html).
