import unittest

from src.analysis import aggregate_ratings, validate_game
from src.core import STATS
from tests.helpers import AWAY, HOME


def row(game_id, team_id, opponent_id, actual, mercy, triggered=True):
    """Team-game row with only pts/poss set (other stats zero)."""
    r = {
        "season": "2025-26", "rule_id": "r", "game_id": game_id,
        "team_id": team_id, "team": str(team_id),
        "opponent_id": opponent_id, "triggered": triggered,
    }
    for stat in STATS:
        r[f"actual_{stat}"] = actual.get(stat, 0)
        r[f"mercy_{stat}"] = mercy.get(stat, 0)
        r[f"removed_{stat}"] = r[f"actual_{stat}"] - r[f"mercy_{stat}"]
    return r


class TestRatings(unittest.TestCase):

    def setUp(self):
        # Home wins 120-90 on 100 possessions each. The rule removes 10
        # home possessions (10 pts) and 10 away possessions (15 pts).
        self.rows = [
            row("g1", HOME, AWAY, {"pts": 120, "poss": 100}, {"pts": 110, "poss": 90}),
            row("g1", AWAY, HOME, {"pts": 90, "poss": 100}, {"pts": 75, "poss": 90}),
        ]
        self.ratings = aggregate_ratings(self.rows).set_index("team_id")

    def test_actual_ratings(self):
        home = self.ratings.loc[HOME]
        self.assertAlmostEqual(home.actual_ortg, 120.0)
        self.assertAlmostEqual(home.actual_drtg, 90.0)
        self.assertAlmostEqual(home.actual_net, 30.0)

    def test_mercy_ratings(self):
        home = self.ratings.loc[HOME]
        self.assertAlmostEqual(home.mercy_ortg, 100 * 110 / 90)
        self.assertAlmostEqual(home.mercy_drtg, 100 * 75 / 90)
        self.assertAlmostEqual(home.delta_net, 100 * 35 / 90 - 30)

    def test_ranks_and_counts(self):
        self.assertEqual(self.ratings.loc[HOME].mercy_rank, 1)
        self.assertEqual(self.ratings.loc[AWAY].mercy_rank, 2)
        self.assertEqual(self.ratings.loc[HOME].games_cut, 1)

    def test_estimate_method(self):
        rows = [
            row("g1", HOME, AWAY, {"pts": 100, "fga": 90, "oreb": 10, "tov": 10, "fta": 25},
                {"pts": 100, "fga": 90, "oreb": 10, "tov": 10, "fta": 25}),
            row("g1", AWAY, HOME, {"pts": 99, "fga": 99}, {"pts": 99, "fga": 99}),
        ]
        ratings = aggregate_ratings(rows, method="estimate").set_index("team_id")
        self.assertAlmostEqual(ratings.loc[HOME].actual_poss, 90 - 10 + 10 + 11)


class TestValidation(unittest.TestCase):

    def test_reports_mismatch(self):
        rows = [
            row("g1", HOME, AWAY, {"pts": 100, "fga": 80}, {}),
            row("g1", AWAY, HOME, {"pts": 90}, {}),
        ]
        game = {"home_box": {"PTS": 100, "FGA": 81}, "away_box": {"PTS": 90}}
        self.assertEqual(validate_game(game, rows), [f"{HOME} FGA: pbp=80, box=81"])


if __name__ == "__main__":
    unittest.main()
