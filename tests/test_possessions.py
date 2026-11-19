import unittest

from src.possessions import PossessionTracker
from tests.helpers import AWAY, HOME


class TestPossessionTracker(unittest.TestCase):

    def setUp(self):
        self.t = PossessionTracker(HOME, AWAY)
        self.t.update("period", "start", None)

    def play(self, *actions):
        """Run (kind, subtype, team, made) tuples; return all ended teams."""
        ended = []
        for kind, subtype, team, *made in actions:
            ended += self.t.update(kind, subtype, team, bool(made and made[0]))
        return ended

    def test_made_shot_ends_possession(self):
        self.assertEqual(self.play(("made shot", "", HOME)), [HOME])
        self.assertEqual(self.t.holder, AWAY)

    def test_defensive_rebound_ends_possession(self):
        ended = self.play(("missed shot", "", HOME), ("rebound", "", AWAY))
        self.assertEqual(ended, [HOME])

    def test_offensive_rebound_continues(self):
        ended = self.play(
            ("missed shot", "", HOME), ("rebound", "", HOME),
            ("made shot", "", HOME),
        )
        self.assertEqual(ended, [HOME])

    def test_turnover_ends_possession(self):
        self.assertEqual(self.play(("turnover", "bad pass", AWAY)), [AWAY])

    def test_free_throw_trip(self):
        ended = self.play(
            ("free throw", "free throw 1 of 2", HOME, True),
            ("free throw", "free throw 2 of 2", HOME, True),
        )
        self.assertEqual(ended, [HOME])

    def test_missed_last_free_throw_is_live(self):
        ended = self.play(
            ("free throw", "free throw 1 of 2", HOME, True),
            ("free throw", "free throw 2 of 2", HOME, False),
        )
        self.assertEqual(ended, [])
        self.assertEqual(self.play(("rebound", "", AWAY)), [HOME])

    def test_and_one_is_not_a_new_possession(self):
        ended = self.play(
            ("made shot", "", HOME),
            ("free throw", "free throw 1 of 1", HOME, True),
            ("made shot", "", AWAY),
        )
        self.assertEqual(ended, [HOME, AWAY])

    def test_technical_free_throw_ignored(self):
        self.play(("missed shot", "", HOME))
        ended = self.play(("free throw", "free throw technical", AWAY, True))
        self.assertEqual(ended, [])
        self.assertEqual(self.t.holder, HOME)

    def test_flagrant_keeps_ball(self):
        ended = self.play(
            ("free throw", "free throw flagrant 1 of 2", HOME, True),
            ("free throw", "free throw flagrant 2 of 2", HOME, True),
        )
        self.assertEqual(ended, [])
        self.assertEqual(self.t.holder, HOME)

    def test_period_end_counts_possession_in_progress(self):
        self.play(("missed shot", "", HOME), ("rebound", "", AWAY))
        self.assertEqual(self.play(("period", "end", None)), [AWAY])
        self.assertIsNone(self.t.holder)

    def test_missing_change_of_possession_is_inferred(self):
        # Home shoots, then away shoots without a logged rebound.
        ended = self.play(("missed shot", "", HOME), ("missed shot", "", AWAY))
        self.assertEqual(ended, [HOME])


if __name__ == "__main__":
    unittest.main()
