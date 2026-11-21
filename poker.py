import random
import itertools
import math
from collections import Counter

# ==================== 德州扑克牌型判定 ====================

RANK_VALUES = {'2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, '10': 10,
               'J': 11, 'Q': 12, 'K': 13, 'A': 14}
RANK_ORDER = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']


def get_rank_value(rank):
    return RANK_VALUES.get(rank, 0)


def straight_high(ranks):
    values = set(ranks)
    if 14 in values:
        values.add(1)
    return next((high for high in range(14, 4, -1)
                 if all(r in values for r in range(high - 4, high + 1))), 0)


def get_hand_rank(cards):
    """直接求5至7张牌中的最佳五张；整个元组越小越强。"""
    if not 5 <= len(cards) <= 7:
        raise ValueError("牌型判断需要5至7张牌")
    counts = Counter(get_rank_value(c['rank']) for c in cards)
    ranks = sorted(counts, reverse=True)
    suits = {}
    for card in cards:
        suits.setdefault(card['suit'], []).append(get_rank_value(card['rank']))
    flush = next((sorted(v, reverse=True) for v in suits.values() if len(v) >= 5), None)

    def score(category, *values):
        return (category,) + tuple(-v for v in values)

    if flush:
        high = straight_high(flush)
        if high:
            return score(1 if high == 14 else 2, high)
    quads = [r for r in ranks if counts[r] == 4]
    if quads:
        return score(3, quads[0], next(r for r in ranks if r != quads[0]))
    trips = [r for r in ranks if counts[r] >= 3]
    if trips:
        pairs = [r for r in ranks if r != trips[0] and counts[r] >= 2]
        if pairs:
            return score(4, trips[0], pairs[0])
    if flush:
        return score(5, *flush[:5])
    high = straight_high(ranks)
    if high:
        return score(6, high)
    if trips:
        return score(7, trips[0], *[r for r in ranks if r != trips[0]][:2])
    pairs = [r for r in ranks if counts[r] >= 2]
    if len(pairs) >= 2:
        return score(8, *pairs[:2], next(r for r in ranks if r not in pairs[:2]))
    if pairs:
        return score(9, pairs[0], *[r for r in ranks if r != pairs[0]][:3])
    return score(10, *ranks[:5])


def compare_hands(hand1, hand2):
    """比较两手牌，返回1表示hand1胜，-1表示hand2胜，0平局"""
    rank1 = get_hand_rank(hand1)
    rank2 = get_hand_rank(hand2)
    if rank1 < rank2:
        return 1
    if rank1 > rank2:
        return -1
    return 0


# ==================== 蒙特卡洛模拟 ====================

def get_deck():
    """生成标准52张牌"""
    suits = ['♠', '♥', '♣', '♦']
    ranks = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
    return [{'rank': r, 'suit': s, 'code': f"{r}{s}"} for r in ranks for s in suits]


def get_remaining_cards(hole, community):
    """计算剩余牌堆"""
    deck = get_deck()
    used = set()
    for c in hole:
        if c:
            used.add(c['code'])
    for c in community:
        if c:
            used.add(c['code'])
    return [c for c in deck if c['code'] not in used]


def simulate_equity(hole, community, opponent_count, iterations=10000):
    """均匀随机对手手牌；河牌单挑精确枚举，其余随机采样。"""
    board = [c for c in community if c]
    deck = get_remaining_cards(hole, board)
    missing = 5 - len(board)
    exact = missing == 0 and opponent_count == 1
    deals = (itertools.combinations(deck, 2) if exact else
             (random.sample(deck, missing + 2 * opponent_count) for _ in range(iterations)))
    wins = ties = total = 0
    equity = 0.0
    fixed_rank = get_hand_rank(hole + board) if not missing else None
    for deal in deals:
        full_board = board + list(deal[:missing])
        player_rank = fixed_rank or get_hand_rank(hole + full_board)
        opponents = [get_hand_rank(list(deal[i:i + 2]) + full_board)
                     for i in range(missing, missing + opponent_count * 2, 2)]
        best = min(opponents)
        if player_rank < best:
            wins += 1
            equity += 1
        elif player_rank == best:
            ties += 1
            equity += 1 / (1 + opponents.count(player_rank))
        total += 1
    return {"win_rate": wins / total, "tie_rate": ties / total,
            "lose_rate": (total - wins - ties) / total, "equity": equity / total,
            "method": "exact" if exact else "monte_carlo", "samples": total}


def monte_carlo_simulation(hole, community, opponent_count, iterations=10000):
    result = simulate_equity(hole, community, opponent_count, iterations)
    return result['win_rate'], result['tie_rate'], result['lose_rate']


# ==================== 牌型分析 ====================

HAND_TYPE_NAMES = {
    1: "皇家同花顺 👑",
    2: "同花顺",
    3: "四条",
    4: "葫芦",
    5: "同花",
    6: "顺子",
    7: "三条",
    8: "两对",
    9: "一对",
    10: "高牌"
}


def analyze_hand_strength(hole, community):
    """分析当前牌型"""
    if not hole[0] or not hole[1]:
        return {"type": "未知", "rank": 10, "description": "请选择手牌", "strength": "---"}

    all_cards = [c for c in hole if c] + [c for c in community if c]
    filled_count = len([c for c in community if c])

    if filled_count < 3:
        return {"type": "未成牌", "rank": 10, "description": f"公共牌不足{filled_count}张", "strength": "待发牌"}

    hand_rank = get_hand_rank(all_cards)
    type_idx = hand_rank[0]
    type_name = HAND_TYPE_NAMES.get(type_idx, "高牌")

    strength_map = {
        1: "极强 ⭐⭐⭐⭐⭐ (皇家同花顺)",
        2: "极强 ⭐⭐⭐⭐⭐",
        3: "很强 ⭐⭐⭐⭐",
        4: "很强 ⭐⭐⭐⭐",
        5: "强 ⭐⭐⭐",
        6: "强 ⭐⭐⭐",
        7: "中等 ⭐⭐",
        8: "中等 ⭐⭐",
        9: "弱 ⭐",
        10: "弱 ⭐"
    }

    return {
        "type": type_name,
        "rank": type_idx,
        "description": f"{type_name}",
        "strength": strength_map.get(type_idx, "中等")
    }


def analyze_draw_potential(hole, community):
    """识别差一张的顺子/同花；枚举剩余公共牌计算成牌概率。"""
    board = [c for c in community if c]
    empty = {"draws": [], "total_outs": 0, "improve_prob": 0}
    if len(board) not in (3, 4):
        return empty
    cards = hole + board
    remaining = get_remaining_cards(hole, board)
    ranks = {get_rank_value(c['rank']) for c in cards}
    suits = Counter(c['suit'] for c in cards)
    targets = []
    for suit, count in suits.items():
        if count == 4:
            targets.append(("同花听牌", lambda cs, suit=suit: sum(c['suit'] == suit for c in cs) >= 5))
    if not straight_high(ranks):
        if any(straight_high(ranks | {get_rank_value(c['rank'])}) for c in remaining):
            targets.append(("顺子听牌", lambda cs: bool(straight_high(get_rank_value(c['rank']) for c in cs))))
    if not targets:
        return empty
    out_sets = [{c['code'] for c in remaining if check(cards + [c])} for _, check in targets]
    hits = [0] * len(targets)
    any_hits = total = 0
    for runout in itertools.combinations(remaining, 5 - len(board)):
        outcomes = [check(cards + list(runout)) for _, check in targets]
        for i, hit in enumerate(outcomes):
            hits[i] += hit
        any_hits += any(outcomes)
        total += 1
    return {"draws": [{"type": name, "description": "到河牌成牌（不代表获胜）",
                        "outs": len(out_sets[i]), "probability": round(hits[i] / total * 100, 2)}
                       for i, (name, _) in enumerate(targets)],
            "total_outs": len(set().union(*out_sets)),
            "improve_prob": round(any_hits / total * 100, 2)}


def validate_calculation(data):
    if not isinstance(data, dict):
        raise ValueError("请求必须为JSON对象")
    hole, board = data.get('hole'), data.get('community', [None] * 5)
    if not isinstance(hole, list) or len(hole) != 2 or not all(hole):
        raise ValueError("请选择两张手牌")
    if not isinstance(board, list) or len(board) != 5:
        raise ValueError("公共牌需包含5个位置")
    filled = [c for c in board if c is not None]
    if len(filled) not in (0, 3, 4, 5) or board != filled + [None] * (5 - len(filled)):
        raise ValueError("公共牌必须按顺序填写0、3、4或5张")
    codes = []
    for card in hole + filled:
        if not isinstance(card, dict) or card.get('rank') not in RANK_VALUES or card.get('suit') not in ['♠', '♥', '♣', '♦']:
            raise ValueError("存在无效扑克牌")
        code = card['rank'] + card['suit']
        if card.get('code') != code:
            raise ValueError("扑克牌编码不一致")
        codes.append(code)
    if len(set(codes)) != len(codes):
        raise ValueError("不能使用重复牌")
    opponents = data.get('opponent_count', 6)
    if type(opponents) is not int or not 1 <= opponents <= 8:
        raise ValueError("对手人数须为1至8")
    if data.get('mode', 'basic') not in ('basic', 'advanced'):
        raise ValueError("无效模式")
    for key in ('pot', 'call_amount'):
        value = data.get(key, 0)
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError("底池和跟注金额须为非负有限数值")


