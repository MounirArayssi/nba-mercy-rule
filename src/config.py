"""Load and validate config.yaml into typed, read-only settings."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

import yaml


# Regular-season games per season. Anything not listed is assumed to be
# 1,230 (30 teams x 82 games / 2). Used to check a season is complete.
EXPECTED_GAMES = {
    "1998-99": 725,   # lockout
    "2011-12": 990,   # lockout
    "2019-20": 1059,  # COVID suspension (971 + 88 bubble seeding games)
    "2020-21": 1080,  # 72-game season
}

CUTOFF_MODES = ("possession", "event")
POSSESSION_METHODS = ("tracked", "estimate")


@dataclass(frozen=True)
class Tier:
    """One condition: lead >= min_lead with <= max_seconds_remaining left."""
    name: str
    min_lead: int
    max_seconds_remaining: float
    periods: tuple[int, ...] = (4,)

    def matches(self, period, seconds, margin):
        return (
            period in self.periods
            and seconds <= self.max_seconds_remaining
            and abs(margin) >= self.min_lead
        )


@dataclass(frozen=True)
class MercyRule:
    """
    A mercy rule made of one or more tiers. The game ends the first
    moment ANY tier is satisfied.
    """
    id: str
    name: str
    tiers: tuple[Tier, ...]

    def matching_tier(self, period, seconds, margin):
        """The first listed tier satisfied at this moment, or None."""
        for tier in self.tiers:
            if tier.matches(period, seconds, margin):
                return tier
        return None

    def matches(self, period, seconds, margin):
        """True if the game should end at this moment."""
        return self.matching_tier(period, seconds, margin) is not None


@dataclass(frozen=True)
class Settings:
    name: str
    seasons: tuple[str, ...]
    season_type: str
    rules: tuple[MercyRule, ...]
    cutoff: str
    possessions: str
    possession_factor: float
    historical_comparison: bool
    historical_start: str
    cache_dir: Path
    request_delay: float
    timeout: int
    retries: int
    output_dir: Path
    charts: bool

    def expected_games(self, season):
        if self.season_type != "Regular Season":
            return None  # playoff game counts vary
        return EXPECTED_GAMES.get(season, 1230)


def check_season(season):
    """Seasons look like 2024-25."""
    if not re.fullmatch(r"\d{4}-\d{2}", season) or (
        int(season[-2:]) != (int(season[:4]) + 1) % 100
    ):
        raise ValueError(f"Invalid season {season!r}, expected e.g. 2024-25")
    return season


def parse_tier(item, default_name):
    tier = Tier(
        name=str(item.get("name", default_name)),
        min_lead=int(item["min_lead"]),
        max_seconds_remaining=float(item["max_seconds_remaining"]),
        periods=tuple(int(p) for p in item.get("periods", [4])),
    )
    if tier.min_lead <= 0:
        raise ValueError(f"{tier.name}: min_lead must be positive")
    if tier.max_seconds_remaining < 0:
        raise ValueError(f"{tier.name}: max_seconds_remaining cannot be negative")
    if not tier.periods or any(p < 1 for p in tier.periods):
        raise ValueError(f"{tier.name}: invalid periods")
    return tier


def parse_rule(item):
    rule_id = str(item["id"])
    if not re.fullmatch(r"[A-Za-z0-9_-]+", rule_id):
        raise ValueError(f"Rule id {rule_id!r} must be letters, digits, _ or -")

    # A rule either lists tiers, or is itself a single condition.
    raw_tiers = item.get("tiers") or [item]
    tiers = tuple(parse_tier(t, rule_id) for t in raw_tiers)

    return MercyRule(
        id=rule_id,
        name=str(item.get("name", rule_id)),
        tiers=tiers,
    )


def load_config(path: str | Path) -> Settings:
    path = Path(path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Configuration must be a YAML mapping")

    exp = raw["experiment"]
    analysis = raw.get("analysis", {})
    data = raw.get("data", {})
    output = raw.get("output", {})

    rules = tuple(parse_rule(item) for item in raw.get("rules", []))
    if not rules:
        raise ValueError("Configure at least one mercy rule")
    if len({r.id for r in rules}) != len(rules):
        raise ValueError("Rule ids must be unique")

    seasons = tuple(check_season(str(s)) for s in exp["seasons"])
    if not seasons:
        raise ValueError("At least one season required")

    season_type = exp.get("season_type", "Regular Season")
    if season_type not in ("Regular Season", "Playoffs"):
        raise ValueError("season_type must be 'Regular Season' or 'Playoffs'")

    cutoff = analysis.get("cutoff", "possession")
    if cutoff not in CUTOFF_MODES:
        raise ValueError(f"analysis.cutoff must be one of {CUTOFF_MODES}")

    possessions = analysis.get("possessions", "tracked")
    if possessions not in POSSESSION_METHODS:
        raise ValueError(
            f"analysis.possessions must be one of {POSSESSION_METHODS}"
        )

    factor = float(analysis.get("possession_factor", 0.44))
    if not 0 <= factor <= 1:
        raise ValueError("possession_factor must be between 0 and 1")

    # Relative paths are relative to config.yaml, not the terminal.
    root = path.resolve().parent

    def local_path(value):
        p = Path(value)
        return p if p.is_absolute() else root / p

    return Settings(
        name=str(exp.get("name", "NBA Mercy Rule")),
        seasons=seasons,
        season_type=season_type,
        rules=rules,
        cutoff=cutoff,
        possessions=possessions,
        possession_factor=factor,
        historical_comparison=bool(
            analysis.get("historical_comparison", False)
        ),
        historical_start=check_season(
            str(analysis.get("historical_start", "1996-97"))
        ),
        cache_dir=local_path(data.get("cache_dir", "data/cache")),
        request_delay=float(data.get("request_delay", 0.8)),
        timeout=int(data.get("timeout", 35)),
        retries=int(data.get("retries", 3)),
        output_dir=local_path(output.get("directory", "output")),
        charts=bool(output.get("charts", True)),
    )
