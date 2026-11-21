import copy
import random
import unittest
from bots import decide
from game import Game
from ranges import distributions
from test_app import cards


class StrategyTests(unittest.TestCase):
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
