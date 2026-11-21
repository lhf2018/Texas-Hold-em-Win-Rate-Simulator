"""仅接收公开快照。下注范围为启发式估计，不代表真实对手策略。"""
import itertools
import random
from bisect import bisect
from poker import get_deck, get_hand_rank, analyze_hand_strength, analyze_draw_potential, get_rank_value
from game import pot_layers


def range_strength(hole, board):
    if len(board) >= 3:
        rank = get_hand_rank(hole + board)
        # 牌型及主点数，保留弱牌和诈唬权重。
        return min(.98, (10 - rank[0]) / 9 + (-rank[1]) / 14 * .18)
    a, b = sorted((get_rank_value(c['rank']) for c in hole), reverse=True)
    score = (a + b - 4) / 24 * .58
    if a == b:
        score = .48 + a / 14 * .48
    elif hole[0]['suit'] == hole[1]['suit']:
        score += .08
    if a != b and a - b <= 2:
        score += .06
    return min(.98, score)


def analyze_public(view, iterations=2500, seed=None):
    if view['done'] or view['actor'] != 0 or view['players'][0]['folded']:
        raise ValueError('仅在轮到你行动时分析当前决策')
    rng = random.Random(seed)
    hero = view['players'][0]['hole']
    board = view['board']
    known = {c['code'] for c in hero + board}
    deck = [c for c in get_deck() if c['code'] not in known]
    opponents = [p['seat'] for p in view['players'][1:] if not p['folded']]
    candidates = list(itertools.combinations(deck, 2))
    distributions, notes = [], []
    for seat in opponents:
        events = [e for e in view['history'] if e['seat'] == seat and e['action'] not in ('小盲', '大盲', '弃牌')]
        # 限制最近的公开行动数量，避免反复跟注过度收窄范围。
        events = events[-4:]
        cumulative, total = [], 0.0
        for hand in candidates:
            weight = 1.0
            for event in events:
                strength = range_strength(list(hand), event['board'])
                pressure = min(2, event['amount'] / max(20, event['pot'] - event['amount']))
                if event['action'] in ('加注到', '全下加注'):
                    weight *= .15 + (strength ** 2) * (2 + pressure * 3)
                elif event['action'] in ('跟注', '全下跟注'):
                    weight *= .4 + strength * (1 + pressure)
                elif event['action'] == '过牌':
                    weight *= 1.1 - strength * .25
            total += weight
            cumulative.append(total)
        distributions.append((cumulative, total))
        notes.append(dict(name=view['players'][seat]['name'], actions=len(events),
                          range='下注记录加权范围' if events else '随机范围（尚无自愿下注信息）'))
    projected = [dict(p) for p in view['players']]
    call = view['legal']['call']
    projected[0]['total'] += call
    pots = pot_layers(projected)
    wins = ties = completed = 0
    equity = expected_return = 0.0
    while completed < iterations:
        hands, used = {}, set()
        collision = False
        for seat, (cumulative, total) in zip(opponents, distributions):
            hand = candidates[bisect(cumulative, rng.random() * total)]
            codes = {c['code'] for c in hand}
            if used & codes:
                collision = True
                break
            used |= codes
            hands[seat] = list(hand)
        if collision:
            continue
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
                pot_odds=round(call / max(1, view['pot'] + call) * 100, 1), samples=iterations,
                hand_strength=analyze_hand_strength(hero, board), draw_potential=analyze_draw_potential(hero, board),
                ranges=notes, version=view['version'],
                suggestion='可过牌，观察下一步行动' if not call else ('跟注的估计EV为正' if ev > 0 else '跟注的估计EV为负，可考虑弃牌'),
                assumption='仅使用你的手牌、已发公共牌和公开下注记录；对手范围为启发式估计。EV假设此后无额外下注、无抽水，已计入边池资格。')
