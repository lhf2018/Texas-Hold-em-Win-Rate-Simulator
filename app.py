from flask import Flask, render_template, request, jsonify
import random
import itertools
from collections import Counter
import requests
import json
import os

app = Flask(__name__)

# ==================== 德州扑克牌型判定 ====================

RANK_VALUES = {'2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, '10': 10,
               'J': 11, 'Q': 12, 'K': 13, 'A': 14}
RANK_ORDER = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']


def get_rank_value(rank):
    return RANK_VALUES.get(rank, 0)


def get_hand_rank(cards):
    """
    返回牌型等级和比较值，数字越小牌型越强
    牌型等级:
    1: 皇家同花顺, 2: 同花顺, 3: 四条, 4: 葫芦, 5: 同花,
    6: 顺子, 7: 三条, 8: 两对, 9: 一对, 10: 高牌
    """
    ranks = [get_rank_value(c['rank']) for c in cards]
    suits = [c['suit'] for c in cards]
    rank_counts = Counter(ranks)
    sorted_ranks = sorted(ranks, reverse=True)
    is_flush = len(set(suits)) == 1

    # 检查顺子
    is_straight = False
    straight_high = 0
    unique_ranks = sorted(set(ranks), reverse=True)

    # 普通顺子检查
    for i in range(len(unique_ranks) - 4):
        if unique_ranks[i] - unique_ranks[i + 4] == 4:
            is_straight = True
            straight_high = unique_ranks[i]
            break

    # A-2-3-4-5 特殊顺子
    if not is_straight and set([14, 2, 3, 4, 5]).issubset(set(ranks)):
        is_straight = True
        straight_high = 5

    # 同花顺判断
    if is_flush and is_straight:
        # 皇家同花顺: 顺子高牌是A (14) 且包含A-K-Q-J-10
        if straight_high == 14 or (straight_high == 5 and 14 in ranks):
            # 检查是否为10-J-Q-K-A
            royal_ranks = {10, 11, 12, 13, 14}
            if royal_ranks.issubset(set(ranks)):
                return (1, 14)  # 皇家同花顺
        return (2, straight_high)  # 普通同花顺

    # 四条
    if 4 in rank_counts.values():
        four_rank = [r for r, c in rank_counts.items() if c == 4][0]
        kicker = [r for r in rank_counts if r != four_rank][0]
        return (3, four_rank, kicker)

    # 葫芦
    if 3 in rank_counts.values() and 2 in rank_counts.values():
        three_rank = [r for r, c in rank_counts.items() if c == 3][0]
        pair_rank = [r for r, c in rank_counts.items() if c == 2][0]
        return (4, three_rank, pair_rank)

    # 同花
    if is_flush:
        return (5, sorted_ranks[:5])

    # 顺子
    if is_straight:
        return (6, straight_high)

    # 三条
    if 3 in rank_counts.values():
        three_rank = [r for r, c in rank_counts.items() if c == 3][0]
        kickers = sorted([r for r in rank_counts if r != three_rank], reverse=True)
        return (7, three_rank, kickers)

    # 两对
    pairs = [r for r, c in rank_counts.items() if c == 2]
    if len(pairs) == 2:
        high_pair = max(pairs)
        low_pair = min(pairs)
        kicker = [r for r in rank_counts if r not in pairs][0]
        return (8, high_pair, low_pair, kicker)

    # 一对
    if len(pairs) == 1:
        pair_rank = pairs[0]
        kickers = sorted([r for r in rank_counts if r != pair_rank], reverse=True)
        return (9, pair_rank, kickers)

    # 高牌
    return (10, sorted_ranks[:5])


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


def monte_carlo_simulation(hole, community, opponent_count, iterations=10000):
    """
    蒙特卡洛模拟胜率
    hole: 两张手牌 [card, card]
    community: 公共牌数组，长度5，未发的为None
    opponent_count: 对手数量
    """
    if not hole[0] or not hole[1]:
        return 0.0, 0.0, 0.0

    # 获取已发牌
    known_cards = [c for c in hole if c] + [c for c in community if c]
    remaining_deck = get_remaining_cards(hole, community)

    if len(remaining_deck) < 2 * opponent_count:
        return 0.0, 0.0, 0.0

    wins = 0
    ties = 0
    total = iterations

    for _ in range(iterations):
        # 随机洗牌
        shuffled = remaining_deck.copy()
        random.shuffle(shuffled)

        # 补全公共牌
        missing_count = 5 - len([c for c in community if c])
        if missing_count > 0:
            full_community = [c for c in community if c] + shuffled[:missing_count]
            idx = missing_count
        else:
            full_community = community
            idx = 0

        # 生成对手手牌
        opponent_hands = []
        for i in range(opponent_count):
            if idx + 1 < len(shuffled):
                opp_hand = [shuffled[idx], shuffled[idx + 1]]
                opponent_hands.append(opp_hand)
                idx += 2

        # 计算玩家牌型
        player_hand = hole + full_community
        player_rank = get_hand_rank(player_hand)

        # 比较对手
        best_opp_rank = None
        for opp_hand in opponent_hands:
            opp_full = opp_hand + full_community
            opp_rank = get_hand_rank(opp_full)
            if best_opp_rank is None or opp_rank < best_opp_rank:
                best_opp_rank = opp_rank

        if best_opp_rank is None:
            wins += 1
        elif player_rank < best_opp_rank:
            wins += 1
        elif player_rank == best_opp_rank:
            ties += 1

    win_rate = wins / total
    tie_rate = ties / total
    lose_rate = 1 - win_rate - tie_rate

    return win_rate, tie_rate, lose_rate


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
    """分析听牌潜力"""
    if not hole[0] or not hole[1]:
        return {"draws": [], "total_outs": 0, "improve_prob": 0}

    all_cards = [c for c in hole if c] + [c for c in community if c]
    community_filled = [c for c in community if c]
    remaining = get_remaining_cards(hole, community)

    draws = []

    # 同花听牌检查
    if len(community_filled) >= 3:
        suits = [c['suit'] for c in all_cards]
        suit_counts = Counter(suits)
        for suit, count in suit_counts.items():
            if count >= 4:
                outs = 13 - count
                draws.append({
                    "type": "同花听牌",
                    "description": f"已有{count}张{suit}花",
                    "outs": outs,
                    "probability": min(35, outs * 4)
                })
                break

    # 顺子听牌简化检查
    ranks = [get_rank_value(c['rank']) for c in all_cards]
    unique_ranks = sorted(set(ranks))
    for i in range(len(unique_ranks) - 4):
        if unique_ranks[i + 4] - unique_ranks[i] <= 4:
            draws.append({
                "type": "顺子听牌",
                "description": "两端顺子听牌",
                "outs": 8,
                "probability": 32
            })
            break

    total_outs = sum(d['outs'] for d in draws) if draws else 0
    improve_prob = min(85, total_outs * 4) if total_outs > 0 else 0

    return {
        "draws": draws,
        "total_outs": total_outs,
        "improve_prob": improve_prob
    }


# ==================== DeepSeek大模型接入 ====================

DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"


def call_deepseek_analysis(hole, community, win_rate, mode, pot_info=None):
    """调用DeepSeek大模型进行AI分析"""
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")

    if not api_key:
        return "⚠️ 请先设置环境变量 DEEPSEEK_API_KEY 以启用AI分析功能\n\n示例: export DEEPSEEK_API_KEY='your-key'"

    hole_str = f"{hole[0]['rank']}{hole[0]['suit']} {hole[1]['rank']}{hole[1]['suit']}" if hole[0] and hole[
        1] else "未选择"
    community_str = " ".join([f"{c['rank']}{c['suit']}" for c in community if c]) if any(community) else "无"

    prompt = f"""你是一位专业的德州扑克教练。请分析以下牌局并给出建议：

手牌: {hole_str}
公共牌: {community_str}
当前胜率: {win_rate:.1f}%
模式: {mode}

{f'底池: {pot_info["pot"]} BB, 需跟注: {pot_info["call"]} BB' if pot_info else ''}

请给出:
1. 当前牌局评估 (50字以内)
2. 具体行动建议 (跟注/加注/弃牌)
3. 风险评估 (20字以内)"""

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 300
    }

    try:
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=10)
        if response.status_code == 200:
            result = response.json()
            return result["choices"][0]["message"]["content"]
        else:
            return f"AI服务异常: {response.status_code}"
    except Exception as e:
        return f"AI调用失败: {str(e)}"


# ==================== Flask路由 ====================

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/calculate', methods=['POST'])
def calculate():
    """胜率计算接口"""
    data = request.json

    # 解析手牌
    hole = data.get('hole', [None, None])
    community = data.get('community', [None] * 5)
    mode = data.get('mode', 'basic')
    opponent_count = data.get('opponent_count', 6)

    # 执行蒙特卡洛模拟
    win_rate, tie_rate, lose_rate = monte_carlo_simulation(hole, community, opponent_count)

    # 牌型分析
    hand_strength = analyze_hand_strength(hole, community)
    draw_potential = analyze_draw_potential(hole, community)

    result = {
        "win_rate": round(win_rate * 100, 1),
        "tie_rate": round(tie_rate * 100, 1),
        "lose_rate": round(lose_rate * 100, 1),
        "hand_strength": hand_strength,
        "draw_potential": draw_potential
    }

    # 进阶模式额外计算
    if mode == 'advanced':
        pot = data.get('pot', 0)
        call_amount = data.get('call_amount', 0)

        # 底池赔率
        pot_odds = (call_amount / (pot + call_amount)) * 100 if (pot + call_amount) > 0 else 0

        # 期望价值
        ev = (win_rate * (pot + call_amount)) - (lose_rate * call_amount)

        # 行动建议
        if ev > 10:
            action = "✅ 建议跟注/加注 (正EV显著)"
        elif ev > 0:
            action = "🟡 边缘决策，可考虑跟注"
        else:
            action = "❌ 建议弃牌 (负EV)"

        result.update({
            "pot_odds": round(pot_odds, 1),
            "ev": round(ev, 1),
            "action_suggestion": action
        })

    return jsonify(result)


@app.route('/api/ai_analyze', methods=['POST'])
def ai_analyze():
    """AI分析接口"""
    data = request.json

    hole = data.get('hole', [None, None])
    community = data.get('community', [None] * 5)
    win_rate = data.get('win_rate', 0)
    mode = data.get('mode', 'basic')

    pot_info = None
    if mode == 'advanced':
        pot_info = {
            "pot": data.get('pot', 0),
            "call": data.get('call_amount', 0)
        }

    analysis = call_deepseek_analysis(hole, community, win_rate, mode, pot_info)

    return jsonify({"analysis": analysis})


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)