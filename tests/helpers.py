"""Build fake PlayByPlayV3 actions for tests."""

HOME = 100
AWAY = 200

GAME = {
    "game_id": "0022500001",
    "home_id": HOME,
    "away_id": AWAY,
    "home": "Home",
    "away": "Away",
}


def action(period, clock, kind, team=None, subtype="", home="", away="",
           shot_value=0, person=1):
    """
    One play-by-play action. `team` is HOME, AWAY or None. Scores are
    only given on scoring plays, like the real feed. Pass person=0 for a
    team-level action (team rebound, shot-clock turnover).
    """
    location = {HOME: "h", AWAY: "v"}.get(team, "")
    return {
        "period": period,
        "clock": clock,
        "actionType": kind,
        "subType": subtype,
        "teamId": team if (team and person) else 0,
        "personId": person if team else 0,
        "location": location,
        "scoreHome": str(home),
        "scoreAway": str(away),
        "shotValue": shot_value,
        "description": "",
    }


def payload(actions):
    """Wrap actions in the v3 payload shape, numbering them in order."""
    for number, row in enumerate(actions, start=1):
        row["actionId"] = number
        row["actionNumber"] = number
    return {"game": {"actions": actions}}
