import copy
import random
import unittest
from app import app
from game import Game, pot_layers
from analysis import analyze_public
from test_app import cards


class GameTests(unittest.TestCase):
    def test_play_and_chip_conservation(self):
        rng = random.Random(11)
        for seed in range(30):
            game = Game(seed)
            for hand in range(15):
                if game.players[0]['stack'] == 0 or sum(p['stack'] > 0 for p in game.players) < 2:
                    break
                game.start_hand()
                steps = 0
                while not game.done:
                    steps += 1
                    self.assertLess(steps, 180)
                    seat = game.actor
                    legal = game.legal(seat)
                    chance = rng.random()
                    if chance < .12:
                        game.act(seat, 'fold')
                    elif chance < .35 and legal['can_raise']:
                        target = min(legal['max_raise_to'], max(legal['min_raise_to'], rng.choice([40,100,300,1000])))
                        game.act(seat, 'raise', target)
                    else:
                        game.act(seat, 'call' if legal['call'] else 'check')
                    self.assertTrue(all(p['stack'] >= 0 for p in game.players))
                    self.assertEqual(sum(p['stack'] for p in game.players) + (0 if game.done else sum(p['total'] for p in game.players)), 4000)
                self.assertEqual(sum(p['stack'] for p in game.players), 4000)

    def test_blinds_and_big_blind_option(self):
        g = Game(1); g.start_hand()
        self.assertEqual(g.button, 0)
        self.assertEqual(g.actor, 3)
        for seat in (3,0,1):
            self.assertEqual(g.actor, seat)
            g.act(seat, 'call')
        self.assertEqual(g.actor, 2)
        self.assertEqual(g.street, 0)
        g.act(2, 'check')
        self.assertEqual((g.street, g.actor), (1,1))
        self.assertEqual(len(g.board), 3)

    def test_side_pots_and_refund(self):
        g = Game(1)
        g.board = cards('2♠ 3♥ 7♣ 9♦ J♠')
        for p, total, hole in zip(g.players, (100,300,500,500), ('A♠ A♥','K♠ K♥','Q♠ Q♥','10♠ 10♥')):
            p.update(total=total, stack=1000-total, hole=cards(hole))
        g.finish()
        self.assertEqual([p['stack'] for p in g.players], [1300,1300,900,500])
        self.assertEqual(sum(p['stack'] for p in g.players),4000)
        g = Game(2)
        g.board = cards('2♠ 3♥ 7♣ 9♦ J♠')
        for p,total,hole in zip(g.players,(100,300,0,0),('A♠ A♥','K♠ K♥','Q♠ Q♥','10♠ 10♥')):
            p.update(total=total,stack=1000-total,hole=cards(hole),folded=total==0)
        g.finish()
        self.assertEqual([p['stack'] for p in g.players],[1100,900,1000,1000])

    def test_one_raise_per_street(self):
        g=Game(3, rule_mode='practice');g.start_hand()
        self.assertTrue(g.legal(3)['can_raise'])
        g.act(3,'raise',100)
        self.assertTrue(g.raise_used)
        before=g.public_view()
        for seat in (0,1,2):
            self.assertFalse(g.legal(seat)['can_raise'])
        with self.assertRaises(ValueError):g.act(0,'raise',200)
        self.assertEqual(before,g.public_view())
        for seat in (0,1,2):g.act(seat,'call')
        self.assertEqual(g.street,1)
        self.assertFalse(g.raise_used)
        g.act(1,'check');g.act(2,'raise',40)
        self.assertFalse(g.legal(3)['can_raise'])
        for seat in (3,0,1):g.act(seat,'call')
        self.assertEqual(g.street,2)
        self.assertTrue(g.legal(g.actor)['can_raise'])

    def test_no_private_information(self):
        g=Game(5);g.start_hand();g.act(3,'call')
        view=g.public_view()
        self.assertEqual(view['actor'],0)
        for p in view['players'][1:]:self.assertEqual(p['hole'],[])
        self.assertNotIn('deck',view)
        before=analyze_public(view,iterations=300,seed=42)
        # 即使服务器隐藏底牌和待发牌改变，相同公开信息的分析完全相同。
        g.players[1]['hole'],g.players[2]['hole']=g.players[2]['hole'],g.players[1]['hole']
        g.deck.reverse()
        self.assertEqual(before,analyze_public(g.public_view(),iterations=300,seed=42))
        # 即使外部传入对手底牌，分析器也不会读取。
        exposed=copy.deepcopy(view)
        for p in exposed['players'][1:]:p['hole']=cards('A♠ A♥')
        self.assertEqual(before,analyze_public(exposed,iterations=300,seed=42))

    def test_heads_up_and_allin_runout(self):
        g=Game(10)
        g.players[2]['stack']=g.players[3]['stack']=0
        g.start_hand()
        self.assertEqual((g.button,g.actor),(0,0))
        self.assertEqual(g.players[0]['bet'],10)
        g.act(0,'raise',1000);g.act(1,'call')
        self.assertTrue(g.done);self.assertEqual(len(g.board),5)
        self.assertEqual(sum(p['stack'] for p in g.players),2000)

    def test_short_allin_uses_raise_opportunity(self):
        g=Game(8, rule_mode='practice');g.start_hand()
        for seat in (3,0,1):g.act(seat,'call')
        g.act(2,'check')
        g.act(1,'check')
        g.players[2]['stack']=10
        g.act(2,'raise',10)
        for seat in (3,0,1):
            self.assertFalse(g.legal(seat)['can_raise'])
            g.act(seat,'call')
        self.assertEqual(g.street,2)
        self.assertFalse(g.raise_used)

    def test_configurable_two_to_ten_players(self):
        for count in range(2,11):
            g=Game(seed=count,player_count=count,starting_stack=2000)
            g.start_hand()
            self.assertEqual(len(g.players),count)
            self.assertEqual(len({c['code'] for p in g.players for c in p['hole']}),count*2)
            steps=0
            while not g.done:
                legal=g.legal(g.actor)
                g.act(g.actor,'call' if legal['call'] else 'check')
                steps+=1
                self.assertLess(steps,100)
            self.assertEqual(sum(p['stack'] for p in g.players),count*2000)
            self.assertEqual(len(g.board),5)
            self.assertEqual(g.public_view()['player_count'],count)
        client=app.test_client()
        self.assertEqual(client.post('/api/game/new',json={'player_count':10}).status_code,200)
        for value in (1,11,True,3.5):
            self.assertEqual(client.post('/api/game/new',json={'player_count':value}).status_code,400)

    def test_api_sessions_and_stale_actions(self):
        first,second=app.test_client(),app.test_client()
        view=first.post('/api/game/new',json={}).json
        self.assertTrue(second.get('/api/game').json['empty'])
        self.assertEqual(first.post('/api/game/step',json={'version':-1}).status_code,409)
        view=first.post('/api/game/step',json={'version':view['version']}).json
        self.assertEqual(view['actor'],0)
        self.assertTrue(all(not p['hole'] for p in view['players'][1:]))
        result=first.get('/api/game/analyze')
        self.assertEqual(result.status_code,200)
        self.assertEqual(result.json['version'],view['version'])
        self.assertEqual(first.post('/api/game/action',json={'version':view['version'],'action':'raise','amount':'all'}).status_code,400)
        self.assertEqual(first.get('/api/game').json['version'],view['version'])

if __name__=='__main__':unittest.main()
