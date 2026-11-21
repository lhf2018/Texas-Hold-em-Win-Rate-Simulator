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
            self.assertIn('首轮行动已结束', g.legal(seat)['raise_reason'])
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

    def test_every_postflop_street_reopens_hero_before_last_player_locks(self):
        g = Game(1)
        # 庄家在座位1，翻牌后玩家0先于最后行动的庄家行动。
        g.button = 0
        g.start_hand()
        self.assertEqual(g.button, 1)
        while g.street == 0:
            g.act(g.actor, 'call' if g.legal(g.actor)['call'] else 'check')
        for street in (1, 2, 3):
            self.assertEqual(g.street, street)
            self.assertFalse(g.raises_closed)
            self.assertEqual(g.raised_seats, set())
            # 初始顺序2 -> 3 -> 0 -> 1，玩家0未加注先过牌。
            g.act(2, 'check')
            g.act(3, 'check')
            self.assertTrue(g.public_view()['legal']['can_raise'])
            g.act(0, 'check')
            g.act(1, 'raise', 20)
            self.assertTrue(g.raises_closed)
            for seat in (2, 3):
                g.act(seat, 'call')
            view = g.public_view()
            self.assertEqual(view['actor'], 0)
            self.assertNotIn(0, g.raised_seats)
            self.assertFalse(view['legal']['can_raise'])
            self.assertIn('首轮行动已结束', view['legal']['raise_reason'])
            self.assertEqual(view['legal']['call'], 20)
            g.act(0, 'call')
        self.assertTrue(g.done)

    def test_per_player_cannot_raise_twice_even_before_lock(self):
        g = Game(1)
        g.start_hand()
        g.act(3, 'raise', 40)
        g.act(0, 'raise', 80)
        g.act(1, 'call')
        g.act(2, 'call')
        self.assertTrue(g.raises_closed)
        self.assertEqual(g.actor, 3)
        self.assertFalse(g.legal(3)['can_raise'])
        self.assertIn('首轮行动已结束', g.legal(3)['raise_reason'])
        g.act(3, 'call')
        self.assertEqual(g.street, 1)

    def test_first_pass_can_raise_above_highest_then_only_match(self):
        g = Game(1)
        g.start_hand()
        g.act(3, 'call')
        g.act(0, 'raise', 60)
        self.assertTrue(g.legal(1)['can_raise'])
        self.assertEqual(g.legal(1)['min_raise_to'], 61)
        g.act(1, 'raise', 61)
        self.assertTrue(g.legal(2)['can_raise'])
        g.act(2, 'raise', 62)
        for seat in (3, 0, 1):
            self.assertEqual(g.actor, seat)
            self.assertFalse(g.legal(seat)['can_raise'])
            self.assertEqual(g.legal(seat)['call'], 62-g.players[seat]['bet'])
            g.act(seat, 'call')
        self.assertEqual(g.street, 1)

    def test_first_pass_ends_even_if_last_player_only_calls(self):
        g = Game(1)
        g.start_hand()
        g.act(3, 'call')
        g.act(0, 'raise', 60)
        g.act(1, 'call')
        g.act(2, 'call')
        self.assertEqual(g.actor, 3)
        self.assertNotIn(3, g.raised_seats)
        self.assertFalse(g.legal(3)['can_raise'])
        g.act(3, 'call')
        self.assertEqual(g.street, 1)

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

    def test_short_allin_does_not_block_later_first_actions(self):
        g = Game(1)
        g.start_hand()
        for seat in (3, 0, 1):
            g.act(seat, 'call')
        g.act(2, 'check')
        g.players[1]['stack'] = 10
        g.act(1, 'raise', 10)
        for seat, target in ((2, 11), (3, 12), (0, 13)):
            self.assertTrue(g.legal(seat)['can_raise'])
            self.assertEqual(g.legal(seat)['min_raise_to'], target)
            g.act(seat, 'raise', target)
        self.assertTrue(g.raises_closed)
        for seat in (2, 3):
            self.assertFalse(g.legal(seat)['can_raise'])
            g.act(seat, 'call')
        self.assertEqual(g.street, 2)

    def test_table_has_one_rule_and_no_selector(self):
        from app import app
        client = app.test_client()
        page = client.get('/').get_data(as_text=True)
        self.assertNotIn('ruleMode', page)
        # 旧客户端的模式字段不能再切换服务端规则。
        response = client.post('/api/game/new', json={'rule_mode': 'practice'})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('rule_mode', response.json)

    def test_no_raise_into_allin_opponents(self):
        g = Game(1, player_count=2)
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
        g = Game(2)
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
