#!/usr/bin/env python3
"""
Rebuilds data.json with World Cup 2026 scorers grouped by CLUB side.
Fully automated, with a fix for the "everyone became a country" problem:

During the tournament, football-data.org reports many players' currentTeam
as their NATIONAL squad. This version cross-checks every answer against the
player's national team (known from the scorer list) and rejects it if they
match. Rejected or missing answers fall back to TheSportsDB, a free public
database that tracks club affiliation and needs no API key.

Results are cached in club_cache.json so each player is looked up once.
Old cache entries that turn out to be countries are dropped automatically.

Needs: FOOTBALL_DATA_KEY environment variable.
First run takes ~7 minutes (free-tier rate limits). After that, seconds.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

BASE = "https://api.football-data.org/v4"
SCORERS_URL = f"{BASE}/competitions/WC/scorers?limit=100"
TSDB_URL = "https://www.thesportsdb.com/api/v1/json/3/searchplayers.php?p="
CACHE_FILE = "club_cache.json"
FD_WAIT = 6.5    # football-data free tier: 10 requests/minute
TSDB_WAIT = 1.5  # be polite to the fallback API

ALIASES = {
    "FC Bayern München": "Bayern Munich",
    "Club Atlético de Madrid": "Atlético Madrid",
    "FC Internazionale Milano": "Inter Milan",
    "SSC Napoli": "Napoli",
    "Sport Lisboa e Benfica": "Benfica",
    "Sporting Clube de Portugal": "Sporting CP",
    "Real Sociedad de Fútbol": "Real Sociedad",
    "Al Nassr FC": "Al-Nassr",
    "Al Qadsiah FC": "Al-Qadsiah",
    "Inter Miami CF": "Inter Miami",
    "Wolverhampton Wanderers FC": "Wolves",
    "Paris Saint-Germain": "Paris Saint-Germain",
}
STRIP_SUFFIXES = (" FC", " CF", " AFC", " CFC", " LFC")


def tidy(raw):
    if not raw:
        return None
    if raw in ALIASES:
        return ALIASES[raw]
    name = raw
    for s in STRIP_SUFFIXES:
        if name.endswith(s):
            name = name[: -len(s)]
            break
    return name.strip()


def get_json(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt == 1:
                print("  rate limit, waiting 65s...")
                time.sleep(65)
                continue
            raise
    return None


def looks_national(club, national_names):
    """True if this 'club' is actually somebody's national team."""
    if not club:
        return False
    c = club.lower().replace("national football team", "").strip()
    return any(c == n or n in c for n in national_names)


def from_football_data(pid, key, national_names):
    person = get_json(f"{BASE}/persons/{pid}", {"X-Auth-Token": key})
    team = (person or {}).get("currentTeam") or {}
    club = tidy(team.get("name"))
    if not club or looks_national(club, national_names):
        return None
    league = ""
    for comp in team.get("runningCompetitions") or []:
        if comp.get("type") == "LEAGUE":
            league = comp.get("name", "")
            break
    return {"club": club, "league": league}


def from_thesportsdb(player_name, national_names):
    url = TSDB_URL + urllib.parse.quote(player_name)
    data = get_json(url)
    for p in (data or {}).get("player") or []:
        if p.get("strSport") != "Soccer":
            continue
        club = tidy(p.get("strTeam"))
        if club and not looks_national(club, national_names):
            return {"club": club, "league": p.get("strLeague") or ""}
    return None


def display_name(full_name):
    parts = full_name.split()
    if len(parts) >= 2 and parts[-1].lower().rstrip(".") in ("junior", "jr", "júnior"):
        return f"{parts[-2]} Jr"
    return parts[-1] if parts else full_name


def main():
    key = os.environ.get("FOOTBALL_DATA_KEY")
    if not key:
        sys.exit("FOOTBALL_DATA_KEY is not set.")

    payload = get_json(SCORERS_URL, {"X-Auth-Token": key})
    scorers = (payload or {}).get("scorers", [])
    if not scorers:
        sys.exit("API returned no scorers - leaving data.json alone.")

    # Every national team present at the tournament, for the sanity check
    national_names = {
        (r.get("team", {}).get("name") or "").lower()
        for r in scorers if r.get("team", {}).get("name")
    }

    # Load cache, throwing out anything that is secretly a country or empty
    cache = {}
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, encoding="utf-8") as fh:
            for pid, info in json.load(fh).items():
                club = (info or {}).get("club")
                if club and not looks_national(club, national_names):
                    cache[pid] = info
    print(f"Cache: {len(cache)} good entries kept")

    todo = [r for r in scorers if str(r.get("player", {}).get("id")) not in cache]
    if todo:
        mins = len(todo) * (FD_WAIT + TSDB_WAIT) / 60
        print(f"{len(todo)} player(s) to look up (~{mins:.0f} min worst case)...")

    for i, row in enumerate(todo, 1):
        player = row.get("player", {})
        pid = str(player.get("id"))
        pname = (player.get("name") or "").strip()
        nation = row.get("team", {}).get("name", "?")
        if not pid or not pname:
            continue

        time.sleep(FD_WAIT)
        info = None
        try:
            info = from_football_data(pid, key, national_names)
        except Exception as exc:
            print(f"  [{i}/{len(todo)}] {pname}: football-data failed ({exc})")

        if info is None:
            time.sleep(TSDB_WAIT)
            try:
                info = from_thesportsdb(pname, national_names)
            except Exception as exc:
                print(f"  [{i}/{len(todo)}] {pname}: fallback failed ({exc})")

        if info:
            cache[pid] = info
            print(f"  [{i}/{len(todo)}] {pname} ({nation}) -> {info['club']}")
        else:
            print(f"  [{i}/{len(todo)}] {pname} ({nation}) -> no club found")

    with open(CACHE_FILE, "w", encoding="utf-8") as fh:
        json.dump(cache, fh, ensure_ascii=False, indent=2)

    clubs, unmapped = {}, []
    for row in scorers:
        player = row.get("player", {})
        pid = str(player.get("id"))
        pname = (player.get("name") or "").strip()
        goals = row.get("goals") or 0
        if not pname or goals < 1:
            continue
        info = cache.get(pid)
        if not info:
            unmapped.append([pname, goals])
            continue
        club = info["club"]
        entry = clubs.setdefault(club, {"club": club, "league": info.get("league") or "", "scorers": []})
        entry["scorers"].append([display_name(pname), goals])

    club_list = sorted(
        clubs.values(),
        key=lambda c: (-sum(g for _, g in c["scorers"]), -len(c["scorers"])),
    )

    out = {
        "updated": date.today().isoformat(),
        "source": "football-data.org scorers + per-player club lookup (with national-team guard)",
        "clubs": club_list,
        "unmapped": unmapped,
    }
    with open("data.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)

    print(f"Wrote data.json: {len(club_list)} clubs, {len(unmapped)} scorer(s) without a club")
    for name, goals in unmapped:
        print(f"  no club: {name} ({goals})")


if __name__ == "__main__":
    main()
