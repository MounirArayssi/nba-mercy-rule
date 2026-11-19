"""
Turn per-game rows into season ratings.

Definitions (per 100 possessions):
    ORtg = 100 * points scored  / own possessions
    DRtg = 100 * points allowed / opponent possessions
    Net  = ORtg - DRtg

This matches how NBA.com computes them. Every metric is calculated twice:
"actual" (the real game) and "mercy" (the game cut off by the rule).
"""

from __future__ import annotations

import pandas as pd


# Box-score fields checked against the official schedule box score.
BOX_FIELDS = (
    "PTS", "FGA", "FGM", "FG3A", "FG3M",
    "FTA", "FTM", "OREB", "TOV",
)

PREFIXES = ("actual", "mercy")
KEYS = ["season", "rule_id", "team_id", "team"]


def validate_game(game, rows):
    """
    Compare the stats rebuilt from play-by-play with the official box
    score. Returns a list of issue strings (empty means a perfect match).
    `rows` are the two team rows from simulate_game.
    """
    issues = []
    for row, box in zip(rows, (game["home_box"], game["away_box"])):
        for field in BOX_FIELDS:
            official = box.get(field)
            if official is None or pd.isna(official):
                continue
            rebuilt = row[f"actual_{field.lower()}"]
            if abs(float(official) - rebuilt) > 0.001:
                issues.append(
                    f"{row['team']} {field}: pbp={rebuilt:g}, box={official:g}"
                )
    return issues


def estimate_possessions(df, prefix, factor=0.44):
    """Box-score estimate: FGA - OREB + TOV + factor * FTA."""
    return (
        df[f"{prefix}_fga"]
        - df[f"{prefix}_oreb"]
        + df[f"{prefix}_tov"]
        + factor * df[f"{prefix}_fta"]
    )


def aggregate_ratings(team_rows, method="tracked", factor=0.44):
    """
    One row per (season, rule, team) with actual_*, mercy_* and delta_*
    ratings, plus net-rating ranks within each season and rule.

    method="tracked" uses possessions counted from play-by-play.
    method="estimate" replaces them with the box-score formula.
    """
    df = pd.DataFrame(team_rows)
    if df.empty:
        raise ValueError("No team-game statistics")

    if method == "estimate":
        for prefix in PREFIXES:
            df[f"{prefix}_poss"] = estimate_possessions(df, prefix, factor)

    # Attach each team's opponent points and possessions.
    opp_cols = [f"{p}_{s}" for p in PREFIXES for s in ("pts", "poss")]
    opponents = df[["season", "rule_id", "game_id", "team_id", *opp_cols]]
    opponents = opponents.rename(columns={
        "team_id": "opponent_id",
        **{c: c.replace("_", "_opp_", 1) for c in opp_cols},
    })
    df = df.merge(
        opponents,
        on=["season", "rule_id", "game_id", "opponent_id"],
        validate="one_to_one",
    )

    sums = [c for c in df.columns if c.startswith(("actual_", "mercy_", "removed_"))]
    totals = df.groupby(KEYS, as_index=False).agg(
        games=("game_id", "nunique"),
        games_cut=("triggered", "sum"),
        **{c: (c, "sum") for c in sums},
    )

    for p in PREFIXES:
        if (totals[f"{p}_poss"] <= 0).any() or (totals[f"{p}_opp_poss"] <= 0).any():
            raise ValueError("Nonpositive possessions")

        totals[f"{p}_ortg"] = 100 * totals[f"{p}_pts"] / totals[f"{p}_poss"]
        totals[f"{p}_drtg"] = 100 * totals[f"{p}_opp_pts"] / totals[f"{p}_opp_poss"]
        totals[f"{p}_net"] = totals[f"{p}_ortg"] - totals[f"{p}_drtg"]
        totals[f"{p}_pace"] = (
            (totals[f"{p}_poss"] + totals[f"{p}_opp_poss"]) / 2 / totals["games"]
        )

        fga = totals[f"{p}_fga"].replace(0, float("nan"))
        totals[f"{p}_efg"] = (
            totals[f"{p}_fgm"] + 0.5 * totals[f"{p}_fg3m"]
        ) / fga
        totals[f"{p}_ts"] = totals[f"{p}_pts"] / (
            2 * (totals[f"{p}_fga"] + factor * totals[f"{p}_fta"])
        )

        totals[f"{p}_rank"] = (
            totals.groupby(["season", "rule_id"])[f"{p}_net"]
            .rank(method="min", ascending=False)
            .astype(int)
        )

    for metric in ("ortg", "drtg", "net", "pace", "efg", "ts"):
        totals[f"delta_{metric}"] = totals[f"mercy_{metric}"] - totals[f"actual_{metric}"]

    # Positive = the team moved up the net-rating table.
    totals["rank_gain"] = totals["actual_rank"] - totals["mercy_rank"]

    return totals.sort_values(["season", "rule_id", "mercy_rank"]).reset_index(drop=True)


def compare_scenarios(games, ratings):
    """One summary row per season and mercy rule."""
    game_df = pd.DataFrame(games)
    results = []

    for (season, rule_id), group in game_df.groupby(["season", "rule_id"]):
        teams = ratings[(ratings.season == season) & (ratings.rule_id == rule_id)]
        cut = group[group.triggered]

        results.append({
            "season": season,
            "rule_id": rule_id,
            "games": len(group),
            "games_cut": len(cut),
            "pct_games_cut": 100 * len(cut) / len(group),
            # Which tier ended each cut game, e.g. "extreme: 2, moderate: 5".
            "cuts_by_tier": ", ".join(
                f"{tier}: {count}"
                for tier, count in cut.trigger_tier.value_counts().items()
            ),
            "comebacks_erased": int(group.comeback_erased.sum()),
            # Q4 cutoffs: seconds left in the period = time removed.
            "avg_minutes_removed": (
                cut.cutoff_clock.mean() / 60 if len(cut) else 0.0
            ),
            "possessions_removed": int(teams.removed_poss.sum()),
            "avg_abs_net_change": teams.delta_net.abs().mean(),
            "max_net_gain": teams.delta_net.max(),
            "max_net_loss": teams.delta_net.min(),
            "largest_rank_gain": int(teams.rank_gain.max()),
            "largest_rank_drop": int(-teams.rank_gain.min()),
        })

    return pd.DataFrame(results).sort_values(["season", "rule_id"])
