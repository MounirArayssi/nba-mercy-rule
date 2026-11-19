"""
Count possessions from play-by-play.

A possession belongs to the team with the ball. It ends when the other
team gets the ball, or when the period ends:

    made field goal ............. ends the shooting team's possession
    defensive rebound ........... ends the shooting team's possession
    turnover .................... ends the team's possession
    last free throw of a trip ... ends it if made (a miss is a live ball)
    end of period ............... ends whatever possession is in progress

Special cases:

* Technical free throws are ignored. They don't change who has the ball.
* Flagrant and clear-path free throws never end a possession, because
  the fouled team keeps the ball afterwards.
* An and-one free throw does not start a new possession. The made
  basket already ended it.
* A possession only counts if the team did something with the ball
  (a shot, free throw or turnover), or if it was still going when the
  period ended. This skips "phantom" possessions created by gaps in
  the play-by-play.

Checked against NBA.com's official possession counts on 30 games
(60 team-games) from 2025-26: 47 match exactly and the rest are off
by one. Run `python check_possessions.py` to repeat the check.

The tracker sees one action at a time and reports which team's
possession (if any) ended on that action.
"""

from __future__ import annotations

import re


FREE_THROW_NUMBER = re.compile(r"(\d+) of (\d+)")

# Actions that prove a team has the ball.
OFFENSIVE_ACTIONS = {
    "made shot", "missed shot", "turnover", "heave",
}


class PossessionTracker:
    """Follows which team has the ball, one action at a time."""

    def __init__(self, home_id: int, away_id: int):
        self.home_id = home_id
        self.away_id = away_id
        self.holder: int | None = None  # team with the ball
        self.used = False  # has the holder done anything yet?

    def other(self, team: int) -> int:
        return self.away_id if team == self.home_id else self.home_id

    def update(self, kind, subtype, team, made=False) -> list[int]:
        """
        Process one action and return the teams whose possession ended
        on it. Usually empty or one team. It can be two if the play-by-play
        skipped a change of possession.

        kind     lower-case NBA actionType ("made shot", "rebound", ...)
        subtype  lower-case NBA subType ("free throw 2 of 2", "end", ...)
        team     team id that made the action, or None
        made     True for a made free throw
        """
        ended: list[int] = []

        if kind == "period":
            # NBA counts the possession still going when a period ends,
            # even if the team never got a shot off.
            if subtype == "end" and self.holder is not None:
                self.used = True
            self._give(None, ended)
            return ended

        if team not in (self.home_id, self.away_id):
            return ended

        if kind == "free throw":
            self._free_throw(subtype, team, made, ended)

        elif kind in OFFENSIVE_ACTIONS:
            self._take(team, ended)
            if kind in ("made shot", "turnover"):
                self._give(self.other(team), ended)

        elif kind == "rebound":
            # Whoever rebounds has the ball. If that is the defense, the
            # shooting team's possession is over.
            self._give(team, ended)

        return ended

    # -- helpers ---------------------------------------------------------

    def _give(self, team, ended):
        """Hand the ball to `team`, closing the current possession."""
        if team == self.holder:
            return
        if self.holder is not None and self.used:
            ended.append(self.holder)
        self.holder = team
        self.used = False

    def _take(self, team, ended):
        """`team` is acting with the ball, so it must have possession."""
        self._give(team, ended)
        self.used = True

    def _free_throw(self, subtype, team, made, ended):
        if "technical" in subtype:
            return

        match = FREE_THROW_NUMBER.search(subtype)
        if not match:
            return

        attempt, total = int(match[1]), int(match[2])
        keeps_ball = "flagrant" in subtype or "clear path" in subtype

        # And-one: the basket already gave the ball to the other team.
        # A miss is a live ball and the rebound decides who gets it.
        if total == 1 and self.holder == self.other(team):
            return

        self._take(team, ended)

        if attempt == total and made and not keeps_ball:
            self._give(self.other(team), ended)
