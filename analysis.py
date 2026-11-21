"""仅接收公开快照。下注范围为启发式估计，不代表真实对手策略。"""
import random
from poker import get_hand_rank, analyze_hand_strength, analyze_draw_potential
from game import pot_layers


from ranges import distributions, sample_hands


def analyze_public(view, iterations=2500, seed=None):
    if view['done'] or view['actor'] != 0 or view['players'][0]['folded']:
        raise ValueError('仅在轮到你行动时分析当前决策')
    if type(iterations) is not int or iterations < 1:
        raise ValueError('抽样次数必须为正整数')
    rng = random.Random(seed)
    hero = view['players'][0]['hole']
    board = view['board']
    opponents = [p['seat'] for p in view['players'][1:] if not p['folded']]
    deck, candidates, weighted = distributions(hero, board, opponents, view['history'], view.get('stats'))
    notes = [dict(name=view['players'][seat]['name'],
                  actions=sum(e['seat'] == seat for e in view['history']),
                  range='公开行动与位置加权范围') for seat in opponents]
    projected = [dict(p) for p in view['players']]
    call = view['legal']['call']
    projected[0]['total'] += call
    pots = pot_layers(projected)
    wins = ties = completed = 0
    equity = expected_return = 0.0
    while completed < iterations:
        hands, used = sample_hands(candidates, weighted, rng)
        unseen = [c for c in deck if c['code'] not in used]
        full_board = board + rng.sample(unseen, 5 - len(board))
        ranks = {0: get_hand_rank(hero + full_board)}
        ranks.update({seat: get_hand_rank(hand + full_board) for seat, hand in hands.items()})
        best = min(ranks.values())
        winners = [seat for seat, rank in ranks.items() if rank == best]
        if 0 in winners:
            wins += len(winners) == 1
            ties += len(winners) > 1
            equity += 1 / len(winners)
        for amount, eligible in pots:
            if 0 not in eligible:
                continue
            top = min(ranks[i] for i in eligible)
            winning = [i for i in eligible if ranks[i] == top]
            if 0 in winning:
                expected_return += amount / len(winning)
        completed += 1
    ev = expected_return / iterations - call
    return dict(win_rate=round(wins / iterations * 100, 1), tie_rate=round(ties / iterations * 100, 1),
                equity=round(equity / iterations * 100, 1), ev=round(ev, 1),
                pot_odds=round(call / max(1, view['pot'] + call) * 100, 1), samples=iterations, error_95=round(98 / iterations ** .5, 2),
                hand_strength=analyze_hand_strength(hero, board), draw_potential=analyze_draw_potential(hero, board),
                ranges=notes, version=view['version'],
                suggestion='可过牌，观察下一步行动' if not call else ('跟注的估计EV为正' if ev > 0 else '跟注的估计EV为负，可考虑弃牌'),
                assumption='仅使用你的手牌、已发公共牌和公开下注记录；对手范围为启发式估计。EV假设此后无额外下注、无抽水，已计入边池资格。')
