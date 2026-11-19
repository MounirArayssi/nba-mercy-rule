"""
NBA Stats API access, with an on-disk cache.

Every response is saved under `cache_dir`, so a game is only downloaded
once. Delete the cache folder to force a fresh download.
"""

from __future__ import annotations

import json
import logging
import time

import pandas as pd
from nba_api.stats.endpoints import (
    boxscoreadvancedv3,
    leaguedashteamstats,
    leaguegamefinder,
    playbyplayv3,
)

LOG = logging.getLogger(__name__)


def cached_request(path, request, settings):
    """Return the cached file at `path`, or call `request()` and cache it.

    `.json` paths hold dicts, `.csv` paths hold DataFrames.
    """
    if path.exists():
        if path.suffix == ".json":
            return json.loads(path.read_text(encoding="utf-8"))
        return pd.read_csv(path, dtype={"GAME_ID": str})

    error = None
    for attempt in range(1, settings.retries + 1):
        try:
            result = request()
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.suffix == ".json":
                path.write_text(json.dumps(result), encoding="utf-8")
            else:
                result.to_csv(path, index=False)
            time.sleep(settings.request_delay)  # be polite to the API
            return result
        except Exception as exc:
            error = exc
            LOG.warning(
                "Request failed %s (%d/%d): %s",
                path.name, attempt, settings.retries, exc,
            )
            time.sleep(settings.request_delay * attempt * 3)

    raise RuntimeError(f"Failed to retrieve {path.name}: {error}")


def load_schedule(season, settings):
    """One row per team per game, including the team box score."""
    path = settings.cache_dir / (
        f"schedule_{season}_{settings.season_type.replace(' ', '_')}.csv"
    )

    def request():
        return leaguegamefinder.LeagueGameFinder(
            player_or_team_abbreviation="T",
            season_nullable=season,
            season_type_nullable=settings.season_type,
            league_id_nullable="00",
            timeout=settings.timeout,
        ).get_data_frames()[0]

    df = cached_request(path, request, settings).copy()
    if df.empty:
        raise ValueError(f"Empty schedule: {season}")

    df["GAME_ID"] = df["GAME_ID"].astype(str).str.zfill(10)
    df["TEAM_ID"] = pd.to_numeric(df["TEAM_ID"]).astype(int)

    # Game id prefixes: 002 regular season, 004 playoffs. This also drops
    # the NBA Cup final (006), which doesn't count in the standings.
    prefix = "002" if settings.season_type == "Regular Season" else "004"
    df = df[df.GAME_ID.str.startswith(prefix)]

    # Keep games with exactly one row per team and a final score.
    df = df[df["PTS"].notna()]
    counts = df.groupby("GAME_ID").size()
    if (counts != 2).any():
        LOG.warning("%d games lack two team rows", int((counts != 2).sum()))
    return df[df.GAME_ID.isin(counts[counts == 2].index)].copy()


def home_abbreviation(matchup):
    """'BOS vs. NYK' -> 'BOS' and 'NYK @ BOS' -> 'BOS'."""
    if " vs. " in matchup:
        return matchup.split(" vs. ")[0].strip()
    if " @ " in matchup:
        return matchup.split(" @ ")[1].strip()
    return None


def schedule_games(df):
    """Yield one dict per game with ids, names and both box scores."""
    for game_id, group in df.groupby("GAME_ID", sort=True):
        # Read the home team from the matchup text rather than relying on
        # one row saying "vs." and the other "@". The API sometimes labels
        # both rows "DAL @ DET".
        homes = {home_abbreviation(str(m)) for m in group.MATCHUP}
        is_home = group.TEAM_ABBREVIATION.isin(homes)
        if len(homes) != 1 or is_home.sum() != 1:
            raise ValueError(f"Could not identify home/away: {game_id}")

        h, a = group[is_home].iloc[0], group[~is_home].iloc[0]
        yield {
            "game_id": game_id,
            "home_id": int(h.TEAM_ID),
            "away_id": int(a.TEAM_ID),
            "home": str(h.TEAM_NAME),
            "away": str(a.TEAM_NAME),
            "home_box": h.to_dict(),
            "away_box": a.to_dict(),
        }


def load_pbp(game_id, settings):
    """Raw PlayByPlayV3 payload: {"game": {"actions": [...]}}."""
    path = settings.cache_dir / "pbp" / f"{game_id}.json"

    def request():
        payload = playbyplayv3.PlayByPlayV3(
            game_id=game_id,
            start_period=1,
            end_period=10,
            timeout=settings.timeout,
        ).nba_response.get_dict()
        if not payload.get("game", {}).get("actions"):
            raise ValueError(f"No actions in {game_id}")
        return payload

    return cached_request(path, request, settings)


def load_official_possessions(game_id, settings):
    """NBA.com's official possession count per team: {team_id: poss}."""
    path = settings.cache_dir / "advanced" / f"{game_id}.json"

    def request():
        return boxscoreadvancedv3.BoxScoreAdvancedV3(
            game_id=game_id, timeout=settings.timeout,
        ).nba_response.get_dict()

    box = cached_request(path, request, settings)["boxScoreAdvanced"]
    return {
        box[side]["teamId"]: float(box[side]["statistics"]["possessions"])
        for side in ("homeTeam", "awayTeam")
    }


def load_historical_season(season, settings):
    """Published NBA team ratings for one season, without mercy rule."""
    path = settings.cache_dir / "history" / f"{season}.csv"

    def request():
        return leaguedashteamstats.LeagueDashTeamStats(
            season=season,
            season_type_all_star="Regular Season",
            measure_type_detailed_defense="Advanced",
            timeout=settings.timeout,
        ).get_data_frames()[0]

    df = cached_request(path, request, settings)
    if not {"TEAM_ID", "TEAM_NAME", "NET_RATING"}.issubset(df.columns):
        raise ValueError(f"Missing historical rating columns for {season}")
    return df
