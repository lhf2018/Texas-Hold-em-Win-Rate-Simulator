"""固定发牌、交换座位的新版/旧版单挑评测；按配对牌局估计误差。"""
import argparse
import math
import random
import statistics
from bots import choose_action, decide, make_profile
from game import Game
from poker import simulate_equity


def benchmark(pairs=100, seed=42, mode='practice', samples=256):
    results = []
    for pair in range(pairs):
        paired = []
        for new_seat in (0, 1):
            game = Game(seed+pair, player_count=2, rule_mode=mode)
            # 每次复制相同牌堆与庄位；只交换策略，重置筹码避免淘汰偏差。
            game.start_hand()
            rng = random.Random(seed+pair+100000)
            profile = make_profile(random.Random(9), 'balanced')
            random.seed(seed+pair+200000)
            while not game.done:
                seat = game.actor
                view = game.decision_view(seat)
                p, legal = view['players'][seat], view['legal']
                if seat == new_seat:
                    action, amount, _ = decide(view, seat, profile, rng,
                        min_samples=samples, max_samples=samples, time_budget=float('inf'))
                else:
                    strength = simulate_equity(p['hole'], game.board+[None]*(5-len(game.board)), 1, 100)['equity']
                    action, amount = choose_action(profile, strength, game.street, 1,
                        view['pot'], p['stack'], game.current_bet, legal, rng,
                        position=view['position'], hole=p['hole'], board=game.board)
                game.act(seat, action, amount)
            paired.append((game.players[new_seat]['stack']-game.starting_stack)/20)
        results.append(statistics.mean(paired))
    mean = statistics.mean(results)*100
    error = 1.96*statistics.stdev(results)/math.sqrt(pairs)*100 if pairs > 1 else None
    return dict(pairs=pairs, hands=pairs*2, seed=seed, rule_mode=mode,
                bb_per_100=round(mean,2), approximate_95_half_width=round(error,2) if error is not None else None,
                note='单挑、每手重置筹码；配对正态近似区间，小样本不足以判定强弱。')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--pairs', type=int, default=100)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--samples', type=int, default=256)
    parser.add_argument('--mode', choices=['practice','standard'], default='practice')
    args = parser.parse_args()
    if args.pairs < 1 or args.samples < 1:
        parser.error('pairs 和 samples 必须为正数')
    print(benchmark(args.pairs, args.seed, args.mode, args.samples))
