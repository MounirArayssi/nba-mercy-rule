"""
Core mercy-rule logic.

1. parse_game()     turns raw play-by-play into a list of Event objects.
                    Each one records the stats it adds for each team.
2. find_cutoff()    finds where a mercy rule would have ended the game.
3. simulate_game()  totals each team's stats for the real game and for
                    the shortened game.

Nothing here touches the network or pandas, so it is easy to unit test.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from src.possessions import PossessionTracker


# Stats tracked for every team in every game. "poss" is the number of
# possessions counted by src/possessions.py.
STATS = (
    "pts", "fga", "fgm", "fg3a", "fg3m",
    "fta", "ftm", "oreb", "tov", "poss",
)


@dataclass(frozen=True)
class Event:
    period: int
    seconds: float          # seconds left in the period
    home_score: int
    away_score: int
    action_number: int
    kind: str               # lower-case actionType, e.g. "made shot"
    ends_possession: bool   # a possession ended on this event
    stats: dict[int, dict[str, float]]  # stat changes, keyed by team id

    @property
    def margin(self):
        """Home lead (negative when the away team leads)."""
        return self.home_score - self.away_score


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def clock_seconds(value):
    """Convert an NBA v3 clock like PT03M21.00S to seconds (201.0)."""
    match = re.fullmatch(
        r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?",
        str(value),
    )
    if not match:
        raise ValueError(f"Invalid NBA clock: {value}")
    return (
        int(match[1] or 0) * 3600
        + int(match[2] or 0) * 60
        + float(match[3] or 0)
    )


def safe_score(value, previous):
    """Play-by-play only fills in the score on scoring plays."""
    if value is None or str(value).strip() in ("", "nan", "None"):
        return previous
    return int(float(value))


def event_team(row, home_id, away_id):
    """
    Return the team id an action belongs to, or None.

    Team-level actions (team rebounds, shot-clock turnovers, timeouts)
    have teamId 0 in v3 play-by-play. Their `location` ("h"/"v") still
    tells us the side, and personId holds the team id.
    """
    location = str(row.get("location") or "").lower()
    if location == "h":
        return home_id
    if location == "v":
        return away_id

    for key in ("teamId", "personId"):
        try:
            value = int(row.get(key) or 0)
        except (TypeError, ValueError):
            continue
        if value in (home_id, away_id):
            return value
    return None


def is_team_action(row, home_id, away_id):
    """True for team (not player) rebounds and turnovers."""
    try:
        person = int(row.get("personId") or 0)
    except (TypeError, ValueError):
        return True
    return person == 0 or person in (home_id, away_id)


def empty_stats():
    return {stat: 0.0 for stat in STATS}


def parse_game(payload, home_id, away_id):
    """
    Normalize a PlayByPlayV3 payload into chronological Events.

    Returns (events, final), where `final` has the reconstructed final
    score. Points come from scoreboard changes, so score corrections are
    handled automatically.
    """
    actions = payload.get("game", {}).get("actions", [])
    if not actions:
        raise ValueError("Empty play-by-play")

    # actionId is the chronological order. actionNumber is not: events
    # entered late (e.g. replay corrections) get high actionNumbers.
    actions = sorted(
        actions,
        key=lambda x: int(x.get("actionId", x.get("actionNumber", 0))),
    )

    tracker = PossessionTracker(home_id, away_id)
    events = []
    home_score = away_score = 0
    last_miss_team = None  # used to spot offensive rebounds

    for row in actions:
        period = int(row["period"])
        seconds = clock_seconds(row["clock"])
        kind = str(row.get("actionType") or "").lower()
        subtype = str(row.get("subType") or "").lower()
        team = event_team(row, home_id, away_id)

        old_home, old_away = home_score, away_score
        new_home = safe_score(row.get("scoreHome"), home_score)
        new_away = safe_score(row.get("scoreAway"), away_score)
        # Older feeds (2015-16, 2016-17) write "0" instead of a blank on
        # non-scoring plays. A 0-0 score after anyone has scored is one of
        # those placeholders, not a real score, so keep the previous one.
        if not (new_home == new_away == 0 and (home_score or away_score)):
            home_score, away_score = new_home, new_away

        delta = {home_id: empty_stats(), away_id: empty_stats()}

        def add(stat, value=1):
            if team in delta:
                delta[team][stat] += value

        made = False

        if kind in ("made shot", "missed shot"):
            made = kind == "made shot"
            add("fga")
            add("fgm", made)
            if int(row.get("shotValue") or 0) == 3:
                add("fg3a")
                add("fg3m", made)

        elif kind == "free throw":
            # Misses read "MISS Smith Free Throw 1 of 2". The trailing
            # space matters: "Missi Free Throw" is a make. Score changes
            # are unreliable here because free throws are sometimes
            # logged out of order.
            description = str(row.get("description") or "").lower()
            made = not description.startswith("miss ")
            add("fta")
            add("ftm", made)

        elif kind == "turnover" and not is_team_action(row, home_id, away_id):
            # Player turnovers only, matching the official box score.
            # Team turnovers (shot clock, 8 seconds) still end
            # possessions in the tracker.
            add("tov")

        # Offensive rebounds, counted like the official box score:
        # player rebounds only, after the same team missed.
        if kind == "rebound":
            if (
                team is not None
                and team == last_miss_team
                and not is_team_action(row, home_id, away_id)
            ):
                add("oreb")
            last_miss_team = None
        elif kind == "missed shot" or (kind == "free throw" and not made):
            last_miss_team = team
        elif kind in ("made shot", "free throw", "turnover", "period"):
            last_miss_team = None

        ended = tracker.update(kind, subtype, team, made)
        for team_id in ended:
            delta[team_id]["poss"] += 1

        delta[home_id]["pts"] += home_score - old_home
        delta[away_id]["pts"] += away_score - old_away

        events.append(Event(
            period=period,
            seconds=seconds,
            home_score=home_score,
            away_score=away_score,
            action_number=int(
                row.get("actionNumber", row.get("actionId", 0))
            ),
            kind=kind,
            ends_possession=bool(ended),
            stats=delta,
        ))

    if events[-1].period < 4:
        raise ValueError("Game appears incomplete")
    if home_score == away_score:
        raise ValueError("Game ended tied or incomplete")

    return events, {"home_score": home_score, "away_score": away_score}


# ---------------------------------------------------------------------------
# Applying a rule
# ---------------------------------------------------------------------------

def find_trigger(events, rule):
    """Index of the first event where the rule's conditions are met."""
    for index, event in enumerate(events):
        if rule.matches(event.period, event.seconds, event.margin):
            return index
    return None


def find_cutoff(events, rule, mode="possession"):
    """
    Return (trigger_index, last_kept_index), or (None, None).

    mode="event"       stop right on the triggering event.
    mode="possession"  let the possession in progress finish, so no team
                       is left with half a possession. Free throws awarded
                       at the same moment (and-ones, technicals) are kept.
    """
    trigger = find_trigger(events, rule)
    if trigger is None:
        return None, None
    if mode == "event":
        return trigger, trigger
    if mode != "possession":
        raise ValueError(f"Unknown cutoff mode: {mode}")

    last = len(events) - 1
    end = trigger
    while end < last and not events[end].ends_possession:
        end += 1

    # Keep free throws shot at the same moment, e.g. an and-one.
    stop = events[end]
    scan = end + 1
    while (
        scan <= last
        and events[scan].period == stop.period
        and events[scan].seconds == stop.seconds
    ):
        if events[scan].kind == "free throw":
            end = scan
        scan += 1

    return trigger, end


def sum_events(events, home_id, away_id):
    """Total the stats of a list of events, by team id."""
    totals = {home_id: empty_stats(), away_id: empty_stats()}
    for event in events:
        for team_id, stats in event.stats.items():
            for name, value in stats.items():
                totals[team_id][name] += value
    return totals


def simulate_game(events, game, season, rule, mode="possession"):
    """
    Apply one rule to one game.

    Returns (metadata, rows): one metadata dict for the game and one
    row per team holding actual_*, mercy_* and removed_* stats.
    """
    home_id, away_id = game["home_id"], game["away_id"]

    trigger_index, end_index = find_cutoff(events, rule, mode)
    triggered = trigger_index is not None

    retained = events[:end_index + 1] if triggered else events
    actual_totals = sum_events(events, home_id, away_id)
    mercy_totals = sum_events(retained, home_id, away_id)

    actual_final = events[-1]
    mercy_final = retained[-1]
    trigger = events[trigger_index] if triggered else None
    tier = (
        rule.matching_tier(trigger.period, trigger.seconds, trigger.margin)
        if triggered else None
    )

    def winner(event):
        return home_id if event.margin > 0 else away_id

    metadata = {
        "season": season,
        "rule_id": rule.id,
        "game_id": game["game_id"],
        "home": game["home"],
        "away": game["away"],
        "triggered": triggered,
        "trigger_tier": tier.name if triggered else None,
        "trigger_period": trigger.period if triggered else None,
        "trigger_clock": trigger.seconds if triggered else None,
        "trigger_lead": abs(trigger.margin) if triggered else None,
        "cutoff_clock": mercy_final.seconds if triggered else None,
        "actual_home": actual_final.home_score,
        "actual_away": actual_final.away_score,
        "mercy_home": mercy_final.home_score,
        "mercy_away": mercy_final.away_score,
        "events_removed": len(events) - len(retained),
        "actual_winner_id": winner(actual_final),
        "mercy_winner_id": winner(mercy_final),
        "comeback_erased": winner(mercy_final) != winner(actual_final),
        # Positive: the leader's margin shrank after the cutoff.
        "lead_eroded": (
            abs(mercy_final.margin) - abs(actual_final.margin)
            if triggered else 0
        ),
    }

    rows = []
    for team_id, team_name, opponent_id in (
        (home_id, game["home"], away_id),
        (away_id, game["away"], home_id),
    ):
        row = {
            "season": season,
            "rule_id": rule.id,
            "game_id": game["game_id"],
            "team_id": team_id,
            "team": team_name,
            "opponent_id": opponent_id,
            "triggered": triggered,
        }
        for stat in STATS:
            actual = actual_totals[team_id][stat]
            mercy = mercy_totals[team_id][stat]
            row[f"actual_{stat}"] = actual
            row[f"mercy_{stat}"] = mercy
            row[f"removed_{stat}"] = actual - mercy
        rows.append(row)

    return metadata, rows
