import unittest

from src.config import MercyRule, Tier
from src.core import clock_seconds, find_cutoff, parse_game, simulate_game
from tests.helpers import AWAY, GAME, HOME, action, payload


def single(name, lead, seconds):
    """A rule with one tier."""
    return MercyRule(name, name, (Tier(name, lead, seconds),))


MODERATE = single("moderate", 25, 210)
AGGRESSIVE = single("aggressive", 20, 480)
IMPOSSIBLE = single("impossible", 50, 60)

TIERED = MercyRule("tiered", "Tiered", (
    Tier("extreme", 40, 510),
    Tier("aggressive", 30, 270),
    Tier("moderate", 25, 210),
))


def sample_actions():
    """
    Home leads 108-80 at 5:00 of Q4, scores to go up 30 at 3:20, then the
    away team hits a three and the game ends 117-99.
    """
    return [
        action(1, "PT12M00.00S", "period", subtype="start"),
        action(1, "PT00M01.00S", "timeout", home=30, away=20),
        action(1, "PT00M00.00S", "period", subtype="end"),
        action(4, "PT12M00.00S", "period", subtype="start"),
        action(4, "PT05M00.00S", "timeout", home=108, away=80),            # 4
        action(4, "PT03M20.00S", "made shot", HOME, home=110, away=80,
               shot_value=2),                                               # 5
        action(4, "PT02M00.00S", "made shot", AWAY, home=110, away=83,
               shot_value=3),                                               # 6
        action(4, "PT00M00.00S", "timeout", home=117, away=99),            # 7
        action(4, "PT00M00.00S", "period", subtype="end"),                 # 8
    ]


def parse(actions):
    return parse_game(payload(actions), HOME, AWAY)[0]


def team_row(rows, team_id):
    return next(r for r in rows if r["team_id"] == team_id)


class TestParsing(unittest.TestCase):

    def test_clock(self):
        self.assertEqual(clock_seconds("PT03M20.00S"), 200)
        self.assertEqual(clock_seconds("PT00M00.40S"), 0.4)

    def test_final_score(self):
        _, final = parse_game(payload(sample_actions()), HOME, AWAY)
        self.assertEqual((final["home_score"], final["away_score"]), (117, 99))

    def test_sorted_by_action_id(self):
        # actionNumber is not chronological in real data; actionId is.
        data = payload(sample_actions())
        for row in data["game"]["actions"]:
            row["actionNumber"] = 1000 - row["actionId"]
        events, _ = parse_game(data, HOME, AWAY)
        self.assertEqual(events[-1].period, 4)

    def test_team_turnover_ends_possession_but_not_box_tov(self):
        events = parse([
            action(4, "PT12M00.00S", "period", subtype="start"),
            action(4, "PT11M30.00S", "made shot", HOME, home=2, shot_value=2),
            # Shot-clock violation: a team action (personId = team).
            action(4, "PT11M04.00S", "turnover", AWAY, person=0),
            action(4, "PT00M00.00S", "period", subtype="end"),
        ])
        away_tov = sum(e.stats[AWAY]["tov"] for e in events)
        away_poss = sum(e.stats[AWAY]["poss"] for e in events)
        self.assertEqual(away_tov, 0)
        self.assertEqual(away_poss, 1)

    def test_zero_score_placeholder_is_ignored(self):
        # 2015-17 feeds write "0"/"0" on non-scoring plays.
        events = parse([
            action(4, "PT12M00.00S", "period", subtype="start"),
            action(4, "PT05M00.00S", "made shot", HOME, home=110, away=80,
                   shot_value=2),
            action(4, "PT04M40.00S", "missed shot", AWAY, home=0, away=0),
            action(4, "PT04M30.00S", "made shot", AWAY, home=110, away=82,
                   shot_value=2),
            action(4, "PT00M00.00S", "period", subtype="end"),
        ])
        self.assertEqual((events[2].home_score, events[2].away_score), (110, 80))
        self.assertEqual(sum(e.stats[HOME]["pts"] for e in events[:3]), 110)
        self.assertEqual(sum(e.stats[AWAY]["pts"] for e in events), 82)

    def test_free_throw_made_comes_from_score(self):
        # A player named "Missi" must not read as a miss.
        row = action(4, "PT05M00.00S", "free throw", HOME,
                     subtype="Free Throw 1 of 1", home=1)
        row["description"] = "Missi Free Throw 1 of 1 (1 PTS)"
        events = parse([
            action(4, "PT12M00.00S", "period", subtype="start"),
            row,
            action(4, "PT00M00.00S", "period", subtype="end"),
        ])
        self.assertEqual(sum(e.stats[HOME]["ftm"] for e in events), 1)


class TestCutoff(unittest.TestCase):

    def setUp(self):
        self.events = parse(sample_actions())

    def test_first_qualifying_event(self):
        self.assertEqual(find_cutoff(self.events, MODERATE), (5, 5))

    def test_event_mode_stops_on_trigger(self):
        self.assertEqual(find_cutoff(self.events, AGGRESSIVE, "event"), (4, 4))

    def test_possession_mode_finishes_possession(self):
        # Triggered at a dead ball at 5:00. Home's next possession ends
        # with the made basket at 3:20.
        self.assertEqual(find_cutoff(self.events, AGGRESSIVE, "possession"), (4, 5))

    def test_no_trigger(self):
        self.assertEqual(find_cutoff(self.events, IMPOSSIBLE), (None, None))

    def test_mid_possession_trigger_waits_for_rebound(self):
        events = parse([
            action(4, "PT12M00.00S", "period", subtype="start"),
            action(4, "PT03M25.00S", "timeout", home=100, away=72),   # trigger
            action(4, "PT03M10.00S", "missed shot", HOME),
            action(4, "PT03M08.00S", "rebound", AWAY),               # cutoff
            action(4, "PT03M00.00S", "made shot", AWAY, home=100, away=74,
                   shot_value=2),
            action(4, "PT00M00.00S", "period", subtype="end"),
        ])
        self.assertEqual(find_cutoff(events, MODERATE), (1, 3))

    def test_and_one_free_throw_is_kept(self):
        actions = sample_actions()
        actions[6:6] = [
            action(4, "PT03M20.00S", "foul", AWAY),
            action(4, "PT03M20.00S", "free throw", HOME,
                   subtype="Free Throw 1 of 1", home=111, away=80),
        ]
        meta, _ = simulate_game(parse(actions), GAME, "2025-26", MODERATE)
        self.assertEqual((meta["mercy_home"], meta["mercy_away"]), (111, 80))


class TestTiers(unittest.TestCase):

    def test_first_satisfied_tier_ends_the_game(self):
        # Up 40 with 7:00 left ends the game on the extreme tier, even
        # though the lead is down to 27 with 3:00 left.
        events = parse([
            action(4, "PT12M00.00S", "period", subtype="start"),
            action(4, "PT07M00.00S", "timeout", home=100, away=60),   # 40 up
            action(4, "PT05M00.00S", "made shot", AWAY, home=100, away=63,
                   shot_value=3),
            action(4, "PT03M00.00S", "timeout", home=100, away=73),   # 27 up
            action(4, "PT00M00.00S", "period", subtype="end"),
        ])
        meta, _ = simulate_game(events, GAME, "2025-26", TIERED, "event")
        self.assertEqual(meta["trigger_tier"], "extreme")
        self.assertEqual(meta["trigger_clock"], 420)
        self.assertEqual((meta["mercy_home"], meta["mercy_away"]), (100, 60))

    def test_later_tier_when_earlier_never_met(self):
        meta, _ = simulate_game(parse(sample_actions()), GAME, "2025-26", TIERED)
        # Lead peaks at 30 with 3:20 left: aggressive (30 / 4:30) fires.
        self.assertEqual(meta["trigger_tier"], "aggressive")
        self.assertEqual(meta["trigger_clock"], 200)

    def test_simultaneous_tiers_report_first_listed(self):
        tier = TIERED.matching_tier(4, 60, 45)  # every tier is satisfied
        self.assertEqual(tier.name, "extreme")


class TestSimulateGame(unittest.TestCase):

    def setUp(self):
        self.events = parse(sample_actions())

    def test_removed_stats(self):
        meta, rows = simulate_game(self.events, GAME, "2025-26", MODERATE)
        self.assertTrue(meta["triggered"])
        self.assertEqual((meta["mercy_home"], meta["mercy_away"]), (110, 80))
        self.assertEqual(meta["events_removed"], 3)

        home, away = team_row(rows, HOME), team_row(rows, AWAY)
        self.assertEqual(home["mercy_pts"], 110)
        self.assertEqual(home["mercy_fgm"], 1)
        self.assertEqual(away["mercy_pts"], 80)
        self.assertEqual(away["removed_fga"], 1)
        self.assertEqual(away["removed_poss"], 1)

    def test_no_trigger_keeps_everything(self):
        meta, rows = simulate_game(self.events, GAME, "2025-26", IMPOSSIBLE)
        self.assertFalse(meta["triggered"])
        self.assertEqual((meta["mercy_home"], meta["mercy_away"]), (117, 99))
        self.assertEqual(team_row(rows, HOME)["removed_pts"], 0)

    def test_comeback_erased(self):
        actions = sample_actions()
        actions[7] = action(4, "PT00M00.00S", "timeout", home=117, away=120)
        meta, _ = simulate_game(parse(actions), GAME, "2025-26", MODERATE)
        self.assertTrue(meta["comeback_erased"])
        self.assertEqual(meta["mercy_winner_id"], HOME)
        self.assertEqual(meta["actual_winner_id"], AWAY)


if __name__ == "__main__":
    unittest.main()
