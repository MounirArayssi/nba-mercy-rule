"""Write CSVs, JSON summaries and charts to the output folder."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.data import load_historical_season


GAIN_COLOR = "#347F75"
LOSS_COLOR = "#B65C5C"


def save_csv(df, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def save_json(data, path):
    Path(path).write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------

def _pyplot():
    import matplotlib
    matplotlib.use("Agg")  # no display needed
    import matplotlib.pyplot as plt
    return plt


def _label(df):
    return df["team"] + " (" + df["season"] + ")"


def plot_net_changes(ratings, path, top=8):
    """Bar chart of the biggest net-rating gains and losses."""
    data = ratings[ratings.games_cut > 0]
    if data.empty:
        return
    data = pd.concat([
        data.nsmallest(top, "delta_net"),
        data.nlargest(top, "delta_net"),
    ]).drop_duplicates(["season", "team_id"]).sort_values("delta_net")

    plt = _pyplot()
    fig, ax = plt.subplots(figsize=(10, max(5, len(data) * 0.4)))
    ax.barh(
        _label(data), data.delta_net,
        color=[LOSS_COLOR if x < 0 else GAIN_COLOR for x in data.delta_net],
    )
    ax.axvline(0, color="black", linewidth=0.8)
    ax.set_xlabel("Change in net rating per 100 possessions")
    ax.set_title("Mercy Rule: Biggest Net Rating Changes")
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)


def plot_before_after(ratings, path, top=12):
    """Dumbbell chart: actual vs mercy net rating for the biggest movers."""
    data = ratings[ratings.games_cut > 0]
    if data.empty:
        return
    data = data.reindex(data.delta_net.abs().sort_values().index).tail(top)
    y = list(range(len(data)))

    plt = _pyplot()
    fig, ax = plt.subplots(figsize=(10, max(5, len(data) * 0.45)))
    ax.hlines(y, data.actual_net, data.mercy_net, color="#A0A0A0", linewidth=2)
    ax.scatter(data.actual_net, y, label="Actual", s=45, color=LOSS_COLOR)
    ax.scatter(data.mercy_net, y, label="Mercy rule", s=45, color=GAIN_COLOR)
    ax.set_yticks(y, _label(data))
    ax.set_xlabel("Net rating per 100 possessions")
    ax.set_title("Before vs. After the Mercy Rule")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Historical leaderboard
# ---------------------------------------------------------------------------

def build_historical_comparison(ratings, settings):
    """
    Hybrid leaderboard: every team since `historical_start` ranked by
    net rating. The experiment's team-seasons use mercy-adjusted
    ratings and every other team uses NBA.com's published rating.

    This is NOT a like-for-like all-time ranking. Only the experiment
    seasons have the rule applied.
    """
    start = int(settings.historical_start[:4])
    end = max(int(s[:4]) for s in settings.seasons)

    frames = []
    for year in range(start, end + 1):
        season = f"{year}-{(year + 1) % 100:02d}"
        raw = load_historical_season(season, settings)
        frames.append(pd.DataFrame({
            "season": season,
            "team_id": raw["TEAM_ID"].astype(int),
            "team": raw["TEAM_NAME"],
            "net": pd.to_numeric(raw["NET_RATING"], errors="coerce"),
            "source": "published_unadjusted",
        }))
    history = (
        pd.concat(frames, ignore_index=True)
        .dropna(subset=["net"])
        .drop_duplicates(["season", "team_id"])
    )

    boards = []
    for rule_id, rule_ratings in ratings.groupby("rule_id"):
        adjusted = rule_ratings[["season", "team_id", "team", "mercy_net"]].rename(
            columns={"mercy_net": "net"}
        )
        adjusted["source"] = "mercy_adjusted"

        replaced = history.set_index(["season", "team_id"]).index.isin(
            adjusted.set_index(["season", "team_id"]).index
        )
        if replaced.sum() != len(adjusted):
            raise ValueError(f"Historical team mismatch for {rule_id}")

        board = pd.concat([history[~replaced], adjusted], ignore_index=True)
        board = board.sort_values("net", ascending=False).reset_index(drop=True)
        board["hybrid_rank"] = board.index + 1
        board["rule_id"] = rule_id
        boards.append(board)

    return pd.concat(boards, ignore_index=True)


# ---------------------------------------------------------------------------
# Output folder
# ---------------------------------------------------------------------------

def write_reports(games, rows, ratings, comparisons, summary, settings):
    """
    output/
      summary.json              run status, coverage, warnings
      errors.json               games that failed to parse
      validation_issues.csv     play-by-play vs box score mismatches
      scenario_comparison.csv   one row per season x rule
      all_games.csv             every game x rule
      all_team_game_stats.csv   every team x game x rule
      all_team_ratings.csv      every team-season x rule
      <rule_id>/                games, ratings, erased comebacks, charts
      historical_hybrid_rankings.csv   (only with historical_comparison)
    """
    root = settings.output_dir
    root.mkdir(parents=True, exist_ok=True)
    games_df = pd.DataFrame(games)

    save_json(summary, root / "summary.json")
    save_json(summary["errors"], root / "errors.json")
    save_csv(pd.DataFrame(summary["validation_issues"],
                          columns=["season", "game_id", "issue"]),
             root / "validation_issues.csv")
    save_csv(games_df, root / "all_games.csv")
    save_csv(pd.DataFrame(rows), root / "all_team_game_stats.csv")
    save_csv(ratings, root / "all_team_ratings.csv")
    save_csv(comparisons, root / "scenario_comparison.csv")

    for rule in settings.rules:
        folder = root / rule.id
        folder.mkdir(parents=True, exist_ok=True)
        rule_games = games_df[games_df.rule_id == rule.id]
        rule_ratings = ratings[ratings.rule_id == rule.id]

        save_csv(rule_games, folder / "games.csv")
        save_csv(rule_ratings, folder / "team_ratings.csv")
        save_csv(rule_games[rule_games.comeback_erased], folder / "erased_comebacks.csv")

        if settings.charts:
            plot_net_changes(rule_ratings, folder / "net_rating_changes.png")
            plot_before_after(rule_ratings, folder / "before_after.png")

    if settings.historical_comparison:
        if summary["publishable"]:
            save_csv(
                build_historical_comparison(ratings, settings),
                root / "historical_hybrid_rankings.csv",
            )
        else:
            print("Skipped historical leaderboard: needs complete seasons.")
