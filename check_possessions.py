"""
Check the possession tracker against NBA.com's official counts.

Run this after changing src/possessions.py, or before trusting a season
the tracker hasn't been checked on:

    python check_possessions.py --season 2025-26 --games 30
    python check_possessions.py --season 2016-17 --games 20 --verbose

It samples games spread across the season and prints how far the
tracked possession totals are from the official ones. The official
box scores are cached in data/cache/advanced/.
"""

from __future__ import annotations

import argparse
from collections import Counter

from src.config import check_season, load_config
from src.core import parse_game, sum_events
from src.data import (
    load_official_possessions,
    load_pbp,
    load_schedule,
    schedule_games,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--season", default="2025-26", type=check_season)
    parser.add_argument("--games", type=int, default=30,
                        help="number of games to sample (default 30)")
    parser.add_argument("--verbose", action="store_true",
                        help="print every team-game")
    args = parser.parse_args()

    settings = load_config(args.config)
    games = list(schedule_games(load_schedule(args.season, settings)))
    step = max(1, len(games) // args.games)
    sample = games[::step][:args.games]

    differences = []
    for game in sample:
        events, _ = parse_game(
            load_pbp(game["game_id"], settings), game["home_id"], game["away_id"]
        )
        tracked = sum_events(events, game["home_id"], game["away_id"])
        official = load_official_possessions(game["game_id"], settings)

        for side in ("home", "away"):
            team_id = game[f"{side}_id"]
            ours = tracked[team_id]["poss"]
            diff = ours - official[team_id]
            differences.append(diff)
            if args.verbose or abs(diff) > 1:
                print(f"{game['game_id']} {game[side]:<25} "
                      f"tracked={ours:.0f} official={official[team_id]:.0f} "
                      f"diff={diff:+.0f}")

    n = len(differences)
    exact = sum(d == 0 for d in differences)
    print(f"\n{args.season}: {n} team-games from {len(sample)} games")
    print(f"exact match:     {exact} ({100 * exact / n:.0f}%)")
    print(f"within 1:        {sum(abs(d) <= 1 for d in differences)}")
    print(f"mean difference: {sum(differences) / n:+.2f}")
    print("distribution:   ", dict(sorted(Counter(differences).items())))


if __name__ == "__main__":
    main()
