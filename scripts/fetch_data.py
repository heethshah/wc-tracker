#!/usr/bin/env python3
"""
Pulls the current World Cup 2026 top scorers from football-data.org
and rebuilds data.json, grouped by each player's CLUB side.

Needs one environment variable:
    FOOTBALL_DATA_KEY  - free key from https://www.football-data.org/client/register

The World Cup API lists scorers by national team, not club, so the
player-to-club mapping lives in CLUB_MAP below. When a new player scores
who isn't in the map yet, he lands in the "unmapped" list in data.json
instead of silently disappearing. Add him to CLUB_MAP and re-run.
"""

import json
import os
import sys
import urllib.request
from datetime import date

API_URL = "https://api.football-data.org/v4/competitions/WC/scorers?limit=100"

# surname fragment (lowercase) -> (club, league)
# Matching is substring-based against the API's full player name,
# so "mbapp" catches both Mbappé and Mbappe.
CLUB_MAP = {
    "messi":        ("Inter Miami", "MLS"),
    "mbapp":        ("Real Madrid", "La Liga"),
    "vin":          ("Real Madrid", "La Liga"),
    "bellingham":   ("Real Madrid", "La Liga"),
    "güler":        ("Real Madrid", "La Liga"),
    "guler":        ("Real Madrid", "La Liga"),
    "demb":         ("Paris Saint-Germain", "Ligue 1"),
    "barcola":      ("Paris Saint-Germain", "Ligue 1"),
    "dou":          ("Paris Saint-Germain", "Ligue 1"),
    "hakimi":       ("Paris Saint-Germain", "Ligue 1"),
    "neves":        ("Paris Saint-Germain", "Ligue 1"),
    "nuno mendes":  ("Paris Saint-Germain", "Ligue 1"),
    "kane":         ("Bayern Munich", "Bundesliga"),
    "musiala":      ("Bayern Munich", "Bundesliga"),
    "luis d":       ("Bayern Munich", "Bundesliga"),
    "havertz":      ("Arsenal", "Premier League"),
    "trossard":     ("Arsenal", "Premier League"),
    "martinelli":   ("Arsenal", "Premier League"),
    "gy":           ("Arsenal", "Premier League"),          # Gyökeres
    "cunha":        ("Manchester United", "Premier League"),
    "amad":         ("Manchester United", "Premier League"),
    "casemiro":     ("Manchester United", "Premier League"),
    "rashford":     ("Manchester United", "Premier League"),
    "brobbey":      ("Sunderland", "Premier League"),
    "diarra":       ("Sunderland", "Premier League"),
    "xhaka":        ("Sunderland", "Premier League"),
    "isidor":       ("Sunderland", "Premier League"),
    "sarr":         ("Crystal Palace", "Premier League"),
    "kamada":       ("Crystal Palace", "Premier League"),
    "muñoz":        ("Crystal Palace", "Premier League"),
    "munoz":        ("Crystal Palace", "Premier League"),
    "gakpo":        ("Liverpool", "Premier League"),
    "salah":        ("Liverpool", "Premier League"),
    "van dijk":     ("Liverpool", "Premier League"),
    "isak":         ("Liverpool", "Premier League"),
    "haaland":      ("Manchester City", "Premier League"),
    "elanga":       ("Newcastle United", "Premier League"),
    "wissa":        ("Newcastle United", "Premier League"),
    "pép":          ("Villarreal", "La Liga"),
    "pepe":         ("Villarreal", "La Liga"),
    "gueye":        ("Villarreal", "La Liga"),
    "lukaku":       ("Napoli", "Serie A"),
    "de bruyne":    ("Napoli", "Serie A"),
    "tielemans":    ("Aston Villa", "Premier League"),
    "mcginn":       ("Aston Villa", "Premier League"),
    "jonathan david": ("Juventus", "Serie A"),
    "ronaldo":      ("Al-Nassr", "Saudi Pro League"),
    "saibari":      ("PSV Eindhoven", "Eredivisie"),
    "undav":        ("VfB Stuttgart", "Bundesliga"),
    "manzambi":     ("SC Freiburg", "Bundesliga"),
    "balogun":      ("AS Monaco", "Ligue 1"),
    "quiñones":     ("Al-Qadsiah", "Saudi Pro League"),
    "quinones":     ("Al-Qadsiah", "Saudi Pro League"),
}

# Careful with short fragments like "gy" or "sarr" - substring matching
# means they can collide with other names. If two players clash, use a
# longer, more specific fragment (e.g. "ismaila sarr" vs "bouna sarr").


def find_club(player_name: str):
    name = player_name.lower()
    # longest fragments first, so "jonathan david" wins over any shorter hit
    for frag in sorted(CLUB_MAP, key=len, reverse=True):
        if frag in name:
            return CLUB_MAP[frag]
    return None


def main():
    key = os.environ.get("FOOTBALL_DATA_KEY")
    if not key:
        sys.exit("FOOTBALL_DATA_KEY is not set. Get a free key at football-data.org and add it as a repo secret.")

    req = urllib.request.Request(API_URL, headers={"X-Auth-Token": key})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.load(resp)
    except Exception as exc:
        # Fail loudly so the GitHub Action doesn't commit a broken file
        sys.exit(f"API request failed: {exc}")

    scorers = payload.get("scorers", [])
    if not scorers:
        sys.exit("API returned no scorers - leaving the existing data.json alone.")

    clubs = {}
    unmapped = []

    for row in scorers:
        player = row.get("player", {}).get("name", "").strip()
        goals = row.get("goals") or 0
        if not player or goals < 1:
            continue

        hit = find_club(player)
        if hit is None:
            unmapped.append([player, goals])
            continue

        club, league = hit
        clubs.setdefault(club, {"club": club, "league": league, "scorers": []})
        clubs[club]["scorers"].append([player.split()[-1].title(), goals])

    club_list = sorted(
        clubs.values(),
        key=lambda c: (-sum(g for _, g in c["scorers"]), -len(c["scorers"])),
    )

    out = {
        "updated": date.today().isoformat(),
        "source": "football-data.org /competitions/WC/scorers",
        "clubs": club_list,
        "unmapped": unmapped,
    }

    with open("data.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)

    print(f"Wrote data.json: {len(club_list)} clubs, {len(unmapped)} unmapped players")
    if unmapped:
        print("Add these to CLUB_MAP when you get a minute:")
        for name, goals in unmapped:
            print(f"  - {name} ({goals})")


if __name__ == "__main__":
    main()
