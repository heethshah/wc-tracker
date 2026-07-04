# WC26 Club Goal Tracker

A small self-updating site that shows every 2026 World Cup goal grouped by the
scorer's club side. No servers, no AI, nothing to babysit. GitHub does the
daily refresh for free while you sleep.

## How it works

```
GitHub Action (7:00 UTC daily)
      |
      v
scripts/fetch_data.py  -- pulls scorers from football-data.org
      |
      v
data.json              -- committed back to the repo if anything changed
      |
      v
index.html             -- reads data.json when someone opens the page
```

## Setup (about ten minutes)

1. **Get a free API key.** Register at https://www.football-data.org/client/register
   and copy the token they email you. The free tier covers the World Cup.

2. **Create a GitHub repo** and push these files into it, keeping the folder
   structure as-is (the `.github/workflows/` path matters).

3. **Add the key as a secret.** In the repo: Settings -> Secrets and variables
   -> Actions -> New repository secret. Name it `FOOTBALL_DATA_KEY`, paste the token.

4. **Turn on GitHub Pages.** Settings -> Pages -> deploy from branch `main`,
   folder `/ (root)`. A minute later your dashboard is live at
   `https://<your-username>.github.io/<repo-name>/`.

5. **Test the refresh** without waiting for tomorrow: Actions tab ->
   "Update World Cup data" -> Run workflow.

That's the whole thing. Every morning at 7:00 UTC the action pulls fresh
scorers and commits the new numbers. Pages redeploys automatically.

## The one thing you'll maintain

World Cup APIs list scorers by country, not club, so the player-to-club
mapping lives in `CLUB_MAP` inside `scripts/fetch_data.py`. When someone new
scores who isn't in the map, the script doesn't guess - it puts them in an
`unmapped` list in data.json and prints them in the action log. Add a line to
`CLUB_MAP` and they'll be sorted from the next run. During the group stage
this happens a lot; by the knockouts, almost never.

## Tweaks

- **Different refresh time:** edit the cron line in
  `.github/workflows/update-data.yml`. `0 7 * * *` means 07:00 UTC daily.
- **Different API:** swap the fetch logic in `fetch_data.py`. API-Football
  (api-sports.io) includes each player's club directly, which kills most of
  the manual mapping, but the free tier is 100 requests/day and the response
  shape is different.
- **Club colours and crests:** the `STYLES` object at the top of
  `index.html`. Unlisted clubs get a neutral badge automatically.

## Known quirks

- Crest images hotlink from Wikipedia. If a filename changes there, that
  club falls back to its monogram badge. Nothing breaks.
- Opening `index.html` straight from disk shows baked-in seed data, because
  browsers won't let a local file fetch `data.json`. Use the hosted version,
  or run `python3 -m http.server` in the folder to preview locally.
