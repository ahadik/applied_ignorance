import unittest
from draft import score, snake_picks


class DraftTests(unittest.TestCase):
    def test_snake_turns(self):
        self.assertEqual(snake_picks(1, 14, 3), [1, 28, 29])
        self.assertEqual(snake_picks(14, 14, 3), [14, 15, 42])

    def test_league_specific_scoring(self):
        result = score({"pass_yd": 300, "pass_td": 2, "pass_int": 1},
                       {"pass_yd": .04, "pass_td": 4, "pass_int": -1})
        self.assertEqual(result["points"], 19)

    def test_unknown_stats_rejected(self):
        with self.assertRaises(ValueError):
            score({"touchdowns": 2}, {"pass_td": 4})

    def test_nonfinite_rejected(self):
        with self.assertRaises(ValueError):
            score({"rec": float("nan")}, {"rec": 1})


if __name__ == "__main__":
    unittest.main()
