"""仅使用观察者底牌与公开行动构建范围，不访问 Game。"""
import itertools
from bisect import bisect
from poker import get_deck, get_hand_rank, get_rank_value

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



def distributions(hero, board, opponents, history, stats=None):
    known = {c['code'] for c in hero + board}
    deck = [c for c in get_deck() if c['code'] not in known]
    candidates = list(itertools.combinations(deck, 2))
    result = []
    for seat in opponents:
        events = [e for e in history if e['seat'] == seat and e['action'] not in ('小盲', '大盲', '弃牌')][-4:]
        stat = (stats or {}).get(seat, {})
        vpip = (stat.get('vpip', 0) + 3) / (stat.get('hands', 0) + 10)
        pfr = (stat.get('pfr', 0) + 2) / (stat.get('hands', 0) + 10)
        cumulative, total = [], 0.
        for hand in candidates:
            weight = 1.
            for event in events:
                strength = range_strength(list(hand), event['board'])
                pressure = min(2, event['amount'] / max(20, event['pot'] - event['amount']))
                position = event.get('position', .5)
                if event['action'] in ('加注到', '全下加注'):
                    weight *= .08 + strength ** (2.8 - pfr * 2 + (.5-position)*.5) * (3 + pressure * 4)
                elif event['action'] in ('跟注', '全下跟注'):
                    weight *= .2 + strength ** (1.6-vpip) * (1 + pressure)
                elif event['action'] == '过牌':
                    weight *= 1.1 - strength * .25
            total += weight
            cumulative.append(total)
        result.append((seat, cumulative, total))
    return deck, candidates, result


def sample_hands(candidates, distributions, rng):
    # 整组拒绝采样，保持多人范围在牌张互斥条件下的联合分布。
    while True:
        hands, used = {}, set()
        for seat, cumulative, total in distributions:
            hand = candidates[min(len(candidates)-1, bisect(cumulative, rng.random()*total))]
            codes = {c['code'] for c in hand}
            if used & codes:
                break
            hands[seat] = list(hand)
            used |= codes
        else:
            return hands, used
