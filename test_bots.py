import copy
import random
import unittest
from collections import Counter
from unittest.mock import patch

from bots import make_profile, choose_action
from game import Game


class BotTests(unittest.TestCase):
    def sample(self, style, strength=.30, call=60, can_raise=True):
        rng = random.Random(245)
        profile = make_profile(random.Random(9), style)
        legal = dict(call=call, can_raise=can_raise, min_raise_to=120, max_raise_to=1000)
        actions = [choose_action(profile, strength, 0, 2, 140, 1000,
                                 60, legal, rng) for _ in range(4000)]
        return Counter(action for action, _ in actions), actions

    def test_styles_change_frequencies_but_keep_mixed_actions(self):
        tight, _ = self.sample('tight')
        loose, _ = self.sample('loose')
        calling, _ = self.sample('calling')
        self.assertGreater(tight['fold'], loose['fold'] + 700)
        self.assertGreater(calling['call'], tight['call'] + 700)
        aggressive, sizes = self.sample('aggressive', strength=.65, call=0)
        passive, _ = self.sample('calling', strength=.65, call=0)
        self.assertGreater(aggressive['raise'], passive['raise'] + 700)
        self.assertGreater(aggressive['check'], 0)
        self.assertGreater(len({amount for action, amount in sizes if action == 'raise'}), 10)

    def test_free_checks_and_short_allin_respect_legality(self):
        rng = random.Random(10)
        for style in ('tight', 'loose', 'aggressive', 'calling', 'balanced'):
            profile = make_profile(rng, style)
            for call in (0, 10):
                for can_raise in (False, True):
                    legal = dict(call=call, can_raise=can_raise,
                                 min_raise_to=40, max_raise_to=30)
                    for _ in range(100):
                        action, amount = choose_action(profile, .45, 1, 3, 100,
                                                       30, 20, legal, rng)
                        if action == 'raise':
                            self.assertTrue(can_raise)
                            self.assertEqual(amount, 30)
                        if call == 0:
                            self.assertIn(action, ('check', 'raise'))
                        if not can_raise:
                            self.assertNotEqual(action, 'raise')

    def test_profiles_persist_and_are_private(self):
        game = Game(11, player_count=10)
        original = copy.deepcopy(game.bot_profiles)
        self.assertEqual(original, Game(11, player_count=10).bot_profiles)
        self.assertGreater(len({p['style'] for p in original.values()}), 1)
        self.assertNotEqual(original, Game(12, player_count=10).bot_profiles)
        for _ in range(3):
            game.start_hand()
            self.assertNotIn('bot_profiles', game.public_view())
            while not game.done:
                legal = game.legal(game.actor)
                game.act(game.actor, 'call' if legal['call'] else 'check')
            self.assertEqual(original, game.bot_profiles)

    def test_bot_games_conserve_chips(self):
        # 固定估计权益以隔离策略和规则，覆盖不同人数、浅筹码和完整多手牌局。
        with patch('poker.simulate_equity', return_value={'equity': .38}):
            for count in range(2, 11):
                game = Game(count, player_count=count, starting_stack=100)
                for _ in range(8):
                    if not game.players[0]['stack'] or sum(p['stack'] > 0 for p in game.players) < 2:
                        break
                    game.start_hand()
                    steps = 0
                    while not game.done:
                        if game.actor == 0:
                            legal = game.legal(0)
                            game.act(0, 'call' if legal['call'] else 'check')
                        else:
                            game.bot_step()
                        steps += 1
                        self.assertLess(steps, 150)
                        self.assertTrue(all(p['stack'] >= 0 for p in game.players))
                        chips = sum(p['stack'] for p in game.players)
                        if not game.done:
                            chips += sum(p['total'] for p in game.players)
                        self.assertEqual(chips, count * 100)


if __name__ == '__main__':
    unittest.main()
