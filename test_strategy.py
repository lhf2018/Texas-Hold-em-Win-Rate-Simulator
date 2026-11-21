import copy
import random
import unittest
from bots import decide
from game import Game
from ranges import distributions
from test_app import cards


class StrategyTests(unittest.TestCase):
    def test_per_player_last_raise_locks_everyone_and_resets(self):
        g = Game(1)
        g.start_hand()
        self.assertEqual(g.rule_mode, 'per_player')
        # 初始顺序 3 -> 0 -> 1 -> 2；0 和 1 尚未使用加注机会。
        g.act(3, 'raise', 40)
        g.act(0, 'call')
        g.act(1, 'call')
        self.assertTrue(g.legal(2)['can_raise'])
        g.act(2, 'raise', 80)
        self.assertTrue(g.raises_closed)
        for seat in (3, 0, 1):
            self.assertEqual(g.actor, seat)
            self.assertFalse(g.legal(seat)['can_raise'])
            self.assertIn('最后一位', g.legal(seat)['raise_reason'])
            before = copy.deepcopy(g.public_view())
            with self.assertRaises(ValueError):
                g.act(seat, 'raise', 160)
            self.assertEqual(before, g.public_view())
            g.act(seat, 'call')
        self.assertEqual(g.street, 1)
        self.assertFalse(g.raises_closed)
        self.assertEqual(g.raised_seats, set())
        # 翻牌后顺序 1 -> 2 -> 3 -> 0，最后一位同样有加注权。
        for seat in (1, 2, 3):
            g.act(seat, 'check')
        g.act(0, 'raise', 40)
        self.assertTrue(g.raises_closed)
        self.assertFalse(g.legal(1)['can_raise'])

    def test_per_player_cannot_raise_twice_even_before_lock(self):
        g = Game(1)
        g.start_hand()
        g.act(3, 'raise', 40)
        g.act(0, 'raise', 80)
        g.act(1, 'call')
        g.act(2, 'call')
        self.assertFalse(g.raises_closed)
        self.assertEqual(g.actor, 3)
        self.assertFalse(g.legal(3)['can_raise'])
        self.assertIn('已加注一次', g.legal(3)['raise_reason'])
        g.act(3, 'call')
        self.assertEqual(g.street, 1)

    def test_per_player_unused_raise_survives_if_last_player_only_calls(self):
        g = Game(1)
        g.start_hand()
        g.act(3, 'call')
        g.act(0, 'raise', 60)
        g.act(1, 'call')
        g.act(2, 'call')
        self.assertEqual(g.actor, 3)
        self.assertFalse(g.raises_closed)
        self.assertTrue(g.legal(3)['can_raise'])
        g.act(3, 'raise', 100)
        self.assertFalse(g.legal(0)['can_raise'])
        g.act(0, 'call')
        self.assertTrue(g.legal(1)['can_raise'])

    def test_per_player_heads_up_last_allin_closes_raise_rights(self):
        g = Game(1, player_count=2)
        g.start_hand()
        g.act(0, 'call')
        g.players[1]['stack'] = 10
        g.act(1, 'raise', 30)
        self.assertTrue(g.raises_closed)
        self.assertFalse(g.legal(0)['can_raise'])
        g.act(0, 'call')
        self.assertTrue(g.done)
        self.assertEqual(len(g.board), 5)

    def test_standard_reraise_and_short_allin_does_not_reopen(self):
        g = Game(1, rule_mode='standard')
        g.start_hand()
        g.act(3, 'raise', 100)
        g.act(0, 'raise', 200)
        g.act(1, 'call')
        g.players[2]['stack'] = 230-g.players[2]['bet']
        g.act(2, 'raise', 230)
        g.act(3, 'call')
        self.assertFalse(g.legal(0)['can_raise'])
        self.assertEqual(g.actor, 0)

    def test_raise_reasons_and_full_reraise(self):
        practice = Game(1, rule_mode='practice')
        practice.start_hand()
        practice.act(3, 'raise', 100)
        self.assertIn('练习模式', practice.legal(0)['raise_reason'])
        g = Game(1, rule_mode='standard')
        g.start_hand()
        g.act(3, 'raise', 100)
        self.assertTrue(g.legal(0)['can_raise'])
        self.assertEqual(g.legal(0)['min_raise_to'], 180)
        g.act(0, 'raise', 180)
        g.act(1, 'call')
        g.act(2, 'raise', 300)
        self.assertTrue(g.legal(3)['can_raise'])
        self.assertEqual(g.legal(3)['min_raise_to'], 420)
        g.players[3]['stack'] = 100
        self.assertFalse(g.legal(3)['can_raise'])
        self.assertIn('仅够跟注', g.legal(3)['raise_reason'])

    def test_cumulative_short_raises_reopen_rights(self):
        g = Game(1, rule_mode='standard')
        g.start_hand()
        g.act(3, 'raise', 100)
        g.act(0, 'call')
        g.players[1]['stack'] = 140-g.players[1]['bet']
        g.act(1, 'raise', 140)
        g.players[2]['stack'] = 180-g.players[2]['bet']
        g.act(2, 'raise', 180)
        self.assertTrue(g.legal(3)['can_raise'])
        self.assertEqual(g.legal(3)['min_raise_to'], 260)

    def test_no_raise_into_allin_opponents(self):
        g = Game(1, player_count=2, rule_mode='standard')
        g.start_hand()
        g.players[0]['stack'] = 90
        g.act(0, 'raise', 100)
        self.assertFalse(g.legal(1)['can_raise'])
        self.assertIn('均已全下', g.legal(1)['raise_reason'])

    def test_privacy_and_determinism(self):
        g = Game(4)
        g.start_hand()
        seat = g.actor
        before = g.decision_view(seat)
        for i,p in enumerate(g.players):
            if i != seat:
                p['hole'] = cards('A♠ A♥')
        g.deck.reverse()
        self.assertEqual(before, g.decision_view(seat))
        profile = g.bot_profiles[seat]
        a = decide(before, seat, profile, random.Random(1), min_samples=64, max_samples=64)
        b = decide(g.decision_view(seat), seat, profile, random.Random(1), min_samples=64, max_samples=64)
        self.assertEqual(a,b)
        self.assertEqual(g.public_view()['review'], [])

    def test_statistics_persist_and_count_once_per_hand(self):
        g = Game(2, rule_mode='standard')
        g.start_hand()
        g.act(3,'raise',40)
        g.act(0,'raise',80)
        g.act(1,'fold')
        g.act(2,'call')
        g.act(3,'call')
        self.assertEqual(g.stats[3]['vpip'],1)
        self.assertEqual(g.stats[3]['pfr'],1)
        self.assertEqual(g.stats[1]['folds'],1)
        while not g.done:
            g.act(g.actor,'fold')
        g.start_hand()
        self.assertEqual(g.stats[3]['hands'],2)
        self.assertEqual(g.stats[3]['pfr'],1)

    def test_pressure_changes_range(self):
        hero = cards('2♠ 3♥')
        _,_,base = distributions(hero,[],[1],[])
        event = dict(seat=1, action='加注到', board=[], amount=200, pot=230)
        _,_,weighted = distributions(hero,[],[1],[event])
        self.assertNotEqual(base,weighted)

    def test_river_nuts_does_not_fold(self):
        g = Game(3,player_count=2)
        g.start_hand()
        seat = g.actor
        v = g.decision_view(seat)
        v['board'] = cards('A♠ K♠ Q♠ J♠ 2♥')
        v['players'][seat]['hole'] = cards('10♠ 3♥')
        v['street'] = 3
        v['legal']['call'] = 20
        action,_,report = decide(v,seat,dict(looseness=0,aggression=.5),random.Random(4),min_samples=64,max_samples=128)
        self.assertNotEqual(action,'fold')
        self.assertEqual(report['equity'],100)
        self.assertLessEqual(report['samples'],128)


if __name__ == '__main__':
    unittest.main()
