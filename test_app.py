import itertools
import random
import unittest
from app import app, get_hand_rank, compare_hands, get_deck, simulate_equity, analyze_draw_potential


def cards(text):
    return [dict(rank=c[:-1], suit=c[-1], code=c) for c in text.split()]


class PokerTests(unittest.TestCase):
    def test_categories(self):
        cases = [('A♠ K♠ Q♠ J♠ 10♠ 2♥ 3♦', 1),
                 ('9♠ 8♠ 7♠ 6♠ 5♠ A♥ K♦', 2),
                 ('A♠ A♥ A♣ A♦ K♠ 2♥ 3♦', 3),
                 ('A♠ A♥ A♣ K♦ K♠ K♥ 3♦', 4),
                 ('A♠ J♠ 8♠ 6♠ 2♠ K♥ 3♦', 5),
                 ('A♠ 2♥ 3♣ 4♦ 5♠ K♥ Q♦', 6),
                 ('A♠ A♥ A♣ J♦ 9♠ 4♥ 3♦', 7),
                 ('A♠ A♥ K♣ K♦ Q♠ Q♥ 3♦', 8),
                 ('A♠ A♥ K♣ J♦ 9♠ 4♥ 3♦', 9),
                 ('A♠ K♥ J♣ 9♦ 7♠ 4♥ 3♦', 10)]
        for text, category in cases:
            with self.subTest(text=text):
                self.assertEqual(get_hand_rank(cards(text))[0], category)

    def test_kickers_and_wheel(self):
        self.assertEqual(compare_hands(cards('A♠ A♥ K♣ J♦ 9♠'), cards('K♠ K♥ A♣ J♦ 9♣')), 1)
        self.assertEqual(compare_hands(cards('A♠ A♥ K♣ J♦ 9♠'), cards('A♣ A♦ Q♣ J♥ 9♣')), 1)
        self.assertEqual(compare_hands(cards('A♠ 2♥ 3♣ 4♦ 5♠'), cards('2♠ 3♥ 4♣ 5♦ 6♠')), -1)
        self.assertEqual(get_hand_rank(cards('A♠ A♥ K♣ K♦ Q♠ Q♥ 3♦')), (8, -14, -13, -12))

    def test_seven_equals_best_five(self):
        rng = random.Random(42)
        for _ in range(3000):
            hand = rng.sample(get_deck(), 7)
            self.assertEqual(get_hand_rank(hand), min(get_hand_rank(list(c)) for c in itertools.combinations(hand, 5)))

    def test_split_equity(self):
        board = cards('A♠ K♠ Q♠ J♠ 10♠')
        for opponents in (1, 2, 8):
            result = simulate_equity(cards('2♥ 3♦'), board, opponents, 100)
            self.assertEqual(result['tie_rate'], 1)
            self.assertAlmostEqual(result['equity'], 1 / (opponents + 1))
        self.assertEqual(result['lose_rate'], 0)

    def test_unbeatable_royal(self):
        result = simulate_equity(cards('A♠ K♠'), cards('Q♠ J♠ 10♠ 2♥ 3♦'), 1)
        self.assertEqual(result['win_rate'], 1)
        self.assertEqual(result['samples'], 990)
        self.assertEqual(result['method'], 'exact')

    def test_draws(self):
        hole = cards('A♠ 8♠')
        result = analyze_draw_potential(hole, cards('2♠ 5♠ K♥'))
        self.assertEqual(result['total_outs'], 9)
        self.assertAlmostEqual(result['improve_prob'], (1 - 38 * 37 / (47 * 46)) * 100, places=2)
        result = analyze_draw_potential(hole, cards('2♠ 5♠ K♥ Q♦'))
        self.assertAlmostEqual(result['improve_prob'], 9 / 46 * 100, places=2)
        self.assertEqual(analyze_draw_potential(hole, cards('2♠ 5♠ K♥ Q♦ 3♣'))['total_outs'], 0)
        result = analyze_draw_potential(cards('8♠ 9♠'), cards('6♠ 7♥ K♠'))
        self.assertEqual(result['total_outs'], 15)  # 同花9 + 顺子8，重叠2

    def test_api_validation_and_ev(self):
        client = app.test_client()
        payload = dict(hole=cards('2♥ 3♦'), community=cards('A♠ K♠ Q♠ J♠ 10♠'),
                       opponent_count=1, mode='advanced', pot=100, call_amount=20)
        result = client.post('/api/calculate', json=payload)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json['ev'], 40)  # 共享底池权益为一半
        for change in (dict(opponent_count=0), dict(opponent_count=True), dict(pot=-1),
                       dict(hole=cards('2♥ 2♥')), dict(community=cards('A♠') + [None] * 4)):
            with self.subTest(change=change):
                self.assertEqual(client.post('/api/calculate', json={**payload, **change}).status_code, 400)
        self.assertEqual(client.post('/api/calculate', json=[]).status_code, 400)


if __name__ == '__main__':
    unittest.main()
