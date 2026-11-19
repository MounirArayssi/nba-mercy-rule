"""
NBA Mercy Rule experiment.

For every game: download play-by-play, find where each mercy rule would
have ended it, and compare offensive / defensive / net ratings with and
without the minutes the rule removes.

    python main.py                         # everything in config.yaml
    python main.py --seasons 2025-26 --limit 10
    python main.py --historical

See README.md for details.
"""

from __future__ import annotations

import argparse
import dataclasses
import logging

from src.analysis import aggregate_ratings, compare_scenarios, validate_game
from src.config import check_season, load_config
from src.core import parse_game, simulate_game
from src.data import load_pbp, load_schedule, schedule_games
from src.reporting import write_reports


LOG = logging.getLogger("nba_mercy")


def process_game(game, season, settings):
    """Run every rule on one game. Returns (games, rows, issues)."""
    payload = load_pbp(game["game_id"], settings)
    events, final = parse_game(payload, game["home_id"], game["away_id"])

    # If the final score doesn't match, the play-by-play is broken and
    # the game is unusable. Raise so it is recorded as an error.
    for side in ("home", "away"):
        official = int(game[f"{side}_box"]["PTS"])
        if official != final[f"{side}_score"]:
            raise ValueError(
                f"{side} score mismatch: pbp={final[f'{side}_score']}, "
                f"box={official}"
            )

    games, rows = [], []
    for rule in settings.rules:
        meta, team_rows = simulate_game(events, game, season, rule, settings.cutoff)
        games.append(meta)
        rows.extend(team_rows)

    # Smaller stat mismatches are only reported. They don't affect
    # points, and they barely move possessions.
    issues = validate_game(game, rows[:2])
    return games, rows, issues


def run(settings, limit=None):
    games, rows, errors, issues, coverage = [], [], [], [], {}

    for season in settings.seasons:
        descriptors = list(schedule_games(load_schedule(season, settings)))
        scheduled = len(descriptors)
        if limit is not None:
            descriptors = descriptors[:limit]
        LOG.info("Season %s: %d of %d games", season, len(descriptors), scheduled)

        processed = 0
        for index, game in enumerate(descriptors, start=1):
            try:
                g, r, game_issues = process_game(game, season, settings)
            except Exception as exc:
                LOG.warning("Skipped %s: %s", game["game_id"], exc)
                errors.append({"season": season, "game_id": game["game_id"],
                               "error": str(exc)})
            else:
                games.extend(g)
                rows.extend(r)
                issues.extend({"season": season, "game_id": game["game_id"],
                               "issue": i} for i in game_issues)
                processed += 1

            if index % 100 == 0:
                LOG.info("%s: %d/%d", season, index, len(descriptors))

        coverage[season] = {
            "expected_games": settings.expected_games(season),
            "scheduled_games": scheduled,
            "processed_games": processed,
        }

    if not games:
        raise RuntimeError("No games processed. Check errors above.")

    # Rankings are only "publishable" if every game of every season was
    # processed. Sample runs still produce every output, just flagged.
    warnings = []
    if limit is not None:
        warnings.append(f"--limit {limit}: sample run, not full seasons")
    if errors:
        warnings.append(f"{len(errors)} games failed (see errors.json)")
    for season, c in coverage.items():
        if c["expected_games"] and c["scheduled_games"] != c["expected_games"]:
            warnings.append(
                f"{season}: schedule has {c['scheduled_games']} games, "
                f"expected {c['expected_games']}"
            )
    if issues:
        warnings.append(
            f"{len(issues)} box-score mismatches (see validation_issues.csv)"
        )

    def complete(c):
        expected = c["expected_games"] or c["scheduled_games"]
        return c["processed_games"] == c["scheduled_games"] == expected

    publishable = (
        limit is None
        and not errors
        and all(complete(c) for c in coverage.values())
    )

    ratings = aggregate_ratings(rows, settings.possessions, settings.possession_factor)
    comparisons = compare_scenarios(games, ratings)

    summary = {
        "experiment": settings.name,
        "publishable": publishable,
        "warnings": warnings,
        "seasons": list(settings.seasons),
        "rules": {
            r.id: {
                "name": r.name,
                "tiers": [
                    f"{t.name}: lead >= {t.min_lead} with "
                    f"<= {t.max_seconds_remaining:g}s left in periods {list(t.periods)}"
                    for t in r.tiers
                ],
            }
            for r in settings.rules
        },
        "cutoff": settings.cutoff,
        "possessions": settings.possessions,
        "games_processed": len(games) // len(settings.rules),
        "coverage": coverage,
        "errors": errors,
        "validation_issues": issues,
    }
    write_reports(games, rows, ratings, comparisons, summary, settings)

    print("\n" + comparisons.to_string(index=False))
    print(f"\nOutputs written to {settings.output_dir}")
    for w in warnings:
        print("WARNING:", w)
    print("Publishable:", publishable)
    return summary


def main():
    parser = argparse.ArgumentParser(description="NBA Mercy Rule Experiment")
    parser.add_argument("--config", default="config.yaml",
                        help="YAML configuration file (default: config.yaml)")
    parser.add_argument("--seasons", nargs="+", metavar="YYYY-YY",
                        help="override the seasons in the config")
    parser.add_argument("--limit", type=int,
                        help="only process the first N games of each season")
    parser.add_argument("--historical", action="store_true",
                        help="also build the hybrid all-time leaderboard")
    args = parser.parse_args()

    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be positive")

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    settings = load_config(args.config)
    if args.seasons:
        settings = dataclasses.replace(
            settings, seasons=tuple(check_season(s) for s in args.seasons)
        )
    if args.historical:
        settings = dataclasses.replace(settings, historical_comparison=True)

    run(settings, limit=args.limit)


if __name__ == "__main__":
    main()
