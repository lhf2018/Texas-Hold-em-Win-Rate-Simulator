from flask import Flask, render_template, request, jsonify, session
import os

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY') or os.urandom(32)
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

from game import Game
from analysis import analyze_public
from threading import RLock
from secrets import token_urlsafe
from time import monotonic

games = {}
games_lock = RLock()


def current_game():
    key = session.get('table_id')
    if key not in games:
        raise ValueError('牌桌已过期，请重新开桌')
    games[key]['seen'] = monotonic()
    return games[key]['game']


@app.route('/api/game', methods=['GET'])
def game_state():
    with games_lock:
        try:
            return jsonify(current_game().public_view())
        except ValueError:
            return jsonify({"empty": True})


@app.route('/api/game/new', methods=['POST'])
def new_game():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error='请求必须为JSON对象'), 400
    try:
        game = Game(player_count=data.get('player_count', 4), starting_stack=data.get('starting_stack', 1000), rule_mode=data.get('rule_mode', 'per_player'))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    with games_lock:
        # 本地单进程牌桌，清理长时间闲置的会话。
        now = monotonic()
        for key in list(games):
            if now - games[key]['seen'] > 7200:
                del games[key]
        old = session.get('table_id')
        games.pop(old, None)
        key = token_urlsafe(24)
        session['table_id'] = key
        games[key] = dict(game=game, seen=now)
        game.start_hand()
        return jsonify(game.public_view())


@app.route('/api/game/<operation>', methods=['POST'])
def game_operation(operation):
    with games_lock:
        try:
            game = current_game()
            data = request.get_json(silent=True)
            if not isinstance(data, dict) or type(data.get('version')) is not int or data['version'] != game.version:
                return jsonify({"error": "牌局状态已更新，请刷新页面重试"}), 409
            if operation == 'action':
                game.act(0, data.get('action'), data.get('amount'))
            elif operation == 'step':
                game.bot_step()
            elif operation == 'next':
                game.start_hand()
            else:
                raise ValueError('无效操作')
            return jsonify(game.public_view())
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400


@app.route('/api/game/analyze', methods=['GET'])
def game_analysis():
    try:
        with games_lock:
            public = current_game().public_view()
        # 分析函数不接收Game对象、牌堆或真实对手底牌。
        return jsonify(analyze_public(public))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


from poker import *

# ==================== Flask路由 ====================

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/calculate', methods=['POST'])
def calculate():
    """胜率计算接口"""
    data = request.get_json(silent=True)
    try:
        validate_calculation(data)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    # 解析手牌
    hole = data.get('hole', [None, None])
    community = data.get('community', [None] * 5)
    mode = data.get('mode', 'basic')
    opponent_count = data.get('opponent_count', 6)

    # 执行蒙特卡洛模拟
    simulation = simulate_equity(hole, community, opponent_count)
    win_rate, tie_rate, lose_rate = (simulation[k] for k in ('win_rate', 'tie_rate', 'lose_rate'))

    # 牌型分析
    hand_strength = analyze_hand_strength(hole, community)
    draw_potential = analyze_draw_potential(hole, community)

    result = {
        "win_rate": round(win_rate * 100, 1),
        "tie_rate": round(tie_rate * 100, 1),
        "lose_rate": round(lose_rate * 100, 1),
        "equity": round(simulation['equity'] * 100, 2),
        "method": simulation['method'],
        "samples": simulation['samples'],
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
        ev = simulation['equity'] * (pot + call_amount) - call_amount

        # 行动建议
        if call_amount == 0:
            action = "✅ 无需跟注，可过牌；加注需额外策略分析"
        elif ev > 10:
            action = "✅ 跟注为正EV（假设此后无额外下注）"
        elif ev > 0:
            action = "🟡 跟注为正EV（假设此后无额外下注）"
        else:
            action = "❌ 建议弃牌 (负EV)"

        result.update({
            "pot_odds": round(pot_odds, 1),
            "ev": round(ev, 1),
            "action_suggestion": action
        })

    return jsonify(result)


if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)