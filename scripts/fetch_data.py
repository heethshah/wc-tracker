#!/usr/bin/env python3
"""
Rebuilds data.json with World Cup 2026 scorers grouped by CLUB side.

Fully automated version - no manual player-to-club map. For every scorer,
the script asks football-data.org's /persons endpoint which club the player
currently belongs to, and remembers the answer in club_cache.json so it
never has to ask twice.

Needs: FOOTBALL_DATA_KEY environment variable.

Notes on speed and limits:
- The free tier allows 10 requests per minute, so the script waits ~6s
  between club lookups. The FIRST run does one lookup per scorer and can
  take 5-10 minutes. Every run after that only looks up brand-new scorers
  and finishes in seconds.
- If a player has no club on record (some leagues aren't covered by the
  free tier), he lands in the "unmapped" list in data.json instead of
  being guessed.
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import date

BASE = "https://api.football-data.org/v4"
SCORERS_URL = f"{BASE}/competitions/WC/scorers?limit=100"
CACHE_FILE = "club_cache.json"
WAIT_BETWEEN_LOOKUPS = 6.2  # seconds; free tier = 10 requests/minute

# The API uses formal club names ("FC Bayern München"). These aliases map
# them to the shorter names the dashboard's crest/colour styles expect.
# This is name normalisation, not player mapping - it rarely needs touching.
ALIASES = {
    "FC Bayern München": "Bayern Munich",
    "Club Atlético de Madrid": "Atlético Madrid",
    "FC Internazionale Milano": "Inter Milan",
    "SSC Napoli": "Napoli",
    "Società Sportiva Calcio Napoli": "Napoli",
    "Sport Lisboa e Benfica": "Benfica",
    "Sporting Clube de Portugal": "Sporting CP",
    "Real Sociedad de Fútbol": "Real Sociedad",
    "Al Nassr FC": "Al-Nassr",
    "Al-Nassr FC": "Al-Nassr",
    "Al Qadsiah FC": "Al-Qadsiah",
    "Inter Miami CF": "Inter Miami",
    "Wolverhampton Wanderers FC": "Wolves",
}

STRIP_SUFFIXES = (" FC", " CF", " AFC", " CFC", " LFC")


def api_get(url: str, key: str):
    """GET with one polite retry if we hit the rate limit."""
    req = urllib.request.Request(url, headers={"X-Auth-Token": key})
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt == 1:
                print("Rate limit hit, waiting 65s...")
                time.sleep(65)
                continue
            raise
    return None


def tidy_club_name(raw: str) -> str:
    if raw in ALIASES:
        return ALIASES[raw]
    name = raw
    for suffix in STRIP_SUFFIXES:
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    return name.strip()


def pick_league(team: dict) -> str:
    comps = team.get("runningCompetitions") or []
    for c in comps:
        if c.get("type") == "LEAGUE":
            return c.get("name", "")
    return comps[0].get("name", "") if comps else ""


def display_name(full_name: str) -> str:
    """'Vinícius Júnior' should show as 'Vinícius Jr', not 'Junior'."""
    parts = full_name.split()
    if not parts:
        return full_name
    if len(parts) >= 2 and parts[-1].lower().rstrip(".") in ("junior", "jr", "júnior"):
        return f"{parts[-2]} Jr"
    return parts[-1]


def main():
    key = os.environ.get("FOOTBALL_DATA_KEY")
    if not key:
        sys.exit("FOOTBALL_DATA_KEY is not set.")

    # 1. Current scorer list
    payload = api_get(SCORERS_URL, key)
    scorers = (payload or {}).get("scorers", [])
    if not scorers:
        sys.exit("API returned no scorers - leaving the existing data.json alone.")

    # 2. Load the cache of player-id -> club so repeat lookups are free
    cache = {}
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, encoding="utf-8") as fh:
            cache = json.load(fh)

    # 3. Look up any scorer we haven't seen before
    new_lookups = [
        row for row in scorers
        if str(row.get("player", {}).get("id")) not in cache
    ]
    if new_lookups:
        print(f"{len(new_lookups)} new scorer(s) to look up "
              f"(~{len(new_lookups) * WAIT_BETWEEN_LOOKUPS / 60:.0f} min at free-tier speed)...")

    for i, row in enumerate(new_lookups, 1):
        player = row.get("player", {})
        pid = str(player.get("id"))
        pname = player.get("name", "?")
        time.sleep(WAIT_BETWEEN_LOOKUPS)
        try:
            person = api_get(f"{BASE}/persons/{pid}", key)
        except Exception as exc:
            print(f"  [{i}/{len(new_lookups)}] {pname}: lookup failed ({exc})")
            continue
        team = (person or {}).get("currentTeam") or {}
        club_raw = team.get("name")
        if club_raw:
            cache[pid] = {
                "club": tidy_club_name(club_raw),
                "league": pick_league(team),
            }
            print(f"  [{i}/{len(new_lookups)}] {pname} -> {cache[pid]['club']}")
        else:
            cache[pid] = {"club": None, "league": None}
            print(f"  [{i}/{len(new_lookups)}] {pname} -> no club on record")

    # 4. Save the cache no matter what, so progress is never lost
    with open(CACHE_FILE, "w", encoding="utf-8") as fh:
        json.dump(cache, fh, ensure_ascii=False, indent=2)

    # 5. Group scorers by club
    clubs = {}
    unmapped = []
    for row in scorers:
        player = row.get("player", {})
        pid = str(player.get("id"))
        pname = player.get("name", "").strip()
        goals = row.get("goals") or 0
        if not pname or goals < 1:
            continue
        hit = cache.get(pid) or {}
        club = hit.get("club")
        if not club:
            unmapped.append([pname, goals])
            continue
        entry = clubs.setdefault(club, {"club": club, "league": hit.get("league") or "", "scorers": []})
        entry["scorers"].append([display_name(pname), goals])

    club_list = sorted(
        clubs.values(),
        key=lambda c: (-sum(g for _, g in c["scorers"]), -len(c["scorers"])),
    )

    out = {
        "updated": date.today().isoformat(),
        "source": "football-data.org (scorers + per-player club lookup)",
        "clubs": club_list,
        "unmapped": unmapped,
    }
    with open("data.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)

    print(f"Wrote data.json: {len(club_list)} clubs, {len(unmapped)} scorer(s) without a club on record")
    for name, goals in unmapped:
        print(f"  no club: {name} ({goals})")


if __name__ == "__main__":
    main()
